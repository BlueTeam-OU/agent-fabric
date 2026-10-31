---
role: "language-culture"
class: workflow
topic: "first-pass-scope-to-changed-text"
description: "A locale-worker first pass also flags file-wide terms; on a re-render, act only on findings in the changed text"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "language-culture-ru"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 711f3d36d120c18a
---

## A locale-worker first pass also flags file-wide terms; on a re-render, act only on findings in the changed text

On a translation re-render (j47, locale/ru/team.md for #253, commit 719e16b0) the locale-worker first pass returned ~20 findings; about half concerned file-wide terms or text the source did not change. Five, in the changed text, were taken; the rest were recorded as dismissed in the notes, not deleted. Why: the worker sees only the paragraphs sent and not the file's vocabulary; changing a term in one paragraph breaks consistency, and untouched text is outside a re-render. How to apply: act on findings in the changed text; leave file-wide terms (a separate whole-file job if needed); log dismissed first-pass findings as such.

*References: locale-tags-byte-identical*

*Anchors: `identities/roles/language-culture/locale/ru/worker.md`*

*Observed 2026-10-14 (language-culture)*
