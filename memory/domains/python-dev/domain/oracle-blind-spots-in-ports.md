---
role: "python-dev"
class: domain
topic: "oracle-blind-spots-in-ports"
description: Porting a script with its old test as the oracle — the shapes of mutation an oracle passes, and how each was pinned
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - b35f82e6e051b88c
  - ec9fd73c26a4daf0
---

## Porting a script with its old test as the oracle — the shapes of mutation an oracle passes, and how each was pinned

A port's unchanged old test proves parity only where it looks. In agent-fabric's launcher port (88 mutations, one per
behaviour), 5 survived the oracle (the launcher's bash test, 228 assertions; it is tests/test_launch.py now) and a
byte-for-byte --print parity. Their shapes recur:

- **A check made redundant by a later failure with the same status.** The launcher refuses a missing capabilities.json;
  delete that check and the routing load fails a moment later, also exit 1. The oracle asserted the status only. Pin it
  by asserting the exact refusal line, end to end through the shim (a test of the helper alone let the call site's
  mutation through).
- **Two scopes that overlap in the oracle's one scenario.** An inherited REPO_ROOT and the $PWD scope both name the repo
  when the launch is from its toplevel; only a launch from a subdirectory tells them apart.
- **`grep -c` counts lines, not occurrences.** "Only one --effort reaches the child" counted lines of a one-line command:
  two flags passed.
- **A stamp nobody reads.** A trailing bare --effort kept the routed level in the stamp where the bash cleared it; the
  command line was right, so the oracle was too.
- **The environment answered for the code.** A test inherits what the session exports (launch stamps, AGENT_FABRIC_*,
  CLAUDE_*, ANTHROPIC_*) and CI has none of it: a suite that is green in the session can fail on a runner. Run the suite
  with CI's environment, not the session's.

**How to apply:** after the oracle passes, plant a mutation per behaviour and run oracle, differential and Python tests
per mutation; a survivor is a decision to pull into a function and test directly, or a case to add end to end.
Equivalent-looking mutants are rarely equivalent: ask what output differs (a message, a stamp, a non-toplevel cwd). A
finding about the oracle's own weakness goes into a new test beside it, never into the oracle itself during the port.

*Observed 2026-10-10 (python-dev)*
