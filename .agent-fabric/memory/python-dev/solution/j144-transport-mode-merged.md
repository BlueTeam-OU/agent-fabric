---
role: "python-dev"
class: solution
topic: "j144-transport-mode-merged"
description: "j144 W5 per-account GZCoord transport mode, PR 584 merged; traps for a suite that imports the protocol suite and for new in-process ctl suites"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 3ce40c4a66b8e08d
---

## j144 W5 per-account GZCoord transport mode, PR 584 merged; traps for a suite that imports the protocol suite and for new in-process ctl suites

PR 584 (merged, head 6f2af1bf): `tools/fabric/gzcoord/transport/mode.py` (state file `transport-mode.json`, absent = relay-record, damaged = ModeError never the default, bounded regular-file read, `Watcher`), `control/transport_mode.py` (signed op `<carrier>-mode`), carrier-only refusal in `fabric-ctl` from the fleet read.

**Why this matters:** two CI-only reds cost two review rounds, both from conventions living on main or in a helper suite, not in my tree.
- A suite that imports `tests/test_gzcoord_protocol.py` as `P` must remove `P.SCRATCH` itself in `tearDownModule`; `P` cleans only at the end of its own main(), and `tests/run.py` fails the whole run (not a named suite) on any scratch left under the run's TMPDIR.
- main's `test_run_control_carrier` requires every suite calling `ctl.main(`/`ctl.run(` to set `os.environ["FABRIC_CONTROL_CARRIER"]`; it appears only after merging origin/main, so a branch behind main passes locally.

**How to apply:** before the first push, merge origin/main and run the whole suite with a fresh TMPDIR, then `ls` it. A python-runner red with no named suite: split the log on `== tests/` blocks and print the block whose last line is not a verdict; `test_reads_live.py: FAILED` and `acme2claude-shim` FAIL lines are deliberate fixtures.

Open, carried P3s (named in the arming comment): mode.py contract text, ctl.py:682 comment scope, an overstated test message, one double print when the file breaks during a reopen. Backfill builds RelayTransport directly and ignores the mode (W6 to W8 to decide). `test_jobs_switch` and `test_control_agentd_dual` flake in CI and pass on rerun.

*Anchors: `tools/fabric/gzcoord/transport/mode.py::class Watcher`, `tests/test_run_control_carrier.py::FABRIC_CONTROL_CARRIER`*

*Observed 2026-11-13 (python-dev)*
