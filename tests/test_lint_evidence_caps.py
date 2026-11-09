#!/usr/bin/env python3
"""tools/fabric/lint_rules/evidence.py: agent-fabric ADR-067 rule 1 for GitHub's list caps over the tracked tree, with
policies/evidence-caps.json's declared modules. The predicate is tests/test_evidence_caps.py's; the pre-commit leg is
tests/test_githook_pre_commit.py's EvidenceCaps.

Stdlib only; runnable as `python3 tests/test_lint_evidence_caps.py`. **Each case names the mutation it kills**:

  lint_is_wired            <- evidence_cap_findings not called from lint.main, or a judged module's finding dropped
  vendored_is_judged       <- lint narrowed by ruff.toml's exclude, which the pre-commit hook is not (#516 F1)
  declared_module_passes   <- the policy's entry not honoured
  entry_that_admits_nothing <- an entry for a clean module left silent, one naming an untracked file, or one naming a
                               tracked file the check never judges (an owner, outside tools/fabric/, not Python)
  unreadable_policy        <- a policy that is not JSON read as empty (every finding then raised, or none)
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

TMP = tempfile.mkdtemp(prefix="lint-evidence-")
atexit.register(shutil.rmtree, TMP, ignore_errors=True)
POLICY = "policies/evidence-caps.json"
COPY = "import gh\n\nCAP = 250\n"


def fabric(policy: dict | str | None, extra: dict[str, str] | None = None) -> str:
    root = make_base(tempfile.mkdtemp(dir=TMP))
    for rel, text in (extra or {}).items():
        write(os.path.join(root, rel), text)
    write(os.path.join(root, "tools", "fabric", "evx.py"), COPY)
    write(os.path.join(root, "tools", "fabric", "clean.py"), "x = 1\n")
    if policy is not None:
        write(os.path.join(root, POLICY), policy if isinstance(policy, str) else json.dumps(policy))
    subprocess.run(["git", "-C", root, "init", "-q"], check=True, env=git_env())
    subprocess.run(["git", "-C", root, "add", "-A"], check=True, env=git_env())
    return root


def case_lint_is_wired() -> None:
    rc, out = run_lint(fabric(None))
    assert rc != 0 and "tools/fabric/evx.py:3: cap:" in out and "ADR-067 rule 1" in out, out


def case_declared_module_passes() -> None:
    _, out = run_lint(fabric({"modules": {"tools/fabric/evx.py": "a test"}}))
    assert "tools/fabric/evx.py:3" not in out, out


def case_entry_that_admits_nothing() -> None:
    _, out = run_lint(fabric({"modules": {"tools/fabric/evx.py": "a test", "tools/fabric/clean.py": "a test",
                                          "tools/fabric/gone.py": "a test"}}))
    assert f"{POLICY}: tools/fabric/clean.py admits nothing" in out, out
    assert f"{POLICY}: tools/fabric/gone.py is not a tracked file" in out, out
    owners = {"tools/fabric/github/evidence.py": "x = 1\n", "tools/fabric/notes.txt": "x\n"}
    _, out = run_lint(fabric({"modules": {m: "a test" for m in owners}}, owners))
    assert f"{POLICY}: tools/fabric/github/evidence.py is not judged by this check" in out, out
    assert f"{POLICY}: tools/fabric/notes.txt is not judged by this check" in out, out


def case_unreadable_policy() -> None:
    _, out = run_lint(fabric("{"))
    assert f"{POLICY}: cannot be read as JSON" in out and "tools/fabric/evx.py:3" not in out, out


def case_vendored_is_judged() -> None:
    """#516 F1/F2: ruff.toml's exclude does not narrow lint, as it does not narrow the pre-commit hook."""
    from test_lint import make_base, run_lint, write

    def vendored(policy: dict) -> str:
        root = make_base(tempfile.mkdtemp(dir=TMP))
        write(os.path.join(root, "ruff.toml"), 'exclude = ["tools/fabric/vendor"]\n')
        write(os.path.join(root, "tools/fabric/vendor/evx.py"), "import gh\n\nCAP = 250\n")
        write(os.path.join(root, "policies/evidence-caps.json"), json.dumps(policy))
        subprocess.run(["git", "-C", root, "init", "-q"], check=True, env=git_env())
        subprocess.run(["git", "-C", root, "add", "-A"], check=True, env=git_env())
        return root
    _, out = run_lint(vendored({"modules": {}}))
    assert "tools/fabric/vendor/evx.py:3:" in out, out
    _, out = run_lint(vendored({"modules": {"tools/fabric/vendor/evx.py": "a vendored tool"}}))
    assert "tools/fabric/vendor/evx.py" not in out, out


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
