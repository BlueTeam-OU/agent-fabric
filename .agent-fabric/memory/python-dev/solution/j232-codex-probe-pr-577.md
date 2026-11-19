---
role: "python-dev"
class: solution
topic: "j232-codex-probe-pr-577"
description: "j232 (#577) Codex probe + unavailable statements — where it stands, the http.client/watchdog traps the review found, how the re-review brief was pasted"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - bd3d1df46d78fb77
---

## j232 (#577) Codex probe + unavailable statements — where it stands, the http.client/watchdog traps the review found, how the re-review brief was pasted

j232 (REQUEST 01a1d152, owner 2026-11-12: "the Codex review never blocks an arm"): #577, branch
`develop-qzapp/python-dev-01/feat/j232-codex-probe-never-blocks`, head 3d264a75, REPLY seq 1071214.
1 work + 2 fix commits, under the arming minimum: arm needs the owner's word. Round 3 of the blind
review has no finding; full `tests/run.sh all` green with CI's environment. Left: the almalinux
platform-smoke timing check in `tests/test_trial_merge.py` (8.3 s vs a grace bound; not in the diff)
was rerun; the coordinator commits the ADR-053 wording and the README/schema text.

**Merged 2026-11-13** on the owner's word ("arm 577"), 1 work + 2 fix. Arm sequence: `fabric-jobs start j232`
first (the hook refuses arm once the job left active), then `fabric-pr arm 577 --basis "the owner's word ..."`;
an open P3 from an earlier head blocks until `--defer "<head8 of the finding's review>:F5" "<why>"` names it
(the head the finding was raised on, not the current one). Then INFO to the coordinator, `fabric-jobs done`.

**Traps the review found (field, reusable):**
- `http.client` quotes the whole header in its `ValueError` for a CR/LF in a header value: a key with a
  trailing newline leaks the secret on stderr. Refuse the value at the settings boundary without echoing
  it; redact the key from any backend text *before* classifying it, not only on the error path.
- A per-read socket timeout is reset by every byte; a whole-call deadline is a `threading.Timer` that
  shuts the socket. The timer and the read's own timeout then race: the shutdown surfaces as an empty
  chunk, an OSError, or (TLS) ValueError/AttributeError. Make the timer set an Event *first* and treat
  the Event as the only evidence of the deadline in every handler, else the reason flips by a coin toss.
  The test must loop (6 runs) because the wrong reason shows about two runs in three.
- Equivalent mutants: two guards covering one input survive alone; plant both at once to show the test.
- A scripted ADR/doc claim that "nothing is posted" outlives a behaviour change in README and schema
  text outside the entry: grep for the old sentence across the repo before the first review.

**Process:** a re-review brief is pasted into the Agent prompt verbatim; transcription slips (a typo in
a diff line, a dropped locator) cost nothing here but are the author's error — copy, don't retype. `fabric-review next`
needs `card_base` in the request when the range base is `origin/main`.

*Anchors: `tools/fabric/review_codex.py::_expire`, `tools/fabric/review_codex.py::probe`, `tests/test_review_codex.py::stall`*

*Observed 2026-11-13 (python-dev)*
