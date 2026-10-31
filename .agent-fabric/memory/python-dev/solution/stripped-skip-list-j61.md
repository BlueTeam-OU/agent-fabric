---
role: "python-dev"
class: solution
topic: "stripped-skip-list-j61"
description: "stripped_run --skip-list design, which files were red and why, and the long-TMPDIR trap for AF_UNIX tests"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-03"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 8607c6b417ff645a
---

## stripped_run --skip-list design, which files were red and why, and the long-TMPDIR trap for AF_UNIX tests

j61 (branch develop-qzapp/python-dev-03/for/user/stripped-skip-list, 3873aca3): `tests/stripped_run.py --skip-list` fails an unlisted red file and a listed file that now passes; a malformed list (no reason, repeat, missing path, KNOWN_RED path) is exit 2. Red on a stripped copy at b3f2dcb5 and not deliberate: test_gateway_plan (j62), test_repo_settings_cli (j63), test_session_start and test_subagent_ledger (j64); causes of j64 not yet found.

**Why:** a full stripped run takes about 45 min under load, and any test that opens an AF_UNIX socket (bootstrap_internals, secret_store, control_secrets, control_local_selftest) fails with "path too long" when TMPDIR is long, as this login's scratchpad is.
**How to apply:** run the stripped run with a short `TMPDIR=/var/tmp/<x>`; check a candidate red file unstripped in the same env before listing it; run `tests/run.sh python` with only AGENT_FABRIC_*, GITHUB_*, GIT_DIR stripped, not `env -i` (that breaks test_review_rounds' account lookup). See [[test-children-hygiene-and-surviving-mutations]].

*References: test-children-hygiene-and-surviving-mutations*

*Observed 2026-10-19 (python-dev)*
