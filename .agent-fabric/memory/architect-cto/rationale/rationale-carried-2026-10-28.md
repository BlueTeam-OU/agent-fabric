---
role: "architect-cto"
class: rationale
topic: "rationale-carried-2026-10-28"
description: "What the review pipeline costs and why (measured 2026-10-14): the fixed preamble re-sent per turn is 59-76% of a reviewer's prompt tokens; turns, not diff size, set the cost; re-reviews read more outside the fix range than inside it…"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-01"
origin:
  - agent: "architect-cto-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 7d371494f323cb86
  - f55dbc1042d13893
---

## What the review pipeline costs and why (measured 2026-10-14): the fixed preamble re-sent per turn is 59-76% of a reviewer's prompt tokens; turns, not diff size, set the cost; re-reviews read more outside the fix range than inside it; Codex usage is never recorded

Measured on 539 code-review dispatches of this login (2026-09-11 to 2026-10-14) and 174 merged PRs across agent-fabric, InterWeave and gzapp; report in the session scratchpad `econ/report.md` and published as the artifact "Review Economics in Agent Fabric" (2026-10-14), delivered to the owner as job j119.

- Nothing serializes file bodies into a reviewer's prompt: the brief is 1.4-2.6 KB, the constitution 13 KB. The reviewer pulls evidence itself from the live clone.
- First-turn context is 46.5k tokens in gzapp and 15k in agent-fabric; the gap is the project instruction files a subagent inherits. Measured causally by fabric-coordinator 2026-10-14 (REPLY 01a139c7): `omitClaudeMd: true` takes a gzapp subagent's first turn from 36,172 to 2,031 tokens and drops every instruction file including the @-imported AGENTS.md and the auto-memory MEMORY.md (undocumented). gzapp's root CLAUDE.md alone is 70 KB ≈ 17.6k tokens in every session turn: an author-side lever, raised separately. Re-sent every turn, that preamble is 59% of a review's prompt tokens and 76% of a re-review's. Lever: `omitClaudeMd` on the review agent file plus a 2 KB per-project review card.
- Review tokens correlate 0.95 with turn count and 0.53 with diff bytes; findings do not correlate with spend (0.04). Fitted: review equiv ≈ 476k + 15/diff byte; re-review ≈ 242k + 10/byte.
- Re-reviews: 52% of evidence bytes are file reads, 31% of evidence on files outside B..C vs 20% inside. The constitution's "only the hunks" rule is followed in spirit, not mechanism. Lever: embed the exact B..C diff and locators in the re-review brief.
- Codex (ADR-053): 7 PRs, 17 posts, ~3-5 unique confirmed P2, 0 unique P1, one-level severity inflation, duplicates frequent; its tokens are never recorded (events carry usage; scratch deleted). The arming policy lists claude only; codex is additional by the owner's word 2026-10-13.
- Telemetry: control-plane `tokens` is per model per login per 7 days; nothing per PR, stage or engine. The SubagentStop hook gives agent_transcript_path/agent_id/agent_type; meta.json gives description and toolUseId; a background Agent result carries no usage.
- Commit band: work-commit count correlates weakly with rounds (0.20-0.39); PRs ≥8 work review fewer rounds per 100 added lines. Leave the band.

**Why:** the owner asked (2026-10-14) for the smallest evidence-backed change to tokens per verified result; these are the measurements the recommendation rests on, and the next session should not re-derive them.
Owner's refinements (2026-10-14, report section 11, the plan of record): attribution is structural (a fenced `agent-fabric-dispatch v1` header rendered into the brief, read by the SubagentStop hook; schema_version 1; status completed|failed|timeout|cancelled|allowance-exhausted, never conflated with zero findings); the review card is read at base_sha, never the head's copy (a PR changing the card is reviewed under the base's); two evidence modes, pinned (git show C:path) and working-tree (never posted as coverage of a head); P3 targets turns, "widen only to establish the fix's semantics or detect a regression"; P4 advisory only, "byte-identical at <head>", the symbol-reference invalidation rule dropped; E1/E2 staged and quality-first (no P1 regression, P2 non-inferiority, duplicates by identity, blind adjudication of disagreements); report raw tokens, equivalents and money separately, never "cost fell".

Landed: agent-fabric #259 (16 work, 13 fix) merged 9b1aa7cb on 2026-10-14 with P1 (ledger), P2 (card at base + omitClaudeMd, unconditional), P3 (delta-first re-review), P5 and the evidence mode. A project's reviewer gets no project text until its `.agent-fabric/review-card.md` lands, and only fabric-coordinator can commit there (the project pre-commit fence refuses every other role, measured on gzapp and InterWeave the same day).

**How to apply:** recommendation order is P1 ledger (devex-tooling), then P2 reviewer context + P3 delta-first re-review together (fabric-coordinator), then the E1/E2 replay before any further policy change; the second-engine policy waits on a month of recorded Codex usage. Reports of review dispatches live in the parent transcript as hand-back messages keyed by agent id, not in the subagent file. The replay's results are [[review-economics-e2-replay-2026-10-15]].

*References: review-economics-e2-replay-2026-10-15*

*Observed 2026-10-14 (architect-cto)*
