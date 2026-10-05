---
role: "python-dev"
class: domain
topic: "oracle-blind-spots-in-ports"
description: Porting a script with its old test as the oracle — the shapes of mutation an oracle passes, and how each was pinned
tier: 2
knowledge_scope: full
distilled_at: "2026-10-05"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - ec9fd73c26a4daf0
---

## Porting a script with its old test as the oracle — the shapes of mutation an oracle passes, and how each was pinned

A port's unchanged bash test proves parity only where it looks. In
agent-fabric's Wave 4 (the launcher, 2026-10-01), 88 mutations, one per
behaviour; 5 survived the oracle (test_launch.sh, 228 assertions) and a
byte-for-byte --print parity. Their shapes recur:

- **A check made redundant by a later failure with the same status.**
  The launcher refuses a missing capabilities.json; delete that check and
  the routing load fails a moment later, also exit 1. The oracle asserted
  the status only. Pinned by asserting the exact refusal line, end to end
  through the shim (a test of the helper alone let the call site's
  mutation through).
- **Two scopes that overlap in the oracle's one scenario.** An inherited
  REPO_ROOT and the $PWD scope both name the repo when the launch is from
  its toplevel; only a launch from a subdirectory tells them apart.
- **`grep -c` counts lines, not occurrences.** "Only one --effort reaches
  the child" counted lines of a one-line command: two flags passed.
- **A stamp nobody reads.** A trailing bare --effort kept the routed level
  in the stamp where the bash cleared it; the command line was right, so
  the oracle was too.
- **The environment answered for the code** (see [[suites-inherit-launch-stamps]]).

**How to apply:** after the oracle passes, plant a mutation per behaviour
and run oracle, differential and Python tests per mutation; a survivor is
a decision to pull into a function and test directly, or a case to add
end to end. Equivalent-looking mutants are rarely equivalent: ask what
output differs (a message, a stamp, a non-toplevel cwd). The finding about
the oracle's own weakness goes into Wave 6 (the bash tests' port), never
into the oracle during the port.

*References: suites-inherit-launch-stamps*

*Observed 2026-10-01 (python-dev)*
