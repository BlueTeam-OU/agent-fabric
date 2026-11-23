# What the review class's findings carry for judging them — 2026-11-07

ADR-066 proposes measuring the review class like a classifier. Before the
record was written, a throwaway reader asked GitHub how many of the review
class's findings exist in a parseable form and how many carry a judgement
of whether they were real. This is what came back. It decides where the
labels must come from. It says nothing about any reviewer's standing.

**Run.** 2026-11-07, around 12:40Z, on develop-qzapp, with main at
2a374df4, by fabric-coordinator, through `gh` as the fleet's account.
Repository: BlueTeam-OU/agent-fabric only. Input:
`gh pr list --state all --limit 400 --json number,createdAt,reviews,comments`,
which returned 400 PRs created 2026-10-05 to 2026-11-06. A review was
counted when its body (review or comment) contains
`<!-- agent-fabric-review v1 -->` (`post_review.py` REVIEW_MARKER). Lines
were matched as `errors.py` matches them: `^Finding:` and `^Judgement:`
at the start of a line, and fields split on `|`. Prose findings were
matched as `errors.py` FINDING matches them, `**F<n> (P<level>`. The
scripts were throwaway and are not committed; their logic is above.

## Result

- **Marked reviews:** 794.
- **Machine lines** (the shape of `runtime/claude-code/agents/code-review.md`):
  - They appear on 16 PRs, the first created 2026-10-20.
  - 79 `Finding:` lines and 20 `Finding: none`. By level: P1 5, P2 28,
    P3 43, plus 3 whose level field did not read. By confidence: certain
    44, likely 32.
  - 93 `Judgement:` lines: fixed 78, partly 12, not-fixed 3.
    **Real 0, not-real 0.**
- **Prose findings** (`**F<n> (P<level>`): 222 on 45 PRs (P1 3, P2 61,
  P3 158).
- **The phrases** "not real", "judged not real", "false positive",
  "withdraw" and "not a bug/defect" occur 35 times in marked reviews, as
  prose only.

## What it decides

1. **No finding has a parseable judgement of validity.** Every
   `Judgement:` line in the sample answers whether a fix landed, not
   whether the finding was real. The 35 prose phrases show that judgements
   of validity happen, but none reached a form a reader counts. ADR-061
   §7 predicted this gap.
2. **The judgements that do exist are the review class's own.** ADR-020
   §5 rule 1 has a finding judged with the review class. The class's
   verdict on its own finding is the thing to be measured, so it cannot
   also be the ground truth. Labels must come from outside the judge: the
   owner for validity, and an executable test for recall.
3. **Volume is enough for a first calibration.** About 300 findings were
   raised in a month (222 in prose, 79 as lines). A labelled set of 100
   or more is a few weeks of findings, not a quarter's.
4. **The labels must not carry text.** agent-fabric is public, and gzapp,
   whose findings would be among those labelled, is private. A label
   names the finding by its coordinates (repository, PR, review id,
   finding label) and holds the verdict. Whoever computes reads the text
   through `gh` under their own access.

## Also read: gavel, the source ADR-066 ports from

github.com/TechTideOhio/gavel at 27ff6e1d9d7e (MIT, Copyright (c) 2026
TechTide Ohio): `src/classifier.rs`, `src/debias.rs`, `src/dataset.rs`.
The arithmetic was checked by hand against its README table. TPR 0.85
and TNR 0.75 at a true rate of 0.20 give an observed 0.37, and
Rogan-Gladen returns 0.20. Three behaviours are not to be ported as they
are:

- `ConfusionMatrix::tpr()` and `tnr()` return 0.0 when there are no
  positives or negatives. That is undefined, not zero.
- The bootstrap drops a draw whose Youden J ≤ 0.001 without counting it.
  This narrows the interval when the judge is weak.
- `load_dataset` checks a record's hash chain only when `prev_hash` and
  `record_hash` are non-empty. A ledger with its hashes stripped passes,
  so it fails open.
