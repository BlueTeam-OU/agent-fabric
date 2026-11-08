---
role: "python-dev"
class: solution
topic: "j108-stripped-nightly-five-suites-merged"
description: "A test green locally can be red on the stripped nightly runner (ubuntu-26.04 bwrap and sleep differ): dispatch the nightly on the branch; a boundary-arm word must be a header"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 988948d41735404d
---

## A test green locally can be red on the stripped nightly runner (ubuntu-26.04 bwrap and sleep differ): dispatch the nightly on the branch; a boundary-arm word must be a header

BlueTeam-OU/agent-fabric#461 merged (6 work, 1 fix), tests/ only. Causes: test_control_ctl (parse_args checks pool-add's role against identities/roles/catalog.json; Help.setUp patches ctl.check_pool_args with known={"python-dev"}); test_cpu_lease (installer case copied policies/host-load.json; writes its own); test_harvest_memory (named anchors need projects/registry.json ids; run() passes AGENT_FABRIC_OPERATOR=fixture tree; layout.project_ids() returns [] silently on unreadable registry, production, not fixed); test_self_kill_guard (stand-in was a symlink to /bin/sleep named gzcoord-inbox; dead on the ubuntu-26.04 runner; now `exec -a` like the sibling); test_review_mcp (runner bwrap words the tmpfs-on-dangling-link refusal "Can't mount tmpfs on /newroot/mnt/link: No such file or directory", no "symlink"; control matches the path).

**Why:** a case that passes locally can still be red on the runner: the stripped nightly runs on ubuntu-26.04 with different coreutils/bwrap. Dispatch it on the branch (`gh workflow run stripped-nightly.yml --ref <branch>`) and put a temporary diagnostic in a check label to read the real message.

**How to apply:** `fabric-pr post-review` of my own reviewer's report is refused by the classifier (Self-Approval): the owner posts it with `!`. A boundary file (tests/test_self_kill_guard.py) under 8 work arms only with the coordinator's REPLY whose metadata header (not body) carries `AUTHORIZES: <repo>#<n>@<head>`; pass its id with --authorization. A re-review request must leave previous_findings out.

*Anchors: `tests/stripped_run.py::KNOWN_RED`, `tests/test_review_mcp.py::sandbox_cases`, `tests/test_self_kill_guard.py::main`*

*Observed 2026-11-03 (python-dev)*
