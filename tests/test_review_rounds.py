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
REVIEW = os.path.join(HERE, "bin", "fabric-review")
GIT = {"GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null", "GIT_AUTHOR_NAME": "t",
       "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: object = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {detail}"))
        fails += not good

    tmp = tempfile.mkdtemp(prefix="test_review_rounds.")
    try:
        env = {k: v for k, v in os.environ.items() if not k.startswith(("AGENT_FABRIC_", "GITHUB_", "GIT_"))}
        env.update(GIT, AGENT_FABRIC_STATE_DIR=os.path.join(tmp, "state"), HOME=os.path.join(tmp, "home"))
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

        req = os.path.join(tmp, "scratch", "REQUEST.yaml")
        os.makedirs(os.path.dirname(req))
        with open(req, "w") as f:
            f.write(f"mode: review\nrepository: {repo}\nrange: {base[:12]}..{head1[:12]}\n"
                    "objective: >-\n  The thing exists.\nrequirements:\n  - It exists.\n"
                    "lenses:\n  - general\n  - security\n")

        print("save")
        r = run("save", "7", "1", stdin="## Round 1\n\n1. **P2:** a finding.\n")
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
        r = run("next", req, "--pr", "7", cwd=elsewhere)
        nxt_path = os.path.join(tmp, "scratch", "REQUEST-rr2.json")
        check("--pr finds the round by the request's repository, not the cwd's (review of #89)",
              r.returncode == 0, r.stderr)
        nxt = json.load(open(nxt_path)) if os.path.exists(nxt_path) else {}
        check("a moved head: REQUEST-rr2.json beside the request",
              r.returncode == 0 and os.path.isfile(nxt_path), r.stderr)
        check("…mode re-review, range old head..new head, the saved report as previous findings",
              nxt.get("mode") == "re-review" and nxt.get("range") == f"{head1[:12]}..{head2[:12]}"
              and nxt.get("previous_findings") == saved, nxt)
        check("…lenses narrowed to general, everything else carried",
              nxt.get("lenses") == ["general"] and nxt.get("requirements") == ["It exists."]
              and nxt.get("repository") == repo, nxt)
        check("…and the brief is rendered to stdout, the saved report in it",
              "## Mode\nre-review" in r.stdout and "a finding." in r.stdout, r.stdout[:300])
        head3 = commit("fix 2")
        report2 = os.path.join(tmp, "scratch", "report-2.md")
        with open(report2, "w") as f:
            f.write("## Round 2\n\nclean\n")
        r = run("next", nxt_path, "--report", report2, "--keep-lenses")
        nxt3 = json.load(open(os.path.join(tmp, "scratch", "REQUEST-rr3.json")))
        check("from a round's own request: REQUEST-rr3.json, range from that round's head, --report taken",
              r.returncode == 0 and nxt3["range"] == f"{head2[:12]}..{head3[:12]}"
              and nxt3["previous_findings"] == report2, (r.stderr, nxt3))
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
        check("a source request whose range does not validate: one line, exit 1, no traceback (review of #89)",
              r.returncode == 1 and "Traceback" not in r.stderr and "range" in r.stderr, r.stderr)
        r = run("next", req, "--pr", "8")
        check("a PR with no saved round is refused, naming save", r.returncode == 1 and "fabric-review save" in r.stderr,
              r.stderr)
        r = run("next", req)
        check("neither --report nor --pr: usage, exit 2", r.returncode == 2, r.stderr)
        r = run("next", req, "--pr", "7", "--head", "nonesuch")
        check("a --head that is no commit is refused", r.returncode == 1 and "not a commit" in r.stderr, r.stderr)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n{'all passed' if not fails else str(fails) + ' FAILED'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
