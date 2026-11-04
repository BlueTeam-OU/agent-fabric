#!/usr/bin/env python3
"""tools/fabric/provisioning/install_cpu_shims.py — place the cpu lease's shims:
/usr/local/bin/cargo and /usr/local/bin/dotnet, which take a slot for a heavy
subcommand and run /usr/bin/<tool> (ADR-010 §5 rule 9, A 2026-10-28). Needs
root; idempotent.

    sudo /usr/local/bin/fabric-python tools/fabric/provisioning/install_cpu_shims.py

CONTRACT
  installs  <prefix>/share/agent-fabric/cpu-lease-<hash>/{lease.py,cpu_shim.py,
            host-load.json} (644, directories 755): a COPY of the repository's
            files, named by the hash of their contents, so the shim never runs a
            lease.py of one version beside a cpu_shim.py of another, and a
            policy change (policies/host-load.json) is applied by running this
            again; and <prefix>/bin/cargo, <prefix>/bin/dotnet (755), forwarders
            that name that directory. The directory is made whole before any
            forwarder names it, and each forwarder is replaced by a rename, so a
            run cut off at any step leaves forwarders that work. Directories of
            earlier hashes (and the leftovers of a cut-off run) are removed once the forwarders name the new one.
  forwarder keeps bin/fabric-lease's SIGPIPE hand-over; and, where the pinned
            Python or the copy is missing, says so on stderr and runs the real
            tool without a slot — a load measure must not take every build on
            the host down with it. (A policy that is present and invalid is the
            shim's refusal, not this fallback.)
  prefix    /usr/local; CPU_SHIMS_PREFIX overrides it for a test, honoured only
            when not root, as python_pin.py's overrides are.
  stdout    one line: installed (the directory) or already in place
  exit      0 done; 1 not root, or a step failed (said on stderr, nothing after it ran)
"""
from __future__ import annotations

import hashlib
import os
import shutil
import sys
import tempfile

FABRIC = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
# (source in the repository, name in the installed directory)
PAYLOAD = (("tools/fabric/lease.py", "lease.py"), ("tools/fabric/cpu_shim.py", "cpu_shim.py"),
           ("policies/host-load.json", "host-load.json"))
TOOLS = ("cargo", "dotnet")
SHARE = "share/agent-fabric"
STEM = "cpu-lease-"

FORWARDER = """#!/bin/bash
# {tool}: takes a slot of the host's cpu lease for a heavy subcommand (agent-fabric ADR-010 A 2026-10-28).
unset _FABRIC_LEASE_PIPE_IGNORED
[[ "$(trap -p PIPE)" == *"''"* ]] && export _FABRIC_LEASE_PIPE_IGNORED=1
py={prefix}/bin/fabric-python
shim={directory}/cpu_shim.py
[[ -x $py && -r $shim ]] || {{ echo "{tool}: the cpu lease shim is not installed at $shim; running /usr/bin/{tool} without a slot" >&2; exec /usr/bin/{tool} "$@"; }}
exec "$py" -I "$shim" {tool} "$@"
"""


def prefix() -> str:
    return "/usr/local" if os.geteuid() == 0 else os.environ.get("CPU_SHIMS_PREFIX") or "/usr/local"


def digest(root: str = FABRIC) -> str:
    h = hashlib.sha256()
    for src, name in PAYLOAD:
        with open(os.path.join(root, src), "rb") as fh:
            data = fh.read()
        h.update(f"{name}\0{len(data)}\0".encode() + data)
    return h.hexdigest()[:16]


def _replace(path: str, data: bytes, mode: int) -> None:
    fd, tmp = tempfile.mkstemp(prefix=".install-", dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        if os.path.lexists(tmp):
            os.unlink(tmp)
        raise


def install(pfx: str, root: str = FABRIC) -> str:
    """Make the forwarders name this repository's files; what was done, in one line."""
    share = os.path.join(pfx, SHARE)
    directory = os.path.join(share, STEM + digest(root))
    os.makedirs(share, exist_ok=True)
    os.chmod(share, 0o755)
    made = not os.path.isdir(directory)
    if made:
        tmp = tempfile.mkdtemp(dir=share, prefix=".cpu-lease-")
        try:
            for src, name in PAYLOAD:
                with open(os.path.join(root, src), "rb") as fh:
                    _replace(os.path.join(tmp, name), fh.read(), 0o644)
            os.chmod(tmp, 0o755)
            os.rename(tmp, directory)
        except BaseException:
            shutil.rmtree(tmp, ignore_errors=True)
            raise
    os.makedirs(os.path.join(pfx, "bin"), exist_ok=True)
    changed = made
    for tool in TOOLS:
        path = os.path.join(pfx, "bin", tool)
        text = FORWARDER.format(tool=tool, prefix=pfx, directory=directory).encode()
        try:
            with open(path, "rb") as fh:
                same = fh.read() == text and os.access(path, os.X_OK)
        except OSError:
            same = False
        if not same:
            _replace(path, text, 0o755)
            changed = True
    for name in os.listdir(share):
        if name.startswith((STEM, ".cpu-lease-")) and os.path.join(share, name) != directory:
            shutil.rmtree(os.path.join(share, name), ignore_errors=True)
    return f"cpu shims installed: {directory}" if changed else f"cpu shims already in place: {directory}"


def main(argv: list[str]) -> int:
    if argv:
        print("usage: install_cpu_shims.py", file=sys.stderr)
        return 2
    if os.geteuid() != 0 and not os.environ.get("CPU_SHIMS_PREFIX"):
        print(f"install_cpu_shims: writes {prefix()}/bin: run it as root "
              f"(sudo /usr/local/bin/fabric-python {os.path.abspath(__file__)})", file=sys.stderr)
        return 1
    try:
        print(install(prefix()))
    except (OSError, ValueError) as e:
        print(f"install_cpu_shims: {e.strerror or e}{': ' + e.filename if getattr(e, 'filename', None) else ''}; nothing after it ran",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
