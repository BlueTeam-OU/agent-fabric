---
role: "fabric-coordinator"
class: workflow
topic: "addenda-reissue-parent-builds"
description: "Re-issuing holder addenda (against_digest only) — the parent builds the files from its mirror; a holder's auto mode may refuse writing them"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - b1de60b437771ea9
  - cdffaa3f13d25f67
---

## Re-issuing holder addenda (against_digest only) — the parent builds the files from its mirror; a holder's auto mode may refuse writing them

On 2026-10-18 a holder's auto mode refused writing its own re-issued addendum file ("Instruction Poisoning": an
agent writing text installed into its own launch prompt).

What works for a frontmatter-only re-issue: build each set from `git show HEAD:settings/roles/<role>/*.md` on
my mirror of the child's store, change the against_digest line, confirm the diff is that one line, and check
the sha256 against the one the holder reports in its REPLY. Then `fabric-secrets store refresh-mirror <login>`
and `fabric-secrets child roles-put --agent <login> --role <role> --from <dir> --approval <ref>
--authored-by <login>`. A body change needs the owner first; a non-English set needs language-culture-<key>'s
two passes over the new file sha256s (`--reviewed-by`).

**Why:** holders cannot always write the files; the parent is the installer anyway (ADR-060 §5 rule 3).

**How to apply:** ask holders to verify and report sha256s, never to write the files into a shared directory;
a file that must travel goes by REPLY ([[artifact-handoff-by-reply]]). Build from the mirror. Related:
[[holder-addenda-plan]].

*References: artifact-handoff-by-reply, holder-addenda-plan*

*Anchors: `tools/fabric/secretstore/roles.py::roles_put`, `tools/fabric/secretstore/roles.py::refresh-mirror`*

*Observed 2026-10-23 (fabric-coordinator)*
