# ADR-066 — The review class is measured like a classifier: owner labels for its judgements, seeded defects for its recall, every rate with its interval

**Date:** 2026-11-07
**Status:** Accepted
**Ratified:** owner, 2026-11-07, in the coordinator's session ("accepted"), carried by the pull request that marks it Accepted
**Decision Makers:** the owner; drafted by fabric-coordinator
**Scope:** how well the review class judges and finds. The ground truth it is measured against (owner labels, seeded defects), the configuration a result belongs to, the rates and their intervals, the split that keeps tuning from leaking into the measure, and what a change to the review class's routing or instructions must show. The reader `fabric-review-calibration` and the code it ports. Not who erred (ADR-061), not cost (ADR-036)
**Pillar:** P3
**Evidence:** docs/live-checks/2026-11-07-review-findings-judged.md

## 1. Context and Problem

Every PR's head is reviewed by the review class before it is armed, and
every finding is judged with the review class before it is answered
(ADR-020 §5 rule 1). The review is the fabric's main quality control. Its
own quality has never been measured: nothing says how often a finding is
real, how often a real defect in a range goes unfound, or whether a
change of the class's model, effort, engine or instructions made it
better or worse. ADR-005 §5 rule 10 reads a model back as *served*
before it enters routing. Nothing reads it back as *reviewing well*.

The live check shows what the artifacts hold. There are 794 marked
reviews over 400 PRs in a month, about 300 findings, and 93 `Judgement:`
lines. All 93 judge whether a fix landed (fixed, partly, not-fixed).
None says whether a finding was real; that happens in prose, 35 times,
in no form a reader counts. More fundamentally, those judgements are the
review class's own. The verdict on a finding is the thing to be
measured, so it cannot also be the ground truth.

The method exists outside the fabric: treat an AI judge as a binary
classifier. Hold human labels, split them into tuning and held-out
halves, report the true-positive and true-negative rates on the held-out
half with intervals, require the critique before the verdict, pin the
model, and correct any observed rate for the judge's measured error
(Rogan-Gladen). The MIT-licensed tool gavel implements it in a few
hundred lines of Rust that can be ported. A paired exact test on the
same items says whether two configurations differ beyond noise (plumb,
weir), and running each case several times separates "found once" from
"found every time" (temper).

## 2. Decision

The review class is measured **per configuration**, against ground
truth that does not come from the review class, and every rate is
published with its interval and its count.

- **A configuration** is everything that decides how a review reads: the
  engine (the review class, or Codex under ADR-053), the resolved model
  id, the effort, and the sha256 of the reviewer's instructions (the
  rendered `code-review.md`, or the Codex brief template). A result
  belongs to one configuration. A change to any part starts a new one.
- **Ground truth** has two sources, one per question:
  1. **Is a finding real?** The owner labels it `real`, `not-real` or
     `unsure`, blind: shown the finding, its hunk and the range, never
     the engine, the model, the author's reply or any judgement.
  2. **Did the review find the defect?** A **seeded defect**: a merged,
     sha-pinned range of a public managed repository, with one defect
     planted and a test that fails on the planted tree and passes on the
     original. The test is the truth, so no one labels.
- **Three rates:**
  1. **Adjudication agreement.** A fresh review-class dispatch judges
     labelled findings (`Judgement: … | real` or `not-real`). Against
     the owner's labels this gives its true-positive and true-negative
     rates, Cohen's κ, and Youden's J, each with a Wilson 95% interval.
  2. **Finding precision.** The share of findings that are real, per
     level (P1, P2, P3). Measured directly on owner-labelled findings.
     On the far larger unlabelled population it is the adjudicated rate
     corrected by Rogan-Gladen with rate 1's numbers, with a bootstrap
     interval.
  3. **Seeded recall.** The share of seeded defects named by a finding,
     with each range reviewed three times: found in a given run
     (pass@1), and found in all three (pass^3). A finding names a seeded
     defect when its path and line fall inside the planted hunk, which
     is decided by code with no judgement.
- **One use, as evidence.** A change to the review class's routing
  (model, effort, engine) or to the parts of its instructions that find
  and judge carries a comparison with the configuration it replaces, on
  the same held-out items. The comparison is a paired exact McNemar test
  on seeded-defect outcomes and on adjudication agreement; when the
  change is a cost cut, an equivalence margin (TOST) is added. The
  comparison goes to the owner, who decides; it gates nothing by itself.

## 3. Alternatives Considered

- **The review class's own judgements as the truth.** Free, and already
  in every PR. Rejected because it is circular. A judge measured against
  itself always scores perfectly, and the live check shows those
  judgements are the only ones there are.
- **Codex as the labeller.** Cheap and independent of Anthropic's
  models. Rejected as ground truth: two model judges share error modes
  (a plausible argument persuades both), and agreement between them
  says nothing about whether either is right. Kept as a reported number,
  the claude–Codex κ on the same findings, which ADR-053 makes
  available.
- **The author's response as the label** (fixed means real, declined
  means not real). Rejected. An author fixes in order to arm, so a fix
  is not evidence that the finding was real. A decline is the author's
  own interest, and declines are rare.
- **Seeded defects for precision too.** Rejected: a planted range says
  what was missed, not whether the findings raised on real code are
  real. Precision needs findings on the code the fleet actually writes.
- **Natural misses (reverts and fixes forward, ADR-061 kinds 3 and 4) as
  recall.** Real, and free. Not the measure, because whether the review
  could have seen a defect that surfaced later is itself a judgement.
  They are reported beside seeded recall as candidate misses, with
  their count.
- **Run gavel itself** (its binary, or a dependency on its crate).
  Rejected. The repository is days old with no review history, it would
  put a Rust toolchain on the control plane's path, and its release
  ships without a checksum. The useful part is about two hundred lines
  of arithmetic, which are ported to Python with their notice (§5 rule
  10), with the three defects the live check found fixed.
- **Keep arguing quality from incidents.** That is the present state,
  and it leaves a routing change for the review class decided by one
  read-back and a feeling.

## 4. Rationale

The review class gates every merge, so its errors compound across the
fleet. A false finding costs a fix cycle, and a missed defect costs a
revert. Both are invisible today. Splitting the question in two lets
each half have honest ground truth: a person for "is this real" (only a
person can say that without being the judge), and a test for "was it
found" (only a planted defect has a known location). Keying results to
the configuration, including the instructions' hash, means a result
can never be read as describing a review it did not measure.

Intervals are the point, not decoration. At 50 held-out labels a rate of
80% has a Wilson interval about ±11 points wide, so the first periods
answer coarse questions ("is precision above two thirds?"), not fine
ones. A rule that publishes counts below a floor keeps a thin sample
from posing as a finding. The paired test is what makes a small sample
usable at all: it spends its power on the items where two
configurations disagree.

The owner's time is the scarce input. About a hundred findings, read
with their hunks, buys the first calibration. After that, labels are
added at the rate findings arrive, and the hash split keeps every added
label's half fixed.

## 5. Binding Rules

1. A result is keyed by its configuration as §2 defines it: engine,
   resolved model id, effort, and the instructions' sha256. A reader
   never reports a result under a configuration it was not measured
   with, and never pools two configurations.
2. Ground truth for validity is the owner's label, entered blind. The
   label view shows the finding's summary, its hunk and the range, and
   never the engine, model, author reply or any `Judgement:`. A label is
   `real`, `not-real` or `unsure`. An `unsure` label is counted and kept
   out of every denominator. A review-class or Codex verdict is never a
   label.
3. Labels live in `docs/review-calibration/labels.jsonl`, one line per
   finding. A line holds the finding's coordinates (repository, PR,
   review id, finding label), the verdict, the date, the labeller, and
   a sha256 chaining it to the line before. It holds **no finding text**:
   the repository is public and the findings are not all from public
   repositories. The reader refuses a ledger with a missing or broken
   chain hash. It never skips a line that has no hash.
4. Each labelled finding's half is `sha256(coordinates) mod 2`: dev or
   held-out. The half is fixed for good, whatever labels are added
   later. The judging and finding parts of the reviewer's instructions
   may be changed on dev evidence. A held-out finding is never quoted in
   an agent file, a brief template, a review card, a slice or a memory,
   and the reader refuses a run in which a held-out finding's summary
   appears in the configuration's instructions.
5. Adjudication for calibration is a fresh review-class dispatch, never
   the judgement made while the PR was open. It sees no owner label. It
   writes its reasoning for each finding before the machine lines, as
   `code-review.md` already orders a report. `partly` counts as `real`
   for the binary rates and is reported apart.
6. Rates 1 and 2 are published for a configuration only when its
   held-out half holds at least 20 `real` and 20 `not-real` labels.
   Below that the counts are published and the rate is not. Every rate
   carries its Wilson 95% interval (rate 1, rate 3 and labelled
   precision) or its bootstrap 95% interval (corrected precision). The
   corrected value is shown beside the raw Rogan-Gladen value and the
   number of bootstrap draws discarded as degenerate.
7. Seeded defects live under `tests/review-calibration/defects/`. Each
   is a sha-pinned range of a public managed repository, the planted
   patch, and the test that proves it: the test fails on the planted
   tree and passes on the original, and the suite checks both. Defects
   are planted by a writing class from the kinds of P1 and P2 findings
   seen in the fleet, and split dev or held-out by the same hash rule.
   A seeded range is reviewed with an ordinary brief whose objective
   does not mention the plant.
8. Each held-out seeded range is reviewed three times per configuration.
   Recall is reported per run (pass@1) and all-three (pass^3), with
   Wilson intervals, beside the count of candidate natural misses
   (ADR-061 kinds 3 and 4 on reviewed PRs in the period).
9. A PR that changes the `code-review` class's routing, or the finding
   or judging sections of its instructions, states in its body the
   calibration comparison between the configuration it replaces and the
   one it brings, on the same held-out items. The comparison is the
   exact McNemar p-value on paired seeded outcomes and on paired
   adjudication outcomes; for a change argued as cheaper, a TOST
   equivalence test at a 5-point margin. An underpowered comparison is
   reported as underpowered, never as equal. The owner decides; lint
   does not gate this until §7 says it does.
10. The reader is `fabric-review-calibration`
    (`tools/fabric/review_calibration.py`), Python standard library
    only. It ports from gavel at 27ff6e1d9d7e (MIT, Copyright (c) 2026
    TechTide Ohio): the confusion matrix and its rates (TPR, TNR,
    precision, κ, MCC, Youden's J), the Wilson interval, the
    Rogan-Gladen estimator with its parametric bootstrap, and SplitMix64
    to seed the bootstrap so a run reproduces. The MIT notice is kept
    through `REUSE.toml` and `LICENSES/MIT.txt`. Three behaviours are
    changed and each has a test: a rate with no denominator is undefined
    (`None`), never 0.0; discarded bootstrap draws are counted and
    reported; and the ledger fails closed (rule 3). The exact McNemar
    and TOST tests are written from their formulas with `math.comb`.
11. The results are about a configuration, never an actor. A calibration
    report names no PR author and is never read as an error count of
    the agents whose PRs were reviewed (ADR-061 §5 rule 6).

## 6. Consequences

- A routing change for the review class becomes an argument with
  numbers, both ways. A cheaper model that holds recall and agreement
  within the margin can be shown to; one that loses a third of the
  seeded defects can be shown to as well.
- The review class's instructions gain a held-out half that tuning must
  not touch. Rule 4 makes "fix the instruction on the example that
  failed" a dev-only move.
- The owner's labelling is a recurring task, about a hundred findings
  for the first calibration and a trickle after it.
- Each calibration run costs review dispatches: three per held-out
  seeded range per configuration, plus the adjudication batches. A
  comparison doubles that, since both configurations run.
- `Judgement:` gains its first `real` and `not-real` lines, written by
  calibration dispatches. ADR-061's reader will see them too, and must
  keep calibration dispatches out of its per-actor counts, because they
  judge old findings, not a PR under review.

## 7. Future Evolution

- When three periods of rule 9 comparisons exist, decide whether lint
  refuses a review-class routing PR without one.
- Pairwise comparison of two engines' reports on the same range (each
  judged twice with the order swapped, only consistent verdicts
  counted) if the owner wants claude and Codex ranked against each
  other, not only each against the truth.
- Seeded ranges from private repositories, once a defect set can live
  in the repository it was cut from.
- ADR-061 §7's parseable judgement line for every PR, which this record
  supplies for calibration only, may become the ordinary way a finding
  is judged.

## 8. Decision Status

Accepted. The reader is requested of python-dev, the labelling run is
the owner's, and the first seeded defects are requested of a writing
class.

## References

- ADR-005 §5 rules 6 and 10 (the review-grade set; read back before
  routing), ADR-020 §5 rule 1 (a finding judged with the review class),
  ADR-026 (verified results, artifacts only), ADR-036 (cost), ADR-053
  (Codex as a second engine), ADR-061 (errors per actor; §7 the missing
  judgement line), ADR-065 (pinned review tools, coverage).
- `runtime/claude-code/agents/code-review.md` (machine lines),
  `tools/fabric/errors.py` (their reader),
  `tools/fabric/github/post_review.py` (REVIEW_MARKER).
- github.com/TechTideOhio/gavel at 27ff6e1d9d7e (`src/classifier.rs`,
  `src/debias.rs`, `src/dataset.rs`), MIT. The method: Rogan and
  Gladen, 1978; McNemar, 1947; Wilson, 1927; Chen et al., 2021
  (pass@k); Yao et al., 2024 (pass^k).
- `docs/live-checks/2026-11-07-review-findings-judged.md`.
