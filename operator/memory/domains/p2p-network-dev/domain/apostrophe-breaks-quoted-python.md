---
role: "p2p-network-dev"
class: domain
description: "An apostrophe in a comment inside a shell script's single-quoted python block silently ends the quote; bash -n passes and the failure surfaces as a runtime syntax error far from the edit"
tier: 2
knowledge_scope: full
distilled_at: "2026-09-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: interweave
    working_copy: InterWeave
derived_from:
  - 77eb29fc1b888c77
---

## An apostrophe in a comment inside a shell script's single-quoted python block silently ends the quote; bash -n passes and the failure surfaces as a runtime syntax error far from the edit

**Writing prose into a `python3 -c '...'` block inside a shell script means
no apostrophes — including the one in a possessive like `deny.toml`'s.**

InterWeave's tree checks embed python in single quotes. Twice on 2026-09-10 I
added an explanatory comment containing an apostrophe and broke the script:

- the first time, `ADR-0045's` inside `check_vendored_advisories.sh`;
- the second, "which `deny.toml`'s own `yanked` key disproves".

**What makes it expensive is how it fails.** `bash -n` PASSES — the quotes
still balance overall, they just balance differently than intended. The error
appears at runtime, reported against a python line tens of lines from the
edit:

```
line 541: syntax error near unexpected token `"severity"'
```

The second time it turned into 23 failing self-test assertions, every one of
them a misleading "exit 2, but the baseline proved the database reachable" —
so the symptom pointed at the advisory database rather than at a quote.

**How to apply.** Write such comments without possessives and without
contractions: "the yanked key in deny.toml", not "`deny.toml`'s yanked key".
After editing inside one of these blocks, extract the block and assert it
carries no `'`, or simply RUN the script — `bash -n` is not the check that
catches this.

Related: [[verification-pipelines-must-fail-loudly]] — the exit code was
there to be read; [[assertions-that-cannot-fail]].

*References: assertions-that-cannot-fail, verification-pipelines-must-fail-loudly*
