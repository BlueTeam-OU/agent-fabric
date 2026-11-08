---
role: "python-dev"
class: solution
topic: "j107-codex-reviewer-allowlist-pr455"
description: "j107 audit F01/F13 — Codex review engine permission profile + raw-tree extract; PR 455 state, traps found"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - e0e12dafae120195
---

## j107 audit F01/F13 — Codex review engine permission profile + raw-tree extract; PR 455 state, traps found

PR #455 (head 43d5528e, 3 work/5 fix): tools/fabric/review_codex.py runs `codex exec` under `[permissions.reviewer.filesystem]` in the scratch CODEX_HOME (`default_permissions`, no `--sandbox`, the two cannot coexist); `:minimal` is needed (explicit /usr failed to exec: root symlinks) and exposes /etc. Allow the codex binary file + codex-code-mode-host, the extract, and the repo's git objects/refs/HEAD/packed-refs/shallow. `codex sandbox -P reviewer` honours CODEX_HOME's config; real `codex exec` verified with a stand-in /responses SSE endpoint (tool name `exec_command`, arg `cmd`).
Extract via ls-tree -z + cat-file --batch lockstep, verified against ls-tree. Traps the blind review found: lexical link check misses link chains (resolve with realpath after writing); never create links before files (a link `d` plus tree `d/` writes outside); refuse repeated/prefix paths first. Test traps: a local `import io` / variable named `mode` in test main() shadows module/helper; a test that skips on any FailedReview masks real failures (skip only on "cannot start"); other suites carry their own fake codex (test_review_gateway.py needs the read-probe answer 43).
Open: F3 ADR-053 rule 2 amendment is coordinator's j552, committed onto the branch; F6 P3 carried; arm refused by repo settings (fabric/armed rule) until owner fixes; below minimum so coordinator/owner word needed.

*Anchors: `tools/fabric/review_codex.py::PROFILE`, `tools/fabric/review_codex.py::verify_extract`*

*Observed 2026-11-01 (python-dev)*
