#!/usr/bin/env python3
"""tests/test_rename_history.py — the Python half of rename_working_copy.py
against a throwaway HOME: a merge into an existing history directory
never overwrites, every rewrite is atomic, and the binding moves through
identity.update_binding (stamped, locked) rather than a rewrite in
place. Runs as the current login, with the state dir pointed at the
sandbox; the shell half (sudo, the live-session refusal, the mv) is host
tooling and is not exercised here."""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
TOOL = os.path.join(ROOT, "runtime", "provisioning", "rename_history.py")
IDENTITY = os.path.join(ROOT, "runtime", "identity.py")
import pwd
LOGIN = pwd.getpwuid(os.geteuid()).pw_name   # the agent is the login, never $USER (unset in a container)


def write(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def key(p: str) -> str:
    return p.replace("/", "-")


def run(home: str, oldp: str, newp: str, dry: bool = False) -> subprocess.CompletedProcess:
    env = {**os.environ, "AGENT_FABRIC_STATE_DIR": os.path.join(home, "state")}
    return subprocess.run([sys.executable, TOOL, home, LOGIN, oldp, newp, "1" if dry else "0", IDENTITY],
                          capture_output=True, text=True, env=env)


def fixture(tmp: str, name: str) -> tuple[str, str, str]:
    home = os.path.join(tmp, name); oldp, newp = os.path.join(home, "projects", "old"), os.path.join(home, "projects", "new")
    pdir_old = os.path.join(home, ".claude", "projects", key(oldp))
    write(os.path.join(pdir_old, "s1.jsonl"), json.dumps({"cwd": oldp, "type": "user"}) + "\n" + json.dumps({"cwd": oldp, "type": "assistant"}) + "\n")
    write(os.path.join(pdir_old, "memory", "MEMORY.md"), "# index\n")
    write(os.path.join(home, ".claude", "history.jsonl"), json.dumps({"display": "hi", "project": oldp}) + "\n")
    write(os.path.join(home, ".claude.json"), json.dumps({"projects": {oldp: {"allowedTools": ["Bash(ls:*)"], "hasTrustDialogAccepted": True}}}))
    return home, oldp, newp


def binding_write(home: str, rec: dict) -> None:
    spec = importlib.util.spec_from_file_location("i", IDENTITY); i = importlib.util.module_from_spec(spec); spec.loader.exec_module(i)
    os.environ["AGENT_FABRIC_STATE_DIR"] = os.path.join(home, "state")
    try:
        i.write_binding(rec)
    finally:
        del os.environ["AGENT_FABRIC_STATE_DIR"]


def jobs_write(home: str, jobs: list[dict]) -> None:
    spec = importlib.util.spec_from_file_location("i", IDENTITY); i = importlib.util.module_from_spec(spec); spec.loader.exec_module(i)
    os.environ["AGENT_FABRIC_STATE_DIR"] = os.path.join(home, "state")
    try:
        i.update_jobs(lambda doc: doc.update(jobs=jobs, seq=len(jobs)))
    finally:
        del os.environ["AGENT_FABRIC_STATE_DIR"]


def jobs_read(home: str) -> dict:
    with open(os.path.join(home, "state", "agents", LOGIN, "jobs.json"), encoding="utf-8") as fh:
        return {j["id"]: j for j in json.load(fh)["jobs"]}


def binding_read(home: str) -> dict:
    return json.load(open(os.path.join(home, "state", "agents", LOGIN, "binding.json"), encoding="utf-8"))


def test_plain_rename_moves_everything_and_rewrites_the_fields(tmp: str) -> None:
    home, oldp, newp = fixture(tmp, "plain")
    binding_write(home, {"role": "db-admin", "working_copy": oldp, "workspace": oldp})
    r = run(home, oldp, newp)
    assert r.returncode == 0, r.stderr
    pdir_new = os.path.join(home, ".claude", "projects", key(newp))
    assert os.path.isdir(pdir_new) and not os.path.isdir(os.path.join(home, ".claude", "projects", key(oldp)))
    lines = [json.loads(l) for l in open(os.path.join(pdir_new, "s1.jsonl"))]
    assert all(l["cwd"] == newp for l in lines), lines
    assert json.loads(open(os.path.join(home, ".claude", "history.jsonl")).readline())["project"] == newp
    cj = json.load(open(os.path.join(home, ".claude.json")))
    assert newp in cj["projects"] and oldp not in cj["projects"]
    b = binding_read(home)
    assert b["working_copy"] == newp and b["workspace"] == newp and b["role"] == "db-admin"
    assert b["agent"] == LOGIN and b["host"], "the binding was not written through identity (no OS stamp)"
    for d in (pdir_new, os.path.join(home, ".claude"), home, os.path.join(home, "state", "agents", LOGIN)):
        assert not [n for n in os.listdir(d) if n.startswith(".tmp-")], f"a temporary was left in {d}"


def test_unfinished_jobs_follow_the_checkout(tmp: str) -> None:
    home, oldp, newp = fixture(tmp, "jobs")
    other = os.path.join(home, "projects", "other")
    binding_write(home, {"role": "db-admin", "working_copy": oldp})
    jobs_write(home, [
        {"id": "j1", "state": "active", "working_copy": oldp, "worktree": oldp, "title": "t"},
        {"id": "j2", "state": "queued", "working_copy": oldp, "title": "t"},
        {"id": "j3", "state": "delivered", "working_copy": other, "worktree": oldp + "/sub", "title": "t"},
        {"id": "j4", "state": "done", "working_copy": oldp, "worktree": oldp, "title": "t"},
        {"id": "j5", "state": "active", "working_copy": oldp + "-sibling", "title": "t"},
        {"id": "j6", "state": "paused", "working_copy": other, "title": "t"},
    ])
    r = run(home, oldp, newp)
    assert r.returncode == 0, r.stderr
    jobs = jobs_read(home)
    assert (jobs["j1"]["working_copy"], jobs["j1"]["worktree"]) == (newp, newp), jobs["j1"]
    assert jobs["j2"]["working_copy"] == newp and "worktree" not in jobs["j2"], jobs["j2"]
    assert jobs["j3"]["working_copy"] == other and jobs["j3"]["worktree"] == newp + "/sub", jobs["j3"]
    assert jobs["j4"]["working_copy"] == oldp and jobs["j4"]["worktree"] == oldp, "a closed job's record was rewritten"
    assert jobs["j5"]["working_copy"] == oldp + "-sibling", "a sibling that shares the prefix was rewritten"
    assert jobs["j6"]["working_copy"] == other
    assert "3 unfinished job(s)" in r.stderr, r.stderr


def test_dry_run_leaves_jobs_alone(tmp: str) -> None:
    home, oldp, newp = fixture(tmp, "jobs-dry")
    jobs_write(home, [{"id": "j1", "state": "active", "working_copy": oldp, "title": "t"}])
    r = run(home, oldp, newp, dry=True)
    assert r.returncode == 0 and "would: rewrite 1 unfinished job(s)" in r.stderr, r.stderr
    assert jobs_read(home)["j1"]["working_copy"] == oldp


def test_merge_keeps_both_files_when_names_collide_with_different_bytes(tmp: str) -> None:
    home, oldp, newp = fixture(tmp, "collide")
    pdir_new = os.path.join(home, ".claude", "projects", key(newp))
    write(os.path.join(pdir_new, "s1.jsonl"), json.dumps({"cwd": newp, "type": "user", "earlier": True}) + "\n")   # same name, different bytes
    write(os.path.join(pdir_new, "s2.jsonl"), "same\n"); write(os.path.join(home, ".claude", "projects", key(oldp), "s2.jsonl"), "same\n")  # identical
    r = run(home, oldp, newp)
    assert r.returncode == 0, r.stderr
    names = sorted(os.listdir(pdir_new))
    assert "s1.jsonl" in names and f"s1.from-{key(oldp)}.jsonl" in names, names
    assert json.loads(open(os.path.join(pdir_new, "s1.jsonl")).readline())["earlier"] is True, "the earlier session was overwritten"
    moved = [json.loads(l) for l in open(os.path.join(pdir_new, f"s1.from-{key(oldp)}.jsonl"))]
    assert all(l["cwd"] == newp for l in moved), "the moved transcript's cwd was not rewritten"
    assert names.count("s2.jsonl") == 1 and not os.path.exists(os.path.join(pdir_new, f"s2.from-{key(oldp)}.jsonl")), "an identical file was kept twice"
    assert "1 name collision(s) kept" in r.stderr, r.stderr


def test_merge_refuses_a_directory_on_both_sides(tmp: str) -> None:
    home, oldp, newp = fixture(tmp, "dirs")
    pdir_new = os.path.join(home, ".claude", "projects", key(newp))
    write(os.path.join(pdir_new, "memory", "MEMORY.md"), "# other index\n")
    r = run(home, oldp, newp)
    assert r.returncode == 1 and "REFUSED" in r.stderr and "memory" in r.stderr, r.stderr
    assert os.path.isfile(os.path.join(home, ".claude", "projects", key(oldp), "s1.jsonl")), "the refusal moved something first"
    assert open(os.path.join(pdir_new, "memory", "MEMORY.md")).read() == "# other index\n"


def test_dry_run_touches_nothing(tmp: str) -> None:
    home, oldp, newp = fixture(tmp, "dry")
    binding_write(home, {"role": "db-admin", "working_copy": oldp})
    before = binding_read(home)
    r = run(home, oldp, newp, dry=True)
    assert r.returncode == 0 and "would:" in r.stderr, r.stderr
    assert os.path.isdir(os.path.join(home, ".claude", "projects", key(oldp))) and binding_read(home) == before


def main() -> int:
    cases = [test_plain_rename_moves_everything_and_rewrites_the_fields,
             test_merge_keeps_both_files_when_names_collide_with_different_bytes,
             test_merge_refuses_a_directory_on_both_sides, test_dry_run_touches_nothing,
             test_unfinished_jobs_follow_the_checkout, test_dry_run_leaves_jobs_alone]
    failures = 0
    with tempfile.TemporaryDirectory() as tmp:
        for case in cases:
            try:
                case(tmp)
                print(f"  ok   {case.__name__}")
            except AssertionError as exc:
                failures += 1
                print(f"  FAIL {case.__name__}: {exc}")
    print(f"\n{len(cases) - failures}/{len(cases)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
