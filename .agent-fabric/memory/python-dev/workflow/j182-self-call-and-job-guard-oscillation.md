---
role: "python-dev"
class: workflow
topic: "j182-self-call-and-job-guard-oscillation"
description: "A text-replace helper inserted before the block it replaced turned a helper into a self-call that mocked tests hid; and starting a second job in a session that worked one blocks every commit"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 799041945aa5ccee
---

## A text-replace helper inserted before the block it replaced turned a helper into a self-call that mocked tests hid; and starting a second job in a session that worked one blocks every commit

Two traps from the #413 follow-ups on repo-policy apply (branch develop-qzapp/python-dev-01/for/user/repo-policy-apply).

1. I extracted `_registry_and_clients` out of `arm_policy.load` with a script that inserted the new helper first and then `str.replace`d the old block with a call to it; the old block it found was already inside the new helper, so the helper's whole body became a call to itself (RecursionError on every real plan/verify/apply). 50 tests passed because the Source tests patched the helper. **Why:** a test that mocks the function it claims to cover proves nothing, and I never ran the real `bin/fabric-repo-policy plan` before delivering. **How to apply:** after any scripted refactor read the diff of the touched function, and run the real command once (`AGENT_FABRIC_PYTHON=$(which python3) ./bin/fabric-repo-policy plan <repo>`) before sending a delivery REPLY. Patch the files a helper reads (workingcopy.load_registry, the clients read), never the helper.

2. The jobs commit guard (ADR-037 rule 3) records the jobs a session has worked. After j180 was delivered and j181/j182 arrived as follow-ups on the same branch, `fabric-jobs start`/`pause` between them made every `git commit` fail ("worked job X, which has left active; Y is active"), alternating whichever I made active. The hook reads the whole command, so a `pause && commit` chain is refused before the pause runs. **How to apply:** commit follow-ups in the session while the job that worked the branch is the only one started (reopen it with `fabric-jobs start` once, before the first edit); if the guard has already fired, save `git diff HEAD --binary` to a patch under ~/agent-fabric-tmp, restore the tree, send an interim REPLY, pause from the branch's own checkout, and let the fresh session apply the patch. Related: [[job-hook-commit-in-main-checkout-works]].

State when j182 was paused (2026-10-28): the F5/F6 fix (`arm_policy.load_with_source`, one registry reader, tests patching `workingcopy.load_registry`) is the patch `~/agent-fabric-tmp/j182-f5-f6.patch` against c3f4e8a9, applies clean (`git apply --check`); to land it: start j182 from the worktree, `git apply`, run the suite, commit with `Answers: #413 F5 F6`, push, REPLY to the coordinator's request 01a180e2 with the first lines of a real `plan BlueTeam-OU/agent-fabric`.

*References: job-hook-commit-in-main-checkout-works*

*Anchors: `tools/fabric/github/arm_policy.py::_registry_and_clients`, `tools/fabric/github/repo_policy.py::describe_source`*

*Observed 2026-10-28 (python-dev)*
