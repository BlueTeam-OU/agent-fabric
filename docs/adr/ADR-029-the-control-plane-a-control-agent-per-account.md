# ADR-029 — The control plane: a control agent per account answers signed actions over the relay

**Date:** 2026-09-17
**Status:** Accepted
**Ratified:** owner, 2026-09-27, by arming agent-fabric #53 (ratification by merge, the owner's rule of 2026-09-27)
**Decision Makers:** the owner; drafted by fabric-coordinator
**Scope:** runtime/control/, every module and the unit file, and its Python package tools/fabric/control/ from its creation (ADR-040 Wave 8); bin/fabric-ctl; the control channel's refusal in GZCoord's inbox and send tools; the unit's installation in tools/fabric/bootstrap.py; tools/fabric/local_settings.py (rule 15) and runtime/claude-code/hooks/session-state.py (rule 16); account persistence (runtime/provisioning/persist-accounts.sh, runtime/provisioning/platform/qubes/agent-fabric-accounts.rc); the fallbacks bin/fabric-usage and bin/fabric-host; bin/fabric-op, the break-glass action path (rule 19)
**Pillar:** P5
**Evidence:** docs/live-checks/2026-09-17-control-plane.md

## 1. Context and Problem

On 2026-09-17 the first fleet usage table was made by hand, and the
second (`bin/fabric-usage`) could be made only from the coordinator's
login, through sudo, one host at a time. Anything else the coordinator
needed to know about an account — which Claude account it is signed into,
which keys it holds, how far its fabric is behind, whether a session is
running — was read the same way, by entering another account's home.
The alternative inside the fleet was to ask the agent in a session, and
an account with no session running, or a session busy with its own work,
could not answer at all.

The owner asked for a real-time control plane: a message received by a
process on the account, answered with the data asked for. What
"received" means is the whole design, because the one thing every
account already has is the relay, and a session's inbox is the one place
such records must never land.

## 2. Decision

**Every account runs a control agent** — `tools/fabric/control/agentd.py`,
a daemon under a systemd user unit, alive whether or not a Claude session
is. It reads requests on a control channel of the relay the fleet's
GZCoord traffic already rides, answers what it can say about its own
account, and posts the reply. No session, no model, no prompt and no
sudo are in the loop.

- **A channel no session drains.** The records ride the relay on a
  channel of their own, `fabric:control` (`runtime/control/config.json`),
  one JSON object per relay message. They are not GZCOORD/1 messages, and
  the GZCoord tools refuse any channel whose name ends in `:control`.
- **A second carrier: InterWeave** (rule 18). On an account switched to
  it, agentd also holds its InterWeave profile's `fabric-control`
  endpoint through the command-line client `interweave-human`, and the
  operator's agentd carries `fabric-ctl`'s sends. A record is the same
  JSON object, one message each. On the relay's host the relay stays the
  transport of record until the owner's word on a control parity report.
- **No delivery, only reading.** Every daemon reads every record and
  answers only what names it (`to`: its address, a list holding it, or
  `*`); the coordinator reads replies by `in_reply_to`. A daemon keeps no
  cursor and acks nothing: it primes from the newest record and
  long-polls after it, so a restart never replays history, and a request
  posted while a daemon was down is not answered.
- **Reads and actions.** A closed set of read ops reports the account;
  actions change it (`tools/fabric/control/sign.py` `ACTION_OPS`, the
  eight rows marked *action* below) and are answered only when signed by the operator's
  key. One unsigned write exists, a pool claim (rule 4).

| op | what the account answers |
|---|---|
| `ping` | that it is there |
| `identity` | agent, host, role, project, working copy; the Claude account signed in and whether a credentials file exists; a setup-token by fingerprint |
| `usage` | the five-hour and seven-day windows, with the account's own token in one request header and nowhere else |
| `keys` | each synced key's name, presence and a twelve-hex-digit sha256 prefix, and whether the key git signs with has a usable secret in the keyring — never a value |
| `fabric` | head, branch, distance behind `origin/main`, dirty |
| `session` | Claude processes as the login; whether one is planning |
| `presence` | whether a session is running, a public op (ADR-030) |
| `host` | load, memory and swap, block devices, held leases, the largest processes — the same numbers from every daemon on a host, collapsed by host (ADR-010) |
| `disk` | what the account's home holds, by its largest directories, one bounded scan shared by the requests that arrive while it runs |
| `script` | the letters of the notes, the visible text, stored thinking and the locale worker's transcripts, by script and language, counts only (ADR-027) |
| `recall` | which corpus paths the account's sessions read over 24 h — index, slice, charter — paths and counts only |
| `tokens` | the login's own spend per model over a window, direct-path and broker models summed apart; the only place a login's share of a Claude account can be read |
| `memory` | the drain: the account's own harvest, in bundles (rule 9) |
| `accounts` | the Claude accounts this login observes and their usage windows (ADR-031) |
| `jobs` | the account's open jobs (ADR-037) |
| `local` | per working copy, the per-clone harness settings: env key names and which are synced secrets, permission rules by count — never a value (ADR-038) |
| `tools` | the account's tools report: every tool the bound role's projects declare, found or missing, with the report's age; written by the daemon from `fabric-tools --all --json` at start, hourly and after a rebind |
| `pool-list` | a role's open pool of jobs, a public op (ADR-037) |
| `pool-claim` | a claim of one pool job for the asker's own list, a public op, checked against the role the asker's own daemon reports (ADR-037) |
| `upgrade` | *action*: the account to the pinned Claude Code or to the merged fabric (ADR-009) |
| `secrets-sync` | *action*: the account's store projected where its tools read it (ADR-038) |
| `jobs-add` | *action*: the owner's job on the account's list (rule 13, ADR-037) |
| `local-prune` | *action*: per-clone settings entries that duplicate a synced secret, removed (rule 15) |
| `secrets-selftest` | *action*: a canary through the account's store and back (rule 17) |
| `tools-install` | *action*: the one tool named, installed from what its project pins (`projects/registry.json` `install`): a release (version, https url, sha256, the hash checked before a byte is unpacked or run), an `installer` pin run once with fixed arguments after the same check (rustup-init), a `cargo` pin built by `cargo +<toolchain> install --locked --version =<v>`, which cargo checks against the crates.io index and Cargo.lock and nothing here hashes, or a `rustup-target` pin added by `rustup target add <target> --toolchain <toolchain>` through the account's rustup, both fields matched by pattern and proved by the install's own list (A 2026-10-19); skipped on an account with no working copy of a project that declares it (`tools/fabric/tools_install.py`) |
| `gateway` | read: the installed agent-fabric-gateway's version and runtime contract as the binary reports them, and the release digest its install marker recorded (not compared with `runtime/gateway.json`: after the pin moves, `gateway-install` is what brings an account to it); beside a live usage relay also `setup_tokens`, one per relayed entry in order, the setup-token fingerprint its generation is joined to in the account's `gateway-generations.json` or null, and `sessions`, `{status: ok|unknown, gateway: N, other: M}`, how many running harness sessions are on the gateway transport and how many are not (ADR-052) |
| `switch` | read, operator only: the switch controller's policy mode and the last lines of its move log (`<state>/account-switch.jsonl`, ADR-052 rule 11); only the coordinator's account keeps one, any other answers `{"status": "none"}` |
| `gateway-install` | *action*: the pinned gateway release (`runtime/gateway.json`), its SHA-256 checked before anything is extracted, the one pinned member only, run with `--version --json` and required to match the pin before it is renamed into `~/.local/bin` (`tools/fabric/control/gateway.py`) |
| `interweave` | read: the account's InterWeave programs as they report themselves (version, digests), whether they are the release `runtime/interweave/release.json` pins, whether the two user-unit templates are installed, `client` (the client unit's program: `ok`, `absent`, `differs` from this clone's, or `unreadable`), and the channel: `ok`, `off`, `not-running` or `unknown` (a check that could not be made, which ADR-064 rule 14 counts as off the channel), from that rule's check of the running units (`tools/fabric/control/carrier_install.py`) |
| `interweave-install` | *action*, no arguments: the release the pin names as `current`, its size and SHA-256 checked before anything is extracted, an archive with any member outside its root refused, the archive's own `install.sh` run, the pinned programs' `--version` and digests checked; the units that were running restarted and checked through the control plane, and the previous programs put back on a failed check (ADR-064 rules 4, 14); last, on an installed or a `current` account alike, the client unit's program from this clone put in `~/.local/libexec/interweave/client` (ADR-064 rule 5), the reply's `client` saying installed, already or failed. One download at a time per host, under the host lease `interweave-download` (`tools/fabric/control/carrier_install.py`) |
| `interweave-start` | *action*, no arguments: the dual run's switch for one account (ADR-064 rule 11). Refused, nothing touched, unless the account lingers, its programs are the pin's, both unit templates are installed, the client unit's program is in place (`interweave-install` puts it there) and, unless a running pair's file is already current, the host reserves the roster's port range (`net.ipv4.ip_local_reserved_ports`, ADR-064 rule 1); an unreadable setting refuses it and an unreadable roster fails it; the profile's `config.yaml` rendered from the roster under the host lease `interweave-render`, one account's render at a time (refused for an account with no valid row), the daemon unit then the client unit enabled and started (with both already running the render is compared with the file: identical, nothing is changed, the reservation and the port range are not read, and the reply says `already_running`; different, as after a roster change, the reservation and the port range are checked first, then the file is replaced and both units are restarted and checked, the reply saying `rerendered`; a refused or broken render, a held lease, an unreadable port range, a missing reservation or a failed write leaves both units running on the previous `config.yaml` and the reply names them; a lone running unit is restarted after the render, so it reads the file written), and ADR-064 rule 14's check polled; a unit that does not come up or a failed check stops both and says so, and the relay carries alone (`tools/fabric/control/carrier_install.py`) |
| `interweave-stop` | *action*, no arguments: the client unit then the daemon unit disabled and stopped, answered `stopped` only once neither runs; `config.yaml` and the programs stay. The rollback drill of ADR-064 rule 11 (`tools/fabric/control/carrier_install.py`) |
| `interweave-evidence` | *signed read*, arguments `section` (`arrivals` or `deliveries`), `since` and `until` (`YYYY-MM-DDTHH:MM:SSZ`, `since` before `until`), nothing else; the files ADR-064 rule 11's parity report is computed from: the account's `gzcoord-arrivals.jsonl` lines with `t` in the window, or its InterWeave delivery records with `queued` in it, oldest first, and for arrivals the kind (direct, role, broadcast) of each message from the account's journal, opened read-only. Rows are built key by key from a closed list, each value a short string, and a body never leaves the account. A page is at most 64 KiB of rows, cut on a whole second; `next` is the `since` of the following page, and `fabric-ctl` pages every account to completion. Refused: an argument other than the three, a section other than the two, a time not in that form, a window that is empty, a second holding more than a page (`tools/fabric/control/carrier_evidence.py`, `evidence_collect.py`) |
| `pool-add` | *action*, on the pool's holder only: a job on a role's pool (ADR-037 rule 9) |
| `status` | identity, usage, keys, fabric and session together |

- **The switch controller** (ADR-052) runs in the coordinator's control
  agent, on the host operator's account only: a timer every `interval_s`
  of `routing/policies/account-switch.json`, one run at a time under an
  exclusive flock (`<state>/account-switch.lock`) shared with a person's
  `fabric-accounts switch --tick`. A run asks the fleet with the
  coordinator's ordinary reads (`identity`, `gateway`, `states`, and
  `usage` on one login of a stale account, ADR-031 rule 9's probe). It
  moves only in mode `act`, and only by `fabric-accounts assign <login>
  <account> --no-restart`, whose signed `secrets-sync` is the existing
  action; mode `off` asks nothing.
- **The coordinator's side** is `bin/fabric-ctl <login|all> <op>`: one
  request, the replies read until every placed address has answered or
  the timeout is spent, and a row for each — silence included.

The sudo paths stay as fallbacks for a host whose control agents are
down: `bin/fabric-usage` for the usage windows, `bin/fabric-host <host>
drain <login>` for a drain; and, until the operations that replace them
exist, the fleet views' read of closed jobs (ADR-046 rule 5).

## 3. Alternatives Considered

- **Sudo from the coordinator's login** (`fabric-usage`, the drain by
  reading another home). Rejected as the path: one host at a time, the
  coordinator reading every account's files, and a check that is the
  coordinator's rather than the account's. It stays as the fallback.
- **Ask the session.** Rejected: an account with no session cannot
  answer, a session's answer costs a model call, and a machine record in
  a session's context is exactly what must not happen.
- **A GZCoord message type for control.** Rejected: the protocol's
  grammar is frozen and its messages are for sessions; the records are
  machine data on their own channel.
- **A consumer cursor per daemon.** Rejected: the relay's `since_id` is
  an explicit cursor, so priming from the newest record needs no state
  on the relay or on disk, and a restart cannot replay history.
- **HMAC for actions.** Rejected: a shared secret in every account would
  let any account forge the operator. Ed25519 keeps the private half in
  one login.

## 4. Rationale

The account is the one that knows its own state, and it can say so
without a model: P5's "the control plane keeps answering when a model
does not." Reading only its own home, the control agent removes the
coordinator's need to enter any other, and the drain became the first
that read no home but the account's own. A closed op set with bounded
arguments keeps a forged or malformed request from reaching a shell.
The fence is honest about what it is: it stops accidents and bounds what
a forged read can obtain to non-secret facts; only the actions carry a
proof, and the one unsigned write, a pool claim, is bounded to a job's
claimant (rule 4).

## 5. Binding Rules

1. Every placed account runs `tools/fabric/control/agentd.py` under the user
   unit `agent-fabric-agentd.service` (`Restart=always`), installed and
   started by `bootstrap.sh`. The account lingers, so the unit runs from
   boot with no login and no session.
2. The control channel is named in `runtime/control/config.json` and ends
   in `:control`; `gzcoord-inbox` and `gzcoord-send` refuse such a channel with
   exit 2 before any request reaches the relay. Control records are never
   GZCOORD/1 messages.
3. The op set is closed (`tools/fabric/control/ops/__init__.py`). No field of a request ever
   reaches a shell. A read op takes no argument but `tokens`'s `days`, a
   number capped at 90, `pool-list`'s role and `pool-claim`'s pool id
   (`pool.py`); an action takes only its own closed set of
   arguments (`upgrade.py` and `secrets.py` `check_args`, `jobs.py`
   `check_job_args`, `pool.py` `check_pool_args` for `pool-add`, and
   `tools.py` `tools_install`'s one `tool`, matched by `TOOL_NAME`, and
   `gateway-install`'s one `version`, a key of `runtime/gateway.json`;
   `interweave-install` takes none, the release being the pin's
   `current`, nor do `interweave-start` and `interweave-stop`;
   `interweave-evidence` takes `section`, `since` and `until` and no other).
4. A daemon answers a request only when its `from` is a host operator's
   address as `runtime/hosts/registry.json` places it — re-read for every
   record — or, for a public op (`PUBLIC_OPS`: `presence`, `pool-list` and
   `pool-claim`), any
   placed account's address; its `ts + ttl_s` is not past; and its id is
   not among the last 256 seen. An op is public only if its answer is
   nothing a relay-token holder could not already obtain by writing an
   operator's address on an unsigned read. `pool-claim` is the one public
   op that writes: it sets one pool job's claimant to the asker, checked
   against the role the asker's own daemon reports, and adds, removes or
   reorders no job; a forged claim takes a job off the pool for a role's
   holder. `pool-list` shows unclaimed jobs only, so the claim and its
   claimant are seen in the pool holder's `pool.json`.
5. An action (`sign.py` `ACTION_OPS`) is answered only when it carries
   an Ed25519 signature over its canonical form by the key the operator's
   host commits as `operator_key`; it lives at most 600 s, is refused
   when dated more than a minute ahead of the account's clock, and must
   be strictly newer than the last action accepted from its sender
   (ADR-009 §5 rule 2). `interweave-evidence` is signed though it
   writes nothing: its rows are the account's own logs, and only an
   operator may ask for them. The private key is only in the operator's
   own store (`FABRIC_CONTROL_SIGNING_KEY`, ADR-038), made by `fabric-ctl
   keygen` (A 2026-09-30).
6. Every request gets a reply; a section that cannot be read says so
   inline (`{"status": …}`). Replies carry no secret: keys by presence and
   a twelve-hex-digit fingerprint only, text measures as counts only, a
   memory bundle only after the harvester's credential check;
   `interweave-evidence` rows are metadata from a closed list of keys,
   never a message body.
7. Every refusal but the routine ones (a reply, a request for another
   account, a duplicate) is one line in the daemon's journal.
8. `fabric-ctl` refuses, before posting, a run by a login that is not a
   host operator, except for a public op from a placed account. It exits
   1 when any addressed account stayed silent, when a drain bundle was
   short or refused, and for an action when any row is not a success. It keeps no state: the request and replies stay
   on the channel and nowhere else.
9. The drain (`fabric-ctl <login|all> memory --out <dir>`) has each
   account harvest its own memory and send each bundle in parts of at
   most 90 KiB; `fabric-ctl` files a bundle only when every announced
   part arrived, its sha256 matches, and its manifest names the account it
   came from — otherwise the row names the status and no file is written.
10. A daemon that sees its own source change exits once no action is
    running, and the unit restarts it on the new code.
11. On a host whose root volume does not persist (a Qubes AppVM), an
    account is persisted when it is created — `persist-accounts.sh` into
    `/rw/config/agent-fabric/accounts/`, re-added at boot by
    `agent-fabric-accounts.rc` — and linger is enabled in the same step.
    `/rw/bind-dirs` is never used for the account files.
12. An action runs beside the control agent's read loop, so a request
    that arrives meanwhile is still answered; one action of a kind runs
    per account at a time, and a second upgrade or `secrets-sync` sent
    while one runs is answered `busy`, as is an upgrade sent while a
    `secrets-sync` is restarting the session; a second `gateway-install`
    is answered `refused` by the install's own lock, and so is any of
    `interweave-install`, `interweave-start` and `interweave-stop` while
    another of the three runs on the account (one lock for the three). `fabric-ctl` waits for an
    answer as long as the operation's own budget (`tools/fabric/control/ctl.py`):
    20 s by default, 5 s for `ping`, 60 s for `tokens`, 120 s for a drain,
    200 s for `disk`, 240 s for `secrets-sync`, 300 s for `accounts`,
    1230 s for `tools-install` (past the account's own 1200 s bound, which
    a cargo pin's crate build needs, so a hung fetch or build is its
    verdict, not a silence), 300 s for `gateway-install`
    (its 240 s download bound, two 10 s version bounds and 40 s of margin), 100 s for
    `interweave`, 2668 s for `interweave-install` (a 1200 s wait for the
    host's download turn and 60 s of grace before the install's own
    1408 s: the download, the archive, `install.sh`, the version runs and
    two restart-and-check rounds), 1600 s for `interweave-start` (a
    600 s wait for the host's render turn; its rule-14 check polls the
    carrier's `status` up to 45 times, a cold carrier having taken 29 s
    to open its socket with 26 roster rows),
    156 s for `interweave-stop`, 60 s a page for `interweave-evidence`
    (`fabric-ctl` sends one request per page, to every account whose
    next page starts at the same time), 480 s for
    `secrets-selftest`, and an upgrade's
    computed budget; `--timeout` overrides it (A 2026-09-27).
13. `jobs` is an operator's read of an account's open jobs, and
    `jobs-add` an action that puts the owner's job on one login's list
    with source `owner` (ADR-037 rules 4 and 6). Neither is public: a
    peer sees whether a session runs, never another agent's list.
    `jobs-add` names one login, never `all`, and takes a one-line title,
    topic and project id (A 2026-09-28).
**§5 rule 14 — withdrawn** (Amendment 2026-09-30): the `secrets-migrate`
action moved every account from Doppler to its own store and retired
with Doppler (ADR-038 §5 rule 8).
15. `local` is an operator's read of the account's
    `.claude/settings.local.json` files, one per working copy under
    `~/projects` and the projects root's: the `env` key names, which are
    synced secrets, the permission rules by count, the other top-level
    keys; never a value. `local-prune` is an action that removes from
    those files the `env` entries duplicating a synced secret (ADR-038
    rule 9) and nothing else; it takes no arguments, never follows a
    symlink, and writes nothing when the file changed under it. Both run
    `tools/fabric/local_settings.py` as the account; neither is public
    (A 2026-10-06).
16. A session's state — working, blocked on a person, or idle — is
    kept by the harness hook `session-state.py` in the account's own
    state directory, and the account's control agent posts it as a
    `state` record (`sessions.py`) when what it would say changes, and
    every ten minutes, on a state channel of its own (`config.json`
    `state_channel`, ending in `:control`), so a burst of replies on the
    control channel never buries it. The record names each live session's id, state
    and since when, the binding's role and project, and the binding's last
    session id with whether its transcript is on the account (resumable),
    which Fleet Deck reads before it re-enters a tab, never a path
    (A 2026-10-08); a session whose
    `claude` process is gone is left out. `fabric-ctl states` reads
    those records, sending no request; a record older than two
    heartbeats reads as unknown, and `--follow` prints a row when it
    changes or goes stale. A display that shows the states
    consumes `fabric-ctl states --follow --json` and never polls the
    accounts (A 2026-10-07).
17. `secrets-selftest` is an action that proves the account can add,
    use and delete a secret of its own: it runs `fabric-secrets selftest
    --json` as the login (`selftest.py`), which sets a canary name in
    the account's own store, reads it through `fabric-secret-run`, and
    removes it — two signed commits pushed to the store's remote. It
    takes no arguments; the reply is the verdict (`pass` or `fail`) and
    its steps, never the canary or its digest. One runs at a time per
    account, a second is answered busy (A 2026-10-07).
18. InterWeave is control's second carrier, off for an account until
    `runtime/control/config.json` `control_carrier` names it `dual`
    (A 2026-10-28):
    - agentd runs one supervised, long-lived child,
      `interweave-human --profile gzcoord listen --json --input --consume
      --endpoint fabric-control`, from the pinned release (ADR-064 rule
      4), and sends through its stdin; no other `interweave-human` run
      uses that profile, and agentd drives no admin-changing verb;
    - `fabric-control` is the profile's only human endpoint, configured
      by the render; `gzcoord` stays automated-only. Every control send
      names `<peer>/fabric-control`; the GZCoord carrier refuses a
      `fabric-control/1 ` body on `gzcoord`, and agentd drops anything on
      `fabric-control` without that prefix;
    - a request counts only when its `from` is the address the roster
      (ADR-064 rule 2) maps the sender's PeerId to, and `fabric-ctl`
      accepts a reply only from its `from`'s PeerId;
    - rule 4's seen-set is one across both carriers, so a request is
      answered once; while both run, the reply goes by both, the same
      reply split into the same parts, and `fabric-ctl` keeps one copy
      per reply and per part, the InterWeave copy where both arrive, and
      logs every arrival with its carrier;
    - when both copies of a reply arrive within the op's budget, the
      row is the InterWeave copy, whose sender is authenticated; a relay
      copy that differs from it is flagged in the row, never shown as
      the account's answer; a row only the relay carried says so;
    - a send never outlives its request's `ttl_s`, and nothing is left
      pending for a later run; what the human store holds of a record is
      deleted after its line is printed, never before;
    - rule 9's parts and `interweave-evidence`'s pages are bounded by
      the carriers that send them: an account on both splits once, at
      the InterWeave bound, a figure measured on this path before the
      dual run starts and at most 32 KiB, and sends those parts by both;
    - `fabric-ctl` holds no lease: it hands its sends to the operator's
      own agentd over a socket in its runtime directory, mode 0600, and
      `all` is one direct send per placed account's roster row;
    - `interweave`, `interweave-install`, `interweave-start` and
      `interweave-stop` go on the relay only (ADR-064 rule 14);
      `interweave-evidence` goes by both, as any other op;
    - the relay stays the transport of record. InterWeave becomes it on
      the owner's word, given on a parity report in `docs/live-checks/`
      (every request id and addressee with the carriers that carried
      the request and the reply, p50 and p95 per carrier, each miss
      with its cause, and an `interweave-stop` drill mid-window with
      every request still answered), as an amendment of this record.
19. An action reaches an account with no relay only through
    `bin/fabric-op` (`tools/fabric/control/breakglass.py`), the
    break-glass path (A 2026-10-30). The operator runs `fabric-ctl
    <login> <action-op> … --via hostexec`: the request is built and
    signed as for the relay and handed to `hostexec <host> --as <login>
    -- @fabric/bin/fabric-op <op>` on stdin, never in argv; the relay
    and its token are not touched. On the account:
    - the decision is agentd's own `accept()` (rules 4–5: the operators,
      their keys, the ttl and the clock skew) and the op is agentd's own `answer()`, never a
      copy; the replay floor is the same `actions-seen.json` as the
      control agent's (ADR-003 §2), claimed by one check-and-record under
      its lock, so a request accepted on either path is a replay on the
      other;
    - beyond rules 4–5 it refuses, with exit 2 and nothing run, a read
      op (a read without the relay is a plain `fabric-host` run), a `to`
      holding `*`, and an argv op that is not the signed request's op; a
      `to` not naming this account is `accept()`'s refusal, and a `to`
      listing this account beside others is run here. `fabric-ctl`
      sends a read or more than one account nothing;
    - it journals to `fabric-op.jsonl` in the account's state directory,
      on both ends: a line before the run and one after, and a first line
      that cannot be written refuses the run, so no action runs that the
      journal does not show (ADR-041 rule 10);
    - its reply is the record the relay would have carried, one JSON
      line, and `fabric-ctl` prints it as that account's row;
    - the `busy` of rules 12 and 17 for `upgrade`, `secrets-sync` and
      `secrets-selftest`, and `restart`'s own exclusion and its refusals
      beside an upgrade or a `secrets-sync`, are held inside the control
      agent's process: an action through `fabric-op` is not refused
      against one the control agent is running at that moment, and
      `pool-add` can lose an update beside a `pool-claim` (ADR-003 §5
      rule 2). The locks of `gateway-install` and of the three InterWeave
      ops are file locks and do hold across both. Until every exclusion
      spans processes, break-glass is for an account whose relay is not
      there, not a second path beside a live one.
    It is verified on the host executor's local backend; the SSH backend
    and `--as` another login are not yet exercised.

## 6. Consequences

- The fence is not a proof for reads on the relay: it verifies no
  sender, so a relay-token holder can write the operator's `from` on a
  read, or post a reply in another account's name that `fabric-ctl`
  prints as that account's row. The table is as honest as the least
  trusted token holder until replies are signed. On an account on both
  carriers the InterWeave copy, authenticated by PeerId, is the row and
  a differing relay copy is flagged (rule 18); a reply that only the
  relay carried is no more honest than before.
- A request posted while a daemon was down is lost, not queued; the row
  says `no answer`, and the operator asks again.
- One relay carries the channel: when it is down, no account answers
  but one on both carriers (rule 18), and for the rest the sudo
  fallbacks are the only read (ADR-010's host executor) and `fabric-op`
  the only action (rule 19), one account per command.
- A drain costs no sudo and reads no other home; a credential-shaped hit
  in a memory refuses that account's whole drain at the harvester.

## 7. Future Evolution

- Signed replies, by a per-account key the same way, so a forged row
  cannot pass as an account's.
- A second host is reached over InterWeave (rule 18), not by the relay,
  which keeps binding `127.0.0.1`. It opens with ADR-064 rule 1's
  second-host amendment, where InterWeave is control's only carrier on
  that host and break-glass `fabric-op` through hostexec over SSH its
  fallback (rule 19; the SSH backend not exercised yet); an
  InterWeave peer on a public address comes after.
  The plan is `docs/proposals/j422-control-plane-on-interweave-cli.md`.
- Removing a login from the Qubes snapshot (`--forget`) waits for the
  first removal; until then a `userdel` there is undone at boot.
- A reboot of the host, read back — `getent passwd` lists every account
  and `fabric-ctl all ping` answers within seconds — has not been done.

## 8. Decision Status

Accepted. The control agent, the channel, the read ops and the signed
actions are in use on every placed account. Rule 18's second carrier is
not built yet: until it is, `control_carrier` is read by nothing and
every account is on the relay alone.

## References

- `tools/fabric/control/` (Python since ADR-040's Wave 8; the Node
  control plane was deleted in #170): `agentd.py`, `sessions.py`,
  `ops/` (the op set and the public ops), `sign.py` (`ACTION_OPS`),
  `ctl.py`, `upgrade.py`, `gateway.py`, `tools.py`; with
  `runtime/claude-code/hooks/session-state.py`,
  `runtime/control/config.json`, `runtime/control/agent-fabric-agentd.service`.
- `bin/fabric-ctl`, `bin/fabric-usage`, `bin/fabric-host`, `bin/fabric-op`
  with `tools/fabric/control/breakglass.py` (rule 19).
- `tools/fabric/gzcoord/inbox_parts/config.py` (`assert_not_control_channel`),
  `tools/fabric/gzcoord/send.py`.
- `runtime/claude-code/bootstrap.sh` (the unit),
  `runtime/provisioning/persist-accounts.sh`,
  `runtime/provisioning/platform/qubes/agent-fabric-accounts.rc`.
- `runtime/hosts/registry.json` (operators, `operator_key`, placement).
- ADR-009 (the actions and fleet operations), ADR-010 (hosts and the
  host executor), ADR-013 (the drain), ADR-027 (the `script` measure).
- The live check in Evidence.

## Amendments

The body above reads current; each change's full note is in [history/ADR-029-amendments.md](history/ADR-029-amendments.md).

| Date | Amendment | Effect |
|---|---|---|
| 2026-09-27 | Actions run beside the read loop | §5 rule 12 added: actions run beside the read loop, one of a kind per account, a second answered busy; fabric-ctl's answer timeouts |
| 2026-09-27 | Rule 12 as the code has it | §5 rule 12: every operation's answer budget, and an upgrade refused while a secrets-sync restarts the session |
| 2026-09-28 | The owner reads and adds jobs through the control plane | §5 rule 3: `jobs.mjs` arguments; rule 13: `jobs`, `jobs-add` |
| 2026-09-29 | secrets-migrate moves an account to its own store | §5 rule 14: the migration action |
| 2026-09-30 | Doppler is retired: the store holds what Doppler held | §5 rule 5 (the signing key's home), rule 14 withdrawn |
| 2026-10-06 | Each account's settings.local.json on the control plane | §5 rule 15: `local`, a names-only read; `local-prune`, an action removing synced secrets from its `env` |
| 2026-10-07 | Session state on the control channel | §5 rule 16: the session-state hook, agentd's `state` record on change and heartbeat, `fabric-ctl states [--follow]` |
| 2026-10-07 | secrets-selftest proves an account's own secrets | §5 rule 17: the `secrets-selftest` action, a canary set, used through `fabric-secret-run` and removed in the account's own store |
| 2026-10-08 | The state record names the last session and whether it can be resumed | §5 rule 16: `last_session` and `resumable`, no path |
| 2026-10-08 | The op table follows ops.mjs: disk, jobs, local, the pool and tools; three public ops | §2 table, §5 rules 3 and 4: rows for the read ops added since; the pool's arguments; `presence`, `pool-list` and `pool-claim` public |
| 2026-10-09 | pool-add's checker named; a forged claim is seen in the holder's pool file | §5 rule 3 names `checkPoolArgs`; rule 4: `pool-list` shows unclaimed jobs only, so a claim is seen in the holder's `pool.json`; the Scope line names pool.mjs, tools.mjs and sessions.mjs |
| 2026-10-09 | Scope: all of runtime/control/, and its Python package from Wave 8 | Scope line: the directory as a whole rather than a list that lagged it; tools/fabric/control/ from its creation; the unit's installation in bootstrap.py; local_settings.py and session-state.py, which rules 15 and 16 name |
| 2026-10-09 | tools-install installs a pinned account tool | §2 table: the `tools-install` row; §5 rule 3: its one argument, checked by `TOOL_NAME`; rule 12: the `disk` and `tools-install` budgets |
| 2026-10-10 | The gateway is installed and read through the control plane | §2 table: `gateway` and `gateway-install`; §5 rule 3: its one `version` argument; rule 12: its budget |
| 2026-10-09 | Fleet views read through fleet.py, with two Stage 1 bridges | §2: the host executor's read of closed jobs is a named fallback for the fleet views until `jobs --all` exists (ADR-046) |
| 2026-10-12 | The switch controller in the coordinator's agent; gateway carries joined accounts and session kinds; switch read | §2 table: `gateway` gains `setup_tokens` and `sessions`, a `switch` row; §2: the switch controller's run in the coordinator's agent (ADR-052 §8 piece 4) |
| 2026-10-18 | tools-install runs installer and cargo pins | §2 table: the `tools-install` row names the `installer` and `cargo` pin kinds and what each checks; rule 12: its budget 1230 s past the account's 1200 s bound (#303) |
| 2026-10-19 | tools-install runs rustup-target pins | §2 table: the `tools-install` row names the `rustup-target` kind (#317) |
| 2026-10-25 | The InterWeave programs are installed and read through the control plane | §2 table: `interweave` and `interweave-install`; §5 rule 3: no arguments; rule 12: their budgets |
| 2026-10-25 | The InterWeave units are started and stopped through the control plane | §2 table: `interweave-start` and `interweave-stop`; §5 rule 3: no arguments; rule 12: one lock for the three ops, their budgets |
| 2026-10-26 | The InterWeave install puts the client unit's program in place | §2 table: `interweave`, `interweave-install` and `interweave-start` |
| 2026-10-26 | The InterWeave start renders one account at a time and needs the port reservation | §2 table: `interweave-start`; §5 rule 12: its budget |
| 2026-10-26 | The InterWeave parity evidence is collected through the control plane | §2 table: `interweave-evidence`; §5 rule 3: its arguments; rule 5: signed; rule 6: no body; rule 12: 60 s a page |
| 2026-10-26 | A running InterWeave pair is re-rendered when the roster changed | §2 table: `interweave-start` |
| 2026-10-28 | The records also ride InterWeave, through interweave-human, beside the relay | §2: the second-carrier bullet; §5 rule 18; §6 first and third bullets; §7 second-host bullet; §8: not built yet |
| 2026-10-30 | fabric-op is the action path with no relay | Scope line: `bin/fabric-op`; §5 rule 19; §6 third bullet; §7 second-host bullet; References |
