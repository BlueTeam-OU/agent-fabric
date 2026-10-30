#!/usr/bin/env python3
"""tools/fabric/provisioning/install_fleetdeck.py — install the FleetDeck binary
the harness unit runs (runtime/control/agent-fabric-harness.service). Needs root.

    sudo python3 tools/fabric/provisioning/install_fleetdeck.py --from <path>

There is no release pipeline (the owner's packaging decision, 2026-10-27): the
operator builds the binary from the fork (BlueTeam-OU/agent-fabric-fleetdeck)
and the owner installs it here. A release-asset pin through tools_install
comes later and replaces the --from path, not the files below.

CONTRACT
  argv      --from PATH (required): the built binary. Refused, exit 1 with one
            line and nothing written, unless PATH is a regular file with an
            execute bit; a symlink is followed, as `install` follows it.
            -h/--help: this text's usage. A bad option: exit 2 (argparse).
  env       FLEETDECK_PREFIX replaces /usr/local, for a test (as MOVETO_PREFIX
            does for install_moveto.py). Nothing else is read.
  installs  <prefix>/bin/agent-fabric-fleetdeck, 0755, root:root when run as
            root (a test as another user keeps its own owner: chown to root
            needs root and is not attempted), replaced by rename so a server
            already running keeps the inode it started from. The directories
            are made 0755.
  manifest  <prefix>/share/agent-fabric-fleetdeck/installed.sha256, 0644,
            swapped in whole: the sha256sum line of the installed binary
            (relative to the prefix, `sha256sum -c` reads it from there) and a
            `# source: <absolute path>` comment line naming what was copied,
            which sha256sum ignores.
  stdout    `agent-fabric-fleetdeck installed to <prefix>/bin/... (sha256 …)`
  exit      0 done; 1 a refusal or any step failed (nothing after it ran),
            said on stderr in one line.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import stat
import sys
import tempfile
from collections.abc import Mapping

BIN = "bin/agent-fabric-fleetdeck"
MANIFEST = "share/agent-fabric-fleetdeck/installed.sha256"


class Refused(Exception):
    """One line on stderr, exit 1, nothing installed."""


def _sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def check_source(path: str) -> None:
    try:
        mode = os.stat(path).st_mode
    except OSError as e:
        raise Refused(f"{path}: {e.strerror or e}") from None
    if not stat.S_ISREG(mode):
        raise Refused(f"{path} is not a regular file")
    if not mode & 0o111:
        raise Refused(f"{path} is not executable")


def _replace_whole(src: str | None, dst: str, mode: int, data: str | None = None) -> None:
    """DST replaced by rename from a temporary file beside it, so a reader or a running binary never sees half a file."""
    fd, tmp = tempfile.mkstemp(prefix=".install-", dir=os.path.dirname(dst))
    try:
        with os.fdopen(fd, "wb") as out:
            if src is not None:
                with open(src, "rb") as fh:
                    shutil.copyfileobj(fh, out)
            else:
                out.write((data or "").encode("utf-8"))
        os.chmod(tmp, mode)
        if os.geteuid() == 0:
            os.chown(tmp, 0, 0)
        os.replace(tmp, dst)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def install(prefix: str, source: str) -> str:
    """Install `source` under `prefix`; the sha256 of what is there afterwards."""
    check_source(source)
    for sub in ("bin", "share/agent-fabric-fleetdeck"):
        os.makedirs(os.path.join(prefix, sub), exist_ok=True)
        os.chmod(os.path.join(prefix, sub), 0o755)
    _replace_whole(source, os.path.join(prefix, BIN), 0o755)
    # Read back from the destination, not the source: the manifest says what is installed.
    digest = _sha256(os.path.join(prefix, BIN))
    _replace_whole(None, os.path.join(prefix, MANIFEST), 0o644, f"{digest}  {BIN}\n# source: {os.path.abspath(source)}\n")
    return digest


def main(argv: list[str] | None = None, environ: Mapping[str, str] | None = None) -> int:
    env = os.environ if environ is None else environ
    parser = argparse.ArgumentParser(prog="install_fleetdeck", description="Install the FleetDeck binary the harness unit runs (needs root).")
    parser.add_argument("--from", dest="source", required=True, metavar="PATH", help="the built agent-fabric-fleetdeck binary")
    args = parser.parse_args(argv)
    prefix = env.get("FLEETDECK_PREFIX") or "/usr/local"
    try:
        digest = install(prefix, args.source)
    except Refused as e:
        print(f"install_fleetdeck: {e}; nothing installed", file=sys.stderr)
        return 1
    except OSError as e:
        print(f"install_fleetdeck: {e.strerror or e}{': ' + e.filename if e.filename else ''}; nothing after it ran", file=sys.stderr)
        return 1
    print(f"agent-fabric-fleetdeck installed to {prefix}/{BIN} (sha256 {digest}; manifest: {prefix}/{MANIFEST})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
