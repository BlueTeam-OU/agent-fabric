# Admission rubric

What earns a place in a role's knowledge base, and what does not.

This file exists because of one failure mode. The first drain reads
thousands of observations under real compression pressure; the fifth reads
eighty. A distiller handed eighty observations and told to "distil" will
fill the page anyway — promoting weak claims, padding prose — because
output volume tends to track how large the task feels rather than how much
was actually learned. Density then drifts drain by drain until the role
base is long instead of dense, and nobody can see it happening.

The fix is structural: **the unit of distillation is the claim, never the
run.** Every candidate faces the same six tests below whether it arrives
among three thousand observations or among eighty. A big drain produces
more candidates, not a lower bar. A small drain usually produces few, and
often produces none.

Changing this file changes the standard for every future drain, uniformly.
That is the point of it being committed and versioned: the bar is
governable, and moving it is a reviewed decision rather than a drift.

## The six tests

A claim is admitted only if it passes all six.

1. **Durable.** It will still be true after the next refactor of the code
   it describes. A fact about a specific line, a transient bug, or a state
   that a single commit resolved is not durable. "The web suite intercepts
   console output unless you disable it" is durable; "test X was failing on
   Tuesday" is not.

2. **Not already recorded.** It is not derivable from the ADRs, the
   contracts, the CLAUDE.md files, or the app READMEs. Those are
   authoritative and load on their own; restating them here creates a
   second copy that will drift from the first. Point at them instead — the
   role base earns its keep with what is *not* written down anywhere.

3. **Evidenced.** At least two independent observations support it, or one
   observation of type `decision`. A single incidental mention is a rumour;
   the same lesson learned twice is knowledge. Decisions are exempt from
   the count because a decision is recorded once by nature.

4. **Actionable for this role.** Someone holding this role would work
   differently for knowing it. Interesting-but-inert facts belong in the
   corpus, which is queryable on demand, not in the base context that every
   session of that role pays for.

5. **Classifiable.** It fits exactly one epistemic class — domain,
   solution, intersection, rationale, workflow or threads. A claim that
   fits none is dropped, not shoehorned into the nearest. A claim that
   seems to fit several is usually two claims that should be split.

6. **A lesson, not a record.** It says what to do or expect next time, not
   what happened once. A fix, a merge, a closed issue, a dated outcome is an
   event, and the tree, git, the PR or the job list already record it; what
   the event taught is the claim. "PR 250 merged the test batch" is a
   record; "a test that reads the committed policy must say so, or a local
   edit passes it" is a lesson.

**The promote verdict.** A claim that passes all six is still weighed for a
stronger home (ADR-015). A lesson that can be a test, a lint rule or a hook
is made one, and its section is deleted: an executable form enforces what a
slice only asks a reader to remember. A `workflow` lesson that stays
replaces its one-off values (a PR number, a branch, a date, a login) with
parameters, so the next session can follow it without the case that taught
it.

## Class boundaries

The classes are not topics; they are kinds of truth, and they decay and
verify differently. Filing a claim in the wrong one is how a role base
starts lying.

- **domain** — true of the field regardless of this system. Verified
  against the discipline. Rarely refreshed. Cross-project evidence is
  allowed here and *only* here.
- **solution** — what this system implements today. Verified against the
  tree. Decays with every merge, so it carries as-of provenance and is
  re-checked on refresh. Code answers "what is"; it never answers "what
  should be" — where code and an active ADR or contract disagree, the
  disagreement is the finding, and the ADR wins.
- **intersection** — where the solution follows the domain and where it
  deliberately departs from it, and why. Cites the governing decisions.
  This is the part a newcomer to the role cannot reconstruct alone.
- **rationale** — reasoning that never made it into an ADR. Explicitly a
  staging area, subordinate to the ADRs: a claim here that contradicts an
  active decision is a discrepancy to report, not a competing authority.
  Entries that prove durable get promoted to an ADR and **deleted here**,
  so this file shrinks over time by design.
- **workflow** — how work is actually done in this role: commands, traps,
  verification steps that are not obvious from the tooling.
- **threads** — known loose ends. Honest about being a backlog, not a
  claim about the system.

## Merge mode

Every drain after the first reads the existing role files first, and they
are the calibration anchor.

- A new claim must clear the bar the existing claims set. If the file
  already says it better, there is nothing to add.
- **Prefer strengthening an existing claim to adding a new one.** More
  evidence, a sharper statement, a corrected detail — these keep a file
  dense. Additions make it long.
- **An empty delta is a correct outcome** and must be reported as such. A
  drain that admits nothing has simply found nothing that clears the bar,
  which is the expected result of a quiet period.
- A claim that contradicts an existing one is not appended alongside it.
  Resolve it: either the world changed (update, with new provenance) or one
  of them was wrong (correct it, and say so in the drain report).

## Language

The role base is written in English, always, whatever language the source
was in. User prompts in particular are frequently not English, and they are
a primary source for `rationale`. Translate rather than quote; mark a
translated quote as translated. A non-English slice found in an existing
role folder is translated in place on the next drain rather than left
alone.

## Telemetry, not quotas

Each drain reports observations in, candidates extracted, claims admitted,
claims merged into existing ones, and claims rejected. A ratio that jumps
an order of magnitude against the drain history is an alarm worth a human
look — the rules may have been misread, or a genuinely dense period may
have happened.

It is deliberately **not** a target. A quota would manufacture exactly the
padding this rubric exists to prevent: told to admit thirty claims, a
distiller will find thirty.
