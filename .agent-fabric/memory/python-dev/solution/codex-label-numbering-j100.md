---
role: "python-dev"
class: solution
topic: "codex-label-numbering-j100"
description: "j100 #446 — Codex full review numbers past the PR's labels via review_brief.carried_findings; mock-gh traps, arm needs no word at count rule 1"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "python-dev-03"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - c67374c90db1fabb
---

## j100 #446 — Codex full review numbers past the PR's labels via review_brief.carried_findings; mock-gh traps, arm needs no word at count rule 1

#446 (merged 2026-11-01): `review_codex.label_start(req, head, pr)` reads the reviews with `review_brief.carried_findings(int(pr), ...)` (the CLI's PR, never `req["pr"]`, which `load_request` lets a request override) AFTER the Codex run. Before the run would break the tests that expect an unavailable statement to post whatever GitHub answers.

**Why:** two engines posting one label for two findings broke the arm gate's chains.

**How to apply:**
- Any suite that fakes `gh` for a full Codex review (`test_review_codex`, `test_review_gateway`) must answer `gh api -i .../reviews` (status line, blank line, flat JSON list) and `pr view --json author`. A new gh call in review_codex turns up as "reviews cannot be listed" in every such stand-in.
- Raw-string mock scripts: write `\r\n` once, not `\\r\\n`.
- `fabric-pr arm --dry-run` printed no minimum here; the real count rule was 1 work commit, and arm said it did not read the authorization. Read `arm: count rule:` from a real arm or `fabric-pr gate` before asking for a word.
- `fabric-review next` wants `--pr N` (not `--report`), a prior `fabric-review save N ROUND < report`, and the derived `req-rrN.json` from the previous `next` as the request for the following round.
- `test_launch.py` (empty AGENT_FABRIC_RESTART_WAIT_S) fails on clean origin/main; fedora platform-smoke `test_jobs_switch` flaked once and passed on `gh run rerun --failed`.
- Hook trap: a command that both uses `$VAR` paths and commits/posts is refused as "in $HOME"; use literal paths, one commit per call.

*Anchors: `tools/fabric/review_codex.py::label_start`, `tests/test_review_codex.py::HTTP/2.0 200 OK`*

*Observed 2026-11-01 (python-dev)*
