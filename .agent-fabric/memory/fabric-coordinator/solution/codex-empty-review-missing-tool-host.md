---
role: "fabric-coordinator"
class: solution
topic: "codex-empty-review-missing-tool-host"
description: "An engine answering in a forced schema returns a valid empty review when it read nothing; a Codex 'No findings' counts only with completed commands in its event log, which review_codex now enforces"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 8341702f2e790bf7
  - 903c7098f870c754
---

## An engine answering in a forced schema returns a valid empty review when it read nothing; a Codex 'No findings' counts only with completed commands in its event log, which review_codex now enforces

2026-10-12: two "No findings" Codex reviews (#225, #228) had read no code: Codex was installed as its one
binary without the `codex-code-mode-host` helper the npm tarball ships beside it, so `codex exec --json` showed
0 `command_execution` items and an error item, and it answered from the brief alone.

Both halves are now in the tree: `fabric-tools --install codex` installs the vendor tree whole
(`tools/fabric/tools_install.py`), and `tools/fabric/review_codex.py` refuses a run with no completed command
or a missing tool host as a failed review, never as "No findings".

**Why:** a review engine that cannot read the change still returns a schema-valid empty answer, which looks
exactly like a clean review.
**How to apply:** an empty review from any engine answering in a forced schema is evidence only when its log
shows it read the change; when adding an engine, give it the same refusal. Related:
[[codex-chatgpt-signin-2026-10-12]], [[codex-review-routing-decision]].

*References: codex-chatgpt-signin-2026-10-12, codex-review-routing-decision*

*Anchors: `tools/fabric/review_codex.py::codex-code-mode-host`, `tools/fabric/tools_install.py::codex-code-mode-host`*

*Observed 2026-10-23 (fabric-coordinator)*
