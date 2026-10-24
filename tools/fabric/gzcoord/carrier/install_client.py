#!/usr/bin/env python3
"""tools/fabric/gzcoord/carrier/install_client.py — the client unit's
program of agent-fabric ADR-064 §5 rule 5, installed in the account that runs
it.

    install_client.py      run AS the account, from its own clone

InterWeave's client unit template runs `%h/.local/libexec/interweave/client
--profile %i`. This copies runtime/interweave/client there.

CONTRACT
  installs  ~/.local/libexec/interweave/client (0755), the directories above
            it 0755 where made; replaced whole (a temporary beside it, then
            renamed), so a unit starting mid-install runs the old or the new
            file, never half of one
  idempotent  a copy that already has the source's bytes and mode is left
            alone and said so; a different one (an old version, an edited
            copy) is replaced
  env     HOME only
  stderr  one line `install_client: <what>`
  exit    0 installed or already there; 1 the source is unreadable or the
          copy could not be made, said
"""
from __future__ import annotations

import os
import shutil
import stat
import sys
import tempfile

HERE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(HERE))))
SOURCE = os.path.join(ROOT, "runtime", "interweave", "client")
RELATIVE = os.path.join(".local", "libexec", "interweave", "client")
MODE = 0o755


def same(src: str, dst: str) -> bool:
    try:
        st = os.lstat(dst)
        if not stat.S_ISREG(st.st_mode) or stat.S_IMODE(st.st_mode) != MODE:
            return False
        with open(src, "rb") as a, open(dst, "rb") as b:
            return a.read() == b.read()
    except OSError:
        return False


def install(home: str, source: str = SOURCE) -> bool:
    """True when it wrote the file, False when it was already as it should be."""
    dst = os.path.join(home, RELATIVE)
    if same(source, dst):
        return False
    directory = os.path.dirname(dst)
    os.makedirs(directory, mode=0o755, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".client.", dir=directory)
    try:
        with os.fdopen(fd, "wb") as out, open(source, "rb") as fh:
            shutil.copyfileobj(fh, out)
        os.chmod(tmp, MODE)
        # A symlink or directory at the target is replaced by the rename, not followed.
        os.replace(tmp, dst)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return True


def main(argv: list[str]) -> int:
    if argv:
        print("install_client: usage: install_client.py (no arguments)", file=sys.stderr)
        return 2
    home = os.environ.get("HOME", "")
    if not os.path.isabs(home):
        print("install_client: HOME is not set to an absolute path", file=sys.stderr)
        return 1
    try:
        wrote = install(home)
    except OSError as e:
        print(f"install_client: {e}", file=sys.stderr)
        return 1
    print(f"install_client: {'installed' if wrote else 'already'} ~/{RELATIVE}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
