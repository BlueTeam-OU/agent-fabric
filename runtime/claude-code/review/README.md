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

````markdown
```agent-fabric-dispatch v1
{
  "dispatch_id": "6f1c2a3e-0b7d-4c55-9a52-1d2e3f4a5b6c",
  "parent_session_id": "…",
  "job_id": null,
  "project": "gzapp",
  "repository": "github.com/BlueTeam-OU/gzapp",
  "pr": null,
  "review_id": null,
  "review_round": 1,
  "purpose": "primary-review",
  "engine": "claude",
  "evidence_mode": "pinned",
  "base_sha": "…",
  "head_sha": "…",
  "card_base": "…",
  "config": "…",
  "started_at": "2026-10-14T10:00:00Z"
}
```
# Review brief (agent-fabric review brief v1)
## Mode
review
## Repository
/home/user/projects/gzapp (the live clone; read-only for you)
Evidence: pinned. Read the range's commits through git (git show <sha>:path, git diff, git log); the files on disk may be a different state.
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
## Project review card
(none)
## Lenses
### general
…
### protocol
…
````

Every heading is rendered, an empty one as `(none stated)`: a field the
dispatcher forgot is visible to the reviewer, never silently gone. An
unknown key is refused (`invariant:` → "did you mean invariants?").

**Machine lines.** A claude review's brief ends with `## Report lines`, the
mode's rule for the `Finding:` and `Judgement:` lines `fabric-errors`
reads (ADR-061); the constitution quotes the same shapes. Codex is not asked
for them: `review_codex.render_review` writes its `Finding:` lines from the
structured answer (confidence `likely`, since the answer carries none). The
shapes, vocabularies and writers are `tools/fabric/review_lines.py`, and
`tests/test_review_lines.py` feeds each writer's text to the reader.

**Wrong and right, side by side.** Objective is one line about the
*system*, in the present tense — not about the change:

| wrong (a verdict) | right (a fact) |
|---|---|
| The executor correctly abstracts the host. | The coordinator can operate an account on a host it is not on. |
| This fixes the PATH reset on Debian. | A command run as the account finds the tools the worker put on PATH, on Fedora and on Debian. |
| I think the dangerous part is the retry. | A retry after a dropped connection converges; nothing is done twice. |

**A re-review** carries `mode: re-review` and the range of the *fix
commits only*. For a PR (`pr` set) the range must start at the head of
the PR's last posted v2 review, every path read, and the previous report
is that review's posted body, read by the renderer: a typed
`previous_findings` or `card_base` that disagrees is refused, and so is
a diff file, which names no commits to look it up against; no such
review means a full review (agent-fabric ADR-065 §5 rule 5). Without a
PR, `previous_findings: <the previous report, a file>` is given as
before. The
constitution then starts from those hunks and findings, answering by
number, and widens only to establish the fix's semantics or to detect a
regression, saying what it widened to and why. A re-review carries only the lenses it names — `general`
included: it verifies, it does not explore — so one that names none pays
for no lens text.

Derive it rather than edit it: `bin/fabric-review save <PR> <round> <
report` keeps a round's report under this account's state, and
`bin/fabric-review next REQUEST --pr <PR>` writes `REQUEST-rr<N>.json`
from the previous request (mode, the range from its head to `HEAD`, that
report as `previous_findings` when the request names no PR, `general` alone unless `--keep-lenses`)
and renders it, with the new head's worktree; it refuses when the head has not moved
(`tools/fabric/review_rounds.py`). The rendered re-review also embeds the
range's exact diff (up to 64 KB, else its `--stat` and a note) and
Locators: each previous finding's file:line at the old head and the same
region at the new, and each hunk's enclosing symbol. They are derived at
render time and are not written into `REQUEST-rr<N>.json`.

**The project review card.** The reviewer runs without the project's
instruction files (`omitClaudeMd`); `.agent-fabric/review-card.md` (at
most 2048 bytes, refused over) is rendered under `## Project review
card`, `(none)` when the file is absent.

*The card is the base's, never the head's* (agent-fabric ADR-020). It is
read as `git show <base_sha>:.agent-fabric/review-card.md`, where the
base is the range's left end (a symbolic base resolves as a head does,
to the commit it names now), and never from the working tree or the
head: a change under review must not write its own rules of review. The
renderer refuses, naming the base, a base that is not an ancestor of the
default branch (the registry's `default_branch`, else origin's HEAD, else
`main`; the remote-tracking ref where there is one). A PR that changes
the card is therefore reviewed under the base's card, with the card's own
diff in the reviewed range as evidence. A re-review's range starts at
the previous head, which the default branch does not contain, so
`review_rounds.py next` writes the first round's base into the request
as `card_base`, and the card is read there. A first base that is not a
commit id (`origin/main`) is refused unless the request pins `card_base`
(round 1's dispatch header names it as `base_sha`).

**The dispatch header.** The brief's first block is a fenced
`agent-fabric-dispatch v1` JSON object: `dispatch_id` (minted at render),
`parent_session_id`, `job_id` (the request's, else fabric-jobs' active
job), `project`, `repository`, `pr`, `review_id`, `review_round`,
`purpose` (from `mode`: `primary-review`, `re-review`,
`finding-adjudication`; the second engine writes `second-engine-review`
itself), `engine`, `evidence_mode`, `base_sha`, `head_sha`, `card_base`
(the commit the card was read at), `config` (sha256 of the review
class's agent file, that card and the renderer's versions: what a
re-review compares before it starts from an earlier head, agent-fabric
ADR-065 §2 C), `started_at`.
The request takes `pr` and `job_id` as optional fields (and `review_id`,
`review_round`, which `review_rounds.py next` fills: the id is kept, else
`<repository>#<PR>`, and the round is the previous one plus one). A brief
without the block is attributed `inferred` by the cost hook.

**The evidence mode.** `evidence: pinned | working-tree` (default
`pinned` for a range, `working-tree` for a diff file) is named in the
header and in a line under `## Repository`. `pinned`: the reviewer reads
the range's commits through git; `working-tree`: it reads the files on
disk. A pinned request with a range also gets a **head worktree**:
`brief` and `next` run `git worktree add --detach` of the range's head at
`<TMPDIR>/fabric-review/<repository basename>-<head12>` (the directory
0700; detached, so no branch or `branch.*` config lands in the clone), reuse
it when it is already a worktree at that head and refuse any other thing
at the path, and the Evidence line names the path; the reviewer reads and
runs there and makes no extract of its own (the earlier practice left
19-74 MB extracts behind, agent-fabric ADR-020's history). `render()`
itself makes nothing: the path is passed in. `fabric-review save` removes
the round's worktree, recomputing the path from the report header's
`head_sha`, and only when it is a worktree at that head; a working-tree or
diff-file request makes none, and `check` makes none. The review class
makes no scratch directory: a check's `/tmp` is the sandbox's own and goes
with it (agent-fabric ADR-065 §2 B). The reviewer opens its report with the brief's header, copied
unchanged, so the mode travels with the report: `fabric-pr post-review`
refuses a report whose header says `working-tree` (only a pinned review
covers a head) and records the review on the header's `head_sha`, the
commit it read, never the PR's head at posting time (agent-fabric
ADR-020 §5 rule 6). A report without the v2 header (`base_sha`,
`head_sha`, `card_base`, `config`) and a coverage block naming every path
of its range is refused (ADR-065 §5 rule 4), Codex's included, and `fabric-review save` records each round's mode in
`round-<N>.json` beside `round-<N>.md` (`null` when the report has no
header). A re-review request carries `evidence` over from the previous
one.

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

## The second engine

`bin/fabric-review --engine codex <PR> REQUEST` renders the same brief and
runs it once through the pinned `codex exec`, read-only, on an extract of
the PR's head, then posts the findings with `fabric-pr post-review <PR>
--model codex --head <the head it read>`. It is not a subagent dispatch: the guard and the dispatch
shape above do not apply, and the Claude review still has to be dispatched.
A finding it posts is judged by the review class like any other. Which
engines a pull request needs is the arming policy's `reviews`
(`policies/arming.json`); the engine and its settings are in
`tools/fabric/review_codex.py`, its answer schema in
`runtime/claude-code/review/codex-answer.schema.json` (agent-fabric ADR-053).

Codex reaches its model through a gateway of its own (ADR-053 rule 3),
given one of two ways:

- `--gateway chatgpt [--codex-home DIR]`: the review starts one for itself
  and stops it before posting (`tools/fabric/review_gateway.py`). It reads
  the ChatGPT sign-in in `DIR/auth.json`, by default `~/.codex-chatgpt`
  (never `~/.codex`, and not the session's `CODEX_HOME`), and refuses when
  its access token has under 30 minutes left, or under the review's time
  budget when that is longer: refresh it with `CODEX_HOME=DIR codex exec`
  once, or sign in again. The installed gateway must list plan schema 1
  and the `openai-responses` protocol in `--version --json`, or it is
  refused by name before anything starts. The access token goes into a
  0600 file in a 0700 directory under `$XDG_RUNTIME_DIR`, which the
  schema-1 plan (`gateway_plan.build_responses`: the ChatGPT backend
  `https://chatgpt.com/backend-api/codex`, one identity route for the
  model) names and the gateway reads on each attempt; the directory is
  removed when the review ends, however it ends. Codex gets the gateway's
  root and local key, and the sign-in's account id as the provider's
  `ChatGPT-Account-ID` header in its `config.toml`; never the token.
- without `--gateway`: from the environment, `AGENT_FABRIC_CODEX_BASE_URL`
  and `AGENT_FABRIC_CODEX_KEY`, with `AGENT_FABRIC_CODEX_ACCOUNT_ID` as the
  optional header.

The model and its reasoning level are routed, like the review class's
(ADR-005, ADR-006): the `openai` provider in `routing/capabilities.json`,
whose one class is `code-review` — `gpt-6.1-sol`, the owner's decision of
2026-10-12 — merged with the login's layers as `fabric-model list
--provider openai` shows them, and admitted by
`routing/policies/review-grade.json` as `openai/gpt-6.1-sol`; its level
is `routing/effort.json`'s `providers.openai` — `high`, chosen for the
contrarian reviewer where the review class asks `medium`, and because
Codex's own default on the ChatGPT plan was `none` — sent as
`-c model_reasoning_effort="high"`. `python3 tools/fabric/routing.py
resolve code-review --provider openai` prints the model, and
`fabric-status` prints the column as its `review engine` line. A routing
answer that cannot be read, or a routed model outside the review grade,
refuses before anything runs.

`--model` or `AGENT_FABRIC_CODEX_MODEL` names another model for one run,
and `--effort` or `AGENT_FABRIC_CODEX_EFFORT` another level (`none`,
`minimal`, `low`, `medium`, `high`, `xhigh`). Without them, the routed
level is sent on `--gateway chatgpt`, the backend the column was decided
for; the environment's gateway gets a level only when one is asked for
(review of #224, F2). The posted review's first line names the model that
ran and the level sent.

A review is posted only from a run that read the code. Codex runs with
`--json`, and its event stream must show no `error` item (Codex's "Model
metadata for X not found" included: the routed model is in its catalog), no failed turn,
at least one command that completed with exit code 0, and a final agent
message that is the schema's answer; anything else is a failed review,
nothing posted, the reason said. A missing tool host is named as such:
Codex runs every tool call through `codex-code-mode-host` beside its own
executable, and installed as `bin/codex` alone it ran no command and
answered `{"findings": []}` from the brief, which was posted as a clean
review (2026-10-12). `fabric-tools --install codex` installs the pinned
tarball's vendor tree under `~/.local/lib/agent-fabric-tools/codex/<version>/`,
with `~/.local/bin/codex` a link to it (`tools/fabric/tools_install.py`).
Tests: `tests/test_review_codex.py`, `tests/test_review_gateway.py`.

## Who enforces what

| guarantee | how |
|---|---|
| the reviewer starts without the parent's conversation or reasoning | Claude Code: a subagent's context is fresh (its agent file + environment + CLAUDE.md + the prompt) — a harness property, read back in `docs/live-checks/` |
| the dispatch shape, the model (routing's pin, review-grade gated), no worktree | structurally: the dispatch guard, `install-agent-files.sh`, `runtime/openrouter/launch`, and their tests |
| the reviewer cannot write, change git state or install | structurally: the agent file's `tools:` allow-list (no Bash, no writing tool), the fabric-review server's fixed-argv git tools and its proved read-only sandbox (ADR-065), `subagent-clone-guard.sh` |
| the brief carries facts, not conclusions | a dispatcher convention with two fences: the renderer's rationale lint before the dispatch, the reviewer's verdict rule after it — never a hook on prompt text (`policies/subagent-dispatch/SKILL.md`) |
| a named lens reaches the reviewer | rendered inline; the reviewer lists the lenses it applied under *Brief notes* |
| charter fields never become routing | the renderer emits Markdown only; routing reads `routing/` and `aliases.json` |

Tests: `tests/test_review_brief.py` (the constitution's frontmatter and
cap; the renderer, every refusal, the rationale lint, the re-review form,
this README's example rendered and compared); the lens lint in
`tools/fabric/lint.py`.
