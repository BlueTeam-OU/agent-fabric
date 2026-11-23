# Rows behind the 2026-11-18 parity record

The JSON lines below are filed unedited from the wider collection (`--since 2026-11-14T00:00:00Z`); the tables are built from
both collections' `meta.json` and `collection.json`, the list of multi-copy pairs is derived from the wide collection's arrival
lines, and the last section is `fabric-ctl` output. Together they hold the times and ids
[2026-11-18-interweave-parity.md](2026-11-18-interweave-parity.md) cites that the tool's output does not print.

## Collection bounds and state (each account's `meta.json`, `collection.json`)

| collection | account | since | until | margin_s | journal | complete |
|---|---|---|---|---|---|---|
| wide | user | 2026-11-14T00:00:00Z | 2026-11-18T02:00:00Z | 3600 | ok | True |
| wide | language-culture-en | 2026-11-14T00:00:00Z | 2026-11-18T02:00:00Z | 3600 | ok | True |
| wide | python-dev-03 | 2026-11-14T00:00:00Z | 2026-11-18T02:00:00Z | 3600 | ok | True |
| narrow (control) | user | 2026-11-15T09:00:00Z | 2026-11-18T02:00:00Z | 3600 | ok | True |
| narrow (control) | language-culture-en | 2026-11-15T09:00:00Z | 2026-11-18T02:00:00Z | 3600 | ok | True |
| narrow (control) | python-dev-03 | 2026-11-15T09:00:00Z | 2026-11-18T02:00:00Z | 3600 | ok | True |

wide: 30 accounts, journal not ok or incomplete: none

narrow: 30 accounts, journal not ok or incomplete: none

## When each collection was written

The `meta.json` files' modification times (`ls --time-style=+%FT%TZ`, UTC), earliest and latest of each collection's accounts:

```text
wide    30 accounts  2026-11-18T01:40:12Z  2026-11-18T01:40:13Z
narrow  30 accounts  2026-11-18T01:39:19Z  2026-11-18T01:39:20Z
```

## The four control pairs

`user/arrivals.jsonl`:

```text
{"addressee": "develop-qzapp/user", "carrier": "relay", "mid": "01a1db67-e363-728c-a911-d55d4bb2c4c6", "t": "2026-11-14T18:53:02Z", "verdict": "unauthenticated"}
{"addressee": "develop-qzapp/user", "carrier": "interweave", "mid": "01a1db67-e363-728c-a911-d55d4bb2c4c6", "t": "2026-11-14T18:53:03Z", "verdict": "ok"}
{"addressee": "develop-qzapp/user", "carrier": "relay", "mid": "01a1de20-7393-759c-9b5c-241c4c03d0a0", "t": "2026-11-15T07:33:51Z", "verdict": "unauthenticated"}
{"addressee": "develop-qzapp/user", "carrier": "relay", "mid": "01a1de35-44cf-765b-893c-ed39dd854b1a", "t": "2026-11-15T07:56:46Z", "verdict": "unauthenticated"}
{"addressee": "develop-qzapp/user", "carrier": "relay", "mid": "01a1db67-e363-728c-a911-d55d4bb2c4c6", "t": "2026-11-15T23:57:42Z", "verdict": "unauthenticated"}
```

`user/shown.jsonl`:

```text
{"mid": "01a1db67-e363-728c-a911-d55d4bb2c4c6", "pending": true, "t": "2026-11-14T18:53:02Z", "via": "relay"}
{"mid": "01a1db67-e363-728c-a911-d55d4bb2c4c6", "t": "2026-11-14T18:53:03Z", "via": "relay"}
{"mid": "01a1de20-7393-759c-9b5c-241c4c03d0a0", "pending": true, "t": "2026-11-15T07:33:51Z", "via": "relay"}
{"mid": "01a1de20-7393-759c-9b5c-241c4c03d0a0", "t": "2026-11-15T07:33:52Z", "via": "relay"}
{"mid": "01a1de35-44cf-765b-893c-ed39dd854b1a", "pending": true, "t": "2026-11-15T07:56:46Z", "via": "relay"}
{"mid": "01a1de35-44cf-765b-893c-ed39dd854b1a", "t": "2026-11-15T07:56:47Z", "via": "relay"}
```

`user/acks.jsonl`:

```text
{"addressee": "develop-qzapp/user", "mid": "01a1db67-e363-728c-a911-d55d4bb2c4c6", "ok": true, "t": "2026-11-14T18:53:03Z"}
{"addressee": "develop-qzapp/user", "mid": "01a1de20-7393-759c-9b5c-241c4c03d0a0", "ok": true, "t": "2026-11-15T07:33:52Z"}
{"addressee": "develop-qzapp/user", "mid": "01a1de35-44cf-765b-893c-ed39dd854b1a", "ok": true, "t": "2026-11-15T07:56:47Z"}
{"addressee": "develop-qzapp/user", "mid": "01a1db67-e363-728c-a911-d55d4bb2c4c6", "ok": true, "t": "2026-11-15T23:57:43Z"}
```

`language-culture-en/arrivals.jsonl`:

```text
{"addressee": "develop-qzapp/language-culture-en", "carrier": "interweave", "mid": "01a1de05-9074-725f-9992-dd9c0b09f922", "t": "2026-11-15T07:04:30Z", "verdict": "ok"}
{"addressee": "develop-qzapp/language-culture-en", "carrier": "interweave", "mid": "01a1de20-7393-759c-9b5c-241c4c03d0a0", "t": "2026-11-15T07:33:51Z", "verdict": "ok"}
{"addressee": "develop-qzapp/language-culture-en", "carrier": "interweave", "mid": "01a1de35-44cf-765b-893c-ed39dd854b1a", "t": "2026-11-15T07:56:46Z", "verdict": "ok"}
{"addressee": "develop-qzapp/language-culture-en", "carrier": "relay", "mid": "01a1de20-7393-759c-9b5c-241c4c03d0a0", "t": "2026-11-15T21:11:00Z", "verdict": "unauthenticated"}
{"addressee": "develop-qzapp/language-culture-en", "carrier": "relay", "mid": "01a1de05-9074-725f-9992-dd9c0b09f922", "t": "2026-11-15T21:11:00Z", "verdict": "unauthenticated"}
{"addressee": "develop-qzapp/language-culture-en", "carrier": "relay", "mid": "01a1de35-44cf-765b-893c-ed39dd854b1a", "t": "2026-11-15T21:11:00Z", "verdict": "unauthenticated"}
```

`language-culture-en/shown.jsonl`:

```text
{"mid": "01a1de05-9074-725f-9992-dd9c0b09f922", "pending": true, "t": "2026-11-15T07:04:56Z", "via": "interweave"}
{"mid": "01a1de05-9074-725f-9992-dd9c0b09f922", "t": "2026-11-15T07:04:56Z", "via": "interweave"}
{"mid": "01a1de20-7393-759c-9b5c-241c4c03d0a0", "pending": true, "t": "2026-11-15T21:11:00Z", "via": "relay"}
{"mid": "01a1de35-44cf-765b-893c-ed39dd854b1a", "pending": true, "t": "2026-11-15T21:11:00Z", "via": "relay"}
{"mid": "01a1de20-7393-759c-9b5c-241c4c03d0a0", "t": "2026-11-15T21:11:00Z", "via": "relay"}
{"mid": "01a1de35-44cf-765b-893c-ed39dd854b1a", "t": "2026-11-15T21:11:00Z", "via": "relay"}
```

`language-culture-en/acks.jsonl`:

```text
{"addressee": "develop-qzapp/language-culture-en", "mid": "01a1de20-7393-759c-9b5c-241c4c03d0a0", "ok": true, "t": "2026-11-15T21:11:01Z"}
{"addressee": "develop-qzapp/language-culture-en", "mid": "01a1de05-9074-725f-9992-dd9c0b09f922", "ok": true, "t": "2026-11-15T21:11:01Z"}
{"addressee": "develop-qzapp/language-culture-en", "mid": "01a1de35-44cf-765b-893c-ed39dd854b1a", "ok": true, "t": "2026-11-15T21:11:01Z"}
```

`python-dev-03/backfills.jsonl` (the sender of `01a1db67-e363`):

```text
{"at": "2026-11-14T18:53:02Z", "channel": null, "mid": "01a1db67-e363-728c-a911-d55d4bb2c4c6", "outcome": "relay-took-send"}
```

`user/watch.jsonl`, 2026-11-15T23:50 to 23:59:

```text
{"code": 0, "event": "end", "pid": 2403717, "reason": "delivery", "t": "2026-11-15T23:50:43Z"}
{"event": "start", "pid": 2948986, "t": "2026-11-15T23:50:50Z"}
{"code": 0, "event": "end", "pid": 2948986, "reason": "delivery", "t": "2026-11-15T23:57:37Z"}
{"event": "start", "pid": 3049391, "t": "2026-11-15T23:57:42Z"}
{"code": 0, "event": "end", "pid": 3049391, "reason": "delivery", "t": "2026-11-15T23:57:43Z"}
{"event": "start", "pid": 3051240, "t": "2026-11-15T23:57:57Z"}
{"code": 0, "event": "end", "pid": 3051240, "reason": "delivery", "t": "2026-11-15T23:57:57Z"}
{"event": "start", "pid": 3065301, "t": "2026-11-15T23:58:50Z"}
```

## Every pair with more than one relay arrival in the wide collection

```text
01a1d922-359f-7260-a063-1c77df771b59 develop-qzapp/architect-cto-01 2026-11-14T08:17:43Z 2026-11-14T08:17:56Z
01a1db67-e363-728c-a911-d55d4bb2c4c6 develop-qzapp/user 2026-11-14T18:53:02Z 2026-11-15T23:57:42Z
01a1dce5-1641-7bb6-9363-927d7b6ba54f develop-qzapp/ux-designer-01 2026-11-15T01:49:24Z 2026-11-15T01:49:43Z
```

## Modes, read 2026-11-18T06:19:09Z (not at collection): `fabric-ctl all interweave`

```text
account status mode stranded
user ok relay-record 0
architect-cto-01 ok relay-record 0
backend-dev-01 ok relay-record 0
backend-dev-02 ok relay-record 0
flutter-dev-01 ok relay-record 0
flutter-dev-02 ok relay-record 0
web-dev-01 ok relay-record 0
web-dev-02 ok relay-record 0
db-admin ok relay-record 0
devex-tooling ok relay-record 0
edge-hosting ok relay-record 0
domain-transit ok relay-record 0
brand-comms-01 ok relay-record 0
language-culture-ge ok relay-record 0
p2p-network-dev-01 ok relay-record 0
language-culture-ru ok relay-record 0
language-culture-en ok relay-record 0
python-dev-01 ok relay-record 0
rust-ui-dev-01 ok relay-record 0
rust-ui-dev-02 ok relay-record 0
p2p-network-dev-02 ok relay-record 0
rust-services-dev-01 ok relay-record 0
python-dev-02 ok relay-record 0
python-dev-03 ok relay-record 0
python-dev-04 ok relay-record 0
rust-services-dev-02 ok relay-record 0
legal-expert-ee-eu ok relay-record 0
legal-expert-ch ok relay-record 0
legal-expert-ge ok relay-record 0
ux-designer-01 ok relay-record 0
```
