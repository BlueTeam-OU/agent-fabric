#!/usr/bin/env python3
"""tools/fabric/review_rounds.py through bin/fabric-review: a round's
report is kept private under the account's state, and a re-review's
request is derived from the previous one and that report, never edited by
hand (architect-cto-01's request 01a10026). Plain script: ok/FAIL, exit 1
on any failure."""
from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
import review_brief  # noqa: E402
REVIEW = os.path.join(HERE, "bin", "fabric-review")
GIT = {"GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null", "GIT_AUTHOR_NAME": "t",
       "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}

# What a re-review of a PR starts from is the PR's last v2 review, read from GitHub (agent-fabric ADR-065 §2 C): a gh
# that answers the three calls the checkpoint makes from the case's state file, and refuses any other.
FAKE_GH = r"""#!%(python)s
import json, os, sys
state = json.load(open(os.environ["GH_STATE_FILE"]))
a = sys.argv[1:]
if a[:2] == ["pr", "view"] and "author" in a:
    print(json.dumps({"author": {"login": "me"}}))
elif a[:2] == ["api", "-i"] and a[2].split("?")[0].endswith("/pulls/7/reviews"):
    sys.stdout.write("HTTP/2.0 200 OK\r\n\r\n" + json.dumps(state["reviews"]))
elif a[:2] == ["api", "-i"] and a[2].split("?")[0].endswith("/pulls/7/commits"):
    sys.stdout.write("HTTP/2.0 200 OK\r\n\r\n" + json.dumps([{"sha": c} for c in state["commits"]]))
else:
    print("fake gh: unhandled " + " ".join(a), file=sys.stderr); sys.exit(1)
"""


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: object = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {detail}"))
        fails += not good

    tmp = tempfile.mkdtemp(prefix="test_review_rounds.")
    try:
        env = {k: v for k, v in os.environ.items() if not k.startswith(("AGENT_FABRIC_", "GITHUB_", "GIT_"))}
        env.update(GIT, AGENT_FABRIC_STATE_DIR=os.path.join(tmp, "state"), HOME=os.path.join(tmp, "home"),
                   TMPDIR=os.path.join(tmp, "tmpdir"))
        os.makedirs(env["TMPDIR"])
        fakebin = os.path.join(tmp, "bin")
        os.makedirs(fakebin)
        with open(os.path.join(fakebin, "gh"), "w") as f:
            f.write(FAKE_GH % {"python": sys.executable})
        os.chmod(os.path.join(fakebin, "gh"), 0o755)
        gh_state = os.path.join(tmp, "gh-state.json")
        env.update(PATH=f"{fakebin}:{env.get('PATH', '')}", GH_STATE_FILE=gh_state, GH_REPO="o/r")
        repo = os.path.join(tmp, "work", "myrepo")
        os.makedirs(repo)

        def git(*a: str) -> str:
            return subprocess.run(["git", "-C", repo, *a], env=env, check=True, capture_output=True,
                                  text=True, timeout=30).stdout.strip()

        def commit(msg: str) -> str:
            git("commit", "-q", "--allow-empty", "--no-gpg-sign", "-m", msg)
            return git("rev-parse", "HEAD")

        git("init", "-q", "-b", "main")
        base = commit("base")
        head1 = commit("work")

        def run(*args: str, stdin: str = "", cwd: str = repo) -> subprocess.CompletedProcess:
            return subprocess.run([REVIEW, *args], env=env, input=stdin, capture_output=True, text=True,
                                  cwd=cwd, timeout=60)

        def review_body(rbase: str, rhead: str, card: str, finding: str) -> str:
            """A posted v2 review: the marker line, the report, the coverage block of a range that changed no path."""
            marker = (f"<!-- agent-fabric-review v2 base={rbase} head={rhead} card={card} "
                      f"config={review_brief.config_fingerprint(repo, card)} -->")
            return (f"{marker}\n<!-- model: codex -->\n**Blind review**\n\n{finding}\n\n"
                    f"```agent-fabric-coverage v1\n{json.dumps({'paths': {}, 'lenses': {}})}\n```\n")

        def serve(reviews: list[dict], commits: list[str]) -> None:
            with open(gh_state, "w") as fh:
                json.dump({"reviews": reviews, "commits": commits}, fh)

        def posted_review(text: str, rhead: str, at: str) -> dict:
            return {"user": {"login": "me"}, "commit_id": rhead, "submitted_at": at, "body": text}

        round1 = review_body(base, head1, base, "## Round 1\n\n1. **P2:** a finding.")
        req = os.path.join(tmp, "scratch", "REQUEST.yaml")
        os.makedirs(os.path.dirname(req))
        with open(req, "w") as f:
            f.write(f"mode: review\nrepository: {repo}\nrange: {base[:12]}..{head1[:12]}\n"
                    "objective: >-\n  The thing exists.\nrequirements:\n  - It exists.\n"
                    "lenses:\n  - general\n  - security\n")

        print("save")
        r = run("save", "7", "1", stdin=round1)
        saved = r.stdout.strip()
        check("a round is kept under the account's state, by repository and PR",
              r.returncode == 0 and saved == os.path.join(tmp, "state", "agents", os.environ.get("USER") or
                                                         subprocess.run(["id", "-un"], capture_output=True,
                                                                        text=True).stdout.strip(),
                                                         "reviews", "myrepo", "pr-7", "round-1.md"), (r, saved))
        levels = [os.path.dirname(saved), os.path.dirname(os.path.dirname(saved)),
                  os.path.dirname(os.path.dirname(os.path.dirname(saved)))]
        check("…0600, under directories 0700 at every level (review of #89)",
              stat.S_IMODE(os.stat(saved).st_mode) == 0o600
              and all(stat.S_IMODE(os.stat(d).st_mode) == 0o700 for d in levels),
              [oct(stat.S_IMODE(os.stat(d).st_mode)) for d in levels])
        def mode_of(rnd: str, pr: str = "7") -> object:
            with open(os.path.join(os.path.dirname(os.path.dirname(saved)), f"pr-{pr}", f"round-{rnd}.json"),
                      encoding="utf-8") as fh:
                return json.load(fh).get("evidence_mode")
        check("a round with no dispatch header records no evidence mode, never a guessed one", mode_of("1") is None,
              mode_of("1"))
        run("save", "99", "2", stdin='```agent-fabric-dispatch v1\n{"evidence_mode": "working-tree"}\n```\n\n## 1.\n')
        check("…a round records the mode its report's dispatch header names (ADR-020 rule 10)",
              mode_of("2", "99") == "working-tree", mode_of("2", "99"))
        run("save", "99", "4", stdin='``` agent-fabric-dispatch v1\n{"evidence_mode": "working-tree"}\n```\n')
        check("a space between the fence and the info string still reads (CommonMark; review round 1 of #259: F5)",
              mode_of("4", "99") == "working-tree", mode_of("4", "99"))
        run("save", "99", "3", stdin='```agent-fabric-dispatch v1\nnot json\n```\n')
        check("…and a header it cannot read as unreadable", mode_of("3", "99") == "unreadable", mode_of("3", "99"))
        r = run("save", "7", "1", stdin="  \n")
        check("an empty report is refused", r.returncode == 1 and "no report" in r.stderr, r.stderr)
        r = run("save", "x7", "1", stdin="r")
        check("a PR that is not a number is refused", r.returncode == 1, r.stderr)
        r = run("save", "7", "1", "--repo", "../etc", stdin="r")
        check("a --repo that is a path is refused", r.returncode == 1 and "plain directory name" in r.stderr, r.stderr)

        print("next")
        r = run("next", req, "--pr", "7")
        check("the head has not moved: refused, nothing written",
              r.returncode == 1 and "has not moved" in r.stderr
              and not os.path.exists(os.path.join(tmp, "scratch", "REQUEST-rr2.json")), r.stderr)
        head2 = commit("fix")
        elsewhere = os.path.join(tmp, "work", "otherrepo")
        os.makedirs(elsewhere)
        subprocess.run(["git", "init", "-q", elsewhere], env=env, check=True, timeout=30)
        serve([posted_review(round1, head1, "2026-10-23T10:00:00Z")], [head1, head2])
        r = run("next", req, "--pr", "7", cwd=elsewhere)
        nxt_path = os.path.join(tmp, "scratch", "REQUEST-rr2.json")
        check("--pr finds the round by the request's repository, not the cwd's (review of #89)",
              r.returncode == 0, r.stderr)
        nxt = json.load(open(nxt_path)) if os.path.exists(nxt_path) else {}
        check("a moved head: REQUEST-rr2.json beside the request",
              r.returncode == 0 and os.path.isfile(nxt_path), r.stderr)
        # With a PR the previous report is its last posted review, which the
        # brief reads; a typed copy would be refused (ADR-065 §5 rule 5).
        check("…mode re-review, range old head..new head, no typed previous findings beside the PR",
              nxt.get("mode") == "re-review" and nxt.get("range") == f"{head1[:12]}..{head2[:12]}"
              and nxt.get("pr") and "previous_findings" not in nxt, nxt)
        check("…lenses narrowed to general, everything else carried",
              nxt.get("lenses") == ["general"] and nxt.get("requirements") == ["It exists."]
              and nxt.get("repository") == repo, nxt)
        check("…and the brief is rendered to stdout, the saved report in it",
              "## Mode\nre-review" in r.stdout and "a finding." in r.stdout, r.stdout[:300])
        head3 = commit("fix 2")
        round2 = review_body(head1, head2, base, "## Round 2\n\nclean")
        serve([posted_review(round1, head1, "2026-10-23T10:00:00Z"), posted_review(round2, head2, "2026-10-23T11:00:00Z")],
              [head1, head2, head3])
        report2 = os.path.join(tmp, "scratch", "report-2.md")
        with open(report2, "w") as f:
            f.write("## Round 2\n\nclean\n")
        r = run("next", nxt_path, "--report", report2, "--keep-lenses")
        nxt3 = json.load(open(os.path.join(tmp, "scratch", "REQUEST-rr3.json"))) if r.returncode == 0 else {}
        check("from a round's own request: REQUEST-rr3.json, range from that round's head, --report taken",
              r.returncode == 0 and nxt3["range"] == f"{head2[:12]}..{head3[:12]}"
              and "previous_findings" not in nxt3, (r.stderr, nxt3))
        check("…the first round's base is carried as card_base, so the card stays the first round's",
              nxt.get("card_base") == base and nxt3.get("card_base") == base, (nxt.get("card_base"), nxt3.get("card_base"), base))
        check("…review_round counts up from 1 and the review_id and pr are filled",
              nxt.get("review_round") == 2 and nxt3.get("review_round") == 3
              and nxt.get("pr") == "7" and nxt.get("review_id") == "myrepo#7", (nxt, nxt3))
        header = json.loads(r.stdout.split("\n```\n", 1)[0].split("\n", 1)[1]) if r.stdout.startswith("```agent-fabric-dispatch v1\n") else {}
        check("…and the brief opens with the dispatch header: a re-review of round 3 over base..head",
              header.get("purpose") == "re-review" and header.get("review_round") == 3 and header.get("pr") == 7
              and header.get("review_id") == "myrepo#7" and header.get("base_sha") == head2 and header.get("head_sha") == head3,
              header)
        keep_req = os.path.join(tmp, "scratch", "KEEP.yaml")
        shutil.copy(req, keep_req)
        r = run("next", keep_req, "--report", report2, "--keep-lenses")
        kept = json.load(open(os.path.join(tmp, "scratch", "KEEP-rr2.json")))
        check("--keep-lenses keeps a two-lens request's lenses; without it they narrow (review of #89)",
              r.returncode == 0 and kept["lenses"] == ["general", "security"] and nxt["lenses"] == ["general"],
              (r.stderr, kept.get("lenses")))
        sym = os.path.join(tmp, "scratch", "SYM.yaml")
        with open(sym, "w") as f:
            f.write(open(req).read().replace(f"..{head1[:12]}", "..HEAD"))
        r = run("next", sym, "--report", report2)
        check("a previous head that is no commit id (..HEAD) is refused, nothing written (review of #89)",
              r.returncode == 1 and "not a commit id" in r.stderr
              and not os.path.exists(os.path.join(tmp, "scratch", "SYM-rr2.json")), r.stderr)
        verdict = os.path.join(tmp, "scratch", "VERDICT.yaml")
        with open(verdict, "w") as f:
            f.write(open(req).read().replace("The thing exists.", "The change correctly makes it exist."))
        r = run("next", verdict, "--report", report2)
        check("a render that refuses writes no request to number past (review of #89)",
              r.returncode == 1 and not os.path.exists(os.path.join(tmp, "scratch", "VERDICT-rr2.json")), r.stderr)
        r = run("next", verdict, "--report", report2, "--allow-rationale")
        check("…and --allow-rationale passes through to the render",
              r.returncode == 0 and os.path.exists(os.path.join(tmp, "scratch", "VERDICT-rr2.json")), r.stderr)
        bad = os.path.join(tmp, "scratch", "BAD.yaml")
        with open(bad, "w") as f:
            f.write(open(req).read().replace(f"range: {base[:12]}..{head1[:12]}", "range: HEAD"))
        r = run("next", bad, "--report", report2)
        check("a source request whose range does not validate: one line naming it, exit 1 (review of #89)",
              r.returncode == 1 and "'HEAD'" in r.stderr and r.stderr.strip().count("\n") == 0, r.stderr)
        gone = os.path.join(tmp, "scratch", "gone-report.md")
        with open(gone, "w") as f:
            f.write("an earlier round\n")
        chain = os.path.join(tmp, "scratch", "CHAIN-rr2.json")
        with open(chain, "w") as f:
            json.dump({**nxt3, "previous_findings": gone}, f)
        os.remove(gone)
        head4 = commit("fix 3")
        round3 = review_body(head2, head3, base, "## Round 3\n\nclean")
        serve([posted_review(round1, head1, "2026-10-23T10:00:00Z"), posted_review(round2, head2, "2026-10-23T11:00:00Z"),
               posted_review(round3, head3, "2026-10-23T12:00:00Z")], [head1, head2, head3, head4])
        r = run("next", chain, "--report", report2)
        check("an earlier round's report deleted since does not refuse the chain (review of #89)",
              r.returncode == 0 and json.load(open(os.path.join(tmp, "scratch", "CHAIN-rr3.json")))["range"]
              == f"{head3[:12]}..{head4[:12]}", r.stderr)
        norepo = os.path.join(tmp, "scratch", "NOREPO.json")
        with open(norepo, "w") as f:
            json.dump({k: v for k, v in nxt3.items() if k != "repository"}, f)
        r = run("next", norepo, "--pr", "7")
        check("--pr with a request naming no repository: refused in one line, no traceback (review of #89)",
              r.returncode == 1 and "names no repository" in r.stderr and "Traceback" not in r.stderr, r.stderr)
        r = run("next", req, "--pr", "8")
        check("a PR with no saved round is refused, naming save", r.returncode == 1 and "fabric-review save" in r.stderr,
              r.stderr)
        r = run("next", req)
        check("neither --report nor --pr: usage, exit 2", r.returncode == 2, r.stderr)
        r = run("next", req, "--pr", "7", "--head", "nonesuch")
        check("a --head that is no commit is refused", r.returncode == 1 and "not a commit" in r.stderr, r.stderr)

        print("delta-first")
        # A real file history: the fix inserts three lines above a finding's
        # line (a move) and rewrites another finding's line.
        drepo = os.path.join(tmp, "work", "deltarepo")
        os.makedirs(drepo)

        def dgit(*a: str) -> str:
            return subprocess.run(["git", "-C", drepo, *a], env=env, check=True, capture_output=True,
                                  text=True, timeout=30).stdout.strip()

        dgit("init", "-q", "-b", "main")
        body = ["def alpha():\n", "    return 1\n", "\n"] + [f"x{i} = {i}\n" for i in range(4, 20)] + \
               ["def beta():\n", "    return 'old'\n", "\n"] + [f"y{i} = {i}\n" for i in range(24, 31)]
        with open(os.path.join(drepo, "a.py"), "w") as f:
            f.writelines(body)
        dgit("add", "a.py")
        dgit("commit", "-q", "--no-gpg-sign", "-m", "one")
        b1 = dgit("rev-parse", "HEAD")
        new_body = ["# header 1\n", "# header 2\n", "# header 3\n"] + body
        new_body[new_body.index("    return 'old'\n")] = "    return 'new'\n"
        with open(os.path.join(drepo, "a.py"), "w") as f:
            f.writelines(new_body)
        dgit("commit", "-q", "--no-gpg-sign", "-am", "two")
        drep = os.path.join(tmp, "scratch", "dreport.md")
        with open(drep, "w") as f:
            f.write("## Findings on the change\n1. P2 likely: `a.py:19` is a leftover; also see localhost:8080 and ghost.py:3.\n"
                    "2. P3 confirmed: a.py:21 returns the wrong value.\n")
        dreq = os.path.join(tmp, "scratch", "DREQ.yaml")
        with open(dreq, "w") as f:
            f.write(f"mode: review\nrepository: {drepo}\nrange: {b1[:12]}..{b1[:12]}\nobjective: >-\n  It exists.\n")
        r = run("next", dreq, "--report", drep, cwd=drepo)
        out = r.stdout
        diff_text = subprocess.run(["git", "-C", drepo, "diff", b1, "HEAD"], env=env, capture_output=True, text=True,
                                   timeout=30).stdout.rstrip("\n")
        check("the re-review's brief embeds the exact diff of its range",
              r.returncode == 0 and f"## Re-review diff\nThe exact diff of the range above.\n```diff\n{diff_text}\n```\n" in out,
              (r.stderr, out[-600:]))
        check("…the finding at a moved line is located at its new line",
              "- finding 1: a.py:19 at " in out and "is now a.py:22 (moved +3)" in out, out[-900:])
        check("…a rewritten line is named as rewritten, with its new line",
              "- finding 2: a.py:21 at " in out and "is now a.py:24-24 (rewritten in the range)" in out, out[-900:])
        check("…text that only looks like a locator (a path the old head lacks) is not listed",
              "localhost" not in out.split("## Locators")[-1] and "ghost.py" not in out.split("## Locators")[-1], out[-900:])
        check("…each hunk's enclosing symbol is listed where git names one",
              "- a.py:24: def beta():" in out.split("enclosing symbol")[-1], out[-400:])
        nxt_d = json.load(open(os.path.join(tmp, "scratch", "DREQ-rr2.json")))
        check("…none of it is written into the derived request", "Locators" not in json.dumps(nxt_d) and "diff" not in nxt_d, nxt_d)

        # Over the cap: the diffstat and a note, not the diff.
        with open(os.path.join(drepo, "big.txt"), "w") as f:
            f.write("".join(f"line {i} " + "z" * 60 + "\n" for i in range(1200)))
        dgit("add", "big.txt")
        dgit("commit", "-q", "--no-gpg-sign", "-m", "three")
        r = run("next", dreq, "--report", drep, cwd=drepo)
        tail = r.stdout.split("## Re-review diff")[-1].split("## Locators")[0]
        check("a diff over 64 KB is replaced by its --stat and a note saying so",
              r.returncode == 0 and "over the 65536-byte cap" in tail and " big.txt | 1200 +" in tail
              and "line 1199 zzzz" not in r.stdout, (r.stderr, tail[:600]))
        nxt_big = [x for x in os.listdir(os.path.join(tmp, "scratch")) if x.startswith("DREQ-rr")]
        check("…and each run wrote its own numbered request", sorted(nxt_big) == ["DREQ-rr2.json", "DREQ-rr3.json"], nxt_big)

        print("card_base")
        crepo = os.path.join(tmp, "work", "cardrepo")
        os.makedirs(crepo)

        def cgit(*a: str) -> str:
            return subprocess.run(["git", "-C", crepo, *a], env=env, check=True, capture_output=True,
                                  text=True, timeout=30).stdout.strip()

        cgit("init", "-q", "-b", "main")
        cgit("commit", "-q", "--allow-empty", "--no-gpg-sign", "-m", "c0")
        c0 = cgit("rev-parse", "HEAD")
        cgit("checkout", "-q", "-b", "feature")
        cgit("commit", "-q", "--allow-empty", "--no-gpg-sign", "-m", "f1")
        f1 = cgit("rev-parse", "HEAD")
        creq = os.path.join(tmp, "scratch", "CARD.yaml")
        with open(creq, "w") as f:
            f.write(f"mode: review\nrepository: {crepo}\nrange: main..{f1[:12]}\nobjective: >-\n  It exists.\n")
        cgit("commit", "-q", "--allow-empty", "--no-gpg-sign", "-m", "f2")
        # The default branch moves BEFORE the first `next`: a symbolic base
        # would resolve to the moved tip, not to the card round 1 read.
        cgit("checkout", "-q", "main")
        cgit("commit", "-q", "--allow-empty", "--no-gpg-sign", "-m", "main moves early")
        cgit("checkout", "-q", "feature")
        r = run("next", creq, "--report", report2, cwd=crepo)
        check("a symbolic first base with no card_base is refused, naming card_base; nothing written",
              r.returncode == 1 and "is not a commit id" in r.stderr and "card_base" in r.stderr
              and not os.path.exists(os.path.join(tmp, "scratch", "CARD-rr2.json")), (r.returncode, r.stderr))
        with open(creq, "a") as f:
            f.write(f"card_base: {c0}\n")
        r = run("next", creq, "--report", report2, cwd=crepo)
        c2 = json.load(open(os.path.join(tmp, "scratch", "CARD-rr2.json"))) if r.returncode == 0 else {}
        check("a symbolic first base, pinned by card_base, is carried as that commit id in the first derived request (review round 1 of #259: F7)",
              c2.get("card_base") == c0, (r.stderr, c2.get("card_base"), c0))
        cgit("checkout", "-q", "main")
        cgit("commit", "-q", "--allow-empty", "--no-gpg-sign", "-m", "main moves")
        cgit("checkout", "-q", "feature")
        cgit("commit", "-q", "--allow-empty", "--no-gpg-sign", "-m", "f3")
        r = run("next", os.path.join(tmp, "scratch", "CARD-rr2.json"), "--report", report2, cwd=crepo)
        c3 = json.load(open(os.path.join(tmp, "scratch", "CARD-rr3.json"))) if r.returncode == 0 else {}
        check("…and a later round keeps it after the default branch has moved on", c3.get("card_base") == c0, (r.stderr, c3))
        old = os.path.join(tmp, "scratch", "OLDCHAIN-rr2.json")
        with open(old, "w") as f:
            json.dump({k: v for k, v in c3.items() if k != "card_base"}, f)
        cgit("commit", "-q", "--allow-empty", "--no-gpg-sign", "-m", "f4")
        r = run("next", old, "--report", report2, cwd=crepo)
        check("a chain begun without card_base, whose base the default branch lacks, is refused naming card_base",
              r.returncode == 1 and "card_base" in r.stderr and "not an ancestor" in r.stderr
              and not os.path.exists(os.path.join(tmp, "scratch", "OLDCHAIN-rr3.json")), r.stderr)
        print("head worktree")
        evroot = os.path.join(env["TMPDIR"], "fabric-review")
        head1 = git("rev-parse", "HEAD")  # the head `next` re-reviews: where the earlier sections left the repository
        wt = os.path.join(evroot, f"myrepo-{head1[:12]}")
        cfg = git("config", "--local", "--list")
        r = run("next", req, "--report", report2)
        check("next makes the new head's detached worktree and names it", r.returncode == 0 and os.path.isdir(wt)
              and f"at {wt}:" in r.stdout and git("worktree", "list").count(wt) == 1, (r.stderr, os.listdir(env["TMPDIR"])))
        check("...which wrote no branch and no config into the clone", git("config", "--local", "--list") == cfg
              and "detached" in git("worktree", "list", "--porcelain"))

        def hdr(sha: object, mode: str = "pinned") -> str:
            return "```agent-fabric-dispatch v1\n" + json.dumps({"evidence_mode": mode, "head_sha": sha}) + "\n```\n## Round\n"
        plain = os.path.join(evroot, f"myrepo-{base[:12]}")
        os.makedirs(plain)
        r = run("save", "8", "1", stdin=hdr(base))
        check("save leaves a directory that is not the expected worktree alone", r.returncode == 0 and os.path.isdir(plain)
              and "removed" not in r.stderr, r)
        # the case the guard protects: a registered worktree of the same repo at the path, checked out elsewhere
        def at(rev: str) -> None:
            subprocess.run(["git", "-C", wt, "checkout", "-q", "--detach", rev], env=env, check=True, capture_output=True, timeout=30)
        at(base)
        r = run("save", "8", "1", stdin=hdr(head1))
        check("save leaves a registered worktree of the repo that is at another commit, and says why",
              r.returncode == 0 and os.path.isdir(wt) and wt in git("worktree", "list") and "removed" not in r.stderr
              and f"left {wt}: not a worktree at {head1[:12]}" in r.stderr, r)
        at(head1)
        r = run("save", "8", "1", stdin=hdr(head1, "working-tree"))
        check("save removes nothing for a report that was not pinned, quietly", r.returncode == 0 and os.path.isdir(wt) and "left" not in r.stderr, r)
        r = run("save", "8", "1", stdin="## Round\n")
        check("...nor without a header", r.returncode == 0 and os.path.isdir(wt) and "left" not in r.stderr, r)
        r = run("save", "8", "1", stdin=hdr("../../etc"))
        check("...nor for a head_sha that is no commit id", r.returncode == 0 and os.path.isdir(wt), r)
        r = run("save", "8", "1", stdin=hdr(head1))
        check("save removes the round's worktree and says so", r.returncode == 0 and not os.path.exists(wt)
              and f"removed the head worktree {wt}" in r.stderr and wt not in git("worktree", "list"), r)
        r = run("save", "8", "2", stdin=hdr(head1))
        check("...and with nothing there it succeeds, naming the path it looked at",
              r.returncode == 0 and "removed" not in r.stderr and f"left {wt}: nothing there" in r.stderr, r)
        shutil.rmtree(plain)
        bad = os.path.join(tmp, "scratch", "BAD.json")
        with open(bad, "w") as f:
            json.dump({"mode": "review", "repository": repo, "range": f"{base[:12]}..{head1[:12]}",
                       "objective": "This fixes the PATH bug.", "requirements": ["It exists."]}, f)
        head3 = commit("moved on")
        listed = git("worktree", "list")
        r = run("next", bad, "--report", report2)
        check("next refuses a rationale-shaped objective and makes no worktree and no request",
              r.returncode == 1 and "objective" in r.stderr and not os.path.exists(os.path.join(evroot, f"myrepo-{head3[:12]}"))
              and git("worktree", "list") == listed and not os.path.exists(os.path.join(tmp, "scratch", "BAD-rr2.json")), (r, listed))

    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n{'all passed' if not fails else str(fails) + ' FAILED'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
