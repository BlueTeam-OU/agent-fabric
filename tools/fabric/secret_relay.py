#!/usr/bin/env python3
"""tools/fabric/secret_relay.py — the relay's database copied to Proton Drive
and read back (ADR-034 §7 step 1), behind `fabric-secrets relay …`.

    fabric-secrets relay backup [--db FILE]   online backup of the live database, gzipped, encrypted to this
                                              login's key (and the owner's recovery key), uploaded as a new
                                              revision of one fixed name; secretstore/relaycopy.py has the contract.
    fabric-secrets relay backup --verify      the latest revision downloaded, decrypted, checked against its
                                              manifest and `PRAGMA integrity_check`; nothing kept.
    fabric-secrets relay restore DIR          the same into DIR, which is empty or absent: DIR/claude-bridge.db,
                                              or nothing. Never over the live database.

Runs AS THE OPERATOR LOGIN (the one that hosts the relay and holds the Proton session), by hand or from a
user timer. Environment read: AGENT_FABRIC_RELAY_DB (the database; else
<projects>/.gzcoord/claude-bridge.db, <projects> being the parent of this checkout), TMPDIR (the scratch
directory), AGENT_FABRIC_STATE_DIR / XDG_STATE_HOME (where the manifest line is kept), PROTON_DRIVE_BIN,
and what secretstore reads. stdout: one line per result; stderr: errors. Exit 0 done, 1 refused or failed
(one line, no traceback), 2 usage. SIGTERM ends the run through its cleanup, so a timer's stop leaves no
scratch behind.
"""
from __future__ import annotations

import argparse
import os
import signal
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "runtime"))
sys.path.insert(0, HERE)
import identity  # noqa: E402
from secretstore.core import StoreError  # noqa: E402
from secretstore.relaycopy import relay_backup, relay_restore, relay_verify  # noqa: E402


def default_db() -> str:
    env = os.environ.get("AGENT_FABRIC_RELAY_DB")
    if env:
        return env
    checkout = os.path.dirname(os.path.dirname(HERE))
    return os.path.join(os.path.dirname(checkout), ".gzcoord", "claude-bridge.db")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="fabric-secrets relay", description="the relay's database, copied to Proton Drive")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("backup")
    b.add_argument("--db", metavar="FILE")
    b.add_argument("--verify", action="store_true", help="read the latest revision back instead of writing one")
    r = sub.add_parser("restore")
    r.add_argument("dest", metavar="DIR")
    args = ap.parse_args(argv)
    # The default SIGTERM action skips `finally`: the snapshot is the relay's
    # whole history in plain text, and must not outlive a stopped timer.
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
    try:
        if args.cmd == "restore":
            res = relay_restore(args.dest)
            print(f"relay restore: {res['size']} bytes of {res['at']} restored, integrity ok")
        elif args.verify:
            res = relay_verify()
            print(f"relay verify: the revision of {res['at']} decrypts, matches its manifest and passes integrity_check")
        else:
            res = relay_backup(args.db or default_db(), identity.agent_state_dir())
            print(f"relay backup: {res['size']} bytes uploaded as {res['uploaded']}, sha256 {res['sha256']}")
    except (StoreError, OSError) as e:
        print(f"fabric-secrets relay: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
