#!/usr/bin/env python3
"""Tests for tools/fabric/github/pr_reply.py, in-process: the ownership
verdict (whose branch, which role, which repository), what is posted and
whether the thread resolves, and the reason of every refusal. What exists
only when the process runs (exit status, streams, stdin, PATH, GH_REPO, cwd,
the real post call shape) is tests/test_pr_reply_cli.py's, run through
fabric-pr, one smoke case per outcome (ADR-040 §5 rule 5)."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile

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

    print("whose thread it is, what is posted and whether it resolves — decided in-process")
    import contextlib
    import io
    import shutil

    me = "h/me"
    other = "h/other"
    body_want = 'Fixed: the `need_operand` guard and $LIMIT — see $(date) and "quotes" \\back.\n\n'

    def drive(branch, *flags, argv=None, body="Fixed.", resolved=False, repo="o/r", here="o/r", wc="/x/wc",
              remote="", bound="", launched="", reply_url="https://github.com/o/r/pull/1#discussion_r1",
              fail=(), missing=()):
        """pr_reply.run with gh, the clone and the role faked: (exit, output, verbs, reply body) as the CLI
        suite's mock would record them. A Refused is the exit 2 and the `pr-reply: ` line main() makes of it.
        remote=None leaves local.remote_url real: it reads origin from the git repository at wc."""
        calls = []

        def graphql(query, **kw):
            if "mutation" not in query:
                calls.append(("READ",))
                if "read" in fail:
                    raise gh.GhError("gh api graphql", "not authenticated")
                return {"node": {"isResolved": resolved, "path": "lib/x.dart", "line": 12, "pullRequest": {
                    "number": 77, "headRefName": branch, "state": "MERGED", "repository": {"nameWithOwner": repo}}}}
            if "addPullRequestReviewThreadReply" in query:
                calls.append(("REPLY", kw["body"]))
                if "reply" in fail:
                    raise gh.GhError("gh api graphql", "rejected")
                return {"addPullRequestReviewThreadReply": {"comment": {"url": reply_url}}}
            calls.append(("RESOLVE",))
            if "resolve" in fail:
                raise gh.GhError("gh api graphql", "rejected")
            return {"resolveReviewThread": {"thread": {"isResolved": True}}}

        def this_repo(cwd=None):
            if here is None:
                raise gh.GhError("this repository", "origin is not a github.com repository here")
            return here

        def probe(cmd, **kw):
            return 0, ("h" if cmd[0] == "hostname" else (bound if cmd[-1] == "--role" else "me")) + "\n"

        saved = (gh.graphql, gh.this_repo, pr_reply.local.toplevel, pr_reply.local.probe, pr_reply.local.remote_url,
                 shutil.which)
        old_role = os.environ.get("AGENT_FABRIC_LAUNCH_ROLE")
        gh.graphql, gh.this_repo = graphql, this_repo
        pr_reply.local.toplevel, pr_reply.local.probe = (lambda: wc), probe
        if remote is not None:
            pr_reply.local.remote_url = lambda root: remote
        shutil.which = lambda b: None if b in missing else "/usr/bin/" + b
        os.environ["AGENT_FABRIC_LAUNCH_ROLE"] = launched
        out = io.StringIO()
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
                try:
                    rc = pr_reply.run(argv if argv is not None else ["PRRT_abc", *flags], body)
                except pr_reply.Refused as e:
                    rc = 2
                    print(f"pr-reply: {e}")
        finally:
            (gh.graphql, gh.this_repo, pr_reply.local.toplevel, pr_reply.local.probe, pr_reply.local.remote_url,
             shutil.which) = saved
            if old_role is None:
                os.environ.pop("AGENT_FABRIC_LAUNCH_ROLE", None)
            else:
                os.environ["AGENT_FABRIC_LAUNCH_ROLE"] = old_role
        return rc, out.getvalue(), [c[0] for c in calls], next((c[1] for c in calls if c[0] == "REPLY"), None)

    rc, out, verbs, sent = drive(f"{me}/feat/thing")
    check("an own branch: read, then reply, then resolve — in that order",
          rc == 0 and verbs == ["READ", "REPLY", "RESOLVE"] and "resolved: #77" in out and "discussion_r1" in out)
    check("the body reaches the reply mutation byte for byte, trailing blank line included",
          drive(f"{me}/feat/thing", body=body_want)[3] == body_want)
    rc, out, verbs, sent = drive(f"{me}/feat/thing", "--no-resolve")
    check("--no-resolve replies, says it left the thread open and sends no resolve",
          rc == 0 and "left open" in out and "resolved: #77" not in out and verbs == ["READ", "REPLY"])

    rc, out, verbs, sent = drive(f"{other}/fix/theirs")
    check("another session's PR is refused, names the session, says why and posts nothing",
          rc == 2 and other in out and "cannot be unsent" in out and "REPLY" not in verbs)
    odd = ("spike-3", "hotfix", "stage-4", "Fix", "chore(gh)", "WIP", "2fix", "-lead", "FEAT")
    refused = [drive(f"{other}/{t}/x") for t in odd]
    check("any <type> on another session's branch is still refused",
          all(r[0] == 2 and "REPLY" not in r[2] for r in refused))
    unowned = ("renovate/pub/apps/driver_flutter/flutter-minor-patch-7a91", "agent/global-event-identity",
               "add-claude-github-actions-1785994932117", "feat/brand-logos", "agent/common-api-idempotency")
    answered = [drive(b) for b in unowned]
    check("a branch naming no session is answered, not refused as a rival's",
          all(r[0] == 0 and "REPLY" in r[2] for r in answered))
    rc, out, verbs, sent = drive("agent/global-event-identity")
    check("an unowned PR warns: names no session, another SURFACE's, left OPEN, no invented rival",
          rc == 0 and "names no session" in out and "another SURFACE's" in out and "left OPEN" in out
          and "mid-flight" not in out)
    check("an unowned branch is answered but not resolved by default, naming --resolve",
          "REPLY" in verbs and "RESOLVE" not in verbs and "--resolve" in out)
    check("--resolve is the opt-in on an unowned branch", "RESOLVE" in drive("agent/global-event-identity", "--resolve")[2])
    rc, out, verbs, sent = drive("renovate/pub/apps/x/flutter-minor-patch-7a91")
    check("a bot branch is never a session called after the bot", rc == 0 and "belongs to 'renovate" not in out)

    legacy = "/x/legacy-testclone"
    rc, out, verbs, sent = drive("h/legacy-testclone/fix/mine", wc=legacy)
    check("an older branch named for this working copy is this agent's own",
          rc == 0 and "named for this working copy" in out and "REPLY" in verbs)
    rc, out, verbs, sent = drive("h/legacy-testclone/fix/mine", wc=legacy, remote="git@example.com:org/legacy-testclone.git")
    check("a clone named after its repository names no session", rc == 2 and "REPLY" not in verbs)
    # The decision above is fed its remote; this one reads it from a real clone's origin, the only
    # thing that tells a clone named after its repository from an older working copy's.
    with tempfile.TemporaryDirectory() as tmp:
        clone = os.path.join(tmp, "legacy-testclone")
        subprocess.run(["git", "init", "-q", clone], check=True)
        subprocess.run(["git", "-C", clone, "remote", "add", "origin", "git@example.com:org/legacy-testclone.git"],
                       check=True)
        rc, out, verbs, sent = drive("h/legacy-testclone/fix/mine", wc=clone, remote=None)
    check("…and the remote is read from the clone's own origin", rc == 2 and "REPLY" not in verbs)
    rc, out, verbs, sent = drive("h/legacy-old/fix/theirs", wc=legacy)
    check("an older branch named for another working copy is another session's", rc == 2 and "REPLY" not in verbs)

    dep = "dependabot/nuget/apps/backend_dotnet/dotnet-minor-patch-04e2"
    rc, out, verbs, sent = drive(dep, bound="devex-tooling", launched="devex-tooling")
    check("devex-tooling, bound and launched: answers, says the role owns it, resolves as on its own branch",
          rc == 0 and "owned by the devex-tooling role" in out and verbs == ["READ", "REPLY", "RESOLVE"])
    rc, out, verbs, sent = drive(dep, bound="backend-dev", launched="backend-dev")
    check("backend-dev: refused, names the owning role, posts nothing",
          rc == 2 and "devex-tooling role owns" in out and "REPLY" not in verbs)
    check("bound devex-tooling, launched backend-dev: refused (review of #68)",
          drive(dep, bound="devex-tooling", launched="backend-dev")[0] == 2)
    check("bound devex-tooling, no launch stamp: refused (review of #70)",
          drive(dep, bound="devex-tooling", launched="")[0] == 2)
    rc, out, verbs, sent = drive(dep)
    check("no role bound: refused, nothing posted", rc == 2 and "REPLY" not in verbs)

    rc, out, verbs, sent = drive(f"{me}/feat/thing", reply_url="")
    check("a reply with no URL is treated as not posted", rc == 2 and "did not post" in out and "RESOLVE" not in verbs)
    rc, out, verbs, sent = drive(f"{me}/feat/thing", fail=("resolve",))
    check("a failed resolve is reported after the reply: replied, and the thread still open",
          rc == 2 and "replied:" in out and "still open" in out)
    rc, out, verbs, sent = drive(f"{me}/feat/thing", resolved=True)
    check("an already-resolved thread is replied to and not re-resolved",
          rc == 0 and "already resolved" in out and verbs == ["READ", "REPLY"])
    rc, out, verbs, sent = drive(f"{me}/feat/thing", fail=("read",))
    check("a failed thread read stops before posting", rc == 2 and verbs == ["READ"])
    rc, out, verbs, sent = drive(f"{me}/feat/thing", repo="someone-else/other-repo")
    check("a thread in another repository is refused, names both, replies and resolves nothing",
          rc == 2 and "someone-else/other-repo" in out and "o/r" in out and verbs == ["READ"])
    rc, out, verbs, sent = drive(f"{me}/feat/thing", here=None)
    check("an unknowable current repository is refused, not assumed",
          rc == 2 and "cannot determine the current repository" in out and verbs == ["READ"])
    rc, out, verbs, sent = drive(f"{me}/feat/thing", "--dry-run", body="Would say this.")
    check("--dry-run shows the target and the body and sends no mutation",
          rc == 0 and "#77" in out and "Would say this." in out and verbs == ["READ"])
    rc, out, verbs, sent = drive(f"{me}/feat/thing", wc=None)
    check("outside a worktree it refuses: the identity is unknown, nothing posted",
          rc == 2 and "identity is unknown" in out and "REPLY" not in verbs)
    check("a missing git is named, not blamed on the cwd",
          "git is required" in drive(f"{me}/feat/thing", missing=("git",))[1])
    check("a missing hostname is named", "hostname is required" in drive(f"{me}/feat/thing", missing=("hostname",))[1])
    for label, argv, body, want in (
            ("a comment id is refused and explained", ["PRRC_abc"], "body", "PRRC_ is a comment"),
            ("a malformed id is refused", ["not-an-id"], "body", "not a review-thread id"),
            ("an empty body is refused", ["PRRT_abc"], "", "empty"),
            ("a whitespace-only body is refused", ["PRRT_abc"], "   ", "empty"),
            ("a missing thread id is refused", [], "body", "thread id is required"),
            ("two thread ids are refused", ["PRRT_abc", "PRRT_second"], "body", "one thread id at a time"),
            ("an unknown option is refused", ["PRRT_abc", "--nope"], "body", "unknown option")):
        rc, out, verbs, sent = drive(f"{me}/feat/thing", argv=argv, body=body)
        check(label, rc == 2 and want in out and not verbs)

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
