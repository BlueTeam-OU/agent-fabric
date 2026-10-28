#!/usr/bin/env python3
"""tools/fabric/cpu_shim.py — /usr/local/bin/cargo and /usr/local/bin/dotnet:
take a slot of the host's `cpu` lease for a heavy subcommand, then become the
real tool (ADR-010 §5 rule 9, A 2026-10-28; the slots are tools/fabric/lease.py's;
provisioning/install_cpu_shims.py places this).

CONTRACT
  argv      <cargo|dotnet> [the tool's own arguments...] — the forwarder passes
            the tool's name, then what the caller typed, untouched
  env       AGENT_FABRIC_CPU_WAIT   seconds to wait for a slot, whole; the
                                    policy's wait_s (1500) when unset or empty
            AGENT_FABRIC_CPU_LEASE  `0`: no slot, one line on stderr
            FABRIC_CPU_SLOT         set (a slot's child): no slot — a cargo test
                                    that runs cargo never waits on its own slot
            CI                      set: no slot
            AGENT_FABRIC_LEASES     the lease directory, as fabric-lease reads it
            AGENT_FABRIC_CPU_TOOLS  where the real tools are, /usr/bin when
                                    unset or empty (tests; /usr/bin/cargo named
                                    by path bypasses the shim, accepted in the ADR)
  heavy     cargo build b test t check c clippy run r bench doc install nextest
            llvm-cov; dotnet build test publish run pack. Everything else — fmt,
            metadata, tree, --version, new, add, restore, --info, and any
            -h/--help — runs the tool at once, with no policy read and no lease
            directory needed.
  stdout    the tool's, nothing of ours
  stderr    the tool's; ours are fabric-lease's lines (lease.py acquire_cpu):
            the wait, the grant, the refusal ending reason=held|timeout|nodir|
            unopenable|cpu-policy|cpu-wait, and the opt-out line
  exit      the tool's (it is this process, exec'd); 75 no slot came free; 2 a
            lease directory, lease file, policy or wait that cannot be used;
            127 / 126 the real tool is absent / not executable

HOW. The process takes the slot and then EXECS the tool with the slot's
descriptor inherited: the slot lives as long as the build and anything it
leaves behind, and a KILL to the shim is a KILL to the tool, never a way to
free the slot under a running build. The tool gets its thread budget, and
MSBuild's node reuse and build server off, so nothing long-lived inherits the
slot (lease.cpu_child_env). A policy that cannot be read refuses the heavy
subcommands rather than guessing how many builds the host runs at once.
"""
from __future__ import annotations

import os
import signal
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lease  # noqa: E402

HEAVY = {
    "cargo": frozenset("build b test t check c clippy run r bench doc install nextest llvm-cov".split()),
    "dotnet": frozenset("build test publish run pack".split()),
}
# Cargo's own options before the subcommand that take the next argument as their value.
CARGO_VALUE_OPTIONS = frozenset({"-C", "--color", "--config", "-Z", "--explain"})
DEFAULT_TOOLS = "/usr/bin"


def subcommand(tool: str, args: list[str]) -> str | None:
    """The subcommand the tool would run, None when the arguments name none or
    ask for help or the version. Looked for the way each tool reads its own
    command line: cargo skips `+toolchain` and its global options, dotnet its
    diagnostics switch; a first word that is not a subcommand (a path to an
    assembly) is returned as it is and is not heavy."""
    i = 0
    if tool == "cargo":
        if args and args[0].startswith("+"):
            i = 1
        while i < len(args):
            a = args[i]
            if a in ("-h", "--help", "-V", "--version", "--list"):
                return None
            if a in CARGO_VALUE_OPTIONS:
                i += 2
            elif a.startswith("-"):
                i += 1
            else:
                return a
        return None
    while i < len(args) and args[i] in ("-d", "--diagnostics"):
        i += 1
    return args[i] if i < len(args) and not args[i].startswith("-") else None


def asks_for_help(args: list[str]) -> bool:
    """-h or --help among the tool's own arguments (those after a bare `--`
    are the program's, as in `cargo run -- --help`)."""
    for a in args:
        if a == "--":
            return False
        if a in ("-h", "--help"):
            return True
    return False


def is_heavy(tool: str, args: list[str]) -> str | None:
    """The subcommand when it takes a slot."""
    sub = subcommand(tool, args)
    return sub if sub in HEAVY[tool] and not asks_for_help(args) else None


def plain(path: str, args: list[str], pipe_ignored: bool) -> int:
    """The tool with nothing of ours held; only a return means it could not run."""
    signal.signal(signal.SIGPIPE, signal.SIG_IGN if pipe_ignored else signal.SIG_DFL)
    signal.signal(signal.SIGXFSZ, signal.SIG_DFL)
    try:
        os.execv(path, [path, *args])
    except FileNotFoundError:
        lease.err(f"fabric-lease: {path}: No such file or directory\n")
        return 127
    except OSError as e:
        lease.err(f"fabric-lease: {path}: {os.strerror(e.errno or 0)}\n")
        return 126


def run(argv: list[str]) -> int:
    if len(argv) < 1 or argv[0] not in HEAVY:
        lease.err("usage: cpu_shim.py <cargo|dotnet> [arguments...]\n")
        return 2
    tool, args = argv[0], argv[1:]
    path = os.path.join(os.environ.get("AGENT_FABRIC_CPU_TOOLS") or DEFAULT_TOOLS, tool)
    pipe_ignored = os.environ.pop(lease.PIPE_IGNORED_ENV, "") == "1"
    # Python handles INT itself; until the tool exists a signal kills this
    # process, which holds nothing yet or is waiting for a slot.
    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        if signal.getsignal(sig) != signal.SIG_IGN:
            signal.signal(sig, signal.SIG_DFL)
    sub = is_heavy(tool, args)
    why = lease.cpu_pass_through() if sub else "light"
    if why == "opt-out":
        lease.err(f"fabric-lease: {lease.OPT_OUT_ENV}=0 — {tool} {sub} runs without a cpu slot\n")
    if why:
        return plain(path, args, pipe_ignored)
    policy = lease.cpu_policy()
    leases = os.environ.get("AGENT_FABRIC_LEASES") or lease.DEFAULT_LEASES
    slot = lease.acquire_cpu(leases, policy, lease.clean_label(f"{tool} {sub}"), lease.cpu_wait(policy))
    return lease.hold_and_exec([path, *args], slot, pipe_ignored)


def main(argv: list[str] | None = None) -> int:
    try:
        return run(sys.argv[1:] if argv is None else argv)
    except lease.Exit as e:
        return e.code


if __name__ == "__main__":
    sys.exit(main())
