# ADR-053 — A second review engine: Codex reviews beside the review class, one-shot, through the gateway

**Date:** 2026-10-11
**Status:** Accepted
**Ratified:** owner, 2026-10-12, in the session ("adr 053 accepted")
**Decision Makers:** the owner; drafted by fabric-coordinator
**Scope:** the review class's engines (ADR-005, ADR-020); `fabric-review --engine codex` (`tools/fabric/review_codex.py`); the arming policy's `reviews` rule (`identities/schemas/arming.schema.json`, `policies/arming.json`); the Codex pin in `projects/registry.json`; the launcher's Codex profile; the review-brief skill
**Pillar:** P1

## 1. Context and Problem

Every pull request in the fleet is reviewed by one engine: the review
class, a Claude model in a Claude Code subagent (ADR-020). The author's
session and the reviewer share a vendor, a harness and much of a
training distribution, so the blind spots they share are the ones no
review finds. The fleet once had a second, contrarian reviewer and lost
it. The owner wants it back, from another vendor: OpenAI's Codex on a
ChatGPT subscription, the latest stable Codex CLI pinned, its credential
held the way Claude's is (the gateway holds it, the controller refreshes
it).

The gateway's Stage 6 makes this possible: it serves the OpenAI
Responses protocol, one protocol per gateway process, and a Codex
harness points its base URL at the gateway's root. A live run of Codex
0.162.1 against a root base URL sent `POST /responses` on every request.

## 2. Decision

Codex is a second review engine, run one-shot: `fabric-review --engine
codex <PR>` renders the same blind brief the review class gets, runs the
pinned `codex exec` read-only on an extract of the PR's head, through a
gateway process of its own that serves the Responses protocol, and posts
its findings in the review class's shape, counted by `fabric-pr
review-status` beside the Claude review. Which PRs need both engines is
the repository's arming policy (`reviews`), checked by `fabric-pr arm`.

## 3. Alternatives Considered

- **A resident second harness** (a Codex session per agent, or a
  reviewer login running Codex). It doubles the sessions to supervise
  and their credentials, for a job that is one process per review. A
  dedicated reviewer login stays open if reviews become a fleet service.
- **Routing the review class's subagent to an OpenAI model.** It needs a
  bridge from the Anthropic protocol to Responses (gateway ADR-003 rule
  3), which no stage builds yet, and it keeps Claude Code's harness, so
  the second opinion would differ in model only, not in harness.
- **The account's own Codex login.** It puts a ChatGPT credential in
  every reviewing account's `~/.codex`, outside the gateway that holds
  and refreshes every other credential.

## 4. Rationale

One-shot keeps the cost to a child process per review, under the
reviewing login, with nothing resident. Going through the gateway keeps
one place for credentials, usage readings and the account policy
(ADR-052). The same brief and the same posting path mean the two
reviews are compared like for like. Today `fabric-pr arm` checks a review
of the head only for security-boundary changes and for every PR on a
direct repository, so rule 6 adds a gate that
counts engines and requires a review of the head for every PR in a
repository whose policy names `reviews`.

## 5. Binding Rules

1. **The brief is the review class's.** `fabric-review --engine codex`
   renders the brief with `review_brief.py`, unchanged: facts, never the
   author's conclusions (ADR-020). The engine adds only the shape of its
   answer.
2. **One process, read-only, on an extract.** Codex runs once per review
   as a child of the reviewing session, in a scratch extract of the head
   (`git archive`), with its sandbox read-only and a time budget (20
   minutes by default). Before the run the engine proves the sandbox:
   Codex's own `codex sandbox` must start read-only on the extract and
   refuse a write there; a sandbox that does not start or lets the write
   through is a failed review (A 2026-10-13). The scratch is removed on
   every path, a timeout or failure included, and the working copy is
   never touched.
3. **Its own gateway, never the session's credential.** Codex's base URL
   is the root of a gateway process serving `openai-responses`, and its
   key is that gateway's local key, passed by environment variable only.
   The session's Anthropic base URL and key never reach Codex; the
   account's `~/.codex` is never read. Missing either setting refuses,
   posting nothing. Codex's own network features (`plugins`,
   `remote_plugin`, `plugin_sharing`, `apps`, `in_app_updates`) are off
   in the engine's configuration, so the gateway is the only place it
   connects to (A 2026-10-13).
4. **The answer is structured or nothing.** Codex answers with one JSON
   object of findings (level P1-P3, file, line, scenario, expected,
   fix). Anything else is a failed review: nothing is posted and the
   reason is said. A posted review names the engine and model on its
   first line and is posted with `fabric-pr post-review <PR> --model
   codex`.
5. **Findings are judged the same way, once per head.** A Codex finding
   is judged by the review class before it is answered (ADR-020), and
   answered like any other: fixed, or declined with the reason. Judging
   is one dispatch per head covering every open finding of both
   engines, each answered by number; never one dispatch per finding.
6. **A review is required; the policy names who reviews.** A pull
   request is armed only when every required review engine its arming
   policy names has reviewed the current head with no open P1 or P2. Which
   engines is policy data, never this record: `reviews`, and
   `boundary_reviews` for a security-boundary change, in
   `policies/arming.json` for the fleet and in a repository's own
   policy, whose list replaces the fleet's. The review class's review is
   always required (ADR-020). The one exception is ADR-054 rule 10's: for
   a pull request whose every work commit was written in a Codex
   session, `codex` in the lists is read as `claude`, since Codex does
   not review its own harness's work. An engine listed under
   `additional_reviews` reviews when it can and never blocks: its review
   of the head, or its unavailable marker for that head, satisfies it
   (ADR-055 rule 8; the fleet lists codex there). `fabric-pr arm` refuses
   until each required engine has reviewed, and the refusal names the
   engine still missing (A 2026-10-13). An additional engine with
   neither its review nor its marker on the head is absent: the arm
   proceeds on the required reviews and says so, and the gate reads the
   same.
7. **The Codex CLI is pinned.** `projects/registry.json` pins the latest
   stable release by version and checksum, as every account tool is
   pinned, and `fabric-tools` installs it.
8. **One sign-in, an access token per login.** The ChatGPT sign-in the
   engine runs on is the coordinator's, in its own home; its refresh
   token never leaves it. Every other login gets the access token and
   the account id only: the coordinator writes them into each login's
   store (ADR-038, as ADR-031 writes Claude tokens), and `fabric-secrets
   sync` puts them in a token file on the login's runtime tmpfs (0600),
   which the review gateway reads on every attempt. The coordinator's
   control agent refreshes the sign-in when under 72 hours of the access
   token remain and writes the new one to every login. A login whose
   token is missing or expired refuses the review, naming the expiry,
   and posts nothing. The gateway-local key between Codex and its
   gateway identifies the calling component; it guards no secret
   (A 2026-10-13).

## 6. Consequences

- A PR that needs both engines takes two reviews; the second is a child
  process, not a session, so its cost is the ChatGPT subscription's
  window, read by the gateway's usage operation.
- Every required engine the policy names must be reachable for a pull
  request to arm: when one is not (its subscription at capacity, its
  token expired), the pull request waits; there is no stand-in for a
  missing review. An additional engine is satisfied by its review of the
  head or its unavailable marker for that head (ADR-055 rule 8)
  (A 2026-10-13).
- Two engines can disagree. The review class judges each finding, so a
  disagreement is resolved the way any finding is, never by vote.

## 7. Future Evolution

A dedicated reviewer login if reviews become a fleet service; other
engines through the same rule once the gateway serves their protocol; a
bridge (gateway Stage 9) if the review class itself should run on a
second vendor's model.

## 8. Decision Status

Accepted (the header names the owner's word). It waits in practice on the
gateway's Stage 6 (the Responses gateway and the ChatGPT credential
held by the gateway) and the launcher's Codex profile.

## References

- ADR-005 (models are routed by capability class), ADR-020 (the review
  class is the review), ADR-052 (the account-switch policy).
- The gateway's Stage 6 plan and its plan contract, Schema 1 (BlueTeam-OU/agent-fabric-gateway).
- `tools/fabric/review_brief.py`, `bin/fabric-review`, `fabric-pr arm` (`tools/fabric/github/arm.py`), `tools/fabric/github/arm_policy.py`.

## Amendments

The body above reads current; each change's full note is in [history/ADR-053-amendments.md](history/ADR-053-amendments.md).

| Date | Amendment | Effect |
|---|---|---|
| 2026-10-13 | the sandbox proven before the run; Codex's own fetches off | §5 rules 2 and 3 |
| 2026-10-13 | every login runs the Codex review on a synced access token; both engines by default | §5 rule 6 changed, rule 8 added |
| 2026-10-13 | the record requires a review, policy names the engines; the fleet requires both | §5 rule 6 |
| 2026-10-13 | An additional engine counts by its review or its unavailable marker | §5 rule 6: additional_reviews; the fleet's codex is additional (ADR-055 rule 8) |
| 2026-10-14 | Findings are judged once per head | §5 rule 5: one judging dispatch per head for every open finding of both engines |
