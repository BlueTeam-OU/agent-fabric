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

import json
import os
import pwd
import signal
import sys
import tempfile

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)
import roots  # noqa: E402
from provisioning import config as cfg  # noqa: E402
from provisioning.new_agent_args import HELP, Exit, die, parse, say  # noqa: E402
from provisioning.signing import signing_key  # noqa: E402
from provisioning.steps import Steps  # noqa: E402
from provisioning.store_step import HUMAN_SHARED, claude_template, login_kind, secrets_step  # noqa: E402


def project_remote(pid: str) -> str | None:
    """The registry's SSH remote for a project (its first remote when it
    names none), or None when the registry does not hold it."""
    try:
        with open(roots.projects_registry(engine=cfg.ROOT), encoding="utf-8") as fh:
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


def new_agent(argv: list[str]) -> int:
    o = parse(argv)
    login, role, host, dry = o["login"], o["role"], o["host"], o["dry"]
    coord = pwd.getpwuid(os.getuid()).pw_name
    if coord == "root":
        die("run this as the fabric-coordinator login, not root: the account's store is filled from yours.")

    # ---- what is asked for must exist in the fabric ---------------------
    if not o["human"] and not os.path.isfile(os.path.join(roots.role_dir(role, engine=cfg.ROOT), "charter.md")):
        die(f"no role '{role}' under identities/roles/ (fabric-role list).")
    remote = {}
    for pid in o["projects"]:
        r = project_remote(pid)
        if r is None:
            die(f"project '{pid}' is not in projects/registry.json — register it first.")
        remote[pid] = r

    hosts_path = roots.hosts_registry(engine=cfg.ROOT)
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
    if s.through([cfg.HX, "--resolve", host], timeout=60, quiet_stdout=True) != 0:
        raise Exit(1, None)
    # The host names itself; a name other than the id it was reached as is refused.
    rc, check = s.capture([cfg.HX, host, "--", cfg.WORKER, "host-check", login], timeout=120)
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
    if s.through([cfg.HX, host, "--", cfg.WORKER, "prepare", login, *who, *claude, *dry_arg]) != 0:
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
    if s.through([cfg.HX, host, "--", cfg.WORKER, "finish", login, *who, *clones, *account, *nxt, *via, *dry_arg]) != 0:
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
