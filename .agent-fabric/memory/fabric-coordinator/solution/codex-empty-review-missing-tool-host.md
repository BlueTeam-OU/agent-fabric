---
role: "fabric-coordinator"
class: solution
topic: "codex-empty-review-missing-tool-host"
description: "Codex 0.162.1 installed as the single npm-tarball member bin/codex cannot run tools (missing codex-code-mode-host) and still answers {\"findings\":[]} — an empty Codex review is not evidence until its event log shows commands ran"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 8341702f2e790bf7
---

## Codex 0.162.1 installed as the single npm-tarball member bin/codex cannot run tools (missing codex-code-mode-host) and still answers {"findings":[]} — an empty Codex review is not evidence until its event log shows commands ran

2026-10-12: two "No findings" Codex reviews (#225, then #228 through gateway 0.3.0) had read no code.
Rerun with `codex exec --json`: 0 `command_execution` items, an `error` item, and stderr
`ERROR codex_core::tools::router: error=failed to spawn code-mode host ~/.local/bin/codex-code-mode-host`;
68k input / 961 output tokens — it answered from the brief alone. `fabric-tools --install codex`
extracted only `package/vendor/x86_64-unknown-linux-musl/bin/codex`; the tarball also carries
`bin/codex-code-mode-host` (74 MB), `codex-path/rg`, `codex-resources/bwrap`. Run from the full vendor
tree, the same binary executed `wc -l` fine.

**Why:** a review engine that cannot read the change still returns a schema-valid empty answer, which
looks exactly like a clean review.
**How to apply:** never count a Codex "No findings" as a review unless its JSON event stream shows
successful commands (the fix in progress makes review_codex refuse such a run, and the install place
Codex's helpers). The same doubt applies to any engine answering in a forced schema.
Related: [[codex-chatgpt-signin-2026-10-12]], [[codex-review-routing-decision]].

*References: codex-chatgpt-signin-2026-10-12, codex-review-routing-decision*

*Observed 2026-10-12 (fabric-coordinator)*
