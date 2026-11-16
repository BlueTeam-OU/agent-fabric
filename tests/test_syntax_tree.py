#!/usr/bin/env python3
"""tools/fabric/lint_rules/syntax_tree.py: the parse cache every syntax-tree rule of the corpus lint shares, and lint_rules/base.py's
per-run answer to "which files are tracked". Stdlib only; runnable as `python3 tests/test_syntax_tree.py`.
**Each case names the mutation it kills**:

  parsed_once              <- a rule parsing for itself again: the same text yields a new tree
  changed_file_is_reread   <- a cache keyed on the path (or the path, size and a coarse mtime): a rewritten file answered
                              with the old tree, so a fixed or newly planted violation goes unreported
  rules_leave_trees_alone  <- a rule that edits the tree it was handed: the next rule reads the edit
  failure_not_cached       <- a SyntaxError remembered as a tree, or raised under another caller's filename
  mechanism_follows_edits  <- mechanism_findings answering twice from the first tree of a test file
  tracked_held_inside_run  <- _tracked asking git again inside one run (the ~11 `git ls-files` a lint paid)
  tracked_fresh_outside    <- _tracked held beyond a run: a test that `git add`s between direct rule calls sees the old list
"""
from __future__ import annotations

import ast
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
FABRIC = os.path.join(ROOT, "tools", "fabric")
_spec = importlib.util.spec_from_file_location(
    "fabric_lint_rules", os.path.join(FABRIC, "lint_rules", "__init__.py"),
    submodule_search_locations=[os.path.join(FABRIC, "lint_rules")])
sys.modules["fabric_lint_rules"] = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sys.modules["fabric_lint_rules"])
from fabric_lint_rules import base, command_names, mechanisms as m, regex  # noqa: E402

st = base.syntax_tree
TMP = tempfile.mkdtemp(prefix="syntax-tree-")
atexit.register(shutil.rmtree, TMP, ignore_errors=True)


def load(name: str):
    spec = importlib.util.spec_from_file_location(f"t_{name}", os.path.join(FABRIC, f"{name}.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def case_parsed_once() -> None:
    first = st.parse("x = 1\n", "a.py")
    assert st.parse("x = 1\n", "b.py") is first, "the same text parsed twice"
    assert st.parse("x = 2\n", "a.py") is not first, "a different text answered with the first one's tree"
    # The checkers find the cache by name, so a rule in lint_rules/ and a checker in tools/fabric/ share it.
    assert load("state_writes")._syntax_tree() is st


def case_changed_file_is_reread() -> None:
    sw = load("state_writes")
    rel = "tools/fabric/x.py"
    assert sw.scan(rel, "x = 1\n", {}) == []
    assert sw.scan(rel, "state_root()\nopen('f', 'w')\n", {}), "a planted write at the same path went unreported"
    assert sw.scan(rel, "x = 1\n", {}) == [], "a fixed file kept its old finding"
    path = os.path.join(TMP, "mod.py")
    for text, stems in (("import alpha\n", {"alpha"}), ("import beta\n", {"beta"})):
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        assert m._loaded_stems(m._tree(TMP, "mod.py")) == stems, text


def _snapshot(tree: ast.AST) -> list:
    """Every node's type, its attribute names and its dump: a rule that edits a field (the dump differs) or hangs an attribute
    on a node (`node.parent = ...`, which ast.dump cannot see) both change it."""
    return [(type(n).__name__, sorted(vars(n)), ast.dump(n, include_attributes=True)) for n in ast.walk(tree)]


def case_rules_leave_trees_alone() -> None:
    names = ("context_reads", "process_spawns", "evidence_caps", "roots_bypass", "transport_calls", "state_writes", "work_writes")
    rel = "tools/fabric/sample.py"
    verbs = os.path.join(TMP, "verbs.py")
    for src in ("state_writes", "roots_bypass", "transport_calls", "work_writes", "lint", "review_cli", "reflect"):
        with open(os.path.join(FABRIC, f"{src}.py"), encoding="utf-8") as fh:
            text = fh.read()
        with open(verbs, "w", encoding="utf-8") as fh:
            fh.write(text)
        tree = st.parse(text, rel)
        before = _snapshot(tree)
        mods = {n: load(n) for n in names}
        mods["context_reads"].scan(rel, text, {})
        mods["process_spawns"].scan(rel, text, {})
        mods["process_spawns"].sites(text, rel)
        mods["evidence_caps"].scan(rel, text)
        mods["roots_bypass"].scan(rel, text)
        mods["transport_calls"].scan(rel, text, {})
        mods["state_writes"].scan(rel, text, {})
        mods["work_writes"].scan(rel, text, {})
        regex._Module(st.parse(text, rel))
        m._loaded_stems(st.parse(text, rel))
        command_names._read_verbs(verbs, "dict", "ROUTES")
        command_names._read_verbs(verbs, "choices", "action")
        # The rule's own walk over a tracked tree, not only its model of one: a fixture root holding this module.
        root = os.path.join(TMP, f"regex-{src}")
        os.makedirs(root)
        with open(os.path.join(root, "mod.py"), "w", encoding="utf-8") as fh:
            fh.write(text)
        subprocess.run(["git", "-C", root, "init", "-q"], check=True, env=git_env())
        subprocess.run(["git", "-C", root, "add", "-A"], check=True, env=git_env())
        regex.regex_dollar_findings(root)
        assert st.parse(text, rel) is tree
        assert _snapshot(tree) == before, f"a rule edited the shared tree of {src}.py"


def case_failure_not_cached() -> None:
    for name in ("a.py", "b.py"):
        try:
            st.parse("def (:\n", name)
        except SyntaxError as exc:
            assert exc.filename == name, exc.filename
        else:
            raise AssertionError("a SyntaxError was not raised")
    assert load("state_writes").scan("tools/fabric/x.py", "def (:\n", {}) == []


def _fabric(test_body: str) -> str:
    root = tempfile.mkdtemp(dir=TMP)
    files = {
        "runtime/identity.py": "x = 1\n",
        "tools/fabric/state_writes.py": "x = 1\n",
        "tools/fabric/state-writers.json": "{}\n",
        "tools/fabric/lint_rules/state.py": 'state_writes = _load("state_writes")\n',
        "tools/fabric/guards/commit_hooks.py": "import state_writes\n",
        "tools/fabric/lint.py": "from fabric_lint_rules.state import state_write_findings\n",
        "tests/test_state_writes.py": test_body,
        m.POLICY: json.dumps({"mechanisms": {"state-persistence": {
            "adr": "ADR-003", "owner": "runtime/identity.py", "status": "enforced",
            "checker": "tools/fabric/state_writes.py", "exceptions": "tools/fabric/state-writers.json"}}}),
    }
    for rel, text in files.items():
        os.makedirs(os.path.dirname(os.path.join(root, rel)), exist_ok=True)
        with open(os.path.join(root, rel), "w", encoding="utf-8") as fh:
            fh.write(text)
    subprocess.run(["git", "-C", root, "init", "-q"], check=True, env=git_env())
    subprocess.run(["git", "-C", root, "add", "-A"], check=True, env=git_env())
    return root


def case_mechanism_follows_edits() -> None:
    root = _fabric("import state_writes\n")
    assert m.mechanism_findings(root) == []
    with open(os.path.join(root, "tests", "test_state_writes.py"), "w", encoding="utf-8") as fh:
        fh.write("x = 1\n")
    out = m.mechanism_findings(root)
    assert any("no tests/test_*.py loads" in f for f in out), out
    with open(os.path.join(root, "tests", "test_state_writes.py"), "w", encoding="utf-8") as fh:
        fh.write("import state_writes\n")
    assert m.mechanism_findings(root) == []


class _CountingGit:
    def __init__(self, real) -> None:
        self.real, self.calls = real, 0

    def run(self, *a, **k):
        self.calls += 1
        return self.real.run(*a, **k)


def case_tracked_held_inside_run() -> None:
    root = _fabric("import state_writes\n")
    real, counter = base._git, None
    counter = _CountingGit(real())
    base._git = lambda: counter
    try:
        base.begin_run()
        first = base._tracked(root)
        first.append("scribbled")   # a rule's own edit of its copy
        assert base._tracked(root) == base._tracked(root) and "scribbled" not in base._tracked(root)
        assert counter.calls == 1, counter.calls
    finally:
        base.end_run()
        base._git = real


def case_tracked_fresh_outside() -> None:
    root = _fabric("import state_writes\n")
    assert "late.py" not in base._tracked(root)
    with open(os.path.join(root, "late.py"), "w", encoding="utf-8") as fh:
        fh.write("x = 1\n")
    subprocess.run(["git", "-C", root, "add", "late.py"], check=True, env=git_env())
    assert "late.py" in base._tracked(root)
    base.begin_run()
    try:
        assert "late.py" in base._tracked(root)
    finally:
        base.end_run()
    base.begin_run()
    base.end_run()
    assert base._run_tracked is None


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
