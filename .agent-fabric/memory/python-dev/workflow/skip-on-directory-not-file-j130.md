---
role: "python-dev"
class: workflow
topic: "skip-on-directory-not-file-j130"
description: "j130 #563 — a stripped-copy skip tests the directory (docs/adr/), never the file, so a deleted record in a full tree still fails; post-review from the session worked"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-03"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 8656fa05c09785b2
---

## j130 #563 — a stripped-copy skip tests the directory (docs/adr/), never the file, so a deleted record in a full tree still fails; post-review from the session worked

- A test that skips for a stripped copy checks the instance directory (`docs/adr/`, in `instance_fixtures.INSTANCE_PATHS`), not the one file it reads: a file check also hides a renamed or deleted record in a full tree. Mutation: move the ADR file away with the directory kept; the test must error.
- `fabric-pr post-review 563 < report` ran from the session this time (report written verbatim with the Write tool, subagent's indent removed).
- Delivering a job and then hearing "arm N" needs `fabric-jobs add` + `switch` (guard refuses `fabric-pr arm`); `switch` also wants a memory change first. Deliver with `'#563'`, not `pr:563`. Add the arm job before delivering when "arm" is likely.
- Push over https: `git -c credential.helper= -c 'credential.helper=!gh auth git-credential' push`.

*Anchors: `tests/test_work_table.py::Table.adr_rows`*

*Observed 2026-11-12 (python-dev)*
