---
role: "python-dev"
class: threads
topic: "j120-review-calibration-state"
description: "j120 fabric-review-calibration reader merged (#498, 73d0f1f5) — decisions, review traps, what stays open"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 86aa3f2052b166f2
---

## j120 fabric-review-calibration reader merged (#498, 73d0f1f5) — decisions, review traps, what stays open

j120 (2026-11-07): `tools/fabric/review_calibration.py`, `bin/fabric-review-calibration`, `tests/test_review_calibration.py` merged as #498 (73d0f1f5; 9 work, 6 fix). Coordinator told (seq 888610); distribution is theirs.

Decisions fixed with the coordinator: half = low bit of sha256 over "repo\npr\nreview\nfinding"; review id = GitHub PR-review id; config of a configuration = sha256 of its instructions, `report` refuses a file matching no configuration and a configuration no file matches; corrected precision per level P1-P3 under the stated assumption that judge accuracy does not depend on level; the level is read via gh from the finding's own `Finding:` line (unreadable reviews and unlevelled findings counted apart, never defaulted); labels.jsonl is committed by the coordinator; McNemar/TOST CLI (`compare`) not built.

**Open:** bootstrap interval never compared draw for draw with gavel's debias.rs; `debias` itself accepts iterations <= 0 as a library call (CLI refuses); gh answers of unexpected shape in candidates/hunk_for could traceback.

**Why:** review rounds kept finding the same class: an unknown value (non-text body, falsy body, null body, a level that cannot be read) must stay "unreadable", never a plausible default, and each such branch needs a test that fails when it is removed.
**How to apply:** for a gh-reading reader, give every untrusted-shape branch its own planted case and a mutation; a PR's CI red before the dependency record (ADR) reaches main is the missing record, merge main and rerun before digging.

*Observed 2026-11-07 (python-dev)*
