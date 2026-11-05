---
role: "fabric-coordinator"
class: solution
topic: "dead-link-lint-is-a-warning"
description: "where an unresolved [[link]] in the memory corpus is named, and why lint cannot say \"undrained\""
tier: 2
knowledge_scope: full
distilled_at: "2026-11-05"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 8cc3a8b9e6f05ba2
---

## where an unresolved [[link]] in the memory corpus is named, and why lint cannot say "undrained"

Two readers name a `[[link]]` or `*References:*` topic that resolves to no slice, both built on
`tools/fabric/assembler/links.py` (#473, python-dev-02's j112):

- the drain: `last-drain-report.json` `unresolved_links`, only the slices that run wrote, with `undrained` taken
  from the harvest's `skipped_no_roles_class`;
- lint: `lint_rules/slices.link_warnings`, the whole committed corpus, one WARNING per slice, never a finding
  (j565, commit 4ef8eb9e on #485's branch). Lint reads no harvest, so an undrained target shows as `no such topic`.

At the rule's start the corpus held 235 such slices (302 links), so turning it into a finding would go red at once;
a ratchet (fail only on new ones) is the next step if the count does not fall. A test fixture's links must sit
under a `## ` heading: `parse_slice` reads no link outside a section.
Related: [[drain-multi-pass-procedure]].

*References: drain-multi-pass-procedure, link*

*Anchors: `tools/fabric/lint_rules/slices.py::def link_warnings`, `tools/fabric/assembler/links.py::def unresolved_links`*

*Observed 2026-11-04 (fabric-coordinator)*
