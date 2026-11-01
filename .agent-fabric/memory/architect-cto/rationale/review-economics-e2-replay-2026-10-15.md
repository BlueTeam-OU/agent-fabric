---
role: "architect-cto"
class: rationale
topic: "review-economics-e2-replay-2026-10-15"
description: "E2 replay of historical re-reviews under the merged P2+P3 review pipeline (2026-10-15): phase 1 six cases, phase 2 27 P2-stratum cases, equivalents 0.45, calls flat, P2 non-inferiority at 2 misses / 7 historical overgrades / 5+ new P2…"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-01"
origin:
  - agent: "architect-cto-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 87777d20d694942a
---

## E2 replay of historical re-reviews under the merged P2+P3 review pipeline (2026-10-15): phase 1 six cases, phase 2 27 P2-stratum cases, equivalents 0.45, calls flat, P2 non-inferiority at 2 misses / 7 historical overgrades / 5+ new P2; transcript sums deduplicate by message id; the corpus-recovery and label-classifier lessons

The replay half of [[rationale-carried-2026-10-28]] (the measurements and the plan of record), split from it on 2026-10-31 because the one memory exceeded the drain's 1800-token claim budget.

E2 phase 1 (2026-10-15, six historical re-reviews replayed under the merged P2+P3, report section 12): no historical P1 existed (the "known P1" strata were "P1: none" lines); all four historical P2 found in substance, two at lower severity; blind adjudication (A/B labelled, one dispatch each) split them: case01 the replay under-graded a real P2 (confirmed; caveat: my adjudication brief added a requirement the originals lacked), case05 the historical P2 was the overstatement (P3 confirmed), so net one under-grade, at the margin on six cases, expand rather than conclude; equivalents 4,150k to 1,658k, raw prompt tokens 21.9M to 10.5M, first-turn context to a quarter in every case; turns NOT down on small ranges (median 1.67x) because pinned evidence costs git show per file and a git archive extract per run that the fence then refuses to delete. Ledger rows do NOT undercount: the "40% short" was my transcript pass summing per record, and a Claude Code transcript writes one record per content block with the message's usage repeated (median 1.80 records per message over 593 review transcripts); case 00's 19 records are 11 messages and the by-message sum equals the row exactly. Only the status was wrong ("cancelled" on a finished hand-back: SubagentStop runs ~0.5 s before the hand-back's tool result is flushed; devex-tooling's bounded re-read, delivered to fabric-coordinator 2026-10-15). Every absolute figure in the report before section 13 is therefore ~1.8x high; ratios hold (phase 1 by message: raw prompt 10.5M to 5.2M = 0.50, equivalents 2,227k to 816k = 0.37, API calls 117 to 132). Rule: a transcript sum deduplicates by message.id before it is believed, and a ledger figure is compared only with one computed the same way (econ/resum.py). Corpus limits: of 96 re-review cases only 12 had commit-id ranges and rendered briefs, 6 of those usable; reports come to the parent as hand-back messages keyed by agent id.

E2 phase 2 corpus (2026-10-15, report section 14, econ/corpus2.py): 210 of 287 historical re-reviews are replayable; ranges came from the rendered brief (105), an inline sha range in a prose prompt (99) or a brief file recovered from the parent session's Bash heredoc (88 of 119 deleted scratchpad briefs are in the parent transcripts; Write calls recovered none). The hand-back report is a later user message in the parent transcript, `<agent-message from="<agent id>">`. Labels need a section-aware classifier: skip the "previous findings" section (answered findings, residues re-filed as new), stop at "pre-existing", count only a P-labelled line that is not "none" or "fixed"; a token count of "P1" mentions is wrong (it counted "P1: none"). Corrected history: 1 live P1, 29 P2, 65 P3, 115 none; 12 cases lack recoverable previous findings. Phase-2 dispatches wait on the coordinator's head worktree (j232).

E2 phase 2 result (2026-10-15, report section 15): 27 P2-stratum re-reviews replayed under the merged P2+P3 build, sums by message id: equivalents 10,781k to 4,882k (0.45; per-case median 0.52), raw prompt 31.0M sent of which 29.5M cache reads, API calls 669 to 671 (median ratio 0.88; fell in 14 of 27). Replay at P2 or above in 18 of 27; all 9 lower cases adjudicated blind (A/B labels at random, one judging dispatch each, no added requirements): 2 real misses (158 Kademlia-not-in-conformance-suite status line; 172 untested 401 path, both runs), 7 historical overgrades where the replay's P3 was right, and at least 5 new confirmed P2 the history lacked. P2 non-inferiority holds at that margin; P1 non-regression rests on one case and stays open. Calls rose only where the brief had no requirements and a prose previous-findings block. Twelve git-archive extracts (13 to 48 MB) left by reviewers, removed by the dispatcher; the head worktree (coordinator j232) is still the fix. Classifier lesson: reports head findings as `**1. [P2, confirmed]`, `Finding N (P2`, `N1 (P2,`, `### F3 — P2`, `P2-1`, `P2 1`; a label grammar for reports would make the count mechanical.

**Why:** the owner's plan of record made every pipeline change quality-first (no P1 regression, P2 non-inferiority, blind adjudication), so the replay is the evidence that P2+P3 may stay; without it the token figures alone would justify nothing.

**How to apply:** compare a ledger figure only with one computed the same way (sums by message id); run a further replay before any further policy change; the P1 non-regression rests on one case and stays open; a label grammar for review reports would make the finding count mechanical.

*References: review-economics-measured-2026-10-14*

*Observed 2026-10-15 (architect-cto)*
