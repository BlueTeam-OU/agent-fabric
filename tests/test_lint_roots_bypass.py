#!/usr/bin/env python3
"""tools/fabric/lint_rules/roots.py: agent-fabric ADR-045 §5 rule 1 over the tracked tree, with tools/fabric/roots_bypass.json's
admitted modules. The predicate is tests/test_roots_bypass.py's.

Stdlib only; runnable as `python3 tests/test_lint_roots_bypass.py`. **Each case names the mutation it kills**:

  lint_is_wired             <- roots_bypass_findings not called from lint.main, or a judged module's finding dropped
  declared_module_passes    <- the policy's entry not honoured
  entry_that_admits_nothing <- an entry for a clean module, or one naming an untracked file, left silent
  unreadable_policy         <- a policy that is not JSON read as empty
  absent_policy_judges_all  <- a missing policy (instance data, ADR-045 rule 2) read as admitting everything
"""
from __future__ import annotations

import atexit
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from instance_fixtures import own_instance_tree  # noqa: E402
own_instance_tree()
from git_env import git_env  # noqa: E402
from test_lint import make_base, run_lint, write  # noqa: E402

TMP = tempfile.mkdtemp(prefix="lint-roots-")
atexit.register(shutil.rmtree, TMP, ignore_errors=True)
POLICY = "tools/fabric/roots_bypass.json"
WRITE = "import os\nx = os.environ.get(\"AGENT_FABRIC_ROOT\")\n"


def fabric(policy: dict | str | None) -> str:
    root = make_base(tempfile.mkdtemp(dir=TMP))
    write(os.path.join(root, "tools", "fabric", "rx.py"), WRITE)
    write(os.path.join(root, "tools", "fabric", "clean.py"), "x = 1\n")
    if policy is not None:
        write(os.path.join(root, POLICY), policy if isinstance(policy, str) else json.dumps(policy))
    subprocess.run(["git", "-C", root, "init", "-q"], check=True, env=git_env())
    subprocess.run(["git", "-C", root, "add", "-A"], check=True, env=git_env())
    return root


def case_lint_is_wired() -> None:
    rc, out = run_lint(fabric({"modules": {}}))
    assert rc != 0 and "tools/fabric/rx.py:2:" in out, out


def case_declared_module_passes() -> None:
    _, out = run_lint(fabric({"modules": {"tools/fabric/rx.py": "a test"}}))
    assert "tools/fabric/rx.py:2" not in out, out


def case_entry_that_admits_nothing() -> None:
    _, out = run_lint(fabric({"modules": {"tools/fabric/rx.py": "a test", "tools/fabric/clean.py": "a test",
                                         "tools/fabric/gone.py": "a test"}}))
    assert f"{POLICY}: tools/fabric/clean.py admits nothing" in out, out
    assert f"{POLICY}: tools/fabric/gone.py is listed but is not a tracked file" in out, out


def case_unreadable_policy() -> None:
    _, out = run_lint(fabric("{"))
    assert f"{POLICY}: cannot be read as JSON" in out and "tools/fabric/rx.py:2" not in out, out


def case_absent_policy_judges_all() -> None:
    _, out = run_lint(fabric(None))
    assert "tools/fabric/rx.py:2:" in out, out


def main() -> int:
    fails = 0
    for name, fn in sorted((n, f) for n, f in globals().items() if n.startswith("case_")):
        try:
            fn()
            print(f"  ok   {name}")
        except AssertionError as exc:
            fails += 1
            print(f"  FAIL {name}: {str(exc)[-400:]}")
    print("all passed" if not fails else f"{fails} FAILED")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
