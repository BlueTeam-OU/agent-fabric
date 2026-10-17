#!/usr/bin/env python3
"""tools/fabric/secret_child.py — what a parent does to its children's stores, from its mirrors
(fabric-secrets child …, ADR-060 §5 rule 3). Runs AS THE PARENT.

  fabric-secrets child roles-put --agent ID|LOGIN --role R --from DIR --approval REF
                                 [--reviewed-by 'login pass-N sha256']… [--authored-by LOGIN] [--retire]

DIR becomes settings/roles/R/ in the child's store, whole, in one commit signed by the parent and pushed;
secretstore/roles.py holds the contract. stdout: one line; stderr: the refusal, one line; exit 0 done
(or nothing to change), 1 refused or failed, 2 usage."""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from secretstore.core import StoreError  # noqa: E402
from secretstore.roles import roles_put  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="fabric-secrets child", description="a parent's work on its children's stores (ADR-060)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    rp = sub.add_parser("roles-put", help="install, replace or retire a holder's addenda of one role in its child's store")
    rp.add_argument("--agent", required=True, metavar="ID|LOGIN")
    rp.add_argument("--role", required=True)
    rp.add_argument("--from", dest="src", required=True, metavar="DIR")
    rp.add_argument("--approval", required=True, metavar="REF", help="the owner's decision or its MESSAGE-ID")
    rp.add_argument("--reviewed-by", action="append", default=[], metavar="'LOGIN pass-N SHA256'",
                    help="one per review pass, with the sha256 of the text it read")
    rp.add_argument("--authored-by", metavar="LOGIN", help="default: the child itself")
    rp.add_argument("--retire", action="store_true", help="remove the role's addenda: DIR is empty")
    args = ap.parse_args(argv)
    try:
        r = roles_put(args.agent, args.role, args.src, args.approval, reviewed_by=args.reviewed_by,
                      authored_by=args.authored_by, retire=args.retire)
    except StoreError as e:
        print(f"fabric-secrets child: {e}", file=sys.stderr)
        return 1
    made = f"committed as {r['commit']}, pushed" if r["changed"] else "unchanged"
    print(f"{r['child']} {r['role']}: {len(r['files'])} file(s) {made}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
