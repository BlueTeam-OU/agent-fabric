#!/usr/bin/env python3
"""runtime/claude-code/retire-doppler.py [--dry-run] — what Doppler left in
this account, removed: the source file the migration wrote, which nothing
reads (ADR-038). The Doppler CLI and its config (~/.doppler) stay: a
project may use them for its own secrets (projects/registry.json tools),
so neither is removed here, and the lint refuses a RETIRED entry naming a
declared tool. bootstrap.sh runs it on every upgrade.

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

# Only what the fabric itself wrote. The Doppler CLI and its config are a
# project's tool too: a managed project may load its application secrets
# with `doppler run`, and removing them took that away from every account
# (the owner, 2026-10-07; ADR-038 §6). ADR-038 retired Doppler as the
# fabric's store, never a project's use of it.
RETIRED = (".config/agent-fabric/secrets-source",)


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
