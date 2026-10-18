---
role: "fabric-coordinator"
class: domain
topic: harness2
description: "Harness² (google-research/harness2): recursive agent harnessing — per-task Propose–Probe–Compose over 8 harness components plus a per-domain lesson library; not adoptable as a tool; borrow its lesson schema, evidence rule and component…"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - e4af293d99431d60
---

## Harness² (google-research/harness2): recursive agent harnessing — per-task Propose–Probe–Compose over 8 harness components plus a per-domain lesson library; not adoptable as a tool; borrow its lesson schema, evidence rule and component ladder for the drain and for guards

github.com/google-research/harness2, read 2026-10-18 (Apache-2.0, Python 3.12, created 2026-10-06, ~2.4k stars;
paper arXiv 2610.14224, Xu et al., Google). Read as data; the benchmark gains in its README (GLM-5, Gemini 3.5 Flash:
up to +11.5 WorkBuddy, +4.5 JobBench, +11.8 pp LAB partial pass) were not verified.

**What it is.** A research framework that improves the *harness* (not the weights) around an executor (OpenCode or
Codex). Eight editable components: system prompt, guardrails, memory, tool guidance, subagents, skills, scripts,
plugins. Task-level recursion: an INVARIANT editor (procedure, tools) and a DOMAIN editor propose edits, candidate
harnesses are probed on the same task, a composer merges them from behavioural contrasts, no ground truth.
Harnessing-level recursion: after each task a reflector writes into a per-domain library
(`<run>/<mode>/<domain>/INDEX.md`, `harnesses/<task>/harness/` the full adopted tree, `EXPERIENCE.md`).

**Worth borrowing (core/selection.py, core/prompts.py, core/library.py, core/ledger.py):**
- *Lesson schema:* `cue` (the shape of situation, not this task's facts), `lesson` (an operation on a named
  component, checkable), `evidence` (cites the per-edit rows), `confidence` (high/medium/low and why). Stored only if
  cue, lesson and evidence are all present; otherwise `NO_ENTRY`, and the per-edit rows are kept anyway.
- *Evidence rule:* per edit a verdict of helped / hurt / no observed effect / **confounded**, preferred when several
  components changed at once or one rollout stands behind it; "a lesson resting only on confounded rows is a guess";
  "adoption alone never establishes that an edit helped". For the fabric: a merged PR is not proof its rule worked.
- *Cheapest effective component:* a tool error gets one bounded fallback; mechanical repetition gets a script; a
  triggered workflow gets a skill; only *repeated* evidence that clear prose is skipped justifies a defensive hook;
  ordinary sequencing stays prose. Matches our "a guard is three things" and the audit's patch-accretion concern.
- *Blind adoption:* finals anonymized (A, B, … seeded shuffle), base runs excluded from the pool by construction;
  stored lessons asserted free of grader verdicts and leak paths; the library keeps only entries that precede the
  current task; a budget ledger asserts its exact rollout and session counts (R = 4k, P = 3k).

**Not adoptable:** it rewrites prompts and guardrails automatically, which the fabric's authority model forbids
(charters and guards change by fabric-coordinator's reviewed PR, the owner accepts records). It runs executors with
unrestricted network and Codex's sandbox off; it needs Vertex/GCP. Where it could serve: the weekly reflection and
the drain (ADR-058, memory/RUBRIC.md) could take the cue/lesson/evidence/confidence shape and the confounded rule.
Related: [[software-factory-loops-graphs-harnesses]], [[trueforge]], [[edgextract]].

*References: edgextract, software-factory-loops-graphs-harnesses, trueforge*

*Observed 2026-10-18 (fabric-coordinator)*
