#!/usr/bin/env python3
"""tools/fabric/new_agent.py — give a role its own account on a host:
everything the control plane can do without a person at a terminal, in
order, idempotently, then the short list of what only a person can do
(ADR-040 Wave 5; runtime/provisioning/new-agent.sh is its shim). Run by a
fabric-coordinator holder from its own login; the account steps go through
the host half, runtime/provisioning/new-agent-worker.sh, and the secrets
step is the coordinator's as the account's parent (ADR-038).

Standard library only, and nothing imported from the fabric:
test_new-agent.sh runs this in a fixture fabric that holds fakes of the
tools it calls (ADR-040 rule 5's fixture departure).

CONTRACT, frozen from the bash (ADR-040 §5 rule 3):
  argv      <login> <role> [--host <id>] [--project <id>]...
            [--claude VERSION|stable|latest] [--dry-run], each value
            spaced or with `=`, flags anywhere. -h/--help: HELP on stdout,
            exit 0 (the bash's header, lines 2-52, cut where it cut).
            An unknown flag, a third positional or a missing login/role:
            exit 2 (USAGE for the last). A flag without its value: exit 1,
            one line (bash: "unbound variable"). --claude must be stable,
            latest or a version with an optional [-.]suffix of [A-Za-z0-9.].
  stdin     never read; the worker phases inherit it.
  env       AGENT_FABRIC_HOSTS_REGISTRY (default runtime/hosts/registry.json);
            everything else reaches the host executor, the worker and the
            store tools as found.
  stdout    HELP; nothing else of its own.
  stderr    `new-agent: …` lines: the host, each step's result, a refusal;
            what store-enroll, the hand-over, the sync and the inbox
            catch-up print, each line indented three spaces.
  exit      0 when every step ran (or a dry run planned them); 1 for a
            refusal or a failed step (`step failed: …`, nothing after it
            ran); 2 for usage; hostexec's own refusal of the host is 1.

Deliberate differences from the bash: a flag without its value is one
line, not "unbound variable"; every step is bounded (STEP_TIMEOUT_S, the
worker's phases WORKER_TIMEOUT_S), and one that runs out is that step's
failure; the store tool runs on this interpreter (the fleet's pin), where
the bash ran PATH's python3.

TWO HALVES (review, 2026-09-16). This is the ORCHESTRATOR: it runs on the
coordinator's host and keeps what only the coordinator holds — the
registry, its own store, the API keys. The HOST half,
runtime/provisioning/new-agent-worker.sh, runs on the host the account is
placed on (runtime/hosts/registry.json; --host names a new placement)
through runtime/hostexec/hostexec — directly on this host, over ssh to any
other — in two phases around the secrets step: `prepare` (0-4) and
`finish` (6-10). The host names itself (`hostname -s`, checked against the
registry id) and the coordinator never stamps a host it is not on.

FAILURE SEMANTICS (review, 2026-09-16 — before this, `run x; say done`
announced success whatever x returned, and a failed useradd, clone,
bootstrap or bind left a half-made account while later steps went on).
Every step names one of three: must (a failure stops the run, naming the
step; nothing after it runs), probe (a question, never an error),
best_effort (a failure is one warning line). A pipeline that ends in a
filter is judged by its FIRST command's status, never by the filter's.
test_new-agent.sh runs the real sequence against fakes and injects a
failure at each must.

NEVER: a secret value on the terminal (provision keeps them inside its
process, and the parent cannot read what it put); a copy of the
coordinator's admin or provisioning keys (provision shares an allowlist of
names, and refuses those even when named); a guess at a port offset.
"""
from __future__ import annotations

import collections
import json
import os
import pwd
import re
import signal
import subprocess
import sys
import tempfile
import threading

HERE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
from new_agent_worker import run_bounded, stop_tree  # noqa: E402
REGISTRY = os.path.join(ROOT, "projects", "registry.json")
SECRETS = os.path.join(ROOT, "runtime", "provisioning", "secrets", "fabric-secrets")
STORE_ENROLL = os.path.join(ROOT, "runtime", "provisioning", "secrets", "store-enroll.sh")
STORE = os.path.join(ROOT, "tools", "fabric", "secret_store.py")
HX = os.path.join(ROOT, "runtime", "hostexec", "hostexec")
WORKER = "@fabric/runtime/provisioning/new-agent-worker.sh"
# A host phase installs claude, ori and a project's toolchain (pnpm
# install can take minutes); the coordinator's own steps cross a host and
# GitHub. Bounds a person would rather see fail than wait past.
WORKER_TIMEOUT_S = 3600
STEP_TIMEOUT_S = 900
# The value reaches the worker's as_login eval inside single quotes, so a
# suffix may carry no quote, semicolon or other shell character — only
# what a real pre-release or build tag holds (review of #34).
CLAUDE_TARGET = re.compile(r"stable|latest|[0-9]+\.[0-9]+\.[0-9]+([-.][A-Za-z0-9.]+)?")
USAGE = ("usage: new-agent.sh <login> <role> [--host <id>] [--project <id>]... [--claude VERSION|stable|latest] "
         "[--dry-run]\n")
HELP = """\
runtime/provisioning/new-agent.sh — give a role its own account on this
host: everything the control plane can do without a person at a
terminal, in order, idempotently, then the short list of what only a
person can do. Run by a fabric-coordinator holder from its own login
(the account steps go through sudo; the secrets step is the
coordinator's as the account's parent, ADR-038).

  runtime/provisioning/new-agent.sh <login> <role> [--host <id>] [--project <id>]... [--claude VERSION|stable|latest] [--dry-run]

  new-agent.sh <login> <role> --project <id> --project <id>
  new-agent.sh <login> <role> --host <host-id> --project <id>      # on another host

TWO HALVES (review, 2026-09-16). This script is the ORCHESTRATOR: it
runs on the coordinator's host and keeps what only the coordinator
holds — the registry, its own store, the API keys. The
HOST half, runtime/provisioning/new-agent-worker.sh, runs on the host
the account is placed on (runtime/hosts/registry.json; --host names a
new placement) through runtime/hostexec/hostexec — directly on this
host, over ssh to any other — in two phases around the secrets step:
`prepare` (0-4) and `finish` (6-10). The host names itself (`hostname
-s`, checked against the registry id) and the coordinator never stamps
a host it is not on.

WHY THIS EXISTS. The host runbook (the managed project's docs/host/
PROVISIONING.md) is twelve sections a person walks by hand, and twice
on 2026-09-15 an account was walked through it in a session and came
out short: a claude binary never installed, a root-owned ~/.local/bin,
the GitHub host key never trusted so every SSH step failed as a
password prompt, pnpm and node_modules absent, and — the one that
mattered — a fill-from that copied the coordinator's admin keys into
the new account's config. Each of those is one line here, checked
before it is done, so the second account costs what the first did.

WHAT IT DOES, in order (each step is skipped when already true):
  0. the host: what this AppVM must already have and what it can hold.
     A Qubes AppVM keeps only /home and /usr/local across a reboot; a
     package is the TemplateVM's (dnf there, not here). So: the rpm
     tools the fabric and the projects use (git, gh, node, npm,
     python3, jq, gpg) are audited and a missing one is named with its
     package for the template; the account's own tools go under its
     ~/.local. What
     a PROJECT needs of the host beyond that is the project's own
     integration/provisioning/host-check.sh, run in finish. [worker: prepare]
  1. the Linux account (useradd), home 700, the shared-cache group, and the
     account persisted across the host's reboot (linger; on Qubes the record
     snapshot under /rw — persist-accounts.sh)
  2. ~/.ssh ~/.claude ~/.config/gh ~/.local/{bin,share}, owned by the
     account; claude and ori installed AS THE ACCOUNT the way their
     vendors say — `curl -fsSL https://claude.ai/install.sh | bash -s --
     <version>` — at the version the fleet pins in
     runtime/claude-code/harness.json (what `fabric-ctl … upgrade
"""


class Exit(Exception):
    def __init__(self, code: int, msg: str | None = None):
        super().__init__(msg)
        self.code, self.msg = code, msg


def say(msg: str) -> None:
    print(f"new-agent: {msg}", file=sys.stderr, flush=True)


def die(msg: str) -> "NoReturn":  # noqa: F821
    raise Exit(1, f"new-agent: {msg}")


def parse(argv: list[str]) -> dict:
    o = {"dry": False, "login": "", "role": "", "projects": [], "claude": "", "host": ""}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("--host", "--claude", "--project"):
            if i + 1 >= len(argv):
                raise Exit(1, f"new-agent: {a} needs a value")
            v = argv[i + 1]
            i += 1
            if a == "--project":
                o["projects"].append(v)
            else:
                o[a[2:]] = v
        elif a.startswith(("--host=", "--claude=", "--project=")):
            name, v = a[2:].split("=", 1)
            if name == "project":
                o["projects"].append(v)
            else:
                o[name] = v
        elif a == "--dry-run":
            o["dry"] = True
        elif a in ("-h", "--help"):
            raise Exit(0, None)
        elif a.startswith("-"):
            raise Exit(2, f"new-agent: unknown flag {a}")
        elif not o["login"]:
            o["login"] = a
        elif not o["role"]:
            o["role"] = a
        else:
            raise Exit(2, f"new-agent: unexpected argument {a}")
        i += 1
    if not (o["login"] and o["role"]):
        raise Exit(2, USAGE.rstrip("\n"))
    if o["claude"] and not CLAUDE_TARGET.fullmatch(o["claude"]):
        raise Exit(2, "new-agent: --claude takes stable, latest or a version")
    return o


def project_remote(pid: str) -> str | None:
    """The registry's SSH remote for a project (its first remote when it
    names none), or None when the registry does not hold it."""
    try:
        with open(REGISTRY, encoding="utf-8") as fh:
            p = (json.load(fh).get("projects") or {}).get(pid)
        if not p:
            return None
        return next((x for x in p["remotes"] if x.startswith("git@")), p["remotes"][0])
    except (OSError, ValueError, KeyError, IndexError, TypeError, AttributeError):
        return None


def hosts_registry(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as fh:
            d = json.load(fh)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError) as exc:
        say(f"{path}: {exc}")
        return {}


class Steps:
    """Each command of the run, bounded, its failures kept out of the way
    in LOG and shown (its last lines) only when a step fails."""

    def __init__(self, log: str):
        self.log = log

    def tail(self, n: int) -> None:
        try:
            with open(self.log, encoding="utf-8", errors="surrogateescape") as fh:
                lines = fh.read().splitlines()
        except OSError:
            return
        for line in lines[-n:]:
            print(line, file=sys.stderr)
        sys.stderr.flush()

    def capture(self, cmd: list[str], *, timeout: float = STEP_TIMEOUT_S, stdin=subprocess.DEVNULL) -> tuple[int, str]:
        """stdout captured; stderr appended to LOG, as `2>>"$LOG"` did."""
        with open(self.log, "a", encoding="utf-8") as err:
            try:
                r = run_bounded(cmd, stdin=stdin, stdout=subprocess.PIPE, stderr=err, text=True,
                                errors="surrogateescape", timeout=timeout)
            except subprocess.TimeoutExpired:
                err.write(f"{cmd[0]}: no answer within {timeout} s\n")
                return 124, ""
            except OSError as exc:
                err.write(f"{cmd[0]}: {exc.strerror or exc}\n")
                return 127, ""
        return r.returncode, r.stdout.rstrip("\n")

    def through(self, cmd: list[str], *, timeout: float = WORKER_TIMEOUT_S, quiet_stdout: bool = False) -> int:
        """A command whose output is the person's to read, as it comes."""
        sys.stderr.flush()
        try:
            return run_bounded(cmd, stdin=None, stdout=subprocess.DEVNULL if quiet_stdout else None,
                               timeout=timeout).returncode
        except subprocess.TimeoutExpired:
            say(f"{os.path.basename(cmd[0])} {' '.join(cmd[1:4])}: no answer within {timeout} s")
            return 124
        except OSError as exc:
            say(f"{cmd[0]}: {exc.strerror or exc}")
            return 127

    @staticmethod
    def indented(*cmds: list[str], timeout: float = STEP_TIMEOUT_S) -> list[int]:
        """`a | b … 2>&1 | sed 's/^/   /' >&2`: a pipeline, the LAST
        command's stderr merged into its stdout, every line indented three
        spaces on our stderr as it comes; each command's status, in order
        (bash's PIPESTATUS, without sed's)."""
        sys.stderr.flush()
        procs, prev = [], subprocess.DEVNULL
        try:
            for n, cmd in enumerate(cmds):
                last = n == len(cmds) - 1
                p = subprocess.Popen(cmd, stdin=prev, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT if last else None)
                if prev is not subprocess.DEVNULL:
                    prev.close()
                procs.append(p)
                prev = p.stdout
        except OSError as exc:
            say(f"{cmds[len(procs)][0]}: {exc.strerror or exc}")
            for p in procs:
                p.kill()
                p.wait()
            return [127] * len(cmds)
        out = procs[-1].stdout
        killed = []

        def overdue() -> None:
            for p in procs:
                if p.poll() is None:
                    killed.append(p)
                    stop_tree(p)
        timer = threading.Timer(timeout, overdue)
        timer.start()
        try:
            for raw in out:
                sys.stderr.buffer.write(b"   " + raw)
                sys.stderr.buffer.flush()
        finally:
            timer.cancel()
            out.close()
        statuses = []
        for p in procs:
            rc = p.wait()
            statuses.append(124 if p in killed else rc)
        if killed:
            say(f"{os.path.basename(cmds[0][0])}: no answer within {timeout} s")
        return statuses


def new_agent(argv: list[str]) -> int:
    o = parse(argv)
    login, role, host, dry = o["login"], o["role"], o["host"], o["dry"]
    coord = pwd.getpwuid(os.getuid()).pw_name
    if coord == "root":
        die("run this as the fabric-coordinator login, not root: the account's store is filled from yours.")

    # ---- what is asked for must exist in the fabric ---------------------
    if not os.path.isfile(os.path.join(ROOT, "identities", "roles", role, "charter.md")):
        die(f"no role '{role}' under identities/roles/ (bin/fabric-role list).")
    remote = {}
    for pid in o["projects"]:
        r = project_remote(pid)
        if r is None:
            die(f"project '{pid}' is not in projects/registry.json — register it first.")
        remote[pid] = r

    hosts_path = os.environ.get("AGENT_FABRIC_HOSTS_REGISTRY") or os.path.join(ROOT, "runtime", "hosts", "registry.json")
    with tempfile.NamedTemporaryFile(prefix="new-agent-", suffix=".log", delete=False) as fh:
        log = fh.name
    LOGS.append(log)
    try:
        return run_steps(o, login, role, host, dry, remote, hosts_path, Steps(log))
    finally:
        remove_logs()


# The bash's EXIT trap removed its log when a signal ended it too; a
# signal's default action ends this process with no finally run. So each
# of these, unless it was ignored on entry, removes the log first and then
# ends the process by the same signal, as the bash's death reported it.
LOGS: list[str] = []
FATAL_SIGNALS = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)


def remove_logs() -> None:
    while LOGS:
        try:
            os.remove(LOGS.pop())
        except OSError:
            pass


def die_of(signum: int, _frame) -> None:
    remove_logs()
    signal.signal(signum, signal.SIG_DFL)
    os.kill(os.getpid(), signum)


def run_steps(o: dict, login: str, role: str, host: str, dry: bool, remote: dict, hosts_path: str, s: Steps) -> int:
    # ---- the host the account lives on ----------------------------------
    # Placement is the registry's: an account already placed is provisioned
    # there and nowhere else; a new account goes to --host, or to this host.
    reg = hosts_registry(hosts_path)
    placed = str((reg.get("placement") or {}).get(login, ""))
    local_host = next((h for h, e in (reg.get("hosts") or {}).items() if isinstance(e, dict) and e.get("ssh") is None), "")
    if placed and host and placed != host:
        die(f"{login} is placed on {placed} (runtime/hosts/registry.json); --host {host} would make a second account of "
            "that name. Move the placement first, or drop --host.")
    host = host or placed or local_host
    if not host:
        die("no host: name one with --host, or register this host (ssh null) in runtime/hosts/registry.json")
    if s.through([HX, "--resolve", host], timeout=60, quiet_stdout=True) != 0:
        raise Exit(1, None)
    # The host names itself; a name other than the id it was reached as is refused.
    rc, check = s.capture([HX, host, "--", WORKER, "host-check", login], timeout=120)
    if rc != 0:
        s.tail(5)
        die(f"host {host}: unreachable, or its worker did not run")
    reported = check.split("\n", 1)[0]
    if reported != host:
        die(f"host {host} answers as '{reported}'; the registry id is the host's short hostname (bin/fabric-host {host} check)")
    say(f"host {host}{' (this host)' if host == local_host else ' (over ssh)'}; account {login}, role {role}")
    if not placed:
        say(f"placement: add \"{login}\": \"{host}\" to runtime/hosts/registry.json placement (bin/fabric-status on the "
            "account reports drift until it is there)")
    dry_arg = ["--dry-run"] if dry else []

    # ---- 0-4 on the host ---------------------------------------------------
    claude = ["--claude", o["claude"]] if o["claude"] else []
    if s.through([HX, host, "--", WORKER, "prepare", login, role, *claude, *dry_arg]) != 0:
        die("the host half stopped (above); nothing after it ran")

    # ---- 5. the account's key, store and secrets (ADR-038) ------------------
    # Its parent is this login: the key is made in the account on its host,
    # certified here, its store mirrored here and filled with put — which this
    # login cannot read back. Every piece is idempotent: store-enroll keeps a
    # key and id already made, and provision leaves a name the store holds
    # alone (a key is minted once; a second run must not mint again).
    if dry:
        say(f"would: store-enroll.sh {login} --host {host} --born-now; provision identity, share, issue-key openrouter "
            f"and openai (each once); its store to {login} as a bundle; fabric-secrets sync --no-pull as {login}; its "
            "inbox cursor to the newest message")
    else:
        secrets_step(s, login, host, o["projects"])

    # ---- 6-10 on the host ---------------------------------------------------
    clones = [a for pid in o["projects"] for a in ("--clone", f"{pid}={remote[pid]}")]
    if s.through([HX, host, "--", WORKER, "finish", login, role, *clones, *dry_arg]) != 0:
        die("the host half stopped (above); nothing after it ran")
    return 0


def secrets_step(s: Steps, login: str, host: str, projects: list[str]) -> None:
    if s.capture([sys.executable, STORE, "export-key"])[0] != 0:
        die("this login has no store of its own, so it cannot be a parent: store-enroll.sh --self first; nothing after "
            "it ran")
    if s.indented([STORE_ENROLL, login, "--host", host, "--born-now"])[0] != 0:
        die(f"step failed: store-enroll.sh {login}; nothing after it ran")

    def provision(label: str, *args: str) -> None:
        """One line per run, statuses only."""
        rc, rows = s.capture([SECRETS, "provision", *args])
        if rc != 0:
            s.tail(3)
            die(f"step failed: fabric-secrets provision {' '.join(args)}; nothing after it ran")
        try:
            counts = collections.Counter(r["status"] for r in json.loads(rows))
            summary = ", ".join(f"{v} {k}" for k, v in sorted(counts.items())) or "nothing to do"
        except (ValueError, TypeError, KeyError):
            summary = ""
        say(f"   {label}: {summary}")
    provision("identity", "identity", login, "--host", host)
    provision("shared names", "share", login)
    provision("OpenRouter key", "issue-key", "openrouter", login)
    provision("OpenAI key", "issue-key", "openai", login)
    as_account = [HX, host, "--as", login, "--"]
    # The filled store reaches the account as a bundle: its SSH key is in
    # it, so it could not pull it (store-enroll's first contact). Then
    # synced as the account, from its own checkout, without a pull: 2 is
    # "applied, names missing", said by the verification in finish; 1 and
    # 3 are a store the account cannot read or one naming someone else.
    bundled, taken = s.indented([sys.executable, STORE, "child-bundle", login],
                                [*as_account, "projects/agent-fabric/bin/fabric-secrets", "store", "take-bundle"])
    if bundled != 0 or taken != 0:
        die(f"step failed: its store did not reach {login} as a bundle; nothing after it ran")
    rc = s.indented([*as_account, "projects/agent-fabric/bin/fabric-secrets", "sync", "--quiet", "--no-pull"])[0]
    if rc not in (0, 2):
        die(f"step failed: fabric-secrets sync as {login} (exit {rc}); nothing after it ran")
    # Its GZCoord cursor at the channel's newest message: a consumer the
    # relay has never seen reads from the first message it holds, and
    # everything before the account existed is someone else's history.
    # Not fatal: an account whose cursor stayed behind still works, it only
    # reads old traffic once.
    if s.indented([*as_account, "python3", "projects/agent-fabric/tools/fabric/relay_catchup.py", *projects])[0] != 0:
        say("   its inbox cursor was not moved (above); its first session reads the channel's backlog")
    say("5. its key made and certified, its store filled and synced; commit identities/keys/, then write its recovery "
        "copy and back up:")
    say(f"     bin/fabric-host {host} run --as {login} -- projects/agent-fabric/bin/fabric-secrets store recovery-copy")
    say("     bin/fabric-secrets store backup")


def main(argv: list[str]) -> int:
    for sig in FATAL_SIGNALS:
        if signal.getsignal(sig) != signal.SIG_IGN:
            signal.signal(sig, die_of)
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="surrogateescape")
    try:
        return new_agent(argv)
    except Exit as exc:
        if exc.code == 0 and exc.msg is None:
            sys.stdout.write(HELP)
        elif exc.msg:
            print(exc.msg, file=sys.stderr)
        return exc.code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
