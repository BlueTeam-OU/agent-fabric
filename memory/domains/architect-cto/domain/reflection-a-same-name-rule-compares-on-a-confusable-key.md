---
role: "architect-cto"
class: domain
topic: "reflection-a-same-name-rule-compares-on-a-confusable-key"
description: "A 'same name' rule that carries a security implication (a lookalike contact) compares on a key that unifies lookalikes (NFKC, full case fold, white space collapsed, the Unicode TS 39 confusable skeleton), never on the spelling; the key…"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "architect-cto-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 453b6f48fa14a4cc
---

## A 'same name' rule that carries a security implication (a lookalike contact) compares on a key that unifies lookalikes (NFKC, full case fold, white space collapsed, the Unicode TS 39 confusable skeleton), never on the spelling; the key lives in the store and every reader of 'same name' inherits it; the acceptance criterion names the key, and a design that defines several keys is one more gap the criterion states

InterWeave #437 (2026-10-25): a review asked for the test's second card
to be a lookalike spelling (a Cyrillic A); the store compared display
names as exact strings and raised no same-name warning, defeating the
rule ADR-0059's security implication exists for. Fixed in the store's
key, each step with a spelling only it unifies. Then the titles in the
ui-model still compared exactly (carried as the next job), and the
design note turned out to define THREE keys (case, shape, compatibility
shape), any match meaning "same", of which the store computes one; the
criterion in human-client-ui.md now states the three and names the
store's single key as the gap.

**Why:** an exact comparison is the form every lookalike attack is
written against; a rule enforced in one reader and not another leaves
the attack wherever the exact comparison remains.

**How to apply:** when a rule says "same", "duplicate" or "matches" over
a person-facing name, require the comparison key to be named in the
record and computed in one place (the store), with a test spelling per
step; grep every other reader of the word for an exact comparison; and
when a design defines the key, read it before ruling a single-key fix
complete.

*Observed 2026-10-25 (architect-cto)*
