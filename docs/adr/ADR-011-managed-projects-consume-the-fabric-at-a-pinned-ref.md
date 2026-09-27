# ADR-011 — Managed projects consume the fabric at a pinned ref

**Date:** 2026-09-18
**Status:** Accepted
**Ratified:** owner, 2026-09-27, by arming agent-fabric #51 (ratification by merge, the owner's rule of 2026-09-27)
**Decision Makers:** fabric-coordinator, after the CEO's challenge of 2026-09-18 ("all time the same error … did you learn?"); the pin in gzapp's CI landed there (gzapp#854, gzapp#857)
**Scope:** `<working copy>/.agent-fabric/fabric-ref` in every managed project; the checkout step of a project's CI that runs the fabric's guards; the order in which a drain lands (memory/README.md, "Landing a drain"); `fabric_ref_findings` in tools/fabric/lint.py
**Pillar:** P1

## 1. Context and Problem

A managed project's CI runs this repository's guards and its corpus lint,
which reads two repositories at once: the project's `.agent-fabric/`
indexes and the fabric's domain slices. The order of a drain's landing is
forced — a project index listing a slice not yet on fabric `main` is a
finding — so the fabric commit goes first, and until the project's index
pull request merges, the project's check sees a fabric that moved under
it. Four times on 2026-09-18 a gzapp required check went red because
agent-fabric `main` moved under an unpinned checkout; the last came after
the landing order had been written down and the window called "minutes".
Sequencing shortens the window; it never closes it.

## 2. Decision

A managed project consumes the fabric **at a pinned commit**. The project
holds `.agent-fabric/fabric-ref` — one line, the full commit id the
project's indexes were assembled against — and a project whose CI runs
the fabric's guards checks out that commit, never the fabric's default
branch. A fabric change reaches the project's check only when the ref
moves, in the pull request that carries the matching indexes; a fabric
defect stops the fabric's CI rather than the project's.

Until the pin is live on a project's `main`, a fabric push that changes
what that project's index must list is held: it waits for an empty merge
queue and goes out with the index pull request in the same minute.

## 3. Alternatives Considered

- **Sequencing alone** — push the fabric, open and arm the project PRs
  in the same breath. Tried on 2026-09-18; a queue run landed inside the
  window anyway. It stays as the landing order, not as the protection.
- **Reverse the order** (project first). Not possible: the project's
  index would list slices not yet on fabric `main`, the same finding.

## 4. Rationale

A project must not be broken by a repository it does not control moving
on its own schedule. Pinning makes the fabric a dependency the project
upgrades deliberately, in a reviewable diff that carries both the new ref
and the indexes that match it.

## 5. Binding Rules

1. `.agent-fabric/fabric-ref`, when present, is exactly one line ending in
   a newline, a full lowercase 40-hex commit id;
   `tools/fabric/lint.py` (`fabric_ref_findings`) refuses anything else.
2. A project whose CI runs the fabric's guards checks out the commit
   `fabric-ref` names, never the fabric's default branch.
3. Landing a drain: the domain slices commit and push here first; then, on
   each project's drain branch, `fabric-ref` is written with that commit
   (`git -C agent-fabric rev-parse origin/main >
   <wc>/.agent-fabric/fabric-ref`) and the project pull requests are
   opened and armed at once.
4. The ref moves only in a project pull request that carries the indexes
   matching it.
5. While a project's CI has not pinned the ref, a fabric push that changes
   what that project's index must list waits for the project's merge queue
   to be empty and goes out with the index PR in the same minute; a queue
   holding one longer is said on the relay.

## 6. Consequences

- With the pin live, a fabric push is free of the project's queue.
- A project lags the fabric by design until its next drain moves the ref;
  what the fabric's `main` says and what a project's CI checked can differ,
  and the ref says which.
- `fabric-ref` is optional: a project without it is still read at the
  fabric's head, and rule 5 applies to it.

## 7. Future Evolution

None stated. Each new managed project whose CI runs the fabric's guards
adopts the pin in its own repository.

## 8. Decision Status

Accepted; in force since 2026-09-18.

## References

- `memory/README.md` §The drain cycle, "Landing a drain, in this order".
- `tools/fabric/lint.py` `fabric_ref_findings`.
- gzapp#854, gzapp#857 (the project's checkout step pinned).
- ADR-004 (the order a new role lands in, which a drain follows).
