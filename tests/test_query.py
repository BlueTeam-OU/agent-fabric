#!/usr/bin/env python3
"""Tests for tools/fabric/query.py's internals; the behaviour is
tests/test_query_cli.py's, run against the shim (ADR-040 §5
rule 5). What a whole run there reaches only awkwardly is checked here
directly: what a crossref may hold and how a broken one is refused, the
ASCII-only fold, labels, the working-copy roots and the slice counts."""
from __future__ import annotations

import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
import query as q  # noqa: E402

# A test never inherits the caller's fabric or GitHub identity.
for _k in [k for k in os.environ if k.startswith(("GITHUB_", "AGENT_FABRIC_"))]:
    del os.environ[_k]

fails = 0


def check(label: str, ok: bool) -> None:
    global fails
    print(f"  {'ok  ' if ok else 'FAIL'} {label}")
    fails += not ok


def refusal(fn) -> tuple[int, str]:
    try:
        fn()
    except q.Failure as e:
        return e.code, str(e)
    return 0, ""


def main() -> int:
    d = tempfile.mkdtemp(dir=os.environ.get("TMPDIR"))
    try:
        def xref(text: str) -> str:
            p = f"{d}/x.json"
            with open(p, "w", encoding="utf-8") as fh:
                fh.write(text)
            return p

        good = xref('{"index": {"adrs": {"ADR-1": {"observations": ["a", "b"], "slices": ["s", "t"]},'
                    ' "Ünï": {"observations": [], "slices": []}}, "prs": {"#4": {"observations": ["a"]}}}}')
        check("a substring of a key, case-insensitive", q.lookup_hits(good, "adrs", "adr-") == [("ADR-1", "s, t", 2)])
        check("an empty slice list is its own, with the real count", q.lookup_hits(good, "adrs", "Ünï") == [("Ünï", "", 0)])
        check("only ASCII letters fold", q.lookup_hits(good, "adrs", "ünï") == [] and q.lookup_hits(good, "adrs", "ÜNÏ") == [])
        check("a missing slices or observations list is empty", q.lookup_hits(good, "prs", "#4") == [("#4", "", 1)])
        check("a kind the file has not is no hit", q.lookup_hits(good, "files", "x") == [])
        check("obs finds an exact element, across kinds",
              q.obs_hits(good, "a") == [("adrs", "ADR-1"), ("prs", "#4")] and q.obs_hits(good, "ab") == [])
        check("citations are the entries of every kind", q.citations(good) == 3)

        check("no index: nothing to look up, a citation count of 0",
              q.lookup_hits(xref('{"role": "r"}'), "adrs", "x") == [] and q.citations(xref("{}")) == 0)
        code, msg = refusal(lambda: q.obs_hits(xref('{"role": "r"}'), "x"))
        check("obs with no index is refused, naming the file", code == 5 and f"{d}/x.json" in msg)
        code, msg = refusal(lambda: q.lookup_hits(xref('{"index": []}'), "adrs", "x"))
        check("a list index is refused for a lookup, exit 5", code == 5 and f"{d}/x.json" in msg)
        check("an empty list index cites nothing and counts 0",
              q.obs_hits(xref('{"index": []}'), "x") == [] and q.citations(xref('{"index": []}')) == 0)
        check("a top level that is not an object is refused",
              refusal(lambda: q.lookup_hits(xref("[1]"), "adrs", "x"))[0] == 5)
        check("an entry that is not an object is refused",
              refusal(lambda: q.lookup_hits(xref('{"index": {"adrs": {"A": 1}}}'), "adrs", "A"))[0] == 5)
        check("slices that are not strings are refused",
              refusal(lambda: q.lookup_hits(xref('{"index": {"adrs": {"A": {"slices": [1]}}}}'), "adrs", "A"))[0] == 5)

        for label, text in (("truncated", '{"index": {"adrs": '), ("empty", ""),
                            ("two documents in one file", '{"index": {}}\n{"index": {}}\n')):
            code, msg = refusal(lambda: q.load(xref(text)))
            check(f"{label}: not JSON, exit 5, the file named", code == 5 and f"{d}/x.json is not JSON" in msg)
        check("a BOM is accepted", q.load(xref("﻿{}")) == {})
        code, msg = refusal(lambda: q.load(f"{d}/missing.json"))
        check("an unreadable file is exit 2, named", code == 2 and f"{d}/missing.json" in msg)

        check("a legacy crossref is labelled project/role",
              q.label_of("/m/memory/projects/proj/role/crossref.json") == "proj/role")
        check("a working copy's is labelled by its basename",
              q.label_of("/h/wc/.agent-fabric/memory/role/crossref.json") == "wc/role")
        check("sort -u: one of each", q.sort_u(["b", "a", "b"]) == ["a", "b"])

        # ── the roots: blank working-copy entries are dropped ──
        os.makedirs(f"{d}/memory")
        os.makedirs(f"{d}/wc/.agent-fabric/memory/r")
        os.environ["AGENT_FABRIC_WORKING_COPIES"] = f" \t::{d}/wc:"
        os.environ["AGENT_FABRIC_STATE_DIR"] = f"{d}/nostate"
        check("blank entries are dropped, the working copy's memory is a root",
              q.project_roots(d, f"{d}/memory") == [f"{d}/wc/.agent-fabric/memory"])
        with open(f"{d}/wc/.agent-fabric/memory/r/crossref.json", "w") as fh:
            fh.write("{}")
        check("a crossref is found two levels below a root",
              q.crossrefs(d, f"{d}/memory") == [f"{d}/wc/.agent-fabric/memory/r/crossref.json"])
        check("md slices are counted without INDEX.md", q.count_md(f"{d}/wc") == 0)
        open(f"{d}/wc/a.md", "w").close()
        open(f"{d}/wc/INDEX.md", "w").close()
        check("…and with one", q.count_md(f"{d}/wc") == 1)
        with open(f"{d}/state-binding.json", "w") as fh:
            fh.write("{broken")
        os.makedirs(f"{d}/st")
        os.replace(f"{d}/state-binding.json", f"{d}/st/binding.json")
        check("a binding that is not JSON costs the binding", q.binding_working_copy(f"{d}/st") == [])
    finally:
        for k in ("AGENT_FABRIC_WORKING_COPIES", "AGENT_FABRIC_STATE_DIR"):
            os.environ.pop(k, None)
        shutil.rmtree(d, ignore_errors=True)

    print("count_md counts what find counted (review of #73)")
    tmp2 = tempfile.mkdtemp(prefix="test_query_count.")
    try:
        role = os.path.join(tmp2, "dev")
        os.makedirs(os.path.join(role, "sub"))
        for name in ("a.md", "INDEX.md", "sub/b.md", "note.txt"):
            open(os.path.join(role, name), "w").close()
        os.makedirs(os.path.join(tmp2, "elsewhere"))
        open(os.path.join(tmp2, "elsewhere", "x.md"), "w").close()
        os.symlink(os.path.join(tmp2, "elsewhere", "x.md"), os.path.join(role, "linked.md"))
        os.symlink(os.path.join(tmp2, "elsewhere"), os.path.join(role, "linkdir"))
        check("a.md, sub/b.md and the symlinked slice; not INDEX.md, not into a linked dir", q.count_md(role) == 3)
        os.symlink(role, os.path.join(tmp2, "linkedrole"))
        check("a top directory that is a link counts nothing, as find did", q.count_md(os.path.join(tmp2, "linkedrole")) == 0)
    finally:
        shutil.rmtree(tmp2, ignore_errors=True)

    print(f"test_query.py: {fails} failure(s)" if fails else "test_query.py: all checks passed")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
