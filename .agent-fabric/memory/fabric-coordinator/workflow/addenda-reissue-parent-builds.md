---
role: "fabric-coordinator"
class: workflow
topic: "addenda-reissue-parent-builds"
description: "Re-issuing holder addenda (against_digest only) — the parent builds the files from its mirror; a holder's auto mode may refuse writing them"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - b1de60b437771ea9
---

## Re-issuing holder addenda (against_digest only) — the parent builds the files from its mirror; a holder's auto mode may refuse writing them

On 2026-10-18 (after #293/#294 made the shared legal-expert and
language-culture texts final), language-culture-en's auto mode refused to
write its own re-issued addendum file ("Instruction Poisoning": an agent
writing text installed into its own launch prompt). Others wrote theirs
to /var/tmp/holder-addenda/reissue/<login>/ (made 1777 by me).

What worked: for a frontmatter-only re-issue, build each set from
`git show HEAD:settings/roles/<role>/*.md` on my mirror
(~/.local/share/agent-fabric/children/<id>), sed the against_digest line,
confirm the diff is that one line, and check the sha256 against the one
the holder reports in its REPLY. Then `fabric-secrets store refresh-mirror
<login>` and `fabric-secrets child roles-put --agent <login> --role <role>
--from <dir> --approval <plan ref> --authored-by <login>`. Installed:
language-culture-en d24f223, legal-expert-ee-eu 7caa73f, legal-expert-ch
0e7b5b3. A body change (legal-expert-ge's brief bullet) needs the owner
first; a non-English set needs language-culture-<key>'s two passes over
the new file sha256s.

**Why:** holders cannot always write the files; the parent is the
installer anyway (ADR-060 §5 rule 3).

**How to apply:** ask holders to verify and report sha256s, not
necessarily to write files; build from the mirror. Related:
[[holder-addenda-plan]].

*References: holder-addenda-plan*

*Anchors: `tools/fabric/secretstore/roles.py::roles_put`*

*Observed 2026-10-18 (fabric-coordinator)*
