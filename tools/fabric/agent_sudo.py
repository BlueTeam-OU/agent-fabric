#!/usr/bin/env python3
"""tools/fabric/agent_sudo.py — sudo, with a password asked every time,
for the agent accounts this host places, so the owner can elevate from a
shell entered with `su` (the owner, 2026-10-06). `su` itself is left as it
is: /etc/pam.d/su admits the qubes group without a password, and that rule
never looks at the target account's password.

    agent_sudo.py plan [--host H]            what apply would change; no root needed
    agent_sudo.py apply [--host H]           as root: the group, its members, the sudoers rule
    agent_sudo.py passwd [LOGIN...]          as root, in a terminal: set each account's password
    agent_sudo.py check [--host H]           as root: is everything in place (exit 1 when not)

The accounts are the placement of runtime/hosts/registry.json for this
host (its short hostname), but the host's operator, who holds sudo
already. apply:
  - creates the group `agent-sudo` and adds each account to it;
  - writes /etc/sudoers.d/agent-sudo, mode 0440, checked with
    `visudo -cf` before it replaces anything:
        Defaults:%agent-sudo timestamp_timeout=0
        %agent-sudo ALL=(ALL) ALL
    timestamp_timeout=0 asks the password at every sudo: an agent's own
    session, which runs as the same account, can never ride on a prompt
    the owner answered a minute before.
It changes nothing it finds right, so it runs again safely. new-agent
joins a new account to the group when the group exists (step 1 of
new-agent-worker.sh); passwd gives it its password.

Where /etc does not survive a reboot (a Qubes AppVM: platform/detect.sh,
PERSISTS_ACROSS_REBOOT=0), apply also keeps a snapshot under /rw —
the group's /etc/group and /etc/gshadow lines and the rule, in
/rw/config/agent-fabric/agent-sudo/ (root's, 0700/0600) — and installs
platform/qubes/agent-fabric-0-sudo.rc into /rw/config/rc.local.d, which
puts them back at boot before agent-fabric-accounts.rc restores each
login's groups; and passwd re-runs persist-accounts.sh for the accounts it
set, so their shadow lines, and with them the passwords, survive too.

passwd runs passwd(1) for each account, interactively, and refuses inside
a model session (CLAUDECODE set): a password typed there would enter a
transcript. The password is the owner's alone: never stored, never in a
store, never in a message (ADR-038 rule 6's reasoning).
"""
from __future__ import annotations

import grp
import json
import os
import socket
import subprocess
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", ".."))
REGISTRY = os.path.join(ROOT, "runtime", "hosts", "registry.json")
GROUP = "agent-sudo"
SUDOERS = "/etc/sudoers.d/agent-sudo"
RULE = f"Defaults:%{GROUP} timestamp_timeout=0\n%{GROUP} ALL=(ALL) ALL\n"
HEADER = ("# agent-fabric tools/fabric/agent_sudo.py: sudo with a password asked every time,\n"
          "# for the agent accounts this host places. Rewritten by `agent_sudo.py apply`.\n")
USAGE = "usage: agent_sudo.py plan|apply|check [--host H] | passwd [LOGIN...]"
SNAPSHOT = "/rw/config/agent-fabric/agent-sudo"
RC_D = "/rw/config/rc.local.d"
RC_NAME = "agent-fabric-0-sudo.rc"
RC_SRC = os.path.join(ROOT, "runtime", "provisioning", "platform", "qubes", RC_NAME)
PERSIST = os.path.join(ROOT, "runtime", "provisioning", "persist-accounts.sh")


class SudoError(Exception):
    pass


def this_host() -> str:
    return socket.gethostname().split(".")[0]


def accounts(host: str, registry: str = REGISTRY) -> list[str]:
    """The logins placed on `host`, but its operator."""
    with open(registry, encoding="utf-8") as fh:
        reg = json.load(fh)
    if host not in (reg.get("hosts") or {}):
        raise SudoError(f"{host} is not a host in {registry}")
    operator = reg["hosts"][host].get("operator")
    return sorted(login for login, h in (reg.get("placement") or {}).items() if h == host and login != operator)


def members(group: str = GROUP) -> set[str] | None:
    try:
        return set(grp.getgrnam(group).gr_mem)
    except KeyError:
        return None


def plan(logins: list[str], group: str = GROUP, sudoers: str = SUDOERS) -> list[str]:
    have = members(group)
    steps = []
    if have is None:
        steps.append(f"create group {group}")
        have = set()
    steps += [f"add {u} to {group}" for u in logins if u not in have]
    extra = sorted(have - set(logins))
    if extra:
        steps.append(f"(left as they are: {', '.join(extra)} in {group}, placed elsewhere or not at all)")
    try:
        with open(sudoers, encoding="utf-8") as fh:
            current = fh.read()
        if current != HEADER + RULE:
            steps.append(f"rewrite {sudoers}")
    except PermissionError:
        steps.append(f"{sudoers}: not readable from this login (apply, as root, writes it if it differs)")
    except FileNotFoundError:
        steps.append(f"write {sudoers}")
    return steps


def _run(argv: list[str]) -> None:
    r = subprocess.run(argv, capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        raise SudoError(f"{' '.join(argv)}: exit {r.returncode}: {(r.stderr or r.stdout).strip()[:200]}")


def write_sudoers(sudoers: str = SUDOERS, run=_run) -> bool:
    """True when it wrote; the rule is checked by visudo before it replaces anything."""
    want = HEADER + RULE
    try:
        with open(sudoers, encoding="utf-8") as fh:
            if fh.read() == want:
                return False
    except FileNotFoundError:
        pass
    d = os.path.dirname(sudoers)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".agent-sudo.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(want)
        os.chmod(tmp, 0o440)
        run(["visudo", "-cf", tmp])
        os.replace(tmp, sudoers)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return True


def persists(root: str = ROOT) -> bool:
    """Whether /etc survives this host's reboot, as platform/detect.sh says."""
    r = subprocess.run(["bash", "-c", '. "$1/runtime/provisioning/platform/detect.sh" >/dev/null && echo "$PERSISTS_ACROSS_REBOOT"', "_", root],
                       capture_output=True, text=True, timeout=30)
    if r.returncode != 0 or r.stdout.strip() not in ("0", "1"):
        raise SudoError(f"platform/detect.sh could not say whether /etc persists: {(r.stderr or r.stdout).strip()[:200]}")
    return r.stdout.strip() == "1"


def _write_private(path: str, text: str, mode: int) -> None:
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".snap.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def group_line(etc: str, name: str, group: str = GROUP) -> str | None:
    try:
        with open(os.path.join(etc, name), encoding="utf-8") as fh:
            return next((line.rstrip("\n") for line in fh if line.startswith(f"{group}:")), None)
    except FileNotFoundError:
        return None


def snapshot(group: str = GROUP, etc: str = "/etc", snap: str = SNAPSHOT, rcd: str = RC_D, rc_src: str = RC_SRC) -> list[str]:
    """The group's lines and the rule kept under /rw, and the boot script
    that puts them back; only what differs is written."""
    done = []
    os.makedirs(snap, mode=0o700, exist_ok=True)
    os.chmod(snap, 0o700)
    for name, text in (("group", group_line(etc, "group", group)), ("gshadow", group_line(etc, "gshadow", group)),
                       ("sudoers", (HEADER + RULE).rstrip("\n"))):
        if text is None:
            continue
        want = text + "\n"
        path = os.path.join(snap, name)
        try:
            with open(path, encoding="utf-8") as fh:
                if fh.read() == want:
                    continue
        except FileNotFoundError:
            pass
        _write_private(path, want, 0o600)
        done.append(f"kept {name} under {snap}")
    with open(rc_src, encoding="utf-8") as fh:
        rc = fh.read()
    dest = os.path.join(rcd, os.path.basename(rc_src))
    try:
        with open(dest, encoding="utf-8") as fh:
            same = fh.read() == rc
    except FileNotFoundError:
        same = False
    if not same:
        os.makedirs(rcd, mode=0o755, exist_ok=True)
        _write_private(dest, rc, 0o755)
        done.append(f"installed {dest}")
    return done


def apply(logins: list[str], group: str = GROUP, sudoers: str = SUDOERS, run=_run) -> list[str]:
    done = []
    have = members(group)
    if have is None:
        run(["groupadd", group])
        done.append(f"created group {group}")
        have = set()
    for u in logins:
        if u not in have:
            run(["usermod", "-aG", group, u])
            done.append(f"added {u} to {group}")
    if write_sudoers(sudoers, run):
        done.append(f"wrote {sudoers}")
    return done


def snapshot_problems(group: str = GROUP, etc: str = "/etc", snap: str = SNAPSHOT, rcd: str = RC_D, rc_src: str = RC_SRC) -> list[str]:
    problems = []
    for name in ("group", "gshadow"):
        live = group_line(etc, name, group)
        try:
            with open(os.path.join(snap, name), encoding="utf-8") as fh:
                kept = fh.read().rstrip("\n")
        except FileNotFoundError:
            kept = None
        if live is not None and kept != live:
            problems.append(f"{snap}/{name} does not hold the live {group} line: a reboot would lose it (apply)")
    if not os.path.exists(os.path.join(snap, "sudoers")):
        problems.append(f"no {snap}/sudoers: a reboot would lose the rule (apply)")
    if not os.path.exists(os.path.join(rcd, os.path.basename(rc_src))):
        problems.append(f"no {rcd}/{os.path.basename(rc_src)}: nothing puts them back at boot (apply)")
    return problems


def check(logins: list[str], group: str = GROUP, sudoers: str = SUDOERS) -> list[str]:
    """What is not in place; empty when all is."""
    problems = []
    have = members(group)
    if have is None:
        problems.append(f"no group {group}")
    else:
        problems += [f"{u} not in {group}" for u in logins if u not in have]
    try:
        with open(sudoers, encoding="utf-8") as fh:
            if fh.read() != HEADER + RULE:
                problems.append(f"{sudoers} differs from the rule")
    except FileNotFoundError:
        problems.append(f"no {sudoers}")
    return problems


def set_passwords(logins: list[str], env=os.environ, run_tty=subprocess.call) -> int:
    if env.get("CLAUDECODE"):
        raise SudoError("passwd refuses inside a model session: a password typed here enters its transcript. "
                        "Run it from your own terminal.")
    if not sys.stdin.isatty():
        raise SudoError("passwd needs a terminal: it asks each password interactively")
    failed = []
    for u in logins:
        print(f"== {u}")
        if run_tty(["passwd", u]) != 0:
            failed.append(u)
    if failed:
        print(f"agent_sudo: no password set for {', '.join(failed)}", file=sys.stderr)
    return 1 if failed else 0


def main(argv: list[str]) -> int:
    if not argv or argv[0] not in ("plan", "apply", "check", "passwd"):
        print(USAGE, file=sys.stderr)
        return 2
    cmd, rest = argv[0], argv[1:]
    try:
        if cmd == "passwd":
            if os.geteuid() != 0:
                raise SudoError(f"passwd sets other accounts' passwords: run it as root (sudo /usr/bin/python3 {os.path.abspath(__file__)} passwd)")
            known = accounts(this_host())
            unknown = [u for u in rest if u not in known]
            if unknown:
                raise SudoError(f"not an agent account placed on this host: {', '.join(unknown)}")
            rc = set_passwords(rest or known)
            # The shadow lines carry the new hashes; where /etc is volatile
            # the snapshot persist-accounts.sh keeps must take them now.
            if not persists():
                r = subprocess.run(["bash", PERSIST, *(rest or known)], timeout=300)
                if r.returncode != 0:
                    print("agent_sudo: persist-accounts.sh failed: the passwords may not survive a reboot", file=sys.stderr)
                    rc = 1
            return rc
        host = this_host()
        if rest[:1] == ["--host"] and len(rest) == 2:
            host = rest[1]
        elif rest:
            print(USAGE, file=sys.stderr)
            return 2
        logins = accounts(host)
        if cmd == "plan":
            steps = plan(logins)
            print("\n".join(steps) if steps else "nothing to change")
            return 0
        if os.geteuid() != 0:
            raise SudoError(f"{cmd} needs root (sudo /usr/bin/python3 {os.path.abspath(__file__)} {cmd})")
        if cmd == "apply":
            done = apply(logins)
            if not persists():
                done += snapshot()
            print("\n".join(done) if done else "nothing to change")
            print("a new group reaches a login at its next login: a running su shell or session does not have it yet")
            return 0
        problems = check(logins) + ([] if persists() else snapshot_problems())
        print("\n".join(problems) if problems else f"agent-sudo: {len(logins)} accounts in {GROUP}, {SUDOERS} in place")
        return 1 if problems else 0
    except (SudoError, OSError) as e:
        print(f"agent_sudo: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
