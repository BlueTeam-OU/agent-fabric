---
role: "fabric-coordinator"
class: domain
topic: "open-code-review"
description: "alibaba/open-code-review (ocr): Go AI review CLI, Apache-2.0, very active; not adopted; borrow a narrow fact-check filter, a coverage manifest, fail-closed checkpoint markers, and pinned read tools instead of a reviewer Bash guard"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 248477410dfe1dcb
---

## alibaba/open-code-review (ocr): Go AI review CLI, Apache-2.0, very active; not adopted; borrow a narrow fact-check filter, a coverage manifest, fail-closed checkpoint markers, and pinned read tools instead of a reviewer Bash guard

https://github.com/alibaba/open-code-review, read 2026-10-21 at the owner's request ("helpful to improve our reviewing process"), from a read-only shallow clone with nothing run. HEAD was 2026-10-20 (#1773).

**What it is:** `ocr`, a Go CLI with an npm wrapper, IDE extensions, a GitHub Action and other CI examples. It reviews a git diff with an LLM agent that has read-only tools and posts line-anchored comments. Its README says it began as Alibaba's internal review assistant. It needs its own LLM key, except in delegation mode, where the host agent reviews. Telemetry (OTel) is off by default. The npm wrapper checks for updates (`OCR_NO_UPDATE=1` turns that off). It claims better precision than Claude Code at 1/9 of the tokens on its own benchmark, unverified.

**How it reviews:**
- Deterministic file selection, with secret paths that can never be re-included.
- LLM grouping of related files (4 or more files, at most 10 per group), one sub-agent per group, with the other changed files listed by name.
- Per-path rule checklists with merge layers.
- An optional plan of risk points, each naming the tool call that would verify it; the plan is dropped from round 2 on so it cannot cap coverage.
- Up to 2–3 rounds that feed back the confirmed findings and stop when a round adds nothing.
- A separate filter call that may delete a finding only if the diff proves it wrong, never for a concurrency or behaviour-change finding.
- Location re-anchoring of each finding against the diff.
- A run manifest (`ocr.run-manifest/v1`) marking every file completed, reused or failed, with a failure class.
- A fail-closed incremental checkpoint: the reviewed head is a hidden marker in its own sticky summary, and any doubt means a full review.
- No judgement of previous findings as fixed or not; no confidence field.

**Verdict: borrow ideas, do not adopt.** Not adopted because it is a second LLM key and a second posting path, and because its `--background` passes the author's own reasoning into the reviewer, which breaks blind review (ADR-020).

**Built (ideas 1-3), ADR-065, #358 merged 2026-10-24 (94487c3b):** pinned read tools in a stdio MCP server plus a proved bwrap sandbox for checks; a coverage block per review (a path not read uncounts it); a v2 marker the next round derives its base, card and previous findings from. Live read-back 2026-10-24: Claude Code passes CLAUDE_PROJECT_DIR to the server and a code-review subagent sees exactly Read/Glob/Grep + the six review_* tools. Ideas 4-5 below are still open.

**Worth borrowing, in order:**
1. **Pinned read-only review tools in place of the review-class Bash guard:** `git show <ref>:<path>`, `git grep`, a diff reader, and no shell. This removes the whole class of guard-parsing gaps for the reviewer.
2. **A coverage manifest per review:** every file and lens in the range marked covered or failed. "No findings" then also means the whole range was read, which the arm could check.
3. **A fail-closed checkpoint marker in our posted review object:** head, base and config fingerprint, accepted only when we posted it and it is an ancestor of the head. This is the fix range for the next round, derived instead of typed.
4. **A narrow, advisory fact-check pass:** it may only flag findings the diff contradicts. Log what it would remove, act on nothing above P3.
5. **Per-path review rules** (a lens attached to a path), e.g. "every guard branch needs a case for each quoting form". That is the pattern behind #348 needing four rounds.

The full report is in this session's transcript, not in the tree. Related: [[pr-agent]], [[ifixai]], [[codex-review-routing-decision]], [[lint-overreport-not-model]].

*References: codex-review-routing-decision, ifixai, lint-overreport-not-model, pr-agent*

*Observed 2026-10-21 (fabric-coordinator)*
