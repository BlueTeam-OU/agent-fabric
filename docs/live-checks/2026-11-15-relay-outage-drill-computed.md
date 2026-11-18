# InterWeave carrier parity report

Window: 2026-11-15T06:50:00Z to 2026-11-15T07:45:00Z (a pair belongs to it by its first copy).
Pairs (MESSAGE-ID, addressee): 78; of them to a TO-ROLE recipient: 0.

| carrier | delivered | missed | duplicate copies | FROM mismatches |
|---|---|---|---|---|
| relay | 78 | 0 | 0 | 0 |
| interweave | 76 | 0 | 0 | 0 |

## Pairs a carrier missed, with the cause

- none

Not counted as InterWeave misses: 2 pair(s) whose addressee is the message's own sender (a broadcast or TO-ROLE: the relay returns the sender its copy, the carrier never sends to its sender).

## Pairs the sender recorded sending, no copy arrived and no receipt came

- none

## Delivered to an addressee that was away (first copy over 60 s after the message was made)

| kind | relay | interweave |
|---|---|---|
| direct | 12 | 1 |
| role | 0 | 0 |
| broadcast | 3 | 0 |
| unknown | 0 | 0 |

## Collected from 30 account(s)

architect-cto-01, backend-dev-01, backend-dev-02, brand-comms-01, db-admin, devex-tooling, domain-transit, edge-hosting, flutter-dev-01, flutter-dev-02, language-culture-en, language-culture-ge, language-culture-ru, legal-expert-ch, legal-expert-ee-eu, legal-expert-ge, p2p-network-dev-01, p2p-network-dev-02, python-dev-01, python-dev-02, python-dev-03, python-dev-04, rust-services-dev-01, rust-services-dev-02, rust-ui-dev-01, rust-ui-dev-02, user, ux-designer-01, web-dev-01, web-dev-02

Arrivals were collected 60 minutes beyond each edge of the window: a pair whose two copies are further apart than that across an edge may show a miss the full files would not.

## Framing: 0 message(s) compressed, 0 chunked, 20 sent plain


## Relay-outage drill (2026-11-15T06:58:26Z to 2026-11-15T07:33:27Z): the three properties hold

Per pair made inside the drill: held by the carrier alone (the InterWeave copy arrived inside the drill and the relay's did not; otherwise the pair proves nothing), shown to the session once or not, shown again, the relay copy acknowledged.

- 01a1de03-26e6-7db2-8723-74d0d5653b61 to develop-qzapp/architect-cto-01 (architect-cto-01): carrier alone; shown once by interweave; shown again: no; relay record: posted (delay 1684 s); relay copy back, acknowledged: yes
- 01a1de08-dac4-7882-822a-05cf8cf82f48 to develop-qzapp/architect-cto-01 (architect-cto-01): carrier alone; shown once by interweave; shown again: no; relay record: posted (delay 1526 s); relay copy back, acknowledged: yes
- 01a1de09-3e4d-71e6-85ba-216cbfe3fe37 to develop-qzapp/architect-cto-01 (architect-cto-01): carrier alone; shown once by interweave; shown again: no; relay record: posted (delay 1527 s); relay copy back, acknowledged: yes
- 01a1de05-9074-725f-9992-dd9c0b09f922 to develop-qzapp/language-culture-en (language-culture-en): carrier alone; shown once by interweave; shown again: no; relay record: posted (delay 1770 s); relay copy back, acknowledged: yes
- 01a1de00-3660-7732-8d9a-81ec6ea2db33 to develop-qzapp/python-dev-02 (python-dev-02): carrier alone; shown once by interweave; shown again: no; relay record: posted (delay 2094 s); relay copy back, acknowledged: yes
- 01a1de07-c599-71cd-b6d2-9a5670a5fced to develop-qzapp/rust-ui-dev-01 (rust-ui-dev-01): carrier alone; shown once by interweave; shown again: no; relay record: posted (delay 1609 s); relay copy back, acknowledged: yes
- 01a1de07-e48d-7ee1-b189-b69f653175c6 to develop-qzapp/rust-ui-dev-02 (rust-ui-dev-02): carrier alone; shown once by interweave; shown again: no; relay record: posted (delay 1604 s); relay copy back, acknowledged: yes
- 01a1de09-d4da-78e0-9b98-48926643de7e to develop-qzapp/rust-ui-dev-02 (rust-ui-dev-02): carrier alone; shown once by interweave; shown again: no; relay record: posted (delay 1477 s); relay copy back, acknowledged: yes
- 01a1de0b-2883-73aa-bcd3-29c3ec3f5170 to develop-qzapp/rust-ui-dev-02 (rust-ui-dev-02): carrier alone; shown once by interweave; shown again: no; relay record: posted (delay 1390 s); relay copy back, acknowledged: yes
- 01a1de19-49fb-7d4d-8be7-54a47b4491b1 to develop-qzapp/user (user): carrier alone; shown once by interweave; shown again: no; relay record: posted (delay 473 s); relay copy back, acknowledged: yes
- 01a1de02-316a-747f-8457-7cf9efc543d4 to develop-qzapp/ux-designer-01 (ux-designer-01): carrier alone; shown once by interweave; shown again: no; relay record: posted (delay 1999 s); relay copy back, acknowledged: yes
- 01a1de0a-2ed4-756b-a743-9d0b0d30f9cd to develop-qzapp/ux-designer-01 (ux-designer-01): carrier alone; shown once by interweave; shown again: no; relay record: posted (delay 1477 s); relay copy back, acknowledged: yes

Watches inside the drill, from each account's watch log (every start with how the watch before it ended; a give-up is the watch's exit 5, after its primary transport, the relay or the carrier where it leads, did not answer for the give-up bound, 15 minutes unless set otherwise):

- architect-cto-01: restarts (starts inside the drill): 3 (2026-11-15T07:06:07Z after delivery, 2026-11-15T07:08:47Z after delivery, 2026-11-15T07:11:32Z after no end line); gave up: yes, at 2026-11-15T07:26:32Z
- backend-dev-01: restarts (starts inside the drill): 2 (2026-11-15T07:14:09Z after gave-up, 2026-11-15T07:29:44Z after gave-up); gave up: yes, at 2026-11-15T07:13:26Z, 2026-11-15T07:29:10Z
- backend-dev-02: restarts (starts inside the drill): 2 (2026-11-15T07:14:14Z after gave-up, 2026-11-15T07:29:47Z after gave-up); gave up: yes, at 2026-11-15T07:13:26Z, 2026-11-15T07:29:15Z
- brand-comms-01: restarts (starts inside the drill): 0 (none); gave up: yes, at 2026-11-15T07:13:26Z
- db-admin: restarts (starts inside the drill): 2 (2026-11-15T07:14:05Z after gave-up, 2026-11-15T07:29:39Z after gave-up); gave up: yes, at 2026-11-15T07:13:26Z, 2026-11-15T07:29:05Z
- devex-tooling: restarts (starts inside the drill): 2 (2026-11-15T07:14:12Z after gave-up, 2026-11-15T07:29:46Z after gave-up); gave up: yes, at 2026-11-15T07:13:26Z, 2026-11-15T07:29:12Z
- domain-transit: restarts (starts inside the drill): 2 (2026-11-15T07:13:53Z after gave-up, 2026-11-15T07:29:05Z after gave-up); gave up: yes, at 2026-11-15T07:13:26Z, 2026-11-15T07:28:53Z
- edge-hosting: restarts (starts inside the drill): 2 (2026-11-15T07:14:04Z after gave-up, 2026-11-15T07:29:38Z after gave-up); gave up: yes, at 2026-11-15T07:13:26Z, 2026-11-15T07:29:05Z
- flutter-dev-01: restarts (starts inside the drill): 2 (2026-11-15T07:13:58Z after gave-up, 2026-11-15T07:29:26Z after gave-up); gave up: yes, at 2026-11-15T07:13:26Z, 2026-11-15T07:28:58Z
- flutter-dev-02: restarts (starts inside the drill): 2 (2026-11-15T07:14:07Z after gave-up, 2026-11-15T07:29:41Z after gave-up); gave up: yes, at 2026-11-15T07:13:26Z, 2026-11-15T07:29:07Z
- language-culture-en: restarts (starts inside the drill): 2 (2026-11-15T07:05:08Z after delivery, 2026-11-15T07:06:24Z after no end line); gave up: yes, at 2026-11-15T07:21:24Z
- language-culture-ge: restarts (starts inside the drill): 2 (2026-11-15T07:14:08Z after gave-up, 2026-11-15T07:29:42Z after gave-up); gave up: yes, at 2026-11-15T07:13:26Z, 2026-11-15T07:29:08Z
- language-culture-ru: restarts (starts inside the drill): 2 (2026-11-15T07:14:06Z after gave-up, 2026-11-15T07:29:40Z after gave-up); gave up: yes, at 2026-11-15T07:13:26Z, 2026-11-15T07:29:06Z
- legal-expert-ch: restarts (starts inside the drill): 2 (2026-11-15T07:14:11Z after gave-up, 2026-11-15T07:29:44Z after gave-up); gave up: yes, at 2026-11-15T07:13:26Z, 2026-11-15T07:29:11Z
- legal-expert-ee-eu: restarts (starts inside the drill): 0 (none); gave up: yes, at 2026-11-15T07:13:26Z
- legal-expert-ge: restarts (starts inside the drill): 2 (2026-11-15T07:14:09Z after gave-up, 2026-11-15T07:29:40Z after gave-up); gave up: yes, at 2026-11-15T07:13:26Z, 2026-11-15T07:29:09Z
- p2p-network-dev-01: restarts (starts inside the drill): 2 (2026-11-15T07:13:59Z after gave-up, 2026-11-15T07:29:33Z after gave-up); gave up: yes, at 2026-11-15T07:13:26Z, 2026-11-15T07:28:59Z
- p2p-network-dev-02: restarts (starts inside the drill): 2 (2026-11-15T07:13:58Z after gave-up, 2026-11-15T07:29:25Z after gave-up); gave up: yes, at 2026-11-15T07:13:26Z, 2026-11-15T07:28:58Z
- python-dev-01: restarts (starts inside the drill): 2 (2026-11-15T07:14:00Z after gave-up, 2026-11-15T07:29:23Z after gave-up); gave up: yes, at 2026-11-15T07:13:26Z, 2026-11-15T07:29:01Z
- python-dev-02: restarts (starts inside the drill): 3 (2026-11-15T06:59:10Z after delivery, 2026-11-15T07:14:25Z after gave-up, 2026-11-15T07:29:58Z after gave-up); gave up: yes, at 2026-11-15T07:14:10Z, 2026-11-15T07:29:25Z
- python-dev-03: restarts (starts inside the drill): 2 (2026-11-15T07:14:00Z after gave-up, 2026-11-15T07:29:13Z after gave-up); gave up: yes, at 2026-11-15T07:13:26Z, 2026-11-15T07:29:00Z
- python-dev-04: restarts (starts inside the drill): 2 (2026-11-15T07:14:24Z after gave-up, 2026-11-15T07:26:53Z after no end line); gave up: yes, at 2026-11-15T07:13:26Z
- rust-services-dev-01: restarts (starts inside the drill): 2 (2026-11-15T07:14:03Z after gave-up, 2026-11-15T07:29:28Z after gave-up); gave up: yes, at 2026-11-15T07:13:26Z, 2026-11-15T07:29:04Z
- rust-services-dev-02: restarts (starts inside the drill): 2 (2026-11-15T07:14:06Z after gave-up, 2026-11-15T07:29:32Z after gave-up); gave up: yes, at 2026-11-15T07:13:26Z, 2026-11-15T07:29:06Z
- rust-ui-dev-01: restarts (starts inside the drill): 2 (2026-11-15T07:07:43Z after delivery, 2026-11-15T07:22:55Z after gave-up); gave up: yes, at 2026-11-15T07:22:43Z
- rust-ui-dev-02: restarts (starts inside the drill): 4 (2026-11-15T07:07:38Z after delivery, 2026-11-15T07:09:51Z after delivery, 2026-11-15T07:11:03Z after delivery, 2026-11-15T07:26:20Z after gave-up); gave up: yes, at 2026-11-15T07:26:03Z
- user: restarts (starts inside the drill): 2 (2026-11-15T07:14:26Z after gave-up, 2026-11-15T07:26:38Z after delivery); gave up: yes, at 2026-11-15T07:13:26Z
- ux-designer-01: restarts (starts inside the drill): 3 (2026-11-15T07:01:08Z after delivery, 2026-11-15T07:09:49Z after delivery, 2026-11-15T07:25:03Z after gave-up); gave up: yes, at 2026-11-15T07:24:49Z
- web-dev-01: restarts (starts inside the drill): 2 (2026-11-15T07:14:14Z after gave-up, 2026-11-15T07:29:48Z after gave-up); gave up: yes, at 2026-11-15T07:13:26Z, 2026-11-15T07:29:14Z
- web-dev-02: restarts (starts inside the drill): 2 (2026-11-15T07:14:06Z after gave-up, 2026-11-15T07:29:40Z after gave-up); gave up: yes, at 2026-11-15T07:13:26Z, 2026-11-15T07:29:06Z

Fourth property, relay record by backfill: holds: every such message is on the relay's record (by backfill, or taken by the relay at send).
  - 01a1de03-26e6-7db2-8723-74d0d5653b61 to develop-qzapp/architect-cto-01: backfill row posted, delay 1684 s
  - 01a1de08-dac4-7882-822a-05cf8cf82f48 to develop-qzapp/architect-cto-01: backfill row posted, delay 1526 s
  - 01a1de09-3e4d-71e6-85ba-216cbfe3fe37 to develop-qzapp/architect-cto-01: backfill row posted, delay 1527 s
  - 01a1de05-9074-725f-9992-dd9c0b09f922 to develop-qzapp/language-culture-en: backfill row posted, delay 1770 s
  - 01a1de00-3660-7732-8d9a-81ec6ea2db33 to develop-qzapp/python-dev-02: backfill row posted, delay 2094 s
  - 01a1de07-c599-71cd-b6d2-9a5670a5fced to develop-qzapp/rust-ui-dev-01: backfill row posted, delay 1609 s
  - 01a1de07-e48d-7ee1-b189-b69f653175c6 to develop-qzapp/rust-ui-dev-02: backfill row posted, delay 1604 s
  - 01a1de09-d4da-78e0-9b98-48926643de7e to develop-qzapp/rust-ui-dev-02: backfill row posted, delay 1477 s
  - 01a1de0b-2883-73aa-bcd3-29c3ec3f5170 to develop-qzapp/rust-ui-dev-02: backfill row posted, delay 1390 s
  - 01a1de19-49fb-7d4d-8be7-54a47b4491b1 to develop-qzapp/user: backfill row posted, delay 473 s
  - 01a1de02-316a-747f-8457-7cf9efc543d4 to develop-qzapp/ux-designer-01: backfill row posted, delay 1999 s
  - 01a1de0a-2ed4-756b-a743-9d0b0d30f9cd to develop-qzapp/ux-designer-01: backfill row posted, delay 1477 s
