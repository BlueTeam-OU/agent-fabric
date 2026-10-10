#!/usr/bin/env python3
"""Tests for tools/fabric/github/pr_reply.py's internals; the behaviour is
tests/test_pr_reply_cli.py's, run against the shim
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
    print("a reply GitHub gave no answer to is never called rejected (review of #71)")
    import gh
    real = (gh.graphql, gh.run, pr_reply.local.toplevel, pr_reply.local.probe, pr_reply.local.remote_url)
    # The repository is read through gh.this_repo, never gh repo view.
    real_this_repo, gh.this_repo = gh.this_repo, (lambda cwd=None: "o/r")
    node = {"node": {"isResolved": False, "path": "a", "line": 1, "pullRequest": {
        "number": 7, "headRefName": "h/me/feat/x", "state": "OPEN", "repository": {"nameWithOwner": "o/r"}}}}

    def graphql(query, **kw):
        if "addPullRequestReviewThreadReply" in query:
            raise gh.GhError("gh api graphql", "no answer within 60 s", transient=True)
        return node
    gh.graphql, gh.run = graphql, (lambda args, **kw: "o/r\n")
    pr_reply.local.toplevel = lambda: "/x/wc"
    pr_reply.local.remote_url = lambda root: ""
    pr_reply.local.probe = lambda cmd, **kw: (0, "h\n" if cmd[0] == "hostname" else "me\n")
    try:
        pr_reply.run(["PRRT_abc"], "body")
        check("refused", False)
    except pr_reply.Refused as e:
        check("says it may have posted, and to look first", "may have posted" in str(e) and "rejected" not in str(e))
    finally:
        gh.graphql, gh.run, pr_reply.local.toplevel, pr_reply.local.probe, pr_reply.local.remote_url = real

    print("an answer to the reply that cannot be read is an unknown outcome too (re-review of #71)")
    real_run = gh.run
    gh.graphql = real[0]

    def answering(args, **kw):
        if args[:2] == ["api", "graphql"]:
            q = kw.get("input") or ""
            if "addPullRequestReviewThreadReply" in q:
                return "<html>truncated"
            import json as _json
            return _json.dumps({"data": node})
        return "o/r\n"
    gh.run = answering
    pr_reply.local.toplevel = lambda: "/x/wc"
    pr_reply.local.remote_url = lambda root: ""
    pr_reply.local.probe = lambda cmd, **kw: (0, "h\n" if cmd[0] == "hostname" else "me\n")
    try:
        pr_reply.run(["PRRT_abc"], "body")
        check("refused", False)
    except pr_reply.Refused as e:
        check("says it may have posted", "may have posted" in str(e))
    finally:
        gh.graphql, gh.run, pr_reply.local.toplevel, pr_reply.local.probe, pr_reply.local.remote_url = \
            real[0], real_run, real[2], real[3], real[4]
        gh.this_repo = real_this_repo

    print("--help and a usage error never wait on an open stdin (review of #71)")
    shim = [os.path.join(HERE, "bin", "fabric-pr"), "reply"]
    for args, want in ((["--help"], 0), (["--bogus"], 2)):
        held = subprocess.Popen([*shim, *args], stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
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
