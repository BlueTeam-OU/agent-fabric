# ADR-063 — fabric-ctl assist: the owner's questions on the claude-pzhuy API key

**Date:** 2026-10-22
**Status:** Proposed
**Decision Makers:** the owner; drafted by fabric-coordinator
**Scope:** `fabric-ctl assist "<question>"`, the module that implements it, the `CLAUDE_APIKEY_CLAUDE_PZHUY_8ALIAS_COM` entry in the host operator's store, and every other path by which that key could be spent
**Pillar:** P5

## 1. Context and Problem

The fleet stops whole when its subscription accounts run out of allowance,
or when a blocker takes down the relay or the control agents. That is
exactly when the owner most needs to ask how the fabric works — "how can I
switch to the claude-pzhuy account?" — and exactly when no agent can
answer: every session rides a subscription token, and `fabric-ctl` asks
control agents that may be down.

Two Claude accounts carry API keys beside their setup-tokens, stored since
2026-10-12 as `CLAUDE_APIKEY_<SLUG>` in the store of the host operator's
login (`runtime/hosts/registry.json` `hosts.develop-qzapp.operator`, which
is also the login fabric-coordinator runs as). They are not templates:
`fabric-secrets store templates` reads only `CLAUDE_ACCOUNT_*`, so
`fabric-accounts assign` never pushes a key to another login. On 2026-10-14
the claude-pzhuy key was refused with "credit balance is too low" while the
Console showed $199.44 of promotional credit; after a $20 top-up the same
probe answered HTTP 200. The promotional credit expires 2026-10-23; what is
left after that is the top-up, a small reserve.

Nothing spends either key today, and nothing says who may. A key that any
session of the operator's login can read is one script away from becoming
a fleet's fallback, and $20 at API rates is minutes of an agent and hours
of questions.

## 2. Decision

`fabric-ctl assist "<question>"` answers the owner's question about the
fabric from the fabric's own committed text, in one request to the
Anthropic Messages API on the claude-pzhuy account's API key. It is that
key's only spend path. It runs only from an interactive terminal of the
host operator's login outside any agent session, and it needs nothing of
the running fleet: no relay, no control agent, no subscription token,
only a checkout of agent-fabric, the operator's store and the network path
to the API. It answers; it never runs anything.

## 3. Alternatives Considered

- **`claude -p` on the key**: the harness brings tools, settings, hooks
  and a session record, all of which assume a launched agent; the
  launcher refuses a session without a setup-token (ADR-031), and a
  harness that can run commands is the wrong shape for advice. One
  stdlib HTTPS request has none of it.
- **Answering through a control agent** (`fabric-ctl <login> ask`): the
  case it serves is the fleet down; a path through agentd fails with it.
- **Search without a model** (`fabric-adr lookup`, grep): exists, and
  stays the first thing to try; the owner asked for a question answered
  in words, with the command it needs.
- **Agents may ask too**: they read the tree themselves, which costs no
  key, and a key every session can spend is the reserve gone in a day.
- **The other account's key** (`CLAUDE_APIKEY_ANDREA_BENETTON_BLUETEAM_GE`)
  as a fallback: two keys double what a mistake can spend, and its credit
  is the owner's to allocate separately. One key, named in one place.
- **A model chosen per call** (`--model`): the class is routing's
  (ADR-005); a flag is how a cheap question turns into a top-tier bill.

## 4. Rationale

The rule is about the budget, not about who is asking. The key's credit
is the owner's out-of-band reserve for a stopped fleet; a person on the
team would be held to the same rule, and an agent session needs the key
for nothing it cannot do by reading the tree. The refusal of an agent
session is therefore a fence against accident, like the other guards: a
session of the operator's login can unset its environment, and the record
does not pretend otherwise. What makes a mistake small is the shape — one
request, a bounded context, a bounded answer, a log of every spend.

Grounding on committed text keeps answers to commands that exist, and
reading only committed files is what lets assist work with everything else
stopped. The answer cannot see the fleet's state, and says so rather than
guessing it.

## 5. Binding Rules

1. **One key, one path.** `CLAUDE_APIKEY_CLAUDE_PZHUY_8ALIAS_COM` is spent
   only by `fabric-ctl assist`. The account slug is a single constant in
   the assist module, citing this record; a second spender, or another key
   for assist, is an amendment of this record. No launcher, `fabric-accounts`
   path, profile or agent file reads a `CLAUDE_APIKEY_*` entry.
2. **The owner's terminal only.** Assist refuses, before reading the store
   and with a reason on stderr and exit status 2: a process with any of
   `CLAUDECODE`, `CLAUDE_CODE_ENTRYPOINT`, `AGENT_FABRIC_LAUNCH_AGENT` or a
   `CODEX_` variable in its environment; standard input or standard output
   not a terminal; a login that is not its host's `operator` in
   `runtime/hosts/registry.json`. Each refusal has a test that also shows
   no request was attempted.
3. **Works with the fleet down.** Assist imports nothing of agentd, the
   relay, GZCoord or the launcher, and reads no runtime binding. It reads
   the key from the store in-process (`tools/fabric/secretstore`); the key
   never enters an environment variable, an argument, a file or a log.
   Python standard library only (ADR-040).
4. **The model is a class.** Assist asks the `code-medium` class, resolved
   at call time from the `anthropic` provider of
   `routing/capabilities.json`; it takes no model option.
5. **Grounded and bounded.** The request carries, in this order and cut
   from the end to 48 KiB: `fabric-ctl`'s verb table and each verb's
   `--help`; the DIGEST's lookup table; the DIGEST entries `fabric-adr
   lookup` returns for the question's words; each skill's name and
   description; the bodies of at most two skills whose description best
   matches the question. Selection is word overlap, deterministic, no
   index or embedding. The answer is capped at 2,048 output tokens.
6. **Advice, never action.** One request, no tools, no conversation state.
   The system prompt tells the model to answer only from the supplied
   text, to quote commands exactly as the text writes them, to cite the
   record, skill or verb each step comes from, to say when the text does
   not answer, and never to assert the fleet's current state. Assist
   prints the answer and executes nothing in it.
7. **Every spend is recorded.** Each request appends one JSON line to
   `${XDG_STATE_HOME:-~/.local/state}/agent-fabric/agents/<login>/assist.jsonl`:
   UTC time, model id, HTTP status, input and output tokens from the
   response's `usage`. Never the question, the answer or the key.
   `fabric-ctl assist --spend` prints the totals; it sends no request.
8. **Failures are said, not retried around.** "credit balance is too low"
   is reported as the account out of API credit, with the Console as the
   remedy; 401 as the key invalid or rotated, naming the store command
   that replaces it; 429 and 529 follow ADR-055's retries (10, 20, 60
   seconds) and then report. No fallback to another key or account.
9. **`assist` is a reserved first word.** `fabric-ctl assist` takes the
   verb where other verbs take a login; no login may be named `assist`,
   and the account-creation path refuses it.

## 6. Consequences

- The owner has an answer when the fleet cannot give one, at the cost of
  a few cents a question, and a record of what it cost.
- The key stays in the store it is in today; nothing is moved or
  re-issued. Its credit is spent by one command the owner types.
- A question asked with the promotional credit expired and the top-up
  spent fails with a clear message, and the owner tops up or stops.
- Assist's answers are as good as the committed text: a gap it reports is
  a gap in the docs, worth a job.

## 7. Future Evolution

- Built after `fabric-ctl`'s per-verb help (#355) lands, which rule 5
  grounds on: a REQUEST to python-dev with this record's rules as the
  acceptance, the refusal tests of rule 2 first.
- If answers prove too thin, the grounding grows by rule 5's budget, not
  by tools. A follow-up question (a conversation) would be an amendment.
- If the fleet gains a non-subscription path of its own (ADR-036's broker
  spend), this key stays the owner's reserve and is not that path.

## 8. Decision Status

Proposed; waits on the owner's acceptance. Nothing is built yet: the
implementation waits on #355 and on this record.

## References

- ADR-005 (capability classes), ADR-012 and ADR-038 (secrets and the
  store), ADR-029 (`fabric-ctl` and the control agent), ADR-031 (Claude
  accounts and setup-tokens), ADR-036 (spend per key), ADR-040 (stdlib
  Python), ADR-044 (the operator login), ADR-055 (capacity retries).
- `tools/fabric/secretstore/accounts.py` (`templates()` reads only
  `CLAUDE_ACCOUNT_*`), `runtime/hosts/registry.json` (`operator`),
  `routing/capabilities.json`, `bin/fabric-ctl`.
- BlueTeam-OU/agent-fabric#355 (per-verb help and the verb table).
