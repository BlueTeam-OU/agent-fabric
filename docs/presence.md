# Presence — asked of the control plane, never announced

Until 2026-09-25 an agent was "online" when its `HELLO` was the last word
on the channel: the launcher sent one before each session and a
`GOODBYE` after it. On that day the host crashed and sixteen sessions
ended with no `GOODBYE`; a launch cancelled at the resume picker sent a
`HELLO`/`GOODBYE` pair five seconds apart that another agent had to ask
about; and the announcements were most of what every watch delivered.
An announcement is a claim a session makes about itself. The owner moved
presence to where it is a fact: the process table.

## What answers it

Each account's control agent (`runtime/control/agentd.mjs`) answers a
`presence` request from its own process table and binding
(`runtime/control/ops.mjs` `presence()`): whether a `claude` session is
running (not the daemon's own children), how many, since when (the
earliest start, from `/proc`), the role and project — the role
derived exactly as the inbox's delivery derives it, so a `TO-ROLE` the
relay would deliver is never refused — and whether it is planning (its
inbox held until the plan is approved, `docs/adr/ADR-022-the-session-lifecycle.md`;
a boolean, nothing more). A `pgrep` that cannot run is
`status: failed`, which every reader treats as unknown, never as offline.

`presence` is the one PUBLIC op (`ops.mjs` `PUBLIC_OPS`): any placed
account may ask it, every other op stays the operator's
(`docs/control-plane.md`, "The fence"). It gives a relay-token holder
nothing new: an unsigned read op with a forged operator `from` already
answered.

## Who asks it

- **Anyone:** `bin/fabric-ctl <login|all> presence` — one row per
  account: running or planning (since, role, project), none, unknown, or
  no answer.
- **`send.mjs`, before a `TO` or `TO-ROLE` message leaves**
  (`runtime/control/presence.mjs`): an addressee with no session, a
  control agent that did not answer or could not tell, or an address no
  host places is named, nothing is sent, exit 4; a `TO-ROLE` passes when
  any holder is running; a broadcast is not checked. An addressee that is
  planning is said and still sent to — a note, never a refusal; for a
  `TO-ROLE`, only when every running holder plans and no account was
  silent. The sender decides:
  `--force` sends anyway, since a message to a login with no session
  waits in the relay until one starts, which may be what is wanted.
- **The working rule "a request dies with its session — re-send at the
  addressee's next `HELLO`"** becomes: check presence; re-send when a
  session is running.

## What stopped

- The launcher sends no `HELLO` before a session and no `GOODBYE` after
  it; `bin/fabric-role bind` sends no `GOODBYE` on a role change;
  `tools/fabric/announce.py` is gone. The session is still the
  launcher's child, which is what lets an upgrade or an account move
  bring it back (`docs/fleet-upgrade.md`).
- The inbox acknowledges a `HELLO` or `GOODBYE` — from a session not yet
  relaunched, or another deployment — and never delivers or lists it; a
  replay by seq still shows one.
- GZCOORD/1 deprecates both (`communication/gzcoord/protocol/SPEC.md`
  §5): an instance SHOULD NOT send them, presence is the deployment's to
  answer, and a conforming parser still accepts both. Inside /1, not
  /2: no message changes meaning and nothing that parses today stops
  parsing (§18).
