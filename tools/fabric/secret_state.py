#!/usr/bin/env python3
"""tools/fabric/secret_state.py — this login's working state backed up
(the owner's j179), behind `fabric-secrets state …`.

    fabric-secrets state backup            the file set of secretstore/statecopy.py, as one encrypted tar
                                           committed to this login's own store and pushed; the parent's
                                           `fabric-secrets store backup` carries it to Proton Drive.
                                           Unchanged since the last: no commit.
    fabric-secrets state restore DIR [--from FILE]
                                           the copy decrypted into DIR, which is empty or absent; never
                                           over live state. FILE defaults to this store's own copy.

Runs AS THE LOGIN, by hand, or from the daily user timer
(runtime/control/agent-fabric-state-backup.timer) once bootstrap installs it. Environment read:
AGENT_FABRIC_STATE_DIR / XDG_STATE_HOME (runtime/identity.py: the state
dir), HOME (the harness's ~/.claude), AGENT_FABRIC_SECRET_STORE, and
what secretstore reads. stdout: one line per result; stderr: errors and the
entries skipped. Exit 0 done, 1 refused (one line, no traceback), 2 usage.
"""
from __future__ import annotations

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "runtime"))
sys.path.insert(0, HERE)
import identity  # noqa: E402
from secretstore.core import StoreError  # noqa: E402
from secretstore.statecopy import state_copy, state_restore  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="fabric-secrets state", description="this login's working state, backed up")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("backup")
    r = sub.add_parser("restore")
    r.add_argument("dest", metavar="DIR")
    r.add_argument("--from", dest="source", metavar="FILE")
    args = ap.parse_args(argv)
    try:
        if args.cmd == "backup":
            res = state_copy(identity.agent_state_dir(), os.path.join(os.path.expanduser("~"), ".claude"))
            for path in res["skipped"]:
                print(f"fabric-secrets state: skipped {path} (not a regular file)", file=sys.stderr)
            # No path and no count: both derive from the secrets store's folder
            # and the files read, and CodeQL's clear-text-logging rule takes
            # anything derived from them for a secret. The copy is state/<agent id>.tar.gpg.
            print("state backup: " + ("written" if res["changed"] else "unchanged"))
        else:
            res = state_restore(args.dest, args.source)
            print(f"{res['dest']}: {res['files']} file(s) restored")
    except StoreError as e:
        print(f"fabric-secrets state: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
