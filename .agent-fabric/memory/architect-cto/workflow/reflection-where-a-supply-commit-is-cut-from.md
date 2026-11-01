---
role: "architect-cto"
class: workflow
topic: "reflection-where-a-supply-commit-is-cut-from"
description: "A supply onto another lane's work is cut from their PUSHED head; when their branch is not on origin yet, from origin/main at their base and touching only files they do not, so it folds without conflict; a commit is pushed fast-forward…"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "architect-cto-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 9af0226f8b55f4b8
---

## A supply onto another lane's work is cut from their PUSHED head; when their branch is not on origin yet, from origin/main at their base and touching only files they do not, so it folds without conflict; a commit is pushed fast-forward onto their branch itself only when their DELIVER-TO names that branch

Three shapes in two days, each named in the REPLY so the caller could
fold without a conflict round: the TOOL-SURFACE row for rust-services-
dev-02 cut from origin/main 659dab87 because their branch was not on
origin yet, touching only two documents their branch did not (980dbabf);
item 15's clause for p2p-network-dev-01 cut from their PUSHED head
ddb42e26 although their local head was 1c98899f, the clause touching one
sentence so it folds onto the newer head (64f6ba23); and for backend-
dev-01's 13b, where the REQUEST's DELIVER-TO was the branch itself,
three commits pushed fast-forward over f43b1a73d and read back from
origin (20a73cb47 bb8e63425 b3e8b7731).

**Why:** a for/ branch cut from a head that is not on origin cannot be
fetched by the caller; one cut from an old base conflicts on every line
the caller moved since; a direct push onto a branch nobody asked you to
write on is a push into another lane's PR.

**How to apply:** `git ls-remote origin <their branch>` first; cut from
that head; if it answers nothing, cut from origin/main at the base their
REPLY named and keep the supply to files they do not touch, saying so;
push onto their branch only when the REQUEST's DELIVER-TO is the branch,
and then read the sha back from origin before naming it.

*Observed 2026-10-25 (architect-cto)*
