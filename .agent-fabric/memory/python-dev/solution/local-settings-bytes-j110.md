---
role: "python-dev"
class: solution
topic: "local-settings-bytes-j110"
description: "j110 #470 — secrets.env names read as bytes; seal copy held equal by a test, not an import; arm minimum was 1"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "python-dev-03"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - dc65df03f1873631
---

## j110 #470 — secrets.env names read as bytes; seal copy held equal by a test, not an import; arm minimum was 1

`tools/fabric/local_settings.py` reads secrets.env/env.sh names as bytes (decode only the ASCII group). `runtime/claude-code/hooks/session-seal.py` is stdlib-only (`-I -S`, no import from the tree), so it keeps its own copy of `HARNESS_CREDENTIALS` and `synced_names`; `tests/test_local_settings.py` loads the seal by path and asserts both agree (tuple, non-UTF-8 file, lone CR in a value). Coordinator decided: no import, a test.

**Why:** a first comment said the seal would be "pointed here"; the re-review showed its contract forbids it.
**How to apply:** change the tuple or the read in one file and the test names the other. Merged as #470; `fabric-pr arm --dry-run` needs `--basis` to print, and the count rule was 1 work commit that day. A full-suite `test_moveto_enter` "bounded command" timing failure was a load flake (passed alone 3/3, green on rerun).

*Anchors: `tools/fabric/local_settings.py::HARNESS_CREDENTIALS`, `runtime/claude-code/hooks/session-seal.py::synced_names`*

*Observed 2026-11-04 (python-dev)*
