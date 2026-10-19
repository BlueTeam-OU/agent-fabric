# ADR-061 — Errors are measured per actor and per kind, the same for people and agents

**Date:** 2026-10-19
**Status:** Proposed
**Decision Makers:** the owner; drafted by fabric-coordinator
**Scope:** what counts as an error of an actor (review findings, red checks, reverts and fixes forward), who it is attributed to, where it is read from, and what the count may and may not be used for; the reader `fabric-errors` and its section in the fleet views. Not the measure of progress (ADR-026) or of cost (ADR-036), which keep their own definitions
**Pillar:** P3
**Evidence:** docs/live-checks/2026-10-19-errors-per-actor.md

## 1. Context and Problem

The fabric has one philosophy of trust, applied to people and agents
alike: both make errors, and an error is answered by review, an audit
trail, reversibility and a correction at its source, not by a wall
around one kind of actor. A control that holds for a role (a reviewer
does not edit what it reviews; every change is reviewed) is the same for
whoever holds the role; a control that exists only because the actor is
an agent, or only because it is a person, is distrust by kind.

Today nothing tells the two apart from evidence. ADR-026 counts verified
results and the supervision they needed, and rejected a per-agent score
(§3); no reader says which actor's work drew which findings, which pushes
went red, or which merges were reverted. A rule that treats one kind of
actor differently is therefore argued, never measured, and so is the
claim that it is unnecessary.

The artifacts already hold most of it (the live check): a marked review
writes each finding as `**F<n> (P<level>, …)**` on the head it read
(ADR-020); a commit answering one names it in `Answers:`; GitHub keeps
every check run per commit; a revert names the commit it reverts; and a
branch is `<host>/<login>/…`, so the login that made a PR is in its head
ref. What they do not hold yet: a finding's judgement (real or not) in a
form a reader can parse — it is the author's words in the PR, in no fixed
shape — and, until ADR-057's cut-over, a commit's own signer: every fleet
commit is signed by one shared key, so the branch is the only name.

## 2. Decision

Errors are counted **per actor and per kind**, from artifacts only, with
one set of definitions for people and agents, and read as evidence for
the rules, never as a judgement of the actor.

- An **actor** is whoever made the thing the error falls on: an agent by
  its login, a person by the GitHub account or branch name that is
  theirs. The PR's author is the login of its head branch; a range
  folded from a `for/` branch is its contributor's (ADR-018 §5 rule 8);
  a review finding against the review itself — a finding judged not real
  — is the reviewing engine's and model's. Where the artifacts name no
  one, the actor is **unattributed**, said as such, never guessed. Once a
  repository is cut over under ADR-057, a commit's signing agent names
  it, ahead of the branch.
- The **kinds**, each with its denominator:
  1. **review finding**, by level (P1, P2, P3), raised in a marked review
     on a head of the actor's PR — per review given; split into
     *answered* (named by an `Answers:` commit), *judged not real*, and
     *unjudged*;
  2. **red check**, a commit the actor pushed as a PR head on which a
     named check run concluded `failure` or `timed_out` — per head
     pushed, by check name; never the aggregate job (`ci-ok`), which
     counts its dependencies again, and never a cancelled run; a red that
     the same commit later passes on a re-run is **flaky**, the check's,
     not the actor's;
  3. **revert**, a commit of the actor's PR reverted on the default
     branch within the window (fourteen days, as ADR-026), told by git's
     revert line naming that commit, as `results.py` tells it, never by
     the phrase alone — per PR merged;
  4. **fix forward**, a later commit on the default branch that the
     commit classifier calls a fix naming the actor's PR, within the
     same window — per PR merged.
- The counts are published per period (a week), per repository and in
  total, per actor and per **actor class**: person or agent, role, and
  for review findings judged not real the engine and model.

What the measure is for: **a rule that treats one class of actor
differently states the error evidence for the difference**, read from
this measure, or is brought to the owner to be made the same for all.
What it is not for: a target, a ranking, or a reason to give or take an
actor's work, resources, role or existence.

## 3. Alternatives Considered

- **No per-actor count; per kind only.** ADR-026 §3's reason for
  refusing a per-agent score — a result spans lanes, and a personal
  number invites optimising one's own row. It loses here because the
  question asked is about actors: whether a control on agents only, or
  on people only, has evidence behind it cannot be answered without
  counting by actor. The cost ADR-026 names is held by §5 rule 6: no
  combined score, no ranking, a denominator beside every count.
- **One error score per actor** (a weighted sum of the kinds). Rejected:
  it is the per-agent score ADR-026 refused, and it hides which rule a
  kind of error points to — a P1 in a guard and a flaky check are
  different evidence about different rules.
- **Count only agents.** Rejected by the philosophy itself: the owner
  arms, corrects and commits too, and a measure that only ever counts
  agents is the wall it is meant to test.
- **Read errors from transcripts or session logs** (a refused command, a
  guard's block). Richer, and rejected for the same reason as ADR-026 §5
  rule 3: a transcript is the agent's private context, a person has
  none, and the two would then be measured differently. Guard refusals
  that reach an artifact may become a kind later (§7).
- **Count every finding raised as an error.** Rejected: a finding judged
  not real is the reviewer's error, not the author's; counting it
  against the author rewards silence in the review. Until judgements are
  parseable, findings are reported in their three states, never summed
  into one.

## 4. Rationale

The philosophy says errors are expected of everyone and handled the same
way. Measuring them the same way is what makes that checkable: if agents
and people in one role draw P1s at the same rate per review, a gate on
one of them alone has no ground; if one kind of actor breaks one check
far more often, the fix is that check's rule or that role's brief, made
for every holder. Reading only artifacts keeps the measure auditable by
anyone and keeps it out of any actor's private context, as ADR-026 does.
Denominators and the flaky split keep a busy actor, or a broken runner,
from reading as an error-prone one.

## 5. Binding Rules

1. An actor, an error kind and its denominator are as §2 defines them; a
   change to any of them is an amendment of this record, and the series
   is recomputed from the start under the new definition, never spliced.
2. Every input is read from artifacts: the PR record (head ref, commits,
   marked reviews, check runs per commit), commit trailers (`Answers:`,
   `Fabric-Role:`), the default branch's reverts and fixes as
   `tools/fabric/github/commit_class.py` classifies them, and, after an
   ADR-057 cut-over, commit signatures. Never a session transcript, an
   agent's memory, or a message body.
3. The definitions are the same for people and agents. An actor the
   artifacts do not name is counted as unattributed, with its count; it
   is never assigned to the likeliest login.
4. Every count is published beside its denominator; findings in their
   three states (answered, judged not real, unjudged), never summed;
   flaky reds apart from the actor's. A period with fewer than five
   denominators for an actor shows the count without a rate.
5. A rule — a guard, a policy entry, a charter clause — that applies to
   one actor class and not another names, in its record or its policy
   entry, the period and the counts that justify the difference. One
   that names none is listed in the first published period's report and
   brought to the owner, to be justified or made the same for all.
6. The counts are never a target, never ranked, never combined into one
   score per actor, and never a reason to assign or withhold work, a
   resource, a role or a login. A view that shows actors' error counts
   side by side shows no verified-work number beside them (ADR-026 §5
   rule 4, ADR-046 §5 rule 7).
7. What the measure finds is corrected at the source, for every holder
   of the role: a rule, a guard, a test, a brief. An actor's own counts
   are information to that actor, as they would be to a person, and are
   never a fence around it alone.
8. The reader is `fabric-errors` (`tools/fabric/errors.py`), sharing
   `results.py`'s readers of the PR record and the default branch; the
   fleet views read its answer as a section of `fabric-fleet`
   (ADR-046 §5 rule 1). Until a finding's judgement has a form a reader
   parses, the report says how many findings are unjudged.

## 6. Consequences

- A trust rule can be argued from a number, both ways: a wall around one
  kind of actor has to show its evidence, and so does the claim that
  none is needed.
- The first reports will be dominated by agents, because the fleet's
  commits are theirs; the owner's actions that reach an artifact
  (armings, direct commits, corrections) are counted by the same
  definitions, and the report says how many there were, however few.
- Attribution is by branch until ADR-057's cut-over: a commit pushed to
  another login's branch, or a PR made on the owner's word by an agent,
  counts against the branch's login. The report states the attribution
  source.
- A judgement of a finding has no fixed form yet; until it has one, the
  split between answered and judged-not-real is partial, and the report
  says so (§7).
- Reading check runs per commit costs one GitHub call per head; the
  reader caches by sha, which never changes.

## 7. Future Evolution

- A parseable judgement line (finding label, real or not, by whom) in
  the PR, written where the author already answers, would close the gap
  §5 rule 8 names; that is a change to the review procedure (ADR-020),
  proposed after the first periods show how many findings stay unjudged.
- Guard refusals that reach an artifact (a refused push, a refused
  arming with its basis comment) are candidate kinds once their records
  carry an actor.
- The owner reads the first few weeks of series and decides whether the
  kinds and windows hold, as ADR-026 §7 does for its measure.

## 8. Decision Status

Proposed. It waits on the owner's acceptance; the reader is requested of
python-dev, and the fleet view follows the reader.

## References

- ADR-018 §5 rule 8 (contributed ranges), ADR-019 (the PR record, the
  `Kind:` and `Answers:` trailers), ADR-020 (the marked review and its
  findings), ADR-026 (verified results, artifacts only, §5 rule 4),
  ADR-036 (cost per verified result), ADR-046 §5 rules 1 and 7 (fleet
  views), ADR-057 (each agent signs its own commits).
- `tools/fabric/results.py`, `tools/fabric/github/commit_class.py`,
  `tools/fabric/github/post_review.py` (REVIEW_MARKER).
- `docs/live-checks/2026-10-19-errors-per-actor.md`.
