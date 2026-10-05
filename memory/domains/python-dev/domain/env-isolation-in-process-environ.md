---
role: "python-dev"
class: domain
topic: "env-isolation-in-process-environ"
description: "an oracle's git/env isolation set in a filtered env dict misses fixture calls that pass no env=; set it in os.environ and prove it with a hostile caller config"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-05"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 9e249cbaef09046e
---

## an oracle's git/env isolation set in a filtered env dict misses fixture calls that pass no env=; set it in os.environ and prove it with a hostile caller config

In a Python test that runs subprocesses, isolation like GIT_CONFIG_GLOBAL=/dev/null
set only in the filtered `env` dict reaches the script under test but not
fixture calls written without `env=` (they inherit os.environ). Found on
agent-fabric #85 (commit 707444f): fabric-fresh, fabric-status and post-review
oracles had such calls. Set it once in the script's own `os.environ` near the top.

**Why:** a per-dict fix looked complete and passed every normal run; only a
hostile control (caller GIT_CONFIG_GLOBAL with core.hooksPath at failing hooks)
showed three of six suites still read the caller's config.

**How to apply:** for any env isolation in a test, plant the hostile value in the
caller's environment and run the suite before and after; the "before" must fail,
the "after" must pass.

*Observed 2026-10-02 (python-dev)*
