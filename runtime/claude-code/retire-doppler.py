#!/usr/bin/env python3
"""runtime/claude-code/retire-doppler.py [--dry-run] — what Doppler left in
this account, removed: its CLI config (~/.doppler, with the token when it
is kept there), a copy of the CLI in ~/.local/bin, and the source file
the migration wrote, which nothing reads (ADR-038). bootstrap.sh runs it, so the upgrade that brings
the fabric without Doppler also takes it off each account.

The binary under /usr/local is the host's, removed there by its operator.
A token kept in the desktop keyring stays there: ~/.doppler holds only a
pointer to it. Removing a file here revokes no token at Doppler; closing
the project does, for all of them. No `doppler logout` here: that is a
write to Doppler, and the project is the owner's to close.

Prints one line naming what it removed, or nothing; exit 1 when a path
could not be removed.
"""
from __future__ import annotations

import os
import shutil
import sys

RETIRED = (".doppler", ".local/bin/doppler", ".config/agent-fabric/secrets-source")


def retire(home: str, dry_run: bool = False) -> tuple[list[str], list[str]]:
    removed, failed = [], []
    for rel in RETIRED:
        path = os.path.join(home, rel)
        if not os.path.lexists(path):
            continue
        if dry_run:
            removed.append(rel)
            continue
        try:
            if os.path.isdir(path) and not os.path.islink(path):
                shutil.rmtree(path)
            else:
                os.remove(path)
            removed.append(rel)
        except OSError as e:
            failed.append(f"{rel} ({e.strerror})")
    return removed, failed


def main(argv: list[str]) -> int:
    dry = "--dry-run" in argv
    removed, failed = retire(os.environ.get("HOME") or os.path.expanduser("~"), dry)
    if removed:
        print(f"  -  Doppler retired: {'would remove' if dry else 'removed'} " + ", ".join(f"~/{r}" for r in removed))
    for f in failed:
        print(f"  !  Doppler retired: ~/{f} could not be removed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
