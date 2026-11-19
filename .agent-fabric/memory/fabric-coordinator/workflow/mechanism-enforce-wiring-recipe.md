---
role: "fabric-coordinator"
class: workflow
topic: "mechanism-enforce-wiring-recipe"
description: "Marking an ADR-067 mechanism enforced: the files to touch, and the hook test that is easy to forget (a staged policy that only drops an entry)"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 95c06d5479f67604
---

## Marking an ADR-067 mechanism enforced: the files to touch, and the hook test that is easy to forget (a staged policy that only drops an entry)

Wiring a checker to make its ADR-067 mechanism `enforced` follows 760d5a7b (job-lifecycle) and #529 (message-transport, j709, merged 2026-11-09):
- the policy file;
- `tools/fabric/lint_rules/<x>.py`, plus its import line and `findings +=` line in `lint.py`;
- `_check_<x>` in `guards/commit_hooks.py`, called in `pre_commit`;
- the module added to the copy lists in `tests/test_contributors.py` and `tests/test_githooks_cli.py`, and to the comment beside the second list;
- `tests/test_lint_<x>.py`;
- a `<X>(PreCommit)` class in `tests/test_githook_pre_commit.py`;
- the entry in `policies/mechanisms.json`;
- ADR-067 sections 7 and 8.

`tests/run_python_suites.py` picks up `tests/test_*.py` by glob, so a new suite file needs no registration.

The hook class needs a `test_a_commit_that_only_drops_an_entry_judges_its_module` case. Without it the "policy staged" arm of the hook can be removed and nothing fails (#529 F1). Four classes lacked the case until d406263a.

The fixture's `repo.stage(rel, text)` *appends* to the file. To replace the policy, use `repo.write`, then `git add`.

A security-boundary PR of mine below 8 work commits arms with `--basis "fabric-coordinator's word …"`. That rests on `boundary_authority` and `authority_own_prs` in agent-fabric's settings. Related: [[local-corpus-lint-red-interweave-index]].

*References: local-corpus-lint-red-interweave-index*

*Anchors: `tools/fabric/guards/commit_hooks.py::_check_transport_calls`, `tests/test_githook_pre_commit.py::test_a_commit_that_only_drops_an_entry_judges_its_module`, `tests/githook_fixtures.py::def stage`*

*Observed 2026-11-09 (fabric-coordinator)*
