---
role: shared
class: workflow
topic: "prefer-python-over-shell"
description: "Fabric tooling is Python above 150 lines, stdlib only, on fabric-python (ADR-040); ad-hoc logic goes in python3 heredocs"
tier: 1
knowledge_scope: full
shared_with:
  - "fabric-coordinator"
  - "python-dev"
distilled_at: "2026-10-10"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 2daef4d9679a1131
  - 9772e263a18eef83
---

## Fabric tooling is Python above 150 lines, stdlib only, on fabric-python (ADR-040); ad-hoc logic goes in python3 heredocs

The owner's 2026-09-29 preference ("better if you use python than shell scripts") is ADR-040: lint refuses a tracked bash script over 150 lines unless it is on the allowlist, which is now empty; new tooling is Python, standard library only, on the pinned `fabric-python`. The existing bash was ported wave by wave, not lazily; what stays bash is shims, forwarders, hook entry points and suite runners (§5 rule 1).

**How to apply:** a new tool is `tools/fabric/*.py`; a bash file past 150 lines does not pass lint. Ad-hoc logic in a session (parsing, loops with error handling) goes in `python3 - <<'PY'`, not chained shell.

**Why:** shell had exactly the bugs Python makes explicit: a `command -v` finding a function instead of the binary, a timeout's exit code swallowed by `|| true`, `$?` gates spread over lines, heredoc quoting. See [[a-wrong-why-outlives-the-code]].

*References: a-wrong-why-outlives-the-code*

*Observed 2026-10-10 (fabric-coordinator)*
