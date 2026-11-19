---
role: "python-dev"
class: solution
topic: "self-status-js-stringify-j132"
description: "agentd --self writes js.stringify (raw non-ASCII); tests compare with js.stringify, not json.dumps; j62-j64 branches never became a PR"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-03"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 17b5e73ac8503d11
---

## agentd --self writes js.stringify (raw non-ASCII); tests compare with js.stringify, not json.dumps; j62-j64 branches never became a PR

#567 (j132): `agentd --self` prints `js.stringify(r, 2)`, which keeps non-ASCII raw like JSON.stringify; `json.dumps(indent=2)` escapes it, so the Wire --self test failed on a host whose status had "… and N more". Fixed by comparing with js.stringify; the injected case runs `agentd.main(["--self"])` in-process with `answer`, `gzcoord.whoami/identity`, `control_config` mocked and stdout a StringIO. Real stdout encoding under a non-UTF-8 locale stays untested (review risk).

**Why:** a test that recomputes expected output with a different serializer than the writer depends on host data.
**How to apply:** compare against the writer's own function; inject the awkward value rather than hoping the host has it.

Also: j62/j63/j64 (stripped skip list) were marked delivered on pushed branches that never had a PR; the coordinator found the four lines still in tests/stripped_skip.txt on main (2026-11-12). A "delivered" job needs the merge, not the branch. Pending: rebase the three branches (one commit each, ~2200 behind) into one PR. Almalinux CI flake: tests/test_jobs_switch.py "held: next is switch" (memory-dir-unchanged refusal) failed on main ab101b34 too; rerun passes. After post-review, `fabric-pr arm --dry-run` needs `--basis` to print; push needs `git -c credential.helper= -c 'credential.helper=!gh auth git-credential' push`.

*Anchors: `tests/test_control_agentd.py::test_port_self_writes_non_ascii_text_raw`*

*Observed 2026-11-12 (python-dev)*
