# InterWeave carrier parity report

Window: 2026-11-15T10:00:00Z to 2026-11-18T00:00:00Z (a pair belongs to it by its first copy).
Pairs (MESSAGE-ID, addressee): 566; of them to a TO-ROLE recipient: 7.

| carrier | delivered | missed | duplicate copies | FROM mismatches |
|---|---|---|---|---|
| relay | 566 | 0 | 0 | 0 |
| interweave | 560 | 4 | 0 | 0 |

## Pairs a carrier missed, with the cause

- 01a1db67-e363-728c-a911-d55d4bb2c4c6 to develop-qzapp/user, interweave: the sender recorded no InterWeave delivery (not carried: no roster row, carrier off or sender had none); the addressee's first InterWeave arrival in the collection is 2026-11-15T21:17:04Z, later
- 01a1de05-9074-725f-9992-dd9c0b09f922 to develop-qzapp/language-culture-en, interweave: the sender recorded no InterWeave delivery (not carried: no roster row, carrier off or sender had none); the addressee's first InterWeave arrival in the collection is 2026-11-15T21:15:46Z, later
- 01a1de20-7393-759c-9b5c-241c4c03d0a0 to develop-qzapp/language-culture-en, interweave: the sender recorded no InterWeave delivery (not carried: no roster row, carrier off or sender had none); the addressee's first InterWeave arrival in the collection is 2026-11-15T21:15:46Z, later
- 01a1de35-44cf-765b-893c-ed39dd854b1a to develop-qzapp/language-culture-en, interweave: the sender recorded no InterWeave delivery (not carried: no roster row, carrier off or sender had none); the addressee's first InterWeave arrival in the collection is 2026-11-15T21:15:46Z, later

Not counted as InterWeave misses: 2 pair(s) whose addressee is the message's own sender (a broadcast or TO-ROLE: the relay returns the sender its copy, the carrier never sends to its sender).

## Pairs the sender recorded sending, no copy arrived and no receipt came

- none

## Delivered to an addressee that was away (first copy over 60 s after the message was made)

| kind | relay | interweave |
|---|---|---|
| direct | 48 | 19 |
| role | 2 | 1 |
| broadcast | 2 | 0 |
| unknown | 0 | 0 |

## Collected from 30 account(s)

architect-cto-01, backend-dev-01, backend-dev-02, brand-comms-01, db-admin, devex-tooling, domain-transit, edge-hosting, flutter-dev-01, flutter-dev-02, language-culture-en, language-culture-ge, language-culture-ru, legal-expert-ch, legal-expert-ee-eu, legal-expert-ge, p2p-network-dev-01, p2p-network-dev-02, python-dev-01, python-dev-02, python-dev-03, python-dev-04, rust-services-dev-01, rust-services-dev-02, rust-ui-dev-01, rust-ui-dev-02, user, ux-designer-01, web-dev-01, web-dev-02

Arrivals were collected 60 minutes beyond each edge of the window: a pair whose two copies are further apart than that across an edge may show a miss the full files would not.

## Framing: 0 message(s) compressed, 0 chunked, 503 sent plain

