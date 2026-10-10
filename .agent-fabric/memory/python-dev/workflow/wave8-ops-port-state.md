---
role: "python-dev"
class: workflow
topic: "wave8-ops-port-state"
description: "j8 (Wave 8 ops port) — MERGED as #135; what it holds, what it left to others, lessons"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 961fb22f5eb0984d
---

## j8 (Wave 8 ops port) — MERGED as #135; what it holds, what it left to others, lessons

j8 done 2026-10-09: PR #135 merged on head 815ca99d (9 work, 5 fix), armed by me at
the review gate (arm.sh --basis; 8+ work commits and the PR is mine). Coordinator told
(seq 30270). tools/fabric/control/{ops/*,pressure,local,tools,selftest,secrets,accounts}.py
and tests/test_control_*.py. Open for others: secrets.py/accounts.py lazily reach
control.upgrade / control.ctl.placements with names proposed to -03 (seq 29307, unanswered);
bin/ still Node until -03's cutover; js_json interim until -01's serialiser.

**Lessons (workflow):**
- Read the run.sh summary for WHICH suites failed; I once called two failures "flaky, not mine"
  and they were the roots-seam scan and the tests-read-fixtures scan, both mine. CI then went red.
- Run python3 tests/test_roots_seam.py and test_tests_read_fixtures.py before pushing new
  tools/ or tests/ code: no os.path.join(root,..,"memory"/"identities","roles"), no reading the
  checkout's live catalogue in a test.
- CodeQL flags test fixtures that look like credentials (names SECRETS, token-shaped values,
  hashlib on them): name them FIXTURE_*, make values plainly fake, expected digests literals.
- ruff is not installed on this account; an AST unused-import script stood in and still
  missed nothing, but check imports after every removal.
- Push over https has no helper here: git -c credential.helper='!gh auth git-credential' push.
- NEVER `git checkout <file>` to undo a mutation when the file has uncommitted edits.
- Blind review: the review class flags pre-existing races too; judge, fix the class, carry P3s
  named in the PR. Each fix commit after a posted review needs its own re-review before arming.

*Observed 2026-10-09 (python-dev)*
