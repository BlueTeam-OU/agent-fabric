---
role: "fabric-coordinator"
class: solution
topic: "wave-9-landed-where"
description: "which PR landed each ADR-040 Wave 9 batch, and what of Wave 9 is still open (2026-10-24)"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - b255b92d37eef3ba
---

## which PR landed each ADR-040 Wave 9 batch, and what of Wave 9 is still open (2026-10-24)

Wave 9 (ADR-040 §7) by PR, read from origin/main 2026-10-24: batch 1 #200; 2 and 3 #323;
4, 5, the fallback note of 6 and the host check of 9 #329; plan-hold (6) and batch 7 #318
(python-dev-02); batch 8 #316 (python-dev-04, not python-dev-02 as j341's title said);
langid installer (9) #314; batch 10 runners #265, leak check #267 and #327. Recorded as a
"landed" column in §7 by PR #361 (j341).

Still open: `session-start.sh` (bash export, host python3) → j369; `pre-push` stays on host
python3 by its own decision; the §7 lint change never landed — `tools/fabric/lint_rules/shape.py`
still enforces the 160-line rule and `policies/bash-allowlist.json` has only `scripts: {}`
→ j368.

**Why:** the ADR's status said "in progress" long after the batches merged, because no
batch PR updated §8. **How to apply:** a batch/wave PR updates the record's status in the
same PR; before claiming a wave state, compute it from the tree (git log per inventory file).

*Anchors: `tools/fabric/lint_rules/shape.py::BASH_LINE_LIMIT`, `runtime/claude-code/hooks/session-start.sh::CLAUDE_ENV_FILE`, `docs/adr/ADR-040-implementation-language-python-above-150-lines.md::| landed |`*

*Observed 2026-10-24 (fabric-coordinator)*
