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
