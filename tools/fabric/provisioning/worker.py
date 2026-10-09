#!/usr/bin/env python3
"""tools/fabric/provisioning/worker.py — the host half of new-agent: what
touches THIS machine (the account, its home, the installers, the host keys,
the clones, bootstrap, the binding, the toolchain), run on the host the
account is placed on, through runtime/hostexec/hostexec; it knows nothing of
the account's secrets (ADR-038). A step-runner (ADR-040 rule 1): sudo,
useradd and the vendors' installers run here as argument lists, never a
shell string. Ported from runtime/provisioning/new-agent-worker.sh (off
shell); the entry on the path is a few lines that find the pinned Python
(runtime/provisioning/new-agent-worker.sh), and what it must decide is asked
of tools/fabric/new_agent_worker.py (its arguments, the claude version, the
subordinate id range, the host keys an account lacks, the verification).

    worker.py prepare <login> (<role> | --human) [--claude V] [--dry-run]    0-4 (a human, ADR-044: 0, 1, 4)
    worker.py finish  <login> (<role> | --human) [--clone <id>=<remote>]... [--claude-account <slug>=<fp12> |
                      --no-claude-account] [--signing-key-next] [--via-host <id>] [--dry-run]     6-10 (a human: 10)
    worker.py host-check <login>      hostname -s, then whether the account exists

Every step is must, probe or best_effort (tests/test_new_agent_cli.py fails
each must): a must that fails ends the run, named, and nothing after it ran —
every step is idempotent, so the fix and a re-run converge; a probe is a
question, asked in a dry run too; a best_effort is a warning and the run goes
on. A dry run prints `would: <what>` for each step that changes anything and
runs no step.

CONTRACT, frozen from the shell
  env     SUDO (sudo; a test's fake, split into words — read from the running
          operator's own environment: hostexec's ssh forwards none, so whoever
          sets it already is that operator), AGENT_FABRIC_CLONE_URL (the
          fabric's https clone URL), AGENT_FABRIC_ETC (the subordinate id
          files' directory), AGENT_FABRIC_PLATFORM, and PATH: every external
          command is found there (a test fakes them)
  stderr  every line, `new-agent: <what>` (the steps numbered as the
          orchestrator's closing numbers them)
  exit    0 done; 1 a must failed or a refusal; 2 usage (new_agent_worker.args)
"""
from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import dataclass, field

HERE = os.path.dirname(os.path.realpath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, TOOLS)
import roots  # noqa: E402
from provisioning import host_platform  # noqa: E402
import new_agent_worker as nw  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(TOOLS))
PY = "/usr/local/bin/fabric-python"
CALL_TIMEOUT_S = 3600           # an installer, a clone, bootstrap: none waits on a person
PROBE_TIMEOUT_S = 120


class Stop(Exception):
    def __init__(self, code: int):
        self.code = code


def _log(text: str) -> None:
    sys.stderr.write(text)
    sys.stderr.flush()


@dataclass
class Worker:
    a: "nw.WorkerArgs"
    root: str = ROOT
    sudo: list[str] = field(default_factory=lambda: ["sudo"])
    env: Mapping[str, str] = field(default_factory=lambda: os.environ)
    home: str = ""
    group: str = ""

    # ── the vocabulary: say, die, run, must, probe, best_effort ──────

    def say(self, text: str) -> None:
        _log(f"new-agent: {text}\n")

    def die(self, text: str) -> None:
        self.say(text)
        raise Stop(1)

    def _exec(self, argv: list[str], *, stdin: str | None = None, capture: bool = False, quiet: bool = False,
              timeout: float = CALL_TIMEOUT_S) -> subprocess.CompletedProcess:
        _log("")
        sys.stdout.flush()
        out = subprocess.PIPE if capture else subprocess.DEVNULL if quiet else None
        return subprocess.run(argv, input=stdin, text=True, timeout=timeout, stdout=out,
                              stderr=subprocess.STDOUT if capture else subprocess.DEVNULL if quiet else None)

    def run(self, argv: list[str], *, describe: str | None = None, stdin: str | None = None, quiet: bool = False) -> int:
        if self.a.dry:
            self.say(f"would: {describe or ' '.join(argv)}")
            return 0
        return self._exec(argv, stdin=stdin, quiet=quiet).returncode

    def must(self, argv: list[str], *, describe: str | None = None, stdin: str | None = None, quiet: bool = False) -> None:
        if self.run(argv, describe=describe, stdin=stdin, quiet=quiet) != 0:
            self.die(f"step failed: {describe or ' '.join(argv)} — nothing after it ran; fix the cause and re-run "
                     "(every step is idempotent)")

    def probe(self, argv: list[str]) -> int:
        try:
            return self._exec(argv, capture=True, timeout=PROBE_TIMEOUT_S).returncode
        except (OSError, subprocess.TimeoutExpired):
            return 127

    def best_effort(self, argv: list[str]) -> None:
        if self.run(argv) != 0:
            self.say(f"warning: {' '.join(argv)} failed; continuing")

    # ── as the account, in a login shell ──────────────────────────────

    def as_login_argv(self, argv: list[str], cwd: str | None = None) -> list[str]:
        """The command as the account, in a LOGIN shell (its profile: what its installers put on PATH). The PATH is
        re-asserted INSIDE the shell: Debian's /etc/profile assigns PATH outright for a non-root login, so what env
        -i set would be gone by the time the command runs (found by the Debian smoke container, which then downloaded
        the real claude in place of the test's fake)."""
        p = f"/usr/local/bin:/usr/bin:/bin:{self.home}/.local/bin"
        script = 'export PATH="$AGENT_FABRIC_PATH:$PATH"; cd "${AGENT_FABRIC_CWD:-$HOME}" && exec "$@"'
        env = [f"HOME={self.home}", f"PATH={p}", f"AGENT_FABRIC_PATH={p}"]
        if cwd:
            env.append(f"AGENT_FABRIC_CWD={cwd}")
        return [*self.sudo, "-n", "-u", self.a.login, "-H", "env", "-i", *env, "bash", "-lc", script, "_", *argv]

    def as_login(self, argv: list[str], *, cwd: str | None = None, stdin: str | None = None,
                 timeout: float = CALL_TIMEOUT_S) -> subprocess.CompletedProcess:
        """Run it as the account, output captured (stdout and stderr together)."""
        _log("")
        try:
            return subprocess.run(self.as_login_argv(argv, cwd), input=stdin, text=True, timeout=timeout,
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        except (OSError, subprocess.TimeoutExpired) as e:
            return subprocess.CompletedProcess(argv, 127, f"{e}\n", None)

    def as_login_out(self, argv: list[str], **kw) -> str:
        """What the command printed, or "" when it failed: `$(as_login …)` with a quiet stderr."""
        got = self.as_login(argv, **kw)
        return (got.stdout or "") if got.returncode == 0 else ""

    def must_as_login(self, argv: list[str], describe: str, *, cwd: str | None = None, quiet: bool = False) -> None:
        """`must as_login "<line>"`: the run shows the shell line that did it; its output is the run's."""
        full = f"as_login {describe}"
        if self.a.dry:
            self.say(f"would: {full}")
            return
        _log("")
        try:
            quiet_out = subprocess.DEVNULL if quiet else None
            done = subprocess.run(self.as_login_argv(argv, cwd), timeout=CALL_TIMEOUT_S, stdout=quiet_out, stderr=quiet_out)
            rc = done.returncode
        except (OSError, subprocess.TimeoutExpired):
            rc = 127
        if rc != 0:
            self.die(f"step failed: {full} — nothing after it ran; fix the cause and re-run (every step is idempotent)")

    def sudo_test(self, flag: str, path: str) -> bool:
        return self.probe([*self.sudo, "-n", "test", flag, path]) == 0

    # ── the pieces a step needs from the host ─────────────────────────

    def getent_home(self) -> str:
        got = subprocess.run(["getent", "passwd", self.a.login], capture_output=True, text=True, timeout=PROBE_TIMEOUT_S)
        fields = (got.stdout or "").strip().split("\n")[0].split(":")
        return fields[5] if got.returncode == 0 and len(fields) > 5 and fields[5] else ""

    def account_exists(self) -> bool:
        return subprocess.run(["getent", "passwd", self.a.login], capture_output=True, timeout=PROBE_TIMEOUT_S).returncode == 0

    def settle_home(self) -> None:
        self.home = self.getent_home() or f"/home/{self.a.login}"

    def primary_group(self) -> str:
        got = subprocess.run(["id", "-gn", self.a.login], capture_output=True, text=True, timeout=PROBE_TIMEOUT_S)
        return (got.stdout or "").strip() if got.returncode == 0 and (got.stdout or "").strip() else self.a.login


# ── the pieces of a step ───────────────────────────────────────────────

PYTHON_FLOOR_CHECK = ("import sys; m = tuple(int(x) for x in sys.argv[1].split(\".\")); "
                      "sys.exit(sys.version_info[:2] < m)")
CLAUDE_INSTALLER = "https://claude.ai/install.sh"
ORI_INSTALLER = "https://openrouter.ai/labs/ori/install.sh"


def host_python_ok() -> bool:
    got = subprocess.run(["python3", "-c", PYTHON_FLOOR_CHECK, ".".join(str(n) for n in host_platform.FABRIC_HOST_PYTHON_MIN)],
                         capture_output=True, timeout=PROBE_TIMEOUT_S)
    return got.returncode == 0


def tail(text: str, n: int = 5) -> None:
    for line in (text or "").splitlines()[-n:]:
        _log(line + "\n")


def vendor_install(w: Worker, url: str, extra: list[str]) -> tuple[bool, str]:
    """`curl -fsSL --proto '=https' -m 120 <url> | bash -s -- <extra>` as the account, as two commands: the vendor's
    script from curl, then to bash on stdin. Fails when either does (the shell's pipefail); the output of both is
    the log."""
    fetched = subprocess.run(w.as_login_argv(["curl", "-fsSL", "--proto", "=https", "-m", "120", url]), text=True,
                             capture_output=True, timeout=CALL_TIMEOUT_S)
    if fetched.returncode != 0:
        return False, (fetched.stderr or "") + (fetched.stdout or "")
    ran = w.as_login(["bash", "-s", *(["--", *extra] if extra else [])], stdin=fetched.stdout)
    return ran.returncode == 0, (fetched.stderr or "") + (ran.stdout or "")


# ── prepare: 0-4 (a human: 0, 1, 4) ────────────────────────────────────

def prepare(w: Worker) -> int:
    a = w.a
    login, etc = a.login, w.env.get("AGENT_FABRIC_ETC") or "/etc"
    w.settle_home()
    # ---- 0. the host: the fabric's contract (host_platform), each missing tool's package
    prof = host_platform.profile(host_platform.detect(w.env))
    missing = sorted({prof.pkg_for(t) for t in host_platform.FABRIC_HOST_TOOLS if shutil.which(t) is None})
    if shutil.which("python3") and not host_python_ok():
        said = subprocess.run(["python3", "-V"], capture_output=True, text=True, timeout=PROBE_TIMEOUT_S)
        version = ((said.stdout or "") + (said.stderr or "")).strip()
        floor = ".".join(str(n) for n in host_platform.FABRIC_HOST_PYTHON_MIN)
        w.die(f"this host's python3 ({version}) is older than {floor}, the fabric's floor (ADR-040 rule 1); "
              "install a newer python3, then rerun")
    _log(nw.audit(prof.id, "1" if prof.persists_across_reboot else "0", prof.pkg_install_hint,
                  str(len(host_platform.FABRIC_HOST_TOOLS)), missing))
    # ---- 1. the account, its subordinate ids, home 700, the shared cache, linger
    if w.account_exists():
        w.say(f"1. account {login} exists")
    else:
        w.must([*w.sudo, "-n", "useradd", "-m", "-s", "/bin/bash", "-c", f"agent-fabric {a.role or 'human'}", login])
        w.say(f"1. account {login} created")
    w.settle_home()
    try:
        plan = nw.subids(login, etc).rstrip("\n")
    except (OSError, ValueError):
        w.die(f"the subordinate id plan for {login} could not be made")
    if plan.startswith("have "):
        w.say(f"   subuid/subgid: {plan[len('have '):]}")
    elif plan.startswith("alloc "):
        r = plan[len("alloc "):]
        start, end = (int(n) for n in r.split("-"))
        if a.dry:
            w.say(f"would: usermod --add-subuids {r} --add-subgids (the same) {login}")
        else:
            w.must([*w.sudo, "-n", "usermod", "--add-subuids", r, "--add-subgids", r, login])
            w.say(f"   subuid/subgid: {start}:{end - start + 1} allocated (rootless podman needs both)")
    w.group = w.primary_group()
    w.must([*w.sudo, "-n", "chmod", "700", w.home])
    if w.probe(["getent", "group", "otscache"]) == 0:
        groups = subprocess.run(["id", "-nG", login], capture_output=True, text=True, timeout=PROBE_TIMEOUT_S)
        if "otscache" not in (groups.stdout or "").split():
            w.best_effort([*w.sudo, "-n", "usermod", "-aG", "otscache", login])
            w.say("   otscache (the shared timestamp cache): joined")
    # Survive the host's reboot: linger everywhere; on Qubes the record goes into the /rw snapshot (after the group join).
    w.must([*w.sudo, "-n", PY, "-I", os.path.join(w.root, "tools", "fabric", "provisioning", "persist_accounts.py"), login])
    w.say("   persisted across reboot (linger" + ("" if prof.persists_across_reboot else "; record snapshot under /rw") + ")")
    if not a.human:     # 2-3 never for a human (ADR-044 rule 2)
        install_claude_and_ori(w)
        trust_github_host_keys(w)
    fabric_checkout(w)
    return 0


def install_claude_and_ori(w: Worker) -> None:
    """---- 2. the home skeleton, then claude and ori from their vendors' installers, as the account."""
    a, h = w.a, w.home
    login = a.login
    w.must([*w.sudo, "-n", "-u", login, "mkdir", "-p", *(os.path.join(h, d) for d in (
        "projects", ".ssh", ".claude", ".config/gh", ".local/bin", ".local/share/claude/versions"))])
    w.must([*w.sudo, "-n", "-u", login, "chmod", "700", os.path.join(h, ".ssh")])
    w.must([*w.sudo, "-n", "chown", f"{login}:{w.group}", *(os.path.join(h, d) for d in (".local", ".local/bin", ".local/share"))])
    want = nw.claude_want(w.root, a.claude)
    resolved = want
    if want == "latest":
        got = subprocess.run(["curl", "-fsSL", "-m", "20", "https://downloads.claude.ai/claude-code-releases/latest"],
                             capture_output=True, text=True, timeout=PROBE_TIMEOUT_S) if shutil.which("curl") else None
        text = "".join((got.stdout or "").split()) if got is not None and got.returncode == 0 else ""
        resolved = text if re.match(r"[0-9]+\.[0-9]+\.[0-9]+", text) else ""
    claude = os.path.join(h, ".local", "bin", "claude")
    have = ""
    if w.as_login(["test", "-e", claude]).returncode == 0:
        target = w.as_login_out(["readlink", "-f", claude]).strip()
        have = os.path.basename(target) if target else ""
    if have and resolved and have == resolved:
        w.say(f"2. claude {have} present (= {want})")
    elif a.dry:
        w.say(f"would: as {login}: curl -fsSL {CLAUDE_INSTALLER} | bash -s -- {want}")
    else:
        done, log = vendor_install(w, CLAUDE_INSTALLER, [want])
        if not (done and w.as_login(["claude", "--version"]).returncode == 0):
            tail(log)
            w.die(f"step failed: claude — the vendor's installer failed for {login} (target {want}); nothing after it ran")
        version = (w.as_login_out(["claude", "--version"]).split() or [""])[0]
        w.say(f"2. claude {version} installed by the vendor's installer ({want}{', was ' + have if have else ''})")
    ori = os.path.join(h, ".local", "bin", "ori")
    if w.as_login(["test", "-x", ori]).returncode == 0:
        first = (w.as_login_out(["ori", "--version"]).split("\n") or [""])[0]
        w.say(f"   ori {first[:24]} present")
    elif a.dry:
        w.say(f"would: as {login}: curl -fsSL {ORI_INSTALLER} | bash")
    else:
        done, log = vendor_install(w, ORI_INSTALLER, [])
        if not (done and w.as_login(["test", "-x", ori]).returncode == 0):
            tail(log)
            w.die(f"step failed: ori — the vendor's installer failed for {login}; nothing after it ran")
        w.say("   ori installed by the vendor's installer")


def trust_github_host_keys(w: Worker) -> None:
    """---- 3. GitHub's published host keys, never a keyscan."""
    host_keys = os.path.join(w.root, "runtime", "provisioning", "github-host-keys")
    if not os.path.isfile(host_keys) or os.path.getsize(host_keys) == 0:
        w.die(f"step failed: {host_keys} is missing or empty; nothing after it ran")
    known = os.path.join(w.home, ".ssh", "known_hosts")
    held = subprocess.run([*w.sudo, "-n", "cat", known], capture_output=True, text=True, timeout=PROBE_TIMEOUT_S)
    try:
        # A known_hosts not there yet (a new account) holds no key: every published one is missing.
        missing = nw.missing_keys(host_keys, held.stdout if held.returncode == 0 else "")
    except OSError:
        w.die(f"step failed: the host keys {w.a.login} lacks could not be read; nothing after it ran")
    if not missing.strip("\n"):
        with open(host_keys, encoding="utf-8") as fh:
            published = sum(1 for ln in fh.read().splitlines() if ln)
        w.say(f"3. github.com host keys trusted ({published} published keys)")
    elif w.a.dry:
        w.say(f"would: append GitHub's published host keys (runtime/provisioning/github-host-keys) to {known}")
    else:
        w.must([*w.sudo, "-n", "-u", w.a.login, "tee", "-a", known], stdin=missing.rstrip("\n") + "\n", quiet=True,
               describe=f"append the published host keys to {known}")
        w.must([*w.sudo, "-n", "-u", w.a.login, "chmod", "600", known])
        w.say("3. github.com host keys trusted (from the committed published set)")


def fabric_checkout(w: Worker) -> None:
    """---- 4. the fabric checkout: a clone already there is brought to origin/main, never left old (bootstrap and the
    launcher run from it), or refused off main."""
    login, repo = w.a.login, os.path.join(w.home, "projects", "agent-fabric")
    if not w.sudo_test("-d", os.path.join(repo, ".git")):
        url = w.env.get("AGENT_FABRIC_CLONE_URL") or "https://github.com/gzapi-org/agent-fabric.git"
        w.must_as_login(["git", "clone", "-q", url, repo], f"git clone -q '{url}' ~/projects/agent-fabric")
        w.say("4. agent-fabric cloned (https; the fabric is public)")
        return
    branch = w.as_login_out(["git", "-C", repo, "symbolic-ref", "-q", "--short", "HEAD"]).strip("\n")
    if branch != "main":
        w.die(f"step failed: ~/projects/agent-fabric is on {branch or 'a detached HEAD'}, not main; bring it to main as "
              f"{login}, then re-run; nothing after it ran")
    w.must_as_login(["timeout", "60", "git", "-C", repo, "fetch", "-q", "origin", "main"],
                    "timeout 60 git -C ~/projects/agent-fabric fetch -q origin main")
    ahead = w.as_login_out(["git", "-C", repo, "rev-list", "--count", "origin/main..HEAD"]).strip("\n")
    if not w.a.dry and ahead != "0":
        w.die(f"step failed: ~/projects/agent-fabric has {ahead or 'an unknown number of'} commit(s) not on origin/main "
              f"(pull --ff-only would keep them); push or drop them as {login}, then re-run; nothing after it ran")
    w.must_as_login(["git", "-C", repo, "merge", "-q", "--ff-only", "origin/main"],
                    "git -C ~/projects/agent-fabric merge -q --ff-only origin/main")
    if not w.a.dry:
        sha = w.as_login_out(["git", "-C", repo, "rev-parse", "--short", "HEAD"]).strip("\n")
        w.say(f"4. ~/projects/agent-fabric at origin/main ({sha})")


# ── finish: 6-10 (a human: 10) ─────────────────────────────────────────

def finish(w: Worker) -> int:
    a = w.a
    w.settle_home()
    for pid in a.projects:
        check = roots.project_integration(pid, "provisioning", "host-check.sh", engine=w.root)
        if os.access(check, os.X_OK):
            got = subprocess.run(["bash", check], capture_output=True, text=True, timeout=PROBE_TIMEOUT_S, stdin=subprocess.DEVNULL,
                                 stderr=subprocess.STDOUT)
            for line in (got.stdout or "").splitlines():
                _log(f"   {line}\n")
    # ---- 6. each project's clone, as the account, over SSH
    for pid in a.projects:
        if w.sudo_test("-d", os.path.join(w.home, "projects", pid, ".git")):
            w.say(f"6. ~/projects/{pid} present")
        else:
            remote = a.remote.get(pid, "")
            w.must_as_login(["git", "clone", "-q", remote, os.path.join(w.home, "projects", pid)],
                            f"git clone -q '{remote}' ~/projects/'{pid}'")
            w.say(f"6. {pid} cloned from {remote}")
    if not a.human:     # 7-9 never for a human (ADR-044 rule 2)
        bootstrap_and_bind(w)
        toolchains(w)
    # ---- 10. verify, and what is left for a person
    if a.dry:
        w.say("dry run: nothing verified")
        return 0
    w.say("10. verification")
    return verify(w)


def bootstrap_and_bind(w: Worker) -> None:
    """---- 7. bootstrap; 8. the role, bound from the first clone."""
    a, h = w.a, w.home
    login = a.login
    if a.dry:
        w.say(f"would: as {login}: bootstrap.sh")
    else:
        got = w.as_login([os.path.join(h, "projects", "agent-fabric", "runtime", "claude-code", "bootstrap.sh")])
        if got.returncode != 0:
            tail(got.stdout)
            w.die(f"step failed: bootstrap.sh as {login}; nothing after it ran")
        for line in (got.stdout or "").splitlines()[-1:]:
            _log(f"   {line}\n")
    w.say("7. bootstrap run")
    first = a.projects[0] if a.projects else ""
    where = "~/projects" + (f"/{first}" if first else "")
    cwd = os.path.join(h, "projects", first) if first else os.path.join(h, "projects")
    fabric_role = os.path.join(h, "projects", "agent-fabric", "bin", "fabric-role")
    status = subprocess.run(w.as_login_argv([fabric_role, "status"]), text=True, capture_output=True, timeout=PROBE_TIMEOUT_S)
    # awk's answer, whatever status said (the shell's pipeline ended in awk): the lines `role <name>`.
    bound = "\n".join(ln.split()[1] for ln in (status.stdout or "").splitlines() if ln.startswith("role") and len(ln.split()) > 1)
    if bound == a.role:
        w.say(f"8. role {a.role} already bound")
        return
    if a.dry:
        w.say(f"would: as_login cd {where} && bin/fabric-role bind '{a.role}'")
    else:
        got = w.as_login([fabric_role, "bind", a.role], cwd=cwd)
        if got.returncode != 0:
            tail(got.stdout)
            w.die(f"step failed: fabric-role bind {a.role} as {login}; nothing after it ran")
        for line in (got.stdout or "").splitlines():
            if re.search(r"bound|refus", line, re.I):
                _log(f"   {line}\n")
    w.say(f"8. role {a.role} bound (from {where})")


def toolchains(w: Worker) -> None:
    """---- 9. the toolchain each project declares, from its lockfile."""
    h = w.home
    for pid in w.a.projects:
        wc = os.path.join(h, "projects", pid)
        if w.sudo_test("-f", os.path.join(wc, "pnpm-lock.yaml")):
            if w.as_login(["bash", "-c", "command -v pnpm >/dev/null"]).returncode != 0:
                w.must_as_login(["npm", "config", "set", "prefix", os.path.join(h, ".local")],
                                "npm config set prefix ~/.local && npm i -g pnpm >/dev/null")
                w.must_as_login(["npm", "i", "-g", "pnpm"], "npm config set prefix ~/.local && npm i -g pnpm >/dev/null", quiet=True)
                w.say("9. pnpm installed under ~/.local")
            if w.sudo_test("-d", os.path.join(wc, "node_modules")):
                w.say(f"9. {pid}: node_modules present")
            else:
                w.must_as_login(["pnpm", "install", "--frozen-lockfile"], f"cd ~/projects/'{pid}' && pnpm install --frozen-lockfile >/dev/null 2>&1",
                                cwd=wc, quiet=True)
                w.say(f"9. {pid}: pnpm install")
        elif w.sudo_test("-f", os.path.join(wc, "package-lock.json")):
            if w.sudo_test("-d", os.path.join(wc, "node_modules")):
                w.say(f"9. {pid}: node_modules present")
            else:
                w.must_as_login(["npm", "ci"], f"cd ~/projects/'{pid}' && npm ci >/dev/null 2>&1", cwd=wc, quiet=True)
                w.say(f"9. {pid}: npm ci")
        elif w.sudo_test("-f", os.path.join(wc, "requirements.txt")):
            if w.sudo_test("-d", os.path.join(wc, ".venv")):
                w.say(f"9. {pid}: .venv present")
            else:
                describe = f"cd ~/projects/'{pid}' && python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt"
                w.must_as_login(["python3", "-m", "venv", ".venv"], describe, cwd=wc)
                w.must_as_login([".venv/bin/pip", "install", "-q", "-r", "requirements.txt"], describe, cwd=wc)
                w.say(f"9. {pid}: venv")


def verify(w: Worker) -> int:
    a = w.a
    sudo = " ".join(w.sudo)
    if a.human:
        text, failed = nw.verify_human(a.login, w.home, sudo)
    else:
        text, failed = nw.verify(w.root, a.login, w.home, sudo, a.projects, account=a.account, no_account=a.no_account,
                                 signing_next=a.signing_next, via=a.via)
    _log(text + failed)
    return 1 if failed else 0


# ── the entry ──────────────────────────────────────────────────────────

def main(argv: list[str] | None = None, environ: Mapping[str, str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    env = os.environ if environ is None else environ
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="surrogateescape")
    try:
        args = nw.parse_args(argv)
    except nw.Exit as exc:
        print(exc.msg, file=sys.stderr)
        return exc.code
    try:
        if args.phase == "host-check":
            sys.stdout.write(nw.host_check(args.login))
            return 0
        w = Worker(args, ROOT, shlex.split(env.get("SUDO") or "sudo"), env)
        w.settle_home()
        w.group = w.primary_group()
        if not args.dry and w.probe([*w.sudo, "-n", "true"]) != 0:
            host = subprocess.run(["hostname", "-s"], capture_output=True, text=True, timeout=PROBE_TIMEOUT_S).stdout.strip()
            w.die(f"sudo without a password is needed for the account steps (the operator on {host} has none).")
        return prepare(w) if args.phase == "prepare" else finish(w)
    except Stop as stop:
        return stop.code
    except nw.Exit as exc:
        print(exc.msg, file=sys.stderr)
        return exc.code
    # A question that got no answer is not a "no": the step is neither done nor failed by a guess.
    except subprocess.TimeoutExpired as exc:
        print(f"new-agent: {exc.cmd[0]}: no answer within {exc.timeout:g} s", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"new-agent: {exc.filename}: {exc.strerror}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
