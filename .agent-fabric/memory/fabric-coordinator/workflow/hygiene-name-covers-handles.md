---
role: "fabric-coordinator"
class: workflow
topic: "hygiene-name-covers-handles"
description: "a person's-name hygiene entry must also catch the handles and accounts built from it (joined, hyphenated, underscored, any case); \\b is defeated by _"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 7a4104ac47845a32
---

## a person's-name hygiene entry must also catch the handles and accounts built from it (joined, hyphenated, underscored, any case); \b is defeated by _

j610 (2026-11-05, commit fac43809): the CEO's entry in policies/hygiene.json matched only the capitalised name between `\b`s, so the joined lowercase GitHub handle, the hyphenated Claude account name and the underscored key variable all reached four slices (Codex F2 on the j553 live check). Fixed with two `"flags": "i"` entries using `(?<![a-z0-9])…(?![a-z0-9])`: an account/handle form first (refer_as "the CEO's account"), then the name. The order matters, because the name entry run first leaves the account's tail behind. tests/test_hygiene_person_name.py reads the committed list, and swapping the order or dropping the flag turns it red.

**Why:** a slice cites accounts and handles far more often than a name in prose; the rule was written for prose.

**How to apply:** when adding any person or deployment entry, write the handle and account forms too, and test them against the committed list. A drained slice can also be stale because its source was fixed and never re-drained (devex-tooling's was rewritten 2026-11-02): ask the holder before asking for a rewrite. See [[fix-a-claim-everywhere-it-is-made]].

*References: fix-a-claim-everywhere-it-is-made*

*Anchors: `policies/hygiene.json::an account or handle built from a person's name`, `tests/test_hygiene_person_name.py`*

*Observed 2026-11-05 (fabric-coordinator)*
