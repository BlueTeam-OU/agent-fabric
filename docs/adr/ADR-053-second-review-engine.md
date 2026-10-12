# ADR-053 — A second review engine: Codex reviews beside the review class, one-shot, through the gateway

**Date:** 2026-10-11
**Status:** Accepted
**Ratified:** owner, 2026-10-12, in the session ("adr 053 accepted")
**Decision Makers:** the owner; drafted by fabric-coordinator
**Scope:** the review class's engines (ADR-005, ADR-020); `fabric-review --engine codex` (`tools/fabric/review_codex.py`, to be built); the arming policy's `reviews` rule (`identities/schemas/arming.schema.json`, `policies/arming.json`); the Codex pin in `projects/registry.json`; the launcher's Codex profile; the review-brief skill
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
   minutes by default). The scratch is removed on every path, a timeout
   or failure included, and the working copy is never touched.
3. **Its own gateway, never the session's credential.** Codex's base URL
   is the root of a gateway process serving `openai-responses`, and its
   key is that gateway's local key, passed by environment variable only.
   The session's Anthropic base URL and key never reach Codex; the
   account's `~/.codex` is never read. Missing either setting refuses,
   posting nothing.
4. **The answer is structured or nothing.** Codex answers with one JSON
   object of findings (level P1-P3, file, line, scenario, expected,
   fix). Anything else is a failed review: nothing is posted and the
   reason is said. A posted review names the engine and model on its
   first line and is posted with `fabric-pr post-review <PR> --model
   codex`.
5. **Findings are judged the same way.** A Codex finding is judged by the
   review class before it is answered (ADR-020), and answered like any
   other: fixed, or declined with the reason.
6. **The arming policy says which PRs need both engines.** The policy's
   `reviews` rule lists the engines a PR needs: `["claude"]` by default;
   a repository may require `["claude", "codex"]` for every PR or for a
   class (the security boundary first). `fabric-pr arm` refuses until
   each required engine has reviewed the current head with no open P1 or
   P2, and the refusal names the engine still missing.
7. **The Codex CLI is pinned.** `projects/registry.json` pins the latest
   stable release by version and checksum, as every account tool is
   pinned, and `fabric-tools` installs it.

## 6. Consequences

- A PR that needs both engines takes two reviews; the second is a child
  process, not a session, so its cost is the ChatGPT subscription's
  window, read by the gateway's usage operation.
- Until the launcher's Codex profile starts the Responses gateway, the
  engine refuses on every account; the `reviews` rule stays `["claude"]`
  everywhere until then.
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
