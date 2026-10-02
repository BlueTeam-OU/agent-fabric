#!/usr/bin/env python3
"""The oracle for runtime/claude-code/bootstrap.sh: what it writes, leaves
alone and removes in an account, step by step (1-8), what it prints on
which stream, its exit status, and that a second run changes nothing.

The script under test is the path in $BOOTSTRAP, default
runtime/claude-code/bootstrap.sh, so one file runs against a port's shim and
against the bash it replaced. It is never run where it lies: it derives its
checkout and the workspace from its own location, so it is copied into a
scratch fabric (an archive of this checkout's HEAD, committed in a fresh
repository) inside a scratch workspace inside a scratch HOME, and run there.

Nothing it runs reaches this account: HOME, CLAUDE_CONFIG_DIR, the XDG
directories and TMPDIR are under one mkdtemp; PATH holds only fakes (which
record their argv) and links to the plain tools the script needs, so
systemctl, loginctl, curl, ss, pgrep, claude, pip and uv are fakes and the
real ones are not on it; `python3 -m venv` is intercepted by a python3
wrapper. Paths the script derives from elsewhere: XDG_RUNTIME_DIR falls back
to /run/user/<uid> (always set here), `id -un` and the passwd entry are read,
never written.

Exit codes: 0 all assertions passed, 1 one or more failed."""
from __future__ import annotations

import hashlib
import json
import os
import pwd
import shutil
import stat
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.abspath(os.environ.get("BOOTSTRAP") or os.path.join(HERE, "runtime", "claude-code", "bootstrap.sh"))
if not os.path.isfile(SCRIPT):
    sys.exit(f"test: script under test not found at {SCRIPT}")

REAL_PYTHON = shutil.which("python3") or sys.executable
LOGIN = pwd.getpwuid(os.geteuid()).pw_name
UID = os.geteuid()
REAL_HOME = pwd.getpwuid(os.geteuid()).pw_dir
UNIT = "agent-fabric-agentd"
RELAY = "gzcoord-relay"
HOOK_REL = "policies/githooks"
# The plain tools the script and what it runs call. Anything not here, and
# not a fake, is "command not found": a port that starts calling something
# new shows up as a failure rather than reaching the host.
SYSTOOLS = ("bash", "sh", "env", "git", "cmp", "install", "mkdir", "cp", "rm", "grep", "dirname", "readlink",
            "ln", "mktemp", "id", "sed", "cut", "head", "tail", "chmod", "cat", "ls", "sort", "tr", "basename",
            "uname", "date", "mv", "touch", "wc", "awk", "realpath", "stat", "printf", "true", "false", "test")
FAKES = ("systemctl", "loginctl", "curl", "ss", "pgrep", "claude", "pip", "pip3", "uv", "sudo", "python3")

fails = 0
T = ""


def ok(label: str) -> None:
    print(f"  ok   {label.replace(T, '$T') if T else label}")


def fail(label: str, detail: str = "") -> None:
    global fails
    fails += 1
    print(f"  FAIL {label}")
    # The scratch root is long and in every path: shown as $T.
    for line in str(detail).replace(T, "$T").splitlines() if T else str(detail).splitlines():
        print(f"      {line}")


def check(label: str, good: bool, detail: object = "") -> None:
    ok(label) if good else fail(label, str(detail))


def put(path: str, content: str, mode: int | None = None) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    if mode is not None:
        os.chmod(path, mode)


def read(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def git(*args: str, cwd: str | None = None) -> str:
    # The fixture's own git: no global or system config of this account.
    e = {"PATH": "/usr/bin:/bin", "HOME": f"{T}/git-home", "GIT_CONFIG_NOSYSTEM": "1", "LC_ALL": "C.UTF-8"}
    return subprocess.run(["git", "-c", "commit.gpgsign=false", "-c", "user.name=fixture", "-c",
                           "user.email=fixture@example.org", "-c", "init.defaultBranch=main",
                           # No detached auto-gc: it repacks .git/objects while the fixture is copied.
                           "-c", "gc.auto=0", "-c", "maintenance.auto=false", *args],
                          cwd=cwd, env=e, capture_output=True, text=True, check=True).stdout.strip()


def git_config(repo: str, key: str) -> str | None:
    e = {"PATH": "/usr/bin:/bin", "HOME": f"{T}/git-home", "GIT_CONFIG_NOSYSTEM": "1"}
    r = subprocess.run(["git", "-C", repo, "config", "--local", "--get", key], env=e, capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None


# --- the fakes -------------------------------------------------------------

LOGGER = 'printf "%s" "$(basename "$0")" >>"$FAKE_LOG"; for a in "$@"; do printf "\\t%s" "$a" >>"$FAKE_LOG"; done; echo >>"$FAKE_LOG"\n'

FAKE_BODIES = {
    # The user manager: daemon-reload's status and each unit's is-active
    # answer come from the case (FAKE_RELOAD_RC, FAKE_ACTIVE_<unit>).
    "systemctl": r'''
case "$*" in
  "--user daemon-reload") exit "${FAKE_RELOAD_RC:-0}" ;;
  "--user is-active "*) u="${*: -1}"; v="FAKE_ACTIVE_${u//-/_}"; s="${!v:-active}"; echo "$s"; [[ "$s" == active ]]; exit ;;
esac
exit 0
''',
    "curl": 'exit "${FAKE_CURL_RC:-7}"\n',
    "ss": '[[ -n "${FAKE_SS_OUT:-}" ]] && printf "%s\\n" "$FAKE_SS_OUT"; exit 0\n',
    "pgrep": '[[ -n "${FAKE_PGREP_OUT:-}" ]] && { printf "%s\\n" "$FAKE_PGREP_OUT"; exit 0; }; exit 1\n',
    # Claude Code's built-in auto-mode lists, the one call user-settings.py makes.
    "claude": r'''
if [[ "$*" == "auto-mode defaults" ]]; then
  printf '%s\n' '{"environment": ["**Trusted repo**: fixture"], "allow": ["a"], "soft_deny": ["s"], "hard_deny": ["h"]}'
  exit 0
fi
exit 1
''',
    "loginctl": "exit 0\n",
    "pip": "exit 1\n", "pip3": "exit 1\n", "uv": "exit 1\n", "sudo": "exit 1\n",
    # `python3 -m venv DIR` makes a fake venv whose pip "installs" by marker
    # and whose python answers `import pycld2` by that marker; every other
    # python3 call is the real interpreter.
    "python3": r'''
if [[ "${1:-}" == -m && "${2:-}" == venv ]]; then
  [[ -n "${FAKE_VENV_FAIL:-}" ]] && exit 1
  v="${*: -1}"; mkdir -p "$v/bin"
  cat >"$v/bin/python" <<PYW
#!/bin/bash
if [[ "\$*" == "-c import pycld2" ]]; then [[ -e "\$(dirname "\$0")/../pycld2-installed" ]]; exit; fi
exec @PY@ "\$@"
PYW
  cat >"$v/bin/pip" <<'PIP'
#!/bin/bash
printf pip >>"$FAKE_LOG"; for a in "$@"; do printf '\t%s' "$a" >>"$FAKE_LOG"; done; echo >>"$FAKE_LOG"
[[ -n "${FAKE_PIP_FAIL:-}" ]] && exit 1
touch "$(dirname "$0")/../pycld2-installed"
PIP
  chmod 755 "$v/bin/python" "$v/bin/pip"
  exit 0
fi
exec @PY@ "$@"
''',
}


def make_bins() -> None:
    os.makedirs(f"{T}/fakebin")
    os.makedirs(f"{T}/sysbin")
    for name, body in FAKE_BODIES.items():
        # The python3 wrapper logs only the venv call: every python3 the
        # script runs would otherwise flood the log.
        logger = LOGGER
        if name == "python3":
            body = body.replace("@PY@", REAL_PYTHON)
            logger = 'if [[ "${1:-}" == -m && "${2:-}" == venv ]]; then ' + LOGGER.rstrip("\n") + "; fi\n"
        put(f"{T}/fakebin/{name}", "#!/bin/bash\n" + logger + body, 0o755)
    for tool in SYSTOOLS:
        real = shutil.which(tool, path="/usr/bin:/bin")
        if real:
            os.symlink(real, f"{T}/sysbin/{tool}")


def path_without(*tools: str) -> str:
    """A PATH with every fake and plain tool except these: a host that lacks them."""
    d = f"{T}/path-without-{'-'.join(tools)}"
    if not os.path.isdir(d):
        os.makedirs(d)
        for src in (f"{T}/fakebin", f"{T}/sysbin"):
            for n in os.listdir(src):
                if n not in tools and not os.path.lexists(f"{d}/{n}"):
                    os.symlink(os.path.realpath(f"{src}/{n}") if src.endswith("sysbin") else f"{src}/{n}", f"{d}/{n}")
    return d


# --- the fabric and the accounts -------------------------------------------

REGISTRY = {
    "version": 1,
    "projects": {
        "agent-fabric": {"remotes": ["git@github.com:example-org/agent-fabric.git"]},
        "alpha": {"remotes": ["git@github.com:example-org/alpha.git"]},
        "beta": {"remotes": ["https://example.org/beta"]},
        "gamma": {"remotes": ["https://github.com/example-org/gamma"]},
    },
}


def make_pristine(script: str) -> str:
    """The fabric as a fresh checkout: HEAD's tree, the script under test in
    its place, a registry of neutral fixture projects, one commit."""
    d = f"{T}/pristine/agent-fabric"
    os.makedirs(d)
    arch = subprocess.run(["git", "-C", HERE, "archive", "HEAD"], capture_output=True, check=True,
                          env={"PATH": "/usr/bin:/bin", "HOME": f"{T}/git-home", "GIT_CONFIG_NOSYSTEM": "1"}).stdout
    subprocess.run(["tar", "-x", "-C", d], input=arch, check=True)
    shutil.copyfile(script, f"{d}/runtime/claude-code/bootstrap.sh")
    os.chmod(f"{d}/runtime/claude-code/bootstrap.sh", 0o755)
    # The port's module beside the script under test, from the same tree
    # (ADR-040 §5 rule 5): a shim runs whatever module sits next to it.
    module = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(script))), "tools", "fabric", "bootstrap.py")
    if os.path.isfile(module):
        shutil.copyfile(module, f"{d}/tools/fabric/bootstrap.py")
    put(f"{d}/projects/registry.json", json.dumps(REGISTRY, indent=2) + "\n")
    git("init", "-q", d)
    git("-C", d, "add", "-A")
    git("-C", d, "commit", "-q", "-m", "fixture")
    return d


class Account:
    """One scratch account: everything the script may write is under root."""

    def __init__(self, name: str, ws: str = "projects", relay: bool = False, wcs: bool = True) -> None:
        self.root = f"{T}/{name}"
        self.home = f"{self.root}/home"
        self.ws = f"{self.home}/{ws}"
        self.fr = f"{self.ws}/agent-fabric"
        self.cfg = f"{self.root}/claude-config"     # CLAUDE_CONFIG_DIR
        self.state = f"{self.root}/state"           # XDG_STATE_HOME
        self.xdgcfg = f"{self.root}/xdg-config"     # XDG_CONFIG_HOME
        self.run = f"{self.root}/run"               # XDG_RUNTIME_DIR
        self.tmp = f"{self.root}/tmp"               # TMPDIR
        # Outside root, so the tree snapshot sees only what the script wrote.
        self.log = f"{T}/logs/{name}.log"
        os.makedirs(f"{T}/logs", exist_ok=True)
        self.lb = f"{self.home}/.local/bin"
        for d in (self.home, self.ws, self.cfg, self.state, self.xdgcfg, self.run, self.tmp):
            os.makedirs(d, exist_ok=True)
        open(self.log, "w").close()
        shutil.copytree(f"{T}/pristine/agent-fabric", self.fr, symlinks=True)
        self.wc = {}
        if wcs:
            self.make_wcs()
        if relay:
            put(f"{self.ws}/.gzcoord/venv/bin/claude-bridge", "#!/bin/sh\nexit 0\n", 0o755)

    def make_wcs(self) -> None:
        w = self.wc = {n: f"{self.ws}/{n}" for n in ("alpha", "alpha-wt", "beta", "gamma", "notes", "stray")}
        for n in ("alpha", "beta", "gamma", "stray"):
            git("init", "-q", w[n])
        git("-C", w["alpha"], "remote", "add", "origin", "git@github.com:example-org/alpha.git")
        put(f"{w['alpha']}/README", "alpha\n")
        git("-C", w["alpha"], "add", "-A")
        git("-C", w["alpha"], "commit", "-q", "-m", "alpha")
        # A linked worktree: a .git FILE, registered like its main checkout.
        git("-C", w["alpha"], "worktree", "add", "-q", w["alpha-wt"])
        put(f"{w['beta']}/.agent-fabric-project", "beta\n")              # registered by marker, no remote
        git("-C", w["beta"], "config", "core.hooksPath", "/elsewhere/hooks")
        git("-C", w["gamma"], "remote", "add", "origin", "https://github.com/Example-Org/gamma.git")
        git("-C", w["gamma"], "config", "core.hooksPath", f"{self.fr}/{HOOK_REL}")   # already current
        git("-C", w["stray"], "remote", "add", "origin", "git@github.com:example-org/stray.git")
        os.makedirs(w["notes"])

    def env(self, **more: str) -> dict[str, str]:
        e = {"HOME": self.home, "PATH": f"{T}/fakebin:{T}/sysbin", "LC_ALL": "C.UTF-8", "TMPDIR": self.tmp,
             "CLAUDE_CONFIG_DIR": self.cfg, "XDG_STATE_HOME": self.state, "XDG_CONFIG_HOME": self.xdgcfg,
             "XDG_RUNTIME_DIR": self.run, "FAKE_LOG": self.log}
        for k, v in more.items():
            if v is None:
                e.pop(k, None)
            else:
                e[k] = v
        return e

    @property
    def ch(self) -> str:
        return self.cfg

    @property
    def units(self) -> str:
        """Where `systemctl --user` reads unit files: XDG_CONFIG_HOME is always set here."""
        return f"{self.xdgcfg}/systemd/user"

    def bus(self) -> None:
        """A user manager's bus: a socket file is all the script tests for."""
        os.mknod(f"{self.run}/bus", stat.S_IFSOCK | 0o600)

    def calls(self, tool: str | None = None) -> list[list[str]]:
        rows = [line.split("\t") for line in read(self.log).splitlines() if line]
        return [r for r in rows if tool is None or r[0] == tool]

    def clear_log(self) -> None:
        open(self.log, "w").close()


class Run:
    def __init__(self, rc: int, out: str, err: str) -> None:
        self.rc, self.out, self.err = rc, out, err
        self.lines = out.splitlines()

    def __str__(self) -> str:
        return f"rc={self.rc}\n--- stdout\n{self.out}--- stderr\n{self.err}"


def bootstrap(acct: Account, *args: str, env: dict[str, str] | None = None, cwd: str | None = None) -> Run:
    e = env if env is not None else acct.env()
    # The one guard that matters before anything runs: nothing points at
    # this account's own home or configuration.
    for k in ("HOME", "CLAUDE_CONFIG_DIR", "XDG_STATE_HOME", "XDG_CONFIG_HOME", "XDG_RUNTIME_DIR", "TMPDIR"):
        if k in e and not os.path.realpath(e[k]).startswith(T + "/"):
            sys.exit(f"test: refusing to run: {k}={e[k]} is outside {T}")
    if not os.path.realpath(e["HOME"]).startswith(T + "/") or os.path.realpath(e["HOME"]) == os.path.realpath(REAL_HOME):
        sys.exit("test: refusing to run: HOME is not the scratch home")
    for k in e:
        if k.startswith(("AGENT_FABRIC_", "GITHUB_", "GZCOORD_", "GIT_")) or (k.startswith("CLAUDE") and k != "CLAUDE_CONFIG_DIR"):
            if k not in ("AGENT_FABRIC_DEFER_AGENTD_RESTART", "AGENT_FABRIC_LOCAL_BIN"):
                sys.exit(f"test: refusing to run: {k} reaches the script")
    script = f"{acct.fr}/runtime/claude-code/bootstrap.sh"
    p = subprocess.run([script, *args], env=e, capture_output=True, timeout=300, cwd=cwd or acct.root, stdin=subprocess.DEVNULL)
    return Run(p.returncode, p.stdout.decode("utf-8", "surrogateescape"), p.stderr.decode("utf-8", "surrogateescape"))


def snapshot(root: str) -> dict[str, tuple]:
    """Every path under root: its type, mode and content hash (or link target)."""
    snap: dict[str, tuple] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        # The interpreter's bytecode cache, beside each module a python3
        # imports: written by Python, not by the script, even in a dry run.
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        for n in dirnames + filenames:
            p = os.path.join(dirpath, n)
            st = os.lstat(p)
            rel = os.path.relpath(p, root)
            if stat.S_ISLNK(st.st_mode):
                snap[rel] = ("l", os.readlink(p))
            elif stat.S_ISDIR(st.st_mode):
                snap[rel] = ("d", stat.S_IMODE(st.st_mode))
            elif stat.S_ISREG(st.st_mode):
                with open(p, "rb") as f:
                    snap[rel] = ("f", stat.S_IMODE(st.st_mode), hashlib.sha256(f.read()).hexdigest())
            else:
                snap[rel] = ("o", stat.S_IFMT(st.st_mode), stat.S_IMODE(st.st_mode))
    return snap


def diff(a: dict, b: dict) -> str:
    out = []
    for k in sorted(set(a) | set(b)):
        if a.get(k) != b.get(k):
            out.append(f"{k}: {a.get(k)} -> {b.get(k)}")
    return "\n".join(out[:40])


def mode(path: str) -> int:
    return stat.S_IMODE(os.lstat(path).st_mode)


def commands(fr: str) -> list[tuple[str, str]]:
    return list(json.load(open(f"{fr}/runtime/claude-code/commands.json"))["commands"].items())


def expected_settings(fr: str) -> dict:
    tpl = json.load(open(f"{fr}/runtime/claude-code/workspace/settings.json"))
    tpl.pop("_comment")
    return json.loads(json.dumps(tpl).replace("$AGENT_FABRIC_ROOT", fr))


SKILLS = (("subagent-dispatch", "policies/subagent-dispatch/SKILL.md"),
          ("fabric-decisions", "policies/fabric-decisions/SKILL.md"),
          ("branch-hygiene", "policies/branch-hygiene/SKILL.md"),
          ("agent-jobs", "policies/agent-jobs/SKILL.md"),
          ("gzcoord-send", "communication/gzcoord/skills/gzcoord-send/SKILL.md"),
          ("gzcoord-receive", "communication/gzcoord/skills/gzcoord-receive/SKILL.md"))


def between(lines: list[str], first: str, last: str) -> list[str]:
    """The lines strictly between the first line equal to `first` and the
    next equal to `last` ([] when either is missing)."""
    try:
        i = lines.index(first)
        j = lines.index(last, i + 1)
    except ValueError:
        return []
    return lines[i + 1:j]


# --- the cases --------------------------------------------------------------

def first_run() -> None:
    print("bootstrap: a fresh account, no user manager")
    a = Account("fresh")
    P, FR, CH, LB, H = a.ws, a.fr, a.ch, a.lb, a.home
    HOOKS = f"{FR}/{HOOK_REL}"
    VENV = f"{H}/.cache/agent-fabric/langid/venv"
    pkg = json.load(open(f"{FR}/runtime/langid/detector.json"))["package"]
    r = bootstrap(a)
    check("exit 0", r.rc == 0, r)
    check("nothing on stderr", r.err == "", r.err)
    L = r.lines

    # The lines the script itself prints, in order, as a person reads them.
    head = f"agent-fabric bootstrap for agent {LOGIN} — projects: {P}"
    check("the header names the agent by its login and the workspace", L[:1] == [head], L[:1])
    check("step 1 and 2: their lines, after the header",
          L[1:3] == [f"  +  {P}/CLAUDE.md", f"  +  {P}/.claude/settings.json"], L[1:3])

    # Step 1.
    check("step 1: the workspace CLAUDE.md is the template, byte for byte",
          read(f"{P}/CLAUDE.md") == read(f"{FR}/runtime/claude-code/workspace/CLAUDE.md"))
    check("step 1: …mode 644", mode(f"{P}/CLAUDE.md") == 0o644, oct(mode(f"{P}/CLAUDE.md")))
    check("step 1: no backup of a file that was not there", not os.path.exists(f"{P}/CLAUDE.md.before-agent-fabric"))

    # Step 2.
    s = read(f"{P}/.claude/settings.json")
    check("step 2: the workspace settings are the template with the root substituted, _comment dropped",
          json.loads(s) == expected_settings(FR), s[:400])
    want = expected_settings(FR)
    # Key order as the merge builds it over an empty file: statusLine, env, hooks.
    ordered = {"statusLine": want["statusLine"], "env": want["env"], "hooks": want["hooks"]}
    check("step 2: …statusLine, env, hooks, indented by 2, ASCII-escaped, one final newline",
          s == json.dumps(ordered, indent=2) + "\n", s[:300])
    check("step 2: …no $AGENT_FABRIC_ROOT left in it", "$AGENT_FABRIC_ROOT" not in s)
    check("step 2: …mode 644", mode(f"{P}/.claude/settings.json") == 0o644)

    # The agent files block (install-agent-files.sh), passed through.
    guard_line = f"  +  {CH}/hooks/review-bash-guard.sh"
    block = between(L, f"  +  {P}/.claude/settings.json", guard_line)
    agent_lines = [f"  +  {CH}/agents/{c}.md" for c in ("code-low", "code-medium", "code-high", "code-plan", "code-review")]
    check("the capability-class agent files: installed and said, then the installer's summary",
          block[:5] == agent_lines and block[-1] == "agent files (anthropic): 5 written, 0 already current.", "\n".join(block))
    for c in ("code-low", "code-medium", "code-high", "code-plan", "code-review"):
        check(f"…{c}.md under CLAUDE_CONFIG_DIR/agents, mode 644",
              os.path.isfile(f"{CH}/agents/{c}.md") and mode(f"{CH}/agents/{c}.md") == 0o644)
    check("the review guard: the fabric's script, mode 644",
          read(f"{CH}/hooks/review-bash-guard.sh") == read(f"{FR}/runtime/claude-code/hooks/review-bash-guard.sh")
          and mode(f"{CH}/hooks/review-bash-guard.sh") == 0o644)

    # The command links.
    cmds = commands(FR)
    i = L.index(guard_line) if guard_line in L else -1
    want = [f"  +  {LB}/{n} -> {FR}/{rel}" for n, rel in cmds]
    check("the commands: one line each, in commands.json's order, after the guard",
          i >= 0 and L[i + 1:i + 1 + len(cmds)] == want, "\n".join(L[i + 1:i + 1 + len(cmds)]))
    check("…each a symlink to the checkout's script, by absolute path",
          all(os.path.islink(f"{LB}/{n}") and os.readlink(f"{LB}/{n}") == f"{FR}/{rel}" for n, rel in cmds))
    us = f"  +  {CH}/settings.json fabric user settings"
    check("the user settings: said after the links", i >= 0 and L[i + 1 + len(cmds)] == us, L[i + 1 + len(cmds):i + 2 + len(cmds)])
    doc = json.load(open(f"{CH}/settings.json"))
    check("…the attribution reminder off at its source",
          doc.get("attribution") == {"commit": "", "pr": "", "sessionUrl": False}, doc.get("attribution"))
    check("…every allowed command linked is allowed by name, auto mode",
          doc["permissions"]["defaultMode"] == "auto"
          and all(f"Bash({n} *)" in doc["permissions"]["allow"] for n, _ in cmds
                  if n not in json.load(open(f"{FR}/runtime/claude-code/commands.json")).get("not_allowed", {})))
    check("…autoMode from the fake claude's defaults", doc.get("autoMode", {}).get("environment", [None])[0] == "**Trusted repo**: fixture",
          doc.get("autoMode"))
    check("…mode 600", mode(f"{CH}/settings.json") == 0o600, oct(mode(f"{CH}/settings.json")))
    check("…asked of claude once: auto-mode defaults", a.calls("claude") == [["claude", "auto-mode", "defaults"]], a.calls("claude"))

    j = i + 2 + len(cmds)
    want = [f"  +  {CH}/skills/{n}/SKILL.md" for n, _ in SKILLS]
    check("the six skills: one line each, in order", L[j:j + 6] == want, "\n".join(L[j:j + 6]))
    for n, src in SKILLS:
        check(f"…{n}: the fabric's file, mode 644",
              read(f"{CH}/skills/{n}/SKILL.md") == read(f"{FR}/{src}") and mode(f"{CH}/skills/{n}/SKILL.md") == 0o644)
    check("step 3: no /role command to remove, none said", not any("role.md" in x for x in L))

    # Step 4.
    j += 6
    check("step 4: the checkout's hooksPath set, said", L[j] == f"  +  {FR}: core.hooksPath = {HOOK_REL}", L[j])
    check("step 4: …relative, in the checkout's own config", git_config(FR, "core.hooksPath") == HOOK_REL)

    # Step 5.
    w = a.wc
    # The glob's order puts alpha-wt/ before alpha/ ('-' sorts before '/'),
    # and a linked worktree shares its main checkout's config: set through
    # the worktree, alpha is then already current.
    want = [f"  +  {w['alpha-wt']} (alpha): core.hooksPath = {HOOKS}",
            f"  =  {w['alpha']} (alpha): core.hooksPath",
            f"  +  {w['beta']} (beta): core.hooksPath = {HOOKS}",
            f"  =  {w['gamma']} (gamma): core.hooksPath"]
    check("step 5: each registered working copy, in directory order; the current one said =",
          L[j + 1:j + 5] == want, "\n".join(L[j + 1:j + 5]))
    check("step 5: by remote, by marker, a linked worktree: absolute hooksPath",
          all(git_config(w[n], "core.hooksPath") == HOOKS for n in ("alpha", "beta", "gamma"))
          and subprocess.run(["git", "-C", w["alpha-wt"], "config", "--get", "core.hooksPath"], capture_output=True,
                             text=True, env={"PATH": "/usr/bin:/bin", "HOME": f"{T}/git-home"}).stdout.strip() == HOOKS)
    check("step 5: an unregistered remote: no hooksPath", git_config(w["stray"], "core.hooksPath") is None)
    check("step 5: a plain directory stays plain", os.listdir(w["notes"]) == [])

    # Step 5b.
    trusted = [P, FR, w["alpha-wt"], w["alpha"], w["beta"], w["gamma"]]
    want = [f"  +  {d}: trusted in Claude Code" for d in trusted]
    check("step 5b: the workspace, the checkout, each registered working copy trusted, said in that order",
          L[j + 5:j + 11] == want, "\n".join(L[j + 5:j + 11]))
    cj = json.load(open(f"{a.cfg}/.claude.json"))
    check("step 5b: …in CLAUDE_CONFIG_DIR/.claude.json, those and nothing else",
          {k for k, v in cj["projects"].items() if v.get("hasTrustDialogAccepted") is True} == set(trusted), cj.get("projects"))
    check("step 5b: …not in HOME/.claude.json", not os.path.exists(f"{H}/.claude.json"))

    # Step 6.
    unit = f"{a.units}/{UNIT}.service"
    k = j + 11
    check("step 6: the unit installed, and why it is not started",
          L[k:k + 2] == [f"  +  {unit}",
                         f"  !  {UNIT}: installed, not started — no user manager at {a.run}/bus "
                         f"(loginctl enable-linger {LOGIN}, or the next login starts it)"], "\n".join(L[k:k + 2]))
    # The bash wrote the units under HOME/.config whatever XDG_CONFIG_HOME
    # said; `systemctl --user` reads XDG_CONFIG_HOME/systemd/user when set.
    check("step 6: …the fabric's unit, mode 644, under XDG_CONFIG_HOME (where systemctl --user reads)",
          read(unit) == read(f"{FR}/runtime/control/{UNIT}.service") and mode(unit) == 0o644)
    check("step 6: …nothing under HOME/.config/systemd", not os.path.exists(f"{H}/.config/systemd"))
    check("step 6: no user manager: systemctl and loginctl never called", a.calls("systemctl") == [] and a.calls("loginctl") == [],
          a.calls())
    check("step 6b: no relay venv: no relay unit, no relay line",
          not os.path.exists(f"{a.units}/{RELAY}.service") and not any(RELAY in x for x in L))

    # Step 7.
    check("step 7: the detector's venv made and its package installed, said",
          L[k + 2] == f"  +  {VENV} ({pkg})", L[k + 2:k + 3])
    check("step 7: …by the venv's own pip, quietly, the pinned package",
          a.calls("pip") == [["pip", "install", "-q", pkg]] and a.calls("python3") == [["python3", "-m", "venv", VENV]],
          a.calls())
    check("step 7: …its directory mode 700", mode(f"{H}/.cache/agent-fabric/langid") == 0o700)
    check("step 8: nothing of Doppler's here, nothing said", not any("Doppler" in x for x in L))

    # The summary counts the script's own puts, links, the user settings and
    # step 5's lines; the agent files, steps 4, 5b and 7 are not in it.
    n_written = 2 + 1 + len(cmds) + 1 + 6 + 2 + 1
    check("the summary counts what was written",
          L[k + 3:] == [f"bootstrap: {n_written} written, 2 already current.",
                        f"Launch from {P}: cd \"{P}\" && claude   — the session starts as {LOGIN}."], "\n".join(L[k + 3:]))
    check("curl, ss, pgrep, uv and sudo never called",
          not [c for c in a.calls() if c[0] in ("curl", "ss", "pgrep", "uv", "sudo", "pip3")], a.calls())
    check("the script's own temporary directory is gone", os.listdir(a.tmp) == [], os.listdir(a.tmp))

    # Idempotence.
    before = snapshot(a.root)
    a.clear_log()
    r2 = bootstrap(a)
    after = snapshot(a.root)
    check("second run: exit 0, nothing on stderr", r2.rc == 0 and r2.err == "", r2)
    check("second run: the tree is unchanged (paths, modes, content)", before == after, diff(before, after))
    plus = [x for x in r2.lines if x.startswith("  +  ") or x.startswith("  -  ")]
    check("second run: nothing said written or removed", plus == [], "\n".join(plus))
    n_same = 2 + 1 + len(cmds) + 1 + 6 + 4 + 1
    check("second run: the summary says all of it current",
          f"bootstrap: 0 written, {n_same} already current." in r2.lines, r2.out)
    check("second run: step 4 says =", f"  =  {FR}: core.hooksPath = {HOOK_REL}" in r2.lines)
    check("second run: step 7 says =", f"  =  {VENV} ({pkg})" in r2.lines)
    check("second run: the venv was not remade, pip not run", a.calls("pip") == [] and a.calls("python3") == [], a.calls())

    # The dry run over a settled account changes nothing either.
    r3 = bootstrap(a, "--dry-run")
    check("--dry-run over a settled account: exit 0, tree unchanged", r3.rc == 0 and snapshot(a.root) == after, r3)


def dry_run() -> None:
    print("bootstrap: --dry-run on a fresh account")
    a = Account("dry")
    before = snapshot(a.root)
    r = bootstrap(a, "--dry-run")
    after = snapshot(a.root)
    check("exit 0", r.rc == 0, r)
    check("nothing written anywhere", before == after, diff(before, after))
    P, FR, CH = a.ws, a.fr, a.ch
    for line in (f"  +  {P}/CLAUDE.md (would write)",
                 f"  +  {P}/.claude/settings.json (would write)",
                 f"  +  {CH}/hooks/review-bash-guard.sh (would write)",
                 f"  +  {a.lb}/fabric-status -> {FR}/bin/fabric-status (would link)",
                 f"  +  {CH}/settings.json fabric user settings (would write)",
                 f"  +  {FR}: core.hooksPath = {HOOK_REL}",
                 f"  +  {a.wc['alpha']} (alpha): core.hooksPath = {FR}/{HOOK_REL}",
                 f"  +  {P}: trusted in Claude Code (would write)",
                 f"  +  {a.units}/{UNIT}.service (would write)",
                 f"  +  {a.home}/.cache/agent-fabric/langid/venv (would create and install "
                 f"{json.load(open(f'{FR}/runtime/langid/detector.json'))['package']})"):
        check(f"says: {line.strip()[:70]}", line in r.lines, r.out)
    check("no user-manager line in a dry run", not any(UNIT + ":" in x for x in r.lines), r.out)
    check("the summary: nothing written, the step 5 lines counted",
          r.lines[-2] == "bootstrap: 3 written, 1 already current.", r.lines[-2:])
    check("no fake reached but the read of claude's auto-mode defaults",
          a.calls() == [["claude", "auto-mode", "defaults"]], a.calls())


def arguments() -> None:
    print("bootstrap: arguments")
    a = Account("args", wcs=False)
    before = snapshot(a.root)
    r = bootstrap(a, "--bogus")
    check("an unknown argument: exit 2, said on stderr, nothing on stdout",
          r.rc == 2 and r.out == "" and r.err == "bootstrap: unknown argument --bogus\n", r)
    check("…nothing written", snapshot(a.root) == before)
    # --projects names another workspace: the checkout stays where it is.
    other = f"{a.home}/elsewhere"
    os.makedirs(other)
    r = bootstrap(a, "--projects", other)
    check("--projects DIR: exit 0, the workspace files go there", r.rc == 0 and os.path.isfile(f"{other}/CLAUDE.md")
          and os.path.isfile(f"{other}/.claude/settings.json") and not os.path.exists(f"{a.ws}/CLAUDE.md"), r)
    check("…the header names it", r.lines[0].endswith(f"— projects: {other}"), r.lines[:1])
    check("…the settings still point at the checkout", json.load(open(f"{other}/.claude/settings.json")) == expected_settings(a.fr))
    r = bootstrap(a, "--projects", f"{a.home}/missing")
    check("--projects naming no directory: a non-zero exit, nothing on stdout", r.rc != 0 and r.out == "", r)


def existing_files() -> None:
    print("bootstrap: what an account already has")
    a = Account("existing", wcs=False)
    P, CH, LB, FR = a.ws, a.ch, a.lb, a.fr
    put(f"{P}/CLAUDE.md", "my own notes\n")
    # The review guard carries no agent-fabric marker: a person's file there
    # is backed up, and later fabric versions of it must not replace that.
    put(f"{CH}/hooks/review-bash-guard.sh", "my guard\n")
    old_root = "/old/checkout/agent-fabric"
    put(f"{P}/.claude/settings.json", json.dumps({
        "model": "keep-me",
        "env": {"MINE": "1", "CLAUDE_CODE_DISABLE_TERMINAL_TITLE": "0"},
        "statusLine": {"type": "command", "command": "mine"},
        "hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": f"bash {old_root}/runtime/claude-code/hooks/session-start.sh"}]},
                                   {"hooks": [{"type": "command", "command": "echo mine"}]},
                                   {"hooks": [{"type": "command", "command": f"node {old_root}/communication/gzcoord/scripts/inbox.mjs"}]}],
                  "Stop": [{"hooks": [{"type": "command", "command": "echo stop"}]}]}}) + "\n")
    # Step 3: ours goes; a person's, and a backup sibling, stay.
    put(f"{CH}/commands/role.md", "the agent-fabric /role command\n")
    put(f"{CH}/commands/role.md.before-agent-fabric", "theirs\n")
    # The links: a stale one of ours (another checkout, same path) is
    # refreshed; a foreign file and a foreign link are refused.
    os.makedirs(LB)
    os.symlink("/old/checkout/agent-fabric/bin/fabric-whoami", f"{LB}/fabric-whoami")
    put(f"{LB}/fabric-status", "#!/bin/sh\necho mine\n", 0o755)
    os.symlink("/usr/bin/true", f"{LB}/fabric-jobs")
    # Step 8: every Doppler leftover goes.
    put(f"{a.home}/.doppler/.doppler.yaml", "token: x\n")
    put(f"{a.home}/.local/bin/doppler", "#!/bin/sh\n", 0o755)
    put(f"{a.home}/.config/agent-fabric/secrets-source", "doppler\n")
    # Step 5b: the file's other keys are kept.
    put(f"{a.cfg}/.claude.json", json.dumps({"oauthAccount": {"x": 1}, "projects": {"/somewhere": {"a": 1}}}), 0o640)
    r = bootstrap(a)
    check("exit 0 although two links were refused", r.rc == 0, r)
    check("step 1: a person's CLAUDE.md kept as .before-agent-fabric, said",
          os.path.isfile(f"{P}/CLAUDE.md.before-agent-fabric") and read(f"{P}/CLAUDE.md.before-agent-fabric") == "my own notes\n"
          and f"     (kept the previous file as {P}/CLAUDE.md.before-agent-fabric)" in r.lines
          and read(f"{P}/CLAUDE.md") == read(f"{FR}/runtime/claude-code/workspace/CLAUDE.md"), r.out)
    i = r.lines.index(f"     (kept the previous file as {P}/CLAUDE.md.before-agent-fabric)") if \
        f"     (kept the previous file as {P}/CLAUDE.md.before-agent-fabric)" in r.lines else -1
    check("…the backup line before the + line", i > 0 and r.lines[i + 1] == f"  +  {P}/CLAUDE.md", r.out)
    doc = json.load(open(f"{P}/.claude/settings.json"))
    tpl = expected_settings(FR)
    check("step 2: a key the fabric does not own is kept", doc.get("model") == "keep-me")
    check("step 2: env: the template's key set, the account's other key kept",
          doc["env"] == {"MINE": "1", "CLAUDE_CODE_DISABLE_TERMINAL_TITLE": "1"}, doc["env"])
    check("step 2: the status line is the fabric's", doc["statusLine"] == tpl["statusLine"])
    check("step 2: an event's hooks: the account's own first, an old checkout's entries replaced by the fabric's",
          doc["hooks"]["SessionStart"] == [{"hooks": [{"type": "command", "command": "echo mine"}]}] + tpl["hooks"]["SessionStart"],
          json.dumps(doc["hooks"]["SessionStart"], indent=1))
    check("step 2: an event the template has not is kept", doc["hooks"]["Stop"] == [{"hooks": [{"type": "command", "command": "echo stop"}]}])
    check("step 2: no old checkout's path left", "/old/checkout" not in read(f"{P}/.claude/settings.json"))
    check("step 2: a previous file that names agent-fabric is not backed up",
          not os.path.exists(f"{P}/.claude/settings.json.before-agent-fabric"))
    check("step 3: our /role command removed, said",
          not os.path.exists(f"{CH}/commands/role.md")
          and f"  -  {CH}/commands/role.md (removed: /role is retired, use bin/fabric-role)" in r.lines, r.out)
    check("step 3: the backup sibling stays", read(f"{CH}/commands/role.md.before-agent-fabric") == "theirs\n")
    check("links: one of ours from another checkout refreshed",
          os.readlink(f"{LB}/fabric-whoami") == f"{FR}/bin/fabric-whoami"
          and f"  +  {LB}/fabric-whoami -> {FR}/bin/fabric-whoami" in r.lines)
    check("links: a foreign file and a foreign link left alone",
          read(f"{LB}/fabric-status") == "#!/bin/sh\necho mine\n" and os.readlink(f"{LB}/fabric-jobs") == "/usr/bin/true")
    check("links: each refusal on stderr, one line each",
          r.err.splitlines() == [f"  !  {LB}/fabric-status is not a link this fabric made — left alone; fabric-status is not on PATH",
                                 f"  !  {LB}/fabric-jobs is not a link this fabric made — left alone; fabric-jobs is not on PATH"], r.err)
    us = json.load(open(f"{CH}/settings.json"))
    check("user settings: no allow rule for a name whose link is not the fabric's",
          "Bash(fabric-status *)" not in us["permissions"]["allow"] and "Bash(fabric-whoami *)" in us["permissions"]["allow"])
    check("step 8: the Doppler leftovers removed, said in one line",
          "  -  Doppler retired: removed ~/.doppler, ~/.local/bin/doppler, ~/.config/agent-fabric/secrets-source" in r.lines
          and not os.path.lexists(f"{a.home}/.doppler") and not os.path.lexists(f"{a.home}/.local/bin/doppler")
          and not os.path.lexists(f"{a.home}/.config/agent-fabric/secrets-source"), r.out)
    cj = json.load(open(f"{a.cfg}/.claude.json"))
    check("step 5b: the .claude.json's other keys kept, its mode kept",
          cj["oauthAccount"] == {"x": 1} and cj["projects"]["/somewhere"] == {"a": 1} and mode(f"{a.cfg}/.claude.json") == 0o640)
    check("the summary counts the refusals as NOT written", r.lines[-2].endswith(", 2 NOT written (above).")
          and r.lines[-2].startswith("bootstrap: "), r.lines[-2:])
    # A person's own role.md (no marker) is never removed.
    put(f"{CH}/commands/role.md", "my role command\n")
    r = bootstrap(a)
    check("step 3: a person's role.md stays, unsaid", read(f"{CH}/commands/role.md") == "my role command\n"
          and not any("role.md" in x for x in r.lines))
    # The bash backed up again whenever a marker-less fabric file changed,
    # replacing the person's original with the fabric's previous version.
    guard = f"{CH}/hooks/review-bash-guard.sh"
    check("a person's file with no marker kept once as .before-agent-fabric",
          read(f"{guard}.before-agent-fabric") == "my guard\n")
    put(guard, "an older version of the fabric's guard\n")
    r = bootstrap(a)
    check("…a later change of that fabric file keeps the person's backup, and says no backup",
          r.rc == 0 and read(f"{guard}.before-agent-fabric") == "my guard\n"
          and read(guard) == read(f"{FR}/runtime/claude-code/hooks/review-bash-guard.sh")
          and f"     (kept the previous file as {guard}.before-agent-fabric)" not in r.lines and f"  +  {guard}" in r.lines, r)


def no_config_dir() -> None:
    print("bootstrap: CLAUDE_CONFIG_DIR unset, XDG_CONFIG_HOME unset")
    a = Account("noconfig", wcs=False)
    r = bootstrap(a, env=a.env(CLAUDE_CONFIG_DIR=None))
    check("exit 0", r.rc == 0, r)
    for p in ("agents/code-review.md", "hooks/review-bash-guard.sh", "settings.json", "skills/agent-jobs/SKILL.md"):
        check(f"~/.claude/{p}", os.path.isfile(f"{a.home}/.claude/{p}"))
    check("the trust in ~/.claude.json", a.ws in json.load(open(f"{a.home}/.claude.json"))["projects"])
    check("nothing under the unused config dir", os.listdir(a.cfg) == [], os.listdir(a.cfg))
    b = Account("noxdgconfig", wcs=False)
    r = bootstrap(b, env=b.env(XDG_CONFIG_HOME=None))
    check("XDG_CONFIG_HOME unset: the control agent's unit under HOME/.config/systemd/user",
          r.rc == 0 and os.path.isfile(f"{b.home}/.config/systemd/user/{UNIT}.service") and not os.path.exists(b.units), r)


def local_bin_override() -> None:
    print("bootstrap: AGENT_FABRIC_LOCAL_BIN")
    a = Account("localbin", wcs=False)
    lb = f"{a.root}/bin-elsewhere"
    r = bootstrap(a, env=a.env(AGENT_FABRIC_LOCAL_BIN=lb))
    check("exit 0", r.rc == 0, r)
    check("the links go there, not to ~/.local/bin",
          os.path.islink(f"{lb}/fabric-status") and not os.path.lexists(f"{a.lb}/fabric-status"))


def user_manager() -> None:
    print("bootstrap: step 6 with a user manager")
    a = Account("manager", wcs=False)
    a.bus()
    r = bootstrap(a, env=a.env(FAKE_ACTIVE_agent_fabric_agentd="active"))
    check("exit 0, nothing on stderr", r.rc == 0 and r.err == "", r)
    check("reload, enable --now, restart (the unit changed), is-active, in that order",
          a.calls("systemctl") == [["systemctl", "--user", "daemon-reload"], ["systemctl", "--user", "enable", "--now", UNIT],
                                   ["systemctl", "--user", "restart", UNIT], ["systemctl", "--user", "is-active", UNIT]],
          a.calls("systemctl"))
    check("the line says its state",
          f"  *  {UNIT}: active (systemctl --user status {UNIT})" in r.lines, r.out)
    a.clear_log()
    r = bootstrap(a, env=a.env(FAKE_ACTIVE_agent_fabric_agentd="inactive"))
    check("unchanged unit: no restart", a.calls("systemctl") == [["systemctl", "--user", "daemon-reload"],
                                                                ["systemctl", "--user", "enable", "--now", UNIT],
                                                                ["systemctl", "--user", "is-active", UNIT]], a.calls("systemctl"))
    check("…and an inactive unit says so", f"  *  {UNIT}: inactive (systemctl --user status {UNIT})" in r.lines, r.out)
    # A changed unit under the daemon's own upgrade: the restart is its caller's.
    put(f"{a.units}/{UNIT}.service", "[Unit]\nDescription=agent-fabric old\n")
    a.clear_log()
    r = bootstrap(a, env=a.env(AGENT_FABRIC_DEFER_AGENTD_RESTART="1"))
    check("AGENT_FABRIC_DEFER_AGENTD_RESTART: no restart, said",
          ["systemctl", "--user", "restart", UNIT] not in a.calls("systemctl")
          and f"  *  {UNIT}: unit changed; restart left to the caller" in r.lines, f"{a.calls('systemctl')}\n{r.out}")
    a.clear_log()
    r = bootstrap(a, env=a.env(FAKE_RELOAD_RC="1"))
    check("a manager that will not reload: installed, not started, said; nothing enabled",
          a.calls("systemctl") == [["systemctl", "--user", "daemon-reload"]]
          and f"  !  {UNIT}: installed, not started — no user manager at {a.run}/bus (loginctl enable-linger {LOGIN}, or the next login starts it)" in r.lines,
          f"{a.calls('systemctl')}\n{r.out}")
    a.clear_log()
    r = bootstrap(a, env=a.env(PATH=path_without("systemctl")))
    check("no systemctl on the host: installed, not started, exit 0",
          r.rc == 0 and f"  !  {UNIT}: installed, not started — no user manager at {a.run}/bus (loginctl enable-linger {LOGIN}, or the next login starts it)" in r.lines, r)


def relay() -> None:
    print("bootstrap: step 6b, the relay's account")
    a = Account("relay", relay=True, wcs=False)
    unit = f"{a.units}/{RELAY}.service"
    r = bootstrap(a)
    check("no user manager: the relay unit installed, not started, said",
          r.rc == 0 and read(unit) == read(f"{a.fr}/communication/gzcoord/runtime/{RELAY}.service") and mode(unit) == 0o644
          and f"  +  {unit}" in r.lines
          and f"  !  {RELAY}: installed, not started — no user manager at {a.run}/bus" in r.lines, r)
    check("…after the control agent's lines", r.lines.index(f"  +  {unit}") > r.lines.index(
        f"  +  {a.units}/{UNIT}.service"), r.out)

    b = Account("relay-up", relay=True, wcs=False)
    b.bus()
    r = bootstrap(b, env=b.env(FAKE_ACTIVE_gzcoord_relay="active"))
    rc = [c for c in b.calls("systemctl") if c[-1] == RELAY]
    check("a free port: enable --now, restart (the unit changed), is-active",
          rc == [["systemctl", "--user", "is-active", RELAY], ["systemctl", "--user", "enable", "--now", RELAY],
                 ["systemctl", "--user", "restart", RELAY], ["systemctl", "--user", "is-active", RELAY]], rc)
    check("…said", f"  *  {RELAY} (this workspace hosts the relay): active" in r.lines, r.out)
    check("…an active unit's port is not probed", b.calls("curl") == [], b.calls("curl"))
    b.clear_log()
    r = bootstrap(b, env=b.env(FAKE_ACTIVE_gzcoord_relay="inactive", FAKE_CURL_RC="0",
                               FAKE_SS_OUT='LISTEN 0 5 127.0.0.1:8765 0.0.0.0:* users:(("claude-bridge",pid=4242,fd=3))'))
    check("a relay outside the unit holds the port: probed on 127.0.0.1:8765",
          b.calls("curl") == [["curl", "-sf", "-m", "1", "http://127.0.0.1:8765/status"]], b.calls("curl"))
    check("…the holder from ss", b.calls("ss") == [["ss", "-Hltnp", "sport = :8765"]] and b.calls("pgrep") == [], b.calls())
    check("…enabled only, never started or restarted",
          [c for c in b.calls("systemctl") if c[-1] == RELAY] == [["systemctl", "--user", "is-active", RELAY],
                                                                  ["systemctl", "--user", "enable", RELAY]], b.calls("systemctl"))
    check("…said, with the pid",
          f"  !  {RELAY}: enabled, NOT started — a relay outside the unit holds 127.0.0.1:8765 (pid 4242); stop it, then: systemctl --user start {RELAY}" in r.lines, r.out)
    b.clear_log()
    r = bootstrap(b, env=b.env(FAKE_ACTIVE_gzcoord_relay="activating", FAKE_CURL_RC="0",
                               FAKE_SS_OUT='LISTEN 0 5 127.0.0.1:8765 0.0.0.0:* users:(("claude-bridge",pid=4243,fd=3))'))
    check("…a unit crash-looping against it is said as RESTARTING",
          f"  !  {RELAY}: RESTARTING against a relay outside the unit that holds 127.0.0.1:8765 (pid 4243); stop that relay and the unit takes the port (systemctl --user status {RELAY})" in r.lines, r.out)
    # With no pid from ss, the bash ended the run at the holder lookup,
    # silently, exit 1 (grep -o failed under pipefail and set -e). Fixed in
    # the port: the pgrep fallback, then "unknown", as intended.
    held = f"  !  {RELAY}: enabled, NOT started — a relay outside the unit holds 127.0.0.1:8765 (pid %s); stop it, then: systemctl --user start {RELAY}"
    for label, more in (("an ss answer with no pid", {}), ("no ss on the host", {"PATH": path_without("ss")})):
        b.clear_log()
        r = bootstrap(b, env=b.env(FAKE_ACTIVE_gzcoord_relay="inactive", FAKE_CURL_RC="0", FAKE_PGREP_OUT="777", **more))
        check(f"{label}: the holder from pgrep, by this uid and the exact name; enabled only; said; the run goes on, exit 0",
              r.rc == 0 and r.err == "" and held % "777" in r.lines and r.lines[-2].startswith("bootstrap: ")
              and b.calls("pgrep") == [["pgrep", "-u", str(UID), "-x", "claude-bridge"]]
              and [c for c in b.calls("systemctl") if c[-1] == RELAY] == [["systemctl", "--user", "is-active", RELAY],
                                                                          ["systemctl", "--user", "enable", RELAY]], r)
    b.clear_log()
    r = bootstrap(b, env=b.env(FAKE_ACTIVE_gzcoord_relay="inactive", FAKE_CURL_RC="0"))
    check("neither ss nor pgrep names the holder: pid unknown, exit 0",
          r.rc == 0 and held % "unknown" in r.lines and ["systemctl", "--user", "enable", RELAY] in b.calls("systemctl"), r)
    b.clear_log()
    r = bootstrap(b, env=b.env(FAKE_ACTIVE_gzcoord_relay="inactive"))
    check("an inactive unit and a free port: enable --now, no restart (unit unchanged)",
          [c for c in b.calls("systemctl") if c[-1] == RELAY] == [["systemctl", "--user", "is-active", RELAY],
                                                                  ["systemctl", "--user", "enable", "--now", RELAY],
                                                                  ["systemctl", "--user", "is-active", RELAY]], b.calls("systemctl"))

    c = Account("relay-away", ws="work", relay=True, wcs=False)
    r = bootstrap(c)
    check("a workspace not at $HOME/projects: the relay unit not installed, said",
          r.rc == 0 and not os.path.exists(f"{c.units}/{RELAY}.service")
          and f"  !  {RELAY}: not installed — the unit expects the workspace at $HOME/projects, this one is {c.ws}" in r.lines, r)
    d = Account("relay-noexec", relay=True, wcs=False)
    os.chmod(f"{d.ws}/.gzcoord/venv/bin/claude-bridge", 0o644)
    r = bootstrap(d)
    check("a relay venv whose claude-bridge is not executable: no relay unit",
          not os.path.exists(f"{d.units}/{RELAY}.service") and not any(RELAY in x for x in r.lines), r)


def failures() -> None:
    print("bootstrap: failures")
    a = Account("langid-fail", wcs=False)
    venv = f"{a.home}/.cache/agent-fabric/langid/venv"
    r = bootstrap(a, env=a.env(FAKE_VENV_FAIL="1"))
    check("step 7: no venv: said twice on stdout, exit 0, not counted as NOT written",
          r.rc == 0 and f"  !  {venv}: python3 -m venv failed; the language section stays unavailable" in r.lines
          and "  !  langid: not installed (above); fabric-ctl <login> script reports language unavailable until it is" in r.lines
          and "NOT written" not in r.out and r.err == "", r)
    r = bootstrap(a, env=a.env(FAKE_PIP_FAIL="1"))
    pkg = json.load(open(f"{a.fr}/runtime/langid/detector.json"))["package"]
    check("step 7: pip fails: said, exit 0",
          r.rc == 0 and f"  !  {venv}: could not install {pkg} (offline, or no C++ compiler on this host); the language section stays unavailable" in r.lines, r)
    r = bootstrap(a)
    check("step 7: the next run installs into the venv it left", r.rc == 0 and f"  +  {venv} ({pkg})" in r.lines, r.out)
    put(f"{a.home}/.cache/agent-fabric/langid/lid.176.ftz", "old model")
    r = bootstrap(a)
    check("step 7: the retired fastText model removed, said",
          not os.path.exists(f"{a.home}/.cache/agent-fabric/langid/lid.176.ftz")
          and f"  -  {a.home}/.cache/agent-fabric/langid/lid.176.ftz (removed: the detector is CLD2 now)" in r.lines, r.out)

    b = Account("trust-fail", wcs=False)
    put(f"{b.cfg}/.claude.json", "[1, 2]\n")
    r = bootstrap(b)
    check("step 5b: a .claude.json that is not an object: said on both streams, exit 0, file untouched",
          r.rc == 0 and "  !  workspace trust not recorded (above); a first session asks for it" in r.lines
          and f"workspace_trust: {b.cfg}/.claude.json is not a JSON object; nothing written" in r.err.splitlines()
          and read(f"{b.cfg}/.claude.json") == "[1, 2]\n", r)
    check("…not counted as NOT written", "NOT written" not in r.lines[-2], r.lines[-2])

    c = Account("settings-fail", wcs=False)
    put(f"{c.cfg}/settings.json", '{"hooks": {"PostToolUse": "x"}}\n')
    r = bootstrap(c)
    check("user settings the writer refuses: why on stderr, exit 0, counted NOT written, file untouched",
          r.rc == 0 and "fabric user settings NOT written" in r.err and r.lines[-2].endswith(", 1 NOT written (above).")
          and read(f"{c.cfg}/settings.json") == '{"hooks": {"PostToolUse": "x"}}\n', r)
    # A user settings file that is not JSON: the bash ended in the agent
    # files with a traceback from the WebSearch rule's install.py, exit 1,
    # no summary. Fixed: install.py says one line and leaves it alone, and
    # the run reaches the user settings writer's own refusal.
    c2 = Account("settings-garbage", wcs=False)
    put(f"{c2.cfg}/settings.json", "{not json\n")
    r = bootstrap(c2)
    check("user settings that are not JSON: one line from the WebSearch rule, no traceback, the run goes on, exit 0",
          r.rc == 0 and "Traceback" not in r.err
          and f"  !  {c2.cfg}/settings.json: not JSON (JSONDecodeError); left alone, nothing of the fabric's to remove"
          in r.err.splitlines()
          and "fabric user settings NOT written" in r.err and r.lines[-2].endswith(", 1 NOT written (above).")
          and os.path.isfile(f"{c2.cfg}/hooks/review-bash-guard.sh") and os.path.isfile(f"{c2.cfg}/agents/code-review.md")
          and read(f"{c2.cfg}/settings.json") == "{not json\n", r)

    d = Account("doppler-fail", wcs=False)
    put(f"{d.home}/.config/agent-fabric/secrets-source", "doppler\n")
    os.chmod(f"{d.home}/.config/agent-fabric", 0o555)
    r = bootstrap(d)
    os.chmod(f"{d.home}/.config/agent-fabric", 0o755)
    check("step 8: a leftover that cannot be removed: said on stdout, counted NOT written, exit 0",
          r.rc == 0 and "  !  Doppler retired: ~/.config/agent-fabric/secrets-source (Permission denied) could not be removed" in r.lines
          and r.lines[-2].endswith(", 1 NOT written (above)."), r)

    e = Account("commands-fail", wcs=False)
    put(f"{e.fr}/runtime/claude-code/commands.json", "{broken\n")
    r = bootstrap(e)
    check("commands.json unreadable: said on stderr, nothing linked, counted NOT written, exit 0",
          r.rc == 0 and "  !  runtime/claude-code/commands.json unreadable — no command linked" in r.err.splitlines()
          and not os.path.isdir(e.lb) and "NOT written (above)." in r.lines[-2], r)

    f = Account("readonly-bin", wcs=False)
    os.makedirs(f.lb)
    os.chmod(f.lb, 0o555)
    r = bootstrap(f)
    os.chmod(f.lb, 0o755)
    n = len(commands(f.fr))
    errs = [x for x in r.err.splitlines() if x.startswith("  !  ")]
    check("a read-only ~/.local/bin: each link said on stderr, exit 0, all counted NOT written",
          r.rc == 0 and errs == [f"  !  {f.lb}/{c}: could not link" for c, _ in commands(f.fr)]
          and r.lines[-2].endswith(f", {n} NOT written (above)."), r)

    g = Account("readonly-ws", wcs=False)
    os.makedirs(f"{g.ws}/.claude")
    os.chmod(f"{g.ws}/.claude", 0o555)
    r = bootstrap(g)
    os.chmod(f"{g.ws}/.claude", 0o755)
    check("a workspace .claude/ it cannot write: the run stops there, exit 1, install's word on stderr",
          r.rc == 1 and r.lines[-1] == f"  +  {g.ws}/CLAUDE.md" and "install:" in r.err
          and not os.path.exists(f"{g.cfg}/agents"), r)
    check("…its temporary directory still removed", os.listdir(g.tmp) == [], os.listdir(g.tmp))

    # A working copy whose marker names no registered project: the bash
    # ended the run there, silently, exit 1 (pipefail and set -e in the pid
    # pipeline). Fixed in the port: one line names it, the run goes on.
    m = Account("bad-marker", wcs=False)
    git("init", "-q", f"{m.ws}/badmark")
    put(f"{m.ws}/badmark/.agent-fabric-project", "nosuch\n")
    git("init", "-q", f"{m.ws}/zeta")
    git("-C", f"{m.ws}/zeta", "remote", "add", "origin", "git@github.com:example-org/alpha.git")
    r = bootstrap(m)
    errs = r.err.splitlines()
    check("a marker naming no project: one line on stderr naming that copy and the project, the run goes on, exit 0",
          r.rc == 0 and len(errs) == 1 and errs[0].startswith(f"  !  {m.ws}/badmark: ") and "'nosuch'" in errs[0]
          and git_config(f"{m.ws}/badmark", "core.hooksPath") is None
          and git_config(f"{m.ws}/zeta", "core.hooksPath") == f"{m.fr}/{HOOK_REL}"
          and f"  +  {m.ws}/zeta (alpha): core.hooksPath = {m.fr}/{HOOK_REL}" in r.lines
          and m.ws + "/zeta" in json.load(open(f"{m.cfg}/.claude.json"))["projects"]
          and m.ws + "/badmark" not in json.load(open(f"{m.cfg}/.claude.json"))["projects"]
          and r.lines[-2].endswith(", 1 NOT written (above)."), r)

    h = Account("no-git", wcs=False)
    r = bootstrap(h, env=h.env(PATH=path_without("git")))
    check("no git: step 4 stops the run, exit 127, said on stderr",
          r.rc == 127 and "git: command not found" in r.err and not r.lines[-1].startswith("bootstrap:")
          and not os.path.exists(h.units), r)

    k = Account("no-python", wcs=False)
    r = bootstrap(k, env=k.env(PATH=path_without("python3")))
    # The helpers run on bootstrap's own interpreter, the fleet's pin
    # (ADR-040 §5 rule 4); only step 7's venv needs the host's python3. The
    # bash stopped here with 127 before step 2.
    check("no host python3: the header names the agent, every step runs, step 7 says its venv failed, exit 0",
          r.rc == 0 and r.lines[0] == f"agent-fabric bootstrap for agent {LOGIN} — projects: {k.ws}"
          and os.path.exists(f"{k.ws}/.claude/settings.json") and os.path.exists(k.units)
          and any("python3 -m venv failed" in ln for ln in r.lines), r)


def main() -> int:
    global T
    T = os.path.realpath(tempfile.mkdtemp(prefix="test_bootstrap_cli."))
    try:
        if os.path.realpath(T).startswith(os.path.realpath(REAL_HOME) + "/projects/"):
            sys.exit(f"test: refusing to run: the scratch {T} is inside the real workspace")
        os.makedirs(f"{T}/git-home")
        make_bins()
        make_pristine(SCRIPT)
        for name in ("systemctl", "loginctl", "curl", "ss", "pgrep", "claude", "pip", "uv"):
            if shutil.which(name, path=f"{T}/fakebin:{T}/sysbin") != f"{T}/fakebin/{name}":
                sys.exit(f"test: refusing to run: {name} on the test PATH is not the fake")
        for case in (first_run, dry_run, arguments, existing_files, no_config_dir, local_bin_override,
                     user_manager, relay, failures):
            # A file the script did not write, or a line it did not print,
            # can raise in the case's own reading: that is a failure of the
            # script, counted, and the other cases still run.
            try:
                case()
            except Exception as exc:  # noqa: BLE001 — any raise is the script's failure here
                import traceback
                fail(f"{case.__name__}: stopped by {type(exc).__name__}", traceback.format_exc(limit=-2))
    finally:
        for dirpath, dirnames, _ in os.walk(T):
            for n in dirnames:
                try:
                    os.chmod(os.path.join(dirpath, n), 0o755)
                except OSError:
                    pass
        shutil.rmtree(T, ignore_errors=True)
    if fails:
        print(f"test_bootstrap_cli: {fails} FAILED")
        return 1
    print("test_bootstrap_cli: all passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
