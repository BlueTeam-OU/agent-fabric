#!/usr/bin/env python3
"""Behavioural tests for runtime/identity.py and tools/fabric/workingcopy.py.

The invariant under test: the agent name is the Linux login of the
effective user and nothing else. Changing directory, renaming a working
copy, being inside or outside a repository, or setting environment
variables must leave it untouched — and must still resolve the CONTEXT
(working copy, project) correctly and separately.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
IDENTITY = os.path.join(ROOT, "runtime", "identity.py")
WHOAMI = os.path.join(ROOT, "bin", "fabric-whoami")

sys.path.insert(0, os.path.join(ROOT, "runtime"))
sys.path.insert(0, os.path.join(ROOT, "tools", "fabric"))
import identity  # noqa: E402
import workingcopy  # noqa: E402


def sh(*argv: str, cwd: str | None = None, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(list(argv), cwd=cwd, env=env, capture_output=True, text=True)


def id_un() -> str:
    return sh("id", "-un").stdout.strip()


def git_repo(path: str, remote: str) -> None:
    os.makedirs(path, exist_ok=True)
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    for cmd in (["init", "-q", "."], ["remote", "add", "origin", remote]):
        assert sh("git", "-c", "commit.gpgsign=false", *cmd, cwd=path, env=env).returncode == 0


def fabric_fixture(tmp: str) -> str:
    """A fake agent-fabric root with one registered project."""
    root = os.path.join(tmp, "fabric")
    os.makedirs(os.path.join(root, "projects"))
    os.makedirs(os.path.join(root, "tools", "fabric"))
    with open(os.path.join(root, "projects", "registry.json"), "w", encoding="utf-8") as fh:
        json.dump({"version": 1, "projects": {"demo": {
            "remotes": ["git@example.com:org/demo.git"]}}}, fh)
    os.symlink(os.path.join(ROOT, "tools", "fabric", "workingcopy.py"),
               os.path.join(root, "tools", "fabric", "workingcopy.py"))
    return root


def test_agent_is_the_effective_login() -> None:
    assert identity.current_agent() == id_un()
    assert sh(sys.executable, IDENTITY).stdout.strip() == id_un()
    assert sh("bash", WHOAMI).stdout.strip() == id_un()


def test_agent_is_computed_from_the_uid_not_from_names() -> None:
    fake = lambda uid: type("pw", (), {"pw_name": f"login-{uid}"})()  # noqa: E731
    assert identity.current_agent(getpwuid=fake, geteuid=lambda: 4242) == "login-4242"


def test_agent_ignores_cwd_and_environment(tmp: str) -> None:
    """From the parent directory, inside a repo, inside a renamed copy of
    that repo, and outside any repo: always the same agent."""
    root = fabric_fixture(tmp)
    repo = os.path.join(tmp, "demo-clone-a")
    git_repo(repo, "git@example.com:org/demo.git")
    renamed = os.path.join(tmp, "some-other-name")
    os.rename(repo, renamed)
    env = {**os.environ, "AGENT_FABRIC_ROOT": root, "AGENT_FABRIC_STATE_DIR": os.path.join(tmp, "state"),
           "USER": "not-the-agent", "LOGNAME": "not-the-agent", "AGENT_FABRIC_AGENT": "nope",
           "CLAUDE_PROJECT_DIR": renamed}
    seen = set()
    for cwd in (tmp, renamed, os.path.join(renamed, "sub") if os.path.isdir(os.path.join(renamed, "sub")) else renamed, "/"):
        out = sh(sys.executable, IDENTITY, "--json", cwd=cwd, env=env)
        assert out.returncode == 0, out.stderr
        seen.add(json.loads(out.stdout)["agent"])
    assert seen == {id_un()}, seen


def test_context_changes_while_agent_does_not(tmp: str) -> None:
    root = fabric_fixture(tmp)
    repo = os.path.join(tmp, "whatever-name")
    git_repo(repo, "https://example.com/org/demo")
    env = {**os.environ, "AGENT_FABRIC_ROOT": root, "AGENT_FABRIC_STATE_DIR": os.path.join(tmp, "state")}
    inside = json.loads(sh(sys.executable, IDENTITY, "--json", "--cwd", repo, env=env).stdout)
    outside = json.loads(sh(sys.executable, IDENTITY, "--json", "--cwd", tmp, env=env).stdout)
    assert inside["agent"] == outside["agent"] == id_un()
    assert inside["project"] == "demo" and inside["project_source"] == "working-copy"
    assert inside["address"] == f"{inside['host']}/{inside['agent']}", "the GZCoord address, composed"
    assert inside["working_copy"] == os.path.realpath(repo) or inside["working_copy"] == repo
    assert inside["working_copy_id"] == "whatever-name", "the basename is a label, reported as such"
    assert outside["project"] is None and outside["working_copy"] is None


def test_renaming_the_working_copy_keeps_project_and_agent(tmp: str) -> None:
    root = fabric_fixture(tmp)
    repo = os.path.join(tmp, "demo-one")
    git_repo(repo, "git@example.com:org/demo.git")
    env = {**os.environ, "AGENT_FABRIC_ROOT": root, "AGENT_FABRIC_STATE_DIR": os.path.join(tmp, "state")}
    before = json.loads(sh(sys.executable, IDENTITY, "--json", "--cwd", repo, env=env).stdout)
    moved = os.path.join(tmp, "demo-main")
    os.rename(repo, moved)
    after = json.loads(sh(sys.executable, IDENTITY, "--json", "--cwd", moved, env=env).stdout)
    assert before["agent"] == after["agent"] == id_un()
    assert before["project"] == after["project"] == "demo"
    assert before["working_copy_id"] == "demo-one" and after["working_copy_id"] == "demo-main"


def test_project_is_matched_by_remote_not_by_directory_name(tmp: str) -> None:
    root = fabric_fixture(tmp)
    registry = workingcopy.load_registry(os.path.join(root, "projects", "registry.json"))
    for url in ("git@example.com:org/demo.git", "https://example.com/org/demo/",
                "ssh://git@example.com/org/demo.git", "EXAMPLE.com/org/demo"):
        assert workingcopy.project_for_remote(url, registry) == "demo", url
    # example.com is not a host known to fold path case (tests/test_workingcopy.py)
    assert workingcopy.project_for_remote("example.com/Org/Demo", registry) is None
    assert workingcopy.project_for_remote("git@example.com:org/other.git", registry) is None
    lookalike = os.path.join(tmp, "demo")          # named like the project, but not it
    git_repo(lookalike, "git@example.com:org/other.git")
    assert workingcopy.resolve(lookalike, registry)["project"] is None, \
        "a directory named like a project must not be taken for it"


def test_marker_file_declares_the_project(tmp: str) -> None:
    root = fabric_fixture(tmp)
    registry = workingcopy.load_registry(os.path.join(root, "projects", "registry.json"))
    repo = os.path.join(tmp, "no-remote")
    git_repo(repo, "git@example.com:org/unregistered.git")
    with open(os.path.join(repo, workingcopy.MARKER), "w", encoding="utf-8") as fh:
        fh.write("demo\n")
    got = workingcopy.resolve(repo, registry)
    assert got["project"] == "demo" and got["project_source"] == "marker", got


def test_a_marker_naming_an_unknown_project_is_an_error_not_a_fallthrough(tmp: str) -> None:
    root = fabric_fixture(tmp)
    registry = workingcopy.load_registry(os.path.join(root, "projects", "registry.json"))
    repo = os.path.join(tmp, "bad-marker")
    git_repo(repo, "git@example.com:org/demo.git")     # the remote alone would resolve to demo
    for content, word in (("dmeo\n", "'dmeo'"), ("", "empty")):
        with open(os.path.join(repo, workingcopy.MARKER), "w", encoding="utf-8") as fh:
            fh.write(content)
        try:
            workingcopy.resolve(repo, registry)
        except SystemExit as exc:
            assert word in str(exc) and "demo" in str(exc) and workingcopy.MARKER in str(exc), str(exc)
        else:
            raise AssertionError(f"a marker reading {content!r} was accepted (or fell through to the remote)")


def test_binding_round_trip_is_stamped_by_the_os(tmp: str) -> None:
    os.environ["AGENT_FABRIC_STATE_DIR"] = os.path.join(tmp, "state")
    try:
        path = identity.write_binding({"role": "architect-cto", "agent": "forged", "host": "forged"})
        assert path.startswith(os.path.join(tmp, "state", "agents", id_un()))
        got = identity.read_binding()
        assert got["agent"] == id_un(), "the caller's `agent` must be overwritten"
        assert got["host"] == identity.current_host()
        assert got["role"] == "architect-cto"
        # A binding copied under another agent's directory is refused.
        other = os.path.join(tmp, "state", "agents", "someone-else")
        os.makedirs(other)
        with open(os.path.join(other, "binding.json"), "w", encoding="utf-8") as fh:
            json.dump({"agent": id_un(), "host": "h", "updated_at": "x"}, fh)
        try:
            identity.read_binding("someone-else")
        except SystemExit as exc:
            assert "names agent" in str(exc)
        else:
            raise AssertionError("a binding under the wrong agent directory was accepted")
    finally:
        del os.environ["AGENT_FABRIC_STATE_DIR"]


def test_launch_role_drift_is_one_sentence_or_none() -> None:
    """The launcher stamps the role a session was born with; a rebind from
    a login shell under it must be said, never silent. No stamp (not a
    fabric launch) and no difference are both None."""
    assert identity.launch_role_drift({"role": "db-admin"}, environ={}) is None
    assert identity.launch_role_drift({"role": "db-admin"}, environ={"AGENT_FABRIC_LAUNCH_ROLE": "db-admin"}) is None
    d = identity.launch_role_drift({"role": "db-admin"}, environ={"AGENT_FABRIC_LAUNCH_ROLE": "backend-dev"})
    assert d and "launched as backend-dev" in d and "binding now db-admin" in d and "relaunch" in d, d
    d = identity.launch_role_drift({}, environ={"AGENT_FABRIC_LAUNCH_ROLE": "backend-dev"})
    assert d and "binding now (none)" in d, d


def test_atomic_write_leaves_the_old_file_whole_on_failure(tmp: str) -> None:
    """A write that dies after the temporary is opened leaves the target
    untouched and no temporary behind; a completed write is the new bytes,
    with the old file's mode kept, or the mode asked for."""
    path = os.path.join(tmp, "aw", "state.json")
    os.makedirs(os.path.dirname(path))
    identity.atomic_write(path, '{"v": 1}\n', mode=0o600)
    assert open(path).read() == '{"v": 1}\n' and (os.stat(path).st_mode & 0o777) == 0o600
    class Boom(Exception): pass
    real_replace = identity.os.replace
    identity.os.replace = lambda *a, **k: (_ for _ in ()).throw(Boom())
    try:
        try:
            identity.atomic_write(path, '{"v": 2}\n')
        except Boom:
            pass
        else:
            raise AssertionError("the injected failure did not propagate")
    finally:
        identity.os.replace = real_replace
    assert open(path).read() == '{"v": 1}\n', "the target was torn or changed by a failed write"
    assert not [n for n in os.listdir(os.path.dirname(path)) if n.startswith(".tmp-")], "a temporary was left behind"
    identity.atomic_write(path, "v3\n")
    assert open(path).read() == "v3\n" and (os.stat(path).st_mode & 0o777) == 0o600, "the mode was not kept"


def test_agent_state_mutations_serialize_across_processes(tmp: str) -> None:
    """Two processes doing read-modify-write on the binding under
    update_binding never lose an increment; history lines never interleave.
    (Without the lock, N concurrent +1s on one counter end below N.)"""
    state = os.path.join(tmp, "state-lock")
    code = f"""
import importlib.util, os, sys
os.environ["AGENT_FABRIC_STATE_DIR"] = {state!r}
spec = importlib.util.spec_from_file_location("i", {os.path.join(ROOT, "runtime", "identity.py")!r})
i = importlib.util.module_from_spec(spec); spec.loader.exec_module(i)
import time
for _ in range(25):
    def bump(b):
        n = b.get("counter", 0); time.sleep(0.001); return {{**b, "counter": n + 1}}
    i.update_binding(bump)
    i.append_history({{"pid": os.getpid()}})
"""
    procs = [subprocess.Popen([sys.executable, "-c", code]) for _ in range(4)]
    assert all(p.wait(timeout=120) == 0 for p in procs)
    os.environ["AGENT_FABRIC_STATE_DIR"] = state
    try:
        assert identity.read_binding()["counter"] == 100, identity.read_binding()
        lines = open(os.path.join(identity.agent_state_dir(), "role-history.jsonl")).read().splitlines()
        assert len(lines) == 100 and all(json.loads(l)["pid"] for l in lines), "history lines interleaved or lost"
    finally:
        del os.environ["AGENT_FABRIC_STATE_DIR"]


def test_a_binding_from_another_host_is_refused(tmp: str) -> None:
    """The login is the identity; the state is a runtime instance on one
    machine. A binding stamped by another host — a shared or synced home —
    is refused with the rebind command, never trusted."""
    os.environ["AGENT_FABRIC_STATE_DIR"] = os.path.join(tmp, "state-host")
    try:
        path = identity.write_binding({"role": "db-admin"})
        assert identity.read_binding()["role"] == "db-admin"
        d = json.load(open(path)); d["host"] = "another-machine"
        json.dump(d, open(path, "w"))
        try:
            identity.read_binding()
        except SystemExit as exc:
            assert "written on host 'another-machine'" in str(exc.code) and "bin/fabric-role bind" in str(exc.code), exc.code
        else:
            raise AssertionError("a binding from another host was accepted")
    finally:
        del os.environ["AGENT_FABRIC_STATE_DIR"]


def test_the_job_list_is_the_logins_and_serialized(tmp: str) -> None:
    """jobs.json: empty until written, stamped by the OS, refused when it
    names another agent or host, and read-modify-write under the lock."""
    os.environ["AGENT_FABRIC_STATE_DIR"] = tmp
    try:
        assert identity.read_jobs() == {"agent": identity.current_agent(), "host": identity.current_host(),
                                        "seq": 0, "jobs": []}
        def add(doc):
            doc["seq"] += 1
            doc["jobs"].append({"id": f"j-{doc['seq']}", "title": "t", "agent": "forged"})
        identity.update_jobs(add)
        doc = identity.read_jobs()
        assert doc["seq"] == 1 and doc["jobs"][0]["id"] == "j-1" and doc["agent"] == identity.current_agent(), doc
        path = identity.jobs_path()
        raw = json.load(open(path))
        raw["agent"] = "someone-else"
        json.dump(raw, open(path, "w"))
        try:
            identity.read_jobs()
            raise AssertionError("another agent's list was read")
        except SystemExit as exc:
            assert "someone-else" in str(exc), exc
    finally:
        del os.environ["AGENT_FABRIC_STATE_DIR"]


def main() -> int:
    cases = [
        test_atomic_write_leaves_the_old_file_whole_on_failure,
        test_agent_state_mutations_serialize_across_processes,
        test_a_binding_from_another_host_is_refused,
        test_the_job_list_is_the_logins_and_serialized,
        test_launch_role_drift_is_one_sentence_or_none,
        test_agent_is_the_effective_login,
        test_agent_is_computed_from_the_uid_not_from_names,
        test_agent_ignores_cwd_and_environment,
        test_context_changes_while_agent_does_not,
        test_renaming_the_working_copy_keeps_project_and_agent,
        test_project_is_matched_by_remote_not_by_directory_name,
        test_marker_file_declares_the_project,
        test_a_marker_naming_an_unknown_project_is_an_error_not_a_fallthrough,
        test_binding_round_trip_is_stamped_by_the_os,
    ]
    failures = 0
    for case in cases:
        with tempfile.TemporaryDirectory() as tmp:
            try:
                case(tmp) if case.__code__.co_argcount else case()
                print(f"  ok   {case.__name__}")
            except AssertionError as exc:
                failures += 1
                print(f"  FAIL {case.__name__}: {exc}")
    print(f"\n{len(cases) - failures}/{len(cases)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
