# Git, branches and pull requests in this repository

**Commit after each logical unit of work.** Pushing is not part of that
loop: push when the work asks for it — the branch is finished, or you
were told to. A push that cannot complete (credentials, remote access,
branch protection, environment limits) is said, never claimed. Commit
messages are short, specific and scoped to the change; completed work
is never left uncommitted. Work reaches `{repo.default_branch}` as a pull
request, merged by {method}.

**Every commit declares its kind in its trailers**, because a PR is armed
by its count of work commits: `Kind: work` for new work, a bug fix, docs
or a record; `Answers: <finding labels or thread>` for a commit that
answers a review of its PR, which the `commit-msg` hook stamps
`Kind: review-fix`. A commit with neither is refused; a merge declares
nothing.

**A branch lands at {commits.advice_over} work commits**, folds included:
past that, land before adding more. Past {commits.refuse_over} a commit
that adds work is refused without an `Owner-Word: <date> "<words>"`
trailer quoting the owner. A change that must land together opens its PR
at its first fold.

**One change, one owner, one open PR per agent and repository.** Pieces
that only work together land as one PR, integrated by the concern's
owning role; a supplier delivers commits or a `for/` branch to it and
opens no PR. While your PR is open, the next piece of work, any topic,
is another commit on it. A PR is armed at {commits.min} work commits or
more, never without the review gate ({reviews} on the head); under the
minimum, bundle queued jobs first, then it arms on a word: the arming
authority's that `fabric-pr arm --dry-run` names, asked by `REQUEST`
while you work in another repository, else the owner's. Any PR status
you state carries its counts ("#215: 6 work, 2 fix, minimum
{commits.min}"). Load the `pull-requests` skill before you open, supply,
fold, add to or arm a PR.

**No machine attribution, anywhere.** No `Co-authored-by:` trailer, no
`Claude-Session:` trailer, no session URL and no "Generated with …"
footer — not in a commit message, not in a pull-request description. The
`commit-msg` hook and CI refuse it; write the message right the first
time.

**A commit message with shell metacharacters** (`` ` ``, `$`, `×`, `()`)
is passed through a quoted heredoc (`<<'EOF' … EOF`), never an inline
`-m` string. A command you hand the owner is never a heredoc.
