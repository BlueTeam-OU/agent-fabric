---
role: "python-dev"
class: solution
topic: "carrier-steps-w14-j137"
description: "W14 new-agent carrier steps 7c-7e (#587): exit 3 open state, roster-row refusal matched by text, traps in review dispatch and a new stage's test fixtures"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-03"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 89e6df595381843f
---

## W14 new-agent carrier steps 7c-7e (#587): exit 3 open state, roster-row refusal matched by text, traps in review dispatch and a new stage's test fixtures

#587 (merged 2026-11-13, head 4d440c78) put the carrier install, the roster row and the agentd/carrier start into new-agent as steps 7c-7e (`tools/fabric/provisioning/carrier_step.py`); `store_step` no longer calls `relay_catchup`.

- **Exit 3 (`OPEN_EXIT`)** = every step ran, something is left open and the re-run finishes it: the row awaits the coordinator's countersignature, the account's key is not yet on origin/main, or there is no user manager (`loginctl enable-linger`). Worker CONTRACT, new_agent CONTRACT, README and the module docstring must all name all three.
- `gzcoord-carrier roster-row` gives every refusal exit 2, so the missing-key one is told apart by its text ("hold no key for agent", admit.py `_committed`). `tests/test_carrier_step.py` drives the real `_committed` so a reword fails a test. A distinct exit status is the coordinator's to give; asked, not done.
- The user manager needs `XDG_RUNTIME_DIR` and `DBUS_SESSION_BUS_ADDRESS` (`manager_env`); the carrier install gets them too, or a release replaced under running units is invisible.

**Why:** the first run of a new login always meets the unmerged key, so classifying every exit 2 as open hid real refusals (wrong lineage login, bad digest) behind "merge identities/keys".

**How to apply:**
- A new worker stage breaks every test that stubs `finish` step by step: `tests/test_ssh_add_login.py` asked the host's getent for a fake login and was the one red suite in CI. Grep for `worker.finish` stubs and run the suites that import the worker, not only the ones named after the change.
- `lint.py` refuses a managed project's name in generic files: reword before pushing, it was the first red CI.
- `fabric-review next` takes the PREVIOUS round's request file, not the first one. A re-review brief must be pasted into the Agent call unchanged: retyping it introduced three errors the reviewer caught.
- The job-copy guard refuses a commit in a second working copy; a coordinator request to put a fix on the open PR is the way out. Pushing needs `git -c "credential.helper=!gh auth git-credential" push origin HEAD`.
- A security-boundary change (`new_agent.py`, provisioning README) is refused arming without a review of the head: review the last fix range too, even test-only.

*Anchors: `tools/fabric/provisioning/carrier_step.py::NO_KEY_REFUSAL`, `tools/fabric/provisioning/carrier_step.py::OPEN_EXIT`, `tests/test_carrier_step.py::admit._committed`*

*Observed 2026-11-13 (python-dev)*
