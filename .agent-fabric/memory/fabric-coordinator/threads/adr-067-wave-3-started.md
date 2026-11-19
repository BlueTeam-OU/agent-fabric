---
role: "fabric-coordinator"
class: threads
topic: "adr-067-wave-3-started"
description: "Where the ADR-067 architecture plan stands: Waves 1-2 done (all six mechanisms enforced), Wave 3 started by the owner 2026-11-09; who holds which part"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 86f0087fd0fecb5f
---

## Where the ADR-067 architecture plan stands: Waves 1-2 done (all six mechanisms enforced), Wave 3 started by the owner 2026-11-09; who holds which part

The owner said "start wave 3" on 2026-11-09, around 21:15Z. The plan is ~/.claude/plans/i-think-you-should-swift-frost.md; its Status sections are the running log.

- **Waves 1-2: done.** policies/mechanisms.json on main has all six mechanisms `enforced`, and ADR-067 §7 says "no mechanism is planned now".
- **W3-A stage 2:** python-dev-01, j222 (REQUEST 01a1c224-5580). It characterises the roots bypasses, moves them, and writes a checker. My j724 folds the wiring.
- **W3-A stage 3:** the owner created `BlueTeam-OU/blueteam-fabric` on 2026-11-10 (private, empty; read back). That is the operator repository, distinct from `BlueTeam-OU/agent-fabric-settings` (per-org arming policy only); `docs/split/inventory.md` still names `gzapi-org/blueteam-fabric` and is corrected in j725's PR, with an ADR-045 amendment saying where the settings repos stand. My j725, raised to high.
- **W3-B dispatcher:** my j723. ADR-068 written 2026-11-09 (6b8ba953, 95dadbcb on develop-qzapp/user/feat/j723-wave-3-w3-b-write-the). Build contracted to python-dev-04 (REQUEST 01a1c23e-04e9). My supplies onto their branch: the `fabric` table in commands.json (generator kept at ~/.local/state/agent-fabric/agents/user/j723/make_table.py; it reformats the file, so insert the section by hand), user-settings rule generator, the two hooks onto canonical(), mechanisms.json entry + exceptions, lint wiring, ADR-067 amendment (its §7 says no mechanism planned). Hazard the record fences: a second spelling walks past post-review-shape-guard and job-copy-guard unless they move in the same PR.

**Why:** the owner asks "which wave" without notice. Answer from mechanisms.json on origin/main, not from the plan file.
**How to apply:** j717 and j723 are set to `blocking`, ahead of j699, which is paused. Related: [[owner-arm-word-j674-plan]], [[j675-w2a-job-lifecycle-contract]].
- **j723 supply started (2026-11-10 ~04Z):** python-dev-04's j107 branch was never pushed; I created it on origin from main 0727ffb6 with the table (d3273d90, spliced by text, `commands.fabric` and its not_allowed reason held back to the rule-generator commit) and merged my ADR-068 branch onto it (80038dd1), so the record rides their PR. REPLY 01a1c360. j723 is blocked in free text until canonical() lands there. Supply commits are made in the job copy (switch to their branch there; the job-copy guard refuses a scratch worktree), see [[supply-onto-pr-branch-in-job-copy]].
- **j728 (legal fold, 2026-11-09):** both for/ branches (legal-expert-ch d0060b2e, legal-expert-ee-eu 8bbe03b6) read and fine, docs/legal only; fold them unrebased onto the j723 branch, which is my one open-PR branch (no PR opened yet; the suite run on it was cut by the switch, rerun before review).
- **j723 supply, 2026-11-10 ~07Z:** on python-dev-04's j107 branch (job copy switched to it): a3aa8b2b user-settings rule generator + `fabric` in commands/not_allowed (38 allow, 0 ask; owns the `Bash(fabric ` namespace whole), 10a926f8 ADR-067 seventh mechanism `command-recognition` (ADR-Editorial). Workers out: the three hooks (post-review-shape, job-copy, inbox-watch) onto canonical(); lint/pre-commit wiring + policies/command-names.json (admits agent_fabric_dir_authority.py, commit_hooks.py: trailer key / gpg.program, not Bash lines).
- **j723 supply delivered 2026-11-10 ~08Z:** pushed onto python-dev-04's j107 branch, head a7241297 (a3aa8b2b settings rules, 10a926f8 ADR-067, 970c7018 lint/pre-commit wiring, a5292a14/b9a83085/0cf36085 hooks onto canonical(), a7241297 inbox-watch reads by file name). REPLY 01a1c474. Left to python-dev-04: two F401 in tests/test_fabric_cli.py, suite, review, merge. Mine after merge: distribute, ADR-068 rule 9 live check under docs/live-checks/ (allowed form runs, not_allowed target asks), then the skills/docs/auto-mode.json rewrite.

- **j762 (2026-11-11 09:14Z, python-dev-02 REPLY 01a1c9e2):** #555 opened by python-dev-02 with 1 work commit, unarmed, blind review next. `prepare()` now requires the pinned fabric-python, and the host floor is removed. A for/user supply waits for me to fold onto the j706 branch: `develop-qzapp/python-dev-02/for/user/langid-venv-on-the-pin` at 4c9cde1d (langid venv on sys.executable). Mine on the same branch with j763: `.github/workflows/ci.yml:199` still gates on detect.sh `host_python_ok` (3.13), which AlmaLinux's 3.12 fails.
- **j723, 2026-11-11 12:25Z:** managed snapshot still fabric-80e612ff (`bin/fabric-managed check`: drifted, 39 paths) against main 6339a4b5. j723 blocked in free text on the owner's `sudo …/bin/fabric-managed install --sha 6339a4b5…`; the read-back and skills/docs rewrite start only after check says in force, see [[adr-068-managed-reinstall-gates-readback]].

*References: adr-068-managed-reinstall-gates-readback, j675-w2a-job-lifecycle-contract, owner-arm-word-j674-plan, supply-onto-pr-branch-in-job-copy*

*Observed 2026-11-10 (fabric-coordinator)*
