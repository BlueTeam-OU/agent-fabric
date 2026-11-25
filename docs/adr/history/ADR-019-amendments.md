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
fixes are fixes here. Once the counter reads it, it needs no convention in the description. The counter's half (commit_class) is devex-tooling's and was not yet built when the rule was recorded; review of #125 found the record ahead of it, and the rule now says so.

### Amendment 2026-10-09 — results.py reads a folded PR's review fixes

python-dev-01's #132 (merged 2026-10-09) made `tools/fabric/results.py` pass `commit_class.Folds` for each merged pull request, asking ancestry of GitHub's compare API since results reads every registered repository and not one clone (d64ca04f), and read `Answers:` from the trailer block as pr-gate does (62ab655b). Rule 3's interim clause — that results did not read a fold yet, so a PR's description named the folded PR and its fixes — is withdrawn; the three counters read a fold alike.

### Amendment 2026-10-09 — A push after the arming takes auto-merge off

On #134 (2026-10-09) the gate was met and the owner's word given, then a conflict with main was resolved by a merge that put new code on the head; auto-merge stayed on, so the unreviewed resolution would have merged once checks passed, and was disarmed by hand. GitHub keeps auto-merge across a push from anyone with write access. The owner approved the guard (2026-10-09, from the reading of "loops, graphs & harnesses": a check that runs instead of a rule that is remembered). The workflow reads the arming time when it runs and leaves an arming made at or after the push, which is an arming of the new head; tests/test_disarm_on_push.py runs the workflow's own script against a fake gh.

### Amendment 2026-10-10 — Brand repositories commit straight to main

The owner, 2026-10-10, after arming blueteam.ee#3 (3 work, 0 fix) by hand: "these repo from brand agent updates by likely a commit at time so don't make sense the rule of 8 commit, merge queue or even the branching". Asked which flow replaces it, the owner chose direct commits to main for content, with a pull request only for boundary files, over direct commits for everything (the harness and the npm manifests would lose their only check) and over keeping pull requests without the floor (the branch and review cost stay per change). Same rule a person alone on a marketing site would follow (the owner's trust philosophy: one policy for people and agents). None of the four repositories has branch protection, so GitHub already accepts the push; the fence is the pre-push hook every registered working copy runs through core.hooksPath. `pr_paths` is narrower than `boundary.paths`: page sources, content, styles, design tokens, images and fonts commit directly (the secret-shaped names are anchored words, so `tokens.css` and an `authority` record are not secret-shaped); scripts in any common language, the build and install configuration and every file with the executable mode go by pull request, as does any push that is not a fast-forward; the boundary still governs what a pull request needs to arm.

### Amendment 2026-10-11 — pre-push also checks signatures in every project

Rule 1 said that in a project without `direct` the pre-push hook does nothing. Since the signature check (tools/fabric/guards/ban_unsigned_commits.py, run from tools/fabric/githooks_prepush.py) the hook refuses, in every project, a push that adds a commit without a signature the checker can read; the main ruleset requires signed commits, so the keyboard now says so before the server does. The commits it checks are those no remote-tracking ref has, whatever remote or URL is pushed to (review of #212, F2). A project without `direct` still gets no direct-push rule.

### Amendment 2026-10-19 — an arming authority's word beside the owner's

§5 rule 4. The owner decided on 2026-10-19 that a project's arms below
its minimum need not all wait on the owner: each repository's arming
policy may name the role that gives the word in the owner's place,
`below_min_authority` for any PR under the minimum and
`boundary_authority` for a security-boundary change under
`boundary_min` (identities/schemas/arming.schema.json). `fabric-pr arm`
reads it (the code landed with #305); the settings repositories named
fabric-coordinator for agent-fabric, its gateway and FleetDeck, with
`authority_own_prs` true, and architect-cto for InterWeave and gzapp,
with it false (agent-fabric-settings#9, gzapi-org/agent-fabric-settings#8).
The word travels as an AUTHORIZES message naming the PR and its head,
or the authority arms from its own bound session; neither skips the
review.

### Amendment 2026-11-01 — An arming is tied to its head by a status

§5 rule 5. The owner's audit of 2026-11-01 (F02, P1) found that
disarm-on-push kept auto-merge when the arming's `enabledAt` equalled the
push's time: both are whole seconds, so an arming of the old head made in
the push's second read as an arming of the new one, and the old head's
arming merged the new, unreviewed head. The time it compared,
`pull_request.updated_at`, also moves with any edit of the PR. The owner
asked for the comparison to fail closed and for a required check that
ties the authorization to the head's sha.

Since then `fabric-pr arm` posts a commit status, the context the
arming policy's new `armed_status` names (fleet default `fabric/armed`,
`null` turns it off), state success, on exactly the sha its gates read,
before it enables auto-merge; it refuses when pr-gate's row or a fresh
read of the PR names another head. In mode `auto` the ruleset that
`fabric-repo-policy` applies requires that status beside the policy's
`required_checks`, never inside the list, because a repository's list
replaces the fleet's on merge and would drop it. Mode `queue` and
`owner-only` are left out: nothing posts the status on a merge-group
commit, and an owner-only repository is never armed, so the owner's own
merge would wait on a status nobody posts. disarm-on-push no longer
compares times: it keeps auto-merge only when the pushed head carries
`fabric/armed` success, and a status it cannot read is no tie.

The status is trusted as the arming is: anyone with write access can
post it, as anyone can enable auto-merge; it fences the accident of a
late push, not the intent. Consequences: a merge made by hand in a mode
`auto` repository (the coordinator's Dependabot pin bumps, an owner's
merge in the UI) waits until the status is posted on the head it merges;
a PR armed before its repository's ruleset carries the check waits on it
and is armed again; and the order of rollout is merge, then apply each
repository's ruleset, then re-arm what was open.

### Amendment 2026-11-03 — The owner's word as relayed is read

§5 rule 4 reads an `AUTHORIZES` message only where it stands in the
owner's place. Where the basis already gave the owner's word, `fabric-pr
arm` printed "no authorization is needed" and dropped the message unread,
so a relayed approval naming the wrong PR or head would have armed all
the same: kutaisi-shop-transit #4 was armed that way, its head checked
by hand by the arming session. The message is now read as the owner's
word as it was relayed: addressed to the arming session, from another
login, a DECISION or REPLY naming this repository, PR and head. No role
is asked of its sender, since the owner holds none, and the basis is
what arms, so it can only refuse; the comment records who relayed it.
Without the owner's word, a policy with no `below_min_authority` still
does not read one. Supplied by devex-tooling (j271). j527.

### Amendment 2026-11-05 — A decision record arms on the owner's ruling

The gzapi.brand remit (fabric-coordinator, 2026-09-17, on the owner's
question) says the blind review class is for software: brand content is
reviewed by the roles it touches, the owner's ruling on a decision
record is the approval, and brand-comms merges on it. `fabric-pr arm`
was later made to require the review class's review on every PR of a
direct repository (review of #212), so a record PR there could not be
armed at all: gzapi.brand #10 and #13 were merged from the owner's own
account (brand-comms-01 REPLY 01a19619). The owner chose, 2026-11-05,
to give the tool the remit's path rather than change the remit.

A direct project's `arm.json` may name `direct.record_paths`. A PR every
file of which matches it, none `pr_paths` or the security boundary, and
every file it leaves at the head a regular file (mode 100644 in the
head's tree, so neither an executable, a symlink nor a submodule), arms with no review-class review and no review
engine on the owner's word (an `AUTHORIZES` beside it read as the word
relayed); no other word stands in, an arming authority's included, and
the comment records the record path. Any other file in the PR puts it
back on every gate. `record_cases` are the floor: lint refuses one the
pattern misses, or one `pr_paths` or the boundary matches. Declared for
gzapi.brand (`brand/decisions/*.md`). The arm half is devex-tooling's
(j526).

### Amendment 2026-11-10 — An arming is withdrawn on the record

An arming authority withdrew an arming on a managed project's PR (#600)
by hand: auto-merge came off, and nothing on the PR said who took it off
or why, where an arming leaves its basis as a comment (architect-cto-01,
REPLY 01a1c1ef). `fabric-pr` had no verb for it.

`fabric-pr disarm <n> --basis "<why>"` takes off whatever arms the PR —
the head's `fabric/armed` success (set to pending, since GitHub deletes
no status, so in a mode `auto` repository the ruleset holds the head
until it is armed again), a merge-queue entry, auto-merge — then posts
"Disarming basis: <text> — <role>, head <sha8>." and reads the PR back.
Who may disarm is narrower than who may arm: the session whose PR it is,
or with `--any-owner` only on the owner's word or the word of the role the
arming policy names, held by the session's binding, never on `--any-owner` alone as arm
takes it at the minimum; an owner-only
repository is refused, as it is never armed by the tool. The review,
count and check gates are not asked: they judge whether a head may
merge, and none stands between a merge and its withdrawal. Because a
disarmed head keeps a pending `fabric/armed`, `fabric-pr gate` no
longer reads that status as a check of the head; it was also reading
arm's own success as green on a head with no CI. Supplied by
devex-tooling (j310, REQUEST 01a1c27c). j719.

### Amendment 2026-11-12 — the record names no organisation's projects, counts or accounts

What changed: §5 rule 1 declares `direct` for "the projects
whose `arm.json` declares `direct`" in place of four named projects.
Rule 4 keeps its mechanism (arm at the minimum without the owner's word, a
boundary change too, over the batch size too, ask the owner or the arming
authority below it) and names the counts as `policies/arming.json`'s
`commits.min`, `commits.boundary_min` and `commits.advice_over`; rule 2,
§2 and §4 say the batch size and the minimum the same way, and the title
drops "8 or more". Rule 6 says a merge is made from the operator's GitHub
account, not "the one GitHub account every session uses". §6's access row
reads the repository's administrators. Rule 8 is unchanged.

Why: ADR-045 §5 rule 4 sorts every record into engine or operator, and
this one mixed the PR mechanism every operator runs with this
organisation's direct projects, its minimum and batch size, its account and
its collaborator. `policies/arming.json` already says the counts are the
policy's, so the record points at the data (docs/split/adr-classification.md,
the table row and "Decided"). The numbers were not changed, only where the
record states them: the values stay in `policies/arming.json`.

### Amendment 2026-11-14 — under the minimum, bundle first

What changed: §2 and §5 rule 4 say what an agent does with a PR under
the repository's minimum before it asks for any word: its queued jobs in
that repository ride the PR as further work commits, whatever their
topic, until the count reaches the minimum. A word below the minimum,
the owner's or the arming authority's, is for work that cannot wait (a
broken `main`, a path the owner has put first). `identities/prompt/team.md`
and `policies/pull-requests/SKILL.md` say the same.

Why: the owner, 2026-11-14, after agent-fabric's CI grew long: "PR should
move to 8 minimum commits like gzapp ... and agents must be encouraged to
put together even jobs to reach 8". Each PR costs a full CI run, a review
and an arming, so one PR of eight unrelated jobs costs less than eight of
one. This replaces a rule the owner gave on 2026-11-12, that only work of
the open PR's topic rides it, which was queued (j807) and never landed.
The minimum itself is not this record's: agent-fabric's moves from 1 to
the fleet's 8 in its settings repository (`repos/agent-fabric.json`,
`commits.min`), with `commits.below_min_authority` fabric-coordinator.
Applied to PRs opened after the settings change; those open before it keep
the word they were given. j885.

### Amendment 2026-11-21 — the settings repositories and the no-CI word stay the owner's

What changed: §5 rule 4 says two limits of the arming authority. A
repository that holds the rules every PR is armed under (an
organisation's `agent-fabric-settings`, and the operator repository,
where `policies/arming.json` and `policies/auto-mode.json` move at
ADR-045's split) names no `commits.below_min_authority` or
`commits.boundary_authority`, so a PR there below its minimum or on its
boundary arms only on the owner's word. And the owner's no-CI word, which `fabric-pr arm` reads only on a
PR-mode repository with no CI at all, is never given by an authority:
a repository without CI is given direct mode (where a head with no
check merges on its review alone) or CI in its policy.

Why: the owner's rule of 2026-11-09, that no agent waits on the owner
to arm, found repositories with no authority to ask (j722, from
devex-tooling's REPLY 01a1c220 on gzapp.decks). The owner, 2026-11-21,
answering j722's sweep of every `repos/<repo>.json`: the brand, deck
and transit repositories take architect-cto as both authorities with
`authority_own_prs` false, radicle-spike fabric-coordinator; the
settings repositories stay the owner's, since a settings PR loosens the
fence the agents are armed under; the no-CI word is not delegated,
since only an empty repository would read it today. The operator
repository was not in the sweep's question; it takes the settings
repositories' reason, and its policy has no word from the owner yet.
The engine's repository holds `policies/arming.json` and
`policies/auto-mode.json` until that split and keeps fabric-coordinator
as its authority meanwhile: the rule names its two kinds of repository,
not every repository a rule file sits in.
blueteam-accounting keeps the policy the owner gave it on 2026-11-17:
its accounting role arms at one work commit, every other PR below the
minimum on the owner's word. Which repository
names which role is its settings file's, not this
record's (A 2026-11-12); `policies/auto-mode.json` lists them for the classifier.

### Amendment 2026-11-21 — nobody waits idle on a word

What changed: §5 rule 4 says how an agent waits for a word to arm.
Where `fabric-pr arm --dry-run` names an arming authority
(`commits.below_min_authority`, `commits.boundary_authority`), the agent
asks it by `REQUEST`, never the owner, and works on a job in another
repository until the word arrives: a commit on the PR would move the
head the word names, and a same-repository job would ride the PR.
`identities/prompt/team.md` and `policies/pull-requests/SKILL.md` say the
same.

Why: the owner's rule of 2026-11-09, broadcast to the fleet that day
(INFO 01a1c1dc-793e): sessions ended their turn asking the owner for an
arm word the arming authority could give, and sat idle at the prompt
until the owner read it. The skill carried the rule from 2026-11-18;
this puts it in the record and the launch prompt. A Stop hook that
sends a session back when its turn ends on an arm question was
considered and not built: telling an arm question from any other
question in a turn's last message is a text match that would fire on
the wrong turns, and the prompt line reaches sessions only at their
next launch, so stalls before then say nothing about whether it works.
j718.

### Amendment 2026-11-21 — the AlmaLinux leg runs nightly

What changed: §6's ruleset row. `ci-ok` needs every `platform-smoke`
leg, and since #554's profile (c5e020d1, made blocking by ab17a69e)
those included an almalinux:10 leg, the platform of `fabric-h2`. That
leg leaves `ci.yml`'s matrix and so `ci-ok`, and runs as the job
`platform-almalinux` in `stripped-nightly.yml`: scheduled daily, on
`workflow_dispatch`, and on a pull request that changes any of that
workflow's `pull_request` paths (the workflow, `tests/stripped_run.py`,
`tests/stripped_skip.txt`), where its result is advisory.
Its steps are `platform-smoke`'s for one platform, with the floor
waiver ADR-040 §5 rule 1 (A 2026-11-11) gives EL 10's python3.

Why: the owner, 2026-11-12: "almalinux leg nightly only". With it the
median `ci` run on `main` went from 16 to 22 minutes (2026-11-04 to
11-12), the leg itself 15.0 minutes, on every push of every PR.

What follows: an EL 10 break now merges green. scheduled-red reads the
nightly's newest scheduled run at 17:00 UTC and files one job per
workflow (`scheduled_red.py`'s marker), so while a job for a red of
either job in the workflow is open, in any state, a red of the other
files nothing; the gap is open until python-dev-02's j176 scopes the
marker to the failed job (REQUEST 01a1ffc0-ed0a, review F1 on #679).
`fabric-h2` may take `fabric-ctl all upgrade fabric` in between. A PR
that changes the almalinux profile can run the leg first with
`gh workflow run stripped-nightly.yml --ref <branch>`. A `pull_request`
paths trigger on `runtime/provisioning/platform/` was not added: the
owner said nightly only, and in this workflow it would also start the
90-minute stripped run. j803.

### Amendment 2026-11-24 — a branch is refused past `commits.refuse_over`

What changed: §5 rule 4 measures a branch from its first commit, not
from its pull request, and gives the count two thresholds.
At `commits.advice_over` (the fleet's 16) the branch lands before more
is added, as rule 2 already said; the `commit-msg` hook, `fabric-pr
gate` and the session-start jobs line now say so. Past
`commits.refuse_over` (the fleet's 32, a new key of
`operator/policies/arming.json` that a repository's settings may
override; the schema and `arm_policy.validate` require it greater than
`advice_over`) a commit that raises the count needs an `Owner-Word:`
trailer. The hook, CI and the gate refuse one without it. Folded
commits count like the integrator's own, and a fold that crosses the
line carries the trailer on its merge. A change whose pieces must land
together opens its PR at its first fold.
This replaces the 2026-10-05 reading that sixteen is advice only.

Why: the owner, 2026-11-24, on BlueTeam-OU/InterWeave#752: "how could
this ever happen". It had 220 work and 34 fix commits, 37 merges and
482 files, folded from five roles over five days before its PR opened.
Six partial reviews did not count, and its chain hit post-review's
250-commit cut. agent-fabric#692 had 48 work commits. Nothing measured
a branch before its PR existed. Arm printed one "smaller batches next
time" line, at arming only. And when the PR rules moved into the skill
(4f0a14475, 2026-10-15), the team section lost "stops being addable at
sixteen". The owner chose "warn at 16, refuse at 32", with its own
setting rather than a computed double, overridable per repository.

The owner settled three details the same day. The word is a trailer on
the commit, so CI can read it, with the trust of arming's basis. The
hook reads a per-account copy of the repository's policy, written by
every API read of it, and falls back to the fleet's value when it has
none. The rule lands first; moving the git prose into a layered
`git.md` (j1086) is a second PR.

What follows: CI checks against the fleet's value, not a repository's
override, because a workflow's token cannot read a settings
repository; the gate, which reads it, holds the override. No settings
file overrides `advice_over` today, and no open PR was over 32 work
commits when this landed. j1078.

### Amendment 2026-11-25 — the git rules are `git.md`, by hook

§5 rule 9 is new. How a session commits, sizes a branch, opens, counts
and arms a pull request is one text, `git.md`, in three layers: the
repository's `repos/<repo>.git.md` in its client's settings repository
(the owner's), `operator/prompt/git.md`, and the engine default
`identities/prompt/git.md`. The first found is used whole. Its numbers
are placeholders filled from that repository's merged arming policy, so
the prose and the policy cannot disagree. The session-start hook gives
it for the working copy, the prompt hook again when the session moves
to another working copy, and `fabric-git-rules` prints it for a harness
without hooks. `AGENTS.md`'s "Git discipline" and `team.md`'s pull
request paragraph move into it.

Why: the owner, 2026-11-24. `AGENTS.md` is read from the working copy at
its own commit: a stale copy carries stale rules, and a worktree loads
it twice. The launch prompt is rendered from `main`, but it is the same
for every repository, while the numbers are each repository's (its
settings override `commits.*`), and the managed projects' own git
sections had drifted from their policies (gateway, gzapp, gzapi.ge).
A hook follows the working copy, as the remit does, and renders from
the repository's own policy. The owner chose the three layers, the
whole-file replacement, a missing placeholder as an error, and an
unreadable repository layer falling back to the operator's text, said.

What follows: the hook reads the account's copy of the policy and of
the repository's `git.md`, written whenever `fabric-pr` reads the
policy, and calls no API. Each managed project's role removes its git
section after this lands, by REQUEST. j1086.
