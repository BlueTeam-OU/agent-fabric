# InterWeave carrier parity report

Window: 2026-11-26T00:30:00Z to 2026-11-26T02:20:00Z (a pair belongs to it by its first copy).
Pairs (MESSAGE-ID, addressee): 118; of them to a TO-ROLE recipient: 0.

| carrier | delivered | missed | duplicate copies | FROM mismatches |
|---|---|---|---|---|
| relay | 118 | 0 | 0 | 0 |
| interweave | 115 | 0 | 0 | 0 |

## Pairs a carrier missed, with the cause

- none

Not counted as InterWeave misses: 3 pair(s) whose addressee is the message's own sender (a broadcast or TO-ROLE: the relay returns the sender its copy, the carrier never sends to its sender).

## Pairs the sender recorded sending, no copy arrived and no receipt came

- none

## Delivered to an addressee that was away (first copy over 60 s after the message was made)

| kind | relay | interweave |
|---|---|---|
| direct | 16 | 2 |
| role | 0 | 0 |
| broadcast | 7 | 0 |
| unknown | 0 | 0 |

## Collected from 30 account(s)

architect-cto-01, backend-dev-01, backend-dev-02, brand-comms-01, db-admin, devex-tooling, domain-transit, edge-hosting, flutter-dev-01, flutter-dev-02, language-culture-en, language-culture-ge, language-culture-ru, legal-expert-ch, legal-expert-ee-eu, legal-expert-ge, p2p-network-dev-01, p2p-network-dev-02, python-dev-01, python-dev-02, python-dev-03, python-dev-04, rust-services-dev-01, rust-services-dev-02, rust-ui-dev-01, rust-ui-dev-02, user, ux-designer-01, web-dev-01, web-dev-02

Arrivals were collected 60 minutes beyond each edge of the window: a pair whose two copies are further apart than that across an edge may show a miss the full files would not.

## Framing: 0 message(s) compressed, 0 chunked, 31 sent plain


## Carrier-outage drill of python-dev-03 (2026-11-26T00:40:58Z to 2026-11-26T01:11:46Z): every message held arrived once by the carrier and was shown once

Per pair addressed to the account and made inside the drill: held by a sender's outbox (a delivery row the sender recorded), delivered after the window's end, how many copies each carrier delivered (the relay's mirror copy beside the carrier's is normal in carrier-record), and shown to the session once or not. A pair a copy reached before the window ended, or that no outbox recorded, proves nothing.

- 01a2154d-5d54-7828-b24a-b09db529906c: held by user's outbox (done); delivered after the window's end (2026-11-26T01:12:24Z); 2 copy(ies) (1 interweave, 1 relay); shown once
- 01a2154d-648a-7c53-b863-8a618ccd7978: held by user's outbox (done); delivered after the window's end (2026-11-26T01:12:24Z); 2 copy(ies) (1 interweave, 1 relay); shown once

## Relay-outage drill (2026-11-26T01:15:56Z to 2026-11-26T02:16:13Z): the three properties hold

Per pair made inside the drill: held by the carrier alone (the InterWeave copy arrived inside the drill and the relay's did not; otherwise the pair proves nothing), shown to the session once or not, shown again, the relay copy acknowledged.

- 01a21590-c7cb-7739-8317-c9847769c400 to develop-qzapp/architect-cto-01 (architect-cto-01): carrier alone; shown once by interweave; shown again: no; relay record: posted (delay 1296 s); relay copy back, acknowledged: yes
- 01a21594-2d9e-7f59-bd65-219cf757ff9f to develop-qzapp/architect-cto-01 (architect-cto-01): carrier alone; shown once by interweave; shown again: no; relay record: posted (delay 1054 s); relay copy back, acknowledged: yes
- 01a2159d-1c32-7ce8-919b-3f838641f0b2 to develop-qzapp/architect-cto-01 (architect-cto-01): carrier alone; shown once by interweave; shown again: no; relay record: posted (delay 478 s); relay copy back, acknowledged: yes
- 01a2156c-996f-7b26-8c72-dedee79e9d92 to develop-qzapp/python-dev-02 (python-dev-02): carrier alone; shown once by interweave; shown again: no; relay record: posted (delay 3618 s); relay copy back, acknowledged: yes
- 01a2156c-be62-75e9-a23e-0a456f867d3b to develop-qzapp/python-dev-03 (python-dev-03): carrier alone; shown once by interweave; shown again: no; relay record: posted (delay 3608 s); relay copy back, acknowledged: yes
- 01a21594-4bd1-7f57-b2f8-9c271c4d9871 to develop-qzapp/rust-ui-dev-01 (rust-ui-dev-01): carrier alone; shown once by interweave; shown again: no; relay record: posted (delay 1052 s); relay copy back, acknowledged: yes
- 01a2156d-a7db-72aa-9a87-d20ae457579f to develop-qzapp/user (user): carrier alone; shown once by interweave; shown again: no; relay record: posted (delay 3584 s); relay copy back, acknowledged: yes
- 01a2156e-34e1-7ac2-b89a-3fd898f88695 to develop-qzapp/user (user): carrier alone; shown once by interweave; shown again: no; relay record: posted (delay 3539 s); relay copy back, acknowledged: yes
- 01a2157b-032c-7b7d-997f-38b2386344cd to develop-qzapp/user (user): carrier alone; shown once by interweave; shown again: no; relay record: posted (delay 2689 s); relay copy back, acknowledged: yes
- 01a2157b-5d0a-7349-9e95-3d6f3fe65536 to develop-qzapp/user (user): carrier alone; shown once by interweave; shown again: no; relay record: posted (delay 2705 s); relay copy back, acknowledged: yes
- 01a2157b-65b2-7446-9796-c4813b55b113 to develop-qzapp/user (user): carrier alone; shown once by interweave; shown again: no; relay record: posted (delay 2676 s); relay copy back, acknowledged: yes
- 01a21595-4ce7-7165-914a-fe9221a23c86 to develop-qzapp/ux-designer-01 (ux-designer-01): carrier alone; shown once by interweave; shown again: no; relay record: posted (delay 941 s); relay copy back, acknowledged: yes
- 01a2159d-f506-704f-81be-c83f89ddfa0e to develop-qzapp/ux-designer-01 (ux-designer-01): carrier alone; shown once by interweave; shown again: no; relay record: posted (delay 414 s); relay copy back, acknowledged: yes

Watches inside the drill, from each account's watch log (every start with how the watch before it ended; a give-up is the watch's exit 5, after its primary transport, the relay or the carrier where it leads, did not answer for the give-up bound, 15 minutes unless set otherwise):

- architect-cto-01: restarts (starts inside the drill): 4 (2026-11-26T01:55:51Z after delivery, 2026-11-26T01:57:12Z after no end line, 2026-11-26T02:00:12Z after delivery, 2026-11-26T02:09:33Z after delivery); gave up: no
- backend-dev-01: restarts (starts inside the drill): 0 (none); gave up: no
- backend-dev-02: restarts (starts inside the drill): 0 (none); gave up: no
- brand-comms-01: restarts (starts inside the drill): 0 (none); gave up: no
- db-admin: restarts (starts inside the drill): 0 (none); gave up: no
- devex-tooling: restarts (starts inside the drill): 0 (none); gave up: no
- domain-transit: restarts (starts inside the drill): 0 (none); gave up: no
- edge-hosting: restarts (starts inside the drill): 0 (none); gave up: no
- flutter-dev-01: restarts (starts inside the drill): 0 (none); gave up: no
- flutter-dev-02: restarts (starts inside the drill): 0 (none); gave up: no
- language-culture-en: restarts (starts inside the drill): 0 (none); gave up: no
- language-culture-ge: restarts (starts inside the drill): 0 (none); gave up: no
- language-culture-ru: restarts (starts inside the drill): 0 (none); gave up: no
- legal-expert-ch: restarts (starts inside the drill): 0 (none); gave up: no
- legal-expert-ee-eu: restarts (starts inside the drill): 0 (none); gave up: no
- legal-expert-ge: restarts (starts inside the drill): 0 (none); gave up: no
- p2p-network-dev-01: restarts (starts inside the drill): 0 (none); gave up: no
- p2p-network-dev-02: restarts (starts inside the drill): 0 (none); gave up: no
- python-dev-01: restarts (starts inside the drill): 0 (none); gave up: no
- python-dev-02: restarts (starts inside the drill): 2 (2026-11-26T01:16:29Z after delivery, 2026-11-26T01:19:05Z after no end line); gave up: no
- python-dev-03: restarts (starts inside the drill): 2 (2026-11-26T01:16:45Z after delivery, 2026-11-26T01:19:44Z after no end line); gave up: no
- python-dev-04: restarts (starts inside the drill): 0 (none); gave up: no
- rust-services-dev-01: restarts (starts inside the drill): 0 (none); gave up: no
- rust-services-dev-02: restarts (starts inside the drill): 0 (none); gave up: no
- rust-ui-dev-01: restarts (starts inside the drill): 1 (2026-11-26T02:00:01Z after delivery); gave up: no
- rust-ui-dev-02: restarts (starts inside the drill): 0 (none); gave up: no
- user: restarts (starts inside the drill): 4 (2026-11-26T01:18:31Z after delivery, 2026-11-26T01:19:01Z after delivery, 2026-11-26T01:32:32Z after delivery, 2026-11-26T01:32:59Z after delivery); gave up: no
- ux-designer-01: restarts (starts inside the drill): 3 (2026-11-26T01:57:54Z after no end line, 2026-11-26T02:01:36Z after no end line, 2026-11-26T02:01:51Z after delivery); gave up: no
- web-dev-01: restarts (starts inside the drill): 0 (none); gave up: no
- web-dev-02: restarts (starts inside the drill): 0 (none); gave up: no

Fourth property, relay record by backfill: holds: every such message is on the relay's record (by backfill, or taken by the relay at send).
  - 01a21590-c7cb-7739-8317-c9847769c400 to develop-qzapp/architect-cto-01: backfill row posted, delay 1296 s
  - 01a21594-2d9e-7f59-bd65-219cf757ff9f to develop-qzapp/architect-cto-01: backfill row posted, delay 1054 s
  - 01a2159d-1c32-7ce8-919b-3f838641f0b2 to develop-qzapp/architect-cto-01: backfill row posted, delay 478 s
  - 01a2156c-996f-7b26-8c72-dedee79e9d92 to develop-qzapp/python-dev-02: backfill row posted, delay 3618 s
  - 01a2156c-be62-75e9-a23e-0a456f867d3b to develop-qzapp/python-dev-03: backfill row posted, delay 3608 s
  - 01a21594-4bd1-7f57-b2f8-9c271c4d9871 to develop-qzapp/rust-ui-dev-01: backfill row posted, delay 1052 s
  - 01a2156d-a7db-72aa-9a87-d20ae457579f to develop-qzapp/user: backfill row posted, delay 3584 s
  - 01a2156e-34e1-7ac2-b89a-3fd898f88695 to develop-qzapp/user: backfill row posted, delay 3539 s
  - 01a2157b-032c-7b7d-997f-38b2386344cd to develop-qzapp/user: backfill row posted, delay 2689 s
  - 01a2157b-5d0a-7349-9e95-3d6f3fe65536 to develop-qzapp/user: backfill row posted, delay 2705 s
  - 01a2157b-65b2-7446-9796-c4813b55b113 to develop-qzapp/user: backfill row posted, delay 2676 s
  - 01a21595-4ce7-7165-914a-fe9221a23c86 to develop-qzapp/ux-designer-01: backfill row posted, delay 941 s
  - 01a2159d-f506-704f-81be-c83f89ddfa0e to develop-qzapp/ux-designer-01: backfill row posted, delay 414 s
