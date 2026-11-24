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
  branch_size.py ci                                      the pull request's range (GITHUB_EVENT_PATH), as ci() says
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
OWNER_WORD = re.compile(r'\d{4}-\d{2}-\d{2} +"[^"]*\S[^"]*"')  # fullmatch only
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
    return [r for r in rows if r.count > refuse_over and r.count > r.parent_count and not OWNER_WORD.fullmatch(r.owner_word)]


def count(base: str, heads: list[str], cwd: str | None = None) -> int:
    """Work commits reachable from any of `heads` and not from `base`: the count a commit with those parents starts from."""
    if not heads:
        return 0
    out = _git("log", "--no-merges", "--format=%(trailers:key=Kind,valueonly,separator=%x0a)%x1f"
               "%(trailers:key=Answers,valueonly,separator=%x20)%x1e", *heads, f"^{base}", cwd=cwd)
    n = 0
    for rec in out.split("\x1e"):
        if not rec.strip():
            continue
        kind, _, answers = rec.strip("\n").partition("\x1f")
        n += _work(kind, answers, False)
    return n


def _trailers(msg_path: str, cwd: str | None = None) -> list[tuple[str, str]]:
    out = _git("interpret-trailers", "--parse", msg_path, cwd=cwd)
    return [(k.strip().lower(), v.strip()) for k, sep, v in (t.partition(":") for t in out.splitlines()) if sep]


def hook(msg_path: str, amend: bool, merge_head: str = "", cwd: str | None = None) -> tuple[int, list[str]]:
    """The commit-msg hook's judgement of the commit being made, after the Kind: stamp: (1, why) to refuse, (0, lines to
    say) otherwise. Nothing to judge (no remote default branch, no HEAD yet, on the default branch itself): (0, [])."""
    base = default_base(cwd)
    try:
        head = _git("rev-parse", "--verify", "--quiet", "HEAD", cwd=cwd).strip()
    except RuntimeError:
        return 0, []
    if not base:
        return 0, []
    branch = _git("rev-parse", "--abbrev-ref", "HEAD", cwd=cwd).strip()
    if branch == base.rsplit("/", 1)[-1]:
        return 0, []
    if amend:
        heads = _git("rev-list", "--parents", "-n", "1", head, cwd=cwd).split()[1:]
    else:
        heads = [head] + ([merge_head] if merge_head else [])
    merging = len(heads) > 1
    pairs = _trailers(msg_path, cwd)
    kinds = [v for k, v in pairs if k == "kind"]
    work = not merging and _work("\n".join(kinds), " ".join(v for k, v in pairs if k == "answers"), False)
    before = count(base, heads[:1], cwd)
    after = count(base, heads, cwd) + work
    advice, refuse, src = thresholds(repository_of(cwd))
    words = [v for k, v in pairs if k == "owner-word"]
    if after > refuse and after > before and not (words and OWNER_WORD.fullmatch(words[-1])):
        return 1, [f"commit-msg: this commit takes the branch to {after} work commits, over commits.refuse_over {refuse} "
                   f"({src}). Land the branch first; past {refuse} a commit needs the owner's word in it, as a trailer",
                   "  Owner-Word: <YYYY-MM-DD> \"<the owner's words>\"",
                   "(agent-fabric ADR-019 §5 rule 4). A review fix (Answers:) is never refused."]
    if after >= advice:
        return 0, [f"commit-msg: the branch holds {after} work commits, at or over commits.advice_over {advice} ({src}): "
                   f"land it before adding more; past {refuse} each commit that adds work needs an Owner-Word: trailer "
                   f"(agent-fabric ADR-019 §5 rule 4)."]
    return 0, []


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


def ci(environ=os.environ) -> int:
    """CI's leg: the PR's range from the event payload, judged against the fleet's refuse_over as the BASE commit holds it,
    so a PR cannot raise its own limit. A workflow token cannot read a settings repository, so a repository's own
    override is the gate's to hold (ADR-019 §5 rule 4). No range: said, and passed, as the attribution guard does."""
    import ban_generated_by_attribution as attribution
    rng = attribution.resolve_range(environ)
    if rng is None:
        print("branch_size: no commit range to judge (not a pull request, or a shallow clone): NOT ENFORCED here")
        return 0
    base, head = rng
    top = _git("rev-parse", "--show-toplevel").strip()
    rel = os.path.relpath(roots.policy("arming.json", engine=top), top)
    try:
        doc = json.loads(_git("show", f"{base}:{rel}"))
        commits = doc.get("commits", {}) if isinstance(doc, dict) else {}
        pair = _pair({**FLEET, **{k: commits[k] for k in FLEET if k in commits}})
    except (RuntimeError, ValueError):
        pair = None
    refuse, src = (pair[1], f"{rel} at the base") if pair else (FLEET["refuse_over"], "built-in default")
    rows = walk(base, head)
    print(f"branch_size: {max((r.count for r in rows), default=0)} work commits in {base[:12]}..{head[:12]}, "
          f"refuse_over {refuse} ({src})")
    return check(base, head, refuse)


def main(argv: list[str]) -> int:
    if argv == ["ci"]:
        try:
            return ci()
        except RuntimeError as e:
            print(f"branch_size: {e}", file=sys.stderr)
            return 1
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
