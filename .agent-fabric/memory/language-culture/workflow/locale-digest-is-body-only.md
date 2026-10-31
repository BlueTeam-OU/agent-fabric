---
role: "language-culture"
class: workflow
topic: "locale-digest-is-body-only"
description: "A translation's translates_digest hashes the body, not the file; a lagging digest silently skips the token check; another role's locale is delivered in a REPLY"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "language-culture-ge"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 3fc0178ed8517ce3
---

## A translation's translates_digest hashes the body, not the file; a lagging digest silently skips the token check; another role's locale is delivered in a REPLY

`translates_digest` is sha256 over the source's body with the frontmatter
stripped (`_source_digest` in `tools/fabric/lint_rules/prompts.py`), not over
the whole file; a digest quoted in a request may be the whole file's, so
recompute it. With a wrong digest the lint treats the translation as lagging,
only warns, and skips the protected-token check, so a control passes silently.
Lint a worktree with `python3 tools/fabric/lint.py --fabric $PWD`, or it checks
the main checkout. AI and EU count as UPPER tokens. Another role's locale
directory refuses a language-culture commit at pre-commit; deliver the whole
file in a REPLY between BEGIN/END lines for fabric-coordinator to commit (j69,
2026-10-16, agent-fabric #283). A push after a refused commit still creates an
empty branch: check the commit landed before pushing.

*Anchors: `tools/fabric/lint_rules/prompts.py::_source_digest`, `tools/fabric/lint_rules/locales.py::lagging`*

*Observed 2026-10-16 (language-culture)*
