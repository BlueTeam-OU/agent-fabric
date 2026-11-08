---
role: "python-dev"
class: solution
topic: "moveto-stop-and-codex-default-j104-j105"
description: "j104/j105 #450 — WUNTRACED wait with Popen, codex coverage default, ruff before push, shared TMPDIR msg.txt trap"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "python-dev-03"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 4020fc41e6b4483d
---

## j104/j105 #450 — WUNTRACED wait with Popen, codex coverage default, ruff before push, shared TMPDIR msg.txt trap

#450 (merged): `moveto.wait_for_exit` waits with `os.waitpid(pid, WUNTRACED)`, stops moveto with SIGSTOP when ssh stops (`~^Z`), sends ssh SIGCONT on resume. `Popen.send_signal` polls first and can reap the child behind the raw waitpid, so `except ChildProcessError: return proc.wait()` is required (review F1, P2); the remote's terminal modes are left on at a stop on purpose. `review_codex.COVERAGE_SHAPE` is followed by `DEFAULT_SHAPE` only when the schema's coverage object lists `default`; `answer_coverage` carries a non-null default into the block, null/absent adds no key. The schema (nullable `anyOf`) and lint's stdlib validator are the coordinator's; tests hide jsonschema via `sys.modules["jsonschema"] = None` to prove the stdlib path.

**Why:** traps that cost rounds: (1) I ran `lint.py` but not `ruff check .` before pushing, and CI `static` failed on F841 — a new head, so another review round; (2) a mutation that shows 0 failures is a test that cannot fail — two guards (returncode check and the except) covered each other, so drop the redundant one; (3) `gzcoord-compose -o $TMPDIR/msg.txt` refuses an existing file and `gzcoord-send` then sent the OLD file — write messages to the scratchpad and read the compose output; (4) `fabric-review next` needs `--pr` and a saved round (`fabric-review save N R < report`) and later rounds take the previous `req-rrN.json`; (5) a review binds to one head, so fix known lint/ruff first; (6) the dispatch prompt must be the whole brief verbatim — read the file in full, do not abbreviate.
**How to apply:** `ruff check .` + `lint.py` before every push; run mutations from a script that restores the files and prints counts; check the scratchpad file name before `gzcoord-send`.

*Anchors: `runtime/provisioning/moveto/moveto.py::wait_for_exit`, `tools/fabric/review_codex.py::answer_coverage`*

*Observed 2026-11-01 (python-dev)*
