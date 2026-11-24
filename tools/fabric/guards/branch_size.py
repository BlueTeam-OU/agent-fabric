#!/usr/bin/env python3
"""tools/fabric/guards/branch_size.py — how big a branch is, and how big it may grow (agent-fabric ADR-019 §5 rule 4,
A 2026-11-24). One definition of the count, read by the commit-msg hook, CI (`check` below), fabric-pr gate and the
session-start jobs line: none of them re-implements it.

THE COUNT at a commit is the work commits among its ancestors that are not on the default branch, folded commits
included. A commit is work by its declaration (rule 3): `Kind: work`; `Kind: review-fix`, or an `Answers:` trailer with
no Kind, is a fix; a merge is a merge; a commit that declares nothing is work. Rule 3's subject heuristics are not
read here: every commit made since the hook began stamping (2026-10-08) declares, and a guard that judged by subject
words would refuse or admit by guesswork. commit_class.py's "another PR's review fix is this PR's work" needs GitHub and
is the gate's refinement, not the branch's.

THE RULE. A commit whose count is over refuse_over AND over its first parent's (a work commit, or a merge that brings
work) carries `Owner-Word: <YYYY-MM-DD> "<the owner's words>"`. A fix and a merge that brings no work never need it.
Comparing with the first parent, not "every commit past the line", means a fold is judged once, at its merge: the
folded commits were made on another branch, where their own count was small.

THE THRESHOLDS (thresholds()): the repository's commits.advice_over and refuse_over as this account last read them from
GitHub (arm_policy.load writes cache_path(repo) after each read), else the fleet's operator/policies/arming.json, else
FLEET below. The hook makes no GitHub call: a commit must not wait on the network, and a copy one read old is the
owner's chosen trade (2026-11-24). Which source answered is always said.

CLI (CI's leg, and a by-hand check):
  branch_size.py check <base> <head> [--refuse-over N]   exit 1 and one line per commit lacking the trailer; 0 otherwise
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from typing import NamedTuple

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import roots  # noqa: E402
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(HERE))), "runtime"))
import identity  # noqa: E402  the state dir has one owner (ADR-003 rule 1)

# What a tree without commits.refuse_over in its arming.json gets: the owner's numbers of 2026-11-24.
FLEET = {"advice_over": 16, "refuse_over": 32}
OWNER_WORD = re.compile(r'^\d{4}-\d{2}-\d{2} +"[^"]*\S[^"]*"$')
REPO = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")


class Row(NamedTuple):
    sha: str
    count: int
    parent_count: int
    work: bool
    merge: bool
    owner_word: str


def _git(*args: str, cwd: str | None = None) -> str:
    out = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if out.returncode:
        raise RuntimeError(f"git {' '.join(args)}: {out.stderr.strip()}")
    return out.stdout


def cache_path(repository: str) -> str:
    """The account's copy of `repository`'s thresholds, as arm_policy.load last read them. Under the agent's state dir,
    never the tree: it is one account's reading, not policy."""
    if not (REPO.fullmatch(repository) and all(p not in (".", "..") for p in repository.split("/"))):
        raise ValueError(f"not an <owner>/<name>: {repository!r}")
    owner, name = repository.split("/")
    return os.path.join(identity.agent_state_dir(), "arming-cache", owner, name + ".json")


def _pair(doc: object) -> tuple[int, int] | None:
    """advice_over and refuse_over from a document that holds them, or None when either is not a whole number >= 1 or
    refuse_over is not above advice_over: a malformed copy is no source, and the next one answers."""
    if not isinstance(doc, dict):
        return None
    a, r = doc.get("advice_over"), doc.get("refuse_over")
    ok = all(isinstance(v, int) and not isinstance(v, bool) and v >= 1 for v in (a, r))
    return (a, r) if ok and r > a else None


def fleet(path: str | None = None) -> tuple[int, int, str]:
    path = path or roots.policy("arming.json")
    try:
        with open(path, encoding="utf-8") as f:
            commits = json.load(f).get("commits", {})
    except (OSError, ValueError, AttributeError):
        return FLEET["advice_over"], FLEET["refuse_over"], "built-in default (fleet policy unreadable)"
    merged = {**FLEET, **{k: commits[k] for k in FLEET if k in commits}}
    pair = _pair(merged)
    if pair is None:
        return FLEET["advice_over"], FLEET["refuse_over"], f"built-in default ({path} malformed)"
    return pair[0], pair[1], "fleet policy"


def thresholds(repository: str | None, fleet_path: str | None = None) -> tuple[int, int, str]:
    """(advice_over, refuse_over, source); source names the copy and when it was read, or the fleet."""
    if repository:
        try:
            path = cache_path(repository)
            with open(path, encoding="utf-8") as f:
                doc = json.load(f)
        except (ValueError, OSError):
            doc = None
        pair = _pair(doc)
        if pair is not None and doc.get("repository") == repository:
            return pair[0], pair[1], f"{repository}'s policy as read {doc.get('read_at', 'at an unknown time')}"
    a, r, src = fleet(fleet_path)
    return a, r, src + (f" (no copy of {repository}'s own read yet)" if repository else "")


def repository_of(cwd: str | None = None) -> str | None:
    """<owner>/<name> of the checkout's origin, as GitHub spells it; None for a remote that is not GitHub's."""
    try:
        url = _git("remote", "get-url", "origin", cwd=cwd).strip()
    except RuntimeError:
        return None
    m = re.search(r"github\.com[:/]+([^/]+/[^/]+?)(?:\.git)?/?$", url)
    return m.group(1) if m and REPO.fullmatch(m.group(1)) else None


def default_base(cwd: str | None = None) -> str | None:
    """origin's default branch as a ref, or None when the checkout has no remote-tracking default."""
    try:
        return _git("symbolic-ref", "--quiet", "refs/remotes/origin/HEAD", cwd=cwd).strip()
    except RuntimeError:
        pass
    for ref in ("refs/remotes/origin/main", "refs/remotes/origin/master"):
        try:
            _git("rev-parse", "--verify", "--quiet", ref, cwd=cwd)
            return ref
        except RuntimeError:
            continue
    return None


def _work(kind: str, answers: str, merge: bool) -> bool:
    if merge:
        return False
    kinds = [k.strip() for k in kind.splitlines() if k.strip() in ("work", "review-fix")]
    if kinds:
        return kinds[-1] == "work"
    return not answers.strip()


def walk(base: str, head: str = "HEAD", cwd: str | None = None) -> list[Row]:
    """Every commit of base..head, oldest first, with its count and its first parent's."""
    sep, end = "\x1f", "\x1e"
    fmt = sep.join(["%H", "%P", "%(trailers:key=Kind,valueonly,separator=%x0a)",
                    "%(trailers:key=Answers,valueonly,separator=%x20)",
                    "%(trailers:key=Owner-Word,valueonly,separator=%x0a)"]) + end
    out = _git("log", "--topo-order", "--reverse", f"--format={fmt}", f"{base}..{head}", cwd=cwd)
    commits: dict[str, tuple[list[str], bool, str]] = {}
    order: list[str] = []
    for rec in out.split(end):
        rec = rec.strip("\n")
        if not rec:
            continue
        sha, parents, kind, answers, word = (rec.split(sep) + [""] * 5)[:5]
        ps = parents.split()
        merge = len(ps) > 1
        commits[sha] = (ps, _work(kind, answers, merge), word.strip().splitlines()[-1].strip() if word.strip() else "")
        order.append(sha)
    # count(c) = |work commits in ancestors(c) ∩ range|; sets, since a fold shares ancestors with its integrator.
    seen: dict[str, frozenset[str]] = {}
    rows = []
    for sha in order:
        ps, work, word = commits[sha]
        anc: set[str] = set()
        for p in ps:
            anc |= seen.get(p, frozenset())
        if work:
            anc.add(sha)
        seen[sha] = frozenset(anc)
        first = len(seen.get(ps[0], frozenset())) if ps else 0
        rows.append(Row(sha, len(anc), first, work, len(ps) > 1, word))
    return rows


def offenders(rows: list[Row], refuse_over: int) -> list[Row]:
    """The commits over refuse_over, over their first parent, without a well-formed Owner-Word."""
    return [r for r in rows if r.count > refuse_over and r.count > r.parent_count and not OWNER_WORD.match(r.owner_word)]


def check(base: str, head: str, refuse_over: int | None = None, cwd: str | None = None) -> int:
    if refuse_over is None:
        _, refuse_over, src = fleet()
    else:
        src = "given"
    bad = offenders(walk(base, head, cwd=cwd), refuse_over)
    for r in bad:
        print(f"{r.sha[:12]}: work commit {r.count} of the branch, over commits.refuse_over {refuse_over} ({src}), "
              f"with no Owner-Word: <YYYY-MM-DD> \"<the owner's words>\" trailer (agent-fabric ADR-019 §5 rule 4)",
              file=sys.stderr)
    return 1 if bad else 0


def main(argv: list[str]) -> int:
    if len(argv) >= 3 and argv[0] == "check":
        n = None
        if len(argv) == 5 and argv[3] == "--refuse-over" and argv[4].isdigit():
            n = int(argv[4])
        elif len(argv) != 3:
            print("usage: branch_size.py check <base> <head> [--refuse-over N]", file=sys.stderr)
            return 2
        try:
            return check(argv[1], argv[2], n)
        except RuntimeError as e:
            print(f"branch_size: {e}", file=sys.stderr)
            return 1
    print("usage: branch_size.py check <base> <head> [--refuse-over N]", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
