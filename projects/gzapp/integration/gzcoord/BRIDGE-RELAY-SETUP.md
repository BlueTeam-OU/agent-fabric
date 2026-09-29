# Running the bridge relay (gzapp)

How a gzapp working copy on this host joins the shared GZCoord channel.
This is gzapp's integration of the protocol, not the protocol: the
candidate evaluation is
`communication/gzcoord/history/claude-bridge-selection/TRANSPORT-CANDIDATE-CLAUDE-BRIDGE.md`, and
**the relay carries GZCOORD/1 unchanged** — it is a carrier, not a
successor, and nothing in `communication/gzcoord/protocol/` changes for
it. The values below (relay URL, channel, token location, runtime
directory) are also in [`config.json`](config.json), which
`communication/gzcoord/scripts/inbox.mjs` reads when the working copy
resolves to project gzapp.

**Identity on the relay.** The relay's own `sender` field and the
`consumer_id` cursor key are this agent's address, `<host>/<login>`
(SPEC §3.1) — the account the session runs under, never the working
copy's directory name. Two sessions under one account share one cursor
and one address; that is the model, not a defect. The relay does not
authenticate senders (every instance holds the same bearer token), so a
`sender` there is a claim exactly as `FROM` is.

**Status: one relay is running, hosted by a single working copy.** That
is the limitation to fix next, and it is named at the bottom.

## The shape

One relay process, bound to `127.0.0.1:8765`, is the whole transport.
Every instance on this host is a *client* of it: they write nothing into
the hosting workspace, and the hosting workspace's `projects/.gzcoord/`
holds the database — the only record of the channel's past. The shared
channel is `gzapp:gzcoord`, following the relay's `<project>:<purpose>`
convention.

## Registration — already committed

`.mcp.json` at the repository root carries the entry for every clone:

```json
"claude-bridge": {
  "type": "http",
  "url": "http://127.0.0.1:8765/mcp",
  "headers": { "Authorization": "Bearer ${CLAUDE_BRIDGE_AUTH_TOKEN}" }
}
```

**No secret is committed.** The token is read from the environment, and
each clone supplies its own copy in the gitignored
`.claude/settings.local.json`:

```json
{ "env": { "CLAUDE_BRIDGE_AUTH_TOKEN": "<the shared token>" } }
```

A clone without that variable set simply shows the server as
unavailable; nothing else breaks.

## Hosting the relay

Only one workspace does this, and everything it creates lives in that
workspace's runtime directory, `projects/.gzcoord/` — beside the working
copies, inside none of them (`relay_runtime_dir` in `config.json`,
resolved against the directory the fabric checkout sits in). The relay's
database is the only record of the channel's past, the token is a
secret, and the venv is host state: none of it belongs in a repository,
gitignored or not (until 2026-09-14 it sat in the hosting clone's
`.gzcoord/`, and a directory rename stranded it once). The hosting duty
is the **fabric-coordinator role's**: that role's session start is the
activation of whatever hosts the relay — the `SessionStart` drain
(`scripts/inbox.mjs`, "Receiving", below) brings the relay up before
draining whenever this workspace hosts and the relay is not answering:
the user unit below where bootstrap installed it, else a detached
spawn. A client workspace has no `.gzcoord/venv`, skips
silently, and must not try to host: one relay, one owner, everything
else a client. Starting it by hand stays the documented fallback:

```bash
cd "$(dirname "$AGENT_FABRIC_ROOT")"          # the projects/ workspace
python3 -m venv .gzcoord/venv
.gzcoord/venv/bin/pip install claude-code-bridge
umask 077 && openssl rand -hex 32 > .gzcoord/bridge-token   # never printed, never committed
.gzcoord/venv/bin/claude-bridge \
  --host 127.0.0.1 --port 8765 \
  --db .gzcoord/claude-bridge.db \
  --auth-token-file .gzcoord/bridge-token
```

**Since 2026-09-19 the relay is a systemd user unit on the hosting
account**, `gzcoord-relay.service` (`communication/gzcoord/runtime/`),
installed by `bootstrap.sh` only where `.gzcoord/venv` exists and
gated a second time by the unit's own `ConditionPathExists`. It comes
up with the account's user manager at boot (the account lingers),
restarts on failure, logs to the same `bridge.log`, and is found by
name: `systemctl --user status gzcoord-relay`, `… restart gzcoord-relay`.
The session-start activation (`ensureRelay`) starts that unit when it is
installed and a user manager is up, and only otherwise falls back to the
detached spawn above. The hand-started process this replaced ignored
TERM, died with its terminal, and nothing could find it by name. A
relay started by hand or by an older session's spawn still holds the
port: stop it before the unit takes over — bootstrap says so when it
finds one and does not start the unit against it.

`--host 127.0.0.1` is the default and stays: the relay is unreachable
off this machine. Authentication stays on — a loopback bind is not a
substitute for it, and the token file costs nothing.

## Sending and receiving, and the one trap

The MCP tools (`bridge_send`, `bridge_wait`, `bridge_ack`, …) are the
intended interface. The JSON API underneath them is what an adapter
would target:

- `POST /api/send` — `{channel, sender, content}`. The field is
  **`content`**; `text` is rejected. **Validate before sending** (SPEC
  §1): compose the message in a file, run
  `gzmsg validate <file>`, and send only
  what passes. A message that fails is not sent — the relay carries
  what it is given, so the verdict is the sender's job, not the
  channel's.
- `GET /api/wait?channel=…&consumer_id=…&timeout_seconds=…` — the
  long-poll delivery path. Returns full `content`.
- `GET /api/messages/{id}` — one message, in full.

**The trap: `GET /api/messages` returns a truncated `preview`, not the
message.** It feeds the dashboard. An adapter that read deliveries from
it would hand recipients silently truncated GZCOORD/1 text, which fails
validation at the far end for no visible reason. Deliver from
`/api/wait` or fetch by id.

## Receiving: the session is woken, and reads only what is its own

The MCP tools are pull-only, but a session need not poll by hand.
`$AGENT_FABRIC_ROOT/communication/gzcoord/scripts/inbox.mjs` does two things with one code path:

- **On every session start** it runs from the `SessionStart` hook in
  `.claude/settings.json` and drains what arrived while the session was
  away. The relay keeps a cursor per consumer, keyed on this session's
  address, so each start shows only what is new. The first drain in a
  clone shows the whole channel once — tens of kilobytes today — and
  never again.
- **For the whole session**, it is the watch: `inbox.mjs --follow` under
  a `Monitor`, armed once at the session's first turn. `--follow` blocks
  for the life of the session, prints a delivery **for this session** the
  moment it lands — a broadcast, `TO` its address, or `TO-ROLE` its slug,
  everything else acknowledged and unprinted — and returns nothing on a
  quiet spell (the relay's long-poll ceiling is 55 s per call; `--follow`
  chains them silently). Whether it truly runs for the whole session
  depends on the Monitor tool: a build with a `persistent` boolean holds
  it forever (armed once, never re-armed); a build whose `timeout_ms`
  caps at 30 min expires it there, and the session re-arms on the tool's
  expiry notice. Either way it is one process, the cursor is untouched
  between arms, and the retired shapes — hand-re-armed `--wait`, then a
  `while true; do inbox.mjs --wait 1800 …; done` loop that printed a
  quiet-expiry line to filter every 30 minutes — are gone. A resume does
  not restore the watch (owner rule, 2026-09-13): re-arm first thing
  after one. The `gzcoord-receive` skill has the exact commands.

Both apply SPEC §7.1 addressing and the §17 reading rule **at
delivery**: a message whose `TO` is not this address, whose `TO-ROLE`
is not this session's slug, and which is not a broadcast is listed by
its metadata line only — id, type, addressee, subject — and its body is
never printed. That is the filter the candidate evaluation said a
transport should provide, done where it costs nobody's context. The
cursor advances past those too, in the drain and inside the wait: an
acknowledgement means "shown this position", not "read the body".

Each delivered message is validated on the way in, so a sender's error
— a missing id, a misspelled key, an over-width line — is named beside
the message rather than discovered later.

It never blocks a session start. Relay down, no token, no catalogue:
one line on stderr, exit 0. A subagent worktree has no gitignored token
file, so it skips silently by design.

## The message id is still yours, not the relay's

`MESSAGE-ID` is minted with `gzmsg.mjs new-id` — a UUIDv7 (RFC 9562):
time-ordered, unique without coordination, no counter file, nothing to
seed, nothing to collide. SPEC §7.2 says "opaque identifier"; the format
is a deployment convention, not grammar. The sequential
`<instance>-NNNN` counter this replaced existed for loss visibility on
the lossy human relay; the durable carrier has no gap to detect, and the
counter was the subsystem's largest defect source — a restart-reuse, a
seeding step, a number burned by peeking, a hand-written collision and
an idempotency 409, five incidents across three days. A minted id makes
the sender's MUST-NOT-reuse obligation (§7.2) true by construction.
`next-id` still works as the retired name; its `--peek` and `--seed`
are refused with a message saying the counter is gone.

The relay stamps its own `seq` on every message it stores, and that is a
different thing. It counts **per channel**, not per sender; it is
assigned by the carrier rather than by the author; and it means nothing
once the carrier changes. Reading it as the message id would collapse
every sender's numbering into one channel-wide count, and the
reconciliation that numbering exists for — which messages of mine did you
never receive — becomes impossible to ask.

Use the relay's `seq` and message `id` for what they are: cursors and
deduplication inside the carrier. Correlation between agents stays
`MESSAGE-ID` and `IN-REPLY-TO`.

## What was verified here

- A `HELLO` written to `gzapp:gzcoord` came back to a *different*
  consumer id byte-for-byte identical, and revalidated with
  `gzmsg.mjs validate`. Text passes through unaltered. (`HELLO` is
  retired since, and `validate` now rejects one; who is running is
  presence, `fabric-ctl <login|all> presence`.)
- Both the long-poll path and the fetch-by-id path return full content;
  only the listing truncates.
- Authentication is enforced: `/mcp` answers 401 without the token.

## One consumer id per agent, and the raw API when MCP is not there

The cursor key is the agent's **address**, `<host>/<login>` — exactly
what `inbox.mjs` reads and acks as. A session that reaches the relay
through the MCP tools with a bare login (or any other string) creates a
second cursor for the same agent, and the next `SessionStart` drain
replays everything that second cursor never acknowledged (seen
2026-09-13: seq 105–110 handed back after they had been handled). Use
the address, byte for byte, from every path.

When the MCP connection is dead but the relay answers, the JSON API
above works directly with the bearer token: `POST /api/send`,
`GET /api/wait?channel=…&consumer_id=<address>&timeout_seconds=…`,
`POST /api/ack {consumer_id, channel, message_id}` (used that way after
the 2026-09-13 host reboot). Read with a throwaway consumer id only to
*audit* history, and never ack as the real address from an audit.

## What was once not yet true

Both limits recorded at first bring-up are closed: real instances
exchange traffic on the channel daily, and the relay has an owner that
outlives a session — a systemd user unit on the hosting account, brought
up with the account's user manager and, failing that, by the
fabric-coordinator's session start from the workspace runtime directory
(`projects/.gzcoord/venv`). One
thing learned while it still lived in a clone: **renaming the directory
holding the venv strands it** — its scripts keep the old interpreter
path — and nothing can start the relay again until the venv is rebuilt
in place (`python3 -m venv .gzcoord/venv && .gzcoord/venv/bin/pip
install claude-code-bridge`; token, DB and log stay). The old process
keeps running from open file handles, which hides the breakage until it
exits; the workspace directory is not one anybody renames, which is
one more reason the runtime lives there now.

Still open:

- ~~The relay dies with its hosting session~~ — closed 2026-09-19: it is
  a systemd user unit on the hosting account (§Hosting), up with the
  account's user manager at boot, restarted on failure.
- ~~The token has to reach the other clones~~ — closed 2026-09-14: it
  reaches every account as `CLAUDE_BRIDGE_AUTH_TOKEN` in the environment,
  from the account's own store (`bin/fabric-secrets sync`); the
  coordinator puts it in each store (`fabric-secrets provision share`).
