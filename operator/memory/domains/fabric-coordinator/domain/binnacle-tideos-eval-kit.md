---
role: "fabric-coordinator"
class: domain
topic: "binnacle-tideos-eval-kit"
description: "binnacle / TideOS Eval Kit: MIT pure-Rust dispatcher over 15 agent-eval CLIs (error analysis → judge calibration → paired stats → CI gate → close the loop); not adopted (8 days old, 0-star tools, README-level claims, Windows-built…"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 279ec22f979b55f5
---

## binnacle / TideOS Eval Kit: MIT pure-Rust dispatcher over 15 agent-eval CLIs (error analysis → judge calibration → paired stats → CI gate → close the loop); not adopted (8 days old, 0-star tools, README-level claims, Windows-built, unverified installer); borrow pass^k, critique-before-verdict, paired McNemar, CPST, the 15-step loop as a map of the fabric's gaps

github.com/<owner>/binnacle (an organization account), read 2026-11-07 through `gh api`. It is MIT and 26 stars, created 2026-11-05. The code is about 250 lines of Rust: a table of 15 steps, a binary finder (`../<tool>/target/release`, `~/.cargo/bin`, PATH), `run <tool|step>`, which execs the tool and wraps it in `{step, tool, binary, exit_code, passed, stdout, stderr}` (passed = exit 0), and `doctor`, which checks that each tool answers `--help`. It adds no scoring. The 15 tools are separate repos in the same org, created 2026-10-30 to 11-05. Each has 2 to 11 commits, 0 stars, and 22 to 206 KB of Rust. The READMEs are in a heavy marketing voice. The recorded runs come from `C:\Users\Admin\...`. `install.sh` downloads the latest release tarball with no checksum and falls back to an unpinned `cargo install --git`. I verified the code of binnacle only. The tools' claims are README-level, though the worked numbers I recomputed are correct (gavel's Rogan-Gladen table, plumb's McNemar p-values).

**Not adopted.** The kit is too new and unproven, and it is aimed at product LLM apps (prompts, RAG, chat). The fabric's subject is agents doing engineering work through PRs. The value is in its method.

**The 15 steps against the fabric:**
1. **reval: error analysis.** It codes failure traces (open coding), then clusters them into categories (axial coding) and counts them. Its top 3 categories become the first metrics. Fabric: the reflection passes and the drain hold the open codes (memories), but nothing counts them. Gap: count review-finding and memory categories so the top 3 become guards.
2. **gild: golden dataset.** Cases are stratified with explicit weights, and the prompts and rubrics are sha256-locked. Fabric: `tests/run.sh` covers code, but nothing like it exists for agent behaviour.
3. **tessel: pairwise covering arrays.** It shrinks the 12,000 combinations of dimensions to about 97 tuples that cover every pair. This could serve as a test matrix for launch combinations (provider × class × host × harness).
4. **assay: deterministic assertions first.** A negative check fails closed when its evidence file is missing or empty. Fabric: this is its own rule, that a guard which passed by never running is no guard.
5. **tide-rill: retrieval measured apart from generation.** It reports recall@k, MRR and nDCG over judged queries, with a per-query worst-case floor. Gap: `memory_find` has never been measured. Related: [[claude-mem-and-recall-zero]].
6. **keel: trajectory evaluation.** It scores tool-call precision and recall, order (LCS) and efficiency, where 14 calls against 3 optimal counts as a cost bug. Fabric: "compute, then read" is prose only.
7. **temper: pass@k against pass^k.** pass@k is success at least once in k runs, pass^k is success in all k runs. At 80% per run, pass^5 is about 33%. It also flags runs recorded at a temperature other than the deployed one. Fabric: flaky suites ("passes alone, fails under load") are a pass^k problem.
8. **parley: simulated users.** It covers hidden constraints, amnesia across turns, and giving way under pushback. Fabric: the gzcoord-receive rule to refuse an undo that states no defect.
9. **gavel: align a judge like a classifier.** It needs 100+ labels and a train/dev/test split, reports TPR and TNR, puts the critique before the verdict, rejects unpinned models, and corrects the observed rate with Rogan-Gladen. Fabric: the review class is a judge whose accuracy has never been measured. Past findings, with their outcomes (fixed, declined, deferred), are the labels.
10. **poise: pairwise bias.** Every A/B comparison runs twice with the order swapped, and only consistent verdicts count. A length-controlled win rate removes the verbosity advantage. This would apply to claude-against-codex comparisons.
11. **plumb: paired statistics.** On the same items it uses exact McNemar, a bootstrap CI and TOST equivalence. 80% → 83% on 100 items is noise. Fabric: any routing change (a class's model or effort) is a "model release" decided without this.
12. **weir: per-category CI floors.** A gain in one category cannot hide a loss in another, and the gate runs only when trigger paths change. Fabric: `fabric-pr arm` boundary.paths is the trigger half.
13. **eddy: online evals.** It samples deterministically with `sha256(salt:id) mod 10000 < rate`, weights by inverse probability, uses a per-category CUSUM and runs shadow candidates. This could sample sessions or PRs for audit.
14. **tare: cost per successful task.** CPST = total cost / passed tasks, with p95 latency and a three-way Pareto gate. Fabric: `fabric-usage` measures windows, not cost per delivered job by class.
15. **tether: close the loop.** No bug closes without a reproducing case. Failures are captured with secrets scrubbed and SimHash-deduplicated. A 20% held-out split guards against overfitting, and a stale suite blocks a release. Fabric: "fix the rule, not the instance", "a guard is three things", the hygiene drain. The SimHash dedupe could serve the drain's near-duplicate slices.

**Worth borrowing first:**
- (a) Measure the review class (step 9) from finding outcomes already on GitHub.
- (b) Decide routing changes by paired tasks and CPST (steps 11 and 14), not by single runs.
- (c) A retrieval eval for `memory_find` (step 5).
- (d) Critique before verdict in the review report's format.

Related: [[external-tools-evaluated]], [[ifixai]].

*References: claude-mem-and-recall-zero, external-tools-evaluated, ifixai*

*Observed 2026-11-07 (fabric-coordinator)*
