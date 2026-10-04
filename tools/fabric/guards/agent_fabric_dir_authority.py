#!/usr/bin/env python3
"""tools/fabric/guards/agent_fabric_dir_authority.py — `.agent-fabric/` is
written by the fabric-coordinator ROLE (ADR-040 Wave 2;
policies/check_agent_fabric_dir_authority.sh is its shim).

CONTRACT, frozen from the bash (ADR-040 §5 rule 3):
  argv      none; extra arguments are ignored, as the bash ignored them
  cwd       anywhere inside the repository to check; the guard works at its
            toplevel
  env       AGENT_FABRIC_CHARTER_BASE (the base ref, tried first),
            GITHUB_BASE_REF (origin/<it>, <it>, then one shallow fetch of it),
            AGENT_FABRIC_ROOT (where to find policies/authority.json when the
            repository has none; default <toplevel>/../agent-fabric)
  stdin     not read
  stdout    every verdict that is not a failure: OK, not enforced, and one
            line per commit a carve-out admitted
  stderr    the failure (`FAIL: ...`, the commits, the reason); a refusal to
            examine, prefixed `check_agent_fabric_dir_authority: `
  exit      0 nothing under .agent-fabric/ changed, or every such commit
            declares the role, or no base ref is resolvable (not a violation)
            1 a commit changed .agent-fabric/ without declaring the role
            2 invocation problem (cannot reach the repo root) — and, where the
            bash passed silently, a guard that could not read: git missing,
            a rev-list that failed on a base it had resolved, a git call that
            timed out

`.agent-fabric/` in a repository is written by the fabric-coordinator
ROLE. It holds the project's distilled knowledge (`memory/<role>/`,
written by the drain) and nothing another role may edit by hand: a
`backend-dev` session that changes a slice is asserting something about
the system with no evidence behind it, outside the role that owns the
corpus. This fails when a commit that changes `.agent-fabric/` does not
declare that role.

THE ROLE, NOT THE LOGIN. Which account committed is irrelevant; what
matters is whether the session had the role BOUND when it committed.
That binding is machine-local (runtime/identity.py), and the one place
it can be checked for real is the keyboard: policies/githooks/pre-commit
refuses the commit unless the binding holds the role, and commit-msg
then writes what it verified into the message as a trailer:

    Fabric-Role: fabric-coordinator

This check reads that trailer on every commit the branch adds that
touches `.agent-fabric/**`. In CI it is a TRIPWIRE: the trailer is
text anyone can type, so it stops the accident — a session that never
bound the role and never ran the hooks — and makes a deliberate change
visible in review; it does not stop a session that means to route
around it. The same limit check_charter_authority.sh states for the
branch name. A merge commit is judged on what it changes itself — where
its tree differs from the clean three-way merge of its parents
(merge_own_change) — so a fold of main passes and a hand edit carried in
a merge does not.

RUNS IN ANY REPOSITORY. In agent-fabric ITSELF — recognised by
policies/authority.json at the toplevel — EVERY commit the branch adds
must declare the role: the control plane is read-only for every other
role (CLAUDE.md, policies/AUTHORITY.md). In a managed project only the
commits touching `.agent-fabric/**` must. The role name comes from
policies/authority.json when this repository has one, else from
$AGENT_FABRIC_ROOT/policies/authority.json, else it is
fabric-coordinator.

guards: .agent-fabric/**
guards: ** (in agent-fabric itself)

  0  also when no base ref is resolvable (not a violation)

THE TRAILER IS READ THE WAY THE BASH READ IT: `git interpret-trailers
--parse` over the commit's message, then the LAST line whose key, split at
the first `:` and the spaces after it (awk -F': *'), is `fabric-role` in any
case; its value is what lies up to the NEXT colon, spaces kept on the right.
So `Fabric-Role: a:b` declares `a`, and `Fabric-Role: fabric-coordinator ` (a
trailing space) declares something else. Replicated, not fixed.

THE OWNER ROLE IS THE BASE'S. In agent-fabric itself the role's name is
read from policies/authority.json as the base has it, as the charter guard
reads its holders: read from the working tree, as the bash did, a branch
that edited that file named its own owner for this check. A managed
project has no such file of its own, and reads the fabric's.

WHAT DIFFERS FROM THE BASH, on purpose, each the direction of a refusal: the
git failures named under `exit` above; a `role` that is not a non-empty
string is skipped, as an empty one was (the bash printed `None` or a list's
repr and required the trailer to spell that).
"""
from __future__ import annotations

import os
import re
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import git  # noqa: E402
from guards import common, contributors  # noqa: E402
from guards.common import Refused, err, say  # noqa: E402

NAME = "check_agent_fabric_dir_authority"

# policies/githooks/locale-carve-out.sh's pattern, which the hooks (bash, and
# staying bash) source; tests/test_agent_fabric_dir_authority.py reads that
# file and fails if the two drift.
LOCALE_PATH = re.compile(r"identities/roles/([a-z][a-z0-9-]*)/locale/([a-z][a-z0-9-]*)/[^/]+")

WORKFLOWS = ".github/workflows/"

REFUSAL = """
agent-fabric is read-only for every role but {role} — except a
locale's translations, identities/roles/<role>/locale/<suffix>/, which
the holder of <role> commits declaring its own role, and a contributor
role's entry in policies/authority.json (`contributors`); in a managed
project, .agent-fabric/ (the project's distilled knowledge) is. A commit
there is made with that role bound (bin/fabric-role bind {role},
from a login shell, then a relaunch) and the
agent-fabric git hooks installed (bootstrap.sh sets core.hooksPath): the
pre-commit hook checks the binding, the commit-msg hook records it as
the Fabric-Role trailer this check reads. The login that committed is
irrelevant. A wrong slice is corrected at the memory it was drained
from, or by a memory of the same class carrying merge_target with the
stale section's heading; the next drain puts it in place — never a hand
edit.
See agent-fabric policies/AUTHORITY.md."""


def locale_carve_out_role(paths: list[str]) -> tuple[str, str] | None:
    """Do these paths fall, all of them, under one locale's translations:
    identities/roles/<role>/locale/<suffix>/? (role, suffix) when they do;
    None for any other path, two roles, two suffixes, a path deeper than the
    locale directory, or no path at all."""
    found: tuple[str, str] | None = None
    for p in paths:
        m = LOCALE_PATH.fullmatch(p)
        if not m:
            return None
        if found is None:
            found = (m.group(1), m.group(2))
        elif found != (m.group(1), m.group(2)):
            return None
    return found


def declared_role(message: str, interpreted: str) -> str:
    """The Fabric-Role a commit declares, from `git interpret-trailers
    --parse`'s output for its message; "" when none."""
    declared = ""
    for line in common.lines_of(interpreted):
        fields = re.split(": *", line)
        if fields[0].lower() == "fabric-role" and len(fields) > 1:
            declared = fields[1]
    return declared


def is_fabric_itself(top: str, base: str) -> bool:
    """Whether this is agent-fabric itself, where every commit is guarded.
    Either side's policies/authority.json says so: read from the working
    tree alone, as the bash did, a branch that deleted the file narrowed the
    check to .agent-fabric/** and its other commits passed with no trailer
    (review of #72). A git that cannot say reads as the stricter scope."""
    if os.path.isfile(os.path.join(top, "policies", "authority.json")):
        return True
    try:
        r = git.run(top, "cat-file", "-e", f"{base}:policies/authority.json", check=False)
    except git.GitError:
        return True
    return r.returncode == 0


def owner_role_of(top: str, env: dict[str, str], base: str) -> str:
    if is_fabric_itself(top, base):
        # agent-fabric itself: the base's file, never the branch's.
        shown = git.run(top, "show", f"{base}:policies/authority.json", check=False)
        role = common.role_of(shown.stdout) if shown.returncode == 0 else None
        return role or common.DEFAULT_ROLE
    for f in (os.path.join(env.get("AGENT_FABRIC_ROOT") or os.path.join(top, "..", "agent-fabric"),
                           "policies", "authority.json"),):
        if not os.path.isfile(f):
            continue
        try:
            with open(f, encoding="utf-8", errors="surrogateescape") as fh:
                role = common.role_of(fh.read())
        except OSError:
            continue
        if role:
            return role
    return common.DEFAULT_ROLE


def base_authority(top: str, base: str) -> str:
    """The base's policies/authority.json, "" when it has none: what a
    branch may do is what main says, never what the branch wrote."""
    shown = git.run(top, "show", f"{base}:policies/authority.json", check=False)
    return shown.stdout if shown.returncode == 0 else ""


def commits_to_examine(top: str, base: str) -> tuple[str, list[str]]:
    if is_fabric_itself(top, base):
        scope, args = "agent-fabric itself", ["rev-list", "--no-merges", f"{base}..HEAD"]
    else:
        scope, args = ".agent-fabric/", ["rev-list", "--no-merges", f"{base}..HEAD", "--", ".agent-fabric/**"]
    r = git.run(top, *args, check=False)
    if r.returncode != 0:
        lines = [l for l in r.stderr.strip().splitlines() if l.strip()]
        raise Refused(f"cannot list {base}..HEAD ({(lines or [f'exit {r.returncode}'])[-1]}) — "
                      "a change under .agent-fabric/ could pass unexamined")
    return scope, common.lines_of(r.stdout)


def merge_own_change(top: str, commit: str, prefix: str) -> list[str]:
    """The paths a merge commit changes ITSELF: where its tree differs from
    the clean three-way merge of its parents (git merge-tree --write-tree),
    under the guarded prefix. A fold of main changes nothing, even when both
    sides moved the guarded tree; a conflict resolution or a hand edit is
    exactly the paths it touched. The commit hook judges a merge the same
    way (policies/githooks/guarded-change.sh); the two must agree. An
    octopus merge, or a merge-tree that cannot run, counts everything the
    merge changes against its first parent: judged, never waved through."""
    scope = ["--", prefix] if prefix else []
    parents = git.run(top, "rev-parse", f"{commit}^@", check=False).stdout.split()
    clean = ""
    if len(parents) == 2:
        r = git.run(top, "merge-tree", "--write-tree", parents[0], parents[1], check=False)
        if r.returncode in (0, 1):   # 1: conflicts; the tree still carries every clean path
            head = (r.stdout.splitlines() or [""])[0].strip()
            clean = head if re.fullmatch(r"[0-9a-f]{40,64}", head) else ""
    against = clean or (parents[0] if parents else "")
    if not against:
        return ["(a merge with no parent to compare)"]
    return common.lines_of(git.run(top, "diff", "--name-only", against, commit, *scope, check=False).stdout)


def merges_to_examine(top: str, base: str) -> list[str]:
    r = git.run(top, "rev-list", "--merges", f"{base}..HEAD", check=False)
    if r.returncode != 0:
        lines = [l for l in r.stderr.strip().splitlines() if l.strip()]
        raise Refused(f"cannot list the merges in {base}..HEAD ({(lines or [f'exit {r.returncode}'])[-1]}) — "
                      "a change under .agent-fabric/ could pass unexamined")
    return common.lines_of(r.stdout)


def log1(top: str, commit: str, fmt: str) -> str:
    """One field of a commit, as `$(git log -1 --format=...)` has it: only
    trailing newlines stripped."""
    return git.run(top, "log", "-1", f"--format={fmt}", commit).stdout.rstrip("\n")


def run(env: dict[str, str]) -> int:
    top = git.toplevel(os.getcwd())
    if not top:
        err("check_agent_fabric_dir_authority: not inside a git repository")
        return 2

    base = common.resolve_base(top, env)
    if base is None:
        say("check_agent_fabric_dir_authority: NOT ENFORCED — no base ref to diff")
        say("against (shallow checkout with no GITHUB_BASE_REF). A change under")
        say(".agent-fabric/ would pass unexamined here.")
        return 0

    owner_role = owner_role_of(top, env, base)
    scope, commits = commits_to_examine(top, base)
    # A merge is judged on what it changes itself (merge_own_change); one
    # that only folds its parents' guarded changes is not a change at all.
    # Until 2026-10-04 merges were skipped whole, so a hand edit carried in
    # a merge (a conflict resolution, a --no-verify commit) passed unseen.
    prefix = "" if is_fabric_itself(top, base) else ".agent-fabric/"
    own: dict[str, list[str]] = {}
    for m in merges_to_examine(top, base):
        changed = merge_own_change(top, m, prefix)
        if changed:
            own[m] = changed
    commits = commits + list(own)
    if not commits:
        say(f"check_agent_fabric_dir_authority: OK — no commit changes {scope}.")
        return 0

    # The locale carve-out (policies/AUTHORITY.md): a commit that changes
    # nothing but identities/roles/<role>/locale/<suffix>/ may declare
    # Fabric-Role: <role> — the holder of the role a locale translates writes
    # its translations. The login is not visible here; the pre-commit hook
    # held it to the suffix at the keyboard.
    fabric_itself = scope == "agent-fabric itself"
    authority = base_authority(top, base) if fabric_itself else ""
    bad: list[str] = []
    for c in commits:
        message = git.run(top, "log", "-1", "--format=%B", c).stdout
        declared = declared_role(message, git.run(top, "interpret-trailers", "--parse", input=message).stdout)
        if declared == owner_role:
            continue
        touched = own[c] if c in own else common.lines_of(
            git.run(top, "diff-tree", "--no-commit-id", "--name-only", "-r", c, check=False).stdout)
        locale = locale_carve_out_role(touched)
        if locale and declared == locale[0]:
            say(f"check_agent_fabric_dir_authority: {log1(top, c, '%h')} changes only "
                f"identities/roles/{locale[0]}/locale/{locale[1]}/, declaring Fabric-Role: {locale[0]} "
                "— the locale carve-out.")
            continue
        # The contributor carve-out (ADR-018 §5 rule 8), in agent-fabric
        # itself only — never .agent-fabric/ in a project, which is the
        # drain's: a role the BASE's authority.json names under
        # `contributors`, within its entry's paths. The branch shape was held
        # at the keyboard; folded into the coordinator's branch it is not
        # visible here.
        if fabric_itself and declared and contributors.admitted(authority, declared, touched):
            say(f"check_agent_fabric_dir_authority: {log1(top, c, '%h')} declares Fabric-Role: {declared} "
                "and stays within its contributor entry — the contributor carve-out.")
            continue
        # The Dependabot carve-out: Dependabot bumps the SHA-pinned actions
        # (.github/dependabot.yml) and can carry no trailer. Its commit may
        # change nothing but .github/workflows/; fabric-coordinator reviews
        # and merges the PR. The author name is text, so like the trailer
        # this is a tripwire, not a proof.
        if log1(top, c, "%an") == "dependabot[bot]" and touched \
                and all(p.startswith(WORKFLOWS) for p in touched):
            say(f"check_agent_fabric_dir_authority: {log1(top, c, '%h')} is Dependabot's and changes only "
                ".github/workflows/ — the action-pin carve-out.")
            continue
        bad.append(f"{log1(top, c, '%h %s')}  [Fabric-Role: {declared or 'none'}]")

    if not bad:
        say(f"check_agent_fabric_dir_authority: OK — {len(commits)} commit(s) change {scope}, "
            f"each declaring Fabric-Role: {owner_role}.")
        return 0

    err(f"FAIL: {scope} changed in {len(bad)} commit(s) that do not declare Fabric-Role: {owner_role}.")
    for b in bad:
        err(f"       {b}")
    err(REFUSAL.format(role=owner_role))
    return 1


def main() -> int:
    return common.run_main(NAME, lambda: run(dict(os.environ)))


if __name__ == "__main__":
    sys.exit(main())
