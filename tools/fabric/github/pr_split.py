"""tools/fabric/github/pr_split.py — the work / fix / merge / netted split of a
pull request's commits: over origin/<base>..<head> before the arming, over
<merge>^1..<merge>^2 after the merge. Split out of pr_gate.py, unchanged;
commit_class is the one place the classification rule lives."""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import git  # noqa: E402
from github import commit_class  # noqa: E402
from github.pr_gate_base import succeeds  # noqa: E402


def count_commits(num: int, repo: str, base: str, head: str) -> dict | None:
    """The split of origin/<base>..<head>, or None when the clone cannot
    answer it. The classifier is commit_class, the one place the rule
    lives, so a measurement of the band after the fact reads the same
    split. The subjects counted as fix (and netted) are returned, so the
    split can be checked; the count rule is applied on it and a misread
    moves the band."""
    if not succeeds("cat-file", "-e", f"{head}^{{commit}}") \
            or not succeeds("rev-parse", "--verify", "-q", f"origin/{base}^{{commit}}"):
        return None
    return split_range(num, repo, f"origin/{base}..{head}", head, f"origin/{base}")


def merged_commits(num: int, repo: str, merge_commit: str) -> dict | None:
    """The split of a MERGED pull request's own commits, first parent the
    base and second its head, as the gate splits them before arming — or
    the band measured after the merge is not the band applied before it
    (pr-compliance's measure and this gate's merged row share it). None
    when the clone cannot answer: no merge commit recorded, one never
    fetched, or one with no second parent (a squash or rebase merge leaves
    a plain commit as GitHub's mergeCommit, so it lands here too)."""
    if not merge_commit:
        return None
    try:
        if not git.ok(".", "cat-file", "-e", f"{merge_commit}^{{commit}}") \
                or not git.ok(".", "rev-parse", "--verify", "-q", f"{merge_commit}^2"):
            return None
    except git.GitError:
        return None
    return split_range(num, repo, f"{merge_commit}^1..{merge_commit}^2", f"{merge_commit}^2",
                       f"{merge_commit}^1")


def split_range(num: int, repo: str, rev_range: str, head: str = "", base: str = "") -> dict:
    """The work / fix / merge / netted split of a range of PR #num's
    commits — the gate's before arming, and pr-compliance's after the
    merge (<merge>^1..<merge>^2), so the band is measured as it was
    applied. <head> is the range's tip: with it, a PR folded into it is
    read as one (commit_class.Folds), once per PR the range names; <base>
    is the range's base, and a PR whose head is already in it was folded
    into an earlier PR, not this one."""
    folded = commit_class.Folds(repo, head, base=base) if head else None
    # Kind: values joined by US (0x1f), never a tab or a newline, so the
    # line stays one record; commit_class.kind takes the last of them.
    r = git.run(".", "log", "--format=%H%x09%P%x09%s%x09%(trailers:key=Answers,valueonly,unfold,separator=%x20)"
                "%x09%(trailers:key=Kind,valueonly,unfold,separator=%x1f)",
                rev_range, check=False)
    shas, cls, subj = [], {}, {}
    for line in r.stdout.splitlines():
        fields = line.split("\t", 4) + [""] * 4
        sha, parents, subject, answers, kind = fields[:5]
        if not sha:
            continue
        shas.append(sha)
        cls[sha] = commit_class.classify(parents, subject, answers, str(num), repo, kind, folded)
        subj[sha] = subject
    # Two passes: classify each commit, then net out every revert whose
    # partner is in the range — the pair changes nothing and counts
    # nothing, in whichever column each of them fell. A COMMIT NETS ONCE.
    # git log lists newest first, so a chain "feat A; revert A; reapply A"
    # is walked reapply → revert: the reapply nets the revert, and the
    # revert — already netted — no longer nets A, which stays work: the
    # tree after the chain is the tree after A. Netting every pair a commit
    # belongs to counted the whole chain as nothing (review, 2026-09-20, F1).
    skip: set[str] = set()
    for sha in shas:
        if sha in skip:
            continue
        body = git.run(".", "log", "-1", "--format=%b", sha, check=False).stdout
        for target in commit_class.revert_targets(body):
            for other in shas:
                if other.startswith(target) and other != sha and other not in skip and sha not in skip:
                    skip.update((sha, other))
    c = {"work": 0, "fix": 0, "merge": 0, "netted": 0, "fix_subjects": [], "netted_subjects": []}
    for sha in shas:
        # F2: what was netted is printed like the fix subjects, so the
        # column whose misread moves the band can be checked by eye.
        if sha in skip:
            c["netted"] += 1
            c["netted_subjects"].append(subj[sha])
        elif cls[sha] == "merge":
            c["merge"] += 1
        elif cls[sha] == "fix":
            c["fix"] += 1
            c["fix_subjects"].append(subj[sha])
        else:
            c["work"] += 1
    return c
