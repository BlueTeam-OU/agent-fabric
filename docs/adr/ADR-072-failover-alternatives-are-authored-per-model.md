# ADR-072 — A route's failover alternatives are authored per model, held by a live continuity check, and declared wherever the model is served

**Date:** 2026-11-22
**Status:** Proposed
**Decision Makers:** the owner; drafted by fabric-coordinator
**Scope:** which failover alternatives the session plan compiler (`tools/fabric/gateway_plan.py`) declares on a route, and from which data: the authored file `routing/policies/failover.json` and its lint; when a plan is written as plan schema 2; session-level failover, which ADR-055 §7 left out; a review served by an alternative and how its posted review names it (ADR-055 rule 3); the Codex review's own plan; what is the gateway's and stays there (agent-fabric-gateway ADR-006, ADR-007, the plan contract's "Schema 2")
**Pillar:** P1
**Class:** engine

## 1. Context and Problem

The gateway can now take a route's declared alternatives
(agent-fabric-gateway#97): plan schema 2 lets a route carry `failover`, an
attempt cap of 2 to 4 and one to three alternatives, each a backend, a
model and a credential profile, taken in the order written. The gateway
leaves which alternatives a generated plan declares to a record of the
control plane (gateway ADR-006 §8, ADR-007 §8, open question OQ-1 of
2026-11-13); until one says, no generated plan carries `failover` and every
route is detect-and-report.

What the gateway does with an alternative bounds what is worth declaring:

- A further attempt follows only a failure whose request was not sent: the
  connection or TLS session not made, the credential not resolved, the
  request not formable for that target. An answered 5xx or 429 is passed
  on (gateway ADR-006 §8).
- Health is kept per endpoint, per model and per credential, and filters
  the declared order before each attempt: a model whose scope is open is
  set aside and the next candidate is taken first (gateway ADR-007 §2.4,
  §2.7). Health never empties the order.
- No alternative crosses accounts, and none crosses the listener's
  protocol (gateway ADR-006 rule 16, the plan contract).
- Listing an alternative is the controller's assertion that the
  conversation may continue on it; the gateway checks nothing of it
  (gateway ADR-006 rule 18).
- The response names the model that served it, the upstream's, never
  rewritten (gateway ADR-004 rule 17).

The session plan has one backend and one credential, the login's
subscription token file (or its OpenRouter key). Moving to another
account is ADR-052's, by replacing the credential, never an alternative.
So the one thing an alternative can vary is the model, and what it does
is mostly at selection: when a model's scope opens on capacity failures,
the session's next requests are served by another model. That is
session-level failover, which ADR-055 §7 left outside its record. On the
routes in use it also reaches the review: the plan has one route per
distinct model, and the Claude review class resolves to the same model
as the default session and code-high (`claude-opus-5-5` on the anthropic
column, `deepseek/deepseek-v4-pro-0813` with its shim on openrouter,
where code-plan rides it too). A role or agent whose session is routed
elsewhere (`routing/profiles.json`: python-dev on Sonnet 5.5,
architect-cto-01 on Fable 5.2) has a session route of its own. A review
served by another model is a divert, which ADR-055 rule 3 allows only when
its engine is the only one required and only when the posted review says
so.

## 2. Decision

A running session, a subagent and a review may each be served by another
model of the same provider and account when the gateway moves a request
off the routed one. The alternatives are authored, not derived: a
committed file, `routing/policies/failover.json`, gives per provider and
per routed model the ordered models that may serve in its place, each
admitted only with the live check that showed a conversation begun on the
routed model continuing on it. The compiler declares them on every route
whose target is that model, with an attempt cap of one more than their
number, and writes plan schema 2 only when a route carries them and the
gateway in use reads schema 2. A route the review class uses takes as its
alternatives the next models of ADR-055 rule 7's review order and nothing
else, and the review served by any of them names it on the posted review
as a divert. The Codex review's plan carries none.

## 3. Alternatives Considered

**Declare none; only another endpoint of the same account serving the
same model.** It keeps every session on its routed model and needs no new
policy, but no such endpoint exists for either provider, so the gateway's
enforcement would have no consumer and a capacity spell on the routed
model would still fail every request of every session riding it. The
owner chose failover.

**Model alternatives only on routes no session and no review uses.** It
keeps the session's model fixed and the review out of it, but on the
anthropic column that leaves the haiku, sonnet and fable routes, and the
default session's model, the one the owner watches stall, would get none
(the sessions routed to sonnet or fable would be cut off again by their
own rule).

**Derive the alternatives from ADR-055 rule 7's ordered lists.** Those
lists are a run's divert order for the review capability, not a claim that
a conversation continues; they name `claude-opus-5[1m]`, a harness
marker and no upstream id; and they say nothing for the other classes.
Rule 18 of the gateway makes each alternative an assertion of continuity,
so each is authored and checked. The review route is the exception: its
order is rule 7's, because a divert must follow it.

**Alternatives across accounts or providers.** The gateway validates
only the protocol: both providers' backends speak `anthropic`, and an
account is no plan fact (gateway ADR-006 §2.8), so provider and account
confinement are the controller's, held by rule 1 and rule 8's lint.
ADR-055 rule 3 forbids, besides, a review falling back onto another
engine's provider.

## 4. Rationale

A capacity spell is the provider's and lasts minutes (ADR-055 §1); today
it stops every session on the model and the gateway can do nothing,
though another model of the same subscription would serve. Health that
sets aside an open model and takes the next one is local rediscovery in
ADR-055 rule 1's sense: each launch starts a gateway of its own, which
dies with the session (`tools/fabric/launcher/gateway.py`), and keeps its
health in that process alone (gateway ADR-007 rule 17), so what moves a
request is what this session's own attempts met, never a record another
session or login left. What has to be true for that to be safe is
the continuity of the conversation, which only a live check shows, so the
data carries the check with each pair. Declaring the same alternatives on
every route of a model, rather than per class, follows from the plan
having one route per model: a rule per class would be bound on a shared
route by its strictest user, and the review is the strictest user; making
its order the route's order is what keeps the shared route lawful.

## 5. Binding Rules

1. **Authored per model.** `routing/policies/failover.json` gives, per
   provider column of `routing/capabilities.json` and per model as routing
   composes it (the selector the plan routes), up to three alternative
   models in the order they are to be taken. An alternative is a model of
   the same provider served through the same backend and credential
   profile: never another account, provider or protocol. A harness marker
   such as `[1m]` is no model.
2. **Each pair is checked live.** An alternative is admitted only with a
   live check under `docs/live-checks/` that began a conversation on the
   routed model, tools and thinking included, continued it on the
   alternative through the gateway, and then back on the routed model,
   as the gateway's probe moves it; an entry with more than one
   alternative is checked between every two of its candidates, both
   ways. Every hop is sent in the shape the harness sends for the routed
   model: its context length, its thinking and effort parameters, its
   beta headers. The entry names that file. A model
   change on either side, or a harness pin that changes the request
   shape, re-opens the check.
3. **Declared wherever the model is served.** The compiler writes a
   route's `failover` from the entry of its target model, for the session's
   route and every class's alike, with `max_attempts` one more than the
   number of alternatives. A model without an entry gets no `failover`.
4. **The review's route follows its divert order.** On the route of the
   model the login's routing resolves the review class to when the plan
   is compiled (profile layers included), the alternatives are taken from the models
   after it in `routing/policies/availability.json`'s order for
   `code-review` (ADR-055 rule 7), in that order, each inside the
   review-grade set and an upstream model under rule 1, and the entry
   names nothing else; each still needs its check under rule 2. On a
   provider whose selectors are composite (OpenRouter's model@preset), the
   entry names each alternative with the shim its live check used.
5. **A served divert is named.** A review any of whose requests a model
   other than its routed one answered is a divert: `fabric-review` reads
   the models that answered from the review's transcript (the response
   names its model, gateway ADR-004 rule 17) and the posted review names
   each. Where the pull request's policy requires another engine beside
   the Claude review, a divert is what ADR-055 rule 3 refuses: the review
   posts as not run, and the pull request waits, as for an unavailable
   model. No plan carries `failover` on the review's route before that
   reading is built.
6. **Schema 2 only when it is used.** A plan with no `failover` is written
   as today, byte for byte. A plan with one is schema 2, written only when
   the gateway binary in use lists 2 in `plan_schemas`; otherwise the
   compiler writes the plan without `failover` and says which routes lost
   it.
7. **The Codex review declares none.** Its plan (`build_responses`)
   carries no `failover`: whether that engine diverts stays its run's
   decision under ADR-055 rule 3, never the gateway's.
8. **Lint holds the file.** Every key is a model the provider column
   routes; every alternative is unique, not the key, at most three, inside
   the provider, and names an existing live check; rule 4's order holds
   for the review's model. The compiler refuses to write an alternative
   whose backend or credential profile is not the route's own: nothing in
   the gateway would. The gateway's own refusals (a candidate twice,
   a cap over its ceiling) stay the gateway's.
9. **The gateway decides the rest.** Which failure moves a request, the
   health thresholds and times, and the failure class a further attempt
   admits are the gateway's (gateway ADR-006, ADR-007); this record adds
   nothing a plan could say about them.

## 6. Consequences

- A capacity spell on a model with an entry no longer fails every request
  of the sessions riding it: the gateway sets the model aside and serves
  from the next, and comes back on its own probe.
- A session may be answered by a model it was not launched on, for as long
  as the gateway's health keeps its own aside. The harness still believes
  its launched model; the response and the transcript name the one that
  served.
- The review may divert without a run choosing to, under rule 3's
  conditions only, and says so on the review.
- Each pair costs a live check before it is admitted, and again when either
  model changes. Until the first entry lands, no generated plan carries
  `failover`, as today.
- On OpenRouter an alternative may be priced differently; that is in the
  entry's author's view when it is checked.
- How often an alternative served reaches people through the gateway's log
  events only; carrying it to the control plane beside ADR-055 rule 4's
  report is not built.

## 7. Future Evolution

Another endpoint of the same account serving the same model, if one
appears, would be an alternative with no model change, taken first; it
needs this record amended, rules 1, 4 and 8 and §2 at least, since
today an alternative is a later model on the route's own backend. Widening the failure class a further attempt follows is the
gateway's. If the gateway's log shows a model set aside for long, the
owner notice of ADR-055 rule 6 may read it.

## 8. Decision Status

Proposed. The owner chose, in the coordinator's session, that
failover between models is decided for every route, session and review
included, over declaring none or only on routes no session or review uses.
Until rule 5 is built, the review's route carries nothing, and with it
the default session's, which shares it; when it does, it takes only the
review order's successors. Any other route carries nothing until the
first check of rule 2 for its model lands. ADR-002 needs no amendment: a
session's model fixed at exec is the harness's, which keeps it; the
gateway answering from another is this record's.

What waits on acceptance: the file, its lint and the compiler change
(rules 1, 3, 6, 8), the review's reading of the models that answered
(rule 5), and the first live check with its entry (rule 2). Two live
checks rule 5 rests on: a review-subagent transcript records each
response's model on the anthropic column (seen on a recent review,
not yet on the gateway path), and how OpenRouter's response
spells the model against the composite selector (not yet read).

## References

- ADR-002 (a session's model fixed at exec), ADR-005 (routing), ADR-052
  (the account switch), ADR-053 (the second review engine), ADR-055 (model
  availability, rules 1, 3, 4, 7 and §7).
- agent-fabric-gateway ADR-004 rule 17, ADR-006 §2.7, §8 and rules 15, 16,
  18, 20, ADR-007 §2.3, §2.4, §2.7 and §8, and
  `architecture/contracts/plan-v0/README.md` "Schema 2".
- `tools/fabric/gateway_plan.py`, `routing/capabilities.json`,
  `routing/policies/availability.json`, `routing/policies/review-grade.json`,
  `policies/arming.json`.
