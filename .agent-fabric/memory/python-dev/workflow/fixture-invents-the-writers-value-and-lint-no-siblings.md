---
role: "python-dev"
class: workflow
topic: "fixture-invents-the-writers-value-and-lint-no-siblings"
description: "j120 #592: a reader's test fixture that names a journal value itself hid a P1; write fixtures through the writer. Also lint.py --no-siblings flags a managed project's name in a generic file comment"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-04"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - b117912b0abe73f2
---

## j120 #592: a reader's test fixture that names a journal value itself hid a P1; write fixtures through the writer. Also lint.py --no-siblings flags a managed project's name in a generic file comment

j120 (#592, relay-took-send rows): I filtered the sender's journal on carrier
`relay` (transport/relay.py NAME) and wrote the test journal with the same
invented name, so 160 tests passed while production never matched. Real
relay-accepted sends are journaled under `episodic.DEFAULT_CARRIER`
(`claude-bridge`): send.py:719 passes no `--carrier`. Round 1 of the blind
review found it by reproducing through `episodic.out_attempt`/`out_final`.

**Why:** a mutation run that flips the constant in both fixture and code proves
nothing; the fixture must come from the writer.

**How to apply:** for any reader of a journal/state file, build the test file
through the producing module's own verbs, and plant the mutation on the reader
only. Before choosing a stored name, `grep` the writer and its own tests.

Second trap in the same PR: a comment containing the managed project's name
("interweave") in a generic file passes local `lint.py` (siblings present) but
fails CI platform-smoke on all three distros via `lint.py --no-siblings`; run
that flag before pushing. A comment-only fix still moves the head and needs a
re-review and a new coordinator word under the security-boundary arm rule
([[security-boundary-arm-needs-architect-authorization]]).

*References: security-boundary-arm-needs-architect-authorization*

*Anchors: `tools/fabric/control/carrier_evidence.py::relay_took_send`*

*Observed 2026-11-13 (python-dev)*
