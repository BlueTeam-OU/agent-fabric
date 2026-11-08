#!/usr/bin/env python3
"""tools/fabric/process_spawns.py: process lifetime has one owner (the owner's 2026-11-08 ask, j125).

Stdlib only; runnable as `python3 tests/test_process_spawns.py`. **Each case names the mutation it kills**:

  each_signal_is_found        <- one of killpg / setsid / setpgid / setpgrp dropped from SIGNALS, or the bare-name call missed
  each_spawn_keyword_is_found <- start_new_session or process_group dropped from SPAWN_KEYWORDS
  an_off_keyword_is_not_one   <- _off dropped: start_new_session=False counted
  the_owner_is_not_judged     <- the OWNER exemption dropped
  a_listed_module_is_admitted <- scan ignoring `allowed`
  a_name_is_not_a_call        <- a string, a comment or an attribute that is not called counted
  unparseable_is_not_this     <- a SyntaxError turned into a finding
  policy_entries              <- policy_findings' tracked test or reason test dropped; an entry that is not a string pair admitting
  tests_are_not_judged        <- judged_path counting tests/
  tree_planted_killpg_is_red  <- tree_findings not scanning a tracked module, or main returning 0 with findings
  tree_clean_is_green         <- the positive control for the case above: a finding on a module that spawns through process.py
  admits_nothing              <- the stale-entry findings (a moved module, an exempt path) dropped
  bad_policy_is_said_once     <- an unreadable policy read as empty, or one finding per module
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
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from instance_fixtures import own_instance_tree  # noqa: E402
own_instance_tree()
sys.path.insert(0, os.path.join(ROOT, "tools", "fabric"))
import process_spawns as ps  # noqa: E402

TMP = tempfile.mkdtemp(prefix="process-spawns-")
atexit.register(shutil.rmtree, TMP, ignore_errors=True)
CLEAN = "import process\nwith process.group(['x']) as p:\n    p.wait()\n"


def lines(found: list[str]) -> list[int]:
    return [int(f.split(":")[1]) for f in found]


def case_each_signal_is_found() -> None:
    for call in ("os.killpg(1, 9)", "killpg(1, 9)", "os.setsid()", "os.setpgid(0, 0)", "os.setpgrp()"):
        got = ps.scan("tools/x.py", f"import os\n{call}\n", {})
        assert lines(got) == [2] and call.split("(")[0].split(".")[-1] in got[0], (call, got)


def case_each_spawn_keyword_is_found() -> None:
    for kw in ("start_new_session=True", "process_group=0", "start_new_session=flag"):
        got = ps.scan("tools/x.py", f"import subprocess\nsubprocess.Popen(['x'], {kw})\n", {})
        assert lines(got) == [2], (kw, got)
    got = ps.scan("tools/x.py", "import subprocess\nsubprocess.run(['x'], start_new_session=True)\n", {})
    assert lines(got) == [2] and "run()" in got[0], got


def case_an_off_keyword_is_not_one() -> None:
    assert not ps.scan("tools/x.py", "import subprocess\nsubprocess.Popen(['x'], start_new_session=False)\n", {})


def case_the_owner_is_not_judged() -> None:
    assert not ps.scan(ps.OWNER, "import os\nos.killpg(1, 9)\n", {})
    assert not ps.judged_path(ps.OWNER)


def case_a_listed_module_is_admitted() -> None:
    src = "import os\nos.killpg(1, 9)\nos.setsid()\n"
    assert len(ps.scan("tools/x.py", src, {})) == 2
    assert not ps.scan("tools/x.py", src, {"tools/x.py": "installed alone"})
    assert len(ps.scan("tools/y.py", src, {"tools/x.py": "installed alone"})) == 2, "an entry admits its own path only"


def case_a_name_is_not_a_call() -> None:
    src = "# os.killpg(1, 9)\nx = 'start_new_session=True'\nimport os\nf = os.killpg\ny = {'setsid': 1}\n"
    assert not ps.scan("tools/x.py", src, {})


def case_unparseable_is_not_this() -> None:
    assert ps.scan("tools/x.py", "def (:\n", {}) == []


def case_policy_entries() -> None:
    assert ps.parse_allowed('{"spawns": {"a.py": "why", "b.py": 3, "c.py": null}}') == {"a.py": "why"}
    assert ps.parse_allowed('{"other": 1}') == {} and ps.parse_allowed("[]") == {}
    got = ps.policy_findings({"gone.py": "why", "here.py": " "}, {"here.py"})
    assert len(got) == 2 and "not a tracked file" in got[0] and "no reason" in got[1], got
    try:
        ps.parse_allowed("{")
        raise AssertionError("not JSON, not refused")
    except ValueError:
        pass


def case_tests_are_not_judged() -> None:
    assert not ps.judged_path("tests/test_x.py") and not ps.judged_path("tools/x.sh") and ps.judged_path("tools/x.py")


def repo(files: dict[str, str]) -> str:
    root = tempfile.mkdtemp(dir=TMP)
    for rel, text in files.items():
        os.makedirs(os.path.dirname(os.path.join(root, rel)), exist_ok=True)
        with open(os.path.join(root, rel), "w", encoding="utf-8") as fh:
            fh.write(text)
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": root, "GIT_CONFIG_NOSYSTEM": "1"}
    for cmd in (["init", "-q"], ["add", "-A"]):
        subprocess.run(["git", "-C", root, *cmd], check=True, env=env, stdin=subprocess.DEVNULL, timeout=30)
    return root


def run_main(root: str) -> tuple[int, str]:
    r = subprocess.run([sys.executable, "-I", os.path.join(ROOT, "tools", "fabric", "process_spawns.py"), "--root", root],
                       capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL)
    return r.returncode, r.stdout


def case_tree_clean_is_green() -> None:
    root = repo({"tools/fabric/a.py": CLEAN, "tests/test_a.py": "import os\nos.killpg(1, 9)\n"})
    assert run_main(root) == (0, ""), run_main(root)


def case_tree_planted_killpg_is_red() -> None:
    root = repo({"tools/fabric/a.py": CLEAN, "tools/fabric/b.py": "import os\n\ndef stop(p):\n    os.killpg(p, 9)\n"})
    rc, out = run_main(root)
    assert rc == 1 and out.startswith("tools/fabric/b.py:4: killpg()") and "a.py" not in out, (rc, out)
    # and it is quiet again once the module is listed with a reason
    policy = os.path.join(root, "policy.json")
    with open(policy, "w", encoding="utf-8") as fh:
        json.dump({"spawns": {"tools/fabric/b.py": "installed alone on hosts without the tree"}}, fh)
    r = subprocess.run([sys.executable, "-I", os.path.join(ROOT, "tools", "fabric", "process_spawns.py"), "--root", root,
                        "--policy", policy], capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL)
    assert (r.returncode, r.stdout) == (0, ""), (r.returncode, r.stdout)


def case_admits_nothing() -> None:
    text = json.dumps({"spawns": {"tools/fabric/a.py": "moved", "tests/test_a.py": "a test", "tools/fabric/process.py": "owner",
                                  "tools/fabric/gone.py": "why"}})
    root = repo({"tools/fabric/a.py": CLEAN, "tests/test_a.py": "x = 1\n", "tools/fabric/process.py": "x = 1\n"})
    got = ps.tree_findings(root, ["tools/fabric/a.py", "tests/test_a.py", "tools/fabric/process.py"], text)
    assert len(got) == 4 and sum("admits nothing" in g for g in got) == 3 and sum("not a tracked file" in g for g in got) == 1, got


def case_bad_policy_is_said_once() -> None:
    root = repo({"tools/fabric/a.py": "import os\nos.setsid()\n", "tools/fabric/b.py": "import os\nos.setsid()\n"})
    got = ps.tree_findings(root, ["tools/fabric/a.py", "tools/fabric/b.py"], "{")
    assert len(got) == 1 and "cannot be read as JSON" in got[0], got


def main() -> int:
    for name, fn in sorted((n, f) for n, f in globals().items() if n.startswith("case_") and callable(f)):
        fn()
        print(f"  ok   {name[5:].replace('_', ' ')}")
    print("test_process_spawns.py: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
