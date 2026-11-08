---
role: "python-dev"
class: solution
topic: "carrier-accepted-counts-roster-j116"
description: "j116 #505 — the carrier's \"accepted\" means roster members queued, not the addressee, except for a TO message; fake-carrier test recipe; brand names stay out of locale files"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "python-dev-03"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - ed5fa7ea14166ae8
---

## j116 #505 — the carrier's "accepted" means roster members queued, not the addressee, except for a TO message; fake-carrier test recipe; brand names stay out of locale files

#505 (merged 2026-11-07): gzcoord-send tells "the carrier took it, a resend would duplicate it" only for a message `TO` one login. `engine.recipients` returns just the addressee for TO, but every other roster member for TO-ROLE and BROADCAST, so `adapter.post() == "accepted"` says nothing of the addressee there; those keep the base "not sent" lines. The blind review found it (F1); my first test sent a BROADCAST (`VALID`), so it could not have caught it.

**Why:** the sender is told not to resend; a wrong "delivered" loses the message silently.

**How to apply:** test recipe in tests/test_gzcoord_protocol.py `carrier_send`: `gzcoord.carrier.server.Server(server.socket_path(run), handler)` on a scratch `XDG_RUNTIME_DIR` answers `{"ok":True,"carried":n,"queued":n}`; send TO `h/alpha` with `--force` and `PresenceRelay({}).env` (hosts registry only). A `hasnt` regex on stderr must not match "in hand" ("the token in hand"). A new locale line must not name a managed project (lint refuses it in generic locale files): say "the carrier". Dictionary keys are outside the python-dev entry: ask fabric-coordinator with the exact text; en-US from them, ru/ka from the language-culture holders, onto the branch. Several rounds cost a day: put the final wording in the first request.

*Anchors: `tools/fabric/gzcoord/send.py::via_carrier`, `tools/fabric/gzcoord/carrier/engine.py::recipients`*

*Observed 2026-11-07 (python-dev)*
