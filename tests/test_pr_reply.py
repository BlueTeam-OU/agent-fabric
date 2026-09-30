#!/usr/bin/env python3
"""Tests for tools/fabric/github/pr_reply.py's internals; the behaviour is
runtime/github/test_pr-reply.sh's, run unchanged against the shim
(ADR-040 §5 rule 5)."""
from __future__ import annotations

import os
import subprocess
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
from github import pr_reply  # noqa: E402


def main() -> int:
    fails = 0

    def check(label: str, good: bool) -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}")
        fails += not good

    names = pr_reply.branch_names_a_session
    check("<host>/<login>/<type>/<what> names a session", names("develop-qzapp/user/feat/x"))
    check("any <type>, capitals and parentheses included", names("h/l/Fix/x") and names("h/l/chore(gh)/x"))
    check("three segments name none", not names("h/l/x"))
    check("an automation vendor names none", not names("dependabot/pub/apps/x"))
    check("an empty segment names none", not names("/l/feat/x"))
    check("dependabot's branches are the devex-tooling role's", pr_reply.BOT_OWNER_ROLE["dependabot"] == "devex-tooling")
    print("--help and a usage error never wait on an open stdin (review of #71)")
    shim = os.path.join(HERE, "runtime", "github", "pr-reply.sh")
    for args, want in ((["--help"], 0), (["--bogus"], 2)):
        held = subprocess.Popen(["bash", shim, *args], stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL)
        try:
            rc = held.wait(timeout=20)
        except subprocess.TimeoutExpired:
            held.kill()
            held.wait()
            rc = None
        finally:
            held.stdin.close()
        check(f"{' '.join(args)} exits {want} with stdin still open", rc == want)
    print(f"\n{'FAILED' if fails else 'all passed'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
