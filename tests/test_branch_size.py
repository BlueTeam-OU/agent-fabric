#!/usr/bin/env python3
"""tools/fabric/guards/branch_size.py: the branch count and the Owner-Word rule of agent-fabric ADR-019 §5 rule 4
(A 2026-11-24), on throwaway repositories, and where the thresholds come from."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools", "fabric", "guards"))
import branch_size  # noqa: E402

ENV = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
       "GIT_COMMITTER_EMAIL": "t@t", "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}


def git(repo: str, *args: str) -> str:
    return subprocess.run(["git", "-C", repo, *args], env=ENV, check=True, capture_output=True, text=True).stdout.strip()


def commit(repo: str, subject: str, *trailers: str) -> str:
    msg = subject + ("\n\n" + "\n".join(trailers) if trailers else "")
    git(repo, "commit", "-q", "--allow-empty", "--no-verify", "-m", msg)
    return git(repo, "rev-parse", "HEAD")


def repo() -> str:
    d = tempfile.mkdtemp(prefix="branch-size-")
    git(d, "init", "-q", "-b", "main")
    commit(d, "root", "Kind: work")
    git(d, "switch", "-q", "-c", "feat")
    return d


def cases() -> list[tuple[str, bool]]:
    out = []
    r = repo()
    for i in range(3):
        commit(r, f"w{i}", "Kind: work")
    commit(r, "fix", "Answers: F1", "Kind: review-fix")
    commit(r, "answers only", "Answers: F2")
    commit(r, "undeclared")
    rows = branch_size.walk("main", "HEAD", cwd=r)
    out.append(("work, a fix, an Answers-only fix and an undeclared commit count 3,3,3,4 at the end",
                [x.count for x in rows] == [1, 2, 3, 3, 3, 4]))
    out.append(("under refuse_over nothing is an offender", branch_size.offenders(rows, 4) == []))
    bad = branch_size.offenders(rows, 2)
    out.append(("past refuse_over the work commits are offenders, the fixes never",
                [x.count for x in bad] == [3, 4] and all(x.work for x in bad)))

    r = repo()
    commit(r, "w1", "Kind: work")
    commit(r, "w2", "Kind: work", 'Owner-Word: 2026-11-24 "go on"')
    rows = branch_size.walk("main", "HEAD", cwd=r)
    out.append(("an Owner-Word trailer admits the commit", branch_size.offenders(rows, 1) == []))
    commit(r, "w3", "Kind: work", "Owner-Word: yes")
    rows = branch_size.walk("main", "HEAD", cwd=r)
    out.append(("a malformed Owner-Word does not", [x.count for x in branch_size.offenders(rows, 1)] == [3]))

    # A fold: a contributor's branch of 3 work commits merged into an integrator's branch of 2.
    r = repo()
    commit(r, "i1", "Kind: work")
    commit(r, "i2", "Kind: work")
    git(r, "switch", "-q", "-c", "supply", "main")
    for i in range(3):
        commit(r, f"s{i}", "Kind: work")
    git(r, "switch", "-q", "feat")
    git(r, "merge", "-q", "--no-ff", "--no-verify", "-m", "fold supply", "supply")
    rows = branch_size.walk("main", "HEAD", cwd=r)
    merge = rows[-1]
    out.append(("a fold counts its commits at its merge", merge.merge and merge.count == 5 and merge.parent_count == 2))
    bad = branch_size.offenders(rows, 4)
    out.append(("a fold that crosses refuse_over is judged once, at its merge", [x.sha for x in bad] == [merge.sha]))
    git(r, "commit", "-q", "--amend", "--no-verify", "-m", 'fold supply\n\nOwner-Word: 2026-11-24 "fold it"')
    out.append(("the merge's Owner-Word admits the fold",
                branch_size.offenders(branch_size.walk("main", "HEAD", cwd=r), 4) == []))
    commit(r, "after", "Answers: F1", "Kind: review-fix")
    out.append(("a review fix past the line is never refused",
                branch_size.offenders(branch_size.walk("main", "HEAD", cwd=r), 4) == []))
    out.append(("check() exits 1 on an offender and 0 without",
                branch_size.check("main", "HEAD", 1, cwd=r) == 1 and branch_size.check("main", "HEAD", 9, cwd=r) == 0))

    # Thresholds: the account's copy first, then the fleet file, then the built-in default.
    state = tempfile.mkdtemp(prefix="branch-size-state-")
    fleet = os.path.join(state, "arming.json")
    with open(fleet, "w") as f:
        json.dump({"commits": {"advice_over": 10, "refuse_over": 20}}, f)
    old = os.environ.get("AGENT_FABRIC_STATE_DIR")
    os.environ["AGENT_FABRIC_STATE_DIR"] = state
    try:
        a, rr, src = branch_size.thresholds("o/r", fleet)
        out.append(("no copy: the fleet file, said so", (a, rr) == (10, 20) and "no copy" in src))
        path = branch_size.cache_path("o/r")
        os.makedirs(os.path.dirname(path))
        with open(path, "w") as f:
            json.dump({"repository": "o/r", "read_at": "2026-11-24T00:00:00Z", "advice_over": 5, "refuse_over": 7}, f)
        a, rr, src = branch_size.thresholds("o/r", fleet)
        out.append(("a copy answers with its read time", (a, rr) == (5, 7) and "2026-11-24" in src))
        with open(path, "w") as f:
            json.dump({"repository": "o/r", "advice_over": 7, "refuse_over": 7}, f)
        out.append(("a copy with refuse_over not above advice_over is no source",
                    branch_size.thresholds("o/r", fleet)[:2] == (10, 20)))
        with open(fleet, "w") as f:
            json.dump({"commits": {"advice_over": 16}}, f)
        out.append(("a fleet file without refuse_over gets the built-in 32", branch_size.fleet(fleet)[:2] == (16, 32)))
        out.append(("an unreadable fleet file gets the built-in default, said so",
                    "unreadable" in branch_size.fleet(os.path.join(state, "none.json"))[2]))
    finally:
        if old is None:
            os.environ.pop("AGENT_FABRIC_STATE_DIR", None)
        else:
            os.environ["AGENT_FABRIC_STATE_DIR"] = old
    for bad_name in ("../x", "o/..", "o"):
        try:
            branch_size.cache_path(bad_name)
            out.append((f"cache_path refuses {bad_name!r}", False))
        except ValueError:
            out.append((f"cache_path refuses {bad_name!r}", True))
    return out


def main() -> int:
    results = cases()
    fails = sum(not ok for _, ok in results)
    for label, ok in results:
        print(f"  {'ok  ' if ok else 'FAIL'} {label}")
    print(f"{len(results) - fails}/{len(results)} passed")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
