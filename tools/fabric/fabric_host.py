#!/usr/bin/env python3
"""bin/fabric-host — the coordinator's door to the hosts the agents live on.

  fabric-host list                                  hosts and placements (the hosts registry, found by tools/fabric/roots.py)
  fabric-host <host> check                          the host answers as the id it is registered under
  fabric-host <host> run [--as <login>] [--tty] -- <cmd>...   one command there (runtime/hostexec/hostexec)
  fabric-host <host> moveto <login> [<clone>]       an interactive shell as that account, in its workspace
  fabric-host <host> rename <login> <old> <new> [--dry-run]   provisioning/rename_working_copy.py, run there
  fabric-host <host> persist                        every placement survives the host's reboot (linger; the record snapshot on Qubes)
  fabric-host <host> drain <login> [harvest flags...] > drain.tar   the account's memory as a bundle (stdout) — the sudo
                                                                   fallback; the drain is fabric-ctl <login> memory (docs/adr/ADR-029-the-control-plane-a-control-agent-per-account.md)

Every subcommand is the same operation on every host: the local one is
reached directly (today's sudo and filesystem access, unchanged), any
other over ssh, with the same worker on the far side — the backend is
the registry's choice, never the caller's. What the coordinator keeps
to itself (its own store, the API keys) never goes through here; what is
host-local (accounts, homes, installers, a shell, a rename, a drain)
always does. A path given as @fabric/<rel> is under the fabric checkout
on the TARGET host, wherever its operator keeps it. ADR-010.

Contract (ADR-040 Wave 9; ported from the bash fabric-host, which this keeps):
  registry  roots.hosts_registry(engine=code_root()): AGENT_FABRIC_HOSTS_REGISTRY,
            else the operator's tree, else THIS checkout's — whatever
            AGENT_FABRIC_ROOT (every session exports one) names. An answer
            roots cannot give is a refusal (exit 1), never the checkout's own
            file. It is exported, so hostexec, which keeps its own default,
            reads the same registry when this runs it.
  exit      2 for a usage error; 1 for an unresolvable registry, a host that
            does not answer or answers under another name; otherwise the
            command's (run, moveto, rename, persist and drain exec hostexec).
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
HX = os.path.join(ROOT, "runtime", "hostexec", "hostexec")
USAGE_SUBCOMMANDS = "list | check | run | moveto | rename | persist | drain"
# The bash had no bound on `check`; a host that answers nothing for this long is unreachable. The kernel's own TCP connect
# limit (about two minutes) ends an attempt on a host that is down earlier; this bounds one that connects and then says nothing.
CHECK_TIMEOUT_S = 300


class Refused(Exception):
    def __init__(self, message: str, status: int = 2) -> None:
        super().__init__(message)
        self.status = status


# The fleet's pinned interpreter on the target host (runtime/python.json); the
# provisioning entries run on it, never on whatever python3 the host has.
FABRIC_PYTHON = "/usr/local/bin/fabric-python"


def usage_lines() -> str:
    """The synopsis block alone: what `fabric-host` prints for -h and for a
    missing argument."""
    return "\n".join((__doc__ or "").split("\n")[:10]) + "\n"


def resolve_registry() -> str:
    sys.path.insert(0, HERE)
    try:
        import roots
        path = roots.hosts_registry(engine=roots.code_root())
    except Exception as e:  # noqa: BLE001 — any failure of the resolver is one refusal, never a fallback
        raise Refused(f"cannot resolve the hosts registry (tools/fabric/roots.py failed: {e.__class__.__name__}: {e})", 1) from None
    if not path:
        raise Refused("cannot resolve the hosts registry (tools/fabric/roots.py gave no path)", 1)
    return path


def load_registry(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
    except (OSError, ValueError) as e:
        raise Refused(f"the hosts registry {path} is unreadable ({e.__class__.__name__})", 1) from None
    if not isinstance(doc, dict):
        raise Refused(f"the hosts registry {path} is not an object", 1)
    return doc


def list_text(reg: dict) -> str:
    hosts = reg.get("hosts") or {}
    placement = reg.get("placement") or {}
    out = []
    for hid, h in sorted(hosts.items()):
        where = "this host (direct)" if h.get("ssh") is None else f"ssh {h['ssh']}"
        out.append(f"{hid:20} {h['platform']:14} operator {h['operator']:12} {where}")
        placed = sorted(login for login, p in placement.items() if p == hid)
        out.append("                     accounts: " + (", ".join(placed) or "(none placed)"))
    unplaced = sorted(login for login, p in placement.items() if p not in hosts)
    if unplaced:
        out.append("placed on an unknown host: " + ", ".join(unplaced))
    return "".join(line + "\n" for line in out)


def run_hostexec(argv: list[str]) -> int:
    """Replace this process by hostexec; the registry it reads is exported."""
    import hostworker
    return hostworker.exec_or_say([HX, *argv], who="fabric-host")


def main(argv: list[str]) -> int:
    if not argv:
        sys.stdout.write(usage_lines())
        return 2
    if argv[0] in ("-h", "--help"):
        sys.stdout.write(usage_lines())
        return 0
    sys.path.insert(0, HERE)
    try:
        registry = resolve_registry()
        os.environ["AGENT_FABRIC_HOSTS_REGISTRY"] = registry
        if argv[0] == "list":
            sys.stdout.write(list_text(load_registry(registry)))
            return 0
        host, rest = argv[0], argv[1:]
        if not rest:
            sys.stdout.write(usage_lines())
            return 2
        sub, rest = rest[0], rest[1:]
        if sub == "check":
            return check(host, registry)
        if sub == "run":
            return run_hostexec([host, *rest])
        if sub == "moveto":
            if not rest:
                raise Refused("moveto needs the login")
            return run_hostexec([host, "--tty", "--", "moveto", rest[0], *rest[1:]])
        if sub == "rename":
            if len(rest) < 3:
                raise Refused("rename needs <login> <old> <new>")
            return run_hostexec([host, "--", FABRIC_PYTHON, "-I", "@fabric/tools/fabric/provisioning/rename_working_copy.py", *rest])
        if sub == "persist":
            placement = load_registry(registry).get("placement") or {}
            logins = [login for login, p in placement.items() if p == host]
            if not logins:
                raise Refused(f"no placements on {host}")
            return run_hostexec([host, "--", "sudo", "-n", FABRIC_PYTHON, "-I", "@fabric/tools/fabric/provisioning/persist_accounts.py", *logins])
        if sub == "drain":
            if not rest:
                raise Refused("drain needs the login")
            if os.isatty(1):
                raise Refused("drain writes a tar to stdout; redirect it (> drain.tar) or pipe it to assemble.py --bundle -")
            return run_hostexec([host, "--as", rest[0], "--", "python3", "@fabric/tools/fabric/harvest_memory.py", "--bundle", "-", *rest[1:]])
        raise Refused(f"unknown subcommand {sub} ({USAGE_SUBCOMMANDS})")
    except Refused as e:
        print(f"fabric-host: {e}", file=sys.stderr)
        return e.status


def check(host: str, registry: str) -> int:
    import subprocess
    try:
        r = subprocess.run([HX, host, "--", "hostname", "-s"], capture_output=False, stdout=subprocess.PIPE, text=True,
                           stdin=subprocess.DEVNULL, timeout=CHECK_TIMEOUT_S)
    except (OSError, subprocess.TimeoutExpired):
        r = None
    if r is None or r.returncode != 0:
        raise Refused(f"{host}: unreachable, or the worker did not run (see above)", 1)
    reported = r.stdout.rstrip("\n")
    if reported == host:
        print(f"host {host}: answers as {host}")
        return 0
    raise Refused(f"{host} answers as '{reported}': the registry id is the host's short hostname, and this one is not; "
                  f"fix {registry} or the host's name before placing an account there", 1)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
