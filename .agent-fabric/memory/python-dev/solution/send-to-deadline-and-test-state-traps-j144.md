---
role: "python-dev"
class: solution
topic: "send-to-deadline-and-test-state-traps-j144"
description: "j144 #617 — a deadline that starts after the work it bounds, a test that wrote the login's real transport-mode.json, an oracle that pins a log line, review/arm traps"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-03"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - f2d7a5978fcdecad
---

## j144 #617 — a deadline that starts after the work it bounds, a test that wrote the login's real transport-mode.json, an oracle that pins a log line, review/arm traps

j144 (#615, #617, merged 2026-11-16): the "fabric-ctl's connection is not reading (Broken pipe)" line.

- **Cause.** fabric-ctl closes: its `wait_sent(budget+5)` ran out because agentd's `Carrier.send_to` started its deadline AFTER all hand-overs, and a slowly draining child made 29 of them take tens of seconds. Fixed by starting the deadline before the first hand-over (late ones are not made, `OUT_OF_TIME`). A hand-over is not cut by the budget (a cut line leaves half a line in the child's pipe and `Child._write` ends the child as wedged), so waiters allow `budget + WRITE_WAIT_S + 2` (ctl.py, `Leg.open`). The `_write_lock` wait is still unbounded (pre-existing, carried).
- **UUIDv7 `rid[:8]` is the clock** (~65 s): two requests of one minute print the same, so "answered twice" lines cannot be told from two requests. The tail is random.
- **An oracle pinning a log line decides the fix's shape.** `tests/test_control_agentd.py` pins `(<8 hex>)` then `: current`. Putting the tail inside the brackets failed it in the full suite; the tail went to the end of the line (`id_tail`), the oracle stayed unchanged.
- **A test wrote the login's REAL `transport-mode.json`.** `mode.write(mode, set_by, state_dir=None)`: I passed the scratch dir as `set_by`, so `state_dir=None` wrote `agent_state_dir()`. Always pass the explicit state dir and `set_by`; prove the real file's mtime is unchanged after the suite. fabric-coordinator reset it (relay-record is also what a missing file means); a test never guesses a state value back.
- **A test that calls an op reading a socket reaches the login's live socket** when `XDG_RUNTIME_DIR` is set (`position.stranded`): pass `inbox_carrier_opts: {"runtime_dir": "/nonexistent-runtime"}`.
- **A mutation loop that restores with `git checkout` wipes uncommitted work.** Stage (`git add`) the change first; `git checkout -- file` then restores the index copy. Never `git checkout` an uncommitted edit as the restore.
- **`gzcoord-compose` refuses an existing `-o` file; the script's following `gzcoord-send` then re-posts the OLD file.** Use a fresh name per message; read the compose line before sending.
- **A hook reads `$HOME` in the same command as `git commit`/`git push` as outside the job's copy.** Split the command; do not put `HOME="$HOME"` in the commit command.
- **Full-suite flake while another heavy agent runs:** one `test_control_agentd` `--once` case lost a reply (KeyError `frozen-1`) with the review agent running beside the suite; 3/3 alone, quiet full rerun passed. Cause not shown; do not run a suite and a review dispatch together.
- **Review/arm:** `fabric-review next REQUEST --pr N --head H` needs the request's range pinned to commit ids (`<base>..<head>`, not `HEAD`); `fabric-review save N ROUND < report` first. The security-boundary minimum was 8 work commits (the dry-run says; here it armed without the owner's word at 9).
- **Gate-2 test of carrier-only** (`tests/test_gzcoord_carrier_only_gate2.py`): five functions pass with the relay's port closed; `send` fails on the presence check (`send.py:578` → `presence.py:104/:127`), held as a named KNOWN GAP until python-dev-04's j130 lands, then it becomes a plain pass.

*Anchors: `tools/fabric/gzcoord/carrier/control_link.py::send_to`, `tools/fabric/gzcoord/carrier/control_link.py::id_tail`, `tools/fabric/gzcoord/transport/mode.py::write`, `tests/test_gzcoord_carrier_only_gate2.py::known_gap`*

*Observed 2026-11-15 (python-dev)*
