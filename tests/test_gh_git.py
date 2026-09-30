#!/usr/bin/env python3
"""Tests for tools/fabric/gh.py and tools/fabric/git.py (ADR-040 §5 rule 6):
a body travels on stdin and never in argv; pages come back as one list;
an error names the call, GitHub's reason and status, and whether a retry
could help; git's question-commands answer yes or no and fail otherwise.
gh is a fake on PATH that records what it was given."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
import gh  # noqa: E402
import git  # noqa: E402

FAKE = r'''#!/usr/bin/env python3
import json, os, sys, time
log = os.environ["FAKE_GH_LOG"]
stdin = "" if sys.stdin.isatty() else sys.stdin.read()
open(log, "a").write(json.dumps({"argv": sys.argv[1:], "stdin": stdin}) + "\n")
mode = os.environ.get("FAKE_GH_MODE", "ok")
if mode == "404":
    sys.stderr.write("gh: Not Found (HTTP 404)\n"); sys.exit(1)
if mode == "502":
    sys.stderr.write("gh: Bad Gateway (HTTP 502)\n"); sys.exit(1)
if mode == "hang":
    time.sleep(5)
if mode == "gqlerr":
    print(json.dumps({"errors": [{"message": "Field 'x' doesn't exist"}]})); sys.exit(0)
if "--slurp" in sys.argv:
    print(json.dumps([[{"n": 1}, {"n": 2}], [{"n": 3}]])); sys.exit(0)
if sys.argv[1:3] == ["api", "graphql"]:
    print(json.dumps({"data": {"echo": json.loads(stdin)["variables"]}})); sys.exit(0)
print(json.dumps({"ok": True}))
'''


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: object = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {detail}"))
        fails += not good

    with tempfile.TemporaryDirectory() as tmp:
        bindir = os.path.join(tmp, "bin")
        os.makedirs(bindir)
        open(os.path.join(bindir, "gh"), "w").write(FAKE)
        os.chmod(os.path.join(bindir, "gh"), 0o755)
        log = os.path.join(tmp, "gh.log")
        saved = {k: os.environ.get(k) for k in ("PATH", "FAKE_GH_LOG", "FAKE_GH_MODE")}
        os.environ.update(PATH=bindir + os.pathsep + os.environ["PATH"], FAKE_GH_LOG=log)
        calls = lambda: [json.loads(l) for l in open(log)]
        try:
            secret_body = {"body": "a reply with 'quotes', $dollars and `ticks`", "event": "COMMENT"}
            gh.api("repos/o/r/pulls/7/reviews", method="POST", body=secret_body)
            c = calls()[-1]
            check("a body goes on stdin as JSON", json.loads(c["stdin"]) == secret_body, c)
            check("…and never into argv", not any("quotes" in a for a in c["argv"]) and "--input" in c["argv"], c["argv"])
            items = gh.api("repos/o/r/pulls/7/commits", paginate=True)
            check("paginate returns every page's items as one list", items == [{"n": 1}, {"n": 2}, {"n": 3}], items)
            got = gh.graphql("query($n:Int!){x}", n=7)
            check("graphql sends the query and variables on stdin", got == {"echo": {"n": 7}}
                  and "$n" not in " ".join(calls()[-1]["argv"]), got)
            os.environ["FAKE_GH_MODE"] = "gqlerr"
            try:
                gh.graphql("{x}")
                check("a GraphQL error answered with 200 is raised", False)
            except gh.GhError as e:
                check("a GraphQL error answered with 200 is raised", "doesn't exist" in str(e), e)
            os.environ["FAKE_GH_MODE"] = "404"
            try:
                gh.api("repos/o/r/pulls/999")
                check("a 404 raises", False)
            except gh.GhError as e:
                check("a 404 names the call and the reason, status 404, not transient",
                      e.status == 404 and not e.transient and "gh api GET repos/o/r/pulls/999" in str(e)
                      and "Not Found" in e.reason, (e, e.status, e.transient))
            os.environ["FAKE_GH_MODE"] = "502"
            try:
                gh.pr_view(7, ["number"], repo="o/r")
                check("a 502 raises", False)
            except gh.GhError as e:
                check("a 502 is transient: a retry could help", e.status == 502 and e.transient, (e.status, e.transient))
            os.environ["FAKE_GH_MODE"] = "hang"
            try:
                gh.api("repos/o/r", timeout=1)
                check("a call past its bound raises", False)
            except gh.GhError as e:
                check("a call past its bound is transient and says its bound", e.transient and "within 1 s" in str(e), e)
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

        repo = os.path.join(tmp, "repo")
        subprocess.run(["git", "init", "-q", "-b", "main", repo], check=True)
        open(os.path.join(repo, "f"), "w").write("x\n")
        git.run(repo, "add", "f")
        git.run(repo, "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", "commit", "-qm", "one")
        check("out returns stdout, stripped", len(git.out(repo, "rev-parse", "HEAD")) == 40)
        check("branch names the checked-out branch", git.branch(repo) == "main")
        check("ok: a clean index answers yes", git.ok(repo, "diff", "--cached", "--quiet") is True)
        open(os.path.join(repo, "f"), "w").write("y\n")
        git.run(repo, "add", "f")
        check("ok: a staged change answers no", git.ok(repo, "diff", "--cached", "--quiet") is False)
        try:
            git.ok(repo, "diff", "--no-such-option")
            check("ok: a status other than 0 or 1 raises", False)
        except git.GitError as e:
            check("ok: a status other than 0 or 1 raises", e.code not in (0, 1), e.code)
        try:
            git.run(repo, "checkout", "-q", "no-such-branch")
            check("a failed call raises", False)
        except git.GitError as e:
            check("a failed call names the operation and git's reason, not its advice",
                  str(e).startswith("git checkout:") and not e.reason.startswith("hint:"), e)
        check("toplevel of a path outside any repository is None", git.toplevel(tmp) is None)
    print(f"\n{'FAILED' if fails else 'all passed'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
