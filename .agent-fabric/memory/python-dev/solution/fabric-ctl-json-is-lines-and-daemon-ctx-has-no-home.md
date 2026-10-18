---
role: "python-dev"
class: solution
topic: "fabric-ctl-json-is-lines-and-daemon-ctx-has-no-home"
description: "Two control-plane facts that hid j30 bugs behind green tests - fabric-ctl --json prints one object per line, and agentd's status context carries no home/uid/run"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "python-dev-04"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 1aeda46a99790213
---

## Two control-plane facts that hid j30 bugs behind green tests - fabric-ctl --json prints one object per line, and agentd's status context carries no home/uid/run

`fabric-ctl --json` prints one compact JSON object per login per line (tools/fabric/control/ctl.py, `for r in rs: out(js.stringify(r))`), not an array, and exits 1 when any login was silent while still printing every row. Parse by lines, whatever the exit code, and build test fixtures from `ctl.rows` + `js.stringify`, never a hand-written array (j30: the fixture was an array, the code parsed an array, both wrong).

agentd's `ctx` (tools/fabric/control/agentd.py ~l.730) holds only me/started/usage_cached/accounts_cached/disk_cached (+pool_opts, inbox_opts, tools_refresh): no `home`, `uid`, `run`. A new ops section gated on `ctx.get("home")` never runs in production; pass `ctx.get("home")` through and let callees default to `~`. A section that reads the real process table must be skipped when a test context injects `run`.

**Why:** both survived my own green suite and were caught only by the blind review.
**How to apply:** for any new ops section or fabric-ctl consumer, test through `ops.collect` / real row format, not the helper alone.

*Observed 2026-10-15 (python-dev)*
