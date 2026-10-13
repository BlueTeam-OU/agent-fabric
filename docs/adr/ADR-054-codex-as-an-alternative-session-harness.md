# ADR-054 — Codex as an alternative session harness: AGENTS.md is the instruction file, a harness is an adapter

**Date:** 2026-10-13
**Status:** Accepted
**Ratified:** owner, 2026-10-13, in the session ("accept it")
**Decision Makers:** the owner; drafted by fabric-coordinator
**Scope:** the repository's instruction file (`AGENTS.md`, `CLAUDE.md`) and the workspace template (`runtime/claude-code/workspace/CLAUDE.md`); a harness adapter beside `runtime/claude-code/` (`runtime/codex/`, to be built); the launcher's harness choice and the binding that records it (`identities/schemas/binding.schema.json`); the guards' Codex wiring; the `openai` provider's coding classes (`routing/capabilities.json`, `routing/effort.json`); the ChatGPT credential path through the gateway
**Pillar:** P1

## 1. Context and Problem

Every working session in the fleet runs on Claude Code, on two Claude
subscriptions. When their weekly windows ran out on 2026-10-12 the whole
fleet stopped: the API keys had no usable credit, and nothing else could
run a session. One engine is one failure (ADR-034).

Codex is already in the fleet, as a reviewer only (ADR-053): the pinned
CLI (0.162.1) installed on every account as its whole vendor tree
(`projects/registry.json`, #229), a ChatGPT team sign-in, the gateway's
Responses listener (0.3.0), and an `openai` routing provider bound to
`code-review` alone. Its first review that read the code (#230's range,
2026-10-13) found four defects the review class had passed twice. The
second engine pays for itself in review; this record asks whether it can
also run a session.

What stands between Codex and a session is everything the fabric gives a
Claude Code session that is written *for* Claude Code:

- **Instructions.** The fabric's rules live in `CLAUDE.md`, and the
  workspace layer in `projects/CLAUDE.md`, above every git root. Codex
  reads `AGENTS.md`, from the git root down to the working directory;
  it never reads either file.
- **The launch.** Role, charter, brief, team and memory ride in the
  system prompt by `--append-system-prompt-file` (ADR-002 §5 rules 4–5);
  the project remit arrives from the SessionStart hook. The launcher
  knows one harness.
- **Guards.** The dispatch guard, the review guards, the self-kill guard,
  the pipe-status guard, the PR-count and inbox-watch stop hooks are
  Claude Code hooks in managed settings (ADR-043). The git hooks and CI
  cover commits and pull requests for any harness; nothing covers a
  Codex session's tool calls.
- **Credentials.** Only the coordinator's login is signed in to ChatGPT
  (`~/.codex-chatgpt`); the workspace has device codes disabled, so a
  sign-in per login means a browser per login. ADR-053 rule 8 gives
  every login the access token for reviews instead; a session needs it
  through its own gateway.
- **Routing.** The `openai` provider refuses a coding class on purpose
  (`routing.py check`): no harness existed to run one.

Codex 0.162.1 offers the seams these need. Read from the installed
binary on 2026-10-13, not yet exercised (rule 9): the `hooks` feature is
stable and on, with events named PreToolUse, PostToolUse, SessionStart,
UserPromptSubmit, Stop and SubagentStop; `developer_instructions` and
`model_instructions_file` are configuration keys;
`project_doc_fallback_filenames` and `AGENTS.override.md` are read;
skills, MCP servers and `multi_agent` subagents are stable.

## 2. Decision

Codex becomes a second session harness beside Claude Code, chosen per
login at bind time and fixed for the session, as a role is. It is built
in the order of §8, and no login launches on it until every guard that
applies to its role has a Codex wiring or a recorded reason it needs
none.

The repository's instruction file becomes `AGENTS.md`, the name every
harness but Claude Code reads: `git mv CLAUDE.md AGENTS.md`, keeping its
history, holding what is true for any harness; `CLAUDE.md` becomes
`@AGENTS.md` and the Claude Code section — subagent classes and aliases,
skills, hooks — after it. A Claude session reads what it reads today.

A harness is an adapter: `runtime/claude-code/` is the first, and
`runtime/codex/` the second. Each turns the same rendered launch prompt,
the same routing and the same guards into its harness's own form. What
the fabric decides is harness-neutral; how a harness is told is the
adapter's.

## 3. Alternatives Considered

**Keep Codex review-only.** The fleet stays one subscription family for
every session; the outage of §1 recurs whenever both Claude
windows close together. Lost on ADR-034.

**Codex reads `CLAUDE.md` through `project_doc_fallback_filenames`.**
No file moves, but the Claude-only half of the file — the Agent tool,
`subagent_type`, the tier aliases — reaches a harness that has none of
it, and every other harness still finds no `AGENTS.md`. The rename is
the portable answer; the fallback stays a stopgap if piece 1 slips.

**`AGENT.md`, singular.** An early proposal for the same file; the name
the harnesses converged on, and the one Codex's binary reads, is
`AGENTS.md`.

**A sign-in per login.** `codex login` on every account: a browser per
login (device codes are off in the workspace), a refresh token in every
home, and as many devices on one seat as there are logins. The gateway
already holds the credential for the review engine; sessions take the
same path.

**A neutral harness of the fabric's own.** Everything the adapters do,
done once — and the fleet's attention moved from projects to a harness.
Two real adapters show what is common before a third is designed.

## 4. Rationale

The rename costs one reviewable pull request and changes nothing a
Claude session reads, since Claude Code imports `@AGENTS.md` inline;
everything after it is reached through it. The adapter split follows
what the fabric already does for providers (ADR-005): the vocabulary is
the fabric's, the translation is the adapter's. Gating the launch on the
guards keeps ADR-018's promise — a rule that lives only in prose is lost
the next time a session changes — true for a harness that never read
the prose. Putting the credential in the gateway keeps ADR-012 and
ADR-038's line: no login holds a secret it does not need.

## 5. Binding Rules

1. `AGENTS.md` at the repository root is agent-fabric's instruction file
   of record. It holds only what is true for every harness; anything
   that names a harness's tool, setting or alias is in that harness's
   file. `CLAUDE.md` is `@AGENTS.md` followed by the Claude Code section,
   and nothing else.
2. The workspace layer reaches every harness: the workspace template
   keeps `projects/CLAUDE.md` for Claude Code, and the Codex adapter
   puts the same text in the session's `developer_instructions`, since
   Codex reads no file above a git root.
3. A managed project's instruction file is its own (architect-cto's).
   The fabric recommends the same split and supplies the text; it moves
   no project's file.
4. A harness is chosen at bind time (`fabric-role bind <role> --harness
   claude-code|codex`, default `claude-code`), recorded in the binding,
   printed by `fabric-status`, and fixed for the session; another
   harness is a relaunch.
5. Every harness gets the same launch prompt (ADR-002): header, charter,
   brief, team and memory, rendered once; the adapter decides only how
   it is delivered. The Codex adapter appends it as developer
   instructions, never replacing Codex's own base instructions.
6. The launcher refuses a Codex session for a role while any guard in
   managed settings (ADR-043) that applies to that role has neither a
   Codex hook wiring nor a recorded reason in `runtime/codex/` that git
   hooks or CI cover what it guards. A guard is three things (ADR-018);
   its Codex wiring adds a suite case, not a fourth.
7. A Codex session's credential is the gateway's (ADR-052's path, the
   Responses listener). The session's gateway reads the same access
   token file ADR-053 rule 8 syncs to every login for reviews; the
   refresh token stays with the coordinator's one sign-in per ChatGPT
   seat. The harness holds only a gateway-local key, which identifies
   the calling component and guards no secret. The review engine
   (ADR-053) starts Codex behind the gateway by the same launcher path
   a Codex session uses, so every review exercises the session's route;
   but each component presents its own gateway-local key — the session
   one, the review engine another — so the gateway always knows which
   component is calling and can attribute what it serves
   (A 2026-10-13).
8. A coding class on the `openai` provider is bound only when a Codex
   session can run it; its model and effort are routing's
   (`routing/capabilities.json`, `routing/effort.json`, carried by `-c
   model_reasoning_effort`, ADR-006 §6). Until the subagent mapping of
   §8 piece 6 lands, a Codex session dispatches no subagents.
9. Each Codex seam this record leans on — hooks and their decisions,
   `developer_instructions`, `AGENTS.md` discovery from a subdirectory,
   the SessionStart context — is read back live before the piece that
   uses it merges (ADR-017), in `docs/live-checks/`.
10. A pull request authored on Codex is reviewed by the review class as
    THE review (ADR-020); a Codex review of it is not counted as the
    second engine's (ADR-053), since an engine does not review its own
    harness's work. Under ADR-053 rule 6 such a PR reads `codex` as
    `claude`: `fabric-pr arm` reads the harness from a `Fabric-Harness:`
    trailer the commit-msg hook stamps beside `Fabric-Role:`, and swaps
    only when every work commit names `codex`. A commit without the
    trailer is Claude Code's. The `commit-msg` hook, which reads the
    live binding, stamps the trailer and refuses a commit whose
    `Fabric-Harness:` differs from the binding's harness: the fence is at
    commit time, as for `Fabric-Role:` (`policies/AUTHORITY.md`). CI
    cannot read a binding; it checks the trailer's form only, a tripwire
    with the usual limits (text anyone can type, `--no-verify` skips the
    hook), which makes a hand-written trailer visible, not impossible.

## 6. Consequences

- A closed Claude window no longer stops the fleet: logins bound to
  Codex keep working, and the owner can move a login between harnesses
  by a rebind.
- Every other harness that reads `AGENTS.md` gets the fabric's rules for
  free; the Claude-only half no longer misleads them.
- Two adapters to keep: a launcher change, a new guard or a new
  instruction now has a Codex half, and the suite checks both.
- 127 tracked files mention `CLAUDE.md` (`git grep -l CLAUDE.md` at
  this record's commit); each either keeps meaning the Claude entry
  point or moves to `AGENTS.md` in piece 1.
- Cost becomes comparable across engines (ADR-036): verified results per
  seat, measured in the pilot, not assumed.

## 7. Future Evolution

The pilot's numbers decide how far this goes: a role per harness, a
harness per project, or Codex as the fallback the account-switch
controller (ADR-052) moves a login to when both Claude windows close.
Commit provenance — which harness, model and effort wrote a commit — is
a separate decision with the review records' own provenance gap. A third
harness reopens §3's neutral-harness alternative.

## 8. Decision Status

Accepted (the header names the owner's word). The work lands in this
order, each piece a pull request with its live check:

1. `AGENTS.md`: the rename, the split and the references (fabric-coordinator; instruction files are control plane).
2. The live check of §5 rule 9 on one login, before any adapter code.
3. `runtime/codex/`: the launcher's `--harness`, the binding field, `CODEX_HOME` and `config.toml` per login, the prompt as developer instructions, the `Fabric-Harness:` trailer stamped and fenced by the `commit-msg` hook, its form checked in CI, and `fabric-pr arm`'s reading of it (`arm_policy.required_engines`, rule 10).
4. The guards' Codex wiring and the launch gate of rule 6.
5. The session credential through the gateway (rule 7): the session gateway reads ADR-053 rule 8's token file.
6. Routing: the owner's choice of model and effort per coding class on `openai`; the subagent mapping.
7. A pilot: one login named by the owner, one role, a week, measured against a Claude login on the same kind of work.

## References

- ADR-002 (the launch prompt), ADR-005 and ADR-006 (routing and effort),
  ADR-012 and ADR-038 (secrets), ADR-017 (live checks), ADR-018 (guards),
  ADR-020 (the blind review), ADR-031 (Claude accounts), ADR-034
  (failure), ADR-036 (cost), ADR-043 (managed settings), ADR-052 (the
  account switch), ADR-053 (Codex as the second review engine).
- `projects/registry.json` (the Codex pin); `tools/fabric/review_codex.py`;
  `routing/capabilities.json` (the `openai` provider);
  `runtime/claude-code/hooks/` (the guards to wire).

## Amendments

The body above reads current; each change's full note is in [history/ADR-054-amendments.md](history/ADR-054-amendments.md).

| Date | Amendment | Effect |
|---|---|---|
| 2026-10-13 | the review engine starts Codex behind the gateway as a session will | §5 rule 7 |
