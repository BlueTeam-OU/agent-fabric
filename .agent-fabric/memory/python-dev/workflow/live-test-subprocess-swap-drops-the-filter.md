---
role: "python-dev"
class: workflow
topic: "live-test-subprocess-swap-drops-the-filter"
description: "Replacing an in-process call with the CLI subprocess in a test loses the caller's filter and env override; arm refuses a carried P3 until --defer"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-04"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 93e787b75427d4d5
---

## Replacing an in-process call with the CLI subprocess in a test loses the caller's filter and env override; arm refuses a carried P3 until --defer

j122 (#601): the #598 fix swapped `roster.render_config(r, good, ...)` for `gzcoord-carrier render-config` in the live two-account test; that rendered the whole roster and read GZCOORD_CARRIER_ROSTER. Fix was to call render_config on the judged pair with own_host from `make_me().address.split("/")[0]`.

**Why:** a subprocess replacement is a new seam; check what the old call's inputs filtered. A narrowed `except` (RosterError only) also lost the old catch-all of a subprocess failure: mirror cmd_run's tuple (RosterError, JournalError, OSError, ValueError).

**How to apply:** `fabric-pr arm` refuses while a P3 is open even with the owner's word; carry it with `--defer "<head8>:F<n>" "<why>"` plus `--basis`. Post-review needs the bare command with the report on stdin. See [[defer-label-is-the-raising-head-not-the-chain-head]].

*References: defer-label-is-the-raising-head-not-the-chain-head*

*Anchors: `tests/live_interweave_two_accounts.py::phase_serve`*

*Observed 2026-11-14 (python-dev)*
