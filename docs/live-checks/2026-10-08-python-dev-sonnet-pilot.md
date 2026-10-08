# 2026-10-08: does a python-dev session on Sonnet 5.5 do the work as well as on Opus?

The owner asked whether some agents should move to a smaller session model, and then corrected the question: the criterion is the quality the role's work requires, not how much of the weekly allowance it spends.

A python-dev's work is checked from outside by:
- the oracle tests of a port;
- CI;
- a blind review on the review class (Opus 5.5 on plain claude), which stays as it is.

The question is whether the session's own judgement on Sonnet 5.5 produces work that review finds as sound as Opus 5.5's.

## The set-up

- **python-dev-03** (born 2026-10-08) runs its session on `claude-sonnet-5-5`, launched on the anthropic provider (`routing/profiles.json` `agents.python-dev-03`).
  - Its `code-high`, `code-plan` and `code-review` classes stay on the column's models (Opus 5.5).
  - Read back from its own transcripts (`fabric-ctl python-dev-03 tokens`): after the relaunch its requests went to `claude-sonnet-5-5`; the six before it went to `claude-opus-5-5`.
- **Its first job:** stage 2 of the engine split (the `roots` seam), a refactor with no change of behaviour, against the full suite.
- **The control:** python-dev-01 and python-dev-02, same role and same review class, with sessions on `claude-opus-5-5`, over the same period.

## What is measured, per pull request

- Blind-review findings per work commit, by severity: P1 and P2 are what count; P3s are recorded.
- Review rounds until no P1 or P2 is open.
- Findings from the automated review on the PR (Codex threads), by severity.
- CI failures on the PR after its first push.

## What decides

- **python-dev's role default moves to Sonnet** (a `roles.python-dev` layer) if python-dev-03's P1 and P2 per work commit, and its rounds, are within the range python-dev-01 and -02 show on PRs of comparable size.
- **python-dev-03 goes back to Opus** if they are clearly worse; its layer is removed.
- **One PR is evidence, not proof.** The decision waits for its first PR at least; a second is taken if the first is borderline.

## Results

First measurement, 2026-10-08, from the posted blind reviews and Codex threads of three PRs (read by a read-only agent from the PRs, not from the authors' accounts):

| | #119 roots seam (python-dev-03, Sonnet) | #116 forge scripts (python-dev-02, Opus) | #118 human login + job queue (python-dev-01, Opus) |
|---|---|---|---|
| Work commits at the first review | 6 | 13 | 2, then 5 when the queue was added |
| P1+P2 in the first blind round | 2 | 2 | 1, then 3 |
| ... per work commit | 0.33 | 0.15 | 0.5, then 0.6 |
| Rounds until no P1 or P2 is open | 2 | 4 (9 to a round with nothing on the change) | 1 and 1 (3 and 4 to the last P3) |
| Review-fix commits | 4 | 12 | 6 |
| Codex threads | none | 4, labelled P2 | 3: two labelled P1, one P2 |
| A fix round that opened a new finding | no (one P3 flaw in a fix) | yes: four P3s in successive fixes of one shell-line parser | yes: P3s in successive fixes of the claim-outcome hint |

What it shows: on every measure, #119 sits inside the range the two Opus PRs span, and it has the fewest fix commits and no fix round that opened something new. What it does not show: the three PRs are of different kinds (a refactor across readers, a parser-heavy port, a security-relevant provisioning change plus a new protocol), so the comparison is of one PR each; and #119 is not yet merged, so its last rounds after the merge with main are still to come.

By the rule above, python-dev-03's numbers are within the range. The role default moves to Sonnet when #119 merges with no new P1 or P2, on the owner's word, since it relaunches python-dev-01 and -02 on another model; until then python-dev-03 stays on Sonnet for its next PRs (the tools report and `fabric-pr`), which are the second measurement if the owner wants one.
