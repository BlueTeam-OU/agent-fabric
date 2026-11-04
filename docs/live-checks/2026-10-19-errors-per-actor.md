# Errors per actor, read from artifacts — 2026-10-19

ADR-061 proposes counting errors per actor and per kind from artifacts
only. Before the record was written, a throwaway reader asked GitHub
whether the inputs it names are there, attributable and parseable. This
is what came back; it decides the definitions, not any actor's standing
(ADR-061 §5 rule 6).

**Run.** 2026-10-19 about 09:21Z to 09:50Z, on develop-qzapp, main at
7715fe6d, by fabric-coordinator, through `gh` as the fleet's account.
Repository BlueTeam-OU/agent-fabric only. Two passes: the last 30 merged
PRs (findings, heads with a red check run, reverts), then the last 10
merged PRs again for the check names, re-runs and review shapes. For each
PR: the head ref's second segment as the login, every review whose body
starts with `<!-- agent-fabric-review v1 -->`, and the check runs of
every commit of the PR (`repos/…/commits/<sha>/check-runs`). Reverts:
`git log origin/main --since='30 days ago' --grep='This reverts commit'`.
The scripts were throwaway and are not committed; their logic is above.

## Result

**Attribution.** All 30 PRs had a head ref of the form
`<host>/<login>/…`; none was unattributed. Five logins appeared: the
coordinator's (15 PRs) and four python-dev holders (2, 7, 2, 4). No PR in
the sample was authored on a person's branch, so the person side of the
definitions was not exercised. Every commit carried `Fabric-Role:`, none
a login; commit signatures do not name the agent before ADR-057's
cut-over (`policies/signing.json` lists no repository).

**Review findings.** 84 marked reviews over the 30 PRs. The pattern
`**F<n> (P<level>` matched 43 P3 and 12 P2 findings, all but four in the
coordinator's PRs' reviews. The second pass shows why the split is not
evidence: of 38 marked reviews on the last 10 PRs, 37 mention a level
(`P1`/`P2`/`P3`) but only 13 write findings in the bold `F<n> (P…)` form.
Findings are not written in one parseable shape across reviewers, and a
"P1: none" header line mentions a level without raising a finding.

**Red checks.** Of 137 commits with check runs, 69 had a run that
concluded `failure` or `timed_out`. In the 10-PR pass, 33 commits were
red; every one of them had `ci-ok` red, the aggregate job, and only 22
red named runs lay under them: `platform-smoke` debian 9, fedora 9,
`static` 4. The aggregate counts a cancelled or failed dependency again,
so a count over all check runs double-counts and counts cancellations.
None of the 33 later passed on the same sha, so this sample has no
re-run flake, which says nothing about runners failing.

**Reverts.** The grep returned one commit, 6d3f2a1f, which is not a
revert: it is a pr-gate change whose body quotes git's "This reverts
commit" line. No PR in the 30 was reverted.

## What it decides

1. Attribution by head ref works today for every PR in the sample;
   unattributed stays a defined state, not an observed one (§5 rule 3).
2. A red check is counted per run of a job the required check depends
   on (here the jobs `ci-ok` `needs`), never the required aggregate
   itself, and a cancelled run is not red: neither every run on the
   commit nor the required check alone is the right set.
3. A revert is a commit whose body has git's revert line naming a commit
   of the PR, matched as `results.py` matches it, never a grep over the
   phrase.
4. Findings can be counted only where the review writes them in one
   shape; until reviews do, the reader reports reviews whose findings it
   could not parse beside the counts (ADR-061 §5 rule 8, §7). That makes
   a parseable finding line in every engine's report the first change
   the measure asks for.
5. Not measured: other repositories, people's PRs, `Answers:` coverage
   of findings, fixes forward.
