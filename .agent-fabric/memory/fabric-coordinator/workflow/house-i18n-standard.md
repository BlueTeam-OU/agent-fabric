---
role: "fabric-coordinator"
class: workflow
topic: "house-i18n-standard"
description: Translated strings follow the house i18n standard — check a managed project for an existing convention before inventing a file format
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
  - 59dc78ff13f1c305
---

## Translated strings follow the house i18n standard — check a managed project for an existing convention before inventing a file format

The workspace has a house i18n standard and fabric code follows it, not a
shape invented per tool. It is stated in a managed project (an ADR plus
that project's `product/i18n/README.md` and `contracts/i18n/*.schema.json`);
`communication/gzcoord/i18n/README.md` is the fabric's restatement of it
with the citation, because lint forbids naming a managed project in
generic code but exempts READMEs.

What it fixes: one flat key -> string JSON file per locale, named for the
locale's BCP-47 tag (`en-US.json`, `ka-GE.json`); keys are flat dotted
slugs `<area>.<thing>`, kebab inside a segment; values are non-empty
strings with `{name}` interpolation; `en-US` is mandatory and is what the
fallback chain lands on; every active locale is complete against it.
"No fabricated fallback text" forbids inventing a string, not falling
back to the default locale — so a session-start path may fall back, and
completeness is then enforced at lint time instead.

**Why:** asked to make the GZCoord inbox speak Georgian I designed a
`messages/en.json` catalogue from scratch; the owner's correction was
"we have a standard i18n json files to store translation, follow it".
The keys and `{name}` placeholders happened to match — the layout and the
filenames did not.

**How to apply:** before inventing any format for translated or
configurable strings, look for the convention in the managed
repositories under `projects/` (`contracts/`, `product/`, a schema) and
adopt it; restate it in a README where the fabric uses it rather than
citing the project from code. See [[locale-suffixes]] for what a login's
suffix maps to — the fabric now stores that as `tag` in each locale's
`locale.json` rather than leaving it inferred.

*References: locale-suffixes*

*Observed 2026-09-21 (fabric-coordinator)*
