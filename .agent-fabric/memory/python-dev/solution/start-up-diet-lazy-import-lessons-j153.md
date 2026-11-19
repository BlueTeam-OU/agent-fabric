---
role: "python-dev"
class: solution
topic: "start-up-diet-lazy-import-lessons-j153"
description: "j153 #628 W5: lazy imports, entry files for bytecode, interleaved CPU measure, what broke in CI (source-line oracles, runner rule)"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-03"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 09bfef54bd6899cf
---

## j153 #628 W5: lazy imports, entry files for bytecode, interleaved CPU measure, what broke in CI (source-line oracles, runner rule)

Start-up diet on #628 (commits 992aebf3, 95128a0f, e474c7c0, CI fix 6d90f691). A lazy import moves a module off the start path only if no other module imports it: check `python -X importtime` parent lines (control.ops was pulled in by every `from control.ops import util` budget module, because a package import runs its __init__; fix = leaf module plus a shim that replaces itself in sys.modules).

Before editing an import line, grep the tests for the source text: test_launch_cli group 7 patched the line `import zoneinfo\n` in addenda_check.py by string replace, so the lazy (indented) import silently made the patch a no-op and failed only on debian CI where tzdata is absent. Tests that pass AGENT_FABRIC_ROOT must call own_instance_tree() first (a runner rule that fails only in run_python_suites, not when the file is run alone). test_control_bin pins the module a bin shim execs.

Measure with 50 starts per side interleaved A,B,A,B, CPU from RUSAGE_CHILDREN, median and quartiles: best-of-9 on a loaded host (load ~48) hid a 166 ms gain on `fabric-ctl --help`. Push needs `git -c credential.helper= -c 'credential.helper=!gh auth git-credential' push`; a delivered job is reopened with `fabric-jobs start` to commit a CI fix, then delivered again.

**Why:** two CI reds cost a round trip. **How to apply:** grep tests for the import text, run the whole suite file list that mentions the module, and read the runner rules in tests/run_python_suites.py before pushing.

*Observed 2026-11-16 (python-dev)*
