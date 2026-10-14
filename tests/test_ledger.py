#!/usr/bin/env python3
"""tests/test_ledger.py — tools/fabric/ledger.py, the file of the per-dispatch
token ledger (review economics P1): where it is, how a line is appended, how
rows are read back, how a dispatch header is read from a brief. Plain script:
ok/FAIL, exit 1 on any failure."""
from __future__ import annotations

import json
import multiprocessing
import os
import pwd
import sys
import tempfile

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools", "fabric"))
import ledger  # noqa: E402

LOGIN = pwd.getpwuid(os.getuid()).pw_name
fails = 0


def check(label: str, good: bool, detail: object = "") -> None:
    global fails
    print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {detail}"))
    fails += not good


def _append_many(args: tuple[str, int]) -> None:
    file, n = args
    for i in range(n):
        ledger.append(file, {"schema_version": 1, "engine": "codex", "pad": "x" * 6000, "i": i})


def header(body: str, fence: str = "```") -> str:
    return f"{fence}agent-fabric-dispatch v1\n{body}\n{fence}\n\n# The brief\n"


def main() -> int:
    print("the path: the hook's rule")
    check("AGENT_FABRIC_STATE_DIR wins", ledger.path({"AGENT_FABRIC_STATE_DIR": "/s", "XDG_STATE_HOME": "/x", "HOME": "/h"})
          == f"/s/agents/{LOGIN}/ledger.jsonl")
    check("else XDG_STATE_HOME", ledger.path({"XDG_STATE_HOME": "/x", "HOME": "/h"}) == f"/x/agent-fabric/agents/{LOGIN}/ledger.jsonl")
    check("else the home's .local/state", ledger.path({"HOME": "/h"}) == f"/h/.local/state/agent-fabric/agents/{LOGIN}/ledger.jsonl")
    check("an empty override is no override", ledger.path({"AGENT_FABRIC_STATE_DIR": "", "HOME": "/h"}).startswith("/h/.local/state/"))

    with tempfile.TemporaryDirectory(prefix="test_ledger.") as tmp:
        print("append: one whole line, private, concurrent writers do not interleave")
        file = os.path.join(tmp, "a", "b", "ledger.jsonl")
        ledger.append(file, {"schema_version": 1, "n": "é "})
        with open(file, "rb") as f:
            raw = f.read()
        check("one JSON line, ASCII (a separator cannot split it), newline-terminated",
              raw.endswith(b"\n") and raw.count(b"\n") == 1 and raw.isascii() and json.loads(raw)["n"] == "é ", raw)
        check("the file is 0600 and its directories 0700",
              os.stat(file).st_mode & 0o777 == 0o600 and os.stat(os.path.dirname(file)).st_mode & 0o777 == 0o700)
        busy = os.path.join(tmp, "busy.jsonl")
        with multiprocessing.Pool(4) as pool:
            pool.map(_append_many, [(busy, 25)] * 4)
        with open(busy) as f:
            lines = f.read().splitlines()
        check("four processes, 25 rows of 6 KB each: 100 whole rows, none torn",
              len(lines) == 100 and all(len(json.loads(ln)["pad"]) == 6000 for ln in lines), len(lines))
        blocked = os.path.join(tmp, "dir.jsonl")
        os.mkdir(blocked)
        try:
            ledger.append(blocked, {})
            raised = False
        except OSError:
            raised = True
        check("a file that cannot be opened raises OSError, for the caller to decide", raised)

        print("rows: v1 only, the last stop per (session_id, agent_id), bad lines counted")
        rows_file = os.path.join(tmp, "rows.jsonl")

        def line(**kw):
            return json.dumps({"schema_version": 1, "engine": "claude", "session_id": "s", "agent_id": "a", **kw}) + "\n"
        with open(rows_file, "w") as f:
            f.write(line(n=1) + line(n=2, agent_id="b") + line(n=3) + "\n" + "garbage\n" + "[1]\n"
                    + json.dumps({"schema_version": 2, "engine": "claude"}) + "\n"
                    + line(n=4, engine="codex", session_id="t", agent_id=None) + line(n=5, engine="codex", session_id="t", agent_id=None)
                    + line(n=6, agent_id=None) + line(n=7, agent_id=None))
        got, skipped = ledger.rows(rows_file)
        check("a subagent stopped twice: the later row, in the first row's place", [r["n"] for r in got][:2] == [3, 2], got)
        check("codex rows are never paired, nor a claude row whose ids are not both known",
              [r["n"] for r in got] == [3, 2, 4, 5, 6, 7], got)
        check("not JSON, not an object, another schema_version: skipped and counted, a blank line is neither", skipped == 3, skipped)
        check("an absent file is no rows, none skipped", ledger.rows(os.path.join(tmp, "none")) == ([], 0))
        nested = os.path.join(tmp, "nested.jsonl")
        with open(nested, "w") as f:
            f.write("[" * 200000 + "\n" + line(n=1))
        check("a line nested past the parser's stack is one skipped line, not an exception",
              ledger.rows(nested)[1] == 1 and [r["n"] for r in ledger.rows(nested)[0]] == [1])
        import fcntl
        held = os.open(busy, os.O_WRONLY)
        fcntl.flock(held, fcntl.LOCK_EX)
        ledger.LOCK_WAIT_S = 0.2
        try:
            ledger.append(busy, {"x": 1})
            waited = False
        except TimeoutError:
            waited = True
        finally:
            os.close(held)
            ledger.LOCK_WAIT_S = 5
        check("a lock held by another writer: a bounded wait, then an OSError the caller survives", waited and issubclass(TimeoutError, OSError))
        ledger.append(busy, {"x": 2})
        check("…and once released the next append goes through", json.loads(open(busy).read().splitlines()[-1]) == {"x": 2})
        try:
            ledger.rows(os.path.join(tmp, "dir.jsonl"))
            raised = False
        except OSError:
            raised = True
        check("a path that exists and cannot be read (a directory) raises: no rows is not the same as unreadable", raised)
        with open(rows_file, "wb") as f:
            f.write(b'\xff\xfe\n' + line(n=1).encode())
        got, skipped = ledger.rows(rows_file)
        check("…bad bytes are one skipped line, the next row is read", ([r["n"] for r in got], skipped) == ([1], 1), (got, skipped))

    print("count: a token count is a non-negative int")
    check("ints", ledger.count(0) == 0 and ledger.count(7) == 7)
    check("…below 2**53: a count past a double's exact integers is not a measurement",
          ledger.count(2 ** 53 - 1) == 2 ** 53 - 1 and ledger.count(2 ** 53) is None and ledger.count(10 ** 400) is None)
    check("not a bool, a float, a string, a negative or None", all(ledger.count(v) is None for v in (True, 1.0, "1", -1, None)))

    print("dispatch_header: the first fenced block, fields only in their shape")
    full = {"dispatch_id": "d-1", "parent_session_id": "s:1", "job_id": "j112", "project": "agent-fabric", "review_id": "pr7",
            "purpose": "review", "repository": "o/r", "pr": 7, "review_round": 2, "evidence": "pinned",
            "base_sha": "abcdef1", "head_sha": "a" * 40, "started_at": "2026-10-14T10:00:00Z", "engine": "codex"}
    kind, f = ledger.dispatch_header(header(json.dumps(full)))
    check("a whole header: attribution dispatch, every field copied, the header's engine not",
          kind == "dispatch" and f == {k: v for k, v in full.items() if k != "engine"}, f)
    kind, f = ledger.dispatch_header(header(json.dumps({"pr": True, "review_round": -1, "head_sha": "xyz", "repository": "no-slash",
                                                        "evidence": "other", "started_at": "2026-10-14T10:00:00", "job_id": "a b",
                                                        "base_sha": "ABCDEF1", "dispatch_id": ["x"]})))
    check("every field in the wrong shape is dropped (bool, negative, non-hex, no owner, a time without a zone, prose)", (kind, f) == ("dispatch", {}), f)
    check("a tilde fence of any length", ledger.dispatch_header(header('{"pr": 3}', "~~~~"))[1] == {"pr": 3})
    check("a header whose body is not an object is invalid-header", ledger.dispatch_header(header("[1]"))[0] == "invalid-header"
          and ledger.dispatch_header(header("{oops"))[0] == "invalid-header")
    check("a header never closed is invalid-header", ledger.dispatch_header("```agent-fabric-dispatch v1\n{}\n")[0] == "invalid-header")
    check("a brief whose first fence is something else, or none: inferred, nothing copied",
          ledger.dispatch_header("```python\nx\n```\n" + header('{"pr": 1}')) == ("inferred", {})
          and ledger.dispatch_header("no fence at all") == ("inferred", {}))
    check("a header after the first block is not the brief's header", ledger.dispatch_header("```text\nx\n```\n" + header('{"pr": 1}'))[0] == "inferred")

    print(f"\ntest_ledger: {'OK' if not fails else f'{fails} FAILED'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
