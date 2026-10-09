#!/usr/bin/env python3
"""Tests for tools/fabric/github/commit_class.py's internals; the rule
itself is tests/test_commit_class_cli.py's, run unchanged against the
shim (ADR-040 §5 rule 5)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
from github import commit_class as cc  # noqa: E402


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: object = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {detail}"))
        fails += not good

    with tempfile.TemporaryDirectory() as tmp:
        reg = os.path.join(tmp, "registry.json")
        json.dump({"projects": {"gzapp": {"remotes": ["git@github.com:gzapi-org/gzapp.git"]},
                                "interweave": {"remotes": ["https://github.com/gzapi-org/InterWeave.git"]}}}, open(reg, "w"))
        check("known_repos: each project id and each remote's name, lower-cased",
              cc.known_repos(reg) == {"gzapp", "interweave"}, cc.known_repos(reg))
        check("known_repos: an unreadable registry names none", cc.known_repos(os.path.join(tmp, "none.json")) == set())
    check("_ref: owner/repo#N of this repository is N", cc._ref("gzapi-org/agent-fabric#53", "gzapi-org/agent-fabric") == "53")
    check("_ref: owner/repo#N of another is x", cc._ref("gzapi-org/gzapp#53", "gzapi-org/agent-fabric") == "x")
    check("_ref: 'PR #918' is this repository's", cc._ref("PR #918", "gzapi-org/agent-fabric") == "918")
    check("_ref: without a repository only the number counts", cc._ref("gzapp#9", "") == "9")
    # kind_of reads the trailer block only, as git and pr_gate do (#120 N1).
    k = cc.kind_of
    check("kind_of: a Kind: line in the prose declares nothing (the re-review's message)",
          k("review fix (#5 F1): x\n\nKind: work\nand more prose") == "")
    check("kind_of: the same commit through classify falls back to its subject, as pr_gate reads it",
          cc.classify("a", "review fix (#5 F1): x", "", "5", "",
                      k("review fix (#5 F1): x\n\nKind: work\nand more prose")) == "fix")
    check("kind_of: the trailer block's Kind: is read",
          k("subject\n\nbody prose\n\nKind: work\nFabric-Role: devex-tooling\n") == "work")
    check("kind_of: a Kind: line in an earlier paragraph is not the block",
          k("subject\n\nKind: review-fix\n\nFabric-Role: devex-tooling") == "")
    check("kind_of: a continuation line keeps the block a block",
          k("s\n\nAnswers: F1,\n  F2\nKind: review-fix") == "review-fix")
    check("kind_of: two Kind: trailers, the last wins", k("s\n\nKind: work\nKind: review-fix") == "review-fix")
    check("kind_of: a body of one paragraph that is the subject declares nothing", k("Kind of a subject") == "")
    check("kind_of: an empty body declares nothing", k("") == "")
    check("revert_targets: git's own line, nothing else",
          cc.revert_targets("Revert x\n\nThis reverts commit abcdef1234.\nreverts commit 999") == ["abcdef1234"])
    tool = os.path.join(HERE, "tools", "fabric", "github", "commit_class.py")
    r = subprocess.run([sys.executable, tool, "class"], capture_output=True, text=True)
    check("the CLI refuses too few arguments as usage (exit 2)", r.returncode == 2 and "usage" in r.stderr, r.stderr)
    r = subprocess.run([sys.executable, tool, "class", "a b", "anything"], capture_output=True, text=True)
    check("the CLI prints one word", r.stdout == "merge\n", r.stdout)
    folds(check, tool)
    on_github(check)
    print(f"\n{'FAILED' if fails else 'all passed'}")
    return 1 if fails else 0


# A fake gh on PATH: `gh pr view <n> --json … --repo <r>` prints
# <dir>/pr-<n>.json, or fails as gh does on a PR it cannot read; every call
# is logged, so a second ask of the same PR shows. Never the real gh.
FAKE_GH = """#!/bin/sh
printf '%s\\n' "$*" >> "$FAKE_GH_DIR/calls"
[ "$1 $2" = "pr view" ] && [ -f "$FAKE_GH_DIR/pr-$3.json" ] && exec cat "$FAKE_GH_DIR/pr-$3.json"
echo "GraphQL: Could not resolve to a PullRequest with the number of $3. (HTTP 404)" >&2
exit 1
"""


def folds(check, tool: str) -> None:
    """ADR-019 §5 rule 3, amended: a PR closed unmerged whose head lies
    inside the counted head was folded in, and its review fixes are fixes
    (gateway#10 into #11, 8 work where 6 was right)."""
    print("a folded PR's review fixes are fixes")
    with tempfile.TemporaryDirectory() as tmp:
        repo, ghdir = os.path.join(tmp, "repo"), os.path.join(tmp, "gh")
        os.makedirs(os.path.join(ghdir, "bin"))
        open(os.path.join(ghdir, "calls"), "w").close()
        fake = os.path.join(ghdir, "bin", "gh")
        open(fake, "w").write(FAKE_GH)
        os.chmod(fake, 0o755)
        env = {k: v for k, v in os.environ.items() if not k.startswith(("GIT_", "GH_", "AGENT_FABRIC_", "GITHUB_"))}
        env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1", GIT_AUTHOR_NAME="t",
                   GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t",
                   PATH=f"{ghdir}/bin:{env.get('PATH', '')}", FAKE_GH_DIR=ghdir)

        def git(*args: str) -> str:
            return subprocess.run(["git", "-C", repo, *args], env=env, check=True, capture_output=True,
                                  text=True).stdout.strip()

        def commit(msg: str) -> str:
            git("commit", "-q", "--allow-empty", "-m", msg)
            return git("rev-parse", "HEAD")

        def pr(n: int, state: str, head: str, merged: bool = False) -> None:
            json.dump({"state": state, "headRefOid": head, "mergedAt": "2026-10-08T12:00:00Z" if merged else None},
                      open(os.path.join(ghdir, f"pr-{n}.json"), "w"))

        os.makedirs(repo)
        git("init", "-q", "-b", "main")
        commit("base")
        git("checkout", "-q", "-b", "side")
        aside = commit("a closed PR's head, never folded")
        git("checkout", "-q", "main")
        folded_head = commit("#10's review fix")
        head = commit("#11's own work")
        pr(10, "CLOSED", folded_head)                 # the fold
        pr(9, "MERGED", folded_head, merged=True)     # a follow-up's predecessor
        pr(12, "CLOSED", aside)                       # closed, not inside
        pr(13, "CLOSED", "1234567890abcdef1234567890abcdef12345678")  # a head this clone never had
        pr(14, "OPEN", folded_head)                   # open: not folded

        saved_env, here = dict(os.environ), os.getcwd()
        os.environ.clear()
        os.environ.update(env)
        os.chdir(repo)
        try:
            import io
            from contextlib import redirect_stderr

            def cls(answers: str, n: str = "11", look=None, subject: str = "x", kind: str = "review-fix"):
                err = io.StringIO()
                with redirect_stderr(err):
                    got = cc.classify("p", subject, answers, n, "o/r", kind, look or cc.Folds("o/r", head))
                return got, err.getvalue()

            got, err = cls("review of #10, F1")
            check("a fold: closed, unmerged, head inside — a fix", got == "fix", (got, err))
            check("…and nothing said", err == "", err)
            got, _ = cls("", subject="review of #10: the probe exits 3", kind="")
            check("a fold named only in the subject, undeclared — a fix", got == "fix", got)
            got, err = cls("#9 F2")
            check("a follow-up: #9 merged — work", got == "work" and err == "", (got, err))
            got, err = cls("#12 F1")
            check("closed but its head not inside — work", got == "work" and err == "", (got, err))
            got, err = cls("#13 F1")
            check("closed, its head not in this full clone — work, nothing said", got == "work" and err == "",
                  (got, err))
            shallow = os.path.join(tmp, "shallow")
            subprocess.run(["git", "clone", "-q", "--depth", "1", f"file://{repo}", shallow], env=env, check=True)
            err = io.StringIO()
            with redirect_stderr(err):
                got = cc.classify("p", "x", "#10 F1", "11", "o/r", "review-fix", cc.Folds("o/r", head, cwd=shallow))
            check("a shallow clone cannot answer — work, said", got == "work" and "#10 could not be read" in err.getvalue(),
                  (got, err.getvalue()))
            got, err = cls("#14 F1")
            check("an open PR — work", got == "work" and err == "", (got, err))
            got, err = cls("#77 F1")
            check("a lookup failure — work (the reading before the amendment)", got == "work", got)
            check("…said on stderr, naming the PR", "#77 could not be read" in err and "HTTP 404" in err, err)
            open(os.path.join(ghdir, "pr-78.json"), "w").write("not json")
            got, err = cls("#78 F1")
            check("an answer that is not JSON — work, said", got == "work" and "#78 could not be read" in err,
                  (got, err))
            got, _ = cls("#10 F1, #9 F2")
            check("a fold and a follow-up named together — work: every PR named must be a fold",
                  got == "work", got)
            got, _ = cls("gzapi-org/gzapp#10 F1")
            check("another repository's #10 is never a fold", got == "work", got)
            got, _ = cls("#10 F1", kind="work")
            check("Kind: work stays work, folded or not", got == "work", got)
            got, _ = cls("#10 F1", n="")
            check("without the PR being counted the rule does not ask", got == "fix", got)

            open(os.path.join(ghdir, "calls"), "w").close()
            look = cc.Folds("o/r", head)
            for answers in ("#10 F1", "#10 F2", "review of #10, F3", "#77 F1", "#77 F2"):
                cls(answers, look=look)
            calls = open(os.path.join(ghdir, "calls")).read().splitlines()
            check("one gh call per distinct PR named, a failed one included",
                  sorted(c.split()[2] for c in calls) == ["10", "77"], calls)
            check("…each asking that repository for state, mergedAt and the head",
                  all("--repo o/r" in c and "state,mergedAt,headRefOid" in c for c in calls), calls)

            open(os.path.join(ghdir, "calls"), "w").close()
            asked: list[str] = []
            got, _ = cls("#11 F1", look=lambda n: asked.append(n) or True)
            check("a commit answering this PR's own review is a fix and asks nothing", got == "fix" and not asked,
                  (got, asked))
            r = subprocess.run([sys.executable, tool, "class", "p", "x", "#10 F1", "11", "o/r", "review-fix", head],
                               capture_output=True, text=True, env=env)
            check("the CLI reads a fold with <head>, the eighth argument", r.stdout == "fix\n", (r.stdout, r.stderr))
            r = subprocess.run([sys.executable, tool, "class", "p", "x", "#10 F1", "11", "o/r", "review-fix"],
                               capture_output=True, text=True, env=env)
            check("…and without it reads as before, work, asking nothing",
                  r.stdout == "work\n" and open(os.path.join(ghdir, "calls")).read().count("10") == 1,
                  (r.stdout, r.stderr))
        finally:
            os.chdir(here)
            os.environ.clear()
            os.environ.update(saved_env)




def on_github(check) -> None:
    """Folds' ancestry asked of GitHub: each compare answer as measured
    (2026-10-09), and every other one unread, never "no"."""
    import io
    from contextlib import redirect_stderr
    import gh
    real_api, real_view = gh.api, gh.pr_view
    asked: list[str] = []

    def answering(answer):
        def api(path, **kw):
            asked.append(path)
            if isinstance(answer, Exception):
                raise answer
            return answer
        return api
    try:
        for status, want in (("ahead", True), ("identical", True), ("behind", False), ("diverged", False)):
            gh.api = answering({"status": status, "ahead_by": 1})
            check(f"on_github: {status} is {want}", cc.on_github("o/r")("a" * 40, "b" * 40) is want)
        check("on_github: asks compare <oid>...<head> of the repository, one commit a page",
              asked[-1] == f"repos/o/r/compare/{'a' * 40}...{'b' * 40}?per_page=1", asked[-1])
        for label, answer in (("a 404", gh.GhError("gh api GET repos/o/r/compare", "Not Found", 404)),
                              ("no status", {"message": "x"}), ("an unknown status", {"status": "sideways"}),
                              ("not an object", ["x"]), ("not JSON", ValueError("x"))):
            gh.api = answering(answer)
            try:
                cc.on_github("o/r")("a" * 40, "b" * 40)
                check(f"on_github: {label} raises", False)
            except gh.GhError:
                check(f"on_github: {label} raises, never no", True)
        gh.pr_view = lambda n, fields, **kw: {"state": "CLOSED", "mergedAt": None, "headRefOid": "a" * 40}
        gh.api = answering({"status": "ahead"})
        look = cc.Folds("o/r", "b" * 40, cwd="/nonexistent", ancestor=cc.on_github("o/r"))
        check("Folds with GitHub's ancestry: a fold, no clone asked", look("10") is True)
        gh.api = answering(gh.GhError("gh api GET repos/o/r/compare", "Not Found", 404))
        err = io.StringIO()
        with redirect_stderr(err):
            got = cc.Folds("o/r", "b" * 40, cwd="/nonexistent", ancestor=cc.on_github("o/r"))("10")
        check("...an unread ancestry is no, said", got is False and "#10 could not be read (Not Found)" in err.getvalue(),
              err.getvalue())
    finally:
        gh.api, gh.pr_view = real_api, real_view

if __name__ == "__main__":
    sys.exit(main())
