---
role: "python-dev"
class: solution
topic: "j176-running-pair-rerender-merged-394"
description: "interweave-start re-renders a running pair when the roster render differs (#394); design, traps, review loop cost"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 05ef5bf9be86808c
---

## interweave-start re-renders a running pair when the roster render differs (#394); design, traps, review loop cost

A daemon allowlists the peers of the roster its config.yaml was rendered from, so a new row (language-culture-ru) was refused as UnauthorizedPeer by the 29 running pairs. Merged in BlueTeam-OU/agent-fabric#394: `interweave-start` with both units running reads `render-config` (stdout, under the render lease), compares it with the file; identical = `already_running`, different/missing = port_range + reservation check, `roster.write_config`, restart both, `rerendered`. No new op or arg. Any later roster row reaches the fleet with `fabric-ctl all interweave-start`.

**Why:** every failure before the restart must say "both units still run on the previous config.yaml" and carry `units`; an unreadable port_range is `failed` (as on the start path), a missing reservation `refused`.

**How to apply:** the coordinator adds ADR/DIGEST commits onto the branch mid-review, so each head move needs a new blind review; post-review needs a v2 report file (write the subagent's report to the scratchpad), and a re-review mode only works after a first review is posted. A command mixing `$HOME` with `git commit`/`push` is refused by the job guard: use literal paths. See [[j175-held-roster-port]].

*References: j175-held-roster-port*

*Anchors: `tools/fabric/control/carrier_install.py::_render`, `tools/fabric/control/carrier_install.py::_config_differs`*

*Observed 2026-10-26 (python-dev)*
