#!/usr/bin/env python3
"""tools/fabric/state_writes.py and its lint part, tools/fabric/lint_rules/state.py: agent-fabric ADR-003 rule 1 (j535).
The pre-commit leg is tests/test_githook_pre_commit.py's StateWrites.

Stdlib only; runnable as `python3 tests/test_state_writes.py`. **Each case names the mutation it kills**:

  writer_is_found            <- _write_kind's open() branch dropped, or RESOLVERS emptied
  writer_without_state_passes <- the write findings raised without `resolves or copies`
  unparseable_is_not_this_rules <- a SyntaxError turned into a finding
  invalid_escape_is_not_unparseable <- the SyntaxWarning filter dropped: under -W error the module's own invalid escape reads as a
                                syntax error and a planted violation beside it goes unfound
  each_write_kind            <- one of os.open flags / mkstemp / os.replace / sqlite3.connect / an unknown mode / Path.open /
                                shutil.copy, move / os.link dropped, or os.devnull counted
  state_dir_parameter_resolves <- STATE_PARAM not counted as resolving
  copy_is_found              <- _reads_env dropped or its Compare branch, or a setting (env[...] = ...) counted as a read
  identity_is_not_judged     <- the IDENTITY exemption dropped
  lock_terms                 <- _lock_finding's O_TRUNC or mode test dropped, the builtin-open branch dropped, or the module
                                constant not followed
  lock_on_terms_is_not_a_write <- the `elif kind == "os.open for writing"` exemption dropped
  listed_module_is_admitted  <- scan ignoring `writers`
  policy_entries             <- policy_findings' tracked test or reason test dropped
  lint_is_wired              <- state_write_findings not called from lint.main; tests/ judged; either admits-nothing finding
                                dropped; an unreadable list read as empty
  vendored_is_judged         <- lint narrowed by ruff.toml's exclude, which the pre-commit hook is not (#516 F1)

The tree itself is judged by the suite's corpus lint (tests/run.py), not here: a case reading the live
tools/fabric/state-writers.json is red on a stripped copy, which removes it as instance data (ADR-045 rule 3).
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
import state_writes as sw  # noqa: E402

TMP = tempfile.mkdtemp(prefix="state-writes-")
atexit.register(shutil.rmtree, TMP, ignore_errors=True)

RESOLVE = "import identity\nD = identity.agent_state_dir()\n"


def lines(found: list[str]) -> list[int]:
    return [int(f.split(":")[1]) for f in found]


def case_writer_is_found() -> None:
    got = sw.scan("tools/x.py", RESOLVE + "open(D + '/a', 'w')\n", {})
    assert lines(got) == [3] and "open(..., 'w')" in got[0] and sw.POLICY in got[0], got


def case_writer_without_state_passes() -> None:
    assert sw.scan("tools/x.py", "open('/tmp/a', 'w')\nimport os\nos.replace('a', 'b')\n", {}) == []


def case_unparseable_is_not_this_rules() -> None:
    """A half-merged module is ruff's to refuse; refusing it here stood in the way of the contributor fence's own refusal."""
    assert sw.scan("tools/x.py", "<<<<<<< HEAD\nopen(D, 'w')\n", {}) == []


def case_invalid_escape_is_not_unparseable() -> None:
    src = 'def f(state_dir):\n    open(state_dir + "/a", "w")\nx = "\\ "\n'   # the invalid escape backslash-space beside a violation
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        try:
            ast.parse(src)
        except SyntaxError:
            pass
        else:
            raise AssertionError("the fixture must fail to parse under -W error")
        got = sw.scan("tools/x.py", src, {})
    assert len(got) == 1, got


def case_each_write_kind() -> None:
    body = ("import os, sqlite3, tempfile\n"
            "os.open(D, os.O_WRONLY | os.O_APPEND)\n"
            "tempfile.mkstemp(dir=D)\n"
            "os.replace('a', 'b')\n"
            "sqlite3.connect(D)\n"
            "open(D, mode)\n"
            "open(D)\n"                      # a read: not a write
            "os.open(D, os.O_RDONLY)\n"       # a read: not a write
            "'x'.replace('a', 'b')\n"         # str.replace: not a rename
            "import pathlib, shutil\n"
            "pathlib.Path(D, 'a').open('w')\n"
            "shutil.copy('s', D)\n"
            "shutil.move('s', D)\n"
            "os.link('s', D)\n"
            "pathlib.Path(D).open()\n"         # a read
            "os.open(os.devnull, os.O_WRONLY)\n"    # stdout to devnull: not a write
            "os.open(self.devnull, os.O_WRONLY)\n")  # os's devnull only
    got = sw.scan("tools/x.py", RESOLVE + body, {})
    assert lines(got) == [4, 5, 6, 7, 8, 13, 14, 15, 16, 19], got


def case_state_dir_parameter_resolves() -> None:
    """A writer handed the directory by its caller (relaycopy.relay_backup(db, state_dir)) is judged where it writes."""
    body = "import os\ndef log(db, state_dir):\n    open(os.path.join(state_dir, 'l.jsonl'), 'a')\n"
    assert lines(sw.scan("tools/x.py", body, {})) == [3]
    assert sw.scan("tools/x.py", body.replace("state_dir", "where"), {}) == []


def case_copy_is_found() -> None:
    body = ("import os\n"
            "a = os.environ.get('AGENT_FABRIC_STATE_DIR')\n"
            "b = os.getenv('AGENT_FABRIC_STATE_DIR')\n"
            "c = os.environ['AGENT_FABRIC_STATE_DIR']\n"
            "env = {}\n"
            "env['AGENT_FABRIC_STATE_DIR'] = '/x'\n"          # setting it for a child is not a copy
            "os.environ['AGENT_FABRIC_STATE_DIR'] = '/x'\n"
            "open(a, 'w')\n"
            "if 'AGENT_FABRIC_STATE_DIR' in os.environ: pass\n")
    got = sw.scan("tools/x.py", body, {})
    copies = [f for f in got if "a copy of identity.state_root()" in f]
    assert lines(copies) == [2, 3, 4, 9], got
    assert [f for f in got if "open(..., 'w')" in f], "a copy resolves state, so its module's writes are judged: " + str(got)


def case_identity_is_not_judged() -> None:
    body = "import os\nR = os.environ.get('AGENT_FABRIC_STATE_DIR')\ndef agent_state_dir(): pass\nopen(R, 'w')\n"
    assert sw.scan(sw.IDENTITY, body, {}) == []
    assert len(sw.scan("runtime/other.py", body, {})) == 2


def case_lock_terms() -> None:
    body = ("import os\n"
            "LOCK = 'resume.lock'\n"
            "open(p + '.lock', 'a')\n"
            "os.open(p + '.lock', os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)\n"
            "os.open(f'{p}.lock', os.O_WRONLY | os.O_CREAT)\n"
            "os.open(os.path.join(d, LOCK), os.O_RDWR | os.O_CREAT, 0o644)\n"
            "os.open(p + '.lock', os.O_WRONLY | os.O_CREAT, 0o600)\n")   # on its terms
    got = sw.scan("tools/x.py", body, {})
    assert lines(got) == [3, 4, 5, 6], got
    assert "builtin open()" in got[0] and "O_TRUNC" in got[1] and "0o600" in got[2] and "0o600" in got[3], got


def case_lock_on_terms_is_not_a_write() -> None:
    body = RESOLVE + "import os\nos.open(D + '.lock', os.O_WRONLY | os.O_CREAT | os.O_CLOEXEC, 0o600)\n"
    assert sw.scan("tools/x.py", body, {}) == []


def case_listed_module_is_admitted() -> None:
    body = RESOLVE + "open(D, 'w')\nopen(D + '.lock', 'w')\n"
    assert len(sw.scan("tools/x.py", body, {})) == 3
    assert sw.scan("tools/x.py", body, {"tools/x.py": "gap (j1): a test"}) == []


def case_policy_entries() -> None:
    writers = {"tools/a.py": "ADR-003 §2: control", "tools/b.py": "not state: x", "tools/c.py": "gap (j9): y",
               "tools/gone.py": "not state: z", "tools/bare.py": "because"}
    got = sw.policy_findings(writers, {"tools/a.py", "tools/b.py", "tools/c.py", "tools/bare.py"})
    assert len(got) == 2 and "tools/gone.py is listed" in got[0] and "tools/bare.py's reason" in got[1], got
    assert sw.parse_writers('{"writers": {"a.py": "x", "b.py": 3}}') == {"a.py": "x"}
    try:
        sw.parse_writers("{")
        raise AssertionError("text that is not JSON parsed")
    except ValueError:
        pass


def case_lint_is_wired() -> None:
    """Through lint's whole run on a scratch fabric, as CI runs it: the writer, the test fixture left alone, the entry that
    admits nothing."""
    from test_lint import make_base, run_lint, write
    fabric = make_base(tempfile.mkdtemp(dir=TMP))
    write(os.path.join(fabric, "tools", "fabric", "w.py"), RESOLVE + "open(D, 'w')\n")
    write(os.path.join(fabric, "tests", "test_w.py"), RESOLVE + "open(D, 'w')\n")
    write(os.path.join(fabric, "tools", "fabric", "clean.py"), "x = 1\n")
    write(os.path.join(fabric, sw.POLICY), json.dumps({"writers": {"tools/fabric/clean.py": "not state: a test",
                                                                  "tests/test_w.py": "not state: a fixture"}}))
    subprocess.run(["git", "-C", fabric, "init", "-q"], check=True, env=git_env())
    subprocess.run(["git", "-C", fabric, "add", "-A"], check=True, env=git_env())
    rc, out = run_lint(fabric)
    assert rc != 0, out
    assert "tools/fabric/w.py:3: open(..., 'w')" in out, out
    assert "tests/test_w.py:" not in out, out
    assert "tools/fabric/clean.py admits nothing" in out, out
    assert "tests/test_w.py admits nothing — rule 1 does not judge that path" in out, out
    # A list that is not JSON is said once, not as a finding per module it would have admitted.
    write(os.path.join(fabric, sw.POLICY), "{")
    subprocess.run(["git", "-C", fabric, "add", "-A"], check=True, env=git_env())
    rc, out = run_lint(fabric)
    assert "tools/fabric/state-writers.json: cannot be read as JSON" in out and "tools/fabric/w.py:3" not in out, out


def case_vendored_is_judged() -> None:
    """#516 F1/F2: ruff.toml's exclude does not narrow lint, as it does not narrow the pre-commit hook."""
    from test_lint import make_base, run_lint, write

    def vendored(policy: dict) -> str:
        root = make_base(tempfile.mkdtemp(dir=TMP))
        write(os.path.join(root, "ruff.toml"), 'exclude = ["vendor"]\n')
        write(os.path.join(root, "vendor/w.py"), RESOLVE + "open(D, 'w')\n")
        write(os.path.join(root, "tools/fabric/state-writers.json"), json.dumps(policy))
        subprocess.run(["git", "-C", root, "init", "-q"], check=True, env=git_env())
        subprocess.run(["git", "-C", root, "add", "-A"], check=True, env=git_env())
        return root
    _, out = run_lint(vendored({"writers": {}}))
    assert "vendor/w.py:3:" in out, out
    _, out = run_lint(vendored({"writers": {"vendor/w.py": "not state: a vendored tool"}}))
    assert "vendor/w.py" not in out, out


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
