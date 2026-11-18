---
role: "python-dev"
class: workflow
topic: "j251-test-speed-merged-632"
description: "j251 merged in #632 (with j249): which suites had waiting vs CPU to cut, the MODE_POLL_S seam, boundary arm needs AUTHORIZES even with an earlier word"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 43f49ece0c1d5f7c
---

## j251 merged in #632 (with j249): which suites had waiting vs CPU to cut, the MODE_POLL_S seam, boundary arm needs AUTHORIZES even with an earlier word

Merged #632 (3 work, 1 fix) on head 7b508583. test_project_import: lint.py x2 as Popen side by side (113 -> 76 s wall, CPU up 108 -> 123). test_gzcoord_transport_mode_watch: seam GZCOORD_MODE_POLL_S (default 5.0), 85 -> 24 s, CPU same. test_launch_cli (97 s alone, ~14 production subprocesses per launcher run), test_secret_store (gpg calls, flock retry loop = no waiter event), test_githook_pre_commit (139 runs of the production hook): CPU-bound on production work, nothing to cut; coordinator chose leave.
**Why:** a baseline taken under load lies (launch_cli read 372 s, 97 s alone); measure wall AND CPU alone, same load, before from a HEAD~1 copy.
**How to apply:** profile first with a subprocess-timing wrapper (per-group for section_groups suites); a sleep-bound suite (CPU << wall) is where a test-only seam pays. An earlier "arm below minimum" word does not cover a security-boundary path (ctl.py): arm needs a REPLY with `AUTHORIZES: owner/repo#N@head` header per head, id via --authorization; ask after the clean review. Gate on the real head: merge origin/main, push, then review.

*Anchors: `tools/fabric/gzcoord/inbox.py::GZCOORD_MODE_POLL_S`, `tests/test_gzcoord_transport_mode_watch.py::POLL_S`*

*Observed 2026-11-17 (python-dev)*
