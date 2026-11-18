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
of its siblings here (worker_args: its arguments; host_steps: the claude version,
the subordinate id range, the host keys an account lacks; verify: the read-back).

    worker.py prepare <login> (<role> | --human) [--claude V] [--dry-run]    0-4 (a human, ADR-044: 0, 1, 4)
    worker.py finish  <login> (<role> | --human) [--clone <id>=<remote>]... [--claude-account <slug>=<fp12> |
                      --no-claude-account] [--signing-key-next] [--via-host <id>] [--fabric-remote <url>] [--dry-run]     6-10 (a human: 10)
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
  exit    0 done; 1 a must failed or a refusal; 2 usage (worker_args); 3 every step ran but something is left open
          (the account's roster row for the coordinator, its key not yet on origin/main, or no user manager to start the units in: carrier_step.py)
"""
from __future__ import annotations

import json
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
import project_clone as pc  # noqa: E402
import python_pin  # noqa: E402
import roots  # noqa: E402
from provisioning import carrier_step, host_platform, host_steps as hs, launch_record as lr, verify as vf, worker_args as wa  # noqa: E402

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
    a: "wa.WorkerArgs"
    root: str = ROOT
    sudo: list[str] = field(default_factory=lambda: ["sudo"])
    env: Mapping[str, str] = field(default_factory=lambda: os.environ)
    home: str = ""
    group: str = ""
    py: str = PY

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
        try:
            failed = self.run(argv) != 0
        except (OSError, subprocess.TimeoutExpired):
            failed = True      # a step that may fail may also not start or not answer
        if failed:
            self.say(f"warning: {' '.join(argv)} failed; continuing")

    # ── as the account, in a login shell ──────────────────────────────

    def as_login_argv(self, argv: list[str], cwd: str | None = None, *, login_shell: bool = True,
                      env: list[str] | None = None) -> list[str]:
        """The command as the account, in a LOGIN shell (its profile: what its installers put on PATH). The PATH is
        re-asserted INSIDE the shell: Debian's /etc/profile assigns PATH outright for a non-root login, so what env
        -i set would be gone by the time the command runs (found by the Debian smoke container, which then downloaded
        the real claude in place of the test's fake).

        `login_shell=False` where no profile can change the answer — `test` and `readlink` on a path — and in the two
        calls that predate this rule: the vendor download (its stdout becomes the installer's script) and
        launch_record.py. Everything else that runs a tool (git, claude, ori, installers) keeps the profile, so a read
        and the write beside it see one environment; each login shell costs about 25 execs of /etc/profile.d."""
        p = f"/usr/local/bin:/usr/bin:/bin:{self.home}/.local/bin"
        script = 'export PATH="$AGENT_FABRIC_PATH:$PATH"; cd "${AGENT_FABRIC_CWD:-$HOME}" && exec "$@"'
        pairs = [f"HOME={self.home}", f"PATH={p}", f"AGENT_FABRIC_PATH={p}", *(env or [])]
        if cwd:
            pairs.append(f"AGENT_FABRIC_CWD={cwd}")
        return [*self.sudo, "-n", "-u", self.a.login, "-H", "env", "-i", *pairs, "bash", "-lc" if login_shell else "-c", script, "_", *argv]

    def as_login(self, argv: list[str], *, cwd: str | None = None, stdin: str | None = None,
                 timeout: float = CALL_TIMEOUT_S, stderr: int = subprocess.STDOUT,
                 login_shell: bool = True, env: list[str] | None = None) -> subprocess.CompletedProcess:
        """Run it as the account, output captured (stdout and stderr together unless `stderr` says otherwise)."""
        _log("")
        try:
            return subprocess.run(self.as_login_argv(argv, cwd, login_shell=login_shell, env=env), input=stdin, text=True, timeout=timeout,
                                  stdout=subprocess.PIPE, stderr=stderr)
        except (OSError, subprocess.TimeoutExpired) as e:
            return subprocess.CompletedProcess(argv, 127, f"{e}\n", None)

    def as_login_out(self, argv: list[str], **kw) -> str:
        """What the command printed, or "" when it failed: `$(as_login … 2>/dev/null)`. A profile or git that writes
        to stderr and exits 0 must not become the value."""
        got = self.as_login(argv, stderr=subprocess.DEVNULL, **kw)
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

    def must_as_login_seq(self, argvs: list[list[str]], describe: str, *, cwd: str | None = None) -> None:
        """One shell step of several commands: a dry run says it once, a real run stops at the first that fails."""
        if self.a.dry:
            self.say(f"would: as_login {describe}")
            return
        for argv in argvs:
            self.must_as_login(argv, describe, cwd=cwd, quiet=argv[0] == "npm" and argv[1:2] == ["i"])

    def sudo_test(self, flag: str, path: str) -> bool:
        return self.probe([*self.sudo, "-n", "test", flag, path]) == 0

    def path_kinds(self, paths: list[str]) -> dict[str, str]:
        """What each path is — "dir", "file", "other" or "absent" — in ONE call, as the account (never root: the
        account owns every path asked about, and a probe that needs root to stat a path is a wider root surface).
        An answer that is not exactly one tagged line per path, or a path the account cannot stat for any reason but
        its absence, stops the run: `sudo test` read every failure as "no", which an unknown is not."""
        if not paths:
            return {}
        # No account yet (a dry run plans one): its home is absent, and `sudo -u` of a login that does not exist is
        # an error, not an answer.
        if not self.account_exists():
            return dict.fromkeys(paths, "absent")
        got = self.as_login([self.py, "-I", "-c", PATH_PROBE, *paths], login_shell=False, timeout=PROBE_TIMEOUT_S)
        try:
            if got.returncode != 0:
                refused = next((ln for ln in (got.stdout or "").splitlines() if ln.startswith("new-agent-path-error: ")), "")
                raise ValueError(refused.removeprefix("new-agent-path-error: ") or f"the probe exited {got.returncode}")
            tags = parse_tags(got.stdout or "", "path")
            if sorted(tags) != sorted(str(i) for i in range(len(paths))) or not set(tags.values()) <= {"dir", "file", "other", "absent"}:
                raise ValueError("it answered other than one kind per path")
        except ValueError as exc:
            tail(got.stdout)
            self.die(f"step failed: could not read {len(paths)} path(s) as {self.a.login} ({exc}); nothing after it ran")
        return {p: tags[str(i)] for i, p in enumerate(paths)}

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

# Run as the account with the paths as argv: one "new-agent-path<TAB>index<TAB>kind" line each. os.stat follows links as `test -d/-f` do;
# ENOENT and ENOTDIR are what `test` read as "no" and the only errors that mean "absent" — any other (EACCES, EIO) is an exception
# and a non-zero exit, so an unreadable path is never taken for a missing one.
PATH_PROBE = """import os, stat, sys
for i, p in enumerate(sys.argv[1:]):
    try:
        m = os.stat(p).st_mode
        kind = "dir" if stat.S_ISDIR(m) else "file" if stat.S_ISREG(m) else "other"
    except (FileNotFoundError, NotADirectoryError):
        kind = "absent"
    except OSError as e:
        print("new-agent-path-error: %s: %s" % (p, e.strerror), flush=True)
        sys.exit(1)
    print("new-agent-path\\t%d\\t%s" % (i, kind), flush=True)
"""

# A batched step's answer: one "new-agent-<kind><TAB><name><TAB><value>" line per check on stdout. A login shell's profile may print
# anything else there, so only these lines count, and a repeated name or a tag line of the wrong shape is no answer.
def parse_tags(text: str, kind: str) -> dict[str, str]:
    prefix = f"new-agent-{kind}\t"
    tags: dict[str, str] = {}
    for line in text.splitlines():
        if not line.startswith(prefix):
            continue
        parts = line[len(prefix):].split("\t")
        if len(parts) != 2 or not parts[0] or parts[0] in tags:
            raise ValueError(f"a malformed or repeated {kind} line")
        tags[parts[0]] = parts[1]
    return tags


CLAUDE_INSTALLER = "https://claude.ai/install.sh"
ORI_INSTALLER = "https://openrouter.ai/labs/ori/install.sh"


def pin_problem(root: str) -> str | None:
    """None when fabric-python is installed and is the build runtime/python.json pins; otherwise what is wrong.
    Unreadable pin is a problem too, never "fine": an unknown pin cannot be matched."""
    try:
        return python_pin.check(python_pin.pin(os.path.join(root, "runtime", "python.json")))
    except python_pin.PinError as exc:
        return str(exc)
    except (TypeError, AttributeError) as exc:    # valid JSON of the wrong shape: python_pin.pin() indexes it unchecked
        return f"runtime/python.json unreadable: not the pin's shape ({type(exc).__name__})"


def tail(text: str, n: int = 5) -> None:
    # The batched steps' own tag lines are the protocol, not what a person needs to read.
    for line in [ln for ln in (text or "").splitlines() if not ln.startswith(("new-agent-path\t", "new-agent-step\t"))][-n:]:
        _log(line + "\n")


def vendor_install(w: Worker, url: str, extra: list[str]) -> tuple[bool, str]:
    """`curl -fsSL --proto '=https' -m 120 <url> | bash -s -- <extra>` as the account, as two commands: the vendor's
    script from curl, then to bash on stdin. Fails when either does (the shell's pipefail); the output of both is
    the log."""
    # No login shell for the download: whatever a profile prints on stdout would be prepended to the vendor's script
    # and run by bash. The shell ran the whole pipe inside the login shell, where that output never entered it.
    fetched = subprocess.run(w.as_login_argv(["curl", "-fsSL", "--proto", "=https", "-m", "120", url], login_shell=False), text=True,
                             capture_output=True, timeout=CALL_TIMEOUT_S)
    if fetched.returncode != 0:
        return False, (fetched.stderr or "") + (fetched.stdout or "")
    ran = w.as_login(["bash", "-s", *(["--", *extra] if extra else [])], stdin=fetched.stdout)
    return ran.returncode == 0, (fetched.stderr or "") + (ran.stdout or "")


# ── prepare: 0-4 (a human: 0, 1, 4) ────────────────────────────────────

def prepare(w: Worker) -> int:
    a = w.a
    login, etc = a.login, w.env.get("AGENT_FABRIC_ETC") or "/etc"
    # ---- 0. the host: the fabric's contract (host_platform), each missing tool's package
    prof = host_platform.profile(host_platform.detect(w.env))
    absent = [t for t in host_platform.FABRIC_HOST_TOOLS if shutil.which(t) is None]
    missing, unpackaged = host_platform.split_missing(prof, absent)
    # One Python on every host, the pin (the owner's word, 2026-11-11): the host's own python3 is never asked its
    # version here; only python_pin.py and the entries ADR-040 rule 4 still lists run on it.
    problem = pin_problem(w.root)
    if problem:
        w.die(f"the fleet's pinned Python is not in place: {problem}; as root: "
              f"/usr/bin/python3 {os.path.join(w.root, 'tools', 'fabric', 'python_pin.py')} install, then rerun")
    # The operator's own tools are asked about for the operator's login (--human) only: no role account calls them.
    operator_missing = sorted({prof.pkg_for(t) for t in host_platform.FABRIC_OPERATOR_TOOLS if shutil.which(t) is None}) if a.human else []
    _log(hs.audit(prof.id, "1" if prof.persists_across_reboot else "0", prof.pkg_install_hint,
                  str(len(host_platform.FABRIC_HOST_TOOLS)), missing, operator_missing=operator_missing, unpackaged=unpackaged,
                  template=host_platform.template_name(prof) if (missing or operator_missing) else ""))
    # ---- 1. the account, its subordinate ids, home 700, the shared cache, linger
    if w.account_exists():
        w.say(f"1. account {login} exists")
    else:
        w.must([*w.sudo, "-n", "useradd", "-m", "-s", "/bin/bash", "-c", f"agent-fabric {a.role or 'human'}", login])
        w.say(f"1. account {login} created")
    w.settle_home()
    try:
        plan = hs.subids(login, etc).rstrip("\n")
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
    want = hs.claude_want(w.root, a.claude)
    resolved = want
    if want == "latest":
        got = subprocess.run(["curl", "-fsSL", "-m", "20", "https://downloads.claude.ai/claude-code-releases/latest"],
                             capture_output=True, text=True, timeout=PROBE_TIMEOUT_S) if shutil.which("curl") else None
        text = "".join((got.stdout or "").split()) if got is not None and got.returncode == 0 else ""
        resolved = text if re.match(r"[0-9]+\.[0-9]+\.[0-9]+", text) else ""
    claude = os.path.join(h, ".local", "bin", "claude")
    # One call for "is there one, and what does it point at": -e fails on a missing or dangling link where -f would answer
    # with the path it would have, so the answer is "" exactly when `test -e` said no.
    target = w.as_login_out(["readlink", "-e", claude], login_shell=False).strip()
    have = os.path.basename(target) if target else ""
    present = bool(have and resolved and have == resolved)
    refused = None if present else hs.claude_install_refusal(w.root, want)
    if present:
        w.say(f"2. claude {have} present (= {want})")
    elif a.dry:
        w.say(f"would refuse: claude {want}: {refused}" if refused else
              f"would: as {login}: curl -fsSL {CLAUDE_INSTALLER} | bash -s -- {want}")
    elif refused:
        w.die(f"step failed: claude {want} for {login}: {refused}")
    else:
        done, log = vendor_install(w, CLAUDE_INSTALLER, [want])
        # One run answers both: whether it starts, and what it says (stderr apart, as the version is stdout's).
        ran = w.as_login(["claude", "--version"], stderr=subprocess.DEVNULL) if done else None
        if ran is None or ran.returncode != 0:
            tail(log)
            w.die(f"step failed: claude — the vendor's installer failed for {login} (target {want}); nothing after it ran")
        version = ((ran.stdout or "").split() or [""])[0]
        w.say(f"2. claude {version} installed by the vendor's installer ({want}{', was ' + have if have else ''})")
    ori = os.path.join(h, ".local", "bin", "ori")
    if w.as_login(["test", "-x", ori], login_shell=False).returncode == 0:
        first = (w.as_login_out(["ori", "--version"]).split("\n") or [""])[0]
        w.say(f"   ori {first[:24]} present")
    elif a.dry:
        w.say(f"would: as {login}: curl -fsSL {ORI_INSTALLER} | bash")
    else:
        done, log = vendor_install(w, ORI_INSTALLER, [])
        if not (done and w.as_login(["test", "-x", ori], login_shell=False).returncode == 0):
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
        missing = hs.missing_keys(host_keys, held.stdout if held.returncode == 0 else "")
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


# Step 4's git reads and writes as ONE login shell (each costs about 25 execs of /etc/profile.d), stopping where the run would:
# a branch other than main, a failed fetch, commits not on origin/main, a failed merge. One tag line per check it reached. In a dry
# run only the branch is read: the fetch and the merge are said, never made.
FABRIC_UPDATE = r'''repo=$1; mode=$2
tag() { printf '\nnew-agent-step\t%s\t%s\n' "$1" "$2"; }   # a leading newline: a profile's unterminated line cannot glue to the tag
branch=$(git -C "$repo" symbolic-ref -q --short HEAD 2>/dev/null); tag branch "$branch"
[ "$branch" = main ] && [ "$mode" = real ] || exit 0
timeout 60 git -C "$repo" fetch -q origin main; rc=$?; tag fetch "$rc"; [ "$rc" = 0 ] || exit 0
ahead=$(git -C "$repo" rev-list --count origin/main..HEAD 2>/dev/null); tag ahead "$ahead"; [ "$ahead" = 0 ] || exit 0
git -C "$repo" merge -q --ff-only origin/main; rc=$?; tag merge "$rc"; [ "$rc" = 0 ] || exit 0
tag sha "$(git -C "$repo" rev-parse --short HEAD 2>/dev/null)"
'''


def fabric_checkout(w: Worker) -> None:
    """---- 4. the fabric checkout: a clone already there is brought to origin/main, never left old (bootstrap and the
    launcher run from it), or refused off main."""
    login, repo = w.a.login, roots.account_clone(w.home)
    git_dir = os.path.join(repo, ".git")
    if w.path_kinds([git_dir])[git_dir] != "dir":
        url = w.env.get("AGENT_FABRIC_CLONE_URL") or "https://github.com/BlueTeam-OU/agent-fabric.git"
        w.must_as_login(["git", "clone", "-q", url, repo], f"git clone -q '{url}' ~/projects/agent-fabric")
        w.say("4. agent-fabric cloned (https; the fabric is public)")
        return
    got = w.as_login(["bash", "-c", FABRIC_UPDATE, "_", repo, "dry" if w.a.dry else "real"])
    try:
        tags = parse_tags(got.stdout or "", "step")
    except ValueError as exc:
        tags = {}
        why = str(exc)
    else:
        why = "no answer to the branch question"
    if "branch" not in tags:
        tail(got.stdout)
        w.die(f"step failed: the checkout ~/projects/agent-fabric could not be read as {login} ({why}); nothing after it ran")
    if tags["branch"] != "main":
        w.die(f"step failed: ~/projects/agent-fabric is on {tags['branch'] or 'a detached HEAD'}, not main; bring it to main as "
              f"{login}, then re-run; nothing after it ran")

    def reached(name: str, describe: str) -> str:
        """The tag of a check the script ran, or a stop naming it: a missing tag is the script not running to it, never a pass."""
        if name not in tags:
            tail(got.stdout)
            w.die(f"step failed: {describe} gave no answer as {login} (the batched step 4 stopped short); nothing after it ran")
        return tags[name]

    fetch_line = "timeout 60 git -C ~/projects/agent-fabric fetch -q origin main"
    merge_line = "git -C ~/projects/agent-fabric merge -q --ff-only origin/main"
    if w.a.dry:
        w.say(f"would: as_login {fetch_line}")
        w.say(f"would: as_login {merge_line}")
        return
    if reached("fetch", fetch_line) != "0":
        tail(got.stdout)
        w.die(f"step failed: as_login {fetch_line} — nothing after it ran; fix the cause and re-run (every step is idempotent)")
    ahead = reached("ahead", "counting the commits not on origin/main")
    if ahead != "0":
        w.die(f"step failed: ~/projects/agent-fabric has {ahead or 'an unknown number of'} commit(s) not on origin/main "
              f"(pull --ff-only would keep them); push or drop them as {login}, then re-run; nothing after it ran")
    if reached("merge", merge_line) != "0":
        tail(got.stdout)
        w.die(f"step failed: as_login {merge_line} — nothing after it ran; fix the cause and re-run (every step is idempotent)")
    w.say(f"4. ~/projects/agent-fabric at origin/main ({reached('sha', 'reading the checkout')})")


# ── finish: 6-10 (a human: 10) ─────────────────────────────────────────

def finish(w: Worker) -> int:
    a = w.a
    # A project named twice is one project: the batched answers below are read once, before any clone or install.
    a.projects = list(dict.fromkeys(a.projects))
    w.settle_home()
    for pid in a.projects:
        # A Python probe (ADR-040) is run with the pin; a project that still has a script gets it run by bash.
        py_check = roots.project_integration(pid, "provisioning", "host_check.py", engine=w.root)
        check = roots.project_integration(pid, "provisioning", "host-check.sh", engine=w.root)
        argv = [PY, "-I", py_check] if os.path.isfile(py_check) else ["bash", check]
        if os.access(argv[-1], os.R_OK if argv[0] == PY else os.X_OK):
            # A probe: its output is shown indented, its status is ignored, and it never ends the run.
            try:
                got = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                     timeout=PROBE_TIMEOUT_S, stdin=subprocess.DEVNULL)
            except (OSError, subprocess.TimeoutExpired) as e:
                _log(f"   {pid}: host-check did not run to its end ({type(e).__name__})\n")
                continue
            for line in (got.stdout or "").splitlines():
                _log(f"   {line}\n")
    # ---- 6. each project's clone, as the account, over SSH
    # One question for every project, asked before the first clone: a clone of one makes nothing the others ask about.
    # (Duplicates were removed above: a second pass over a name would read this stale answer.)
    clone_git = {pid: os.path.join(w.home, "projects", pid, ".git") for pid in a.projects}
    held = w.path_kinds(list(clone_git.values()))
    for pid in a.projects:
        if held[clone_git[pid]] == "dir":
            w.say(f"6. ~/projects/{pid} present")
            point_origin_at_registry(w, pid, a.remote.get(pid, ""))
        else:
            remote = a.remote.get(pid, "")
            w.must_as_login(["git", "clone", "-q", remote, os.path.join(w.home, "projects", pid)],
                            f"git clone -q '{remote}' ~/projects/'{pid}'")
            w.say(f"6. {pid} cloned from {remote}")
    # Step 4's https clone is the one that stays when agent-fabric is not a --project: the loop above never saw it.
    # A dry run has made no clone yet, so there is nothing to read. Asked after the clones, with the operator checkout's
    # module: a clone of agent-fabric as a project can bring that module.
    fabric_git, module = roots.account_clone(w.home, ".git"), roots.account_clone(w.home, "tools", "fabric", "operator_checkout.py")
    after = w.path_kinds([fabric_git, module])
    if a.fabric_remote and "agent-fabric" not in a.projects and after[fabric_git] == "dir":
        point_origin_at_registry(w, "agent-fabric", a.fabric_remote)
    operator_checkout_step(w, after[module])
    open_: list[str] = []
    if not a.human:     # 7-9 never for a human (ADR-044 rule 2)
        record_launch_provider(w)
        bootstrap_and_bind(w)
        install_client(w)
        open_ = carrier_step.carrier_steps(w)
        toolchains(w)
        operator_ssh(w)
    # ---- 10. verify, and what is left for a person
    if a.dry:
        w.say("dry run: nothing verified")
        return 0
    w.say("10. verification")
    rc = verify(w)
    if rc == 0 and open_:
        for line in open_:
            w.say(f"open: {line}")
        return carrier_step.OPEN_EXIT
    return rc


def operator_checkout_step(w: Worker, module_kind: str | None = None) -> None:
    """---- 6c. the operator's checkout beside the engine (ADR-045 §6), cloned over SSH like a project's, by the
    account's own copy of the module that bootstrap also runs. Never fatal: the account works without it (nothing
    resolves through it yet), the module's line says what is missing, and bootstrap tries again at step 7."""
    module = roots.account_clone(w.home, "tools", "fabric", "operator_checkout.py")
    if (w.path_kinds([module])[module] if module_kind is None else module_kind) != "file":
        w.say("6c. the operator checkout is not provisioned: this fabric clone has no operator_checkout.py yet")
        return
    argv = [PY, "-I", module, "ensure", "--projects", os.path.join(w.home, "projects")]
    if w.a.dry:
        argv.append("--dry-run")
    got = w.as_login(argv)
    said = (got.stdout or "").strip()
    w.say(f"6c. {said}" if said else "6c. the operator checkout is current" if got.returncode == 0
          else f"6c. the operator checkout step exited {got.returncode}; carrying on")


def point_origin_at_registry(w: Worker, pid: str, remote: str) -> None:
    """A clone that is already there keeps the origin it was made with (project_clone.plan_origin says why and
    when it is rewritten); this reads the two settings as the account and does what the plan says."""
    if not remote:
        return
    repo = os.path.join(w.home, "projects", pid)
    # One read of both settings (the account's shell costs a login each): --null keeps a value with a newline in it whole,
    # and the last of each key wins, as --get gives it. No url, however it failed, is "unreadable".
    got = w.as_login(["git", "-C", repo, "config", "--null", "--get-regexp", r"^remote\.origin\.(url|pushurl)$"],
                     stderr=subprocess.DEVNULL)
    seen: dict[str, str] = {}
    if got.returncode == 0:
        for entry in (got.stdout or "").split("\0"):
            key, _, value = entry.partition("\n")
            seen[key.lower()] = value
    have = seen.get("remote.origin.url", "")
    pushurl = seen.get("remote.origin.pushurl", "")
    plan = pc.plan_origin(remote, have, pushurl)
    if plan.action == "unreadable":
        w.say(f"6. {pid}: origin not readable; left as it is")
        return
    if plan.action == "set":
        w.must_as_login(["git", "-C", repo, "remote", "set-url", "origin", remote],
                        f"git -C ~/projects/'{pid}' remote set-url origin '{remote}'")
        if not w.a.dry:
            w.say(f"6. {pid}: origin set to {remote}")
    if plan.warning:
        w.say(f"6. {pid}: warning: {plan.warning}")


def record_launch_provider(w: Worker) -> None:
    """---- 6b. the provider of the account's first launch. Before bootstrap, which installs the agent files for the
    recorded provider. A role whose provider nothing names is left to the launcher's default, said."""
    a = w.a
    profile = lr.profile_provider(roots.routing_profiles(engine=w.root), a.login, a.role)
    provider = lr.choose(profile, a.account, a.no_account)
    if provider is None:
        w.say("6b. no launch provider recorded: no profile layer names one and no Claude account was asked for")
        return
    # The account's own clone (step 4 brought it to origin/main), not this worker's checkout: homes are 700, so the
    # account cannot read the coordinator's tree it is run from.
    record = roots.account_clone(w.home, "tools", "fabric", "provisioning", "launch_record.py")
    if a.dry:
        w.say(f"would: as {a.login}: launch_record.py {provider}")
        return
    got = w.as_login([PY, "-I", record, provider], login_shell=False)
    if got.returncode != 0:
        tail(got.stdout)
        w.die(f"step failed: launch_record.py {provider} as {a.login}; nothing after it ran")
    w.say(f"6b. first launch on {provider} recorded")


def bootstrap_and_bind(w: Worker) -> None:
    """---- 7. bootstrap; 8. the role, bound from the first clone."""
    a, h = w.a, w.home
    login = a.login
    if a.dry:
        w.say(f"would: as {login}: bootstrap.sh")
    else:
        got = w.as_login([roots.account_clone(h, "runtime", "claude-code", "bootstrap.sh")])
        if got.returncode != 0:
            tail(got.stdout)
            w.die(f"step failed: bootstrap.sh as {login}; nothing after it ran")
        for line in (got.stdout or "").splitlines()[-1:]:
            _log(f"   {line}\n")
    w.say("7. bootstrap run")
    first = a.projects[0] if a.projects else ""
    where = "~/projects" + (f"/{first}" if first else "")
    cwd = os.path.join(h, "projects", first) if first else os.path.join(h, "projects")
    fabric_role = roots.account_clone(h, "bin", "fabric-role")
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


def operator_ssh(w: Worker) -> None:
    """---- 9b. the operator's ssh into the account (ADR-048), on a host whose registry entry pins an sshd: the login
    joins AllowUsers and gets its root-owned keys file from the staging ssh-operator.sh made (ssh_add_login.py has what
    it trusts), with no reboot. A host without the pin has no sshd staged; that is said, not made up. The pin is read
    from THIS host's checkout, which a far host may not have updated yet: then the step says it is skipped and
    `sudo fabric-python -I tools/fabric/provisioning/ssh_add_login.py <login>` is the line to run once it has."""
    here = hs.host_check(w.a.login).split("\n", 1)[0]
    path = roots.hosts_registry(engine=w.root)
    try:
        with open(path, encoding="utf-8") as fh:
            entry = ((json.load(fh).get("hosts") or {}).get(here) or {})
    except (OSError, ValueError, AttributeError) as exc:
        w.die(f"step failed: the host registry {path} could not be read for the sshd pin ({exc}); nothing after it ran")
    if not isinstance(entry, dict) or not isinstance(entry.get("sshd"), dict):
        w.say(f"9b. ssh: {here} pins no sshd in this checkout's registry; the operator's ssh is not set up for {w.a.login} "
              f"(once it is: sudo {PY} -I {os.path.join(w.root, 'tools', 'fabric', 'provisioning', 'ssh_add_login.py')} {w.a.login})")
        return
    script = os.path.join(w.root, "tools", "fabric", "provisioning", "ssh_add_login.py")
    w.must([*w.sudo, "-n", PY, "-I", script, w.a.login], describe=f"{script} {w.a.login} (the operator's ssh)")
    if not w.a.dry:
        w.say(f"9b. ssh: {w.a.login} is in AllowUsers with its keys file, sshd restarted")


def install_client(w: Worker) -> None:
    """---- 7b. the program of the carrier's client unit (ADR-064 §5 rule 5), from the account's own clone as step 6b
    does: homes are 700. After bootstrap only by habit, not need: the program finds gzcoord-carrier when the unit
    starts, not when it is installed."""
    login = w.a.login
    script = roots.account_clone(w.home, "tools", "fabric", "gzcoord", "carrier", "install_client.py")
    if w.a.dry:
        w.say(f"would: as {login}: install_client.py")
        return
    got = w.as_login([PY, "-I", script], login_shell=False)
    if got.returncode != 0:
        tail(got.stdout)
        w.die(f"step failed: install_client.py as {login}; nothing after it ran")
    # The installer's own word tells a write from a re-run that found it in place.
    w.say("7b. carrier client unit program " + ("already in place" if "install_client: already" in (got.stdout or "") else "installed"))


def toolchains(w: Worker) -> None:
    """---- 9. the toolchain each project declares, from its lockfile."""
    h = w.home
    # One question for every project's files, asked once the clones are in and before the first install: one project's
    # install writes nothing another's answers depend on.
    names = ("pnpm-lock.yaml", "package-lock.json", "requirements.txt", "node_modules", ".venv")
    kinds = w.path_kinds([os.path.join(h, "projects", pid, n) for pid in w.a.projects for n in names])

    def has(wc: str, name: str, kind: str) -> bool:
        return kinds[os.path.join(wc, name)] == kind
    for pid in w.a.projects:
        wc = os.path.join(h, "projects", pid)
        if has(wc, "pnpm-lock.yaml", "file"):
            if w.as_login(["bash", "-c", "command -v pnpm >/dev/null"]).returncode != 0:
                w.must_as_login_seq([["npm", "config", "set", "prefix", os.path.join(h, ".local")], ["npm", "i", "-g", "pnpm"]],
                                    "npm config set prefix ~/.local && npm i -g pnpm >/dev/null")
                w.say("9. pnpm installed under ~/.local")
            if has(wc, "node_modules", "dir"):
                w.say(f"9. {pid}: node_modules present")
            else:
                w.must_as_login(["pnpm", "install", "--frozen-lockfile"], f"cd ~/projects/'{pid}' && pnpm install --frozen-lockfile >/dev/null 2>&1",
                                cwd=wc, quiet=True)
                w.say(f"9. {pid}: pnpm install")
        elif has(wc, "package-lock.json", "file"):
            if has(wc, "node_modules", "dir"):
                w.say(f"9. {pid}: node_modules present")
            else:
                w.must_as_login(["npm", "ci"], f"cd ~/projects/'{pid}' && npm ci >/dev/null 2>&1", cwd=wc, quiet=True)
                w.say(f"9. {pid}: npm ci")
        elif has(wc, "requirements.txt", "file"):
            if has(wc, ".venv", "dir"):
                w.say(f"9. {pid}: .venv present")
            else:
                describe = f"cd ~/projects/'{pid}' && python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt"
                w.must_as_login_seq([["python3", "-m", "venv", ".venv"], [".venv/bin/pip", "install", "-q", "-r", "requirements.txt"]],
                                    describe, cwd=wc)
                w.say(f"9. {pid}: venv")


def verify(w: Worker) -> int:
    a = w.a
    sudo = " ".join(w.sudo)
    try:
        if a.human:
            text, failed = vf.verify_human(a.login, w.home, sudo)
        else:
            text, failed = vf.verify(w.root, a.login, w.home, sudo, a.projects, account=a.account, no_account=a.no_account,
                                     signing_next=a.signing_next, via=a.via)
    except vf.ReadbackError as exc:
        # No frame is no answer, and no answer is never "verified": the step fails and says why, with no closing to trust.
        w.say(f"step failed: {exc}; nothing was verified")
        return 1
    _log(text + failed)
    return 1 if failed else 0


# ── the entry ──────────────────────────────────────────────────────────

def main(argv: list[str] | None = None, environ: Mapping[str, str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    env = os.environ if environ is None else environ
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="surrogateescape")
    try:
        args = wa.parse_args(argv)
    except wa.Exit as exc:
        print(exc.msg, file=sys.stderr)
        return exc.code
    try:
        if args.phase == "host-check":
            sys.stdout.write(hs.host_check(args.login))
            return 0
        # No home or group is read here: each phase settles what it uses (prepare after the account exists, finish at its
        # start), and a read made before them is one getent and one id for an answer nothing consumes.
        w = Worker(args, ROOT, shlex.split(env.get("SUDO") or "sudo"), env)
        if not args.dry and w.probe([*w.sudo, "-n", "true"]) != 0:
            host = subprocess.run(["hostname", "-s"], capture_output=True, text=True, timeout=PROBE_TIMEOUT_S).stdout.strip()
            w.die(f"sudo without a password is needed for the account steps (the operator on {host} has none).")
        return prepare(w) if args.phase == "prepare" else finish(w)
    except Stop as stop:
        return stop.code
    except wa.Exit as exc:
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
