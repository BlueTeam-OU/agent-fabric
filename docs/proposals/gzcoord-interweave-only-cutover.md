# GZCoord on InterWeave only: the cutover from the dual run

**Status 2026-11-14.** The owner answered D1, D2, D4, D5 and D10 on 2026-11-13, each as
recommended (§7). D3's first half is done: #573 merged on 2026-11-13. D6, D7 and D8 are not
asked yet, and D9 is partly answered. Two records say what was decided: ADR-041 rule 7 (D4)
and ADR-064 §7 (D1, D2, D5, D10), both amended 2026-11-14. The other records in §4 change when
each gate's word is given. W3, W4, W5, W10, W12 and W14 are done (§5); W4 is on this pull
request.

A plan for the owner's review, drafted for fabric-coordinator. It decides nothing: every step
that changes what carries a message waits for the owner's word and the record named beside it
(§4). The goal is the owner's: the GZCoord data plane runs on InterWeave only, and the central
relay no longer carries, stores or is read for GZCoord messages.

Read against agent-fabric origin/main 08564d8e (2026-11-14), this branch (which adds W4), and
`docs/live-checks/2026-11-09-interweave-parity.md` with its two companion files. The earlier
version of this plan read origin/main 8c3613b1 (2026-11-13) and #573 still open; #573, #581,
#584, #585, #586 and #587 have merged since, and the text below is read against them. Every
claim about the code names its file and function; a path with no function is the whole module.

## 1. Where the fleet stands

- **Every message goes by both carriers, and the relay is the record.**
  `tools/fabric/gzcoord/transport/__init__.py` `open_transport` still builds one shape and no
  other: `RelayTransport` as the primary and `CarrierTransport` as a mirror (no mirror when the
  journal is off). Its docstring says "Moving the primary is a change to this factory".
- **The transport mode exists and changes nothing yet** (#584, W5).
  `tools/fabric/gzcoord/transport/mode.py` holds `MODES` (`relay-record`, `carrier-record`,
  `carrier-only`), the default `relay-record` for an account with no `transport-mode.json`, and
  `Watcher`. `open_transport` reads it and carries it on the mux as `.mode`, and says so: until
  W6 to W8 give the modes their own transports, all three build the same mux. The signed action
  is `interweave-mode` (`tools/fabric/control/transport_mode.py` `MODE_OP`, served by
  `control/ctl.py` and `control/agentd.py`); the `interweave` read carries the mode
  (`control/ops/__init__.py`, `transport_mode.section`) and `ctl.py` `_table_carrier` prints it.
  `fabric-ctl` refuses `carrier-only` while a placed account is not past `relay-record`
  (`_carrier_only_blockers`). A running watch learns of a change through `mode.Watcher`
  (`inbox.py` `main`, every `MODE_POLL_S`, 5 s). The word `both` that `fabric-ctl all interweave`
  prints is still the `units` column: the daemon unit and the client unit are both active. What
  changes what is sent remains the carrier's presence (`tools/fabric/gzcoord/carrier/adapter.py`
  `Adapter.present`, "The switch is the carrier itself"). §6 says what each mode must do.
- **The relay's record is kept whole, and replay no longer needs it** (#573, #581).
  `tools/fabric/gzcoord/backfill.py` `tick`, run by `agentd.backfill_tick` on a timer, posts to
  the relay a message the carrier alone delivered, once the relay answers. `gzcoord-inbox
  --replay <message-id>` and `--history` read the account's own journal first
  (`inbox_parts/records.py` `journal_record`, `replay_journal_row`, `history_journal`,
  `history_journal_only`; `inbox.py` `main`), with the relay down or none configured. A relay
  seq still goes to the relay. `--json` carries `carrier` and `sender_verified`.
- **The control plane rides both carriers.** `runtime/control/config.json` has
  `"control_carrier": "dual"` for the fleet since 2026-11-13. The second carrier of agent-fabric
  ADR-029 rule 18 (`tools/fabric/gzcoord/carrier/control_link.py`, `tools/fabric/control/agentd.py`
  `main`, the `CARRIER_DUAL` branch) is on beside the relay. `agentd.control_config` accepts
  `relay` or `dual` and refuses anything else, so control still has no setting for InterWeave
  alone, and the relay-only ops stay on the relay (`control_link.RELAY_ONLY_OPS`).
- **Presence no longer stops at the relay's outage, in code** (#586, W12). `gzcoord-send` asks it
  before every addressed send (`tools/fabric/gzcoord/send.py` `asked_presence`), through
  `tools/fabric/control/presence.py` `ask_presence`. The post to the relay's control channel
  still goes first; under `dual` the request also goes through the account's own agentd to each
  other account (`_open_leg`, `control_link.Leg.open`), and a failed relay post is made up by
  that leg. `queue.ask_holder` does the same. `send.py` `main` still stops without the relay
  token (`if not tok: return 3`). That a send with the relay stopped passes without `--force`
  is W12's read-back, not yet run.
- **`fabric-history` does not read the relay.** `tools/fabric/history.py` reads the account's
  journal through `episodic.open_readonly`. The docstring of `backfill.py` lists it among the
  relay's readers; it is not one. The journal's one relay reader is the import
  (`tools/fabric/episodic_import.py`).
- **What the last parity run lacked** (`docs/live-checks/2026-11-09-interweave-parity.md`): the
  rollback drill was never run; both relay-outage drills read UNSETTLED because the
  acknowledgement log did not exist yet; 13 InterWeave misses after the rollout days and 516
  duplicate InterWeave copies were not traced. A relay-outage drill of 2026-11-12 is cited by
  #573; no record of it is in `docs/live-checks/` on this branch (its files from 2026-11-10 on
  are other checks).

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
| `send.py` `check_addressees`, `asked_presence` | presence, over the relay's control channel, with the relay token in the request | the same op over control's second carrier | in code, under `dual` (#586, W12): `presence.ask_presence` also opens a `control_link` leg through the account's own agentd; the relay post still goes first and the send still needs the token. Not read back with the relay stopped |
| `tools/fabric/gzcoord/transport/relay.py` `RelayTransport.send`, `refresh`, `never_delivered`, `explain` | `POST /api/send`; a refused token re-read; what a failure proves | the carrier transport's own answers to the same four questions | no: `transport/carrier.py` `CarrierTransport` is a mirror and has none of `Primary`'s verbs (`transport/base.py` says a mirror "need not implement them; moving the record to another transport is the day it must") |
| `tools/fabric/gzcoord/intake.py` `queue_for_addressee` | `fabric-ctl <login> jobs-add`, a control action over the relay | the same action over control's carrier | partly: it runs `fabric-ctl`, which uses the second carrier under `dual` (`ctl.py` `_second_carrier`); not read back with the relay stopped |
| `tools/fabric/gzcoord/backfill.py` `tick` and `agentd.backfill_tick` (#573, merged) | reads the relay's newest page and posts carrier-only rows to it | nothing: under InterWeave only it must not run | n/a; it reads no mode yet (`backfill.py` names none), which is W9 |

### 2.2 Receiving and the watch

| where | uses the relay for | replacement | exists? |
|---|---|---|---|
| `tools/fabric/gzcoord/inbox.py` `main` | `transport.start_hosted` at every run: the hosting workspace starts the relay (`inbox_parts/relay.py` `ensure_relay`) | nothing | n/a |
| `inbox.py` `main`, the watch loop | the long poll is the clock of the watch (`tp.fetch_page` → `RelayTransport.receive`, `GET /api/wait`); an unreachable relay ends a quiet `--until-delivery` watch after 15 minutes with exit 5 (`UNTIL_DELIVERY_DOWN_S`, `watchlock.mark_relay_down`), whether or not the carrier is up, and what the carrier brings after that waits in the spool for the next watch | a wait on the carrier | no (W6): `CarrierTransport.receive` ignores `seconds` and returns at once (`Adapter.unseen` is a poll); `wait_loop` driven by it alone would spin |
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
| `inbox.py` `main` `--replay`; `inbox_parts/records.py` `replay` | a relay seq, or a MESSAGE-ID the journal does not hold: `primary.newest(500)`, with the relay's `sender` | the journal row by MESSAGE-ID: text, `sender`, `sender_verified`, `carrier` | yes for a MESSAGE-ID (#581, W3): `inbox.py` `main` asks `records.journal_record` first, in every configuration, and `replay_journal_row` prints it (`--json` adds `carrier`, `sender_verified`, `state`); only a relay seq still needs the relay |
| `inbox.py` `main` `--history`; `records.history` | the relay's newest 500, one line per message addressed here, by seq | the journal's list | yes (#581, W3): `history_journal` where no relay answers or none is configured, `history_journal_only` after the relay's list for what a carrier alone brought; `fabric-history` lists the journal too |
| `tools/fabric/github/arm.py` `verify_grant` (`--authorization`, `--waiver`) | runs `gzcoord-inbox --replay <ref> --json`. A row a carrier other than the relay brought counts only with `sender_verified` true and that sender equal to `FROM`; a relay-brought row is judged as before, the relay's `sender` equal to `FROM` (a claim) | the journal row, whose sender the carrier verified by PeerId (agent-fabric ADR-064 rule 9) | yes, on this pull request (W4, #604); ADR-041 rule 7 was amended for it on 2026-11-14 (§4). The relay-brought branch goes at gate 2 |
| `tools/fabric/jobsparts/records.py` `fetch_message` (`fabric-jobs add --request`) | the same `--replay --json` | the same journal read | yes: it runs `gzcoord-inbox --replay`, so it takes the journal-first answer (#581) |
| `tools/fabric/episodic_import.py` `Importer`, `main`; `tools/fabric/relay.py` `pages`, `call`; `bootstrap.py` `Bootstrap.journal_import` | backfills a journal from the relay's whole channel | nothing: a carrier keeps no past, and an agent's journal starts at its birth | n/a; `journal_import` still runs at bootstrap, best effort, one "!" line without a relay (`carrier_step.py` says so) |
| `tools/fabric/relay_catchup.py` `catch_up` | put a new account's relay cursor at the newest message | nothing: a new login receives what is sent after its roster row is admitted | done (#587, W14): `provisioning/store_step.py` `secrets_step` no longer calls it, and `provisioning/carrier_step.py` installs and starts the units (steps 7c to 7e); the module and its tests are still in the tree, for W15 |
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

Not GZCoord messages, so outside the goal as worded; listed because the relay cannot be retired
while these stand. Under `"control_carrier": "dual"` (`runtime/control/config.json`, the fleet
since 2026-11-13) control already rides InterWeave beside the relay; what is missing is a value
for InterWeave alone, and the state stream.

| where | uses the relay for | replacement | exists? |
|---|---|---|---|
| `tools/fabric/control/agentd.py` `main` (`call`, `post`, `prime`, the read loop) | reads every request on `fabric:control` by `since_id`, posts every reply | `control_link` on the `fabric-control` endpoint | built, on under `dual`; no InterWeave-alone value (`agentd.control_config` accepts `relay` or `dual`) |
| `agentd.py` `state_poster`; `control/ctl.py` `states`; `control/queue.py` `read_waits`; `control/pool.py` `state_reader`, `role_from_stream` | the state channel: each account's newest state record, read back from the relay's stored history | a request each agentd answers, or a table the reader keeps | no: InterWeave stores no history |
| `control/ctl.py` `main` | posts the request, pages the replies | `_second_carrier`, through the operator's agentd socket | built, used under `dual` |
| `control/presence.py` `ask_presence`; `control/queue.py` `ask_holder`, `bound_call`, `relay` | public ops asked by any account (`presence`, `pool-list`, `pool-claim`, `job-state`) | the asker's own agentd socket | yes under `dual` (#586, W12): `presence.ask_presence` and `queue.ask_holder` also send through the account's agentd and take a reply from either carrier; `bound_call` and `relay` still post to the relay; the relay-stopped read-back is gate 2's |
| `control_link.RELAY_ONLY_OPS` (`interweave`, `-install`, `-start`, `-stop`) | the ops that take the InterWeave channel down ride the relay by rule (ADR-064 rule 14) | `bin/fabric-op` through hostexec (`control/breakglass.py`, ADR-029 rule 19) | built; verified on the local backend only |

## 3. What the relay gives, and what InterWeave gives or the fleet gives up

| capability | on the relay | on InterWeave only | verdict |
|---|---|---|---|
| store and forward to an addressee with no session | the relay holds the record until that consumer acknowledges | the receiving carrier is a unit that runs without a session: it journals, spools and receipts (`Carrier.finish`), and the inbox shows the spool at the next watch | given |
| store and forward to an addressee whose account is down | the same | the sender's outbox retries to the receipt, 1 s doubling to 5 min, never given up (`carrier/record.py` `backoff`, `Outbox.due`) | given, with a difference: the message waits on the sender's disk, not at a third place; a sender host lost before the receipt loses the delivery but not the text (the journal's outbound row holds it) |
| a send while the sender's own carrier is down | the relay takes it | none: `Adapter.post` answers `absent` or `failed` | gap: the send must fail loudly (W8) |
| a global order and a seq | one sequence per channel; `--replay <seq>`, `--history <seq>`, the delivery title and the job's `source.seq` cite it | none: one direct send per recipient, no order across senders | given up; the MESSAGE-ID's UUIDv7 time and `IN-REPLY-TO` order a thread (`history.py` `thread_ids`) |
| history replay | anyone with the token lists the whole channel | each agent's journal holds what it sent and what was addressed to it; nobody holds the whole | own history given (W3 done, #581); the whole-channel record given up |
| broadcast | one post, every reader | one direct send per roster member and a receipt back (`Carrier.recipients`, ADR-064 rule 6) | given; the roster is the membership, so a login with no valid row receives nothing |
| TO-ROLE fan-out | read by whoever holds the role when its watch reads | sent to every member; each carrier keeps it only if its account holds the role at arrival (`carrier/main.py` `make_me`, read per message) | given, with a difference: a login that binds the role after the arrival never sees it; untested (W11) |
| alerts on others' traffic (`--wait --keyword`) | every reader passes every message | a message not addressed here never reaches the inbox | given up |
| an authenticated sender | none: `sender` is a claim (agent-fabric ADR-033 §6) | the PeerId, mapped by the roster; a mismatch is shown flagged (ADR-064 rule 9) | gained |
| presence | a control op on the relay | unchanged by the data plane; control's dual run is on, and `presence.ask_presence` and `queue.ask_holder` also ask through the account's own agentd (#586, W12) | in code the relay's outage no longer stops an addressed send; not yet read back with the relay stopped (gate 2) |
| the human relay (ADR-033 rule 7) | a person carries text between terminals when the relay is down | the same procedure, used when a carrier cannot deliver; it never used the relay | given; rule 7's trigger is reworded |
| journal-off break-glass (ADR-041 rule 10) | "the route is the relay alone" (ADR-064 rule 8); `carrier/main.py` `cmd_run` refuses to start | none | gap: to be decided (D7) |
| reach to a second host | none: the relay binds loopback | the profile's listener. The carrier no longer assumes one host (#585, W10): `Carrier.recipients` carries a `TO` to the roster row whose host matches, and `Carrier.finish` judges and journals a sender as `<row's host>/<login>`, both through `Carrier.row_host` | done in code; the two-host read-back with a throwaway login is not run, and for an account on fabric-h2 InterWeave is the only route from its first day |
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

1. #573 merged (done, 2026-11-13), and its missing read-back done: a message through the real
   carrier to a second account, shown once, then found on the relay after its return.
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
sets the journal row; §2 "Dual run"). ADR-041 rule 7 was amended on 2026-11-14, on this pull
request, with W4: `fabric-pr arm` may read a grant from the arming login's journal (D4), and
ADR-064 §7 then names the path. ADR-029 §2 gained the mode's action op, `interweave-mode`,
on the same pull request (A 2026-11-14), since #584 had built it.

**Gate 2: the relay carries no GZCoord.** Evidence: every account in `carrier-record` for the
agreed soak (D8) with no stranded delivery; a carrier-outage drill (one account's units stopped
for 30 minutes: senders' outboxes hold, everything arrives once on its return, shown once); two
accounts in `carrier-only` through a relay stop of a working hour with every GZCoord function
exercised (send, watch, replay, `fabric-pr arm --authorization`, `fabric-jobs add --request`,
a REQUEST's job intake); and W12's read-back if the owner takes D1's recommendation. Records:
ADR-033 amended again (the relay carries control only; rule 7's trigger; rule 5's "the hosting
session's start brings it up"), ADR-064 (rules 8, 11 and 14, whose "the relay carries for it
alone" goes; the dual run ends), ADR-041 rule 7 (its relay-row half goes) and rule 10 (D7), ADR-030 rule 3's wording, and ADR-069 §1
(the "messages between sessions" row is rewritten and the two new rows of §3 added: ADR-034
rule 1 wants that in the same pull request).

**Gate 3: the relay is retired.** A separate word, on the control parity report ADR-029 rule 18
already asks for, plus the state stream's replacement and the four relay-only ops read back over
`fabric-op`'s SSH backend. Records: an amendment of ADR-029 (rule 18, §2), and a new record that
retires the relay and supersedes ADR-033's deployment rules (5 and 6) and ADR-034 §7's first
step; ADR-069 loses the relay rows. This plan sizes it only as far as §5's W16.

**#573's place.** It is needed for the window and moot after it. While the relay is the record
(today) and while it is the mirror (`carrier-record`), the backfill keeps the relay complete, so
a relay-only reader misses nothing and a step back loses nothing. W3 has landed, so no reader
that holds the MESSAGE-ID needs the relay's copy, and the backfill's only remaining use is the
rollback target. In `carrier-only` it must be off: it is a writer to the relay, and it reads no
mode yet (W9). It has merged.

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
| W1 | Land #573; do its real-carrier read-back; file the 2026-11-12 drill | PD (python-dev-03); FC for the record | the PR's suite; the read-back's three facts (shown once, on the relay after return, a `gzcoord-backfill.jsonl` line) in a live check | #573 merged (2026-11-13); the read-back and the drill's record still to file | - |
| W2 | The two drills and the fresh parity report (gate 1, items 2 to 4); trace the misses and duplicates | FC runs and files; PD reads `carrier/engine.py` `send_due` and `Adapter.post` for the causes | the report's "what it lacks" section is empty; each miss has a cause a reviewer can find in the computed file | S, mostly operations | W1 |
| W3 | **Done, #581.** Journal-first `--replay` and `--history`: a MESSAGE-ID is answered from the journal in every mode; `--json` gains `carrier` and `sender_verified`; a relay seq is still answered from the relay while one is configured | PD (`inbox.py` `main`, `inbox_parts/records.py`; reads through `episodic.open_readonly`, so no supply-tier file changes) | a test with the relay refusing every connection: a row journaled by the carrier alone replays with exit 0, one not addressed exits 2; `jobsparts/records.py` `fetch_message` adds the job | M | - |
| W4 | **Done, on this PR, #604.** `verify_grant`: a journal row a carrier other than the relay brought counts only with `sender_verified` true and that sender equal to `FROM`; a relay-brought row is judged as the relay's record always was, until the relay stops carrying GZCoord at gate 2 | DX (`tools/fabric/github/arm.py`); FC for ADR-041 rule 7 (amended 2026-11-14) | `tests/test_arm_cli.py`: a grant the carrier alone delivered arms with the relay down; an unverified sender on such a row is refused | S | W3, D4 |
| W5 | **Done, #584** (the mode is read, set and shown; the transports that honour it are W6 to W8). The transport mode: `relay-record` (today), `carrier-record`, `carrier-only`; read by `open_transport`; set by a signed action and shown by the `interweave` read and `_table_carrier` (§6) | PD (`gzcoord/transport/`, `control/`); FC supplies ADR-029's op row (done on #604) | default unchanged with no state file; `fabric-ctl all interweave` prints each account's mode; a running watch takes a changed mode within a minute; `carrier-only` is refused while any placed account reports `relay-record` | M | D2, D10 |
| W6 | The carrier as a `Primary`: `CarrierTransport.receive` waits (a `wait` op on the adapter socket), `newest` reads the journal, `explain` and `never_delivered` answer for the carrier; `TransportMux` takes the relay as a mirror both ways | PD (`gzcoord/transport/`, `carrier/server.py`, `carrier/engine.py` `handle_request`); FC for `CARRIER-CONTRACT.md` §6 | `tests/test_gzcoord_transport.py`: in `carrier-record` a relay that refuses every call changes neither the exit status nor what is shown; an idle watch arm makes a bounded number of adapter calls; a message is shown once whichever copy lands first, and the relay's copy is acknowledged | L | W5 |
| W7 | The watch under a carrier primary: no relay-down exit while the carrier answers; exit 5 and its marker mean the carrier; the Stop hook probes the carrier | PD (`inbox.py`, `inbox_parts/watchlock.py`); PD-supply (`runtime/claude-code/hooks/watch-on-stop.py`) | a relay stopped for 30 minutes ends no watch on a `carrier-record` account; a stopped carrier ends it with a line naming `fabric-ctl <login> interweave` | M | W6 |
| W8 | `gzcoord-send` under a carrier primary: exit 0 only when the carrier accepted; no seq on stdout; a carrier that is absent is exit 3, "not sent", the pending row marked failed; a `TO` no roster row carries is said | PD (`send.py`); FC for the stdout contract, `i18n/en-US.json` and the skills; each locale's holder for its dictionary | `tests/test_gzcoord_carrier_send.py` covers the four outcomes of `Adapter.post`; `tests/test_gzcoord_i18n.py` passes in every locale | M | W6 |
| W9 | The backfill reads the mode: on in `relay-record` and `carrier-record`, a no-op in `carrier-only` | PD (`gzcoord/backfill.py`) | a test per mode; no relay call in `carrier-only` | S | W1, W5 |
| W10 | **Done, #585** (the two-host read-back with a throwaway login is not run). Addresses across hosts: `Carrier.recipients` and `Carrier.finish` use the roster row's host | PD (`carrier/engine.py`) | `tests/test_gzcoord_carrier_engine.py`: a `TO` on another host is queued to its row; an arrival from it is `ok` and journaled under its own host; then one message each way with the throwaway login of ADR-069 rule 2 | S to M | - |
| W11 | TO-ROLE at arrival: a test of a role bound after the message arrived, and the behaviour the owner chooses (D6) | PD | the test states the chosen behaviour | S | D6 |
| W12 | **Done, #586** (the relay-stopped read-back is gate 2's). Presence and the other public ops off the relay's outage: control's dual run switched on (`runtime/control/config.json`), and `presence.ask_presence` and `queue.ask_holder` handed to the account's own agentd socket | PD (`control/presence.py`, `control/queue.py`, `control_link.Server`); FC for the switch and ADR-029 | with the relay stopped, an addressed send from one staged account to another is checked and sent without `--force` | M to L | D1 |
| W13 | Read position and health without the relay's cursor: `drift.inbox`, `status.inbox_state` and the `interweave` read show the spool's unseen count and the outbox's oldest outstanding and blocked deliveries | PD | `fabric-status` on a `carrier-only` account prints them with the relay stopped; a lagging relay cursor is no longer reported for it | M | W5 |
| W14 | **Done, #587** (`store_step.py` no longer calls `relay_catchup.py`; `journal_import` stays, best effort). A new login without the relay: the roster row, the install and the start become provisioning steps; `relay_catchup.py` and `Bootstrap.journal_import` leave them | PD (`provisioning/store_step.py`, `new_agent.py`); PD-supply (`bootstrap.py`, `relay_catchup.py`); FC countersigns rows | a scratch login provisioned on a host with the relay stopped sends and receives | M | - |
| W15 | Removal, after gate 2: `RelayTransport` out of the send and inbox paths, `integration_config` no longer asks for a relay, the backfill, the acknowledgement log and the relay half of `parity.py` deleted, a one-carrier health report in its place, the state copy takes the outbox, `transport-calls.json` loses `drift.py`, and `verify_grant`'s relay-row branch (`RELAY_CARRIER`) goes | PD, PD-supply (`relay.py`, `episodic_import.py`), DX (`tools/fabric/github/arm.py`), FC (the 15 integration files, the skills, the manuals, `transport-calls.json`) | `grep` finds no `/api/` call under `tools/fabric/gzcoord/`; `tests/test_arm_cli.py` refuses a grant row whose carrier is the relay; `tools/fabric/transport_calls.py` is clean with the shorter policy; the suite is green with no relay fixture in the GZCoord tests | L | gate 2 |
| W16 | The relay retired (gate 3): control on InterWeave alone, the state stream replaced, the relay unit, its token, its backup timer and `secret_relay.py` removed | PD, FC | sized when gate 3 is asked for | L | gate 3 |

W3, W4, W5, W10, W12 and W14 are done. What is left, and in this order: W2 (the two drills and
the parity report), which needs W1's read-back first; W6 to W9, which follow W5 (W6, then W7 and
W8, W9 beside them); W11, which waits on D6; W13, which follows W5; then the gates. W15 and W16
follow gate 2 and gate 3. The staged switches of §6 are operations, not code:
fabric-coordinator's, on the owner's word.

## 6. The switch, staged, and its way back

**Three modes, per account.** `relay-record` is today. In `carrier-record` the carrier is the
primary (its answer is the exit status, the watch waits on it, replay reads the journal) and the
relay is a mirror both ways. In `carrier-only` nothing in the send or inbox path calls the relay.

**Where the mode lives.** Recommended (D10): the account's state directory, written by a signed
control action as `interweave-start` and `interweave-stop` are today, read back by the
`interweave` op, with an environment override for one command that says so on stderr every
time. The default with no state file is a constant (`mode.DEFAULT`, read through
`open_transport`), which W15 changes last. W5 built the state file, the signed action
`interweave-mode` and the read; it built no environment override (a grep of `tools/fabric` finds
none), so the one-command override is still to build.

**The order is forced by one fact:** a sender in `relay-record` whose carrier is down posts to
the relay alone and exits 0 (`Adapter.post` answers `absent` or `failed`, and `send.py`
`via_mirrors` changes no status). A receiver in `carrier-only` would never see that message. So:

1. Gate 1. Two accounts to `carrier-record`; recommended python-dev-02 and python-dev-03, the
   pair of ADR-064 rule 13. Any sender still reaches them by either carrier.
2. Every account to `carrier-record`, the coordinator's last. From here no send succeeds
   without the carrier, and the relay stays complete through the mirror and the backfill.
3. Gate 2. Two accounts to `carrier-only`, then every account, then the default.

**The way back** is the same action with the earlier mode, one account or all. It takes effect
at the next send; a running watch builds its transport once (`inbox.py` `main`), so W5's
`mode.Watcher` ends the arm within `MODE_POLL_S` (5 s) of a changed mode. What keeps it safe:

- In `carrier-record` the relay has every message (mirror plus backfill), so a step back to
  `relay-record` loses nothing.
- The ledger is not rotated while any account can still read the relay
  (`communication/gzcoord/docs/CARRIER-CONTRACT.md` §6). An account that returns from
  `carrier-only` meets its old relay backlog; `dedup.admit` marks what was shown as `quiet`
  and acknowledges it, so nothing is shown twice.
- From `carrier-only` the step back is to `carrier-record`, not further: the relay's record has
  a hole for that period, and by then no reader uses it (W3).
- If the control plane cannot reach an account, the same signed request goes through
  `fabric-ctl <login> … --via hostexec` to `bin/fabric-op`, for a step back to `carrier-record`
  or `relay-record` only: `fabric-ctl` refuses `carrier-only` over `--via`, because the fleet's
  modes it checks first are read over the relay. The one-command override is not built yet.
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
  only for a row addressed to that login whose sender the carrier verified. That is the owner's
  answer as given. Two things were added on 2026-11-14 by fabric-coordinator, not by the owner,
  when W4 was folded: the verified sender must be the message's `FROM`, as arm already required
  of the relay's sender; and a row the relay brought is judged as before, its sender a claim, so
  that accounts still in `relay-record` can arm. That second half ends at gate 2 (§4, W15).
  ADR-041 rule 7 is amended on this pull request, with W4.
- D5: give up all three. The owner has not yet named the retention period for the relay's
  last database copy.
- D9, in part: fabric-h2 gets a public InterWeave address and port, which the owner accepted on
  2026-11-14 (#597). Whether a login there can send without dialling out is still open.

## 8. What happens first

W3, W4, W5, W10, W12 and W14 are done, and #573 is merged. What is left, in this order:

1. **W1's remainder**: the real-carrier read-back of #573, and the 2026-11-12 drill filed.
2. **W2**: the rollback drill, a judged relay-outage drill, and a parity report with no
   untraced miss. With W1 this is everything gate 1 asks for.
3. **W6 to W9**, from W5's mode: the carrier as a primary (W6), then the watch (W7) and the send
   (W8), and the backfill reading the mode (W9). **W11** waits on D6; **W13** follows W5.
4. **The gates**, each on the owner's word and the records in §4; W15 after gate 2, W16 after
   gate 3.
