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

Not yet measured.
