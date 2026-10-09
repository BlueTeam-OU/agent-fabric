#!/usr/bin/env python3
"""runtime/hostexec/hostexec — run one command on a host the fabric
operates, as the host's operator or as an account there. The one
boundary between the coordinator and the machines the agents live on.

  hostexec <host> [--as <login>] [--cwd <dir>] [--tty] -- <cmd> [args...]
  hostexec --resolve <host>          print the backend and destination, run nothing

<host> is an id in runtime/hosts/registry.json (its short hostname).
Two backends, chosen by the registry, never by the caller:

  local   the host this checkout is on (`ssh: null`): the command goes
          to the worker (tools/fabric/hostworker.py, run in this
          process) — today's direct sudo and filesystem access, unchanged.
  ssh     any other host: `ssh -o BatchMode=yes <ssh destination> --
          <fabric>/runtime/hostexec/worker ...`, the SAME worker on
          the target, as its operator, who holds sudo there. getent,
          passwd, PAM, /run/user, rootless containers and the account's
          home are all host-local, so the work happens where they are;
          nothing here makes a remote home look local.

stdin flows through both backends (a token, a bundle); a secret never
travels in argv. --tty asks for a terminal (an interactive shell such
as moveto); stdout/stderr and the exit status are the command's.

The host is never guessed: a host absent from the registry is a
refusal, and `fabric-host <host> check` compares what the target
reports (`hostname -s`) with the id it was reached as.

$AGENT_FABRIC_HOSTS_REGISTRY points a test at a fixture registry; $SSH
names the ssh to use (a test puts a fake here).

Contract (ADR-040 Wave 9; ported from the bash hostexec, which this keeps):
  registry  AGENT_FABRIC_HOSTS_REGISTRY, else this checkout's
            runtime/hosts/registry.json. Deliberately not roots.py's
            operator tree: hostexec is the host executor and fabric-host,
            which does consult it, exports the answer.
  output    stdout/stderr and the exit status of the worker (local) or of
            ssh (remote); `--resolve` prints one line.
  exit      2 for a usage error, an unknown host or an unreadable
            registry; 127 when ssh is not found; otherwise the command's.
"""
from __future__ import annotations

import json
import os
import shlex
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))


class Refused(Exception):
    """A refusal said as `hostexec: <message>`, exit 2."""


def help_text() -> str:
    return (__doc__ or "").split("\n\nContract", 1)[0] + "\n"


def parse(argv: list[str]) -> tuple[str, str, str, bool, bool, list[str]] | int:
    """(host, as, cwd, tty, resolve, command), or the exit status of --help."""
    host = as_login = cwd = ""
    tty = resolve = False
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--resolve":
            resolve, i = True, i + 1
        elif a in ("--as", "--cwd"):
            if i + 1 >= len(argv):
                raise Refused(f"{a} needs a value")
            if a == "--as":
                as_login = argv[i + 1]
            else:
                cwd = argv[i + 1]
            i += 2
        elif a.startswith("--as="):
            as_login, i = a[len("--as="):], i + 1
        elif a.startswith("--cwd="):
            cwd, i = a[len("--cwd="):], i + 1
        elif a == "--tty":
            tty, i = True, i + 1
        elif a == "--":
            i += 1
            break
        elif a in ("-h", "--help"):
            sys.stdout.write(help_text())
            return 0
        elif a.startswith("-"):
            raise Refused(f"unknown flag {a}")
        else:
            if host:
                raise Refused("one host, then -- and the command")
            host, i = a, i + 1
    return host, as_login, cwd, tty, resolve, argv[i:]


def load_host(registry: str, host: str) -> tuple[str, str, str, str]:
    """(backend, ssh destination or '-', operator, fabric) of `host`."""
    try:
        with open(registry, encoding="utf-8") as fh:
            reg = json.load(fh)
    except OSError:
        raise Refused(f"no host registry at {registry}") from None
    except ValueError as e:
        raise Refused(f"the host registry {registry} is not JSON ({e})") from None
    hosts = reg.get("hosts") if isinstance(reg, dict) else None
    hosts = hosts if isinstance(hosts, dict) else {}
    h = hosts.get(host)
    if not h:
        raise Refused(f"unknown host {host!r}; known: {', '.join(sorted(hosts)) or 'none'}")
    try:
        return ("local" if h.get("ssh") is None else "ssh", h.get("ssh") or "-", h["operator"], h["fabric"])
    except (KeyError, AttributeError, TypeError):
        raise Refused(f"host {host!r} in {registry} lacks its operator or fabric") from None


def remote_line(fabric: str, worker_args: list[str]) -> str:
    """The one command LINE ssh hands the remote shell; every word quoted so
    an argument with a space or a quote arrives whole. ~ in the fabric path
    is the operator's home there, expanded by that shell — the one place it
    is meant to expand."""
    remote = fabric + "/runtime/hostexec/worker"
    line = remote if fabric == "~" or fabric.startswith("~/") else shlex.quote(remote)
    return " ".join([line, *(shlex.quote(a) for a in worker_args)])


def main(argv: list[str]) -> int:
    try:
        parsed = parse(argv)
        if isinstance(parsed, int):
            return parsed
        host, as_login, cwd, tty, resolve, command = parsed
        if not host:
            raise Refused("no host named (an id in runtime/hosts/registry.json; fabric-host list)")
        registry = os.environ.get("AGENT_FABRIC_HOSTS_REGISTRY") or os.path.join(ROOT, "runtime", "hosts", "registry.json")
        backend, dest, operator, fabric = load_host(registry, host)
        if resolve:
            print(f"host {host}: backend {backend}, destination {dest}, operator {operator}, fabric {fabric}")
            return 0
        if not command:
            raise Refused("no command after --")
    except Refused as e:
        print(f"hostexec: {e}", file=sys.stderr)
        return 2
    worker_args = (["--as", as_login] if as_login else []) + (["--cwd", cwd] if cwd else []) + ["--", *command]
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import hostworker  # noqa: E402 — beside this file; the same exec, signals and messages as the worker's own
    if backend == "local":
        # The worker as a program, as before: its own argv, its own exec.
        return hostworker.main(worker_args)
    ssh = (os.environ.get("SSH") or "ssh").split()
    return hostworker.exec_or_say([*ssh, "-o", "BatchMode=yes", *(["-t"] if tty else []), dest, "--",
                                   remote_line(fabric, worker_args)], who="hostexec")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
