# GZCoord on InterWeave only: the cutover from the dual run

**Status 2026-11-14.** The owner answered D1, D2, D4, D5 and D10 on 2026-11-13, each as
recommended (§7). D3's first half is done: #573 merged on 2026-11-13. D6, D7 and D8 are not
asked yet, and D9 is partly answered. The records named in §4 are not amended yet.

A plan for the owner's review, drafted for fabric-coordinator. It decides nothing: every step
that changes what carries a message waits for the owner's word and the record named beside it
(§4). The goal is the owner's: the GZCoord data plane runs on InterWeave only, and the central
relay no longer carries, stores or is read for GZCoord messages.

Read against agent-fabric origin/main 8c3613b1 (2026-11-13), the open pull request #573 at its
head, and `docs/live-checks/2026-11-09-interweave-parity.md` with its two companion files. Every
claim about the code names its file and function; a path with no function is the whole module.

## 1. Where the fleet stands

- **Every message goes by both carriers, and the relay is the record.**
  `tools/fabric/gzcoord/transport/__init__.py` `open_transport` builds one shape and no other:
  `RelayTransport` as the primary and `CarrierTransport` as a mirror (no mirror when the journal
  is off). Its docstring says "Moving the primary is a change to this factory".
- **There is no per-account transport mode on main.** The word `both` that
  `fabric-ctl all interweave` prints is the `units` column of
  `tools/fabric/control/ctl.py` `_table_carrier`: the daemon unit and the client unit are both
  active. The only switch is the carrier's presence (`tools/fabric/gzcoord/carrier/adapter.py`
  `Adapter.present`, "The switch is the carrier itself"). §6 proposes the mode this plan needs.
- **The control plane rides the relay alone.** `runtime/control/config.json` has
  `"control_carrier": "relay"`. The second carrier of agent-fabric ADR-029 rule 18 is built
  (`tools/fabric/gzcoord/carrier/control_link.py`, `tools/fabric/control/agentd.py` `main`, the
  `CARRIER_DUAL` branch) and is off. `agentd.control_config` accepts `relay` or `dual` and
  refuses anything else, so control has no setting for InterWeave alone.
- **Presence is control traffic.** `gzcoord-send` asks it before every addressed send
  (`tools/fabric/gzcoord/send.py` `asked_presence`), through
  `tools/fabric/control/presence.py` `ask_presence`, which posts to and pages the relay's
  control channel. A relay that is down makes every `TO` and `TO-ROLE` send exit 4 unless
  `--force` is given.
- **`fabric-history` does not read the relay.** `tools/fabric/history.py` reads the account's
  journal through `episodic.open_readonly`. The docstring of #573's `backfill.py` lists it
  among the relay's readers; it is not one. The journal's one relay reader is the import
  (`tools/fabric/episodic_import.py`).
- **What the last parity run lacked** (`docs/live-checks/2026-11-09-interweave-parity.md`): the
  rollback drill was never run; both relay-outage drills read UNSETTLED because the
  acknowledgement log did not exist yet; 13 InterWeave misses after the rollout days and 516
  duplicate InterWeave copies were not traced. A relay-outage drill of 2026-11-12 is cited by
  #573; no record of it is in `docs/live-checks/` on main.

## 2. Inventory: what depends on the relay today

Columns: where; what it uses the relay for; what replaces it under InterWeave only; whether the
replacement exists on main. "Journal" is the account's `episodic.db` (agent-fabric ADR-041),
"ledger" is `gzcoord-shown.jsonl` (`tools/fabric/gzcoord/carrier/ledger.py`), "spool" is the
carrier's `interweave/inbox.jsonl` (`carrier/arrivals.py` `Spool`), "outbox" is the carrier's
`deliveries.jsonl` (`carrier/record.py` `Outbox`).

### 2.1 Sending

| where | uses the relay for | replacement | exists? |
|---|---|---|---|
| `tools/fabric/gzcoord/send.py` `main` | the post (`tp.send_primary`), whose outcome is the exit status; the token is required before anything is sent (`if not tok: return 3`) | the carrier's `send` op: accepted when every roster recipient is in the outbox | the op exists (`carrier/engine.py` `Carrier.send`, `adapter.Adapter.post`); as the exit status it does not: `via_mirrors` changes no status |
| `send.py` `main`, the `send.sent` line and `record_sent` | the relay's `seq` on stdout (`sent seq <n> <TYPE> <id>`) and in `gzcoord-sent.jsonl` | no sequence: the MESSAGE-ID (UUIDv7) names the message | no: the stdout contract is frozen in the docstring and in `communication/gzcoord/i18n/en-US.json` `send.sent` |
| `send.py` `main`, the `gzcoord-out-final --seq` call; `tools/fabric/episodic.py` `out_final` | the relay's seq as the journal row's provenance | `--carrier interweave`, no seq | yes (`via_mirrors` already writes it) |
| `send.py` `check_addressees`, `asked_presence` | presence, over the relay's control channel, with the relay token in the request | the same op over control's second carrier | no: `presence.ask_presence` has one path, `gzcoord.api` |
| `tools/fabric/gzcoord/transport/relay.py` `RelayTransport.send`, `refresh`, `never_delivered`, `explain` | `POST /api/send`; a refused token re-read; what a failure proves | the carrier transport's own answers to the same four questions | no: `transport/carrier.py` `CarrierTransport` is a mirror and has none of `Primary`'s verbs (`transport/base.py` says a mirror "need not implement them; moving the record to another transport is the day it must") |
| `tools/fabric/gzcoord/intake.py` `queue_for_addressee` | `fabric-ctl <login> jobs-add`, a control action over the relay | the same action over control's carrier | partly (control's second carrier is built and off) |
| #573, `tools/fabric/gzcoord/backfill.py` `tick` and `agentd.backfill_tick` (not on main) | reads the relay's newest page and posts carrier-only rows to it | nothing: under InterWeave only it must not run | n/a |

### 2.2 Receiving and the watch

| where | uses the relay for | replacement | exists? |
|---|---|---|---|
| `tools/fabric/gzcoord/inbox.py` `main` | `transport.start_hosted` at every run: the hosting workspace starts the relay (`inbox_parts/relay.py` `ensure_relay`) | nothing | n/a |
| `inbox.py` `main`, the watch loop | the long poll is the clock of the watch (`tp.fetch_page` → `RelayTransport.receive`, `GET /api/wait`); an unreachable relay ends a quiet `--until-delivery` watch after 15 minutes with exit 5 (`UNTIL_DELIVERY_DOWN_S`, `watchlock.mark_relay_down`), whether or not the carrier is up, and what the carrier brings after that waits in the spool for the next watch | a wait on the carrier | no: `CarrierTransport.receive` ignores `seconds` and returns at once (`Adapter.unseen` is a poll); `wait_loop` driven by it alone would spin |
| `inbox_parts/watch.py` `wait_loop`, `acknowledge` | `POST /api/ack` per record, the relay's one cursor per consumer; the journal-hold rule compares relay seqs | the ledger: an arrival is listed by `Spool.unseen` until the ledger holds its final line | yes for carrier arrivals (`transport/dedup.py` `admit`, `CarrierTransport.ack` is a no-op by design) |
| `transport/mux.py` `TransportMux.fetch_page`, `ack`, `_log_ack`, `on_arrival` | the page, the acknowledgement, and the two evidence logs of the relay's copies (`gzcoord-arrivals.jsonl` relay lines, `gzcoord-acks.jsonl`) | carrier arrival lines only; no acknowledgement log | yes (`carrier/engine.py` `Carrier.finish` writes the arrival line) |
| `inbox_parts/records.py` `mark_retransmissions`; `inbox.py` `fetch_recent` | the relay's newest 500 records, to mark a retransmission by its earlier seq | the ledger already refuses a second showing | yes |
| `inbox.py` `main`, `--wait --keyword`; `records.keyword_hit` | every reader sees every message, so a keyword can fire on a message addressed to someone else | nothing: a `TO` reaches its addressee only, and a copy not addressed here is receipted and dropped (`Carrier.finish`) | given up (§3) |
| `inbox_parts/config.py` `integration_config`, `default_relay` | a project counts as configured only with `relay_url` and `channel` (`projects/<id>/integration/gzcoord/config.json`, 15 files) | "configured" means the account has a valid roster row | no |
| `inbox_parts/tokens.py` `token`, `_token`, `synced_token` | `CLAUDE_BRIDGE_AUTH_TOKEN`; the inbox and the sender stop without it | no token: the PeerId is the credential | yes (roster) |
| `runtime/claude-code/hooks/watch-on-stop.py` `relay_down`, `relay_answers`, `configured_relay_url`, `decide` | probes the relay before asking a session to re-arm its watch; while the give-up marker stands and the relay is silent it asks for none, so a session stays unwatched through the outage | a probe of the carrier's socket | no |

### 2.3 Readers of the relay's record

| where | uses the relay for | replacement | exists? |
|---|---|---|---|
| `inbox.py` `main` `--replay`; `inbox_parts/records.py` `replay` | `primary.newest(500)`: one message by relay seq, relay id or MESSAGE-ID, with the relay's `sender` | the journal row by MESSAGE-ID: text, `sender`, `sender_verified`, `carrier` | the data is there (`episodic.py` `inbound`, `carrier/main.py` `journal_inbound`); the reader is not: only `history.py` reads rows back, cut and masked |
| `inbox.py` `main` `--history`; `records.history` | the relay's newest 500, one line per message addressed here, by seq | `fabric-history`, or the same listing from the journal | yes as `fabric-history`; not under `gzcoord-inbox --history` |
| `tools/fabric/github/arm.py` `verify_grant` (`--authorization`, `--waiver`) | runs `gzcoord-inbox --replay <ref> --json` and requires the relay's `sender` to equal `FROM`; the relay's sender is a claim | the journal row, whose sender the carrier verified by PeerId (agent-fabric ADR-064 rule 9) | no; and ADR-041 rule 7 says a history result is "not authorisation" (§4) |
| `tools/fabric/jobsparts/records.py` `fetch_message` (`fabric-jobs add --request`) | the same `--replay --json` | the same journal read | no |
| `tools/fabric/episodic_import.py` `Importer`, `main`; `tools/fabric/relay.py` `pages`, `call`; `bootstrap.py` `Bootstrap.journal_import` | backfills a journal from the relay's whole channel | nothing: a carrier keeps no past, and an agent's journal starts at its birth | n/a |
| `tools/fabric/relay_catchup.py` `catch_up`; `tools/fabric/provisioning/store_step.py` `secrets_step` | puts a new account's relay cursor at the newest message | nothing: a new login receives what is sent after its roster row is admitted | n/a |
| `tools/fabric/drift.py` `inbox`; `tools/fabric/status.py` `inbox_state`; `tools/fabric/control/ops/__init__.py` `_inbox`; `agentd.py` `main` (`inbox_opts`) | the account's unread count and lag, read from the relay's cursor (`/api/wait` with `timeout_seconds=0`) | the spool's unseen count and the outbox's outstanding deliveries (`Carrier.status`) | the numbers exist (`gzcoord-carrier status`); nothing reads them into `fabric-status` or `fabric-ctl status` |

### 2.4 Evidence, hosting, backup

| where | uses the relay for | replacement | exists? |
|---|---|---|---|
| `carrier/parity.py` (`relay_outage`, the per-carrier counts); `tools/fabric/control/carrier_evidence.py` (`acks`, `shown`); `evidence_collect.py` | compares the two carriers | a one-carrier health report: stranded deliveries, receipt latency, blocked codes | no |
| `tools/fabric/bootstrap.py` `Bootstrap.relay`, `relay_holder`; `communication/gzcoord/runtime/gzcoord-relay.service` | installs and starts the relay on the hosting account | nothing, once control has left the relay too (§4, gate 3) | n/a |
| `Bootstrap.relay_backup`; `runtime/control/agent-fabric-relay-backup.{service,timer}`; `tools/fabric/secret_relay.py`; `tools/fabric/secretstore/relaycopy.py` `relay_backup` | the 6-hourly copy of the relay's database | the daily state copy, which already carries `episodic.db` and `gzcoord-sent.jsonl` (`secretstore/statecopy.py` `STATE_FILES`, `EPISODIC`); it does not carry the outbox, the spool or the ledger | partly |
| `tools/fabric/launcher/secrets.py` `HARNESS_EXPANDS`, `SYNCED_SECRETS`; `provisioning/store_step.py` `secrets_step` ("relay credential") | hands the relay token to a session and to a project's `.mcp.json` `claude-bridge` entry | nothing | n/a |
| `tools/fabric/transport-calls.json` | admits `agentd.py`, `ctl.py`, `presence.py` and `drift.py` as relay callers outside the transport | each entry leaves with its fix | n/a |

### 2.5 The control plane on the same relay

Not GZCoord messages, so outside the goal as worded; listed because the relay cannot be retired,
and presence cannot survive a relay outage, while these stand.

| where | uses the relay for | replacement | exists? |
|---|---|---|---|
| `tools/fabric/control/agentd.py` `main` (`call`, `post`, `prime`, the read loop) | reads every request on `fabric:control` by `since_id`, posts every reply | `control_link` on the `fabric-control` endpoint | built, off; no InterWeave-alone value |
| `agentd.py` `state_poster`; `control/ctl.py` `states`; `control/queue.py` `read_waits`; `control/pool.py` `state_reader`, `role_from_stream` | the state channel: each account's newest state record, read back from the relay's stored history | a request each agentd answers, or a table the reader keeps | no: InterWeave stores no history |
| `control/ctl.py` `main` | posts the request, pages the replies | `_second_carrier`, through the operator's agentd socket | built, off |
| `control/presence.py` `ask_presence`; `control/queue.py` `ask_holder`, `bound_call`, `relay` | public ops asked by any account (`presence`, `pool-list`, `pool-claim`, `job-state`) | the asker's own agentd socket | no |
| `control_link.RELAY_ONLY_OPS` (`interweave`, `-install`, `-start`, `-stop`) | the ops that take the InterWeave channel down ride the relay by rule (ADR-064 rule 14) | `bin/fabric-op` through hostexec (`control/breakglass.py`, ADR-029 rule 19) | built; verified on the local backend only |

## 3. What the relay gives, and what InterWeave gives or the fleet gives up

| capability | on the relay | on InterWeave only | verdict |
|---|---|---|---|
| store and forward to an addressee with no session | the relay holds the record until that consumer acknowledges | the receiving carrier is a unit that runs without a session: it journals, spools and receipts (`Carrier.finish`), and the inbox shows the spool at the next watch | given |
| store and forward to an addressee whose account is down | the same | the sender's outbox retries to the receipt, 1 s doubling to 5 min, never given up (`carrier/record.py` `backoff`, `Outbox.due`) | given, with a difference: the message waits on the sender's disk, not at a third place; a sender host lost before the receipt loses the delivery but not the text (the journal's outbound row holds it) |
| a send while the sender's own carrier is down | the relay takes it | none: `Adapter.post` answers `absent` or `failed` | gap: the send must fail loudly (W8) |
| a global order and a seq | one sequence per channel; `--replay <seq>`, `--history <seq>`, the delivery title and the job's `source.seq` cite it | none: one direct send per recipient, no order across senders | given up; the MESSAGE-ID's UUIDv7 time and `IN-REPLY-TO` order a thread (`history.py` `thread_ids`) |
| history replay | anyone with the token lists the whole channel | each agent's journal holds what it sent and what was addressed to it; nobody holds the whole | own history given (after W3); the whole-channel record given up |
| broadcast | one post, every reader | one direct send per roster member and a receipt back (`Carrier.recipients`, ADR-064 rule 6) | given; the roster is the membership, so a login with no valid row receives nothing |
| TO-ROLE fan-out | read by whoever holds the role when its watch reads | sent to every member; each carrier keeps it only if its account holds the role at arrival (`carrier/main.py` `make_me`, read per message) | given, with a difference: a login that binds the role after the arrival never sees it; untested (W11) |
| alerts on others' traffic (`--wait --keyword`) | every reader passes every message | a message not addressed here never reaches the inbox | given up |
| an authenticated sender | none: `sender` is a claim (agent-fabric ADR-033 §6) | the PeerId, mapped by the roster; a mismatch is shown flagged (ADR-064 rule 9) | gained |
| presence | a control op on the relay | unchanged by the data plane; still on the relay until control moves | gap for the goal's purpose: a relay outage still stops addressed sends (W12) |
| the human relay (ADR-033 rule 7) | a person carries text between terminals when the relay is down | the same procedure, used when a carrier cannot deliver; it never used the relay | given; rule 7's trigger is reworded |
| journal-off break-glass (ADR-041 rule 10) | "the route is the relay alone" (ADR-064 rule 8); `carrier/main.py` `cmd_run` refuses to start | none | gap: to be decided (D7) |
| reach to a second host | none: the relay binds loopback | the profile's listener; but the carrier assumes one host: `Carrier.recipients` carries a `TO` only when its host is the carrier's own, and `Carrier.finish` judges and journals every sender as `<own host>/<login>` | gap (W10); for an account on fabric-h2 InterWeave is the only route from its first day |
| one place to back up | one database, copied every 6 h | 30 state directories, copied daily | changed: the copy must add the outbox |

Two new single points come with the move, and belong in the operator's inventory (ADR-069 §1):
the roster and the coordinator's countersigning key (a roster that does not verify leaves a
carrier "with NO recipient and admitting no inbound", `Carrier.refresh_roster`, on every account
that pulls it), and the pinned InterWeave release (`runtime/interweave/release.json`).

## 4. The gates, in order

The owner's word is asked three times, each on evidence filed in `docs/live-checks/` and each
landing as records only fabric-coordinator writes. Nothing in the grammar changes, so ADR-032 is
not amended; what the carrier observes of ordering and loss is the evidence its §7 waits for.

**Gate 1: InterWeave becomes the transport of record** (ADR-064 rule 11, as written). Evidence:

1. #573 merged, and its missing read-back done: a message through the real carrier to a second
   account, shown once, then found on the relay after its return.
2. The rollback drill, never run: `fabric-ctl <login> interweave-stop` on two accounts in the
   middle of a window with traffic, then `interweave-start`; `gzcoord-carrier parity --drill`
   reads `nothing_lost`.
3. A relay-outage drill whose acknowledgements are logged, judged by
   `gzcoord-carrier parity --relay-drill` as passing, not UNSETTLED. It must include a watch
   restart inside the outage (the 2026-11-09 report says that property was not exercised) and
   last past 15 minutes, so the watch's give-up (§2.2) is seen. The 2026-11-12 drill gets its
   record, whatever it shows.
4. A fresh parity report over a window after 2026-11-09 in which every InterWeave miss has a
   cause other than "the sender recorded no InterWeave delivery", or that cause is itself
   traced; and the duplicate copies explained. Under InterWeave only a miss is a lost message.
5. A `TO-ROLE` recipient: held (100 pairs in the last report).

Records: an amendment of ADR-033 (§2 third bullet, §8: the relay is the mirror) and of ADR-064
(rule 11: the record moves account by account under a mode; rule 7: which carrier's acceptance
sets the journal row; §2 "Dual run"). ADR-041 rule 7 is amended in the same pull request if
`fabric-pr arm` is to read a grant from the journal (D4). ADR-029 §2 gains the mode's action op.

**Gate 2: the relay carries no GZCoord.** Evidence: every account in `carrier-record` for the
agreed soak (D8) with no stranded delivery; a carrier-outage drill (one account's units stopped
for 30 minutes: senders' outboxes hold, everything arrives once on its return, shown once); two
accounts in `carrier-only` through a relay stop of a working hour with every GZCoord function
exercised (send, watch, replay, `fabric-pr arm --authorization`, `fabric-jobs add --request`,
a REQUEST's job intake); and W12's read-back if the owner takes D1's recommendation. Records:
ADR-033 amended again (the relay carries control only; rule 7's trigger; rule 5's "the hosting
session's start brings it up"), ADR-064 (rules 8, 11 and 14, whose "the relay carries for it
alone" goes; the dual run ends), ADR-041 rule 10 (D7), ADR-030 rule 3's wording, and ADR-069 §1
(the "messages between sessions" row is rewritten and the two new rows of §3 added: ADR-034
rule 1 wants that in the same pull request).

**Gate 3: the relay is retired.** A separate word, on the control parity report ADR-029 rule 18
already asks for, plus the state stream's replacement and the four relay-only ops read back over
`fabric-op`'s SSH backend. Records: an amendment of ADR-029 (rule 18, §2), and a new record that
retires the relay and supersedes ADR-033's deployment rules (5 and 6) and ADR-034 §7's first
step; ADR-069 loses the relay rows. This plan sizes it only as far as §5's W16.

**#573's place.** It is needed for the window and moot after it. While the relay is the record
(today) and while it is the mirror (`carrier-record`), the backfill keeps the relay complete, so
a relay-only reader misses nothing and a step back loses nothing. Once W3 lands, no reader needs
the relay's copy, and the backfill's only remaining use is the rollback target. In
`carrier-only` it must be off: it is a writer to the relay (W9). It should merge now.

## 5. The work, in sequence

Surfaces: **PD** is python-dev's `paths` in `policies/authority.json` (its own branch and pull
request); **PD-supply** is its `supplies` (a `for/` branch fabric-coordinator folds); **DX** is
devex-tooling's `tools/fabric/github/`; **FC** is fabric-coordinator: `tools/fabric/lint.py`
`CONTRIBUTOR_NEVER` (`docs/adr/`, `communication/gzcoord/protocol/`,
`tools/fabric/transport-calls.json`, `runtime/interweave/roster.json`, most of
`runtime/claude-code/`) and whatever no contributor's path reaches (`communication/gzcoord/docs/`,
`skills/`, `i18n/`, `projects/*/integration/gzcoord/`, `docs/live-checks/`). Size: S under about
150 changed lines with tests, M up to about 500, L beyond.

| id | piece | surface | accepted when | size | needs |
|---|---|---|---|---|---|
| W1 | Land #573; do its real-carrier read-back; file the 2026-11-12 drill | PD (python-dev-03); FC for the record | the PR's suite; the read-back's three facts (shown once, on the relay after return, a `gzcoord-backfill.jsonl` line) in a live check | open PR | - |
| W2 | The two drills and the fresh parity report (gate 1, items 2 to 4); trace the misses and duplicates | FC runs and files; PD reads `carrier/engine.py` `send_due` and `Adapter.post` for the causes | the report's "what it lacks" section is empty; each miss has a cause a reviewer can find in the computed file | S, mostly operations | W1 |
| W3 | Journal-first `--replay` and `--history`: a MESSAGE-ID is answered from the journal in every mode; `--json` gains `carrier` and `sender_verified`; a relay seq is still answered from the relay while one is configured | PD (`inbox.py` `main`, `inbox_parts/records.py`; reads through `episodic.open_readonly`, so no supply-tier file changes) | a test with the relay refusing every connection: a row journaled by the carrier alone replays with exit 0, one not addressed exits 2; `jobsparts/records.py` `fetch_message` adds the job | M | - |
| W4 | `verify_grant` accepts the journal's answer and, for a row the carrier brought, requires `sender_verified` and sender equal to `FROM` | DX (`tools/fabric/github/arm.py`); FC for ADR-041 rule 7 | `tests/test_arm_cli.py`: a grant the carrier alone delivered arms with the relay down; an unverified sender on such a row is refused | S | W3, D4 |
| W5 | The transport mode: `relay-record` (today), `carrier-record`, `carrier-only`; read by `open_transport`; set by a signed action and shown by the `interweave` read and `_table_carrier` (§6) | PD (`gzcoord/transport/`, `control/`); FC supplies ADR-029's op row | default unchanged with no state file; `fabric-ctl all interweave` prints each account's mode; a running watch takes a changed mode within a minute; `carrier-only` is refused while any placed account reports `relay-record` | M | D2, D10 |
| W6 | The carrier as a `Primary`: `CarrierTransport.receive` waits (a `wait` op on the adapter socket), `newest` reads the journal, `explain` and `never_delivered` answer for the carrier; `TransportMux` takes the relay as a mirror both ways | PD (`gzcoord/transport/`, `carrier/server.py`, `carrier/engine.py` `handle_request`); FC for `CARRIER-CONTRACT.md` §6 | `tests/test_gzcoord_transport.py`: in `carrier-record` a relay that refuses every call changes neither the exit status nor what is shown; an idle watch arm makes a bounded number of adapter calls; a message is shown once whichever copy lands first, and the relay's copy is acknowledged | L | W5 |
| W7 | The watch under a carrier primary: no relay-down exit while the carrier answers; exit 5 and its marker mean the carrier; the Stop hook probes the carrier | PD (`inbox.py`, `inbox_parts/watchlock.py`); PD-supply (`runtime/claude-code/hooks/watch-on-stop.py`) | a relay stopped for 30 minutes ends no watch on a `carrier-record` account; a stopped carrier ends it with a line naming `fabric-ctl <login> interweave` | M | W6 |
| W8 | `gzcoord-send` under a carrier primary: exit 0 only when the carrier accepted; no seq on stdout; a carrier that is absent is exit 3, "not sent", the pending row marked failed; a `TO` no roster row carries is said | PD (`send.py`); FC for the stdout contract, `i18n/en-US.json` and the skills; each locale's holder for its dictionary | `tests/test_gzcoord_carrier_send.py` covers the four outcomes of `Adapter.post`; `tests/test_gzcoord_i18n.py` passes in every locale | M | W6 |
| W9 | The backfill reads the mode: on in `relay-record` and `carrier-record`, a no-op in `carrier-only` | PD (`gzcoord/backfill.py`) | a test per mode; no relay call in `carrier-only` | S | W1, W5 |
| W10 | Addresses across hosts: `Carrier.recipients` and `Carrier.finish` use the roster row's host | PD (`carrier/engine.py`) | `tests/test_gzcoord_carrier_engine.py`: a `TO` on another host is queued to its row; an arrival from it is `ok` and journaled under its own host; then one message each way with the throwaway login of ADR-069 rule 2 | S to M | - |
| W11 | TO-ROLE at arrival: a test of a role bound after the message arrived, and the behaviour the owner chooses (D6) | PD | the test states the chosen behaviour | S | D6 |
| W12 | Presence and the other public ops off the relay's outage: control's dual run switched on (`runtime/control/config.json`), and `presence.ask_presence` and `queue.ask_holder` handed to the account's own agentd socket | PD (`control/presence.py`, `control/queue.py`, `control_link.Server`); FC for the switch and ADR-029 | with the relay stopped, an addressed send from one staged account to another is checked and sent without `--force` | M to L | D1 |
| W13 | Read position and health without the relay's cursor: `drift.inbox`, `status.inbox_state` and the `interweave` read show the spool's unseen count and the outbox's oldest outstanding and blocked deliveries | PD | `fabric-status` on a `carrier-only` account prints them with the relay stopped; a lagging relay cursor is no longer reported for it | M | W5 |
| W14 | A new login without the relay: the roster row, the install and the start become provisioning steps; `relay_catchup.py` and `Bootstrap.journal_import` leave them | PD (`provisioning/store_step.py`, `new_agent.py`); PD-supply (`bootstrap.py`, `relay_catchup.py`); FC countersigns rows | a scratch login provisioned on a host with the relay stopped sends and receives | M | - |
| W15 | Removal, after gate 2: `RelayTransport` out of the send and inbox paths, `integration_config` no longer asks for a relay, the backfill, the acknowledgement log and the relay half of `parity.py` deleted, a one-carrier health report in its place, the state copy takes the outbox, `transport-calls.json` loses `drift.py` | PD, PD-supply (`relay.py`, `episodic_import.py`), FC (the 15 integration files, the skills, the manuals, `transport-calls.json`) | `grep` finds no `/api/` call under `tools/fabric/gzcoord/`; `tools/fabric/transport_calls.py` is clean with the shorter policy; the suite is green with no relay fixture in the GZCoord tests | L | gate 2 |
| W16 | The relay retired (gate 3): control on InterWeave alone, the state stream replaced, the relay unit, its token, its backup timer and `secret_relay.py` removed | PD, FC | sized when gate 3 is asked for | L | gate 3 |

W3, W5, W10 and W14 depend on nothing and can start beside W1 and W2. W4 and W6 to W9 follow
W3 and W5. The staged switches of §6 are operations, not code: fabric-coordinator's, on the
owner's word.

## 6. The switch, staged, and its way back

**Three modes, per account.** `relay-record` is today. In `carrier-record` the carrier is the
primary (its answer is the exit status, the watch waits on it, replay reads the journal) and the
relay is a mirror both ways. In `carrier-only` nothing in the send or inbox path calls the relay.

**Where the mode lives.** Recommended (D10): the account's state directory, written by a signed
control action as `interweave-start` and `interweave-stop` are today, read back by the
`interweave` op, with an environment override for one command that says so on stderr every
time. The default with no state file is a constant in `open_transport`, which W15 changes last.

**The order is forced by one fact:** a sender in `relay-record` whose carrier is down posts to
the relay alone and exits 0 (`Adapter.post` answers `absent` or `failed`, and `send.py`
`via_mirrors` changes no status). A receiver in `carrier-only` would never see that message. So:

1. Gate 1. Two accounts to `carrier-record`; recommended python-dev-02 and python-dev-03, the
   pair of ADR-064 rule 13. Any sender still reaches them by either carrier.
2. Every account to `carrier-record`, the coordinator's last. From here no send succeeds
   without the carrier, and the relay stays complete through the mirror and the backfill.
3. Gate 2. Two accounts to `carrier-only`, then every account, then the default.

**The way back** is the same action with the earlier mode, one account or all. It takes effect
at the next send; a running watch builds its transport once (`inbox.py` `main`), so W5 has it
notice a changed mode within a minute. What keeps it safe:

- In `carrier-record` the relay has every message (mirror plus backfill), so a step back to
  `relay-record` loses nothing.
- The ledger is not rotated while any account can still read the relay
  (`communication/gzcoord/docs/CARRIER-CONTRACT.md` §6). An account that returns from
  `carrier-only` meets its old relay backlog; `dedup.admit` marks what was shown as `quiet`
  and acknowledges it, so nothing is shown twice.
- From `carrier-only` the step back is to `carrier-record`, not further: the relay's record has
  a hole for that period, and by then no reader uses it (W3).
- If the control plane cannot reach an account, the same signed request goes through
  `fabric-ctl <login> … --via hostexec` to `bin/fabric-op`, or the one-command override is used.
- The relay, its token and its 6-hourly copy stay as they are until gate 3.

Step back at once on: a delivery outstanding past an agreed age in any outbox, a `blocked` code
other than `NotInRoster`, a roster that fails to verify on any account, or an account the
`interweave` read reports off the channel.

## 7. Decisions only the owner can make

- **D1. How far "InterWeave only" goes now.** Recommended: the data plane first (gates 1 and
  2), with W12 inside gate 2 so that a relay outage no longer stops an addressed send; the
  relay's retirement as gate 3, later. Without W12 the relay carries no message and is still a
  single point of failure for sending one.
- **D2. The intermediate rung.** Recommended: keep `carrier-record` as a stage of its own. It
  is the switch ADR-064 rule 11 describes, it is reversible without loss, and it is what makes
  `carrier-only` safe (§6).
- **D3. #573.** Recommended: merge it now, keep it through `carrier-record`, switch it off at
  `carrier-only` (W9). The owner's choice of 2026-11-12, backfill rather than readers of the
  InterWeave copy, holds for the window; under InterWeave only the readers must read the
  journal anyway (W3), so both are built.
- **D4. A grant read from the journal.** `fabric-pr arm` would read AUTHORIZES and WAIVES from
  the arming login's own journal. Recommended: yes, amending ADR-041 rule 7 to say that a
  message addressed to this login, with a sender its carrier verified, is the message and not
  a history result. It is stronger than today's check, where the relay's sender is a claim.
- **D5. What is given up.** The global seq (`--replay <seq>`, `sent seq`), keyword alerts on
  others' traffic, and a whole-channel record anyone with the token can list. Recommended:
  give up all three; keep the relay's last database copy on Proton Drive, encrypted, for a
  period the owner names, then delete it.
- **D6. A TO-ROLE that arrives before its holder binds.** Recommended: accept that it is
  decided at arrival, since the presence check already refuses a role with no running holder
  unless forced; the alternative is each carrier keeping every role-addressed message for a
  later binding.
- **D7. Journal-off.** Recommended: a `GZCOORD_JOURNAL=off` send goes through the carrier with
  its bypass line, since the outbox keeps the text; there is no journal-off receiving, and the
  human relay is the break-glass for an account whose journal cannot be written.
- **D8. The soak and the first accounts.** Recommended: three working days on two accounts and
  seven days on the fleet at each rung, python-dev-02 and python-dev-03 first, the
  coordinator's account last.
- **D9. The second host.** Recommended: W10 before gate 2, and the two-host check before any
  agent moves (ADR-064 rule 1, ADR-069 rule 2). One question in it is architect-cto's, not the
  owner's: fabric-h2 cannot open a connection to develop-qzapp
  (`docs/live-checks/2026-11-11-fabric-h2-registered.md`), so whether a login there can send at
  all depends on what InterWeave does over a connection the other side opened.
- **D10. Where the mode lives.** Recommended: signed action and account state (§6), not a
  committed file: it moves one account in seconds and needs no pull request per stage. The
  cost is that the fleet's modes are read from the accounts, not from git.

**The owner's answers, 2026-11-13**, given in the coordinator's session, each as
recommended:

- D1: the data plane first, through gates 1 and 2. W12 sits inside gate 2. Retiring the relay,
  the control plane included, is a later gate 3.
- D2 and D10: three rungs, `relay-record`, then `carrier-record`, then `carrier-only`. A signed
  action moves each account, and the account's state keeps its mode. python-dev-02 and
  python-dev-03 go first, the coordinator's account last.
- D4: `fabric-pr arm` may read AUTHORIZES and WAIVES from the arming login's own journal, but
  only for a row addressed to that login whose sender the carrier verified. This needs an
  amendment of ADR-041 rule 7.
- D5: give up all three. The owner has not yet named the retention period for the relay's
  last database copy.
- D9, in part: fabric-h2 gets a public InterWeave address and port, which the owner accepted on
  2026-11-14 (#597). Whether a login there can send without dialling out is still open.

## 8. What happens first

1. **W1**: #573 merged with its real-carrier read-back, and the 2026-11-12 drill filed.
2. **W2**: the rollback drill, a judged relay-outage drill, and a parity report with no
   untraced miss. With W1 this is everything gate 1 asks for.
3. **W3**: journal-first replay, which python-dev can start today; W5 beside it.
