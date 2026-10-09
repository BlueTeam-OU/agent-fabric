#!/usr/bin/env python3
"""tools/fabric/new_agent.py — give a role its own account on a host:
everything the control plane can do without a person at a terminal, in
order, idempotently, then the short list of what only a person can do
(ADR-040 Wave 5; runtime/provisioning/new-agent.sh is its shim). Run by a
fabric-coordinator holder from its own login; the account steps go through
the host half, runtime/provisioning/new-agent-worker.sh, and the secrets
step is the coordinator's as the account's parent (ADR-038).

Standard library only, and nothing imported from the fabric:
tests/test_new_agent_cli.py runs this in a fixture fabric that holds fakes of the
tools it calls (ADR-040 rule 5's fixture departure).

CONTRACT, frozen from the bash (ADR-040 §5 rule 3):
  argv      <login> <role> (--claude-account <slug> | --no-claude-account)
            [--host <id>] [--project <id>]...
            [--claude VERSION|stable|latest] [--no-signing-key] [--dry-run],
            or <login> --human [--host <id>] [--dry-run]; each value
            spaced or with `=`, flags anywhere. -h/--help: HELP on stdout,
            exit 0 (the bash's header, lines 2-52, cut where it cut).
            An unknown flag, a third positional or a missing login/role:
            exit 2 (USAGE for the last). A flag without its value: exit 1,
            one line (bash: "unbound variable"). --claude must be stable,
            latest or a version with an optional [-.]suffix of [A-Za-z0-9.].
            Exactly one of --claude-account and --no-claude-account
            (2026-10-07, the owner: the starting Claude account is part of
            onboarding, so a re-run names it too): neither or both, exit 2.
            --human (ADR-044): no role, and none of --claude-account,
            --no-claude-account, --claude, --project: exit 2.
  stdin     never read by this process; the worker phases and step 11's
            gpg inherit it (pinentry asks there). Step 11 runs only when
            stdin and stdout are both terminals.
  env       AGENT_FABRIC_HOSTS_REGISTRY (default runtime/hosts/registry.json);
            everything else reaches the host executor, the worker and the
            store tools as found.
  stdout    HELP; nothing else of its own.
  stderr    `new-agent: …` lines: the host, each step's result, a refusal;
            what store-enroll, the hand-over, the sync and the inbox
            catch-up print, each line indented three spaces.
  exit      0 when every step ran (or a dry run planned them); 1 for a
            refusal or a failed step (`step failed: …`, nothing after it
            ran; step 11, the last, fails alone: 0-10 stay done); 2 for
            usage; hostexec's own refusal of the host is 1.

A HUMAN LOGIN (ADR-044; the coordinator's request of 2026-10-08). A
person's login is an identity of the fleet with a kind, `human`, in
runtime/hosts/registry.json: it has an account, a key its parent
certifies, a store and the relay credential, and nothing of a session —
no claude or ori, no SSH host keys, no bootstrap (agent files, hooks,
agentd), no role, no Claude account, no issued key. It is placed and its
kind recorded BEFORE the run, never by it: the kind decides what
fabric-secrets status requires of the login, and the login's own clone is
what status reads, so a run that came first would end NOT OK. A --human
run on a login the registry does not hold as a human is refused, and so
is an agent run on one it does (ADR-044 rule 5: neither becomes the
other). moveto's sudo grant is the host operator's to give.

THE SIGNING KEY, step 11 (the coordinator's request of 2026-10-08: two
agents in two days started unable to sign). The fleet's commit-signing
key is shared (the owner's choice). On a terminal, an agent's last step
imports it: this login's gpg exports the key its git config signs with
and the account's gpg imports it on a pipe — the passphrase is asked by
gpg's own pinentry, never read, echoed or passed here — its ownertrust is
set, and a test signature as the account proves it. Without a terminal,
or with --no-signing-key, the closing prints the two lines a person runs.
A human never gets it (ADR-044 rule 3).

THE CLAUDE ACCOUNT (ADR-031; the owner, 2026-10-07). Assigned after new-agent
by fabric-accounts, the token was written but the account's own sync
refused it until identities/keys/ merged; new-agent's first sync (bundle,
take-bundle, sync --no-pull) applies what the store holds before that. So
the slug is checked against this login's templates before any account is
made — unknown, tokenless or unreadable all refuse, never skip — the token
is written by the same writer fabric-accounts uses (fabric-secrets store
assign) before the bundle, and finish compares the applied token's
fingerprint with the template's and fails on any other answer.

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
tests/test_new_agent_cli.py runs the real sequence against fakes and injects a
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
import roots  # noqa: E402
from provisioning.bounded import run_bounded, stop_tree  # noqa: E402
from provisioning.verify import signing_key_lines, signs_with_secret  # noqa: E402
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
# A template's slug as fabric-secrets store templates names it (its SLUG_RE);
# the fingerprint, sha256[:12] of the token, as it answers it.
SLUG = re.compile(r"[a-z0-9][a-z0-9-]{0,62}")
FINGERPRINT = re.compile(r"[0-9a-f]{12}")
USAGE = ("usage: new-agent.sh <login> <role> (--claude-account <slug> | --no-claude-account) [--host <id>] "
         "[--project <id>]... [--claude VERSION|stable|latest] [--no-signing-key] [--dry-run]\n"
         "       new-agent.sh <login> --human [--host <id>] [--dry-run]\n")
NO_ACCOUNT_CHOICE = ("new-agent: name the Claude account it starts on: --claude-account <slug> (fabric-accounts "
                     "templates), or --no-claude-account for the broker path only")
HELP = """\
runtime/provisioning/new-agent.sh — give a role its own account on this
host: everything the control plane can do without a person at a
terminal, in order, idempotently, then the short list of what only a
person can do. Run by a fabric-coordinator holder from its own login
(the account steps go through sudo; the secrets step is the
coordinator's as the account's parent, ADR-038).

  runtime/provisioning/new-agent.sh <login> <role> (--claude-account <slug> | --no-claude-account) [--host <id>] [--project <id>]... [--claude VERSION|stable|latest] [--no-signing-key] [--dry-run]
  runtime/provisioning/new-agent.sh <login> --human [--host <id>] [--dry-run]

  new-agent.sh <login> <role> --claude-account <slug> --project <id> --project <id>
  new-agent.sh <login> <role> --claude-account <slug> --host <host-id> --project <id>      # on another host
  new-agent.sh <login> <role> --no-claude-account --project <id>   # the broker path only
  new-agent.sh <login> --human     # a person's login (ADR-044): placed with kinds "human" first

On a terminal, an agent's last step imports the fleet's signing key
(gpg's pinentry asks its passphrase); without one, or with
--no-signing-key, the closing prints the two lines a person runs.

The Claude account it starts on is a template in this login's store
(fabric-accounts templates): checked before any account is made,
its token written into the new store before the first sync, and its
fingerprint compared in finish (ADR-031).

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
    o = {"dry": False, "login": "", "role": "", "projects": [], "claude": "", "host": "", "claude-account": None,
         "no-claude-account": False, "human": False, "no-signing-key": False}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("--host", "--claude", "--project", "--claude-account"):
            if i + 1 >= len(argv):
                raise Exit(1, f"new-agent: {a} needs a value")
            v = argv[i + 1]
            i += 1
            if a == "--project":
                o["projects"].append(v)
            else:
                o[a[2:]] = v
        elif a.startswith(("--host=", "--claude=", "--project=", "--claude-account=")):
            name, v = a[2:].split("=", 1)
            if name == "project":
                o["projects"].append(v)
            else:
                o[name] = v
        elif a == "--dry-run":
            o["dry"] = True
        elif a in ("--no-claude-account", "--human", "--no-signing-key"):
            o[a[2:]] = True
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
    if o["human"]:
        if o["role"]:
            raise Exit(2, f"new-agent: a human login has no role (ADR-044): new-agent.sh {o['login']} --human")
        if o["claude-account"] is not None or o["no-claude-account"] or o["claude"] or o["projects"]:
            raise Exit(2, "new-agent: --human takes --host and --dry-run only: a human has no Claude account, no claude "
                          "and no project clones (ADR-044)")
        if not o["login"]:
            raise Exit(2, USAGE.rstrip("\n"))
        return o
    if not (o["login"] and o["role"]):
        raise Exit(2, USAGE.rstrip("\n"))
    if o["claude"] and not CLAUDE_TARGET.fullmatch(o["claude"]):
        raise Exit(2, "new-agent: --claude takes stable, latest or a version")
    given = o["claude-account"] is not None
    if given == o["no-claude-account"]:
        raise Exit(2, NO_ACCOUNT_CHOICE)
    if given and not SLUG.fullmatch(o["claude-account"]):
        raise Exit(2, f"new-agent: --claude-account {o['claude-account']!r} is not an account slug (lowercase, digits, "
                      "dashes; fabric-accounts templates)")
    return o


def project_remote(pid: str) -> str | None:
    """The registry's SSH remote for a project (its first remote when it
    names none), or None when the registry does not hold it."""
    try:
        with open(roots.projects_registry(engine=ROOT), encoding="utf-8") as fh:
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
    if not o["human"] and not os.path.isfile(os.path.join(roots.role_dir(role, engine=ROOT), "charter.md")):
        die(f"no role '{role}' under identities/roles/ (fabric-role list).")
    remote = {}
    for pid in o["projects"]:
        r = project_remote(pid)
        if r is None:
            die(f"project '{pid}' is not in projects/registry.json — register it first.")
        remote[pid] = r

    hosts_path = roots.hosts_registry(engine=ROOT)
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


def claude_template(s: Steps, slug: str) -> str:
    """The fingerprint of the template's token in this login's store, or a
    refusal: an unknown slug, a template with no token, and a store that
    did not answer are all refused here, before any account is made — the
    same refusals as fabric-accounts assign (runtime/control/accounts.mjs)."""
    rc, out = s.capture([SECRETS, "store", "templates", "--json"])
    try:
        rows = json.loads(out) if rc == 0 else None
    except ValueError:
        rows = None
    if not isinstance(rows, list):
        s.tail(3)
        die(f"this login's Claude account templates could not be read (fabric-secrets store templates, exit {rc}); "
            "nothing made")
    t = next((r for r in rows if isinstance(r, dict) and r.get("account") == slug), None)
    if t is None:
        die(f"'{slug}' is not a template in this store (fabric-accounts templates); nothing made")
    fp = t.get("token_sha256_12")
    if fp is None:
        die(f"template {slug} holds no CLAUDE_CODE_OAUTH_TOKEN yet; nothing made")
    if not isinstance(fp, str) or not FINGERPRINT.fullmatch(fp):
        die(f"template {slug}: the store answered a fingerprint that is not one ({fp!r}); nothing made")
    return fp


def run_steps(o: dict, login: str, role: str, host: str, dry: bool, remote: dict, hosts_path: str, s: Steps) -> int:
    human = o["human"]
    slug = o["claude-account"]
    fp = claude_template(s, slug) if slug else ""
    # ---- the host the account lives on ----------------------------------
    # Placement is the registry's: an account already placed is provisioned
    # there and nowhere else; a new account goes to --host, or to this host.
    reg = hosts_registry(hosts_path)
    placed = str((reg.get("placement") or {}).get(login, ""))
    kind = login_kind(reg, login, hosts_path)
    if human and not (placed and kind == "human"):
        die(f"{login} is not placed as a human: add \"{login}\": \"<host>\" to placement and \"{login}\": \"human\" to "
            "kinds in runtime/hosts/registry.json, merged, first — its clone reads its kind there (ADR-044); nothing made")
    if not human and kind == "human":
        die(f"{login} is a human login (runtime/hosts/registry.json kinds): new-agent.sh {login} --human; an agent's "
            "pieces are never made for it (ADR-044 rule 5)")
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
        die(f"host {host} answers as '{reported}'; the registry id is the host's short hostname (fabric-host {host} check)")
    say(f"host {host}{' (this host)' if host == local_host else ' (over ssh)'}; account {login}, "
        + ("a human (ADR-044)" if human else f"role {role}"))
    if human:
        say("a human: steps 0, 1 and 4 on the host, 5, then 10; no claude, ori, SSH host keys, bootstrap, role, "
            "toolchain or signing key (ADR-044)")
    if not placed:
        say(f"placement: add \"{login}\": \"{host}\" to runtime/hosts/registry.json placement (fabric-status on the "
            "account reports drift until it is there)")
    dry_arg = ["--dry-run"] if dry else []
    who = ["--human"] if human else [role]
    # Step 11 needs a person at a terminal: pinentry asks there.
    signing_next = not human and not o["no-signing-key"] and on_terminal()

    # ---- 0-4 on the host ---------------------------------------------------
    claude = ["--claude", o["claude"]] if o["claude"] else []
    if s.through([HX, host, "--", WORKER, "prepare", login, *who, *claude, *dry_arg]) != 0:
        die("the host half stopped (above); nothing after it ran")

    # ---- 5. the account's key, store and secrets (ADR-038) ------------------
    # Its parent is this login: the key is made in the account on its host,
    # certified here, its store mirrored here and filled with put — which this
    # login cannot read back. Every piece is idempotent: store-enroll keeps a
    # key and id already made, and provision leaves a name the store holds
    # alone (a key is minted once; a second run must not mint again).
    if dry and human:
        say(f"would: store-enroll.sh {login} --host {host} --born-now; provision identity, and share "
            f"{HUMAN_SHARED} only (a human: no other name, no issued key); its store to {login} as a bundle; "
            f"fabric-secrets sync --no-pull as {login}; its inbox cursor to the newest message")
    elif dry:
        say(f"would: store-enroll.sh {login} --host {host} --born-now; provision identity, share, issue-key openrouter "
            f"and openai (each once); its store to {login} as a bundle; fabric-secrets sync --no-pull as {login}; its "
            "inbox cursor to the newest message")
        say(f"would: fabric-secrets store assign {slug} {login} (token {fp}), before the bundle" if slug else
            "would: assign no Claude account (--no-claude-account: the broker path only)")
    else:
        secrets_step(s, login, host, o["projects"], slug, fp, human=human)

    # ---- 6-10 on the host ---------------------------------------------------
    clones = [a for pid in o["projects"] for a in ("--clone", f"{pid}={remote[pid]}")]
    account = [] if human else ["--claude-account", f"{slug}={fp}"] if slug else ["--no-claude-account"]
    nxt = ["--signing-key-next"] if signing_next and not dry else []
    # The closing's hand-import lines run here, on the coordinator's host: an
    # account on another reaches its gpg through fabric-host (#118, Codex).
    via = ["--via-host", host] if host != local_host and not human else []
    if s.through([HX, host, "--", WORKER, "finish", login, *who, *clones, *account, *nxt, *via, *dry_arg]) != 0:
        die("the host half stopped (above); nothing after it ran")

    # ---- 11. the signing key, with a person at the terminal -----------------
    if dry and signing_next:
        say(f"would: 11. export this login's signing key and import it as {login} (gpg's pinentry asks its "
            "passphrase), set its ownertrust, sign once as it")
    elif signing_next:
        return signing_key(login, host, via=host if host != local_host else "")
    return 0


def on_terminal() -> bool:
    """A person at this terminal: stdin and stdout both one."""
    return os.isatty(0) and os.isatty(1)


def login_kind(reg: dict, login: str, path: str) -> str:
    """The login's kind (ADR-044 rule 1): `kinds` names a human; a login it
    does not name is an agent. A kinds that is not a table, or a kind that
    is neither, is refused: the run would make the wrong pieces."""
    kinds = reg.get("kinds") or {}
    kind = kinds.get(login, "agent") if isinstance(kinds, dict) else None
    if kind not in ("agent", "human"):
        die(f"{path}: the kind of {login} cannot be read (kinds is a table of agent or human); nothing made")
    return kind


# The one shared name a human's work needs: its reads of the state stream
# and its messages (ADR-044 rule 3). provision share's allowlist holds it.
HUMAN_SHARED = "CLAUDE_BRIDGE_AUTH_TOKEN"
# A human has no projects to name its channel; the fleet's channel is the
# control plane's (projects/agent-fabric/integration/gzcoord).
HUMAN_CHANNEL_PROJECT = "agent-fabric"


def secrets_step(s: Steps, login: str, host: str, projects: list[str], slug: str, fp: str, *,
                 human: bool = False) -> None:
    if s.capture([sys.executable, STORE, "export-key"])[0] != 0:
        die("this login has no store of its own, so it cannot be a parent: store-enroll.sh --self first; nothing after "
            "it ran")
    if s.indented([STORE_ENROLL, login, "--host", host, "--born-now"])[0] != 0:
        die(f"step failed: store-enroll.sh {login}; nothing after it ran")

    def provision(label: str, *args: str) -> list:
        """One line per run, statuses only; the rows, [] when unreadable."""
        rc, rows = s.capture([SECRETS, "provision", *args])
        if rc != 0:
            s.tail(3)
            die(f"step failed: fabric-secrets provision {' '.join(args)}; nothing after it ran")
        try:
            parsed = json.loads(rows)
            counts = collections.Counter(r["status"] for r in parsed)
            summary = ", ".join(f"{v} {k}" for k, v in sorted(counts.items())) or "nothing to do"
        except (ValueError, TypeError, KeyError):
            parsed, summary = [], ""
        say(f"   {label}: {summary}")
        return parsed if isinstance(parsed, list) else []
    provision("identity", "identity", login, "--host", host)
    if human:
        # The one name is the human's whole use of its store: a row that is
        # not written or present (the parent lacks it, or no row) stops here.
        rows = provision("relay credential", "share", login, "--name", HUMAN_SHARED)
        if not any(isinstance(r, dict) and r.get("name") == HUMAN_SHARED and r.get("status") in ("written", "present")
                   for r in rows):
            die(f"step failed: {HUMAN_SHARED} did not reach {login}'s store (above); nothing after it ran")
        projects = [HUMAN_CHANNEL_PROJECT]
    else:
        provision("shared names", "share", login)
        provision("OpenRouter key", "issue-key", "openrouter", login)
        provision("OpenAI key", "issue-key", "openai", login)
    if slug:
        assign(s, login, slug, fp)
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
    say(f"     fabric-host {host} run --as {login} -- projects/agent-fabric/bin/fabric-secrets store recovery-copy")
    say("     fabric-secrets store backup")


def assign(s: Steps, login: str, slug: str, fp: str) -> None:
    """The template's token into the child's store, by fabric-accounts'
    own writer, before the bundle carries the store to the account: its
    first sync applies it. assign prints every row and exits 1 when one
    failed; a row other than this login's, or none, is no answer."""
    rc, out = s.capture([SECRETS, "store", "assign", slug, login, "--json"])
    try:
        rows = json.loads(out)
    except ValueError:
        rows = None
    row = rows[0] if isinstance(rows, list) and len(rows) == 1 and isinstance(rows[0], dict) else {}
    if rc != 0 or row.get("status") not in ("written", "unchanged") or row.get("login") != login:
        s.tail(3)
        why = f": {row['reason']}" if isinstance(row.get("reason"), str) else f" (exit {rc})"
        die(f"step failed: fabric-secrets store assign {slug} {login}{why}; nothing after it ran")
    # The template is read twice, here and before the account was made; one
    # replaced in between is not the account the run checked.
    if row.get("token_sha256_12") != fp:
        die(f"step failed: fabric-secrets store assign {slug} {login} wrote token {row.get('token_sha256_12')}, not the "
            f"{fp} checked at the start (the template changed); nothing after it ran")
    say(f"   Claude account: {slug}, {row['status']} (token {fp})")


# What the account's shell runs for the test signature: its terminal
# named for pinentry before the pipe takes stdin, then one detached
# signature of a fixed line, thrown away. The key is "$1", never spliced.
SIGN_TEST = ('t="$(tty)" || t=""; printf "%s\\n" "new-agent: a test signature" '
             '| GPG_TTY="$t" gpg --batch --local-user "$1" --detach-sign >/dev/null')
TERM_VALUE = re.compile(r"[A-Za-z0-9._+-]{1,64}")


def primary_fingerprint(listing: str) -> str:
    """The primary key's fingerprint in a `--with-colons` secret listing:
    the first fpr record after the first sec record; "" when there is none."""
    seen_sec = False
    for line in listing.splitlines():
        f = line.split(":")
        if f[0] == "sec":
            seen_sec = True
        elif f[0] == "fpr" and seen_sec and len(f) > 9 and re.fullmatch(r"[0-9A-F]{40,64}", f[9]):
            return f[9]
    return ""


def last_line(err, silent: str = "(gpg said nothing)") -> str:
    err.seek(0)
    lines = [ln for ln in err.read().decode("utf-8", "replace").splitlines() if ln.strip()]
    return lines[-1].strip() if lines else silent


def signing_key(login: str, host: str, *, via: str = "") -> int:
    """11. The fleet's signing key into the account's keyring, with a person
    at this terminal: exported by this login's gpg and imported by the
    account's on a pipe, never a file; the passphrase is pinentry's
    (GPG_TTY names this terminal for it), never read, echoed or passed
    here. Its ownertrust set, then proved by a signature made as the
    account — on every run: a key already there skips only the import, so
    a re-run repairs an ownertrust an earlier run did not set and proves
    the key again (#118 review, F2). A failure is said with gpg's last line
    and the two lines a person runs; 0-10 stay done, and this step alone
    exits 1."""
    def failed(why: str) -> int:
        say(f"11. the signing key: FAILED — {why}")
        say("    by hand, as this login, in a terminal (the key has a passphrase):")
        for line in signing_key_lines(login, via):
            print(f"new-agent: {line}", file=sys.stderr)
        return 1

    def ask(cmd: list[str], *, stdin=subprocess.DEVNULL, data: bytes | None = None, env=None,
            stdout=subprocess.PIPE, silent: str = "(gpg said nothing)") -> tuple[int, str]:
        with tempfile.TemporaryFile() as err:
            try:
                r = run_bounded(cmd, stdin=subprocess.PIPE if data is not None else stdin, input=data,
                                stdout=stdout, stderr=err, env=env, timeout=STEP_TIMEOUT_S)
            except subprocess.TimeoutExpired:
                return 124, f"no answer within {STEP_TIMEOUT_S} s"
            except OSError as exc:
                return 127, f"{cmd[0]}: {exc.strerror or exc}"
            if r.returncode != 0:
                return r.returncode, last_line(err, silent)
            return 0, r.stdout.decode("utf-8", "replace") if r.stdout is not None else ""

    sys.stderr.flush()
    rc, key = ask(["git", "-C", ROOT, "config", "--get", "user.signingkey"])
    key = key.strip() if rc == 0 else ""
    if not key:
        return failed("this login's git config names no user.signingkey")
    rc, listing = ask(["gpg", "--list-secret-keys", "--with-colons", "--", key])
    fpr = primary_fingerprint(listing) if rc == 0 and signs_with_secret(listing) else ""
    if not fpr:
        return failed(f"this login's keyring holds no signing secret for {key}" + ("" if rc == 0 else f": {listing}"))
    as_account = [HX, host, "--as", login, "--"]
    rc, theirs = ask([*as_account, "gpg", "--list-secret-keys", "--with-colons", "--", fpr])
    if rc == 0 and signs_with_secret(theirs):
        say(f"11. the signing key {fpr[-16:]}: already in {login}'s keyring; its ownertrust and a test signature follow")
    else:
        why = import_key(login, fpr, as_account)
        if why:
            return failed(why)
    rc, why = ask([*as_account, "gpg", "--batch", "--import-ownertrust"], data=f"{fpr}:6:\n".encode())
    if rc != 0:
        return failed(f"its ownertrust as {login}: {why}")
    term = os.environ.get("TERM", "")
    term_env = ["env", f"TERM={term}"] if TERM_VALUE.fullmatch(term) else []
    sys.stderr.flush()
    # stdout is the person's terminal, never a pipe: over ssh (`hostexec
    # --tty` is `ssh -t`) the remote pty — the one pinentry draws on, and
    # gpg's stderr with it — comes back on ssh's stdout, and a captured
    # stdout hid the prompt (#118 review, F1). So on that backend gpg's
    # words are on the terminal, not in the stderr file.
    rc, why = ask([HX, host, "--tty", "--as", login, "--", *term_env, "sh", "-c", SIGN_TEST, "_", fpr], stdin=None,
                  stdout=None, silent="gpg's words are above, on the terminal")
    if rc != 0:
        return failed(f"the test signature as {login}: {why}")
    say(f"11. the signing key: in {login}'s keyring, trusted, and a test signature made as it — done.")
    return 0


def import_key(login: str, fpr: str, as_account: list[str]) -> str:
    """The export here piped into the import as the account; "" when both
    exited 0, else what failed, with gpg's last line."""
    say(f"11. the signing key {fpr[-16:]}: exported here, imported as {login}; gpg's pinentry asks for its passphrase")
    env = dict(os.environ)
    if not env.get("GPG_TTY") and os.isatty(0):
        env["GPG_TTY"] = os.ttyname(0)
    with tempfile.TemporaryFile() as exp_err, tempfile.TemporaryFile() as imp_err:
        exp = subprocess.Popen(["gpg", "--export-secret-keys", "--", fpr], stdout=subprocess.PIPE, stderr=exp_err, env=env)
        try:
            imp = subprocess.Popen([*as_account, "gpg", "--batch", "--import"], stdin=exp.stdout,
                                   stdout=subprocess.DEVNULL, stderr=imp_err)
        except OSError as exc:
            stop_tree(exp)
            return f"import as {login}: {exc.strerror or exc}"
        finally:
            exp.stdout.close()
        try:
            imp.wait(timeout=STEP_TIMEOUT_S)
            exp.wait(timeout=60)
        except subprocess.TimeoutExpired:
            for p in (exp, imp):
                if p.poll() is None:
                    stop_tree(p)
            return f"the export or the import gave no answer within {STEP_TIMEOUT_S} s"
        # The export first: an import that read nothing says so, and the
        # export's own line is the cause.
        if exp.returncode != 0:
            return f"the export here: {last_line(exp_err)}"
        if imp.returncode != 0:
            return f"the import as {login}: {last_line(imp_err)}"
    return ""


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
