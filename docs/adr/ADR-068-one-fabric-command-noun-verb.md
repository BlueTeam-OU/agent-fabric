# ADR-068 — One `fabric <noun> <verb>` command, driven by commands.json

**Date:** 2026-11-09
**Status:** Proposed
**Decision Makers:** the owner; drafted by fabric-coordinator
**Scope:** the `fabric` command (`bin/fabric` and the module it forwards to), the table in `runtime/claude-code/commands.json` it reads, the permission rules `runtime/claude-code/user-settings.py` writes for it, how a hook or guard recognises a fabric command in a Bash line, and the order in which skills and docs move to the new form. Not what any command does, which stays in its own record; not the existing binaries, which stay
**Pillar:** P1

## 1. Context and Problem

The external architecture review of 2026-11-08 (ADR-067 §1) counted 53
executables in `bin/`, each a top-level command with its own name:
`fabric-jobs`, `fabric-pr`, `fabric-reflect-jobs`, `gzcoord-inbox`,
`gzmsg`. Read against `origin/main` at 5b831166 on 2026-11-09:

- 46 of them are in `commands.json` `commands`, linked into
  `~/.local/bin` by bootstrap and given a `Bash(<name> *)` allow rule by
  `user-settings.py`, except the eight in `not_allowed` (`fabric-lease`,
  `fabric-secret-run`, `fabric-host`, `fabric-sign`, `fabric-genimage`,
  `fabric-resume`, `fabric-watch`, `gzcoord-carrier`), whose reasons
  are beside them. The other seven (`fabric-op`, `fabric-managed`,
  `fabric-pause`, `fabric-errors`, `fabric-drain-due`,
  `fabric-review-calibration`, `fabric-websearch-locale`) are run by
  path, by a unit, a hook or the operator.
- Nothing groups them. A session learns each name from the skill or the
  brief that mentions it; `fabric-memory-check` and `fabric-memory-mcp`,
  or `fabric-repo-policy` and `fabric-repo-settings`, are related only by
  spelling, and there is no one place that answers "what can I run".
- Several are already one command with verbs: `fabric-pr`
  (ADR-040 §5 rule 7), `fabric-jobs`, `fabric-ctl`, `fabric-review`.
  Their verb tables live in their modules, as ADR-040 rule 1 requires.
- Two hooks decide by a command's name in the Bash line:
  `post-review-shape-guard.py` (`fabric-pr\s+post-review`) and
  `job-copy-guard.py` (`fabric-pr <verb>`). `gzcoord-inbox` finds a
  running watch by the basename of its process's arguments
  (`inbox_parts/session.py`). A second spelling of the same command that
  these do not recognise would walk past them.

The review's remedy was one command with nouns and verbs. Its risk is
the last point: renaming the front door of a guarded command is a guard
bypass unless the guards move first.

## 2. Decision

One command, `fabric <noun> [<verb>] [args…]`, resolves its first one
or two words through a table in `commands.json` to one of today's
commands and replaces itself with it (`exec`), passing the remaining
arguments unchanged. `fabric jobs add X` runs exactly what `fabric-jobs
add X` runs; `fabric memory check` runs `fabric-memory-check`;
`fabric gzcoord inbox` runs `gzcoord-inbox`. Every existing binary stays
where it is and keeps working: it is the implementation, and its name is
a supported spelling.

The first table is mechanical, derived from today's names, so that the
dispatcher changes no behaviour and decides no naming. A permission rule
for a `fabric` form is never broader than the rule for the command it
reaches, and every hook that recognises a fabric command by name
recognises both spellings through one owning function before the
dispatcher is on any account's `PATH`. Skills, docs and the
auto-mode prose move to the new form only after the dispatcher has
landed and been read back on every account.

## 3. Alternatives Considered

- **Rename the binaries and leave wrappers under the old names.** It
  moves 53 contracts at once — the units, hooks, settings and MCP
  registrations that run them by path — for a gain that is only the
  spelling. The dispatcher gets the grouping with none of that.
- **A second table beside `commands.json`.** Two lists of the fabric's
  commands, one for linking and allow rules and one for dispatch, would
  drift; that is the duplicate ADR-067 exists to prevent. The table
  goes into the file that already holds the list.
- **A dispatcher that imports the modules instead of exec'ing the
  binaries.** Faster by one exec, but every module's start-up (the pin
  check, ignored signals passed on, `sys.argv[0]`) would have a second
  entry path to keep identical. Exec'ing the binary keeps one.
- **One allow rule, `Bash(fabric *)`.** It would allow `fabric lease`,
  `fabric secret-run` and `fabric host run`, each refused an allow rule
  today because it runs any command.
- **Teach each guard the new spelling as it comes up.** That is how a
  guard is bypassed: the spelling exists before the guard knows it.
- **Rename for clarity in the same change** (`fabric secrets run` for
  `fabric-secret-run`). Renames are decisions about meaning, each with
  its own readers; mixing them into the dispatcher makes it impossible
  to review the dispatcher as behaviour-preserving.

## 4. Rationale

The cost of the current layout is discovery and grouping, not
execution, so the fix is a front door, not a rewrite. Exec keeps the
process a guard or a watch looks for identical to today's, which is why
`inbox_parts/session.py` needs no change. Driving the table from
`commands.json` keeps one list for linking, allowing and dispatching,
and makes "every session-facing command has exactly one `fabric` form"
checkable by lint. Deriving permission rules from the table, rather than
writing them by hand, keeps the asymmetry that matters: a form is
allowed only where its target is. Moving the guards in the same pull
request as the dispatcher, and the docs only after distribution,
orders the change so that no session is told of a spelling a guard
does not know.

## 5. Binding Rules

1. `bin/fabric` is a forwarder (ADR-040 §5 rule 1) to one module under
   `tools/fabric/cli/`. The module reads `commands.json`, resolves the
   noun and verb, and replaces its process with the target's
   `bin/<command>` in the same checkout (`os.execv`, never a child
   process and never a `PATH` lookup), with `argv[0]` that path and
   every argument after the resolved words passed unchanged.
2. The table is a `fabric` section of `commands.json`. Each noun names
   either its own command, or verbs each naming a command, or both. A
   word after the noun is a table verb only if the noun lists it;
   otherwise it and every argument after it go to the noun's own
   command, whose verb table stays in its module. A noun without its own
   command refuses an unlisted verb.
3. The table covers exactly the commands in `commands.json` `commands`,
   each reached by one form; a binary outside `commands` gets no form
   and stays reached by path. Lint refuses a table that names a command
   not in `commands`, reaches one twice, misses one, or lists a verb
   that the noun's own command also takes as a verb.
4. The first table is mechanical: the noun is the name without its
   `fabric-` prefix; a remainder `X-Y` becomes noun `X` and verb `Y`
   only where `X` is itself a command or the first part of another
   (`fabric memory check`, `fabric repo policy`, `fabric reflect jobs`,
   `fabric review mcp`), and stays one noun otherwise
   (`fabric secret-run`, `fabric gh-ledger`). The `gzcoord-` commands
   are the noun `gzcoord`, and `gzmsg` is `fabric gzcoord msg`. A
   rename later is an amendment of this record, and the earlier form
   stays in the table as an alias of the new one.
5. Before the noun only `help` and `--help` are accepted; any other
   option there is refused, so a permission rule's prefix always starts
   at the noun. Bare `fabric`, `fabric help` and `fabric <noun> help`
   for a noun without its own command print the table's forms. An
   unknown noun or verb exits 2 with that listing on stderr; a target
   missing from the checkout exits 127.
6. `user-settings.py` derives the `fabric` rules from the table and
   `not_allowed`, and never writes `Bash(fabric *)`:
   - a noun whose own command is allowed gets `Bash(fabric <noun> *)`,
     plus an ask rule `Bash(fabric <noun> <verb> *)` for each listed
     verb whose command is in `not_allowed`;
   - a noun without its own command gets `Bash(fabric <noun> <verb> *)`
     for each listed verb whose command is allowed;
   - a noun whose own command is in `not_allowed` gets no allow rule;
   - bare `fabric` and `fabric help` get an exact allow rule each.

   A form is granted under the same link check as its target today: only
   where `~/.local/bin/fabric` is the fabric's own `bin/fabric`. `fabric`
   itself is in `not_allowed`, with that reason.
7. A hook or guard that recognises a fabric command in a Bash line does
   so through one function in `tools/fabric/cli/`, which reads both
   spellings to the canonical `<command> <args…>`; no hook keeps its own
   pattern for a command's name. This is a mechanism in ADR-067's sense:
   it enters `policies/mechanisms.json` with its owner and a checker in
   the pull request that adds the dispatcher, and every such hook has a
   test that its decision is the same for both spellings.
8. The dispatcher, the table, the rules of rule 6 and the hooks'
   adoption of rule 7 land in one pull request. `commands.json` gains
   the `fabric` command (so bootstrap links it) in that pull request and
   in no earlier one.
9. No skill, brief, charter, remit, `AGENTS.md`, `CLAUDE.md`, hook
   message or `policies/auto-mode.json` entry tells a session to use a
   `fabric` form until that pull request is merged, distributed to every
   account (`fabric-ctl all upgrade fabric`) and read back on one account
   in each permission mode: an allowed form runs without asking, a
   `not_allowed` target's form asks. The read-back is a live check under
   `docs/live-checks/`. The rewrite that follows changes
   `auto-mode.json` in the same pull request as the first text that names
   the new form.
10. The existing binaries stay, under their names and paths, with no
    retirement date. Retiring one is a new decision, not an amendment of
    this rule.

## 6. Consequences

- **What gets easier.** One command to discover from: `fabric help`
  lists everything a session may run, grouped. Related commands read as
  related. Lint knows when a command was added without a form.
- **What gets harder.** Two spellings exist for every session-facing
  command, indefinitely. A hook that recognises a command must go
  through the owning function, which is one more import than a regex.
- **What it costs.** A dispatcher module and its tests, a table in
  `commands.json`, a rule generator in `user-settings.py`, the two guard
  hooks moved onto the function, a checker for the new mechanism, one
  live check, and then the docs rewrite, which touches most skills.
- **Unchanged.** Every unit, MCP registration, hook and git setting
  that runs a binary by path. The process a watch or guard sees.

## 7. Future Evolution

- Renames (`secret-run` under `secrets`, a home for `whoami` and
  `status`) are amendments under rule 4, each keeping its alias.
- Shell completion for `fabric`, read from the same table, is a natural
  next step and needs no decision.
- The dispatcher is harness-neutral and its table is not: it sits in
  the Claude Code adapter's `commands.json`. When ADR-054's Codex
  adapter (`runtime/codex/`, not built) needs the same list, the
  command list and its table move to a harness-neutral home that both
  adapters read; that move is an amendment.
- If every account and every text has used only the `fabric` form for
  a long while, retiring the old names can be proposed under rule 10.

## 8. Decision Status

Proposed. Nothing is built. The dispatcher and its tests are contracted
to a python-dev holder; the table, the rule generator, the hooks'
adoption and the mechanism's catalogue entry are fabric-coordinator's
(`runtime/claude-code/`, `policies/`), supplied as commits onto that pull
request (rule 8). The docs rewrite (rule 9) is fabric-coordinator's,
after distribution.

## References

- ADR-018 — `runtime/claude-code/` and `policies/` are fabric-coordinator's; the contributor entries.
- ADR-040 — §5 rule 1, the forwarder; rule 7, `fabric-pr` as one command with verbs.
- ADR-051 — `also_allowed` and `also_asked`, the prefix rules for one tool's subcommands.
- ADR-054 — the harness is an adapter; the Codex adapter, not yet built.
- ADR-067 — one owning module per mechanism; the catalogue rule 7 enters.
- `runtime/claude-code/commands.json`, `runtime/claude-code/user-settings.py`, `runtime/claude-code/hooks/post-review-shape-guard.py`, `runtime/claude-code/hooks/job-copy-guard.py`, `tools/fabric/gzcoord/inbox_parts/session.py`.
