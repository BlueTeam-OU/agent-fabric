#!/usr/bin/env python3
"""tools/fabric/lint_rules/command_names.py: agent-fabric ADR-068 rules 3 and 7 over the tracked tree, with
runtime/claude-code/commands.json's table and policies/command-names.json's declared modules. The predicates are
tests/test_fabric_cli.py's; the pre-commit leg is tests/test_githook_pre_commit.py's CommandNames.

Stdlib only; runnable as `python3 tests/test_lint_command_names.py`. **Each case names the mutation it kills**:

  lint_is_wired             <- command_name_findings not called from lint.main, or a judged module's finding dropped
  table_is_judged           <- table_findings not asked, or its `note:` line left in the output
  declared_module_passes    <- the policy's entry not honoured
  entry_that_admits_nothing <- an entry for a clean module, or one naming an untracked file, left silent
  unreadable_policy         <- a policy that is not JSON read as empty
  absent_policy_judges_all  <- a missing policy (instance data, ADR-045 rule 2) read as admitting everything
  vendored_is_judged        <- lint narrowed by ruff.toml's exclude, which the pre-commit hook is not (#516 F1)
  absent_table_is_silent    <- a fabric with no command table made a finding in every fixture lint runs on
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

TMP = tempfile.mkdtemp(prefix="lint-command-names-")
atexit.register(shutil.rmtree, TMP, ignore_errors=True)
POLICY = "policies/command-names.json"
TABLE = "runtime/claude-code/commands.json"
GUARD = "tools/fabric/guards/wx.py"
DOC = {"commands": {"fabric": "bin/fabric", "fabric-pr": "bin/fabric-pr"},
       "fabric": {"nouns": {"pr": {"command": "fabric-pr"}}}}
RECOGNISER = "def is_pr(cmd):\n    return cmd == \"fabric-pr\"\n"


def tracked(root: str) -> str:
    subprocess.run(["git", "-C", root, "init", "-q"], check=True, env=git_env())
    subprocess.run(["git", "-C", root, "add", "-A"], check=True, env=git_env())
    return root


def fabric(policy: dict | str | None, doc: dict | None = DOC) -> str:
    root = make_base(tempfile.mkdtemp(dir=TMP))
    write(os.path.join(root, GUARD), RECOGNISER)
    write(os.path.join(root, "tools", "fabric", "guards", "clean.py"), "x = 1\n")
    if doc is not None:
        write(os.path.join(root, TABLE), json.dumps(doc))
    if policy is not None:
        write(os.path.join(root, POLICY), policy if isinstance(policy, str) else json.dumps(policy))
    return tracked(root)


def case_lint_is_wired() -> None:
    rc, out = run_lint(fabric({"recognisers": {}}))
    assert rc != 0 and f"{GUARD}:2:" in out, out


def case_table_is_judged() -> None:
    doc = {**DOC, "commands": {**DOC["commands"], "fabric-orphan": "bin/fabric-orphan"}}
    _, out = run_lint(fabric({"recognisers": {GUARD: "a test"}}, doc))
    assert "fabric-orphan: in `commands` and reached by no `fabric` form" in out, out
    assert "own_verbs not supplied" not in out, out


def case_declared_module_passes() -> None:
    _, out = run_lint(fabric({"recognisers": {GUARD: "a test"}}))
    assert GUARD not in out, out


def case_entry_that_admits_nothing() -> None:
    _, out = run_lint(fabric({"recognisers": {GUARD: "a test", "tools/fabric/guards/clean.py": "a test",
                                               "tools/fabric/guards/gone.py": "a test"}}))
    assert f"{POLICY}: tools/fabric/guards/clean.py admits nothing" in out, out
    assert f"{POLICY}: tools/fabric/guards/gone.py admits nothing" in out, out


def case_unreadable_policy() -> None:
    _, out = run_lint(fabric("{"))
    assert f"{POLICY}: cannot be read as JSON" in out and f"{GUARD}:2" not in out, out


def case_absent_policy_judges_all() -> None:
    _, out = run_lint(fabric(None))
    assert f"{GUARD}:2:" in out, out


def case_vendored_is_judged() -> None:
    hook = "runtime/claude-code/hooks/vendor_hook.py"

    def vendored(policy: dict) -> str:
        root = make_base(tempfile.mkdtemp(dir=TMP))
        write(os.path.join(root, "ruff.toml"), 'exclude = ["runtime/claude-code/hooks"]\n')
        write(os.path.join(root, TABLE), json.dumps(DOC))
        write(os.path.join(root, hook), RECOGNISER)
        write(os.path.join(root, POLICY), json.dumps(policy))
        return tracked(root)
    _, out = run_lint(vendored({"recognisers": {}}))
    assert f"{hook}:2:" in out, out
    _, out = run_lint(vendored({"recognisers": {hook: "a vendored hook"}}))
    assert "vendor_hook.py" not in out, out


def case_absent_table_is_silent() -> None:
    _, out = run_lint(fabric(None, doc=None))
    assert GUARD not in out and "commands.json" not in out, out


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
