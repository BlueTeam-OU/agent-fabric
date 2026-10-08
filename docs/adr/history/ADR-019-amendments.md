# ADR-019 — amendments

The full notes; the ADR's body reads current and its Amendments table lists them.

### Amendment 2026-10-04 — `main` is protected

Rule 6 said agent-fabric had auto-merge off and no ruleset, so arming a
pull request meant merging it, and `gh pr merge --auto` merged at once
while CI was still running: the session's own discipline was the only
thing between a red build and `main`. An external review of the fabric
named that as the next hardening step, and the owner approved a minimal
ruleset modelled on gzapp's: a pull request, the CI checks and signed
commits required; deletion and force-pushes refused; merge commits
only; no approval count, since every session merges from one account;
no merge queue, so arming stays one command. Auto-merge is on, so
`gh pr merge --auto` now waits for green. The ruleset is committed as
`tools/fabric/github-ruleset-main.json` and applied by
`tools/fabric/github-repo-settings.sh`, which used to force auto-merge
off. The authority guards still decide who may merge; GitHub now
refuses what is not a green pull request.

### Amendment 2026-10-05 — One required check

The 2026-10-04 ruleset required eleven checks by the names GitHub reports,
one per CI matrix leg; two of them, the platform-smoke legs, are names
GitHub cuts past a length, and every leg's name carries its matrix values,
so a job renamed or a matrix argument changed would have blocked every
merge until the ruleset named it (the record's own §7 said so). CI now
has an aggregate job, `ci-ok`, which needs `static`, `guards-and-suites`
and `platform-smoke` and fails unless each of them succeeded; it runs even
when one failed or was cancelled, since a skipped required check reads as
passing. The ruleset requires `ci-ok` alone. The repository's topics,
set by hand when the icon was made, are written by
`tools/fabric/github-repo-settings.sh` with the rest of the settings.

### Amendment 2026-10-05 — Eight or more arm without the owner's word, over sixteen too

Rule 4 armed eight to sixteen work commits on the gate, asked the owner
under eight, and had a batch over sixteen split before it opened. The
owner ruled twice on 2026-10-05: their standing word ("over 8 commits a
pr can be armed without my authorization") covers a security-boundary
change too, and "over 16 commit don't require my authorization". So
eight or more arm on the gate alone, over sixteen included; under eight
still asks the owner; sixteen stays the size a batch is opened at, as
advice. `tools/fabric/github/arm.py` asks the owner's word on a
security-boundary change only under eight (devex-tooling's supply), and
`identities/prompt/team.md` says the same to every session.


### Amendment 2026-10-06 — One open pull request per agent and repository

rust-ui-dev-01, given gzapi-org/herdr beside InterWeave, asked whether a
herdr pull request waits behind an InterWeave one. It never did in
practice: a branch in another repository cannot take the next commit,
so it is never addable to the open one, and the coordinator had kept a
fabric PR and project PRs open together throughout. team.md said so in
agent-fabric #104; this record follows it, as the two moved together
when "sixteen work commits" replaced "the band's ceiling".


### Amendment 2026-10-08 — Every commit declares its kind

Rule 3 guessed a commit's kind: an `Answers:` trailer meant a review fix,
and without one the subject's words decided. Two sessions reported the
same PR counts wrong on 2026-10-08 — their review fixes lacked the
trailer and read as work, and commits named after the "findings" they
addressed read as fixes — and the owner, deciding whether to arm, found
the marking "not well defined". The conventional `fix:` prefix could not
serve: in gzapp it names a bug fix of the project, which is work. So the
author declares the kind in a `Kind:` trailer, `work` or `review-fix`
(with its `Answers:`), and the `commit-msg` hook every managed checkout
runs refuses a commit without it, stamping the two cases it can tell for
certain (an `Answers:` trailer, git's own revert message). The counter
reads the declaration first and the old reading only for a commit that
has none, so the history before the rule keeps its count. A review fix
that answers another pull request's review stays work in its own
pull request, as before (devex-tooling's classifier keeps the rule it
was written for). The CI half of the guard waits for the branches
opened before the rule: a refusing check now would turn each of them
red.


### Amendment 2026-10-08 — A folded pull request's review fixes are fixes

gateway#10 was folded into gateway#11 (the owner asked why the two were
separate) and #10's two review fixes counted as #11's work: the rule that
a fix answering another PR's review is follow-up work could not tell a
merged PR's follow-up from a fold. rust-services-dev measured it (8 work
read where 6 was right, at the arm-without-asking threshold). A PR closed
unmerged whose head lies inside this range was folded in; its review
fixes are fixes here. The reading needs no convention in the description.
