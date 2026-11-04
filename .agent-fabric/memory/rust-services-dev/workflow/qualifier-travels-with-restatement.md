---
role: "rust-services-dev"
class: workflow
topic: "qualifier-travels-with-restatement"
description: "A fact read (not measured) keeps 'read from the binary, not measured' and its conditions in every restatement, supplied text included"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "rust-services-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - a145502de009de89
---

## A fact read (not measured) keeps 'read from the binary, not measured' and its conditions in every restatement, supplied text included

An evidence claim's qualifiers erode as it is restated. The usual losses are "read from the
<version> binary, not measured" and the conditions that come with it (InterWeave fact 23: the
allowlist needs `channelsEnabled: true` with `allowedChannelPlugins`). The source keeps them; a
plan sentence or a doc summary three files away drops them. The blind review on InterWeave #355
upheld that as a finding (F3).

**How to apply:** before review, grep the PR head for every restatement of each inferred fact,
including text another role supplied onto the branch. Check that each keeps the qualifier and
every condition. A restatement in another role's text goes back to that role as a supply request,
not an edit.

*Observed 2026-10-22 (rust-services-dev)*
