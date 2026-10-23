# ADR-065 — The reviewer reads through pinned tools, says what it covered, and the next round starts where the last one stopped

**Date:** 2026-10-23
**Status:** Accepted
**Ratified:** owner, 2026-10-23, in the session, answering §8's questions: checks run in a sandboxed shell ("Sandboxed shell"), a `not read` path uncounts the review ("Uncount it"), and the record is accepted and built ("Accept and build")
**Decision Makers:** the owner; drafted by fabric-coordinator
**Scope:** the review class's tools (`runtime/claude-code/agents/code-review.md`), a read-only review tool server beside `tools/fabric/memory_mcp/`, the sandbox the reviewer's checks run in, the posted review object (`tools/fabric/github/post_review.py` and its readers), the re-review range (`tools/fabric/review_brief.py` `card_base`), and the arm's reading of a review; the Codex engine (ADR-053) only where it posts through the same object
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

The sandbox §2 B relies on was read back on develop-qzapp on 2026-10-23:
bubblewrap 0.12.0 at `/usr/bin/bwrap`, and
`bwrap --ro-bind / / --dev /dev --proc /proc --unshare-net` refused a
`touch` under the home.

## 2. Decision

**Three parts, built in that order, as commit ranges on one PR.**

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
| `review_check` | an argv the reviewer gives | a proved read-only sandbox over the head worktree, §2 B |

Each tool builds a fixed argv and calls `git` with no shell, a clean
environment (the guard's `CLEAN_ENV`), `--no-pager`, no external diff or
textconv, `core.fsmonitor` and hooks off, and a bounded output that says
when it was cut. Arguments are data: a revision is resolved by
`git rev-parse --verify <rev>^{commit}` before use, a path is a pathspec
after `--`, and no argument may start with `-`. Nothing in the server can
write, fetch or change a ref, because nothing in it names a verb that does.

**B. Checks run in a proved read-only sandbox.** `review_check` takes an
argv from the reviewer, not a shell line, and runs it under bubblewrap:
the whole filesystem bound read-only, a fresh tmpfs at `/tmp` and as
`TMPDIR`, no network (`--unshare-net`), a new session and process group,
the clean environment, the head worktree as its working directory, and a
time budget after which the whole group is ended. Before the first check
of a review the server proves the sandbox as the Codex engine does
(`review_codex.prove_sandbox`): it must start, and it must refuse a write
at a fresh random path in the head worktree; a sandbox that cannot be
proved runs nothing, with one line saying why, and there is no fallback
to a wider one. A check that needs to write outside `/tmp` — an install,
a restore, a build into the tree — fails inside the sandbox and is
reported as not run; the dispatcher runs it. The host's bubblewrap was
read back before this was decided (§1).

**C. The report says what it covered, and the next round reads it.**

- *Coverage manifest.* The report carries a `coverage` block: every path
  in `git diff --name-only base..head`, each `read` or `not read` with a
  reason, and each lens of the brief `applied` or `not applied`.
  `post-review` computes the path set itself and refuses a report whose
  block omits one. A review with a `not read` path posts, says so in its
  first lines, and the arm does not count it as coverage of the head.
- *Checkpoint marker.* The marker becomes
  `<!-- agent-fabric-review v2 base=<sha> head=<sha> card=<sha> config=<sha256> -->`,
  where `base..head` is the range that review read, `card` the commit
  its project card was read at (`card_base`: the card is never read from
  the range under review, so on a re-review it is not `base`), and
  `config` hashes the review class's agent file, that card's text and
  the brief renderer's versions. The next review of the same PR is a
  re-review of `head..<current head>` with the card at `card` only when
  every check holds: the review object was posted by `post-review` on
  this PR, its `head` is an ancestor of the PR's current head, and
  `config` computed today for the same `card` matches. Any doubt — a
  force-push, a changed agent file, an unreadable marker — is a full
  review. `card_base` and `previous_findings` are then derived, not
  typed: a typed `card_base` that disagrees is refused, and so is any
  typed `previous_findings`, since the previous report is that review's
  posted body.
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

**Declared checks: the project's card lists them, the reviewer names
one.** The narrowest surface. Not chosen: every project
would have to write and keep a check list before its reviewer could run
anything, and the check nobody declared is the one a finding needed. The
sandbox makes the argv harmless, so it need not be enumerated.

**Bubblewrap around Claude Code's own Bash.** No sandbox the fabric can
prove at dispatch time wraps the harness's Bash tool, and the reviewer
would keep a shell whose every line the guard still had to read. The
sandbox goes around one argv, inside a tool the fabric owns.

**No checks at all; the dispatcher runs the suite and hands over the log.**
Simplest, and it keeps the reviewer purely a reader. Not chosen because
"run this and see" is often the decisive evidence for a finding (the
agent file says so), and a log the author's session produced is the
author's material.

**Adopt `ocr`.** A second LLM key and a second posting path, and its
`--background` passes the author's reasoning to the reviewer, which ADR-020
forbids. Its ideas are taken, not its tool.

## 4. Rationale

A fence that reads a language is only as good as its reading of that
language. A fence that offers verbs has no reading to get wrong: what the
reviewer can do is the list in §2, and a new need is a new tool, reviewed
once. Where the reviewer does need to run something, the fence is the
kernel's (a read-only mount namespace, proved before use), not a reading
of the command. The cost moves from an open-ended pattern list to a
closed tool list and one sandbox proof, both of which a review can read
whole.

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
3. `review_check` runs one argv, never a shell line, under a bubblewrap
   sandbox that binds the filesystem read-only, gives a fresh `/tmp`, has
   no network, and was proved by a start probe and a refused write for
   this review; an unproved sandbox runs nothing, and nothing names a
   wider one.
4. A posted review carries the `v2` marker and a coverage block naming
   every path of its range. `post-review` refuses a block that omits one;
   a review with a path `not read` is not coverage of its head.
5. A re-review's base is the `head`, and its `card_base` the `card`, of
   the last `v2` marker on the PR that `post-review` posted, whose `head`
   is an ancestor of the current head and whose `config` matches;
   otherwise the review is a full one. A typed `card_base` that disagrees
   is refused; the previous findings are that review's posted body, and a
   typed `previous_findings` on a PR's re-review is refused.
6. The reviewer does not post. The session posts its report with
   `fabric-pr post-review`.
7. `review-bash-guard` stays as the fence `subagent-clone-guard` applies to
   other classes dispatched without a worktree, until those are gone; it
   is no longer the review class's.

## 6. Consequences

- The reviewer runs any check that can run read-only with a scratch
  `/tmp`; anything that must write the tree, restore or reach the network
  is reported as not run, and the dispatcher runs it.
- A host without unprivileged user namespaces (CI's Ubuntu 24.04, as for
  the Codex engine) runs no checks in review: the review reads, and says
  so. Every developer host is read back before the part B commit.
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

- The sandbox proof is shared code with the Codex engine; if the two
  diverge, one module serves both, by amendment.
- The other two `ocr` ideas wait on this one: a narrow fact-check pass
  that may only flag a finding the diff contradicts, and per-path review
  lenses in the card. Each is its own record if adopted.

## 8. Decision Status

Accepted on the owner's word (the Ratified line). The two
questions this record left open were answered then: checks run in the
proved sandbox of §2 B rather than from a declared list or by the
dispatcher alone, and a review with a path `not read` is not counted as
coverage of its head (§5 rule 4).

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
