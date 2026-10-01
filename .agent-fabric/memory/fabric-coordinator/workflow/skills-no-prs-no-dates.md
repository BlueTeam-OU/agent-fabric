---
role: "fabric-coordinator"
class: workflow
topic: "skills-no-prs-no-dates"
description: "Writing or changing a SKILL.md: load the skill-creator skill first and follow it; never cite a PR number, an incident date or a project name inside a skill — the skill states the rule and the procedure, the docs and the commit carry the…"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-01"
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
  - 4b062cd74be851b9
---

## Writing or changing a SKILL.md: load the skill-creator skill first and follow it; never cite a PR number, an incident date or a project name inside a skill — the skill states the rule and the procedure, the docs and the commit carry the evidence

A skill is procedure for the session that loads it, on every account,
in every project. It never cites a pull request, an incident date or a
managed project: that is evidence, and evidence lives in `docs/` (a
note), the spec's prose, or the commit message. Before writing or
editing any `SKILL.md`, invoke the `skill-creator` skill and follow its
structure; do not edit a skill's text freehand.

**Why:** on 2026-09-19 I added a step to the gzcoord-receive skill that
read "(2026-09-19, gzapp #897 and #899)". The corpus lint refused the
project name in a generic file; the owner refused the PR citation and
the date and said the skill-creator skill would have told me so.

**How to apply:** `Skill(skill: "skill-creator")` before touching
`communication/gzcoord/skills/*/SKILL.md` or any role's skills; put the
story in `docs/<concept>.md` and reference the doc from the skill only
where the skill needs a pointer. See [[blind-review-loop]] for where
the review evidence goes (the PR), [[local-grep-is-ugrep]] for the
lint-before-push habit.

*References: blind-review-loop, local-grep-is-ugrep*

*Observed 2026-09-19 (fabric-coordinator)*
