---
role: "fabric-coordinator"
class: workflow
topic: "prompt-change-readback"
description: "After changing any role's charter, brief, prompt template or the team section: run `runtime/openrouter/launch --print` as a holder of that role (hostexec --as) before pushing — lint and tests did not check the rendered total until…"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "fabric-na"
derived_from:
  - 7038080b46396681
---

## After changing any role's charter, brief, prompt template or the team section: run `runtime/openrouter/launch --print` as a holder of that role (hostexec --as) before pushing — lint and tests did not check the rendered total until 2026-09-20 and a green PR broke a launch

A charter, brief, `identities/prompt/*.md` or locale change is read
back as a launch, as the affected account, before it is pushed:

```sh
runtime/hostexec/hostexec <host> --as <login> --cwd <wc> -- bash -lc \
  '~/projects/agent-fabric/runtime/openrouter/launch --print'
```

**Why:** on 2026-09-19 the brand-comms charter passed lint (per-file
budget) and the suite, was merged, and brand-comms-01 could not launch:
the rendered prompt (charter + the fabric's longest brief + a team
section grown that day) was 24.5k against the launcher's 23k ceiling,
which only the launcher checked. The owner: "you have not run the lint
after the last update" — the lint had run and passed; the read-back had
not. The suite now renders every catalogue role against MAX_CHARS
(tests/test_launch_prompt.py), but the live read-back stays the rule:
the launcher also pulls, binds and resolves models, none of which the
suite sees.

**How to apply:** one `--print` per affected role's holder, in the
commit's verification; for a team-section change, the two longest
prompts (language-culture, brand-comms). See [[blind-review-loop]]
for the rest of the gate, [[local-grep-is-ugrep]] for the same lesson
about local greens.

*References: blind-review-loop, local-grep-is-ugrep*

*Observed 2026-09-20 (fabric-coordinator)*
