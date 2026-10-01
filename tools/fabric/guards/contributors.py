#!/usr/bin/env python3
"""tools/fabric/guards/contributors.py — the contributor carve-out
(agent-fabric ADR-018 §5 rule 8): a role policies/authority.json names under
`contributors` may commit, in agent-fabric itself, the paths its entry lists
and nothing its entry excludes, on a contributor branch of its own; the
coordinator folds that branch into its own pull request, unrebased, and
merges it.

One decision, three callers. The pre-commit and commit-msg hooks ask it
through `hook` with the staged paths and the live binding; the CI tripwire
(agent_fabric_dir_authority.py) imports `admitted` and asks it per commit
with the declared trailer. The hooks read authority.json as HEAD has it —
never the working tree or the index, where an uncommitted edit would widen
the entry for the commit it rides with — and CI reads the base's, so a
branch that edits the file is judged by what main says.

  contributors.py hook <fabric-root> <held-role>
    exit 0  every staged path is the held role's, on its contributor branch
    exit 1  the held role is a contributor and this commit is outside its
            entry, or not on its branch; the reason is on stderr
    exit 3  the held role is no contributor (silent: the caller refuses as
            it always did)

WHY A BRANCH SHAPE AT THE KEYBOARD ONLY. `<host>/<login>/for/<caller>/<what>`
is the supplier branch the team's rules name; it keeps a contributor's
commits off any branch that opens a PR of its own. CI cannot hold a commit to
a branch name — once folded, the commit is on the coordinator's branch — so
the shape is checked where the branch is readable, as the locale carve-out
holds the login to its suffix there and not in CI.
"""
from __future__ import annotations

import json
import subprocess
import sys

BRANCH_SEGMENT = "for"


def contributors_of(text: str) -> dict[str, dict]:
    """role -> entry, from an authority.json's text. An entry is kept only
    when its shape is whole (a role, a non-empty list of path strings, a list
    of exclusion strings): a half-written entry admits nothing rather than
    everything."""
    try:
        entries = json.loads(text).get("contributors") or []
    except (ValueError, AttributeError):
        return {}
    out: dict[str, dict] = {}
    if not isinstance(entries, list):
        return out
    for e in entries:
        if not isinstance(e, dict):
            continue
        role, paths, excl = e.get("role"), e.get("paths"), e.get("excluding", [])
        if not (isinstance(role, str) and role and isinstance(paths, list) and paths
                and all(isinstance(p, str) and p for p in paths)
                and isinstance(excl, list) and all(isinstance(p, str) and p for p in excl)):
            continue
        out[role] = {"paths": paths, "excluding": excl}
    return out


def _covers(rule: str, path: str) -> bool:
    # A rule ending in "/" is a directory and everything under it; any other
    # rule is one file. No globs: a pattern is where a widening hides.
    return path.startswith(rule) if rule.endswith("/") else path == rule


def outside(entry: dict, paths: list[str]) -> list[str]:
    """The paths this entry does not admit; every path when there are none
    to judge (an amend or an empty commit is not a contribution)."""
    if not paths:
        return ["(no path staged: an amend or an empty commit)"]
    return [p for p in paths
            if not any(_covers(r, p) for r in entry["paths"])
            or any(_covers(r, p) for r in entry["excluding"])]


def admitted(authority_text: str, role: str, paths: list[str]) -> bool:
    entry = contributors_of(authority_text).get(role)
    return bool(entry) and not outside(entry, paths)


def branch_problem(branch: str, login: str) -> str | None:
    parts = branch.split("/")
    if len(parts) >= 5 and parts[1] == login and parts[2] == BRANCH_SEGMENT and all(parts):
        return None
    return (f"branch '{branch or '(detached)'}' is not a contributor branch of {login}: "
            f"<host>/{login}/{BRANCH_SEGMENT}/<caller>/<what>")


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], capture_output=True, text=True, timeout=60)


def staged_paths() -> list[str]:
    """What this commit adds of its own. --no-renames, so a move out of a
    path the entry excludes shows its source as a deletion; in a merge, what
    the result changes over the merged-in side, as the locale carve-out
    judges a fold of main."""
    merge = _git("rev-parse", "-q", "--verify", "MERGE_HEAD").stdout.strip()
    r = _git("diff", "--cached", "--name-only", "--no-renames", *([merge] if merge else []))
    if r.returncode != 0:
        raise RuntimeError(f"git diff --cached failed: {r.stderr.strip()}")
    return [p for p in r.stdout.splitlines() if p]


def committed_authority() -> str:
    """policies/authority.json as HEAD has it, "" when HEAD has none. Never
    the working tree or the index: an unstaged edit widening the entry would
    admit the very commit it rides along with (review of #75). HEAD's copy
    changed only through a commit this fence judged, and CI reads the base's
    whatever HEAD says."""
    r = _git("show", "HEAD:policies/authority.json")
    return r.stdout if r.returncode == 0 else ""


def hook(fabric_root: str, held: str) -> int:
    # fabric_root is where the hooks live; the entry is the repository's own
    # committed one, which in agent-fabric itself is the same file.
    del fabric_root
    entry = contributors_of(committed_authority()).get(held)
    if not held or entry is None:
        return 3
    login = subprocess.run(["id", "-un"], capture_output=True, text=True, timeout=10).stdout.strip()
    branch = _git("symbolic-ref", "--short", "-q", "HEAD").stdout.strip()
    problems = []
    b = branch_problem(branch, login)
    if b:
        problems.append(b)
    bad = outside(entry, staged_paths())
    if bad:
        shown = " ".join(bad[:8]) + (f" … ({len(bad)} paths)" if len(bad) > 8 else "")
        problems.append(f"outside what {held} commits here: {shown}")
    if not problems:
        return 0
    print(f"{held} contributes to agent-fabric only on its own contributor branch, "
          "within its entry in policies/authority.json:", file=sys.stderr)
    for p in problems:
        print(f"  {p}", file=sys.stderr)
    print("  Anything else is proposed to fabric-coordinator (policies/AUTHORITY.md).", file=sys.stderr)
    return 1


def main(argv: list[str]) -> int:
    if len(argv) != 3 or argv[0] != "hook":
        print("usage: contributors.py hook <fabric-root> <held-role>", file=sys.stderr)
        return 2
    try:
        return hook(argv[1], argv[2])
    except (RuntimeError, subprocess.TimeoutExpired) as e:
        # A hook that cannot read what is staged refuses: exit 1, said.
        print(f"contributors: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
