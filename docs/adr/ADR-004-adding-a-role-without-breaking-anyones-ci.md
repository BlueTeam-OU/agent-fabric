# ADR-004 — Adding a role without breaking anyone's CI

**Date:** 2026-09-17
**Status:** Accepted
**Ratified:** owner, 2026-09-27, by arming agent-fabric #51 (ratification by merge, the owner's rule of 2026-09-27)
**Decision Makers:** fabric-coordinator, after the merge-queue failure of 2026-09-17 (relay seq 1076)
**Scope:** adding a role to the fabric and binding it in a managed project: identities/roles/, identities/roles/catalog.json, runtime/hosts/registry.json, projects/registry.json, a project's .agent-fabric/, the first drain, runtime/provisioning/new-agent.sh
**Pillar:** P1

## 1. Context and Problem

A role is three commits in two repositories, and every managed project's
CI runs this repository's lint, at `main`, against its own working copy.
On 2026-09-17 `p2p-network-dev`'s first domain slices landed here before
the project that indexes them had merged its `.agent-fabric/`, and every
merge-queue run of an unrelated project failed for an hour (relay seq
1076): the lint judged every domain whenever any project was visible.

The lint now judges a domain only where a visible project's taxonomy
binds the role (`tools/fabric/lint.py`,
`case_domain_bound_by_an_unseen_project_is_not_judged`), so the
fabric-first order is safe. The guard covers one shape of the mistake,
not the next; the order stays the rule.

## 2. Decision

A role is added in this order, and each step lands before the next begins:

1. **Here, one commit — the role**: `identities/roles/<role>/charter.md`
   and `recall.md` (a `brief.md` when there is a holder's account to
   distil), the catalogue entry, the placement in
   `runtime/hosts/registry.json`, and for a new project its
   `projects/registry.json` entry and `projects/<id>/integration/`.
   `tests/run.sh` green; push.
2. **In the project, one PR — the binding**: `.agent-fabric/taxonomy.json`
   with the role's paths and keywords, `.agent-fabric/roles/<role>.md`
   (the remit), and `.agent-fabric/memory/<role>/INDEX.md` listing the
   charter, recall and brief in the assembler's line format; linted from
   here with `--working-copy <id>=<checkout>` before the PR opens; merged.
3. **The drain, once, both sides**: `harvest_memory.py --role <role>
   --working-copy <checkout> --all --out <drain>`, then `assemble.py
   --claims <drain>/claims --drain <drain> --project <id> --working-copy
   <checkout> --stamp <date>` — domain slices here under
   `memory/domains/<role>/`, system slices and the regenerated `INDEX.md`
   in the project.
4. **The account**: `runtime/provisioning/new-agent.sh <login> <role>
   --project <id>`, which prints what it leaves for a person (the signing
   key, the credentials file, the first interactive launch) and persists
   the account across the host's reboot in the same run.

## 3. Alternatives Considered

- **Rely on the lint guard alone** and add the pieces in any order.
  Rejected: the guard closes the shape of the merge-queue failure
  of §1 only; a dangling
  index link or an uncatalogued remit fails a project's CI all the same.
- **Loosen the lint** when an intermediate state fails. Rejected: in every
  failure mode the fix is to land the missing half.

## 4. Rationale

Each step leaves every project's CI green on its own: a domain slice
nobody indexes yet is not judged; the project's index links domain slices
only once they are on `main` here; a remit never names a role the
catalogue lacks. The order costs nothing and removes a cross-repository
outage.

## 5. Binding Rules

1. The four steps of §2 are done in that order.
2. No generic file here names the project (lint refuses it); the
   project's remit is where the project appears.
3. The project's own checks may skip `.agent-fabric/`: its links are
   working-copy-relative and reach `../agent-fabric/`.
4. In the drain, the project side is committed first, and the fabric
   commit is pushed before the project PR's checks run — the project's
   index links the domain slices by a path that resolves through
   `../agent-fabric/`.
5. A claim that disagrees with a section already in the corpus stops the
   run until the owner decides (`--collision-decisions`,
   `memory/README.md` §The drain cycle).
6. When an intermediate state fails a project's CI, the missing half is
   landed; the lint is never loosened for it.

## 6. Consequences

What breaks when the order is wrong: a domain slice here with no index
anywhere — nothing now, a lint finding on the binding project's CI once
its taxonomy binds the role; an index in a project pointing at a domain
slice not yet on `main` here — that project's CI fails on a dangling
link; a project remit naming a role not in the catalogue — that project's
lint finding.

The assembler is idempotent: the same drain twice is the
same tree (a claim body's own headings are demoted at render time,
so they never open a section on the re-read), and re-running
step 3 to pick up a brief added after the first run is safe.

## 7. Future Evolution

None stated. A new role or a new project is the next exercise of the
order.

## 8. Decision Status

Accepted and in force.

## References

- `tools/fabric/lint.py`; `tests/test_lint.py`
  `case_domain_bound_by_an_unseen_project_is_not_judged`.
- `tools/fabric/harvest_memory.py`, `tools/fabric/assemble.py`,
  `memory/README.md` §The drain cycle.
- `runtime/provisioning/new-agent.sh`; `identities/roles/catalog.json`;
  `runtime/hosts/registry.json`; `projects/registry.json`.
- ADR-002 (what a role is and how it is bound).
