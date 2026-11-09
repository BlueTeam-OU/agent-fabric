#!/usr/bin/env python3
"""tools/fabric/lint_rules/mechanisms.py: agent-fabric ADR-067 rules 2 and 3, the catalogue of cross-cutting mechanisms.

Stdlib only; runnable as `python3 tests/test_mechanisms.py`. **Each case names the mutation it kills**:

  well_formed_passes        <- any check firing on a catalogue the tree bears out, a planned entry's missing owner included
  enforced_needs_wiring     <- _loads dropped from the lint-rule, pre-commit or tests leg, a rule module lint.py does not
                               import counted as running, or one of _run_rules' three import spellings dropped
  mention_is_not_a_load     <- a comment or a docstring naming the checker counted as loading it (text, not syntax, read)
  real_loads_count          <- `import os, <stem>` or `from <stem> import x` not counted as a load
  enforced_needs_files      <- the checker/exceptions presence or tracked test dropped
  named_paths_are_tracked   <- a pending or planned entry's named path not checked, or a non-string path crashing lint
  owner_package             <- an owner directory/ refused, one holding no tracked file passed, the slash not required,
                               or a checker allowed to be a directory
  pending_and_planned       <- the JOB pattern or the waits_on test dropped
  entry_fields              <- the ADR, owner-required, owner-tracked or status test dropped
  unreadable_and_absent     <- an unreadable catalogue read as empty, or an absent one (instance data) made a finding
  lint_is_wired             <- mechanism_findings not called from lint.main

The tree itself is judged by the suite's corpus lint, not here: policies/*.json is instance data (ADR-045 rule 2), which a
case may not read live (rule 3).
"""
from __future__ import annotations

import atexit
import importlib.util
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

ROOT = os.path.dirname(HERE)
_spec = importlib.util.spec_from_file_location(
    "fabric_lint_rules", os.path.join(ROOT, "tools", "fabric", "lint_rules", "__init__.py"),
    submodule_search_locations=[os.path.join(ROOT, "tools", "fabric", "lint_rules")])
sys.modules["fabric_lint_rules"] = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sys.modules["fabric_lint_rules"])
from fabric_lint_rules import mechanisms as m  # noqa: E402

TMP = tempfile.mkdtemp(prefix="mechanisms-")
atexit.register(shutil.rmtree, TMP, ignore_errors=True)

ENFORCED = {"adr": "ADR-003", "owner": "runtime/identity.py", "status": "enforced",
            "checker": "tools/fabric/state_writes.py", "exceptions": "policies/state-writers.json"}
FILES = {
    "runtime/identity.py": "x = 1\n",
    "tools/fabric/state_writes.py": "x = 1\n",
    "policies/state-writers.json": "{}\n",
    "tools/fabric/lint_rules/state.py": 'state_writes = _load("state_writes")\n',
    "tools/fabric/guards/commit_hooks.py": "import state_writes  # noqa: E402\n",
    "tools/fabric/lint.py": "from fabric_lint_rules.state import state_write_findings\n",
    "tests/test_state_writes.py": "import state_writes as sw\n",
}


def tree(catalogue, files: dict[str, str] | None = None) -> str:
    root = tempfile.mkdtemp(dir=TMP)
    for rel, text in {**FILES, **(files or {})}.items():
        if text is None:
            continue
        os.makedirs(os.path.dirname(os.path.join(root, rel)), exist_ok=True)
        with open(os.path.join(root, rel), "w", encoding="utf-8") as fh:
            fh.write(text)
    if catalogue is not None:
        os.makedirs(os.path.join(root, "policies"), exist_ok=True)
        with open(os.path.join(root, m.POLICY), "w", encoding="utf-8") as fh:
            fh.write(catalogue if isinstance(catalogue, str) else json.dumps({"mechanisms": catalogue}))
    subprocess.run(["git", "-C", root, "init", "-q"], check=True, env=git_env())
    subprocess.run(["git", "-C", root, "add", "-A"], check=True, env=git_env())
    return root


def case_well_formed_passes() -> None:
    out = m.mechanism_findings(tree({
        "state": ENFORCED,
        "process": {"adr": "ADR-067", "owner": "runtime/identity.py", "status": "pending", "job": "python-dev-02/j125"},
        "jobs": {"adr": "ADR-037", "status": "planned", "waits_on": "j100"},
    }))
    assert out == [], out


def case_enforced_needs_wiring() -> None:
    out = m.mechanism_findings(tree({"state": ENFORCED}, {"tools/fabric/lint_rules/state.py": "x = 1\n"}))
    assert [f for f in out if "no lint rule" in f] and not [f for f in out if "pre-commit" in f or "tests/" in f], out
    out = m.mechanism_findings(tree({"state": ENFORCED}, {"tools/fabric/guards/commit_hooks.py": "import state_writes2\n"}))
    assert [f for f in out if "pre-commit hook" in f] and not [f for f in out if "no lint rule" in f], out
    out = m.mechanism_findings(tree({"state": ENFORCED}, {"tests/test_state_writes.py": "x = 1\n"}))
    assert out == [f"{m.POLICY}: state: enforced, but no tests/test_*.py loads tools/fabric/state_writes.py"], out
    # A rule module lint.py never imports never runs, however it loads the checker.
    out = m.mechanism_findings(tree({"state": ENFORCED}, {"tools/fabric/lint.py": "x = 1\n"}))
    assert [f for f in out if "no lint rule that tools/fabric/lint.py imports" in f], out
    for spelling in ("from fabric_lint_rules import state\n", "import fabric_lint_rules.state\n"):
        assert m.mechanism_findings(tree({"state": ENFORCED}, {"tools/fabric/lint.py": spelling})) == [], spelling


def case_mention_is_not_a_load() -> None:
    out = m.mechanism_findings(tree({"state": ENFORCED}, {
        "tools/fabric/lint_rules/state.py": '# state_writes = _load("state_writes")\n',
        # This module's own comment names the loader call too; it must not answer for the rule that runs.
        "tools/fabric/lint_rules/mechanisms.py": '# `_load("state_writes")` by path\n',
        "tools/fabric/guards/commit_hooks.py": '"""\nimport state_writes\n"""\n',
        "tools/fabric/lint.py": "from fabric_lint_rules.state import a\nfrom fabric_lint_rules.mechanisms import b\n"}))
    assert [f for f in out if "no lint rule" in f] and [f for f in out if "pre-commit hook" in f], out


def case_real_loads_count() -> None:
    out = m.mechanism_findings(tree({"state": ENFORCED}, {
        "tools/fabric/lint_rules/state.py": "from state_writes import scan\n",
        "tools/fabric/guards/commit_hooks.py": "import os, state_writes\n"}))
    assert out == [], out


def case_enforced_needs_files() -> None:
    out = m.mechanism_findings(tree({"state": {**ENFORCED, "exceptions": None}}))
    assert any("an enforced mechanism must name its exceptions" in f for f in out), out
    out = m.mechanism_findings(tree({"state": ENFORCED}, {"tools/fabric/state_writes.py": None}))
    assert any("checker 'tools/fabric/state_writes.py' is not a tracked file" in f for f in out), out


def case_named_paths_are_tracked() -> None:
    out = m.mechanism_findings(tree({
        "p": {"adr": "ADR-067", "owner": "runtime/identity.py", "status": "pending", "job": "a-b/j1",
              "checker": "tools/nowhere.py"},
        "q": {"adr": "ADR-067", "owner": "tools/nowhere.py", "status": "planned", "waits_on": "x"},
        "r": {**ENFORCED, "checker": ["x"], "exceptions": {"a": 1}},
    }))
    assert any(": p: checker 'tools/nowhere.py' is not a tracked file" in f for f in out), out
    assert any(": q: owner 'tools/nowhere.py' is not a tracked file" in f for f in out), out
    assert any(": r: checker ['x'] is not a tracked file" in f for f in out), out
    assert any(": r: exceptions {'a': 1} is not a tracked file" in f for f in out), out


def case_owner_package() -> None:
    def findings(owner: str, checker: str = "tools/fabric/state_writes.py") -> list[str]:
        return m.mechanism_findings(tree({"state": {**ENFORCED, "owner": owner, "checker": checker}}))
    assert not any("owner" in f for f in findings("runtime/")), findings("runtime/")
    assert any("owner 'tools/nowhere/' is not a tracked file" in f for f in findings("tools/nowhere/"))
    assert any("owner 'runtime' is not a tracked file" in f for f in findings("runtime"))
    assert any("checker 'tools/fabric/' is not a tracked file" in f for f in findings("runtime/identity.py", "tools/fabric/"))


def case_pending_and_planned() -> None:
    out = m.mechanism_findings(tree({
        "a": {"adr": "ADR-067", "owner": "runtime/identity.py", "status": "pending", "job": "j125"},
        "b": {"adr": "ADR-067", "owner": "runtime/identity.py", "status": "planned", "waits_on": " "},
    }))
    assert any(f.endswith(": a: a pending mechanism names the job building its checker as <login>/j<n>") for f in out), out
    assert any(": b: a planned mechanism says what it waits on" in f for f in out), out


def case_entry_fields() -> None:
    out = m.mechanism_findings(tree({"x": {"adr": "037", "status": "done"},
                                     "y": {"adr": "ADR-001", "owner": "tools/nowhere.py", "status": "pending", "job": "a/j1"},
                                     "z": {"adr": "ADR-001", "status": "pending", "job": "a/j1"}}))
    assert f"{m.POLICY}: z: a pending mechanism must name its owner (ADR-067 rule 2)" in out, out
    assert any("\"adr\" names the record" in f for f in out), out
    assert any("owner 'tools/nowhere.py' is not a tracked file" in f for f in out), out
    assert any("status 'done' is not one of" in f for f in out), out


def case_unreadable_and_absent() -> None:
    out = m.mechanism_findings(tree("{"))
    assert out == [f"{m.POLICY}: cannot be read as JSON (JSONDecodeError); ADR-067 is not judged"], out
    assert m.mechanism_findings(tree(None)) == []
    assert m.mechanism_findings(tree({})) == [f"{m.POLICY}: needs a non-empty \"mechanisms\" object (ADR-067 rule 2)"]


def case_lint_is_wired() -> None:
    from test_lint import make_base, run_lint, write
    fabric = make_base(tempfile.mkdtemp(dir=TMP))
    write(os.path.join(fabric, m.POLICY), json.dumps({"mechanisms": {"x": {"adr": "ADR-067", "owner": "nowhere.py",
                                                                          "status": "planned", "waits_on": "a test"}}}))
    subprocess.run(["git", "-C", fabric, "init", "-q"], check=True, env=git_env())
    subprocess.run(["git", "-C", fabric, "add", "-A"], check=True, env=git_env())
    rc, out = run_lint(fabric)
    assert rc != 0 and "policies/mechanisms.json: x: owner 'nowhere.py' is not a tracked file" in out, out


def main() -> int:
    fails = 0
    for name, fn in sorted((n, f) for n, f in globals().items() if n.startswith("case_")):
        try:
            fn()
            print(f"  ok   {name}")
        except AssertionError as exc:
            fails += 1
            print(f"  FAIL {name}: {exc}")
    print("all passed" if not fails else f"{fails} FAILED")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
