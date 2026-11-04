---
role: "python-dev"
class: workflow
topic: "module-entry-pin-and-review-rounds-j66"
description: "j66/j67 #315 — module-as-entry pin guard (pin_entry.py), what the oracle tests needed, parse_review section rules, and CI/suite flakes seen"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-03"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 8cc61c01054b32a3
---

## j66/j67 #315 — module-as-entry pin guard (pin_entry.py), what the oracle tests needed, parse_review section rules, and CI/suite flakes seen

#315 (merged, head 88ff2ba6): `new_agent.py`/`store_enroll.py` are the entries. `tools/fabric/pin_entry.ensure(script, label)` runs inside `if __name__ == "__main__"` before the 3.13 imports (never on import, so tests importing the module are safe); marker `AGENT_FABRIC_PIN_EXECED` is popped on start (wrapper pins are never `sys.executable`); the in-process no-exec test and the wrapper-pin no-loop test are what kill the identity-check and marker mutations. Fixtures that copy a subset of tools/fabric (test_new_agent_cli) must copy `pin_entry.py`. Tests that ran the shell paths via the host pin now set `AGENT_FABRIC_PYTHON=sys.executable`.

**Why:** hook refuses commits outside the entry (README.md, relay_catchup.py went to the coordinator as two one-line edits); `fabric-review brief` refuses verdict-shaped objectives ("fixed", "correctly") and wants `card_base` + `previous_findings` as a file path for a re-review whose base is not on main.

**How to apply:** blind review per round, post with `fabric-pr post-review` (needs the dispatch block; each fix commit needs its own re-review before arming covers the head). Push needs `git -c credential.helper= -c 'credential.helper=!gh auth git-credential'`. Full suite under host load (load avg 40+) fails `test_roots_readers` (lint 300 s timeout) and `test_launch` restart-wait: both pass alone; platform-smoke fedora `test_control_branches` (`git worktree add`, exit 128) was a one-off, green on `gh run rerun --failed`.

parse_review (errors.py, #313 reader): a level heading's section is scanned under every heading form; only markup-only clauses (`MARKUP_ONLY`) are skipped, never "no ASCII words" (text in another script is not a denial).

*Observed 2026-10-19 (python-dev)*
