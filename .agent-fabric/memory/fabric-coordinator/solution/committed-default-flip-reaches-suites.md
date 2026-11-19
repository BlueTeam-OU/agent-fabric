---
role: "fabric-coordinator"
class: solution
topic: "committed-default-flip-reaches-suites"
description: flipping a committed runtime default (config.json) reaches every suite run on a live account; pin it in tests/run.py run_environment
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 1b7fbe4cd3fab94d
---

## flipping a committed runtime default (config.json) reaches every suite run on a live account; pin it in tests/run.py run_environment

#583 (j793) set `runtime/control/config.json` `control_carrier` to `dual`. The blind review's F1 found that every in-process fabric-ctl suite then read `dual` from the committed file.

Those suites appended fixture replies (`from` h1/a, h1/b, h1/c, h/a) to the account's real `~/.local/state/agent-fabric/agents/<login>/control-arrivals.jsonl`, the source of the parity report, and dialled the live agentd socket. My own full-suite run had already left 12 such rows. They were removed and a backup kept.

The fix follows the existing precedent in `tests/run.py` `run_environment`, which already pins GZCOORD_DEFAULT_LOCALE_ONLY and AGENT_FABRIC_SUITE_RUN. It now also pins `FABRIC_CONTROL_CARRIER=relay`, and `tests/test_run_control_carrier.py` fails if that pin is removed.

**How to apply:** before flipping any committed default that code reads at run time, grep the suites that read it without an override. Pin it in run_environment. Run the full suite after the flip and check the account's state files.

*Observed 2026-11-13 (fabric-coordinator)*
