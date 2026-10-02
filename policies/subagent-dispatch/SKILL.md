---
name: subagent-dispatch
description: "Why every writing subagent dispatch in this repo pins `model` and `isolation: \"worktree\"`, why the REVIEW CLASS (code-review, description beginning review/re-review, fable, NO isolation) is a standing authorisation the dispatch guard enforces rather than asks about, what the PreToolUse hook cannot see (a Workflow script's agent() calls), how worktree isolation actually behaves — what an agent sees, what survives, and why collection is a copy — and the review brief (base..head, revert test, quoted hunks, pre-existing section, re-review scoped to new hunks). Load it before dispatching agents or writing a Workflow script, when an agent reports files that \"do not exist\", when a worktree or worktree-agent branch is left behind, or when tempted to merge an agent's branch."
---

# Why dispatch looks like this

The root `CLAUDE.md` §Subagent dispatch and §Concurrent contributors
carry the rules. This file carries the incidents — each rule was written
after one, and the rule reads as ceremony until you know which.

## Dispatch is opt-in, and that is deliberate

The isolation machinery below makes fan-out *safe*; it does not make it
*wanted*. The user opts in per task when they judge the parallelism
worth its cost. A task that looks parallelisable is not an invitation,
and this was re-opened as a "gap" more than once — it is not one.

One standing exception exists, named in the root file, and it is
review: the review class — the blind review of a PR's head, the
judgement of a finding before it is answered (step 26 of the canonical
lifecycle, added after two findings were dismissed by hand in a row and
both dismissals were wrong), and the re-review of a fix range. It is
the review the project's review-status tooling (`pr-review-status.sh`,
the fabric's, reached through the project's `tools/gh/` forwarder)
counts. Nothing else.

## The `model` field — the ~40-agent bill

Omitting `model` is not a neutral default: the agent **inherits the
session model**. A fold once dispatched a wave of roughly forty agents
with the field unset, from a session running a premium model — every
one of them ran premium, for work that was mostly mechanical. Fan-out multiplies the per-agent cost by the count, so the
tier decision is where the bill is actually made:

| class (`subagent_type`) | alias (`model`) | for |
|---|---|---|
| `code-low` | `haiku` | mechanical, well-specified work: pattern-following edits, extraction, formatting, single-file lookups, structured search |
| `code-medium` | `sonnet` | judgement work: multi-file reasoning, prose that must hold a convention |
| `code-high` | `opus` | only on the user's explicit instruction for that dispatch (the guard asks) |
| `code-plan` | `fable` | planning and design reasoning on the top tier; the guard asks, as for `code-high` |
| `code-review` | `fable` | the review class; shares the tier with `code-plan` but never its export — its model reaches its agent file; see below |

**The class decides the tier, and the call says both.** The binding is
`runtime/claude-code/aliases.json` — the same file the broker launcher
exports from — and the dispatch guard denies a class dispatch whose
`model` is not that class's alias, unset included. Both fields, because
they do different jobs: the class is the vocabulary a repository's
instructions can use without naming a model; the alias is what the
harness resolves and what a launch binds per session. A class whose
tier a call could override would be a label — `code-high` on `sonnet`
is high-consequence work on the cheap tier with nothing saying so — and
a guard that inferred the alias from the class would move a routing
decision into a hook that cannot read `routing/`.

Pinning the tier on every call is also what keeps a campaign
reproducible: if the session model changes while a batch is in flight,
unset-field agents change with it. The hook denies an unset `model`, a
class on the wrong alias, and prompts on a premium one.

### Review is the standing premium-alias exception (`fable`)

One role escapes the premium ban without a per-dispatch ask: the
**review class**, dispatched for the review of a PR's head, for judging
a finding (step 26) and for the re-review of a fix range. It stands in
for nothing: no automated reviewer runs ahead of it, and its review,
posted with `post-review.sh`, is the one the gate counts.

**`fable` is a tier alias, and the target is agent-fabric's routing.**
The Agent tool's `model` field accepts ONLY the four harness aliases —
not a full Claude model id, not a provider-qualified vendor model — so a
dispatch literally cannot name a model. The mapping lives in agent-fabric, not in
settings: `routing/capabilities.json` binds each capability class
(`code-low`, `code-medium`, `code-high`, `code-plan`, `code-review`) to a
concrete model per provider, `routing/shims.json` binds a model family
to its compatibility shim, and `runtime/openrouter/launch` resolves this
agent's layers in `routing/profiles.json` (by role, by login, and the
login's own `model-profile.local.json` — `fabric-model`), refuses a
review model outside `routing/policies/review-grade.json`, and exports
`ANTHROPIC_DEFAULT_{OPUS,SONNET,HAIKU,FABLE}_MODEL` before the exec —
process env, which every subagent inherits — on the broker and on plain
`claude` alike. The review class rides `fable` with `code-plan`, and one
alias carries one export, so its model is NOT the fable export (through
it the reviewer would follow code-plan, as it once followed code-high on
`opus`: a reviewer dispatched on `opus` on the broker path once ran on
the cheap tier's model); it is written into the reviewer's agent file at launch, for
that launch's provider, and the guard drops the dispatch's alias under a
fabric launch so the file decides. The Agent tool accepts only the tier
aliases, so a full model id cannot be named at dispatch.
`modelOverrides` is NOT used: it is taken as the whole map from the
highest-precedence scope that sets it, so any scope both launch paths
share binds both, and it would beat the env pins anyway. The vanilla
`claude` launch stays Anthropic by construction. Committed settings
scopes carry no pins at all (guarded by
`check_repo_settings_carry_no_model_pins.sh`). The tier mechanisms on
OpenRouter: `openrouter/pareto-code` + a dashboard-default
`min_coding_score` is a quality tier (cheapest model above the bar —
the phase-2 opus target), `~vendor/family-latest` is a stable family
alias, `:floor` and `provider.sort: "price"` tune cost within one
model. Verified against the broker's docs and live catalog when the
launcher and registry shipped (`docs/live-checks/`).

The tier table above optimises for cost because, for ordinary work, a
cheaper agent that does the job is strictly better. Review inverts
that. The deliverable IS the quality of the read — there is no output
to inspect afterwards, only findings that either exist or do not — and
a reviewer that misses a defect produces a confident "looks fine" that
is worse than no review, because it manufactures assurance. The cost
of the miss lands in production; the cost of the tier is a few cents.

The scale of the miss is not hypothetical. On the strict-OTP-boundary
branch, four rounds of review found seven real defects, and two of
those rounds found defects introduced by the previous round's own fix.
Every one had passed a full green suite and mutation checks first. That
is the failure rate the review class is being asked to match.

It covers review only. "This task looks hard" is not review, and the
exception must not be read as a general licence — the ~40-agent bill
above is what happens when premium becomes the default rather than the
argued case.

#### The exception is a NAMED CLASS, not a promise to behave

For a while the root file declared the exception and then added "the
hook still prompts", which put the decision back in front of the person
at the keyboard on every review — a standing exception that still asks
is not one, and the ask arrived at the least useful moment, mid-review-
loop.

So the carve-out is structural, and it is a CLASS with four conditions,
enforced by `.claude/agent-dispatch-guard.sh` (the `PreToolUse` hook for
`Agent`; decision table in `tests/test_agent_dispatch_guard_cli.py`):

1. `subagent_type: "code-review"` — a file in the repo
   (`.claude/agents/code-review.md`), reviewable like any other,
   whose charter is review-only;
2. `description` that BEGINS with `review` or `re-review`;
3. `model: "fable"` — the review class's alias, checked and then, under
   a fabric launch, removed so the agent file's pinned model applies;
4. **no `isolation`** at all.

All four, or the dispatch is **denied** — never asked. These were
learned one at a time, and each was load-bearing on its own:

- **The model condition was missing when this first shipped.** Keyed on
  the type alone, the branch returned before the premium check for ANY
  model — `code-review` with any alias skipped the prompt while the
  rule authorised one alias only. The same hole runs the other way: a
  `sonnet` review would take the exemption and evade the rule beside
  it. So the class REQUIRES its one alias, and denies anything else
  rather than asking: a review is not a retryable step, its failure
  mode is a green PR that merges, and "this review looks small" is
  exactly the moment a different tier is tempting and wrong. Which
  alias: `fable`, not `opus` — code-high rides `opus`, and one alias is
  one export, so a reviewer on `opus` is code-high's model. What the
  reviewer runs on is `code-review` in `routing/capabilities.json` (or a
  profile layer), gated by `routing/policies/review-grade.json`
  (architect-cto's decision, not the dispatcher's), through its agent
  file — never the `fable` export, which is `code-plan`'s.
- **The description prefix** stops a writing dispatch from wearing the
  review type. Another project's guard matched `review` ANYWHERE in the
  description and let "Address review feedback" through — a writing
  task that then ran unisolated in the session clone, because the
  review class has no worktree. `^(re-)?review\b` is a condition that
  can only NARROW the exemption; it is not a substitute for the type,
  and it is not the prompt-sniffing hole warned about below.
- **No worktree.** Isolation exists to keep an agent's WRITES out of
  the clone; a review writes nothing. It also actively hurts:
  `worktree.baseRef` is `head`, so a reviewer inside a worktree cannot
  see uncommitted work at all — precisely the work you most want read
  before it is committed. The reviewer runs in the clone, told in its
  brief that the tree is read-only and it runs no git writes — and,
  because a promise is not a fence and this clone auto-allows `git
  push`, an agent-scoped `PreToolUse` hook in the definition
  (`runtime/claude-code/hooks/review-bash-guard.sh`, tested by its
  sibling; installed user-scope by `bootstrap.sh`, or a project's own
  `.claude/` copy) denies
  state-changing git and every install/restore for that agent only.

Keyed on the TYPE, deliberately, and not on prompt text alone. A hook
that GRANTED the exemption on review-ish words would be a string match
any dispatch could satisfy by phrasing, which is not an exception — it
is a hole. A named type is a file; the prefix only removes cases from
what the type would otherwise allow.

Two properties of the guard matter and are pinned by the test file:

- The review branch sits INSIDE the type check, so a `code-review`
  dispatch missing the prefix, the model or carrying an isolation is
  **denied** with a reason naming which; and a general agent whose
  description begins with `review` is denied too — reviews use the
  class.
- It is the ONLY type that passes without a prompt; `general-purpose`
  with `opus` or `fable` still asks exactly as before, and every
  writing agent still needs `model` and `isolation: "worktree"`.
- The read-only harness types — `Explore`, `Plan`, `claude-code-guide`
  — need `model` and must NOT set isolation: they have no writing tool,
  the clone guard fences their Bash in the session clone, and a
  worktree (`baseRef: head`) would hide the uncommitted work a search
  is usually about. Before this exemption every Explore dispatch of a
  planning session was denied and the research done by hand.

Pass `model: "opus"` explicitly anyway, even though the agent
definition's frontmatter already pins it: the class REQUIRES that value
and every dispatch in this repo names its tier.

### The review brief

Three parts, kept apart (`runtime/claude-code/review/README.md`): the
reviewer's **constitution** is its agent file — the method, the revert
test, the quoted hunk, the bounded re-review, the shape of a finding
all live there and nowhere else; the **charter** is what the DISPATCH
carries — the facts of this change; a **lens** is a named bias
(`fabric-review lenses`). The charter is where independence is won
or lost, so it is rendered, not improvised:

1. Write a request in the scratchpad: `mode`, `repository`, `range`
   (or `diff`), `objective` — one line, what must be true of the
   system — `requirements`, `invariants`, `compatibility`,
   `threat_model`, `scope`, `out_of_scope`, `lenses`. Every field is a
   FACT: what must be true. Never how the change makes it true, what
   was fixed, or where you suspect the defect — a reviewer told why the
   code is right agrees with it, and the whole value is that it does
   not know. `fabric-review brief request.yaml` refuses a
   verdict-shaped sentence and names it; rephrase as what must be true
   (`--allow-rationale` renders it flagged, for the rare fact that
   reads like a verdict).
2. Paste the rendered brief into `prompt`, verbatim. Not the plan, not
   the rationale, not the implementation transcript, not another
   reviewer's conclusions.
3. **One agent per PR**, on the exact `base..head` (or a diff file in
   the scratchpad when the range is not yet pushed).
4. **A re-review** is `mode: re-review`, the range of the fix commits
   only, and `previous_findings:` — the previous report, a file. The
   constitution verifies only the new hunks against those findings, by
   number; leaving the bound out once cost another project ~50k tokens
   per comment-only commit and manufactured the next round's findings.
   The description begins `re-review` so the guard and the agent both
   know which mode this is.

The renderer is ergonomics and a lint, not authorisation: the dispatch
guard decides from four fields of the call and never reads the prompt
(above — a hook that judged prompt text would be a hole). A prose brief
written by hand is still admitted; the constitution takes its range and
treats the rest as facts only where they are facts.

### The reviewer reads history; it changes nothing

§Concurrent contributors says a subagent runs no state-changing git, and
that is about worktree and commit hygiene — not about reading. A
reviewer needs `git log`: step 26 asks for a verdict *with evidence* and
names it first, because whether a defect was introduced by the change
under review or was already there decides who fixes it and when.

This was learned the expensive way. The charter originally said "run no
git at all", and an adjudicating reviewer duly reported that it "could
not determine" whether a finding was pre-existing — the exact question
it had been dispatched to answer. Read-only git is now explicit in the
agent definition.

### The locale worker (language-culture logins only)

`locale-worker` is not a class: it is the language-culture bridge's
subagent (`docs/adr/ADR-027-language-and-culture-shape-the-work-the-bridge.md`), whose agent file exists
only on a login of that role (`install-agent-files.sh` writes and
removes it). The guard's branch for it sits before the review-
description branch — reviewing a text in the locale is its job — and
asks: a model set (any alias, no ask: language judgement is premium by
design), no isolation (its one inert tool writes nothing). Read back
live: an empty `tools:` inherits every tool and the harness refuses an
agent with none, so the file says `tools: TaskStop`.

## What the hook cannot see: `Workflow` scripts

The `PreToolUse` hook matches the tool name `Agent`. A `Workflow`
script's agents are created by `agent(prompt, opts)` inside the script,
and never reach it. Both fields are optional in that API and both
default the wrong way — `model` inherits the session, `isolation` runs
in the session's clone — and a workflow can be dozens of agents in one
call, so the forty-agent failure above recurs multiplied. No hook can close
this at dispatch: `Workflow`'s tool input is the script *text*, so any
guard there would be string-matching rather than a structural check.
The rule in the root file is the only place it exists.

What can be closed is the write itself. `subagent-clone-guard.sh`
(`runtime/claude-code/hooks/`, matched on `Write|Edit|MultiEdit|
NotebookEdit|Bash`) denies a class subagent — the three classes, the
reviewer, and the harness built-ins a class-less call names — whose
`cwd` is the session clone rather than a path under
`.claude/worktrees/`, and gives its Bash the review fence. A dispatch
the guard above never saw still cannot edit the tree it should not be
in; it can only report. The main session, a fork and an unknown type
are untouched; whether a Workflow-spawned agent's tool calls carry the
`agent_id` / `agent_type` / `cwd` fields the guard reads has not been
observed live, and absent fields allow — it fails open there, not
closed. Tested by `test_subagent-clone-guard.sh`.

## Isolation — what an agent actually sees

Every WRITING dispatch runs in its own worktree under `.claude/worktrees/`. Four
things about that were learned by probing, not by reading docs:

- **`worktree.baseRef` defaults to `fresh`, which branches from
  `origin/<default-branch>`.** Two agents dispatched to extend a
  decision record and its source found neither, because the unmerged
  task branch was invisible to them; a probe reproduced it unchanged. This repo pins `"baseRef": "head"` in
  `.claude/settings.json`, and a re-probe confirmed the agent then sees
  the full branch. Check it before diagnosing a "blind" agent.
- **`head` means the committed HEAD.** Verified, and re-verified with a cheap-tier probe (untracked file and unstaged edit both absent inside the worktree): an untracked
  file and an unstaged edit to a tracked file both came back MISSING
  from the agent's view. An agent asked to extend uncommitted work
  silently reads the previous version and reports success against it.
  Each worktree also branches at *dispatch* time, so a wave sent either
  side of a commit is not one snapshot.
- **A worktree the agent CHANGED survives.** The harness auto-removes
  only an unchanged worktree, so every productive dispatch leaves a
  worktree plus a `worktree-agent-<id>` branch for the session to remove.
  `.claude/worktrees/` sits inside the repo and each entry holds a `.git`
  file; without the gitignore, `git add -A` staged one as an embedded
  repository and committed a broken gitlink.
- **Parallel worktree creation from one non-main branch is safe** —
  verified with eight simultaneous adds, each with an
  independent `HEAD`, index and tree. This is why the old "no builds in
  parallel" demand is gone: build artifacts were the shared state that
  disjoint source paths did not protect, and a worktree has its own.

## Collection is a copy, not a merge

Isolation removed the index race that first motivated "only the session
commits" — separate worktrees have separate indexes — but not the
reason: authorship and commit shape are the session's to own. An agent
committing in its own worktree produces commits on a throwaway branch
that nothing should merge, and merging `worktree-agent-<id>` back would
put history in `main` the session did not author.

So the session reads what the agent produced, applies it in the clone,
and commits there. That is also why **writes are partitioned by file
set** in every prompt: two agents that both rewrite `foo.ts` hand the
session two divergent versions and no merge. Reads overlap freely.
