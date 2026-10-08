#!/usr/bin/env python3
"""tools/fabric/guards/contributors.py — the contributor carve-out
(agent-fabric ADR-018 §5 rule 8): a role policies/authority.json names under
`contributors` may commit, in agent-fabric itself, the paths its entry lists
and nothing its entry excludes, on a contributor branch of its own; the
coordinator folds that branch into its own pull request, unrebased, and
merges it — unless the entry carries `"merges": true`, when the role
may also open, review and merge its own pull request from a branch
`<host>/<login>/<type>/<what>` (the owner, 2026-10-07).

One decision, three callers. The pre-commit and commit-msg hooks ask it
through `hook` with the staged paths and the live binding; the CI tripwire
(agent_fabric_dir_authority.py) imports `admitted` and asks it per commit
with the declared trailer. The hooks read authority.json as HEAD has it —
never the working tree or the index, where an uncommitted edit would widen
the entry for the commit it rides with — and CI reads the base's, so a
branch that edits the file is judged by what main says.

  contributors.py hook <fabric-root> <held-role>
    exit 0  every staged path is the held role's, on its own branch (its
            for/ branch, or its own <type>/ branch when it merges)
    exit 1  the held role is a contributor and this commit is outside its
            entry, or not on its branch; the reason is on stderr
    exit 3  the held role is no contributor (silent: the caller refuses as
            it always did)

WHY THE COMMIT'S BRANCH AT THE KEYBOARD. `<host>/<login>/for/<caller>/<what>`
is the supplier branch the team's rules name. CI cannot hold a commit to the
branch it was made on — once folded, the commit is on the coordinator's
branch — so that shape is checked where the branch is readable, as the
locale carve-out holds the login to its suffix there. What CI does read is
the pull request's head branch (pull_request_problem): a for/ branch opens
no pull request, and a contributor-only pull request needs `merges`.
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
        merges = e.get("merges", False)
        if not (isinstance(role, str) and role and isinstance(paths, list) and paths
                and all(isinstance(p, str) and p for p in paths)
                and isinstance(excl, list) and all(isinstance(p, str) and p for p in excl)
                and isinstance(merges, bool)):
            continue
        out[role] = {"paths": paths, "excluding": excl, "merges": merges}
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


def branch_problem(branch: str, login: str, merges: bool = False) -> str | None:
    parts = branch.split("/")
    if len(parts) >= 5 and parts[1] == login and parts[2] == BRANCH_SEGMENT and all(parts):
        return None
    # A role that merges its own work also commits on its own PR branch,
    # four segments like every other agent's.
    if merges and len(parts) >= 4 and parts[1] == login and parts[2] != BRANCH_SEGMENT and all(parts):
        return None
    own = f" or <host>/{login}/<type>/<what>" if merges else ""
    return (f"branch '{branch or '(detached)'}' is not a contributor branch of {login}: "
            f"<host>/{login}/{BRANCH_SEGMENT}/<caller>/<what>{own}")


def merges_own(authority_text: str, role: str) -> bool:
    entry = contributors_of(authority_text).get(role)
    return bool(entry) and entry["merges"]


def pull_request_problem(authority_text: str, head_ref: str, declared: list[str], owner_role: str) -> str | None:
    """CI's half of the pull-request rule. A supply branch
    `<host>/<login>/for/<caller>/<what>` is folded, never opened as a pull
    request. A pull request in which no commit declares the owner role is
    a contributor's own: it passes when a role in it merges its own work
    (the folder), and otherwise each contributor role in it must. Which login holds which role is runtime state, never committed,
    so the commits' declared roles are what is judged: a tripwire, like the
    trailer it reads."""
    parts = head_ref.split("/")
    if len(parts) >= 5 and parts[2] == BRANCH_SEGMENT:
        return (f"'{head_ref}' is a supply branch: its caller folds it into its own pull request "
                "(ADR-018 §5 rule 8); it opens none")
    if not declared or owner_role in declared:
        return None
    entries = contributors_of(authority_text)
    # A role that merges its own work may fold another contributor's supply
    # into its pull request, as the owner role does: the folder is the one
    # that merges (a project's configs folded into python-dev's #116 were
    # refused when only the owner could fold). Each commit is still held to
    # its own entry by the path check.
    if any(r in entries and entries[r]["merges"] for r in declared):
        return None
    others = sorted({r for r in declared if r in entries and not entries[r]["merges"]})
    if others:
        return (f"no commit declares {owner_role} or a role that merges its own work, and {', '.join(others)} "
                "does not merge its own work (policies/authority.json `merges`): deliver a supply branch for "
                "a caller that merges to fold")
    return None


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], capture_output=True, text=True, timeout=60)


def _merge_heads() -> list[str]:
    path = _git("rev-parse", "--git-path", "MERGE_HEAD").stdout.strip()
    try:
        with open(path, encoding="utf-8") as f:
            return [line.split()[0] for line in f if line.strip()]
    except OSError:
        return []


def _changed_against(rev: str | None) -> set[str]:
    r = _git("diff", "--cached", "--name-only", "--no-renames", *([rev] if rev else []))
    if r.returncode != 0:
        raise RuntimeError(f"git diff --cached failed: {r.stderr.strip()}")
    return {p for p in r.stdout.splitlines() if p}


def staged_paths() -> list[str]:
    """What this commit adds of its own. --no-renames, so a move out of a
    path the entry excludes shows its source as a deletion. In a merge, what
    the result changes over EVERY parent: a path equal to one parent's came
    from that parent whole, and that commit was judged when it was made.
    Judged over the merged-in side alone, a contributor branch that had
    folded main and then merged an older branch of its own carried main's
    changes as the contributor's, and was refused (python-dev-01, seq 10894)."""
    merges = _merge_heads()
    if not merges:
        return sorted(_changed_against(None))
    own = _changed_against("HEAD")
    for rev in merges:
        own &= _changed_against(rev)
    return sorted(own)


def committed_authority() -> str:
    """policies/authority.json as HEAD has it, "" when HEAD has none. Never
    the working tree or the index: an unstaged edit widening the entry would
    admit the very commit it rides along with (review of #75). HEAD's copy
    can still differ from main's — a fold-only merge of a wider ref is not
    judged here — so this is the keyboard's fence; CI reads the base's."""
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
    b = branch_problem(branch, login, entry["merges"])
    if b:
        problems.append(b)
    staged = staged_paths()
    # A merge that adds nothing of its own (a clean fold) brings only
    # commits already judged; an empty list is otherwise an amend.
    bad = [] if not staged and _merge_heads() else outside(entry, staged)
    if bad:
        shown = " ".join(bad[:8]) + (f" … ({len(bad)} paths)" if len(bad) > 8 else "")
        problems.append(f"outside what {held} commits here: {shown}")
    if not problems:
        return 0
    print(f"{held} contributes to agent-fabric only on its own branch, "
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
