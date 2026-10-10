#!/usr/bin/env python3
"""tools/fabric/memory_mcp/ and bin/fabric-memory-mcp (agent-fabric ADR-049): the three tools on a fixture
corpus (ranking, role and project first, the decay marker, a section a merge_target correction replaced,
paths outside the roots, a call counted without its query), and the real server process over stdio as Claude
Code runs it: initialize, tools/list, tools/call. Plain script: prints ok/FAIL, exit 1 on any failure."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
sys.path.insert(0, os.path.join(HERE, "runtime"))
from assembler.slices import retire_in_siblings  # noqa: E402
import memory_index  # noqa: E402
from memory_mcp import calls, marks, server as srv, tools  # noqa: E402

BIN = os.path.join(HERE, "bin", "fabric-memory-mcp")
# What a person asking this would expect first. Kept with the tests so a change to the ranking shows what it moved.
EXPECTED_HITS = (
    ("how long may a subprocess run", "python-dev", "f:domains/python-dev/domain/subprocess-timeouts#1"),
    ("which interpreter does the launcher pin", "python-dev", "p:python-dev/solution/launcher-pin#1"),
    ("retry backoff rule", "python-dev", "p:python-dev/workflow/retry-2#1"),
    ("what does merge_target do", "python-dev", "p:python-dev/workflow/idents#1"),
    ("css animation", "web-dev", "f:domains/web-dev/domain/css-timeouts#1"),
)


def slice_text(role: str, kind: str, topic: str, description: str, sections: dict[str, str], project: str | None = None,
               shared_with: tuple[str, ...] = ()) -> str:
    origin = "origin:\n  - agent: \"a-agent\"\n    host: \"h\"\n" + (f"    project: \"{project}\"\n" if project else "")
    shared = "".join(f"shared_with:\n" if i == 0 else "" for i in range(1 if shared_with else 0)) + "".join(
        f"  - \"{r}\"\n" for r in shared_with)
    front = (f"---\nrole: \"{role}\"\nclass: {kind}\ntopic: \"{topic}\"\ndescription: \"{description}\"\ntier: 2\n"
             f"knowledge_scope: full\n{shared}distilled_at: \"2026-10-05\"\n{origin}---\n\n")
    return front + "".join(f"## {h}\n\n{t}\n\n*Observed 2026-10-0{n + 1} (a-agent)*\n\n" for n, (h, t) in enumerate(sections.items()))


def put(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: str = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}")
        if not good and detail:
            print("      " + detail.replace("\n", "\n      "))
        fails += not good

    with tempfile.TemporaryDirectory() as t:
        mem, wc, state = f"{t}/op/memory", f"{t}/wc", f"{t}/state"
        outside = f"{t}/outside.md"
        put(outside, slice_text("python-dev", "domain", "leak", "leaked", {"leak heading": "SECRET-OUTSIDE zebra"}))
        put(f"{mem}/domains/python-dev/domain/subprocess-timeouts.md", slice_text(
            "python-dev", "domain", "subprocess-timeouts", "every subprocess has a timeout",
            {"a subprocess without a timeout hangs the hook": "Pass timeout= and check the return code of every subprocess call."}))
        put(f"{mem}/domains/web-dev/domain/css-timeouts.md", slice_text(
            "web-dev", "domain", "css-timeouts", "animation timeouts in css",
            {"timeouts timeouts timeouts in css animation": "subprocess subprocess timeouts timeouts timeouts animation"}))
        put(f"{wc}/.agent-fabric/memory/python-dev/solution/launcher-pin.md", slice_text(
            "python-dev", "solution", "launcher-pin", "the launcher pins its interpreter",
            {"the launcher pins the interpreter at runtime/python.json": "The launcher reads runtime/python.json and refuses an older one."},
            project="agent-fabric"))
        put(f"{wc}/.agent-fabric/memory/python-dev/solution/other-project-pin.md", slice_text(
            "python-dev", "solution", "other-project-pin", "another project pins its interpreter too",
            {"the other project pins the interpreter at its own file": "launcher launcher launcher interpreter interpreter pin pin pin pin"},
            project="gzapp"))
        put(f"{wc}/.agent-fabric/memory/python-dev/workflow/shared-note.md", slice_text(
            "shared", "workflow", "shared-note", "a note two roles own", {"two roles own this note about launcher": "launcher"},
            shared_with=("python-dev", "web-dev")))
        put(f"{wc}/.agent-fabric/memory/python-dev/workflow/idents.md", slice_text(
            "python-dev", "workflow", "idents", "identifiers", {"the merge_target field names the stale section": "merge_target replaces"}))
        put(f"{mem}/domains/python-dev/domain/twin-a.md", slice_text(
            "python-dev", "domain", "twin-a", "twin", {"twin cue text": "twin cue text body one"}))
        put(f"{mem}/domains/python-dev/domain/twin-b.md", slice_text(
            "python-dev", "domain", "twin-b", "twin", {"Twin cue  text": "twin cue text body two"}))
        # A correction by merge_target: the drain wrote the new section into a later part and retired the old.
        d = f"{wc}/.agent-fabric/memory/python-dev/workflow"
        put(f"{d}/retry.md", slice_text("python-dev", "workflow", "retry", "retry rule",
                                        {"retry with backoff": "STALE-RULE retry forever with no backoff", "unrelated kept": "stays"}))
        put(f"{d}/retry-2.md", slice_text("python-dev", "workflow", "retry", "retry rule",
                                          {"retry with backoff (corrected)": "FRESH-RULE retry three times with backoff"}))
        retire_in_siblings(d, "retry-2.md", "retry with backoff")
        put(f"{wc}/.agent-fabric/memory/python-dev/INDEX.md",
            "# idx\n\n## solution\n\n- [`.agent-fabric/memory/python-dev/solution/launcher-pin.md`](x) — the launcher pins its interpreter\n"
            "- [`.agent-fabric/memory/python-dev/solution/other-project-pin.md`](x) — another project pins its interpreter too\n"
            "- [`identities/roles/python-dev/charter.md`](x) — not a slice\n")
        os.symlink(outside, f"{mem}/domains/python-dev/domain/link-out.md")

        corpus = memory_index.build(mem, wc)
        sess = tools.Session(role="python-dev", project="agent-fabric", working_copy=wc, state_dir=state)

        def hit_text(text: str) -> str:
            return "\n".join(ln for ln in text.splitlines() if ln != tools.WEAK_NOTICE)

        def find(query: str, session: tools.Session = sess, **kw) -> str:
            return hit_text(tools.find(corpus, session, {"query": query, **kw})[0])

        print("memory_find")
        first = find("subprocess timeouts").splitlines()[0]
        check("the role's own slice ranks first although another role's section matches the words more often",
              first.startswith("f:domains/python-dev/domain/subprocess-timeouts#1"), first)
        check("…and without a role, BM25 alone orders them (the positive control for the line above)",
              find("subprocess timeouts", tools.Session()).splitlines()[0].startswith("f:domains/web-dev/"),
              find("subprocess timeouts", tools.Session()))
        lines = find("launcher interpreter pin").splitlines()
        check("the project's slice ranks above another project's", lines[0].startswith("p:python-dev/solution/launcher-pin#1")
              and [i for i, ln in enumerate(lines) if "other-project-pin" in ln][0] > 0, "\n".join(lines))
        nop = find("launcher interpreter pin", tools.Session(role="python-dev")).splitlines()
        check("…and without a project, BM25 alone puts the other project's slice first (the positive control)",
              nop[0].startswith("p:python-dev/solution/other-project-pin"), "\n".join(nop))
        check("a solution hit carries its Observed date and 'verify against the tree'",
              "| 2026-10-01 |" in lines[0] and lines[0].endswith("| verify against the tree"), lines[0])
        check("a domain hit has no decay marker", "verify against" not in first, first)
        check("a hit is one line: section id, heading, kind, date, scope, size, score; no body",
              first.count("|") == 6 and re.fullmatch(r"\d+\.\d (strong|weak|none)", first.split(" | ")[-1]) is not None and "Pass timeout" not in first, first)
        check("a role named in shared_with ranks as its own",
              hit_text(tools.find(corpus, tools.Session(role="web-dev"), {"query": "launcher note"})[0]).splitlines()[0].startswith("p:python-dev/workflow/shared-note"))
        check("the limit bounds the list; what it leaves out is counted by scope",
              len(find("pin interpreter launcher timeout", limit=2).splitlines()) == 3
              and find("pin interpreter launcher timeout", limit=2).splitlines()[-1].startswith("+") and " more: " in find("pin interpreter launcher timeout", limit=2))
        wide = find("pin interpreter launcher timeout subprocess retry", tools.Session(), max_tokens=1000)
        narrow = find("pin interpreter launcher timeout subprocess retry", tools.Session(), max_tokens=40)
        check("max_tokens bounds the reply (one hit at least), and the rest is counted",
              len(narrow.splitlines()) < len(wide.splitlines()) and narrow.splitlines()[0].count("|") >= 6 and any(ln.startswith("+") for ln in narrow.splitlines()))
        check("one best section per slice", len({ln.split("#")[0] for ln in wide.splitlines() if not ln.startswith("+")}) == len([ln for ln in wide.splitlines() if not ln.startswith("+")]))
        check("an identifier is found by its parts and by itself",
              find("merge target", tools.Session()).startswith("p:python-dev/workflow/") and find("merge_target", tools.Session()).startswith("p:python-dev/workflow/"))
        check("a near-duplicate cue is shown once",
              len([ln for ln in find("twin cue text", tools.Session(), limit=8).splitlines() if ln.startswith(("f:", "p:"))]) == 1, find("twin cue text", tools.Session(), limit=8))
        check("no match answers with the nearest cue words, never an empty reply",
              find("zzzqqq").startswith("no sections match; try: ") and len(find("zzzqqq")) > 30
              and "interpreter" in find("interpretr pinning"), find("interpretr pinning"))
        check("a section a merge_target correction replaced is not returned; its replacement is",
              "retry with backoff (corrected)" in find("retry backoff") and "STALE" not in find("retry forever no backoff")
              and "retry with backoff |" not in find("retry backoff"), find("retry backoff"))
        check("a symlink out of the root is not loaded", "leak" not in find("leak heading", tools.Session()) and "zebra" not in find("zebra"))
        try:
            tools.find(corpus, sess, {})
            missing = ""
        except tools.ToolError as e:
            missing = str(e)
        check("a missing query is the tool's one-line error", missing == "query is required", missing)

        print("the offline set of expected hits (ADR-049 rule 7): the first hit of each query")
        for query, role, want in EXPECTED_HITS:
            got = hit_text(tools.find(corpus, tools.Session(role=role, project="agent-fabric"), {"query": query})[0]).splitlines()[0].split(" | ")[0]
            check(f"{query!r} as {role}: {want}", got == want, got)

        print("bands")
        exact = tools.find(corpus, sess, {"query": "the launcher pins the interpreter at runtime/python.json"})[0].splitlines()
        check("a query that is the cue itself is strong, and the list carries no weak notice",
              exact[0].endswith(" strong | verify against the tree") and exact[0].startswith("p:python-dev/solution/launcher-pin#1"), "\n".join(exact))
        vague = tools.find(corpus, sess, {"query": "interpreter"})[0].splitlines()
        check("a one-word match is weak (score under the strong threshold): the list opens with the weak notice",
              vague[0] == tools.WEAK_NOTICE and " weak" in vague[1], "\n".join(vague))
        stray = tools.find(corpus, sess, {"query": "launcher zzzaaa yyybbb xxxccc wwwddd"})[0].splitlines()
        check("a hit that covers little of the query is none", stray[0] == tools.WEAK_NOTICE and " none" in stray[1], "\n".join(stray))
        B = memory_index
        check("band: strong needs the score and the coverage", B.band(30, 0.9, 2.0) == "strong" and B.band(11.9, 0.9, 2.0) == "weak"
              and B.band(30, 0.54, 2.0) == "weak" and B.band(30, 0.29, 2.0) == "none")
        check("band: a dead heat on a partial match is not strong; on a near-full match it is",
              B.band(30, 0.6, 1.0) == "weak" and B.band(30, 0.8, 1.0) == "strong")

        print("memory_read")
        ref = "p:python-dev/solution/launcher-pin"
        listing = tools.read(corpus, sess, {"ids": [ref]})[0]
        check("a slice id alone: its section list", listing.startswith(ref + "#1 | the launcher pins the interpreter at runtime/python.json | ~"), listing)
        body = tools.read(corpus, sess, {"ids": [ref + "#1"]})[0]
        check("a section id: provenance line, heading, text", body.splitlines()[0].startswith(ref + "#1 · solution · project · python-dev · observed 2026-10-01")
              and "verify against the tree" in body.splitlines()[0] and "refuses an older one" in body, body)
        check("…and the cue lines of related slices, not the slice itself",
              any(ln.startswith("related: p:python-dev/solution/other-project-pin#1") for ln in body.splitlines())
              and not any(ln.startswith("related: " + ref) for ln in body.splitlines()), body)
        two = tools.read(corpus, sess, {"ids": [ref + "#1", "f:domains/python-dev/domain/subprocess-timeouts#1"]})
        check("several ids in one call, each served", len(two[1]) == 2 and "Pass timeout=" in two[0] and "refuses an older one" in two[0])
        check("an id among several that is not found is said in its place",
              "p:python-dev/solution/nope: no such slice" in tools.read(corpus, sess, {"ids": [ref + "#1", "p:python-dev/solution/nope"]})[0])
        cut = tools.read(corpus, sess, {"ids": [ref + "#1"], "max_tokens": 20})[0]
        check("max_tokens cuts the reply and says so", cut.endswith("[cut at max_tokens 20]") and len(cut) < 200, cut)
        for bad in ("../../etc/passwd", "/etc/passwd", "f:../../../outside", "f:domains/python-dev/domain/link-out", "p:../../x", "nope"):
            try:
                out = tools.read(corpus, sess, {"ids": [bad]})[0]
            except tools.ToolError as e:
                out = "refused: " + str(e)
            check(f"id {bad!r} is refused and reads nothing", out.startswith("refused") and "SECRET-OUTSIDE" not in out, out)
        try:
            tools.read(corpus, sess, {})
            err = ""
        except tools.ToolError as e:
            err = str(e)
        check("no ids is the tool's one-line error", err.startswith("ids is required"), err)

        print("memory_index")
        idx = tools.index(corpus, sess, {})[0].splitlines()
        check("the role's index lines, mapped to ids; a line that is not a slice is dropped; another project's slice is not shown",
              len(idx) == 1 and idx[0].startswith("p:python-dev/solution/launcher-pin | solution |"), "\n".join(idx))
        check("a role with no index is said", tools.index(corpus, sess, {"role": "web-dev"})[0].startswith("no index for role web-dev"))

        print("the library, without the MCP layer")
        code = ("import sys; sys.path.insert(0, sys.argv[1]); import memory_index; ix = memory_index.build(sys.argv[2], sys.argv[3]); "
                "h = ix.find('how long may a subprocess run', 'python-dev', None)[0]; "
                "print(memory_index.section_id(h.section), h.band, 'memory_mcp' in sys.modules)")
        r = subprocess.run([sys.executable, "-I", "-c", code, os.path.join(HERE, "tools", "fabric"), mem, wc], capture_output=True, text=True, timeout=60)
        check("a hook can build and query the same index; the MCP layer is not imported",
              r.returncode == 0 and r.stdout.split() == ["f:domains/python-dev/domain/subprocess-timeouts#1", "weak", "False"], r.stdout + r.stderr)

        print("memory_mark")
        marks_log = f"{state}/{marks.LOG}"
        ok_id = "p:python-dev/solution/launcher-pin#1"
        out, ids = tools.mark(corpus, sess, {"id": ok_id, "verdict": "stale", "note": "the pin moved to 3.14"})
        row = json.loads(open(marks_log).read().splitlines()[-1])
        check("a mark is one line in the login's state: time, id, verdict, note", out == f"marked {ok_id} stale" and ids == [ok_id]
              and set(row) == {"t", "id", "verdict", "note"} and row["id"] == ok_id and row["verdict"] == "stale" and row["note"] == "the pin moved to 3.14", str(row))
        check("…private, and the corpus is untouched", oct(os.stat(marks_log).st_mode & 0o777) == "0o600"
              and "stale" not in open(f"{wc}/.agent-fabric/memory/python-dev/solution/launcher-pin.md").read())
        for label, args in (("a verdict outside helpful | wrong | stale", {"id": ok_id, "verdict": "bad"}),
                            ("an id memory_find never returned", {"id": "p:python-dev/solution/nope#1", "verdict": "wrong"}),
                            ("a section that is not there", {"id": ok_id.replace("#1", "#9"), "verdict": "wrong"}),
                            ("a path", {"id": "../../etc/passwd", "verdict": "wrong"}), ("no verdict", {"id": ok_id})):
            before = open(marks_log).read()
            try:
                tools.mark(corpus, sess, args)
                err = ""
            except tools.ToolError as e:
                err = str(e)
            check(f"{label}: refused in one line, nothing recorded", err != "" and open(marks_log).read() == before, err)
        long_note = tools.mark(corpus, sess, {"id": ok_id, "verdict": "helpful", "note": "x" * 1000})
        check("a long note is cut", len(json.loads(open(marks_log).read().splitlines()[-1])["note"]) <= tools.NOTE_CLIP and long_note[1] == [ok_id])
        ro = f"{t}/state-ro"
        os.makedirs(ro, mode=0o500)
        try:
            tools.mark(corpus, tools.Session(role="python-dev", state_dir=f"{ro}/agent"), {"id": ok_id, "verdict": "helpful"})
            lost = ""
        except tools.ToolError as e:
            lost = str(e)
        finally:
            os.chmod(ro, 0o700)
        check("a mark that cannot be written is an error, never a silent success", lost.startswith("mark not recorded"), lost)

        print("the count of calls")
        log = f"{state}/{calls.LOG}"
        s = srv.Server(corpus, sess, state)
        s.call("memory_find", {"query": "launcher-secret-query-text", "limit": 3})
        s.call("memory_read", {"ids": ["nope"]})
        rows = [json.loads(ln) for ln in open(log)]
        check("each call is one line: time, tool, hit count, the ids returned", [(r["tool"], r["hits"] > 0) for r in rows] == [("memory_find", True), ("memory_read", False)]
              and all({"t", "tool", "hits", "ids"} <= set(r) for r in rows) and all(r["hits"] == len(r["ids"]) for r in rows), str(rows))
        found = rows[0]["ids"]
        s.call("memory_read", {"ids": [found[0]]})
        s.call("memory_read", {"ids": ["f:domains/web-dev/domain/css-timeouts#1"]})
        s.call("memory_mark", {"id": found[0], "verdict": "helpful", "note": "launcher-secret-query-text"})
        after = [json.loads(ln).get("after_find") for ln in open(log).read().splitlines()]
        check("a read of an id the last find returned is marked after_find; another read is not; a find has no mark",
              after[0] is None and after[-3] is True and after[-2] is False and after[-1] is None, str(after))
        check("the query's text is never recorded", "launcher-secret-query-text" not in open(log).read())
        check("a mark is logged as a call with its id, not its note", json.loads(open(log).read().splitlines()[-1])["tool"] == "memory_mark"
              and json.loads(open(log).read().splitlines()[-1])["ids"] == [found[0]])
        check("the log is private", oct(os.stat(log).st_mode & 0o777) == "0o600")
        os.chmod(state, 0o500)
        try:
            res = s.call("memory_find", {"query": "launcher"})
        finally:
            os.chmod(state, 0o700)
        check("a log that cannot be written does not fail the call", res["isError"] is False)

        print("the server process, over stdio")
        env = {"PATH": os.environ.get("PATH", ""), "AGENT_FABRIC_PYTHON": sys.executable, "AGENT_FABRIC_OPERATOR": f"{t}/op",
               "AGENT_FABRIC_STATE_DIR": state}
        os.makedirs(f"{state}/agents", exist_ok=True)
        login = subprocess.run([sys.executable, "-c", "import pwd,os;print(pwd.getpwuid(os.geteuid()).pw_name)"], capture_output=True,
                               text=True, timeout=30).stdout.strip()
        put(f"{state}/agents/{login}/binding.json", json.dumps({"agent": login, "role": "python-dev", "project": "agent-fabric",
                                                              "working_copy": wc}))
        msgs = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                                                                              "clientInfo": {"name": "t", "version": "0"}}},
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "memory_find", "arguments": {"query": "subprocess timeout"}}},
                {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "memory_read", "arguments": {"ids": ["../../etc/passwd"]}}},
                {"jsonrpc": "2.0", "id": 5, "method": "nope"},
                {"jsonrpc": "2.0", "id": 6, "method": "ping"}]
        r = subprocess.run([BIN], input="\n".join(json.dumps(m) for m in msgs) + "\nnot json\n", env=env, capture_output=True, text=True,
                           timeout=60)
        out = [json.loads(ln) for ln in r.stdout.splitlines()]
        by = {o.get("id"): o for o in out}
        check("exit 0 at end of input, stderr empty", r.returncode == 0 and r.stderr == "", r.stderr)
        check("initialize: the client's protocol version, tools capability, server info",
              by[1]["result"]["protocolVersion"] == "2025-06-18" and "tools" in by[1]["result"]["capabilities"]
              and by[1]["result"]["serverInfo"]["name"] == "fabric-memory", str(by[1]))
        check("the notification gets no answer: six requests and one bad line, seven answers", len(out) == 7, str(len(out)))
        names = [x["name"] for x in by[2]["result"]["tools"]]
        check("tools/list: the four tools, each with an input schema", names == ["memory_find", "memory_read", "memory_index", "memory_mark"]
              and all(x["inputSchema"]["type"] == "object" for x in by[2]["result"]["tools"]), str(names))
        text = hit_text(by[3]["result"]["content"][0]["text"])
        check("tools/call: the session's role ranks first (read from its binding)", text.splitlines()[0].startswith("f:domains/python-dev/"), text)
        check("a tool's failure is a result with isError, not a protocol error", by[4]["result"]["isError"] is True and "error" not in by[4])
        check("an unknown method is -32601; a line that is not JSON is -32700 with a null id",
              by[5]["error"]["code"] == -32601 and by[None]["error"]["code"] == -32700, str(by))
        check("the server counted its calls in the login's state, without the query",
              os.path.isfile(f"{state}/agents/{login}/{calls.LOG}") and "subprocess timeout" not in open(f"{state}/agents/{login}/{calls.LOG}").read())

    print("test_memory_mcp:", "OK" if not fails else f"{fails} FAILED")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
