#!/usr/bin/env python3
"""tools/fabric/lint_rules/work.py: agent-fabric ADR-067 rule 1 for the work lifecycle (ADR-037 rule 14) over the tracked tree, with
tools/fabric/work-writes.json's declared modules. The predicate is tests/test_work_writes.py's; the pre-commit leg is
tests/test_githook_pre_commit.py's WorkWrites.

Stdlib only; runnable as `python3 tests/test_lint_work_writes.py`. **Each case names the mutation it kills**:

  lint_is_wired             <- work_write_findings not called from lint.main, or a judged module's finding dropped
  declared_module_passes    <- the policy's entry not honoured
  entry_that_admits_nothing <- an entry for a clean module, or one naming an untracked file, left silent
  unreadable_policy         <- a policy that is not JSON read as empty
  absent_policy_judges_all  <- a missing policy (instance data, ADR-045 rule 2) read as admitting everything
  vendored_is_judged        <- lint narrowed by ruff.toml's exclude, which the pre-commit hook is not (#516 F1): a vendored
                               writer unjudged, or named and then called untracked
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

TMP = tempfile.mkdtemp(prefix="lint-work-")
atexit.register(shutil.rmtree, TMP, ignore_errors=True)
POLICY = "tools/fabric/work-writes.json"
WRITE = "def finish(job):\n    job[\"state\"] = \"done\"\n"


def fabric(policy: dict | str | None) -> str:
    root = make_base(tempfile.mkdtemp(dir=TMP))
    write(os.path.join(root, "tools", "fabric", "wx.py"), WRITE)
    write(os.path.join(root, "tools", "fabric", "clean.py"), "x = 1\n")
    if policy is not None:
        write(os.path.join(root, POLICY), policy if isinstance(policy, str) else json.dumps(policy))
    subprocess.run(["git", "-C", root, "init", "-q"], check=True, env=git_env())
    subprocess.run(["git", "-C", root, "add", "-A"], check=True, env=git_env())
    return root


def case_lint_is_wired() -> None:
    rc, out = run_lint(fabric({"writes": {}}))
    assert rc != 0 and "tools/fabric/wx.py:2:" in out, out


def case_declared_module_passes() -> None:
    _, out = run_lint(fabric({"writes": {"tools/fabric/wx.py": "a test"}}))
    assert "tools/fabric/wx.py:2" not in out, out


def case_entry_that_admits_nothing() -> None:
    _, out = run_lint(fabric({"writes": {"tools/fabric/wx.py": "a test", "tools/fabric/clean.py": "a test",
                                         "tools/fabric/gone.py": "a test"}}))
    assert f"{POLICY}: tools/fabric/clean.py admits nothing" in out, out
    assert f"{POLICY}: tools/fabric/gone.py is listed but is not a tracked file" in out, out


def case_unreadable_policy() -> None:
    _, out = run_lint(fabric("{"))
    assert f"{POLICY}: cannot be read as JSON" in out and "tools/fabric/wx.py:2" not in out, out


def case_absent_policy_judges_all() -> None:
    _, out = run_lint(fabric(None))
    assert "tools/fabric/wx.py:2:" in out, out


def case_vendored_is_judged() -> None:
    def vendored(policy: dict) -> str:
        root = make_base(tempfile.mkdtemp(dir=TMP))
        write(os.path.join(root, "ruff.toml"), 'exclude = ["vendor"]\n')
        write(os.path.join(root, "vendor", "run.py"), WRITE)
        write(os.path.join(root, POLICY), json.dumps(policy))
        subprocess.run(["git", "-C", root, "init", "-q"], check=True, env=git_env())
        subprocess.run(["git", "-C", root, "add", "-A"], check=True, env=git_env())
        return root
    _, out = run_lint(vendored({"writes": {}}))
    assert "vendor/run.py:2:" in out, out
    _, out = run_lint(vendored({"writes": {"vendor/run.py": "a vendored tool"}}))
    assert "vendor/run.py" not in out, out


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
