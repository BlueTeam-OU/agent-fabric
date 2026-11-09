#!/usr/bin/env python3
"""tools/fabric/context_reads.py and its lint part, tools/fabric/lint_rules/context.py: who may read an agent's binding (j212).

Stdlib only; runnable as `python3 tests/test_context_reads.py`. **Each case names the mutation it kills**:

  file_name_is_found         <- the string-constant branch of raw_findings dropped, or _FILE matching a substring
  path_call_is_found         <- the ACCESSORS branches dropped (the attribute form, the bare-name form)
  read_binding_is_allowed    <- read_binding added to ACCESSORS (identity's validated reader is not a finding)
  docstring_and_text_pass    <- docstrings counted, or _FILE loosened so a message that mentions the file is a finding
  homes_and_tests_are_not_judged <- HOMES or the tests/ exemption dropped
  unparseable_is_not_this_rules <- a SyntaxError turned into a finding
  listed_module_is_admitted  <- scan ignoring `readers`
  policy_entries             <- policy_findings' tracked test or the HOMES test dropped; parse_readers keeping a blank reason
  lint_is_wired              <- context_read_findings not called from lint.main; either admits-nothing finding dropped; an
                                unreadable list read as empty
  vendored_is_judged      <- lint narrowed by ruff.toml's exclude, which the pre-commit hook is not (#516 F1)
  invalid_escape_is_quiet <- the SyntaxWarning filter dropped from raw_findings: a scanned file's invalid escape printed
                             on every lint run (tests/test_guard_hook_internals.py)

The tree itself is judged by the suite's corpus lint (tests/run.py), not here.
"""
from __future__ import annotations

import ast
import atexit
import json
import os
import shutil
import subprocess
import sys
import tempfile
import warnings

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from instance_fixtures import own_instance_tree  # noqa: E402
own_instance_tree()
from git_env import git_env  # noqa: E402

ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "tools", "fabric"))
import context_reads as cr  # noqa: E402

TMP = tempfile.mkdtemp(prefix="context-reads-")
atexit.register(shutil.rmtree, TMP, ignore_errors=True)


def case_file_name_is_found() -> None:
    for body in ('open("/state/binding.json")\n', 'p = f"{state}/binding.json"\n', 'N = "binding.json"\n'):
        got = cr.scan("tools/x.py", body, {})
        assert len(got) == 1 and "names binding.json" in got[0] and cr.POLICY in got[0], (body, got)
    assert cr.scan("tools/x.py", 'x = 1\nopen("binding.json")\n', {})[0].startswith("tools/x.py:2:")


def case_path_call_is_found() -> None:
    attr = cr.scan("tools/x.py", "import identity\nopen(identity.binding_path())\n", {})
    assert len(attr) == 1 and "identity.binding_path" in attr[0], attr
    bare = cr.scan("tools/x.py", "from identity import binding_path\nbinding_path()\n", {})
    assert len(bare) == 1 and "uses binding_path" in bare[0], bare   # the call; the import's alias is not a Name node


def case_read_binding_is_allowed() -> None:
    assert cr.scan("tools/x.py", "import identity\nidentity.read_binding()\n", {}) == []
    assert cr.scan("tools/x.py", "import identity\nidentity.update_binding(lambda b: b)\n", {}) == []


def case_docstring_and_text_pass() -> None:
    body = '"""Reads binding.json."""\n\n\ndef f():\n    """The binding.json file."""\n    return "see binding.json (the role)"\n'
    assert cr.scan("tools/x.py", body, {}) == []
    # The positive control of the line above: the same file with the name as a path is a finding.
    assert len(cr.scan("tools/x.py", body + 'P = "/s/binding.json"\n', {})) == 1


def case_homes_and_tests_are_not_judged() -> None:
    body = 'P = "/s/binding.json"\n'
    assert cr.scan("runtime/identity.py", body, {}) == []
    assert cr.scan("tools/fabric/workingcopy.py", body, {}) == []
    assert cr.scan("tests/test_x.py", body, {}) == []
    assert cr.scan("tools/x.py", body, {}) != []
    assert not cr.judged_path("tools/x.txt")


def case_unparseable_is_not_this_rules() -> None:
    assert cr.scan("tools/x.py", "<<<<<<< HEAD\nP = '/s/binding.json'\n", {}) == []


def case_listed_module_is_admitted() -> None:
    body = 'P = "/s/binding.json"\n'
    assert cr.scan("tools/x.py", body, {"tools/x.py": "the restart read"}) == []
    assert cr.scan("tools/x.py", body, {"tools/y.py": "elsewhere"}) != []


def case_policy_entries() -> None:
    readers = {"tools/a.py": "why", "tools/gone.py": "why", "runtime/identity.py": "why"}
    got = cr.policy_findings(readers, {"tools/a.py", "runtime/identity.py"})
    assert len(got) == 2 and "tools/gone.py is listed" in got[0] and "runtime/identity.py is identity's own" in got[1], got
    assert cr.parse_readers('{"readers": {"a.py": "x", "b.py": 3, "c.py": "  "}}') == {"a.py": "x"}
    assert cr.parse_readers('{"readers": []}') == {} and cr.parse_readers("[]") == {}
    try:
        cr.parse_readers("{")
        raise AssertionError("text that is not JSON parsed")
    except ValueError:
        pass


def case_lint_is_wired() -> None:
    """Through lint's whole run on a scratch fabric, as CI runs it: the reader, the test fixture left alone, the entry that
    admits nothing, and a planted read turning the run red (the acceptance's positive control)."""
    from test_lint import make_base, run_lint, write
    fabric = make_base(tempfile.mkdtemp(dir=TMP))
    write(os.path.join(fabric, "tools", "fabric", "r.py"), 'import identity\nF = identity.binding_path()\n')
    write(os.path.join(fabric, "tests", "test_r.py"), 'F = "/s/binding.json"\n')
    write(os.path.join(fabric, "tools", "fabric", "clean.py"), "x = 1\n")
    write(os.path.join(fabric, cr.POLICY), json.dumps({"readers": {"tools/fabric/clean.py": "a test"}}))
    subprocess.run(["git", "-C", fabric, "init", "-q"], check=True, env=git_env())
    subprocess.run(["git", "-C", fabric, "add", "-A"], check=True, env=git_env())
    rc, out = run_lint(fabric)
    assert rc != 0, out
    assert "tools/fabric/r.py:2: calls identity.binding_path" in out, out
    assert "tests/test_r.py:" not in out, out
    assert "tools/fabric/clean.py admits nothing" in out, out
    write(os.path.join(fabric, cr.POLICY), json.dumps({"readers": {"tools/fabric/r.py": "a test"}}))
    subprocess.run(["git", "-C", fabric, "add", "-A"], check=True, env=git_env())
    rc, out = run_lint(fabric)
    assert "tools/fabric/r.py:2" not in out and "context-reads.json" not in out, out
    write(os.path.join(fabric, cr.POLICY), "{")
    subprocess.run(["git", "-C", fabric, "add", "-A"], check=True, env=git_env())
    rc, out = run_lint(fabric)
    assert "policies/context-reads.json: cannot be read as JSON" in out and "tools/fabric/r.py:2" not in out, out


def case_vendored_is_judged() -> None:
    """#516 F1/F2: ruff.toml's exclude does not narrow lint, as it does not narrow the pre-commit hook."""
    from test_lint import make_base, run_lint, write

    def vendored(policy: dict) -> str:
        root = make_base(tempfile.mkdtemp(dir=TMP))
        write(os.path.join(root, "ruff.toml"), 'exclude = ["vendor"]\n')
        write(os.path.join(root, "vendor/r.py"), "P = 'binding.json'\n")
        write(os.path.join(root, "policies/context-reads.json"), json.dumps(policy))
        subprocess.run(["git", "-C", root, "init", "-q"], check=True, env=git_env())
        subprocess.run(["git", "-C", root, "add", "-A"], check=True, env=git_env())
        return root
    _, out = run_lint(vendored({"readers": {}}))
    assert "vendor/r.py:1:" in out, out
    _, out = run_lint(vendored({"readers": {"vendor/r.py": "a vendored tool"}}))
    assert "vendor/r.py" not in out, out


def case_invalid_escape_is_quiet() -> None:
    src = "x = '\\ '\nf = 'binding.json'\n"  # a source file holding the invalid escape backslash-space
    with warnings.catch_warnings(record=True) as control:
        warnings.simplefilter("always")
        ast.parse(src)
    assert any(issubclass(w.category, SyntaxWarning) for w in control), "the fixture must warn when parsed bare"
    with warnings.catch_warnings(record=True) as got:
        warnings.simplefilter("always")
        found = cr.raw_findings("tools/x.py", src)
    assert not got, [str(w.message) for w in got]
    assert found == ["tools/x.py:2: names binding.json"], found


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
