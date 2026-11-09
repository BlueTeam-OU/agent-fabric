#!/usr/bin/env python3
"""tools/fabric/work_writes.py: the work lifecycle has one owner, tools/fabric/work/ (agent-fabric ADR-037 rule 14, ADR-067, j101).

Stdlib only; runnable as `python3 tests/test_work_writes.py`. **Each case names the mutation it kills**:

  each_write_form_is_found        <- one of the subscript, augmented, delete, setdefault, update(kw), update({}) or dict forms dropped
  each_key_is_found               <- "claimed" (or "state") dropped from KEYS
  a_literal_that_is_no_state_is_not_one <- _could_be_a_state taking any literal; "working" or "cleared" counted
  a_name_is_unknown_and_a_finding <- a write of a variable, or a call's result, let through
  a_dict_copying_a_state_is_not_a_write <- the dict form flagging a non-literal value
  the_owner_is_not_judged         <- the OWNER_DIR exemption dropped
  a_listed_module_is_admitted     <- scan ignoring `allowed`
  a_read_is_not_a_write           <- a comparison, a get, a load or a comment counted
  unparseable_is_not_this         <- a SyntaxError turned into a finding
  policy_entries                  <- policy_findings' tracked test or reason test dropped
  tests_are_not_judged            <- judged_path counting tests/
  the_states_are_the_tables       <- STATES here and work/table.py drifting apart
  tree_planted_write_is_red       <- tree_findings not scanning a tracked module, or main returning 0 with findings
  tree_clean_is_green             <- the positive control for the case above: a read of the state, a write through the owner
  admits_nothing                  <- the stale-entry findings dropped
  bad_policy_is_said_once         <- an unreadable policy read as empty, or one finding per module
  this_tree_is_green              <- a state write outside the owner that the exceptions below do not name, in the tree as it is
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
import by_path  # noqa: E402
import work_writes as ww  # noqa: E402

TMP = tempfile.mkdtemp(prefix="work-writes-")
atexit.register(shutil.rmtree, TMP, ignore_errors=True)
CLEAN = "import work\n\ndef move(doc, job):\n    work.transition(doc, job, 'done', 'done', None)\n    return job['state'] == 'done'\n"
# policies/work-writes.json is the control plane's, delivered beside this suite: the writes of the tree that are not a job's.
EXCEPTIONS = {
    "tools/fabric/gzcoord/carrier/record.py": "a carrier record's delivery state, not a job's",
    "tools/fabric/jobsparts/blockers.py": "a blocker cache entry's state (cleared, waiting, unknown), not a job's",
    "tools/fabric/plan.py": "a plan step's state, not a job's",
}


def lines(found: list[str]) -> list[int]:
    return [int(f.split(":")[1]) for f in found]


def case_each_write_form_is_found() -> None:
    forms = ['job["state"] = "done"', 'job["state"] += "x"', 'del job["state"]', 'job.setdefault("state", "queued")',
             'job.update(state="active")', 'job.update({"state": "paused"})', 'x = {"id": 1, "state": "queued"}']
    for form in forms:
        got = ww.scan("tools/x.py", f"job = {{}}\n{form}\n", {})
        assert lines(got) == [2], (form, got)


def case_each_key_is_found() -> None:
    for key, value in (("state", "done"), ("claimed", "closed")):
        got = ww.scan("tools/x.py", f'job = {{}}\njob["{key}"] = "{value}"\n', {})
        assert lines(got) == [2] and key in got[0], (key, got)


def case_a_literal_that_is_no_state_is_not_one() -> None:
    for value in ("working", "cleared", "pending"):
        assert not ww.scan("tools/x.py", f'row = {{}}\nrow["state"] = "{value}"\nrow.update(state="{value}")\ny = {{"state": "{value}"}}\n', {}), value
    assert not ww.scan("tools/x.py", 'row = {}\nrow["state"] = 3\nrow["state"] = None\n', {})
    assert ww.scan("tools/x.py", 'row = {}\nrow["claimed"] = None\n', {}), "a claim written null is a claim reopened"


def case_a_name_is_unknown_and_a_finding() -> None:
    for form in ('job["state"] = new', 'job["state"] = pick(a)', 'job.update(state=new)', 'job.setdefault("state", new)'):
        assert lines(ww.scan("tools/x.py", f"job = {{}}\nnew = 1\n{form}\n", {})) == [3], form


def case_a_dict_copying_a_state_is_not_a_write() -> None:
    assert not ww.scan("tools/x.py", 'row = {"state": s["state"], "since": 1}\nother = {"state": state}\n', {})


def case_the_owner_is_not_judged() -> None:
    assert not ww.scan("tools/fabric/work/lifecycle.py", 'job = {}\njob["state"] = "done"\n', {})
    assert not ww.scan("tools/fabric/work/claims.py", 'job = {}\njob["claimed"] = None\n', {})
    assert not ww.judged_path("tools/fabric/work/lifecycle.py")
    assert ww.scan("tools/fabric/worker.py", 'job = {}\njob["state"] = "done"\n', {}), "a name that only begins like the owner's directory"


def case_a_listed_module_is_admitted() -> None:
    src = 'job = {}\njob["state"] = "done"\njob["claimed"] = None\n'
    assert len(ww.scan("tools/x.py", src, {})) == 2
    assert not ww.scan("tools/x.py", src, {"tools/x.py": "a plan's step"})
    assert len(ww.scan("tools/y.py", src, {"tools/x.py": "a plan's step"})) == 2, "an entry admits its own path only"


def case_a_read_is_not_a_write() -> None:
    src = ('# job["state"] = "done"\nx = "job[\'state\'] = 1"\njob = {}\nif job["state"] == "done":\n    pass\n'
           'y = job.get("state")\nz = job["claimed"]\nw = {"state"}\nclaimed = "open"\njob.update(title="x")\n')
    assert not ww.scan("tools/x.py", src, {})


def case_unparseable_is_not_this() -> None:
    assert ww.scan("tools/x.py", "def (:\n", {}) == []


def case_policy_entries() -> None:
    assert ww.parse_allowed('{"writes": {"a.py": "why", "b.py": 3, "c.py": null}}') == {"a.py": "why"}
    assert ww.parse_allowed('{"other": 1}') == {} and ww.parse_allowed("[]") == {}
    got = ww.policy_findings({"gone.py": "why", "here.py": " "}, {"here.py"})
    assert len(got) == 2 and "not a tracked file" in got[0] and "no reason" in got[1], got
    try:
        ww.parse_allowed("{")
        raise AssertionError("not JSON, not refused")
    except ValueError:
        pass


def case_tests_are_not_judged() -> None:
    assert not ww.judged_path("tests/test_x.py") and not ww.judged_path("tools/x.sh") and ww.judged_path("tools/x.py")


def case_the_states_are_the_tables() -> None:
    work = by_path.load_package("fabric_work", os.path.join(ROOT, "tools", "fabric", "work"))
    assert ww.STATES == set(work.table.JOB_STATES) | set(work.table.POOL_STATES), (ww.STATES, work.table.JOB_STATES, work.table.POOL_STATES)


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


def run_main(root: str, policy: str | None = None) -> tuple[int, str]:
    r = subprocess.run([sys.executable, "-I", os.path.join(ROOT, "tools", "fabric", "work_writes.py"), "--root", root,
                        *(["--policy", policy] if policy else [])], capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL)
    return r.returncode, r.stdout


def case_tree_clean_is_green() -> None:
    root = repo({"tools/fabric/a.py": CLEAN, "tests/test_a.py": 'job = {}\njob["state"] = "done"\n',
                 "tools/fabric/work/lifecycle.py": 'job = {}\njob["state"] = "done"\n'})
    assert run_main(root) == (0, ""), run_main(root)


def case_tree_planted_write_is_red() -> None:
    root = repo({"tools/fabric/a.py": CLEAN, "tools/fabric/b.py": 'def finish(job):\n    job["state"] = "done"\n'})
    rc, out = run_main(root)
    assert rc == 1 and out.startswith('tools/fabric/b.py:2: a write of ["state"]') and "a.py" not in out, (rc, out)
    # and it is quiet again once the module is listed with a reason
    policy = os.path.join(root, "policy.json")
    with open(policy, "w", encoding="utf-8") as fh:
        json.dump({"writes": {"tools/fabric/b.py": "a plan step, not a job"}}, fh)
    assert run_main(root, policy) == (0, ""), run_main(root, policy)


def case_admits_nothing() -> None:
    text = json.dumps({"writes": {"tools/fabric/a.py": "moved", "tests/test_a.py": "a test", "tools/fabric/work/lifecycle.py": "owner",
                                  "tools/fabric/gone.py": "why"}})
    root = repo({"tools/fabric/a.py": CLEAN, "tests/test_a.py": "x = 1\n", "tools/fabric/work/lifecycle.py": "x = 1\n"})
    got = ww.tree_findings(root, ["tools/fabric/a.py", "tests/test_a.py", "tools/fabric/work/lifecycle.py"], text)
    assert len(got) == 4 and sum("admits nothing" in g for g in got) == 3 and sum("not a tracked file" in g for g in got) == 1, got


def case_bad_policy_is_said_once() -> None:
    root = repo({"tools/fabric/a.py": 'j = {}\nj["state"] = "done"\n', "tools/fabric/b.py": 'j = {}\nj["state"] = "done"\n'})
    got = ww.tree_findings(root, ["tools/fabric/a.py", "tools/fabric/b.py"], "{")
    assert len(got) == 1 and "cannot be read as JSON" in got[0], got


def case_this_tree_is_green() -> None:
    policy = os.path.join(TMP, "this-tree.json")
    with open(policy, "w", encoding="utf-8") as fh:
        json.dump({"writes": EXCEPTIONS}, fh)
    rc, out = run_main(ROOT, policy)
    assert (rc, out) == (0, ""), (rc, out)
    # the positive control: without them the tree is red, so the green above is the exceptions' doing and the owner's
    rc, out = run_main(ROOT, os.path.join(TMP, "none.json"))
    assert rc == 1 and all(m in out for m in EXCEPTIONS), (rc, out)


def main() -> int:
    for name, fn in sorted((n, f) for n, f in globals().items() if n.startswith("case_") and callable(f)):
        fn()
        print(f"  ok   {name[5:].replace('_', ' ')}")
    print("test_work_writes.py: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
