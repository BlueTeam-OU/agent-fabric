# ADR-052 — The account-switch policy for gateway sessions: sticky, with hysteresis, soonest reset first, perishable moves rate-limited, decided by the controller

**Date:** 2026-10-11
**Status:** Accepted
**Ratified:** owner, 2026-10-12, in the session ("ADR-052 accepted, build the controller in advise mode")
**Decision Makers:** the owner; drafted by fabric-coordinator
**Scope:** which Claude account a gateway session's login runs on, and when it is moved without the owner; the policy file `routing/policies/account-switch.json` (to be created); the switch controller in the coordinator's account (to be built, `tools/fabric/control/`); the launcher's relay of the gateway's `{"op":"usage"}` answer (`tools/fabric/launcher/gateway.py`); the control plane's read of it (ADR-029); the move log and its lines in `bin/fabric-status` and the Fleet Deck; plain-claude sessions are out of scope
**Pillar:** P7
**Evidence:** docs/live-checks/2026-10-10-gateway-check-6.md

## 1. Context and Problem

The fleet runs on more than one Claude subscription, and a login's account
is changed only by `fabric-accounts assign` (ADR-031). Since agent-fabric
#172 and #177 a session launched with `--provider gateway` is switched
without a restart: the assign's `secrets-sync` replaces the login's token
file by write-then-rename, the gateway reads the file on every upstream
attempt, and `tools/fabric/control/gateway_switch.py` joins the new file's
generation to the token's fingerprint and reports whether the gateway has
used it yet.

What is missing is a rule for *when*. Today the owner reads `fabric-ctl
all usage` (or `fabric-usage`) and moves logins by hand; on 2026-10-10 the
whole fleet was moved onto one account after a free reset, with a second
account held in reserve. A hand-driven move is late (an account found
exhausted has already refused turns), coarse (the fleet moves at once) and
wasteful (a weekly window that resets unused is quota that perished).

Three facts bound any automatic rule:

- **A switch costs a cold cache.** Gateway live check 6
  (`docs/live-checks/2026-10-10-gateway-check-6.md`) switched accounts
  between tool results inside one loop: the loop was served (200) on the
  new account with no restart, and its first turn there wrote the whole
  prompt cache again (cache_read 0, cache_creation 34,616). The gateway's
  checks 4–5 measured the same cost between completed turns, and that
  every cache write was `ephemeral_5m` (agent-fabric-gateway
  `architecture/research/live-checks/2026-10-09-account-switch-thinking-and-cache.md`).
- **Signed thinking across accounts mid-loop is unmeasured.** Check 6's
  run had no thinking block before the swap (`thinking_before_hook`
  false); whether a block signed under one account is accepted by another
  inside a loop is still open, and gateway ADR-010 says that if a new
  account rejects it, the switch happens only at a conversation boundary.
- **The gateway now reports usage.** agent-fabric-gateway #38 (plan s11)
  answers `{"op":"usage"}` on the launcher's control descriptor with, per
  credential source, the latest `anthropic-ratelimit-unified-*` reading:
  `five_hour` and `seven_day` utilisation, reset and surpassed threshold,
  `status` (`allowed`, `allowed_warning`, `rejected`, `rate_limited`),
  overage and fallback, each stamped with the token file's generation and
  the time of the reading; an absent header is `null`, never 0 (plan v0's
  README, "Usage (s11)"). The gateway knows no accounts: joining a
  generation to an account is the controller's.

The design studied is asifjahmed/claudemanager, a local proxy that routes
Claude Code sessions across several subscriptions by the same headers.
Its router is sticky per session, has a land and an eject threshold,
prefers the account whose weekly window resets soonest, moves sessions
proactively to quota about to perish at most once per 30 minutes across
the pool, and splits a 429 into exhausted-until-reset and transient. Its
ideas are taken here; its code is not, and five of its choices are
refused (§3).

## 2. Decision

**The controller moves a gateway session's login between Claude accounts
by a committed policy; the gateway only reports usage and serves the
token file it is given.**

- **Inputs.** Per credential source, the gateway's live usage, relayed by
  the launcher from the control descriptor to the login's state and read
  by the control plane, joined to an account through the generation join
  `gateway_switch.py` already keeps. An account with no fresh gateway
  reading is read by ADR-031 rule 9's one-token probe; `fabric-usage`
  stays the fallback when control agents are down. A 429 counts as
  exhaustion only when classified exhausted-until-reset; a transient 429
  is the harness's to retry.
- **Sticky.** A running session stays on its account, where its prompt
  cache is. It is moved for exhaustion, for crossing its account's eject
  threshold, or for a perishable move (below) — never because another
  account is merely preferable.
- **Hysteresis.** Two thresholds per window: new sessions stop landing on
  an account at its *land* threshold; a session already there is moved
  only at the higher *eject* threshold or at exhaustion.
- **Target.** Among accounts under both land thresholds, the one whose
  seven-day window resets soonest; if none is under, the one with the most
  headroom, and the owner is told.
- **Perishable moves.** When another account's seven-day window resets
  within 24 hours largely unused, one idle session may be moved onto it
  proactively: at most one such move per pool per 30 minutes, and only
  between tool-use loops.
- **Who acts.** The switch controller, in the coordinator's account, which
  alone holds the templates; it moves by the same signed path as
  `fabric-accounts assign`. Every move is logged with its reason and
  readings, and shown in `fabric-status` and the Fleet Deck.
- **The numbers are configuration.** Thresholds, the perishable window,
  the pool rate limit and the mode live in
  `routing/policies/account-switch.json`, a reviewed commit by
  fabric-coordinator, never constants in code.

## 3. Alternatives Considered

- **Manual switching only (today).** The owner reads usage and runs
  `fabric-accounts assign`. Kept as the override and as the `off` mode,
  rejected as the rule: the owner is the slowest reader of a five-hour
  window, an exhausted account is found by its refusals, the whole fleet
  tends to move at once, and quota that resets unused is never claimed.
- **The gateway decides on its own.** It sees every response's headers
  first and could swap credentials itself. Rejected: gateway ADR-001
  says the account behind an authentication profile
  is credential material the controller may change, and the gateway never
  chooses, discovers or ranks it; gateway ADR-006 says a 429 is passed on
  unchanged and the gateway never fails over to another account; gateway
  ADR-007 leaves cross-session account availability to the controller. A
  gateway sees one session; the pool rate limit, the soonest-reset choice
  and the templates are fleet facts it does not hold.
- **Round-robin**, or least-loaded, per new session or per interval.
  Rejected: it ignores stickiness, so every rotation pays a full cache
  write (34,616 tokens in check 6) for nothing; it ignores reset times, so
  it spends the account with the most future quota as readily as the one
  whose quota is about to perish; and an interval rotation moves sessions
  mid-loop, the case check 6 left open for signed thinking.
- **claudemanager as it is.** Its routing ideas are adopted; these of its
  choices are not:
  - *fail-open to the caller's own login* when no pool account can serve:
    a fabric session runs only on a template (ADR-031 §5 rule 3), and an
    unplanned fall-through spends an account nobody assigned;
  - *logging prompt bodies* (plaintext in SQLite): the gateway keeps no
    body (gateway ADR-012), and neither does the controller;
  - *an unauthenticated local API*: usage is read over the launcher's
    control descriptor, which holding is the authority, and the control
    plane's signed relay;
  - *rewriting the request's model* to steer a session between per-model
    windows: the plan maps models (gateway ADR-004), and routing is
    ADR-005's;
  - *remotely fetched configuration*: the policy is a committed file.

## 4. Rationale

Stickiness is the price check 6 measured: one cold cache per switch, so a
switch must buy more than a cache write. Exhaustion buys it (the session
cannot run at all), and so does reaching the eject threshold, past which
the session is about to be refused. A preference does not. Hysteresis
keeps the land and eject decisions apart so that an account near its land
threshold does not flap sessions in and out at every reading.

Soonest weekly reset first spends the quota that would otherwise perish
before the quota that will still be there next week. That is the fleet's
own interest in P7 terms: the subscriptions are paid for whether used or
not, and an unused window at its reset is cost with no verified result.
The perishable move applies the same reasoning to a running session, and
its rate limit ("never a herd") keeps it from moving the fleet at once
onto one account, which would then cross its own threshold together.

Moving only between tool-use loops follows from what check 6 did not
measure: a mid-loop switch with signed thinking is unproven, and gateway
ADR-010 allows a switch only at a boundary if the new account rejects it.
An idle session at its prompt is also cheap to move: a session idle past
the cache's five-minute lifetime has a cold cache on either account.
Exhaustion is the exception, because the session is already stopped and
the gateway retries a 429 once on a replaced credential (gateway ADR-006).

The controller decides because it holds the facts a decision needs — every
account's windows, every session's state, the templates and the last move
— and because ADR-031 already makes a move a signed, proved action of the
coordinator's. The gateway stays a data plane.

## 5. Binding Rules

1. **Inputs.** The controller decides from, per Claude account, the
   five-hour and seven-day utilisation and reset and the `status`, taken
   from the gateway's `{"op":"usage"}` reading of a source whose
   generation the join (`gateway_switch.py`, `gateway-generations.json`)
   maps to that account's fingerprint. A reading older than the policy's
   `reading_max_age_s` is stale; an account whose freshest reading is
   stale is read by ADR-031 §5 rule 9's probe, at most once per
   `probe_min_interval_s`. A `null` field is unknown, never 0; a decision
   that needs an unknown field is not taken. `fabric-usage` is the
   fallback when the control plane is down, and nothing moves on it alone.
2. **Exhaustion.** An account is exhausted until its reset when its
   reading's `status` is `rejected` or `rate_limited`, when a utilisation
   is 1 or above, or when the gateway reports a 429 classified as
   exhausted-until-reset. A 429 classified transient, or not classified,
   moves nothing.
3. **Sticky.** A running gateway session is moved only by rule 4, rule 5
   or rule 7. No other reason moves it, a better account included.
4. **Exhaustion move.** A session whose account is exhausted is moved at
   once, whatever its state, to rule 6's target. It is not counted
   against rule 7's rate limit.
5. **Eject move.** A session whose account has crossed an eject threshold
   (`eject.five_hour`, `eject.seven_day`) is moved to rule 6's target at
   its next boundary (rule 8), or at exhaustion if that comes first.
6. **Target.** The target is, among the pool's accounts other than the
   session's that are under both land thresholds (`land.five_hour`,
   `land.seven_day`) and not exhausted, the one whose seven-day window
   resets soonest; a tie goes to the lower seven-day utilisation. When no
   account qualifies, the target is the non-exhausted account with the
   most headroom (the smaller of its two windows' remaining shares), the
   move is logged as `relaxed`, and the owner is told. When every account
   is exhausted nothing moves, the session waits, and the owner is told;
   the controller never falls back to a login's own sign-in or to an
   account outside the pool.
7. **Perishable move.** When a pool account's seven-day window resets
   within `perishable.within_hours` (24) with utilisation at or below
   `perishable.max_utilization`, and it is under both land thresholds,
   one session may be moved onto it from another account, at a boundary
   (rule 8). At most one perishable move is made per pool per
   `perishable.min_interval_s` (1,800). A session moved in the last
   `min_stay_s` is not moved again by this rule.
8. **The boundary.** A session is between tool-use loops when its state
   record (ADR-029 §5 rule 16) says `idle`. Rules 5 and 7 move only an
   idle session; one that is `working` or `blocked` waits for its next
   `idle`. Among candidates the controller prefers the session idle
   longest. A session whose state is unknown is not moved by rules 5 or 7.
9. **Who acts.** Only the switch controller decides a move, and it runs in
   the coordinator's account. It moves by the same path as
   `fabric-accounts assign <login> <account>` (ADR-031 §5 rules 4–5): the
   store write, then the signed `secrets-sync`, and the reply's gateway
   proof read back. The gateway reports usage and serves the token file it
   is given; it never chooses, ranks or swaps an account itself.
10. **Configuration.** Every number in these rules, the pool's accounts
    and the mode are in `routing/policies/account-switch.json`, written
    by fabric-coordinator (`policies/AUTHORITY.md`). The mode is `off` (no
    move by the controller), `advise` (each move it would make is logged
    and shown, none made) or `act`. Its first committed value is
    `advise`; `act` follows the live checks of §8. Proposed starting
    values: land 0.90 (five-hour) and 0.97 (seven-day), eject 0.97 and
    0.995, perishable within 24 h at or below 0.60, one per 1,800 s,
    `min_stay_s` 7,200.
11. **The move log.** Every move, and in `advise` every move not made, is
    one line in the coordinator's state with the time, login, session id,
    from and to accounts by name and fingerprint, the rule and its reason
    (`exhausted`, `eject-5h`, `eject-7d`, `perishable`, `relaxed`), the
    readings it rested on with their ages, and the assign's verdict and
    gateway proof. No token, prompt, body or header the gateway did not
    parse is logged.
12. **Visible.** `fabric-status` shows a gateway login's last move and its
    reason; the Fleet Deck and `fabric-ctl` show the pool's accounts with
    their windows and the last moves. A `relaxed` move and an all-exhausted
    pool are told to the owner, not only logged.
13. **Scope.** The policy applies only to sessions launched with
    `--provider gateway`. A plain-claude session is moved only by hand
    (ADR-031), because its move is a restart.

## 6. Consequences

- The owner stops reading usage to keep the fleet running; a move by hand
  stays possible and is logged like any other, and a hand move is not
  undone by the controller unless a rule fires.
- Each switch still costs one cold cache; the rules make it rare, and the
  move log counts it.
- The usage reading follows traffic: an account no session uses has no
  gateway reading, so the probe of ADR-031 §5 rule 9 spends one output
  token of it now and then.
- The control plane gains a read (each login's relayed usage) and the
  launcher a periodic poll of its gateway's control descriptor; ADR-029's
  op table is amended when they are built.
- The pool is only as wide as its templates; the policy picks among
  accounts, it does not add any.
- **The pool is settled:** the fleet already
  pools its subscriptions, and does so legitimately; today a login is
  moved by stopping its session in the harness and relaunching it on the
  other account. From the provider's side a stop-and-relaunch and a
  gateway swap between tool-use loops are the same event, so this record
  changes how a move is made, not whether one is made. The mode leaves
  `advise` for `act` on the live checks of §8 alone.

## 7. Future Evolution

- Signed thinking across accounts inside a loop, once measured (the
  pending rerun of check 6 on a model that thinks every turn), may relax
  rule 8 for eject moves, or confirm it.
- Per-model windows (a scarce model's own meter) could steer a session's
  target; the reading does not carry them today, and the steering stays
  out of the request (§3).
- A second pool, or accounts on other hosts, needs the rate limit of rule 7
  kept per pool, which it already is.

## 8. Decision Status

Accepted (the header names the owner's word). The sequence, each piece by the role that builds it:

1. **The 429 split** (agent-fabric-gateway, rust-services-dev): a 429 with
   `rejected`/`rate_limited` headers reported as exhausted-until-reset, any
   other as transient, in the usage answer or the log. In progress; not
   yet in the gateway's main.
2. **The relay** (agent-fabric, python-dev): the launcher polls
   `{"op":"usage"}` on its control descriptor and writes the answer to the
   login's state; the control plane's read returns it joined to accounts
   through `gateway-generations.json`.
3. **The switch controller** (agent-fabric, python-dev): the loop of §5,
   under `tools/fabric/control/`, in the coordinator's account, moving by
   the assign path; the move log; `fabric-status` and the Deck lines.
4. **The policy file and this record** (fabric-coordinator):
   `routing/policies/account-switch.json` in `advise`, its schema and lint,
   and the ADR-029 amendment for the new read.
5. **Live checks**, run with two real accounts and recorded under
   `docs/live-checks/` as checks 6 and 7 were: a perishable move of an idle
   session onto an account due to reset, with the rate limit holding a
   second candidate back; and an eject at threshold, made at the next
   `idle` and not mid-loop. Then the mode moves to `act` by a commit.

## References

- ADR-031 (Claude accounts; the move by signed action; rule 9's probe),
  ADR-029 (the control plane; rule 16's session state), ADR-005 (routing),
  ADR-036 (cost per verified result), ADR-017 (live checks as evidence).
- `tools/fabric/control/gateway_switch.py` (the generation join and the
  gateway proof), `tools/fabric/control/accounts.py`,
  `tools/fabric/control/ops/usage.py`, `tools/fabric/control/sessions.py`,
  `tools/fabric/launcher/gateway.py` (`--control-fd`), `bin/fabric-usage`,
  `bin/fabric-accounts`, `bin/fabric-status`.
- `docs/live-checks/2026-10-10-gateway-check-6.md`.
- agent-fabric-gateway: `architecture/contracts/plan-v0/README.md`
  ("Usage (s11)", #38); ADR-001, ADR-006, ADR-007, ADR-010, ADR-012;
  `architecture/research/live-checks/2026-10-09-account-switch-thinking-and-cache.md`
  and `2026-10-10-switch-inside-a-tool-use-loop.md`.
- asifjahmed/claudemanager, read 2026-10-10 (its README, `src/core/router.ts`).
