# The journal's import, run live on the coordinator's own account

ADR-041 rule 9: each agent imports its own GZCoord history through the
carrier, as itself. `episodic.py gzcoord-import` was run once, on
develop-qzapp, as the account `user` (fabric-coordinator), against the
fleet's relay, before the import was offered to any other account.

## What was run

`/usr/local/bin/fabric-python tools/fabric/episodic.py gzcoord-import`,
with no project named, so every integration was covered: one channel,
`gzapp:gzcoord`. The journal already held 38 rows, all live-captured
since #78.

## What it measured

- **Coverage.** 9 pages of up to 500, read to the newest record, seq
  10764: `complete: true`.
- **Time.** 1.84 s wall-clock for the whole channel.
- **Stored.**
  - 288 sent messages were new rows; 25 were already in the journal as
    live sends.
  - 334 received messages were new rows; 13 were already there. That is
    242 addressed TO this account, 47 TO-ROLE of a role it held at the
    time, and 59 broadcasts after its birth.
  - 1 received id arrived with a body different from the kept one; it
    is in `conflicts`, and the first copy stands.
- **Not stored.**
  - 3206 records addressed to other accounts.
  - 452 retired HELLO and GOODBYE presence messages.
  - 1 record that was not GZCOORD/1.
  - 162 TO-ROLE messages to roles this account did not hold when they
    were sent. By role: architect-cto 42 (outside the stretch this
    account held it), devex-tooling 36, language-culture 33,
    backend-dev 15, flutter-dev 11, db-admin 8, domain-transit 7,
    web-dev 6, product-i18n 3, edge-hosting 1. Every one has the reason
    "role not held then".
- **The new gates.** Nothing came from before this agent's birth
  (2026-01-14T20:27:33Z, from its UUIDv7). No record had a missing time.
  No record claimed this account's FROM with another relay sender.
- **The sent ledger.** 222 sent messages are not in
  `gzcoord-sent.jsonl`, and none differs from it by hash or seq. The
  ledger's first entry is dated 2026-09-26; the sends it lacks are older
  than that.
- **Privacy.** The report `episodic-import.json` is mode 0600 and holds
  counts, ids and role names only. It holds no message content and no
  token.

## The send rule, corrected after review

The first run stored a message as this account's send when its FROM and
the relay's `sender` both named the account. #84's review showed that
proves nothing: the relay authenticates no sender, so either field is a
claim. The rule is now:

- A send is `accepted` when the account's own records hold that body:
  the ledger, or a row its live journal wrote.
- A send dated after the ledger began but missing from it is refused.
- A send from before the ledger is kept as `unverified`.

The coordinator's journal was re-judged by that rule. A backup was kept
beside it first. Of the 288 sends the first run imported:

- 66 are verified by the ledger and stay `accepted`;
- 222 predate the ledger and are now `unverified`;
- none was dated after the ledger began and missing from it, so nothing
  was removed and no send had been forged.

The 222 are the same 222 the first run reported as missing from the
ledger.

## What it decides

The import, with the send rule above, is safe to offer to every account.
It reads its own channel, moves no cursor, keeps only what rule 9
entitles and what the account's own records can vouch for, and takes
under two seconds for the whole of the fleet's history. Its rollout,
run once per account from bootstrap, follows bootstrap's port to Python.
