# InterWeave carrier parity report

Window: 2026-11-12T09:30:00Z to 2026-11-12T10:54:24Z (a pair belongs to it by its first copy).
Pairs (MESSAGE-ID, addressee): 106; of them to a TO-ROLE recipient: 0.

| carrier | delivered | missed | duplicate copies | FROM mismatches |
|---|---|---|---|---|
| relay | 106 | 0 | 1 | 0 |
| interweave | 97 | 9 | 0 | 0 |

## Pairs a carrier missed, with the cause

- 01a1cf1b-518c-782d-a44b-86694156adab to develop-qzapp/architect-cto-01, interweave: the sender recorded no InterWeave delivery (not carried: no roster row, carrier off or sender had none)
- 01a1cf1c-50c6-7bed-9b73-36efd2ecbac6 to develop-qzapp/rust-services-dev-01, interweave: the sender recorded no InterWeave delivery (not carried: no roster row, carrier off or sender had none)
- 01a1cf1d-e400-7f56-8ec8-126fc70a2879 to develop-qzapp/rust-ui-dev-01, interweave: the sender recorded no InterWeave delivery (not carried: no roster row, carrier off or sender had none)
- 01a1cf2b-4277-7913-b8a5-748a4e0f545e to develop-qzapp/user, interweave: the sender recorded no InterWeave delivery (not carried: no roster row, carrier off or sender had none)
- 01a1cf34-63e4-7fc6-9d7d-0ebe4422c640 to develop-qzapp/devex-tooling, interweave: the sender recorded no InterWeave delivery (not carried: no roster row, carrier off or sender had none)
- 01a1cf35-60b2-71b2-99cd-ec64276fc5f3 to develop-qzapp/rust-ui-dev-01, interweave: the sender recorded no InterWeave delivery (not carried: no roster row, carrier off or sender had none)
- 01a1cf3c-846b-7c3c-bf4e-78fdbc0d7532 to develop-qzapp/user, interweave: the sender recorded no InterWeave delivery (not carried: no roster row, carrier off or sender had none)
- 01a1cf5b-87fc-7cac-923a-b48fca6b86e4 to develop-qzapp/user, interweave: the sender recorded no InterWeave delivery (not carried: no roster row, carrier off or sender had none)
- 01a1cf5e-44dc-79c5-a97e-3354b9888f8f to develop-qzapp/user, interweave: the sender recorded no InterWeave delivery (not carried: no roster row, carrier off or sender had none)

## Pairs the sender recorded sending, no copy arrived and no receipt came

- none

## Delivered to an addressee that was away (first copy over 60 s after the message was made)

| kind | relay | interweave |
|---|---|---|
| direct | 6 | 0 |
| role | 0 | 0 |
| broadcast | 7 | 0 |
| unknown | 0 | 0 |

## Collected from 30 account(s)

architect-cto-01, backend-dev-01, backend-dev-02, brand-comms-01, db-admin, devex-tooling, domain-transit, edge-hosting, flutter-dev-01, flutter-dev-02, language-culture-en, language-culture-ge, language-culture-ru, legal-expert-ch, legal-expert-ee-eu, legal-expert-ge, p2p-network-dev-01, p2p-network-dev-02, python-dev-01, python-dev-02, python-dev-03, python-dev-04, rust-services-dev-01, rust-services-dev-02, rust-ui-dev-01, rust-ui-dev-02, user, ux-designer-01, web-dev-01, web-dev-02

Arrivals were collected 60 minutes beyond each edge of the window: a pair whose two copies are further apart than that across an edge may show a miss the full files would not.

## Framing: 0 message(s) compressed, 0 chunked, 13 sent plain

## Rollback drill (2026-11-12T09:34:08Z to 2026-11-12T10:04:30Z): nothing lost

- 01a1cf1c-50c6-7bed-9b73-36efd2ecbac6 to develop-qzapp/rust-services-dev-01 (direct): relay yes, interweave no
- 01a1cf1d-e400-7f56-8ec8-126fc70a2879 to develop-qzapp/rust-ui-dev-01 (direct): relay yes, interweave no
- 01a1cf2b-4277-7913-b8a5-748a4e0f545e to develop-qzapp/user (direct): relay yes, interweave no
- 01a1cf34-63e4-7fc6-9d7d-0ebe4422c640 to develop-qzapp/devex-tooling (direct): relay yes, interweave no
- 01a1cf35-60b2-71b2-99cd-ec64276fc5f3 to develop-qzapp/rust-ui-dev-01 (direct): relay yes, interweave no

## Relay-outage drill (2026-11-12T10:13:30Z to 2026-11-12T10:43:51Z): the three properties hold

Per pair made inside the drill: held by the carrier alone (the InterWeave copy arrived inside the drill and the relay's did not; otherwise the pair proves nothing), shown to the session once or not, shown again, the relay copy acknowledged.

- 01a1cf4d-8b17-782b-90c6-b0bc7c9e8464 to develop-qzapp/architect-cto-01 (architect-cto-01): carrier alone; shown once by interweave; shown again: no; relay record: none; relay copy back, acknowledged: yes
- 01a1cf45-bf69-71d0-9b78-303b69349521 to develop-qzapp/devex-tooling (devex-tooling): carrier alone; shown once by interweave; shown again: no; relay record: none; relay copy back, acknowledged: yes
- 01a1cf4f-9c02-73e9-995c-d5f4e710ea88 to develop-qzapp/devex-tooling (devex-tooling): carrier alone; shown once by interweave; shown again: no; relay record: none; relay copy back, acknowledged: yes
- 01a1cf44-b058-73c0-8200-d6698677f2ac to develop-qzapp/rust-ui-dev-01 (rust-ui-dev-01): carrier alone; shown once by interweave; shown again: no; relay record: none; relay copy back, acknowledged: yes
- 01a1cf4c-94d3-78ac-834b-0c8d84f3460c to develop-qzapp/user (user): carrier alone; shown once by interweave; shown again: no; relay record: none; relay copy back, acknowledged: yes

Fourth property, relay record by backfill: FAILED: a message held by the carrier alone did not reach the relay's record by backfill (over-age, or no row by the report's end).
