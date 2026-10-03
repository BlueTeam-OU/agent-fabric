# A review has three parts

| part | what it is | where it lives | who writes it |
|---|---|---|---|
| **constitution** | the reviewer's stable reasoning discipline — method, evidence rules, the shape of a finding, the report | `runtime/claude-code/agents/code-review.md` — the subagent's whole system prompt (a Claude Code subagent gets its agent file, not the harness prompt, and none of the parent conversation) | fabric-coordinator |
| **charter** | the facts of one change: mode, repository, range, what must be true, what is out of scope, which lenses | the dispatch `prompt`, rendered by `bin/fabric-review brief` from a request file under fixed headings | the dispatching session |
| **lens** | where to look first and what usually goes wrong there | `lenses/<name>.md`; the directory is the vocabulary (`bin/fabric-review lenses`); `general` is always on for a review | fabric-coordinator |

Blindness removes anchoring, not facts. The charter says **what must be
true**; it never says whether or how the change makes it true — that is
the author's conclusion, and a reviewer told why the code is right agrees
with it. `bin/fabric-review brief` refuses a verdict-shaped sentence
("correctly", "fixes", "ensures", "the bug was", "I think") and names it;
`--allow-rationale` renders it flagged under *Brief notes*, where the
constitution's verdict rule tells the reviewer to set it aside and say so.

## The request

```yaml
mode: review                       # review | re-review
repository: /home/user/projects/gzapp
range: origin/main..HEAD           # or diff: <a diff file in the scratchpad>
objective: >-
  Passenger itineraries are computed in the engine's clock, never the host's.
requirements:
  - "An itinerary's times are the engine's (ADR-058 §3)."
  - "A malformed engine response is an error, never an empty itinerary."
invariants:
  - "Nothing under apps/passenger_flutter/ interprets a time zone."
compatibility:
  - "Contracts 1.1.0 clients keep working."
threat_model: []
scope: [apps/backend_dotnet/src/Gzapp.PassengerApi/Transit/]
out_of_scope: ["the OTP image bump in the same PR (#746, reviewed)"]
lenses: [protocol]
```

`bin/fabric-review brief request.yaml` renders:

```markdown
# Review brief (agent-fabric review brief v1)
## Mode
review
## Repository
/home/user/projects/gzapp (the live clone; read-only for you)
## Range
origin/main..HEAD
## Objective
Passenger itineraries are computed in the engine's clock, never the host's.
## Requirements
- An itinerary's times are the engine's (ADR-058 §3).
- A malformed engine response is an error, never an empty itinerary.
## Invariants
- Nothing under apps/passenger_flutter/ interprets a time zone.
## Compatibility
- Contracts 1.1.0 clients keep working.
## Threat model
(none stated)
## Scope
- apps/backend_dotnet/src/Gzapp.PassengerApi/Transit/
## Out of scope
- the OTP image bump in the same PR (#746, reviewed)
## Lenses
### general
…
### protocol
…
```

Every heading is rendered, an empty one as `(none stated)`: a field the
dispatcher forgot is visible to the reviewer, never silently gone. An
unknown key is refused (`invariant:` → "did you mean invariants?").

**Wrong and right, side by side.** Objective is one line about the
*system*, in the present tense — not about the change:

| wrong (a verdict) | right (a fact) |
|---|---|
| The executor correctly abstracts the host. | The coordinator can operate an account on a host it is not on. |
| This fixes the PATH reset on Debian. | A command run as the account finds the tools the worker put on PATH, on Fedora and on Debian. |
| I think the dangerous part is the retry. | A retry after a dropped connection converges; nothing is done twice. |

**A re-review** carries `mode: re-review`, the range of the *fix commits
only*, and `previous_findings: <the previous report, a file>`; the
constitution then verifies only the new hunks against those findings, by
number. A re-review carries only the lenses it names — `general`
included: it verifies, it does not explore — so one that names none pays
for no lens text.

Derive it rather than edit it: `bin/fabric-review save <PR> <round> <
report` keeps a round's report under this account's state, and
`bin/fabric-review next REQUEST --pr <PR>` writes `REQUEST-rr<N>.json`
from the previous request (mode, the range from its head to `HEAD`, that
report as `previous_findings`, `general` alone unless `--keep-lenses`)
and renders it; it refuses when the head has not moved
(`tools/fabric/review_rounds.py`).

## The dispatch

```
Agent(subagent_type: "code-review", model: "fable",
      description: "Review <what>"  /  "Re-review <what>",
      prompt: <the rendered brief, verbatim>)        — and NO isolation
```

`runtime/claude-code/hooks/agent-dispatch-guard.sh` admits exactly that
shape and never reads the prompt; the rendered brief changes nothing about
what may be dispatched, only what the reviewer is told. One reviewer per
PR. A hand-written prose brief remains valid — the constitution takes the
range and treats the rest as facts only where they are facts.

## Who enforces what

| guarantee | how |
|---|---|
| the reviewer starts without the parent's conversation or reasoning | Claude Code: a subagent's context is fresh (its agent file + environment + CLAUDE.md + the prompt) — a harness property, read back in `docs/live-checks/` |
| the dispatch shape, the model (routing's pin, review-grade gated), no worktree | structurally: the dispatch guard, `install-agent-files.sh`, `runtime/openrouter/launch`, and their tests |
| the reviewer cannot write, change git state or install | structurally: the agent file's `tools:` allow-list, `review-bash-guard.sh`, `subagent-clone-guard.sh` |
| the brief carries facts, not conclusions | a dispatcher convention with two fences: the renderer's rationale lint before the dispatch, the reviewer's verdict rule after it — never a hook on prompt text (`policies/subagent-dispatch/SKILL.md`) |
| a named lens reaches the reviewer | rendered inline; the reviewer lists the lenses it applied under *Brief notes* |
| charter fields never become routing | the renderer emits Markdown only; routing reads `routing/` and `aliases.json` |

Tests: `tests/test_review_brief.py` (the constitution's frontmatter and
cap; the renderer, every refusal, the rationale lint, the re-review form,
this README's example rendered and compared); the lens lint in
`tools/fabric/lint.py`.
