---
role: "python-dev"
class: solution
topic: "j233-journal-first-replay-merged-581"
description: "W3 merged in #581 — journal-first replay/history; what the review found, carrier-name facts, process traps"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 7b8c1e2a6b1e6408
---

## W3 merged in #581 — journal-first replay/history; what the review found, carrier-name facts, process traps

#581 (merge c31c36ba, 2026-11-13): `gzcoord-inbox --replay <message-id>` reads the account's journal first (`episodic.open_readonly`), `--history` lists the journal's non-relay rows after the relay's list, the journal alone where no relay answers. Code: `inbox_parts/records.py` (`_journal_select`, `_typed`, `journal_record`, `history_journal_only`), main in `inbox.py`; test `tests/test_gzcoord_journal_replay.py`.

Facts a next session needs:
- The inbox never journals carrier records: the carrier journals them itself with `carrier="interweave"`; `episodic.inbound` default carrier `claude-bridge` is always a relay row. A verified copy sets `sender_verified` and leaves `carrier` (first arrival) as it was, so never say "verified by <carrier>".
- SQLite stores any type in any column: type-check content, time, sender, carrier_seq (BLOB rows reached main's catch-all at exit 0).
- Relay history page is channel-wide newest 500; the journal's 500 reach further back, so "not in the relay's page" is not "carried another way".
- The new journal-row lines are untranslated: a dictionary key is outside python-dev's entry.

Process traps (**Why:** each cost a round): a docstring commit after the last review moved the head and arming refused ("needs a review of the exact head") — push every fix before the final post-review, and make the last range code-complete. `fabric-pr arm` count rule here was "1 or more"; an open P3 from round 1 needed `--defer "<head8>:F<n>"` even when out of entry. TaskStop on a background suite ends only the wrapper: kill the real pids (`kill <pid>`, a -f pattern is refused). A full suite waits behind other agents' lease for hours; CI gated the merge. Re-review chain: `fabric-review save` then `next <prev req json> --pr --head`, then `brief` the printed json.

*Anchors: `tools/fabric/gzcoord/inbox_parts/records.py::history_journal_only`, `tools/fabric/gzcoord/inbox_parts/records.py::_typed`, `tests/test_gzcoord_journal_replay.py::journal_files`*

*Observed 2026-11-13 (python-dev)*
