#!/usr/bin/env python3
"""tools/fabric/guards/charter_authority.py — a role's DEFINITION is
fabric-coordinator's to change (ADR-040 Wave 2; policies/check_charter_authority.sh
is its shim).

CONTRACT, frozen from the bash (ADR-040 §5 rule 3):
  argv      none. Extra arguments are ignored, as the bash ignored them. The
            shim passes the repository root (its own directory's parent) as
            the module's first argument, because the oracle runs a COPY of
            the shim inside a scratch repository; run by hand, the module
            uses the repository it lives in.
  env       AGENT_FABRIC_CHARTER_BASE (the base ref, tried first),
            GITHUB_BASE_REF (origin/<it>, <it>, then one shallow fetch of it),
            AGENT_FABRIC_CHARTER_BRANCH, GITHUB_HEAD_REF (the head branch,
            in that order; else the checked-out branch)
  stdin     not read
  stdout    every verdict that is not a failure: OK, or not enforced
  stderr    the failure (`FAIL: ...`, the files, the reason); a refusal to
            examine, prefixed `check_charter_authority: `
  exit      0 no protected file changed, or the branch is fabric-coordinator's,
            or the head branch is not knowable in this context, or no base ref
            is resolvable
            1 a protected file changed on another role's branch
            2 invocation problem (cannot reach the repo root) — and, where the
            bash passed silently, a guard that could not read: git missing,
            a diff that failed on a base it had resolved (a shallow clone
            with no merge base said "OK — no role definition changed"), a
            git call that timed out

A role's DEFINITION is fabric-coordinator's to change: `identities/roles/*/
charter.md` and `brief.md`, the catalogue `identities/roles/catalog.json`, the
per-project binding rules `.agent-fabric/taxonomy.json` (this repository's own; a
managed project's is under the .agent-fabric/ guard), the routing policy
`routing/policies/*` and `policies/authority.json` itself. This fails
when one of those changes on a branch that is not a fabric-coordinator
branch.

AUTHORITY BELONGS TO THE ROLE, NOT TO THE ACCOUNT. The branch's second
segment names the agent (Linux login) that opened it. The check asks
whether that agent is a recognised holder of fabric-coordinator: named
in policies/authority.json, or named FOR the role by the provisioning
convention (fabric-coordinator, fabric-coordinator-02). An account
currently HOLDING some other role does not thereby own that role's
definition — that is exactly the widening this tripwire exists to catch.

WHY THIS EXISTS. Every distilled slice is generated -- the
assembler writes it and lint.py rejects a hand-edit -- so a role's scope
cannot drift by accident. `charter`, `brief` and `recall` are the classes
lint.py exempts from `derived_from`, precisely because they are authored
rather than distilled. That exemption is what makes charter.md (and the
brief beside it, read to every session at launch) the one
place a session can quietly widen its own remit, and it lints clean:
lint checks PROVENANCE, and this is a question of AUTHORITY.

WHAT THIS CANNOT DO, stated plainly so nobody mistakes it for a fence.
Every session pushes as the same GitHub account, so there is no identity
to check -- CODEOWNERS cannot tell one session from another here. All
that is available is the branch name, which is self-declared. This is a
TRIPWIRE: it stops the accident and the absent-minded edit, and it makes
a deliberate change visible in review. A session that means to route
around it can, by naming its branch differently, and nothing available
in this repository would catch that.

It also only enforces where a head branch is knowable. On a `merge_group`
run the ref is the queue's synthetic branch, so the check reports and
passes -- the `pull_request` run is where it bites, and that run is
required before anything is queued.

guards: identities/**
guards: .agent-fabric/taxonomy.json
guards: routing/policies/**
guards: policies/**

  0  also when no base ref is resolvable -- an environment that cannot
     show a diff is not a violation, and failing there would block every
     PR rather than the one changing a charter

WHAT DIFFERS FROM THE BASH, on purpose, each the direction of a refusal
(a failure to read is a refusal, never a silent pass): the git failures
named under `exit` above; a `holders` that is not a list of strings, or an
entry that is not a string, names nobody (the bash joined a string into its
characters, split an entry on spaces and expanded `*` against the working
directory); a `role` that is empty or not a string is the default,
fabric-coordinator (an empty one made `$agent == ""*` true for everybody).
REPLICATED, though it reads as a defect: the role's name is a PREFIX match,
so an account named fabric-coordinatorX is a holder, as is one named
fabric-coordinator-02.
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import git  # noqa: E402
from guards import common  # noqa: E402
from guards.common import Refused, err, say  # noqa: E402

NAME = "check_charter_authority"

# :(glob) so `*` stays inside one directory: git's default pathspec `*`
# crosses `/`, and matched identities/roles/<role>/locale/<suffix>/charter.md
# — a translation the locale's holder commits under the carve-out
# (policies/AUTHORITY.md), which the .agent-fabric/ tripwire and the hooks
# judge. Judged here too, every locale PR failed CI (#57 blind review F1).
PROTECTED = (':(glob)identities/roles/*/charter.md', ':(glob)identities/roles/*/brief.md',
             'identities/roles/catalog.json', '.agent-fabric/taxonomy.json', 'projects/*/taxonomy.json',
             'routing/policies/*', 'policies/authority.json')

REFUSAL = """
`identities/roles/*/charter.md`, the role catalogue, a project's
taxonomy, the routing policies and policies/authority.json say what a
role is and is not, where it applies, and who may change that. They are
fabric-coordinator's to change (policies/AUTHORITY.md) -- a role does not
redefine itself, and holding a role is not owning its definition.

Propose it instead: open a PR touching only the definition, say what the
role is being asked to take on or give up, and leave it for
fabric-coordinator. Do not self-approve on the grounds that you are the
only session that understands the surface; that is the argument this
exists to refuse."""


def head_branch(repo: str, env: dict[str, str]) -> str:
    # GITHUB_HEAD_REF is set on pull_request and empty elsewhere; fall back to
    # the local branch so this is runnable by hand before pushing.
    branch = env.get("AGENT_FABRIC_CHARTER_BRANCH") or env.get("GITHUB_HEAD_REF") or ""
    if branch:
        return branch
    # `rev-parse --abbrev-ref HEAD || echo ""`: in a repository with no commit
    # git prints HEAD and fails, and the bash kept what it printed.
    return git.run(repo, "rev-parse", "--abbrev-ref", "HEAD", check=False).stdout.rstrip("\n")


def agent_of(branch: str) -> str | None:
    """`<host>/<agent>/<type>/<desc>`: the second segment names the agent (the
    Linux login) that opened the branch, which is the only signal available.
    None when the branch has fewer than three segments or an empty second."""
    # `cut -d/ -f2` per line: a line with no slash comes out whole.
    cut = "\n".join(l.split("/")[1] if "/" in l else l for l in branch.split("\n")).rstrip("\n")
    if branch.count("/") < 2 or not cut:
        return None
    return cut


def holders_of(text: str) -> list[str]:
    """Holders: the committed list. Only a list of strings counts."""
    try:
        listed = (json.loads(text).get("role_definitions") or {}).get("holders") or []
    except (ValueError, AttributeError):
        return []
    return listed if isinstance(listed, list) and all(isinstance(h, str) for h in listed) else []


def is_holder(agent: str, holders: list[str], owner_role: str) -> bool:
    return agent in holders or agent.startswith(owner_role)


def changed_paths(repo: str, base: str) -> list[str]:
    r = git.run(repo, "diff", "--name-only", f"{base}...HEAD", "--", *PROTECTED, check=False)
    if r.returncode != 0:
        lines = [l for l in r.stderr.strip().splitlines() if l.strip()]
        raise Refused(f"cannot diff {base}...HEAD ({(lines or [f'exit {r.returncode}'])[-1]}) — "
                      "a change to a role definition could pass unexamined")
    return common.lines_of(r.stdout)


def listing(paths: list[str], indent: str, to_err: bool = False) -> None:
    for p in paths:
        (err if to_err else say)(f"{indent}{p}")


def run(argv: list[str], env: dict[str, str]) -> int:
    root = os.path.abspath(argv[0]) if argv else os.path.dirname(os.path.dirname(HERE))
    if not os.path.isdir(root):
        err("cannot cd to repo root")
        return 2

    base = common.resolve_base(root, env)
    if base is None:
        # NOT a build failure. This guard is a tripwire; an environment that
        # cannot show it a diff is not a violation, and failing here would
        # block every PR rather than the one changing a charter.
        say("check_charter_authority: NOT ENFORCED — no base ref to diff")
        say("against (shallow checkout with no GITHUB_BASE_REF). A charter")
        say("change would pass unexamined here.")
        return 0

    branch = head_branch(root, env)
    changed = changed_paths(root, base)

    if not changed:
        say("check_charter_authority: OK — no role definition changed.")
        return 0

    # The merge queue's synthetic ref is `gh-readonly-queue/<base>/pr-N-<sha>`,
    # which HAS three segments -- so segment-counting alone reads its second
    # one as the base branch and fails every charter change at the gate.
    # Matched by name, explicitly, before anything is parsed out of it.
    if branch.startswith("gh-readonly-queue/") or branch in ("HEAD", ""):
        say("check_charter_authority: role definition(s) changed; not")
        say(f"enforced on '{branch or 'detached HEAD'}' — the pull_request run")
        say("is where this is enforced, and it gates entry to the queue.")
        listing(changed, "  ")
        return 0

    agent = agent_of(branch)
    if agent is None:
        say("check_charter_authority: role definition(s) changed, but the head")
        say(f"branch is not knowable here ({branch or 'none'}) — the pull_request")
        say("run is where this is enforced.")
        listing(changed, "  ")
        return 0

    # Holders: the committed list, or an account named for the role. Read from
    # the BASE side of the diff, so a branch cannot add itself to the list in
    # the same change it uses the list to justify.
    shown = git.run(root, "show", f"{base}:policies/authority.json", check=False)
    text = shown.stdout if shown.returncode == 0 else ""
    owner_role = common.role_of(text) or common.DEFAULT_ROLE
    if is_holder(agent, holders_of(text), owner_role):
        say(f"check_charter_authority: OK — {len(changed)} role definition(s) "
            f"changed on a {owner_role} branch ({agent}).")
        return 0

    err(f"FAIL: a role's DEFINITION changed on a branch owned by agent '{agent}'.")
    listing(changed, "       ", to_err=True)
    err(REFUSAL)
    return 1


def main() -> int:
    return common.run_main(NAME, lambda: run(sys.argv[1:], dict(os.environ)))


if __name__ == "__main__":
    sys.exit(main())
