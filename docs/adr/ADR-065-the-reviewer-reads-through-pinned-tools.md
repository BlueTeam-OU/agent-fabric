# ADR-065 — The reviewer reads through pinned tools, says what it covered, and the next round starts where the last one stopped

**Date:** 2026-10-23
**Status:** Proposed
**Decision Makers:** the owner; drafted by fabric-coordinator
**Scope:** the review class's tools (`runtime/claude-code/agents/code-review.md`), a read-only review tool server beside `tools/fabric/memory_mcp/`, the checks a project lets its reviewer run, the posted review object (`tools/fabric/github/post_review.py` and its readers), the re-review range (`tools/fabric/review_brief.py` `card_base`), and the arm's reading of a review; the Codex engine (ADR-053) only where it posts through the same object
**Pillar:** P3

## 1. Context and Problem

The review class runs in the session's clone without a worktree (ADR-020,
ADR-005 §5 rule 3), with `Read, Glob, Grep, Bash`. The only fence between
the reviewer and the session's branch is `review-bash-guard.py`, a
PreToolUse hook that reads each shell command and decides whether it
could write. It is a parser of bash, written as regular expressions, and
says of itself that it is "a fence against the ROUTINE path … not a
sandbox".

Keeping that parser right has been expensive. On 2026-10-23 it is 466
lines with a 2141-line case table of 475 commands. 32 commits have
touched it or its table since 2026-08-01. Eleven of them answer review
rounds of the two pull requests that built it (#96 rounds 1–8, #97
rounds 1–4), and eleven more on 2026-10-10 alone, most of them closing
`cd` spellings one at a time (a glob, a brace, an option, a continuation,
a double-quoted word). Each round found
another way to say a forbidden thing. There is no last round: a shell has
more spellings than a pattern list.

What the reviewer needs from a shell is narrow. Its charter names it:
history (`git log`, `git show`, `git blame`, `git diff`), a search, the
range's files in full, and the project's checks run "from what is already
restored". Everything else the guard refuses.

Two neighbouring gaps share the cause, which is that a review's extent is
asserted rather than recorded:

- **"No findings" does not say what was read.** A review that ran out of
  budget on a forty-file range and a review that read all forty post the
  same body. The arm counts both (ADR-020 §5 rule 6 pins the head, not the
  coverage). `codex-empty-review-missing-tool-host` is the one case caught
  so far, by reading a log after the fact.
- **A re-review's range is typed.** `card_base` and `previous_findings` are
  request fields the dispatcher fills by hand (`review_brief.py`); a wrong
  base narrows the re-review silently. The posted review already carries
  `<!-- agent-fabric-review v1 -->` and the `head_sha` it read, but nothing
  reads that back as the start of the next round.

alibaba/open-code-review (`ocr`, read 2026-10-21 at the owner's request;
not adopted, §3) does each of these three things differently, and the
three ideas below are taken from it.

## 2. Decision

**Proposed, in three parts, built in that order, each its own commit
range under one PR per part.**

**A. Pinned read tools in place of the reviewer's Bash.** The review class
loses `Bash`. It keeps `Read, Glob, Grep`, and gains the tools of a
read-only review server (`tools/fabric/review_mcp/`, stdlib, the same
shape as `memory_mcp`, ADR-040, ADR-049):

| tool | runs | bound |
|---|---|---|
| `review_diff` | `git diff <base>..<head> [-- <paths>]` | the dispatch's range only |
| `review_log` | `git log` over the range or a path, any depth | read-only history |
| `review_show` | `git show <rev>:<path>` and `git show <rev>` | any commit the clone has |
| `review_blame` | `git blame <rev> -- <path>` with a line span | any commit the clone has |
| `review_grep` | `git grep <pattern> <rev> -- <pathspec>` | any commit the clone has |
| `review_check` | one check the project declares, by name | the head worktree, §2 C |

Each tool builds a fixed argv and calls `git` with no shell, a clean
environment (the guard's `CLEAN_ENV`), `--no-pager`, no external diff or
textconv, `core.fsmonitor` and hooks off, and a bounded output that says
when it was cut. Arguments are data: a revision is resolved by
`git rev-parse --verify <rev>^{commit}` before use, a path is a pathspec
after `--`, and no argument may start with `-`. Nothing in the server can
write, fetch or change a ref, because nothing in it names a verb that does.

**B. Checks are declared, not composed.** A project lists the checks its
reviewer may run in its review card (`.agent-fabric/review-card.md`'s
front matter, or a sibling `review-checks.json`): a name, an argv, a
working directory relative to the head worktree, a timeout. `review_check`
runs one by name in the head worktree with the clean environment and no
network namespace where the host allows one; a check the card does not
declare is reported as not run, with its reason, and the dispatcher runs
it. The fabric's own card declares `tests/run.sh` per suite and
`tools/fabric/lint.py`.

**C. The report says what it covered, and the next round reads it.**

- *Coverage manifest.* The report carries a `coverage` block: every path
  in `git diff --name-only base..head`, each `read` or `not read` with a
  reason, and each lens of the brief `applied` or `not applied`.
  `post-review` computes the path set itself and refuses a report whose
  block omits one. A review with a `not read` path posts, says so in its
  first lines, and the arm does not count it as coverage of the head.
- *Checkpoint marker.* The marker becomes
  `<!-- agent-fabric-review v2 base=<sha> head=<sha> config=<sha256> -->`,
  where `config` hashes the agent file, the project card and the brief
  renderer's version. The next review of the same PR is a re-review from
  that `head` only when every check holds: the review object was posted
  by `post-review` on this PR, its `head` is an ancestor of the PR's
  current head, and `config` matches today's. Any doubt — a force-push, a
  changed card, an unreadable marker — is a full review. `card_base` and
  `previous_findings` are then derived, not typed; a typed value that
  disagrees is refused.
- *Posting is the dispatcher's.* The reviewer returns its report; the
  session posts it. The post-review admission in the guard goes, since the
  reviewer has no shell to post with.

## 3. Alternatives Considered

**Keep the guard and keep patching it.** The status quo. Each spelling
found costs a review round, and the guard cannot be complete by design;
it fences the routine path and leaves the rest to the charter. Rejected
because part A removes the class of defect rather than its instances.

**A worktree for the reviewer, with Bash.** Isolation would keep the
session's branch safe from a push, but not the shared object store, the
secrets a shell can read, or an install that writes outside the worktree.
It also gives the reviewer a writable tree, which ADR-020 deliberately
does not.

**A sandbox around Bash (bubblewrap, read-only bind).** What the Codex
engine does (ADR-053 rule 2, `prove_sandbox`). It is the strongest fence,
and the fallback for part B if declared checks prove too narrow. Not
chosen first: Claude Code's Bash has no sandbox the fabric can prove at
dispatch time on every host, and a sandbox still leaves the reviewer a
shell whose output the guard would have to stop reading as a decision.

**No checks at all; the dispatcher runs the suite and hands over the log.**
Simplest, and it keeps the reviewer purely a reader. Rejected as the
default because "run this and see" is often the decisive evidence for a
finding (the agent file says so), and a log the author's session produced
is the author's material. It is the owner's call if part B is judged too
much surface (§8).

**Adopt `ocr`.** A second LLM key and a second posting path, and its
`--background` passes the author's reasoning to the reviewer, which ADR-020
forbids. Its ideas are taken, not its tool.

## 4. Rationale

A fence that reads a language is only as good as its reading of that
language. A fence that offers verbs has no reading to get wrong: what the
reviewer can do is the list in §2, and a new need is a new tool, reviewed
once. The cost moves from an open-ended pattern list to a closed tool list
plus a per-project check list, both of which a review can read whole.

The manifest and the marker turn two claims the gate takes on trust ("I
read it all", "this is the fix range") into records the gate can check.
Both fail closed: a missing path refuses or uncounts, a doubtful marker
means a full review.

## 5. Binding Rules

1. The review class's agent file lists no `Bash`, no `Write`, no `Edit`
   and no `NotebookEdit`. Its tools are `Read`, `Glob`, `Grep` and the
   review server's.
2. Every review-server tool calls its program with a fixed argv and no
   shell, in the clean environment, and refuses an argument that starts
   with `-` or a revision `rev-parse --verify` does not resolve to a
   commit. A tool that can write, fetch or change a ref is not added.
3. `review_check` runs only a check the project's card declares, by name,
   in the head worktree; it never takes an argv from the reviewer.
4. A posted review carries the `v2` marker and a coverage block naming
   every path of its range. `post-review` refuses a block that omits one;
   a review with a path `not read` is not coverage of its head.
5. A re-review's base is the `head` of the last `v2` marker on the PR that
   `post-review` posted, is an ancestor of the current head, and has the
   same `config`; otherwise the review is a full one. A typed `card_base`
   that disagrees is refused.
6. The reviewer does not post. The session posts its report with
   `fabric-pr post-review`.
7. `review-bash-guard` stays as the fence `subagent-clone-guard` applies to
   other classes dispatched without a worktree, until those are gone; it
   is no longer the review class's.

## 6. Consequences

- The reviewer cannot run an ad-hoc command. Anything not in the tool list
  or the project's declared checks is reported as not run, and the
  dispatcher runs it. Expect a short period of "not run" lines while
  projects declare their checks.
- Each managed project with a review card gains a check list; that is the
  project's to write (its remit), and the fabric supplies the shape.
- The `v1` marker stays readable: a `v1` review counts as coverage of its
  head as today, and never as a checkpoint, so the first review after the
  change is a full one.
- The Codex engine already reads through a sandbox; it gains the manifest
  and marker through the shared `post-review`, and nothing else.
- Code: the review server and the readers of the marker are in
  python-dev's entry and go out as REQUESTs; the agent file, the brief
  renderer and the guards are on the contributor never-list and are
  fabric-coordinator's.

## 7. Future Evolution

- If declared checks prove too narrow, a bubblewrap-proved `review_check`
  that takes an argv inside a read-only bind (the Codex engine's proof,
  reused) is the next step, by amendment.
- The other two `ocr` ideas wait on this one: a narrow fact-check pass
  that may only flag a finding the diff contradicts, and per-path review
  lenses in the card. Each is its own record if adopted.

## 8. Decision Status

Proposed, for the owner's word. Two questions are the owner's:

1. Part B (declared checks) or the dispatcher runs every check (§3).
2. Whether the arm uncounts a review with a path `not read` (§5 rule 4),
   or only shows it.

Nothing is built before both are answered.

## References

- ADR-005, ADR-015, ADR-020, ADR-040, ADR-049, ADR-053.
- `runtime/claude-code/agents/code-review.md`,
  `runtime/claude-code/hooks/review-bash-guard.py`,
  `tests/fixtures/review-bash-guard-cases.json`,
  `runtime/claude-code/hooks/subagent-clone-guard.py`,
  `tools/fabric/github/post_review.py`, `tools/fabric/review_brief.py`,
  `tools/fabric/review_codex.py`, `tools/fabric/memory_mcp/`.
- #96, #97 (the guard's review rounds).
- alibaba/open-code-review, read 2026-10-21 at HEAD #1773: its read-only
  tools, `ocr.run-manifest/v1`, and the incremental checkpoint marker.
