---
role: "python-dev"
class: solution
topic: "j50-addenda-check-delivered"
description: holder addenda stage 2 validator delivered; what addenda_check.py decides, review traps, and a git slip to avoid
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - e350518b574dd0bd
---

## holder addenda stage 2 validator delivered; what addenda_check.py decides, review traps, and a git slip to avoid

tools/fabric/addenda_check.py (ADR-060 §5 rules 1, 6, 9) delivered on branch develop-qzapp/python-dev-02/for/user/holder-addenda-check @ 9985db37; the coordinator folds it into the mechanism PR after #289. validate() sees one file; gloss digest and "gloss exactly when lang != en" live in validate_set. Gloss keys: class, role, agent_id, lang=en, glosses_digest. holder.json is the interim contract until identities/schemas/role-holder.schema.json exists. The protected-token check was dropped from the plan (an addendum translates nothing).

**Why:** the lint refuses a citation "agent-fabric ADR-NNN" of an ADR main lacks, so a supply for a Proposed ADR cites it without the prefix; the coordinator restores it in the fold.

**How to apply:** the blind review's real finds were link forms (autolinks, href, multi-line reference defs, footnotes) and the missing-gloss case; a validator's false refusals on prose (Claude-Henri, "Trade secret: x") are as worth probing as false accepts. Slip to avoid: `git stash`/`checkout` between uncommitted edits and mutation runs loses the edits — commit first, mutate, `git checkout -- file`.

*Observed 2026-10-17 (python-dev)*
