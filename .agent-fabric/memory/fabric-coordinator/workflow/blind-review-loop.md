---
role: "fabric-coordinator"
class: workflow
topic: "blind-review-loop"
description: "How to review a fabric change — render a request with bin/fabric-review, dispatch code-review on fable with the brief verbatim, POST the brief, the report and the per-finding judgement on the PR, fix, then re-review the fix range with…"
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
  - 2ff3e1161c2af3f2
---

## How to review a fabric change — render a request with bin/fabric-review, dispatch code-review on fable with the brief verbatim, POST the brief, the report and the per-finding judgement on the PR, fix, then re-review the fix range with previous_findings; the reviewer finds what the suite passes

Before merging a non-trivial agent-fabric change, write a request file
in the scratchpad (mode, repository, range, objective, requirements,
invariants, lenses), render it with `bin/fabric-review brief`, and
dispatch `code-review` (`model: fable`, description "Review …", no
isolation) with the rendered text as the whole prompt. Save the report
to a file, fix, then dispatch a `mode: re-review` of the fix range only
with `previous_findings:` that file: the reviewer answers each finding
by number and finds what the fix broke.

**Why:** on 2026-09-16 two rounds on the renderer itself (`2b61473`,
`0db784b`) found fourteen real defects that an 11/11 suite passed,
including a regression the first fix introduced. The live check
(`docs/live-checks/2026-09-16-review-context-boundary.md`) showed the
reviewer sees nothing of the parent conversation, so blindness is
exactly what the prompt withholds.

**The PR carries the whole exchange** (the owner, 2026-09-19): the
brief as a comment naming the head it reviews ("Review requested — …
head `<sha>`"), the reviewer's report as the next comment, then the
judgement of each finding by number (real → fix commit named; not real →
why, checkably) and the re-review's verdict. A review that lives only
in the session is invisible to the owner, the next session and the arm
gate ("a posted review of the current head"). Post before dispatching,
so a session that dies mid-review leaves the request on record.

**How to apply:** never paste conclusions into the request; if the lint
refuses a sentence, restate what must be true. Keep the range to the
commits under review. Say "re-review" in the description or the guard
denies it. See [[smoke-container-before-ci]] for the same read-back
rule applied to CI.

*References: smoke-container-before-ci*

*Observed 2026-09-16 (fabric-coordinator)*
