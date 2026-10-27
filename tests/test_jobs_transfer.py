#!/usr/bin/env python3
"""fabric-jobs export | import (agent-fabric j422 gap F2): a login's list moved between two state directories through a pipe, as
hostexec stdin will carry it. The list is built with the verbs themselves (every state, a priority, a request id, blockers, a
deliver_to, a non-ASCII title), and the proof is `list --all --json --stored` of the two lists, byte for byte. Each refusal has its
positive control: the same document imports into the same empty list when only the defect is removed. Plain script: ok/FAIL, exit 1."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from git_env import scrub_process_env  # noqa: E402
from instance_fixtures import own_instance_tree  # noqa: E402

scrub_process_env()
own_instance_tree()
ROOT = os.path.dirname(HERE)
JOBS = os.path.join(ROOT, "bin", "fabric-jobs")
MSG = "01a17c59-9346-7ee6-a8be-c994a7bd1cb3"


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: object = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {detail}"))
        fails += not good

    with tempfile.TemporaryDirectory() as tmp:
        home = os.path.join(tmp, "home")
        repo = os.path.join(tmp, "repo")
        os.makedirs(home)
        os.makedirs(repo)
        base = {k: v for k, v in os.environ.items() if not k.startswith(("GIT_", "AGENT_FABRIC_", "GITHUB_"))}

        def env(side: str) -> dict:
            return {**base, "AGENT_FABRIC_STATE_DIR": os.path.join(tmp, side), "AGENT_FABRIC_ROOT": ROOT, "HOME": home, "LC_ALL": "C"}

        def run(side: str, *argv: str, stdin: bytes | None = b"") -> subprocess.CompletedProcess:
            return subprocess.run([JOBS, *argv], cwd=repo, env=env(side), input=stdin, capture_output=True, timeout=120)

        def ok(side: str, *argv: str) -> bytes:
            r = run(side, *argv)
            assert r.returncode == 0, (argv, r.stderr)
            return r.stdout

        for title in ("first job", "ünïcode — title", "third", "fourth", "fifth", "sixth"):
            ok("src", "add", title, "--topic", "t")
        ok("src", "prio", "j2", "high")
        ok("src", "start", "j1")
        ok("src", "deliver", "j1", "owner/repo#1")
        ok("src", "start", "j3")
        ok("src", "block", "j3", "--on-request", MSG)
        ok("src", "block", "j4", "--on", "pr:owner/repo#7", "--on", f"job:someone/j2")
        ok("src", "start", "j5")
        ok("src", "pause", "j5", "set aside")
        ok("src", "drop", "j6", "not needed")
        ok("src", "done", "j1", "--no-artifact", "x")
        listing = ("list", "--all", "--json", "--stored")

        print("the round trip")
        exported = run("src", "export")
        check("export exits 0 and writes only the document on stdout", exported.returncode == 0 and exported.stderr == b"", exported.stderr)
        doc = json.loads(exported.stdout)
        check("the document names format, version, agent, seq and every job",
              doc["format"] == "fabric-jobs-export" and doc["version"] == 1 and doc["seq"] == 6 and len(doc["jobs"]) == 6 and doc["agent"], list(doc))
        check("every state is in it", {j["state"] for j in doc["jobs"]} == {"queued", "blocked", "paused", "dropped", "done"}, [j["state"] for j in doc["jobs"]])
        # What `block` learned from gh and the journal is in the blocker cache; seen_open is the memory a destination cannot re-derive.
        (cache,) = [os.path.join(d, "jobs-blockers.json") for d, _, fs in os.walk(os.path.join(tmp, "src")) if "jobs-blockers.json" in fs]
        with open(cache, encoding="utf-8") as fh:
            entries = json.load(fh)
        entries["job:someone/j2"]["seen_open"] = True
        with open(cache, "w", encoding="utf-8") as fh:
            json.dump(entries, fh)
        exported = run("src", "export")
        before = run("src", *listing).stdout
        got = run("dst", "import", stdin=exported.stdout)
        check("import into a fresh state dir exits 0 and says how many", got.returncode == 0 and b"imported 6 jobs" in got.stdout, got)
        after = run("dst", *listing)
        check("list --all --json is byte for byte the same", after.stdout == before and before != b"", (after.stderr, len(before), len(after.stdout)))
        (dcache,) = [os.path.join(d, "jobs-blockers.json") for d, _, fs in os.walk(os.path.join(tmp, "dst")) if "jobs-blockers.json" in fs]
        with open(dcache, encoding="utf-8") as fh:
            check("the blocker cache's entries came with the jobs, seen_open included", json.load(fh) == entries)
        check("export of the copy is the document it was made from", run("dst", "export").stdout == exported.stdout)
        added = ok("dst", "add", "after the move")
        check("the next id continues the counter", b"j7" in added, added)
        check("the document carries the title as UTF-8, not escapes", "ünïcode — title".encode() in exported.stdout)
        check("the unicode title survived as UTF-8", "ünïcode — title" in json.loads(before)[1]["title"])

        print("each refusal, and its positive control")

        def refused(label: str, side: str, payload: bytes, needle: str) -> None:
            r = run(side, "import", stdin=payload)
            lines = r.stderr.decode().strip().splitlines()
            check(label, r.returncode == 1 and len(lines) == 1 and needle in lines[0] and r.stdout == b"", (r.returncode, r.stderr))
            # A refusal that came after a write would still exit 1 with one line: the list file itself must be empty or absent.
            written = [os.path.join(d, "jobs.json") for d, _, fs in os.walk(os.path.join(tmp, side)) if "jobs.json" in fs]
            if side not in ("dst", "used", "counted"):
                check("  and the list was not written", not any(json.load(open(w, encoding="utf-8"))["jobs"] for w in written), written)

        def mutated(**changes) -> bytes:
            return json.dumps({**doc, **changes}).encode()

        refused("a non-empty list", "dst", exported.stdout, "not empty")
        check("it is untouched", run("dst", "export").stdout != b"" and json.loads(run("dst", "export").stdout)["seq"] == 7)
        ok("used", "add", "only one")
        ok("used", "drop", "j1", "gone")
        refused("a list with jobs", "used", exported.stdout, "not empty")
        ok("counted", "add", "x")
        (counted,) = [os.path.join(d, "jobs.json") for d, _, fs in os.walk(os.path.join(tmp, "counted")) if "jobs.json" in fs]
        with open(counted, encoding="utf-8") as fh:
            kept = json.load(fh)
        kept["jobs"] = []
        with open(counted, "w", encoding="utf-8") as fh:
            json.dump(kept, fh)
        refused("no jobs but a used id counter", "counted", exported.stdout, "not empty")
        refused("a different login", "e1", mutated(agent="somebody-else"), "somebody-else")
        refused("an unknown version", "e2", mutated(version=2), "version 2")
        refused("a version that is not an integer", "e3", mutated(version="1"), "version '1'")
        refused("another format", "e4", mutated(format="other"), "not a fabric-jobs export")
        refused("not JSON", "e5", b"{nope", "not valid JSON")
        refused("not UTF-8", "e6", b"\xff\xfe", "not UTF-8")
        refused("NaN", "e7", b'{"format": "fabric-jobs-export", "version": NaN}', "not valid JSON")
        refused("an array", "e8", b"[]", "not a fabric-jobs export")
        refused("an unknown top-level field", "e9", mutated(extra=1), "unknown field 'extra'")
        refused("no jobs list", "e10", mutated(jobs="x"), "no list of jobs")
        refused("a job that is not an object", "e11", mutated(jobs=[1]), "not an object")
        refused("a bad state", "e12", mutated(jobs=[{**doc["jobs"][0], "state": "weird"}]), "state 'weird'")
        refused("a bad priority", "e13", mutated(jobs=[{**doc["jobs"][0], "priority": "urgent"}]), "priority 'urgent'")
        refused("a duplicate id", "e14", mutated(jobs=[doc["jobs"][0]] * 2), "twice")
        refused("a counter below an id", "e15", mutated(seq=2), "seq 2")
        refused("two active jobs", "e16", mutated(jobs=[{**doc["jobs"][0], "state": "active"}, {**doc["jobs"][1], "state": "active"}]), "more than one active")
        refused("a last that is not listed", "e17", mutated(last="j99"), "last job")
        refused("a job id that is not jN", "e18", mutated(jobs=[{**doc["jobs"][0], "id": "x1"}]), "no id")
        refused("a control character in a title", "e23", mutated(jobs=[{**doc["jobs"][0], "title": "a \x1b[2J b"}]), "control character")
        refused("a control character in a topic", "e24", mutated(jobs=[{**doc["jobs"][0], "topic": "a\x07"}]), "control character")
        refused("a title of white space", "e25", mutated(jobs=[{**doc["jobs"][0], "title": "  "}]), "no title")
        refused("a working_copy that is not text", "e26", mutated(jobs=[{**doc["jobs"][0], "working_copy": 5}]), "working_copy")
        refused("blockers that are not strings", "e27", mutated(jobs=[{**doc["jobs"][0], "blockers": [1]}]), "blockers")
        refused("a time that is not a time", "e28", mutated(jobs=[{**doc["jobs"][0], "created": "x"}]), "created time")
        refused("a control character in a blocker", "e30", mutated(jobs=[{**doc["jobs"][0], "blockers": ["pr:owner/repo#7\x1b[2J"]}]), "blocker")
        refused("a blocker that is no checkable form", "e31", mutated(jobs=[{**doc["jobs"][0], "blockers": ["free text"]}]), "checkable form")
        refused("a control character in source", "e32", mutated(jobs=[{**doc["jobs"][0], "source": {"kind": "request", "from": "\x1b[31mred"}}]), "control character")
        refused("a control character in a cache detail", "e33", mutated(blocker_cache={"pr:owner/repo#7": {"state": "waiting", "detail": "\x1b]0;x\x07"}}), "control character")
        refused("a control character in a field name", "e35", mutated(jobs=[{**doc["jobs"][0], "x\x1b[2J": 1}]), "control character")
        refused("a cache detail that is not text", "e36", mutated(blocker_cache={"pr:owner/repo#7": {"detail": 5}}), "wrong type")
        deep = "[" * 1500 + "]" * 1500
        refused("a field nested 1500 deep inside a job", "e37", json.dumps({**doc, "jobs": [{**doc["jobs"][0], "x": "@@"}]}).replace('"@@"', deep).encode(), "nested deeper")
        refused("a cache entry nested 1500 deep", "e39", json.dumps({**doc, "blocker_cache": {"pr:owner/repo#7": {"x": "@@"}}}).replace('"@@"', deep).encode(), "nested deeper")
        # A complete document: whether the parser gives up (RecursionError) or reads it, the answer is one line and no traceback.
        refused("a document nested 100000 deep", "e38", b"[" * 100000 + b"]" * 100000, "")
        refused("a seen_open that is not a bool", "e34", mutated(blocker_cache={"pr:owner/repo#7": {"seen_open": "no"}}), "wrong type")
        refused("a blocker_cache that is not entries", "e29", mutated(blocker_cache={"a": 1}), "blocker_cache")
        refused("artifacts that are not strings", "e19", mutated(jobs=[{**doc["jobs"][0], "artifacts": [1]}]), "artifacts")
        check("a refused import wrote nothing", not os.path.exists(os.path.join(tmp, "e9", "agents")) or json.loads(run("e9", "export").stdout)["jobs"] == [])
        check("positive control: the unmodified document imports", run("e20", "import", stdin=exported.stdout).returncode == 0)
        check("positive control: a document with fewer jobs and a high seq imports",
              run("e21", "import", stdin=mutated(jobs=doc["jobs"][:2], seq=9, last=None)).returncode == 0)
        tty = subprocess.run(["script", "-qec", f"{JOBS} import", "/dev/null"], cwd=repo, env=env("e22"), input=b"", capture_output=True, timeout=60) if os.path.exists("/usr/bin/script") else None
        if tty is not None:
            check("a terminal on stdin is refused, not waited on", b"stdin" in tty.stdout, tty)

        print("the blocker cache is merged, not replaced")
        ok("seeded", "add", "x")
        ok("seeded", "drop", "j1", "gone")
        (seeded,) = [d for d, _, fs in os.walk(os.path.join(tmp, "seeded")) if "jobs.json" in fs]
        os.remove(os.path.join(seeded, "jobs.json"))
        mine = {"job:someone/j2": {"state": "waiting", "detail": "mine", "checked_at": 1.0}}
        with open(os.path.join(seeded, "jobs-blockers.json"), "w", encoding="utf-8") as fh:
            json.dump(mine, fh)
        stray = {**doc["blocker_cache"], "pr:other/repo#9": {"state": "cleared"}}
        check("a document with a stray cache entry imports", run("seeded", "import", stdin=mutated(blocker_cache=stray)).returncode == 0)
        with open(os.path.join(seeded, "jobs-blockers.json"), encoding="utf-8") as fh:
            merged = json.load(fh)
        check("the host's own entry is kept", merged["job:someone/j2"]["detail"] == "mine", merged)
        check("an entry no job names is not taken", "pr:other/repo#9" not in merged, merged)
        check("an entry a job names and the host lacks is taken", "pr:owner/repo#7" in merged, merged)

        print("the parser's own depth limit, whatever the interpreter's")
        # Whether json.loads gives up on a deep document depends on the interpreter; the guard is tested by making it give up.
        import importlib.util
        spec = importlib.util.spec_from_file_location("jobs_transfer_unit", os.path.join(ROOT, "tools", "fabric", "jobs.py"))
        jobs_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(jobs_mod)
        transfer = sys.modules["fabric_jobs"].transfer

        class GivesUp:
            @staticmethod
            def loads(*_args, **_kwargs):
                raise RecursionError("maximum recursion depth exceeded")
        real_json = transfer.json
        transfer.json = GivesUp
        try:
            transfer.parse("[]")
            said = "no refusal"
        except jobs_mod.Refused as exc:
            said = str(exc)
        except RecursionError:
            said = "RecursionError escaped"
        finally:
            transfer.json = real_json
        check("a parser that gives up on depth is a one-line refusal", said == "the document is nested too deeply", said)

        print("an empty list exports and imports")
        empty = run("blank", "export")
        check("an empty list round-trips", run("blank2", "import", stdin=empty.stdout).returncode == 0 and run("blank2", "export").stdout == empty.stdout)

    print(f"\ntest_jobs_transfer: {'OK' if not fails else f'FAILED — {fails} check(s)'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
