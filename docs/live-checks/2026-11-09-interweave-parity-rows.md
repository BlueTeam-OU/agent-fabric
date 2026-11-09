# Parity report rows — 2026-11-09

The rows `2026-11-09-interweave-parity.md` reads that the tool's report does not print. They are taken from the same collection (`fabric-ctl all interweave-evidence --since 2026-10-24T00:00:00Z --until 2026-11-09T17:50:06Z`), metadata only: MESSAGE-IDs, logins, carriers, times. No body was collected. Times are UTC, as each account wrote them.

## Relay-outage drill pairs: every arrival, showing and acknowledgement line

| drill | MESSAGE-ID | account | arrivals (carrier time) | shown ledger (via time, pending) | acknowledgement lines |
|---|---|---|---|---|---|
| 11-05 | `01a1ac73-ed01-7bda-bc52-c270c23e028e` | architect-cto-01 | relay 2026-11-05T16:10:26Z; interweave 2026-11-05T16:10:27Z | relay 2026-11-05T16:10:26Z pending; relay 2026-11-05T16:10:27Z | none |
| 11-05 | `01a1ac68-bcdd-70db-ae31-5f7a5b1639d7` | devex-tooling | interweave 2026-11-05T15:51:48Z | interweave 2026-11-05T16:09:28Z pending; interweave 2026-11-05T16:09:28Z | none |
| 11-05 | `01a1ac73-ec74-734d-b082-50dfa36050a3` | rust-ui-dev-02 | relay 2026-11-05T16:10:25Z; interweave 2026-11-05T16:10:25Z | relay 2026-11-05T16:10:25Z pending; relay 2026-11-05T16:10:25Z | none |
| 11-07 | `01a1b818-afd7-71f9-bc22-89eaf4c46e67` | devex-tooling | relay 2026-11-08T07:26:57Z; interweave 2026-11-08T07:26:57Z | relay 2026-11-08T07:26:57Z pending; relay 2026-11-08T07:26:57Z | none |
| 11-07 | `01a1b81f-f37e-745e-952a-4d8ac7349027` | devex-tooling | interweave 2026-11-07T22:30:10Z; relay 2026-11-07T23:21:33Z | interweave 2026-11-07T22:30:10Z pending; interweave 2026-11-07T22:30:10Z | none |
| 11-07 | `01a1b819-45db-7886-aa0d-b75c62aa00a6` | python-dev-03 | interweave 2026-11-07T22:20:29Z; relay 2026-11-07T23:23:32Z | interweave 2026-11-07T22:20:41Z pending; interweave 2026-11-07T22:20:41Z | none |
| 11-07 | `01a1b81a-4214-77a3-b65e-79aa62a54a0b` | rust-ui-dev-01 | interweave 2026-11-07T22:24:29Z; relay 2026-11-07T23:20:48Z | interweave 2026-11-07T22:24:36Z pending; interweave 2026-11-07T22:24:36Z | none |
| 11-07 | `01a1b81d-2e7e-7d12-b7d1-037388010756` | rust-ui-dev-02 | relay 2026-11-07T23:20:41Z; interweave 2026-11-07T23:20:41Z | relay 2026-11-07T23:20:41Z pending; relay 2026-11-07T23:20:41Z | none |
| 11-07 | `01a1b81c-4d34-76f1-aa71-15b11dc9425e` | ux-designer-01 | interweave 2026-11-07T22:23:56Z; relay 2026-11-07T23:21:29Z | interweave 2026-11-07T22:24:10Z pending; interweave 2026-11-07T22:24:10Z | none |

## First acknowledgement line per account

`gzcoord-acks.jsonl` was added by e4424b06. The earliest line in each account's collected log:

| account | first line | lines |
|---|---|---|
| rust-ui-dev-01 | 2026-11-08T17:05:31Z | 22 |
| brand-comms-01 | 2026-11-08T17:09:46Z | 5 |
| legal-expert-ge | 2026-11-08T17:11:38Z | 2 |
| user | 2026-11-08T17:15:42Z | 97 |
| ux-designer-01 | 2026-11-08T18:07:32Z | 6 |
| rust-ui-dev-02 | 2026-11-08T18:08:51Z | 12 |
| architect-cto-01 | 2026-11-08T18:09:24Z | 12 |
| p2p-network-dev-01 | 2026-11-08T18:14:40Z | 3 |
| python-dev-02 | 2026-11-08T20:39:28Z | 19 |
| python-dev-03 | 2026-11-08T20:39:30Z | 22 |
| python-dev-01 | 2026-11-08T20:39:32Z | 14 |
| python-dev-04 | 2026-11-08T20:39:34Z | 14 |
| p2p-network-dev-02 | 2026-11-08T22:31:02Z | 26 |
| devex-tooling | 2026-11-08T23:23:39Z | 11 |
| rust-services-dev-01 | 2026-11-09T03:33:08Z | 2 |
| language-culture-en | 2026-11-09T05:31:04Z | 1 |
| language-culture-ru | 2026-11-09T11:46:44Z | 1 |
| language-culture-ge | 2026-11-09T11:46:51Z | 1 |
| rust-services-dev-02 | 2026-11-09T12:33:04Z | 2 |
| backend-dev-01 | none | 0 |
| backend-dev-02 | none | 0 |
| collection.json | none | 0 |
| db-admin | none | 0 |
| domain-transit | none | 0 |
| edge-hosting | none | 0 |
| flutter-dev-01 | none | 0 |
| flutter-dev-02 | none | 0 |
| legal-expert-ch | none | 0 |
| legal-expert-ee-eu | none | 0 |
| web-dev-01 | none | 0 |
| web-dev-02 | none | 0 |

## ux-designer-01's last relay copy

The latest relay arrival in its log: 2026-11-09T03:52:31Z. Its arrivals on 2026-11-09 by carrier: relay 1, interweave 4.

## Totals

Arrival lines collected: 7584. Delivery records collected: 5237. The arrival lines equal the copies the report counts: relay 3 963 + 37, InterWeave 3 068 + 516.
