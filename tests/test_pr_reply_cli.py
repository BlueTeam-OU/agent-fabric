#!/usr/bin/env python3
"""runtime/github/pr-reply.sh, driven through the real script with a
mocked `gh`. Ported from runtime/github/test_pr-reply.sh (ADR-040 Wave 6),
case for case.

Three things the script promises, each unrecoverable if wrong — a posted
reply cannot be unsent:
  1. the body reaches GitHub byte-for-byte, with no shell expansion (the
     defect the script exists to remove: a reply lost the name of the
     guard it described because a backtick was command-substituted on its
     way through a double-quoted argument);
  2. another session's PR is refused;
  3. a thread is never resolved unless the reply actually landed.
The mock records the exact request it was handed, so (1) is about what
would have been transmitted rather than what the script believed it sent.
Plain script: prints ok/FAIL, exit 1 on any failure."""
from __future__ import annotations

import json
import os
import pwd
import shutil
import subprocess
import sys
import tempfile
from git_env import git_env, scrub_process_env  # noqa: E402 — tests/, the script's own directory

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UNDER_TEST = os.path.join(ROOT, "runtime", "github", "pr-reply.sh")
THREAD_ID = "PRRT_kwDOtest123"

# The mock gh speaks the transport tools/fabric/gh.py uses: the query and
# its variables as JSON on --input, answered in GraphQL's own shape. Its
# interpreter is an absolute path, so a case that strips PATH still runs it.
GH_MOCK = r'''#!{python}
import json, os, sys
s, a = os.environ["GH_MOCK_STATE"], sys.argv[1:]
def log(line):
    with open(os.path.join(s, "calls"), "a") as fh:
        fh.write(line + "\n")
def answer(path, value):
    doc = {"data": {}}
    node = doc["data"]
    for key in path[:-1]:
        node = node.setdefault(key, {})
    node[path[-1]] = value
    print(json.dumps(doc))
req = {"query": "", "variables": {}}
if "--input" in a:
    src = a[a.index("--input") + 1]
    req = json.load(sys.stdin if src == "-" else open(src))
query, var = req.get("query", ""), req.get("variables") or {}
tid = var.get("id", "")
if "PullRequestReviewThread" in query and "mutation" not in query:
    log("READ " + tid)
    if os.environ.get("GH_MOCK_READ_FAIL"):
        sys.exit(1)
    answer(["node"], json.load(open(os.path.join(s, "thread.json"))))
    sys.exit(0)
if "addPullRequestReviewThreadReply" in query:
    log("REPLY " + tid)
    with open(os.path.join(s, "body.txt"), "w", newline="") as fh:
        fh.write(var.get("body", ""))
    if os.environ.get("GH_MOCK_REPLY_FAIL"):
        sys.exit(1)
    url = "" if os.environ.get("GH_MOCK_REPLY_EMPTY") else "https://github.com/o/r/pull/1#discussion_r1"
    answer(["addPullRequestReviewThreadReply", "comment", "url"], url)
    sys.exit(0)
if "resolveReviewThread" in query:
    log("RESOLVE " + tid)
    if os.environ.get("GH_MOCK_RESOLVE_FAIL"):
        sys.exit(1)
    answer(["resolveReviewThread", "thread", "isResolved"], True)
    sys.exit(0)
print("mock gh: unhandled query", file=sys.stderr)
sys.exit(1)
'''


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: str = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}")
        if not good and detail:
            print("      " + detail.replace("\n", "\n      "))
        fails += not good

    host = subprocess.run(["hostname", "-s"], stdout=subprocess.PIPE, text=True, check=True, timeout=10).stdout.strip()
    login = pwd.getpwuid(os.geteuid()).pw_name
    clone_name = "legacy-testclone"
    me = f"{host}/{clone_name}"
    other = f"{host}/legacy-otherclone"

    with tempfile.TemporaryDirectory() as sandbox:
        clone, state, bin_ = f"{sandbox}/{clone_name}", f"{sandbox}/state", f"{sandbox}/bin"
        for d in (clone, state, bin_):
            os.makedirs(d)
        subprocess.run(["git", "-C", clone, "init", "-q"], check=True, timeout=30, stderr=subprocess.DEVNULL, env=git_env())
        with open(f"{bin_}/gh", "w", encoding="utf-8") as fh:
            fh.write(GH_MOCK.replace("{python}", sys.executable, 1))
        os.chmod(f"{bin_}/gh", 0o755)
        base = {k: v for k, v in os.environ.items()
                if not k.startswith(("GITHUB_", "AGENT_FABRIC_", "CLAUDE_", "ANTHROPIC_")) and k != "GIT_DIR"}
        # The repository the mock serves (gh.this_repo never reads gh's default).
        base["GH_REPO"] = "gzapi-org/gzapp"
        base.update(PATH=f"{bin_}:{base.get('PATH', '')}", GH_MOCK_STATE=state)

        def thread_fixture(branch: str, resolved: bool, repo: str = "gzapi-org/gzapp") -> None:
            with open(f"{state}/thread.json", "w", encoding="utf-8") as fh:
                json.dump({"isResolved": resolved, "path": "lib/x.dart", "line": 12,
                           "pullRequest": {"number": 77, "state": "MERGED", "headRefName": branch,
                                           "repository": {"nameWithOwner": repo}},
                           "comments": {"nodes": [{"author": {"login": "some-reviewer"}}]}}, fh)
            open(f"{state}/calls", "w").close()
            if os.path.exists(f"{state}/body.txt"):
                os.remove(f"{state}/body.txt")

        # THE ROLE IS PART OF EVERY FIXTURE. Bot branches are owned by a
        # role, so whoever runs this suite must not decide a case through
        # their own binding: every run reads its binding from a private
        # state dir — no role unless a case plants one, for this login, in
        # the shape identity.py reads.
        role_dir = f"{sandbox}/state-role"

        def with_role(role: str | None) -> None:
            shutil.rmtree(role_dir, ignore_errors=True)
            os.makedirs(f"{role_dir}/agents/{login}")
            if role:
                with open(f"{role_dir}/agents/{login}/binding.json", "w", encoding="utf-8") as fh:
                    json.dump({"agent": login, "role": role}, fh)
        with_role(None)

        def invoke(body: str | bytes, *args: str, cwd: str = clone, path: str | None = None, **env: str) -> tuple[int, str]:
            e = {**base, "AGENT_FABRIC_STATE_DIR": role_dir, **env}
            if path is not None:
                e = {"PATH": path, "GH_MOCK_STATE": state}
            r = subprocess.run(["bash", UNDER_TEST, *args], cwd=cwd, env=e,
                               input=body.encode() if isinstance(body, str) else body,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
            return r.returncode, r.stdout.decode("utf-8", "replace")

        def calls() -> str:
            try:
                with open(f"{state}/calls", encoding="utf-8") as fh:
                    return fh.read()
            except OSError:
                return ""

        def sent() -> bytes | None:
            try:
                with open(f"{state}/body.txt", "rb") as fh:
                    return fh.read()
            except OSError:
                return None

        print("pr-reply: the happy path")
        thread_fixture(f"{me}/feat/thing", False)
        rc, out = invoke("Fixed in #123.", THREAD_ID)
        check("exits 0", rc == 0, out)
        check("reports the reply URL", "discussion_r1" in out, out)
        check("reports the resolve", "resolved: #77" in out, out)
        # The repository check is in-process now (gh.this_repo: GH_REPO, else
        # origin; never gh repo view), and refuses before any write.
        check("read, then reply, then resolve — in that order",
              calls() == f"READ {THREAD_ID}\nREPLY {THREAD_ID}\nRESOLVE {THREAD_ID}\n", calls())

        print("pr-reply: a trailing blank line survives to GitHub")
        # Reading the body back must not strip the bytes under test: a
        # documented heredoc ends with a blank line, and the script exists
        # to deliver the body byte-for-byte.
        thread_fixture(f"{me}/feat/thing", False)
        rc, out = invoke(b"line one\n\n", THREAD_ID)
        check("exits 0", rc == 0, out)
        check("the trailing blank line reached GitHub intact", sent() == b"line one\n\n", repr(sent()))

        print("pr-reply: the body is transmitted verbatim")
        # The defect this script exists to remove: each of these is
        # something a shell would have eaten from a double-quoted argument.
        body = 'Fixed: the `need_operand` guard and $LIMIT — see $(date) and "quotes" \\back.'
        thread_fixture(f"{me}/feat/thing", False)
        rc, out = invoke(body, THREAD_ID)
        check("exits 0", rc == 0, out)
        check("backticks, $vars, $( ), quotes and backslashes survive intact", sent() == body.encode(),
              f"sent: {sent()!r}\nwant: {body!r}")

        print("pr-reply: --no-resolve replies without claiming the finding is handled")
        thread_fixture(f"{me}/feat/thing", False)
        rc, out = invoke("Real, but the contract has to change first.", THREAD_ID, "--no-resolve")
        check("exits 0", rc == 0, out)
        check("says it left the thread open", "left open" in out, out)
        check("did not resolve", "resolved: #77" not in out, out)
        check("no resolve mutation was sent", "RESOLVE" not in calls(), calls())

        print("pr-reply: another session's PR is refused")
        thread_fixture(f"{other}/fix/theirs", False)
        rc, out = invoke("I would like to answer this.", THREAD_ID)
        check("exits 2", rc == 2, out)
        check("names the owning session", other in out, out)
        check("explains why not", "cannot be unsent" in out, out)
        check("nothing was posted", "REPLY" not in calls(), calls())

        print("pr-reply: a branch naming no session is answered, not refused as a rival's")
        # The guard once took the first two segments of ANY branch: four
        # unowned PRs held seven unresolved findings for a month, each
        # refused as a session's that does not exist.
        for branch in ("renovate/pub/apps/driver_flutter/flutter-minor-patch-7a91", "agent/global-event-identity",
                       "add-claude-github-actions-1785994932117", "feat/brand-logos"):
            thread_fixture(branch, False)
            rc, _ = invoke("Obsolete — the file was deleted before this landed.", THREAD_ID)
            check(f"answers '{branch}'", rc == 0 and "REPLY" in calls(), f"rc={rc} {calls()}")

        print("pr-reply: an older branch named for this working copy is this agent's own")
        # Before the login model, prefixes carried the working-copy name.
        thread_fixture(f"{host}/{clone_name}/fix/mine-under-the-old-name", False)
        rc, out = invoke("Verified against main; obsolete.", THREAD_ID)
        check("exits 0", rc == 0, out)
        check("says it is this agent's under the older convention", "named for this working copy" in out, out)
        check("replied on the legacy-named branch", "REPLY" in calls(), calls())

        print("pr-reply: a clone named after its repository names no session")
        # ~/projects/<repo> is every login's default clone: its name taken
        # for a session made an older branch under it "mine" in every one.
        subprocess.run(["git", "-C", clone, "remote", "add", "origin", f"git@example.com:org/{clone_name}.git"],
                       check=True, timeout=30, env=git_env())
        thread_fixture(f"{host}/{clone_name}/fix/mine-under-the-old-name", False)
        rc, out = invoke("Verified against main; obsolete.", THREAD_ID)
        check("refused: the repository's own name is no session's", rc == 2, out)
        check("nothing posted on the old branch", "REPLY" not in calls(), calls())
        subprocess.run(["git", "-C", clone, "remote", "remove", "origin"], check=True, timeout=30, env=git_env())

        print("pr-reply: an older branch named for another working copy is another session's")
        thread_fixture(f"{host}/legacy-old/fix/theirs", False)
        rc, out = invoke("Verified against main; obsolete.", THREAD_ID)
        check("refused: no record of retired clones exists, so it is someone's", rc == 2, out)
        check("nothing posted", "REPLY" not in calls(), calls())

        print("pr-reply: an unowned PR still warns before it replies")
        # Allowed is not unremarkable: the finding may belong to a surface
        # whose role has verified nothing.
        thread_fixture("agent/global-event-identity", False)
        rc, out = invoke("Verified fixed.", THREAD_ID)
        check("exits 0", rc == 0, out)
        check("says the branch names no session", "names no session" in out, out)
        check("warns about the owning surface", "another SURFACE's" in out, out)
        check("  and bounds what may be resolved", "left OPEN" in out, out)
        check("does not invent a rival session", "mid-flight" not in out, out)

        print("pr-reply: a bot branch is never a session called after the bot")
        # `renovate/pub` has the right SHAPE for a session prefix: only the
        # vendor deny-list separates it from a real one.
        thread_fixture("renovate/pub/apps/driver_flutter/flutter-minor-patch-7a91", False)
        rc, out = invoke("Answered.", THREAD_ID)
        check("exits 0", rc == 0, out)
        check("never names the bot as a session", "belongs to 'renovate" not in out, out)

        print("pr-reply: a Dependabot PR is the devex-tooling role's — that role answers, others do not")
        # A Dependabot PR has an OWNER: the devex-tooling role
        # (architect-cto, 2026-09-14). The session holding it answers and
        # may resolve as on its own branch; any other is refused; with no
        # role bound the PR is still somebody's, so refused too.
        dep = "dependabot/nuget/apps/backend_dotnet/dotnet-minor-patch-04e2"
        thread_fixture(dep, False)
        with_role("devex-tooling")
        rc, out = invoke("Superseded by #694; rebased there.", THREAD_ID, AGENT_FABRIC_LAUNCH_ROLE="devex-tooling")
        check("devex-tooling: exits 0", rc == 0, out)
        check("devex-tooling: says the role owns it", "owned by the devex-tooling role" in out, out)
        check("devex-tooling: replied", "REPLY" in calls(), calls())
        check("devex-tooling: resolved by default, as on its own branch", "RESOLVE" in calls(), calls())
        thread_fixture(dep, False)
        with_role("backend-dev")
        rc, out = invoke("Let me answer this one.", THREAD_ID)
        check("backend-dev: refused", rc == 2, out)
        check("backend-dev: names the owning role", "devex-tooling role owns" in out, out)
        check("backend-dev: nothing posted", "REPLY" not in calls(), calls())
        # Bound devex-tooling, launched as another role: the launched role is
        # the session's (review of #68).
        thread_fixture(dep, False)
        with_role("devex-tooling")
        rc, out = invoke("Answering as the binding says.", THREAD_ID, AGENT_FABRIC_LAUNCH_ROLE="backend-dev")
        check("bound devex-tooling, launched backend-dev: refused", rc == 2, out)
        check("…nothing posted", "REPLY" not in calls(), calls())
        # Bound devex-tooling, not started by the launcher: no stamp, no role
        # (review of #70).
        thread_fixture(dep, False)
        with_role("devex-tooling")
        rc, out = invoke("Answering without a launch.", THREAD_ID)
        check("bound devex-tooling, no launch stamp: refused", rc == 2, out)
        check("…nothing posted", "REPLY" not in calls(), calls())
        thread_fixture(dep, False)
        with_role(None)
        rc, out = invoke("No role here.", THREAD_ID)
        check("no role bound: refused", rc == 2, out)
        check("no role bound: nothing posted", "REPLY" not in calls(), calls())

        print("pr-reply: a real session's PR is STILL refused")
        # The relaxation must not reach the case the guard exists for.
        thread_fixture(f"{other}/fix/theirs", False)
        rc, out = invoke("I would like to answer this.", THREAD_ID)
        check("exits 2", rc == 2, out)
        check("still names the owning session", other in out, out)
        check("still posts nothing", "REPLY" not in calls(), calls())

        print("pr-reply: an odd <type> segment is a session, not an unowned branch")
        # pr-sessions imposes no vocabulary on <type>; disagreeing here would
        # ANSWER another session's PR, reached from the other side.
        for t in ("spike-3", "hotfix", "stage-4"):
            thread_fixture(f"{other}/{t}/theirs", False)
            rc, _ = invoke("no", THREAD_ID)
            check(f"refuses another session's '{t}/' branch", rc == 2 and "REPLY" not in calls(), f"rc={rc} {calls()}")

        print("pr-reply: an unowned branch is answered but NOT resolved by default")
        # Resolving is a claim, and this is the path with the least standing
        # to make it.
        thread_fixture("agent/global-event-identity", False)
        rc, out = invoke("Looks addressed, but I have not verified it.", THREAD_ID)
        check("still replies", rc == 0, out)
        check("the reply was posted", "REPLY" in calls(), calls())
        check("the thread was left OPEN", "RESOLVE" not in calls(), calls())
        check("says it is leaving it open", "left OPEN" in out, out)
        check("names the opt-in flag", "--resolve" in out, out)

        print("pr-reply: --resolve is the opt-in on an unowned branch")
        thread_fixture("agent/global-event-identity", False)
        rc, out = invoke("Verified fixed in abc1234.", THREAD_ID, "--resolve")
        check("exits 0", rc == 0, out)
        check("resolves when explicitly asked", "RESOLVE" in calls(), calls())

        print("pr-reply: an OWNED branch still resolves by default")
        thread_fixture(f"{me}/feat/mine", False)
        rc, out = invoke("Fixed.", THREAD_ID)
        check("exits 0", rc == 0, out)
        check("own PR still resolves by default", "RESOLVE" in calls(), calls())

        print("pr-reply: an UNUSUAL <type> is still another session's branch")
        # A shape test on <type> is a permission decision resting on an
        # open-ended set: the guard refuses on the SPECIFIED shape (four
        # segments, non-empty host/clone, non-vendor) and nothing more.
        for t in ("Fix", "chore(gh)", "WIP", "2fix", "-lead", "FEAT", "spike-3", "hotfix"):
            thread_fixture(f"{other}/{t}/x", False)
            rc, _ = invoke("I must not be able to post this.", THREAD_ID)
            check(f"refuses another session's '{t}/' branch", rc == 2 and "REPLY" not in calls(), f"rc={rc} {calls()}")

        print("pr-reply: removing the type test did not make the orphans unreachable")
        for branch in ("renovate/pub/apps/driver_flutter/flutter-minor-patch-7a91",
                       "add-claude-github-actions-1785994932117", "agent/global-event-identity",
                       "agent/common-api-idempotency"):
            thread_fixture(branch, False)
            rc, _ = invoke("Obsolete.", THREAD_ID)
            check(f"still answers '{branch}'", rc == 0 and "REPLY" in calls(), f"rc={rc} {calls()}")

        print("pr-reply: a failed reply never resolves the thread")
        # The worst outcome is a resolved thread with no reply: it reads as
        # answered and shows nothing.
        thread_fixture(f"{me}/feat/thing", False)
        rc, out = invoke("…", THREAD_ID, GH_MOCK_REPLY_FAIL="1")
        check("exits 2", rc == 2, out)
        check("says the reply was rejected", "rejected" in out, out)
        check("the thread was left open", "RESOLVE" not in calls(), calls())

        print("pr-reply: a reply with no URL is treated as not posted")
        thread_fixture(f"{me}/feat/thing", False)
        rc, out = invoke("…", THREAD_ID, GH_MOCK_REPLY_EMPTY="1")
        check("exits 2", rc == 2, out)
        check("says so plainly", "did not post" in out, out)

        print("pr-reply: a failed resolve is reported, not swallowed")
        thread_fixture(f"{me}/feat/thing", False)
        rc, out = invoke("Fixed.", THREAD_ID, GH_MOCK_RESOLVE_FAIL="1")
        check("exits 2", rc == 2, out)
        check("says the reply landed", "replied:" in out, out)
        check("and that the thread is open", "still open" in out, out)

        print("pr-reply: an already-resolved thread is not re-resolved")
        thread_fixture(f"{me}/feat/thing", True)
        rc, out = invoke("One more note.", THREAD_ID)
        check("exits 0", rc == 0, out)
        check("says it is already resolved", "already resolved" in out, out)
        check("no resolve mutation was sent", "RESOLVE" not in calls(), calls())

        print("pr-reply: invocation errors")
        thread_fixture(f"{me}/feat/thing", False)
        rc, out = invoke("body", "PRRC_notathread")
        check("a comment id is refused", rc == 2, out)
        check("explains the difference", "PRRC_ is a comment" in out, out)
        rc, out = invoke("body", "not-an-id")
        check("a malformed id is refused", rc == 2, out)
        rc, out = invoke("", THREAD_ID)
        check("an empty body is refused", rc == 2, out)
        check("says the body is empty", "empty" in out, out)
        for label, body, args in (("a whitespace-only body is refused", "   ", (THREAD_ID,)),
                                  ("a missing thread id is refused", "body", ()),
                                  ("two thread ids are refused", "body", (THREAD_ID, "PRRT_second")),
                                  ("an unknown option is refused", "body", (THREAD_ID, "--nope"))):
            rc, out = invoke(body, *args)
            check(label, rc == 2, f"rc={rc}\n{out}")

        print("pr-reply: outside a worktree it refuses rather than trusting itself")
        # The ownership check is the only protection the script offers, and
        # an unresolvable clone identity once SKIPPED it. Not knowing whose
        # PR this is has to mean stop, not proceed.
        thread_fixture(f"{me}/feat/thing", False)
        with tempfile.TemporaryDirectory() as nogit:
            rc, out = invoke("would post anywhere", THREAD_ID, cwd=nogit)
        check("exits 2", rc == 2, out)
        check("says the identity is unknown", "identity is unknown" in out, out)
        check("nothing was posted", "REPLY" not in calls(), calls())

        print("pr-reply: a missing hard dependency is named, not guessed at")
        # Without git and hostname in the preflight, a missing git surfaces
        # as "not inside a git worktree" at an operator standing in exactly
        # that clone. Diagnostic quality, not a bypass — and it needs a test,
        # since reverting the preflight leaves every other assertion green.
        thread_fixture(f"{me}/feat/thing", False)
        with tempfile.TemporaryDirectory() as strip:
            for b in ("bash", "env", "cat", "cut", "basename", "sed", "grep", "mktemp", "rm"):
                src = shutil.which(b)
                if src:
                    os.symlink(src, f"{strip}/{b}")
            os.symlink(f"{bin_}/gh", f"{strip}/gh")
            # deliberately NOT git and NOT hostname
            rc, out = invoke("body", THREAD_ID, path=strip)
            check("exits 2", rc == 2, out)
            check("names git rather than blaming the cwd", "git is required" in out, out)
            os.symlink(shutil.which("git"), f"{strip}/git")
            rc, out = invoke("body", THREAD_ID, path=strip)
            check("exits 2 for hostname too", rc == 2, out)
            check("names hostname", "hostname is required" in out, out)

        print("pr-reply: a failed thread read stops before posting")
        thread_fixture(f"{me}/feat/thing", False)
        rc, out = invoke("body", THREAD_ID, GH_MOCK_READ_FAIL="1")
        check("exits 2", rc == 2, out)
        check("nothing was posted", "REPLY" not in calls(), calls())

        print("pr-reply: a thread in ANOTHER repository is refused")
        # node(id:) is a GLOBAL lookup, so a foreign thread resolves fine.
        # The branch is one this session OWNS, so the case passes only if the
        # repository check is what stops it.
        thread_fixture(f"{me}/feat/thing", False, "someone-else/other-repo")
        rc, out = invoke("body", THREAD_ID)
        check("exits 2", rc == 2, out)
        check("names both repositories", "someone-else/other-repo" in out, out)
        check("neither replied nor resolved", "REPLY" not in calls() and "RESOLVE" not in calls(), calls())

        print("pr-reply: an unknowable current repository is refused, not assumed")
        # Failing open here restores the whole hole: with no local repository
        # to compare, every foreign thread would match nothing and pass.
        thread_fixture(f"{me}/feat/thing", False)
        # No GH_REPO and a clone with no GitHub origin: nothing names the
        # repository, and gh's default is never asked.
        rc, out = invoke("body", THREAD_ID, GH_REPO="")
        check("exits 2", rc == 2, out)
        check("says it cannot tell", "cannot determine the current repository" in out, out)
        check("nothing was posted", "REPLY" not in calls(), calls())

        print("pr-reply: --dry-run touches nothing")
        thread_fixture(f"{me}/feat/thing", False)
        rc, out = invoke("Would say this.", THREAD_ID, "--dry-run")
        check("exits 0", rc == 0, out)
        check("shows the target", "#77" in out, out)
        check("shows the body", "Would say this." in out, out)
        check("no mutation was sent", "REPLY" not in calls() and "RESOLVE" not in calls(), calls())

        print("pr-reply: --help lists the flags")
        rc, out = invoke("", "--help")
        check("exits 0", rc == 0, out)
        check("documents --no-resolve", "--no-resolve" in out, out)
        check("documents --dry-run", "--dry-run" in out, out)

    print(f"\ntest_pr_reply_cli: {'OK' if not fails else f'FAILED — {fails} check(s)'}")
    return 1 if fails else 0


if __name__ == "__main__":
    scrub_process_env()
    sys.exit(main())
