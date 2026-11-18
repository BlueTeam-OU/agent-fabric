---
role: "python-dev"
class: solution
topic: "repoint-armed-needs-disarm-on-push-check"
description: "j105 (#536): switch --repoint keeps an armed PR only where the repo has disarm-on-push.yml on default or a ruleset requiring fabric/armed; fail closed"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-04"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 3ab794c2c8515633
---

## j105 (#536): switch --repoint keeps an armed PR only where the repo has disarm-on-push.yml on default or a ruleset requiring fabric/armed; fail closed

`tools/fabric/jobsparts/branching.py::_no_disarm` (#536, 2026-11-09): for an armed PR only, `--repoint` reads
`contents/.github/workflows/disarm-on-push.yml?ref=<default>` (accepted only as a dict of type file) and
`rules/branches/<default>` (a required_status_checks rule naming fabric/armed). Neither, or either unreadable: refuse as before #526.
Coordinator's survey: only gzapp, agent-fabric, InterWeave have the workflow; others have neither.

**Why:** the note "the first push disarms it" is true only where one of the two exists.
**How to apply:** tests fake `branching.vcs.gh.api` and must restore it after the j105 cases; a workflow answer's shape is checked, not just its success.
Arm minimum in agent-fabric was 1 work commit (read from `arm --dry-run`); a `Answers:` fix commit does not count.
Reviewer risks left open: a disabled workflow counts as present; ruleset-only repos get the inaccurate "disarms" wording; rules not paginated.

*Anchors: `tools/fabric/jobsparts/branching.py::_no_disarm`*

*Observed 2026-11-09 (python-dev)*
