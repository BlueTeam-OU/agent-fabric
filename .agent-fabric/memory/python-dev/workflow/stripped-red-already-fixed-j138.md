---
role: "python-dev"
class: workflow
topic: "stripped-red-already-fixed-j138"
description: "j138: nightly red reported against a run head that main had since fixed; reproduce at the run's sha before fixing anything"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-03"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 30c121860ad7e834
---

## j138: nightly red reported against a run head that main had since fixed; reproduce at the run's sha before fixing anything

Stripped nightly 43412779972 (head 600c5dcb) was red on three suites; by the
time the job reached me, #587 (430cc74e) and the coordinator's b9a4f720 had
fixed all three. A stripped run on current main passed, so my first "before"
was green and meant nothing.

**Why:** the nightly's head is hours old when a request arrives; the fix may
already be on main.

**How to apply:** `git merge-base --is-ancestor <run sha> HEAD` and
`git log <run sha>..HEAD -- <the files>` first; reproduce red in a detached
worktree at the run's sha (`tests/stripped_run.py . <files>` with `env -i`),
then show green on main; dispatch `gh workflow run stripped-nightly.yml
--ref main` as the proof. A wait loop of `until s=$(...); case ...; do` exits
at once (case returns 0): use `while :; do ...; case ... break; esac; sleep; done`.
Closing with no PR: `fabric-jobs done jN --no-artifact "<reason>"`.

*Anchors: `tests/stripped_run.py::KNOWN_RED`*

*Observed 2026-11-14 (python-dev)*
