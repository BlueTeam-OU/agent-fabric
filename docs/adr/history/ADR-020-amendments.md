# ADR-020 — amendments

The full notes; the ADR's body reads current and its Amendments table lists them.

### Amendment 2026-10-05 — The reviewer inherits no secret

Rule 4 said the reviewer's Bash fence denies state-changing git and
package installs. On 2026-10-04 a review subagent printed its environment,
which every account's shell fills with its synced secrets, and the
operator's signing key was rotated (#95). #96 taught the fence to refuse
printing the environment and reading secret material by path, and ported
it to Python; its nine blind review rounds then each found a spelling the
patterns did not know, all of one class: bash expanding a path, or an
allowed tool running a program the guard never sees, which no string
match can follow. The environment half of that class now has a structural
answer. A live check showed that a `PreToolUse` hook in the code-review
agent's frontmatter can rewrite the command through `updatedInput` with no
permission decision, so the fence rewrites every command it lets through
to run under `env -i`, keeping only the variables a build or a test needs
(`CLEAN_ENV`); the names are fixed in the module and the values are
expanded by the reviewer's own shell, so none passes through the hook.
The patterns stay as the first line, and only that: secret material on
disk, a parent's `/proc` environ and a shell init file that sources
`secrets.env` stay reachable by some spelling (the review of #97 found
`/usr/../proc/…`, `{ . ~/.bashrc; …}` and `BASH_ENV=`), and what closes
them is keeping secrets out of what a session can read. The
session markers (`CLAUDECODE` and its kin) stay in the clean environment:
they are no secret, and tools read them to refuse inside a model session.

### Amendment 2026-10-14 — The card is read at the base; a review names its evidence mode

The review-economics measurement of 2026-10-14 (539 review-class
dispatches of architect-cto-01; report "Review Economics in Agent
Fabric") found a reviewer's first-turn context at 46.5k tokens in gzapp
against 15k in agent-fabric, the difference being the project
instruction files a subagent inherits, re-sent on every turn: 59% of a
review's prompt tokens and 76% of a re-review's. The remedy, a small
review card in place of the instruction files, raised a trust question
the owner put first: the card in the head under review must not govern
the review of that head, or a change could rewrite the instructions
that judge it. Rule 9 reads the card at the base, which is already the
trusted side of every ranged review, and makes the head's card evidence.
The same measurement showed that a brief naming base and head commits
does not by itself make the reviewer's reads pinned: it reads the live
clone, which can move. Rule 10 names the two modes and ties the marker
to the pinned one; the working-tree mode is kept for what the clone was
chosen for (reviewing uncommitted work) and labelled so it never passes
as coverage. Hardening beyond `git show` (a detached worktree, an
extract as the second engine uses) waits on ledger evidence of how
often a pinned review's head differs from the clone's HEAD.

### Amendment 2026-10-15 — A pinned review reads a detached worktree of the head

§5 rule 10's pinned mode told the reviewer to read the head through
`git show <sha>:<path>`, and the note above left hardening (a detached
worktree) to wait on evidence. The evidence is an architect-cto replay
(E2): reviewers, told only to use `git show`, made their own
`git archive` extracts of the head to read and run things; 4 of 6
such extracts were left behind, at 19-74 MB each, and small ranges cost
1.67x the turns. The rule now has the dispatcher make the head once:
`fabric-review brief` and `next` run `git worktree add --detach` of the
range's head at `<TMPDIR>/fabric-review/<repository basename>-<head12>`
(detached, so the clone gains no branch and no `branch.*` config; the
directory 0700; an existing worktree at that head is reused, anything
else at the path refuses the render, and nothing is deleted that was not
identified), and the brief's Evidence line names the path. The reviewer
reads and runs the head's files there and makes no extract or copy of
its own. `fabric-review save` removes the round's worktree, with the
path recomputed from the repository name and the report header's
`head_sha`, never taken from the report's text, and only when it is a
worktree at that head; a failed removal is a warning, the report being
saved. `render()` stays side-effect free (the path is passed in), and a
working-tree or diff-file request makes none. Not changed: the second
engine's own extract (`review_codex.py`) and the reviewer's Bash fence.

### Amendment 2026-10-16 — A review covers the commit it read

§5 rule 6 said only how a review is posted. post-review sent the PR's
head at the time of posting as the review's commit, so a review of an
older head, posted after a push, was counted by the gate and the arm as
a review of the new one: seen live on 2026-10-16, when a review was
posted after its PR's head had moved (devex-tooling j137). The rule now
pins a review to the commit its report read: the dispatch header's
`head_sha` (every header in the report must agree), or `--head` with a
full sha for a report that carries none, which is the second engine's
shape (`review_codex.py` passes the head it archived). A report naming
no head, a `--head` that disagrees with its header, or a commit that is
not one of the PR's (read from the PR's commit list, failing closed when
it cannot be read or is truncated) is refused before anything is posted,
`--dry-run` included. The gate's coverage test is unchanged: it already
compared a review's commit with the head.

### Amendment 2026-10-22 — A supplier dispatches no review of its own part

The pull-requests skill told a supplier to review before hand-off
(`Supplier-Review:`), and suppliers read it as a review-class review of
their own slice: on #354 (four python-dev patches folded into one
coordinator PR) each supplier's slice was reviewable on its own while the
caller's one blind review of the folded head was what the gate counted.
The owner ruled on 2026-10-22 that the caller folds first and runs one
full review: a slice's review costs what the batch's costs and cannot see
the hunks together, and the batch review of #354 found two P1s (process
substitution and function/coproc bodies in the job-copy guard) that the
supplier's own tests had passed. §5 rule 11 now says so; the
`SUPPLIER-REVIEW` section and trailer keep their names and carry the
supplier's own checks; `dispatch_guard.py` denies a code-review dispatch
from a session with a `for/` branch checked out, with a suite case.

### Amendment 2026-10-24 — The reviewer reads through pinned tools and posts nothing headerless

§5 rule 4 said the reviewer had Bash behind review-bash-guard, a fence
that read shell text and took 32 commits and two PRs of review rounds
to keep (#96, #97, the 2026-10-10 `cd` series) without closing every
spelling. ADR-065, accepted by the owner on 2026-10-23, replaces it
with pinned read tools and a proved bubblewrap sandbox; the guard stays
only for the other classes dispatched without a worktree. Rule 6's
headerless `--head` post goes with it: post-review now writes only the
v2 marker with a coverage block, so a report that names no range
cannot post (ADR-065 §5 rule 4). Built on #358.
