# Review card — agent-fabric (ADR-020; the only project text a reviewer gets)

## Run, from the tree as it is (no install)
- Suites are plain scripts, not pytest (not installed): `python3 tests/test_<x>.py` (ok/FAIL lines, non-zero exit on failure); bash suites `bash <dir>/test_<x>.sh`. `tests/run.sh python | bash | static | all` runs them; the python section ends `FAILED_SUITES=<n>`, 0 is the pass, the others end "all suites passed" or "N suite(s) FAILED".
- Bash suites sit beside what they test: `runtime/claude-code/test_*.sh`, `runtime/claude-code/hooks/test_*.sh`, `policies/test_*.sh`. Static: `bash -n`, `shellcheck -S error`, `ruff check .`.
- Lint: `AGENT_FABRIC_ROOT=$PWD python3 tools/fabric/lint.py` (judges the checkout it names).

## What is authoritative
- `docs/adr/` with `DIGEST.md`: an amendment is body, history note under `docs/adr/history/`, Amendments row and DIGEST line, with `python3 tools/fabric/adr.py index --write` clean, in one range; `fabric-adr lookup <topic>` finds the record.
- Schemas under `identities/schemas/`, `projects/schemas/`, `routing/schemas/` (`*.schema.json`) are the shapes; the code validates against them, never the reverse.
- Only fabric-coordinator commits here (and `.agent-fabric/` anywhere), except the contributor paths in `policies/authority.json`. Every commit carries `Fabric-Role:` and `Kind:` trailers; no machine attribution anywhere.

## Invariants every review holds
- A credential never enters a committed file, a message, a log or a test fixture; a secret is named by shape and locator.
- Every refusal names what it refused and why; silence is never a pass; an op's answer stays within its budget.
- A guard decides from the fields it can see and never from prompt text.
- A test that cannot fail is a finding: name the production mutation it would catch.
