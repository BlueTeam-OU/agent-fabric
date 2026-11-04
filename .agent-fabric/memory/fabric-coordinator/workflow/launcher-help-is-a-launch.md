---
role: "fabric-coordinator"
class: workflow
topic: "launcher-help-is-a-launch"
description: "launch --help installs no agent files; it still passes through to claude, so read usage from the launcher source"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 064c499bc654e4a5
  - 27d54ffc79996488
  - 2fea146cd3147988
  - 680413bbff1c0314
  - 974d92ea06ea6406
---

## launch --help installs no agent files; it still passes through to claude, so read usage from the launcher source

`launch --help` or `-h` before any `--` installs no agent files (header of `tools/fabric/launch.py`). It still
passes `--help` through to claude (the launcher has no help text of its own), so read the launcher's options
from that docstring, never by running it. The launcher's own suites (`tests/test_launch_cli.py`,
`tests/test_launch.py`) are the check of what `--print` renders. If a session's agent files were rewritten:
`runtime/claude-code/install-agent-files.sh --provider "$AGENT_FABRIC_LAUNCH_PROVIDER"` restores them.
Related: [[run-suites-as-ci-before-push]].

*References: run-suites-as-ci-before-push*

*Anchors: `tools/fabric/launch.py::installs no agent files`, `tests/test_launch_cli.py`*

*Observed 2026-10-23 (fabric-coordinator)*

## launch --help installs no agent files; it still passes through to claude, so read usage from source

`launch --help` installs no agent files, but it still passes `--help` through to claude, so
read the launcher's options from `tools/fabric/launch.py`'s docstring, never by running it.
There is no `--print` parity script any more (tests/parity/ was deleted in #202): the
launcher's own suites (tests/test_launch_cli.py) are the check. If a session's agent files
were rewritten: `runtime/claude-code/install-agent-files.sh --provider
"$AGENT_FABRIC_LAUNCH_PROVIDER"` restores them. Related: [[run-suites-as-ci-before-push]].

*References: run-suites-as-ci-before-push*

*Anchors: `tools/fabric/launch.py`*

*Observed 2026-10-11 (fabric-coordinator)*
