#!/usr/bin/env python3
"""Tests for tools/fabric/github/review_coverage.py: the v2 marker and the coverage block, the one parser post-review
and every reader use (agent-fabric ADR-065 §2 C, §5 rule 4). Pure logic first, then git (a real repository in a
scratch directory; no network). Each threat of the request has its case, with the positive control beside it."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

from git_env import git_env, scrub_process_env  # noqa: E402 — tests/, the script's own directory
from instance_fixtures import own_instance_tree  # noqa: E402 — tests/, the script's own directory
own_instance_tree()
scrub_process_env()

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
from github import review_coverage as rc  # noqa: E402

BASE, HEAD, CARD, CONFIG = "1" * 40, "2" * 40, "3" * 40, "4" * 64
MARKER = f"<!-- agent-fabric-review v2 base={BASE} head={HEAD} card={CARD} config={CONFIG} -->"


def block(paths: dict, lenses: dict | None = None, fence: str = "```") -> str:
    return f"{fence}{rc.BLOCK_INFO}\n{json.dumps({'paths': paths, 'lenses': {} if lenses is None else lenses}, indent=1)}\n{fence}"


def read_all(*names: str) -> dict:
    return {n: {"status": "read"} for n in names}


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: object = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {str(detail)[:600]}"))
        fails += not good

    def refused(text: str) -> str:
        """The refusal parse_block gives a block's JSON, or "" when it reads."""
        try:
            rc.parse_block(text)
            return ""
        except rc.CoverageError as e:
            return str(e)

    print("the marker: the whole first line, four fields")
    m = rc.parse_marker(MARKER + "\nbody")
    check("a v2 first line reads", m == rc.Marker(BASE, HEAD, CARD, CONFIG), m)
    check("and writes back byte for byte", rc.format_marker(BASE, HEAD, CARD, CONFIG) == MARKER and m.line() == MARKER)
    check("CRLF line ends read", rc.parse_marker(MARKER + "\r\nx") == m)
    for label, line in (("a short sha", MARKER.replace(BASE, "1" * 39)), ("uppercase hex", MARKER.replace(CONFIG, "A" * 64)),
                        ("a short config", MARKER.replace(CONFIG, "4" * 63)), ("a v3", MARKER.replace("v2", "v3")),
                        ("trailing text on the line", MARKER + " x"), ("no card", MARKER.replace(f"card={CARD} ", "")),
                        ("fields out of order", f"<!-- agent-fabric-review v2 head={HEAD} base={BASE} card={CARD} config={CONFIG} -->")):
        check(f"{label}: no marker", rc.parse_marker(line + "\nx") is None)
    check("a marker on the second line is not the first line", rc.parse_marker("x\n" + MARKER) is None)
    try:
        rc.format_marker("abc", HEAD, CARD, CONFIG)
        check("a malformed field is not written", False)
    except rc.CoverageError:
        check("a malformed field is not written", True)

    print("the block: JSON by the contract, each key once")
    good = json.dumps({"paths": {"a.py": {"status": "read"}, "b.py": {"status": "not read", "reason": "binary"}},
                       "lenses": {"security": "applied", "perf": "not applied"}})
    cov = rc.parse_block(good)
    check("a block reads: paths with status and reason, lenses", cov.paths == {"a.py": ("read", ""), "b.py": ("not read", "binary")}
          and cov.lenses == {"security": "applied", "perf": "not applied"}, cov)
    check("not_read names the paths", cov.not_read == ["b.py"])
    check("no lenses is a block", refused('{"paths": {}, "lenses": {}}') == "")
    for label, text in (
        ("not JSON", "{"), ("a list", "[]"), ("a key missing", '{"paths": {}}'), ("an extra key", '{"paths": {}, "lenses": {}, "x": 1}'),
        ("paths a list", '{"paths": [], "lenses": {}}'),
        ("a duplicate top-level key", '{"paths": {}, "paths": {}, "lenses": {}}'),
        ("a duplicate path", '{"paths": {"a": {"status": "read"}, "a": {"status": "not read", "reason": "x"}}, "lenses": {}}'),
        ("a duplicate lens", '{"paths": {}, "lenses": {"l": "applied", "l": "not applied"}}'),
        ("a status that is neither", '{"paths": {"a": {"status": "skimmed"}}, "lenses": {}}'),
        ("a status missing", '{"paths": {"a": {"reason": "x"}}, "lenses": {}}'),
        ("an unknown entry key", '{"paths": {"a": {"status": "read", "why": "x"}}, "lenses": {}}'),
        ("not read without a reason", '{"paths": {"a": {"status": "not read"}}, "lenses": {}}'),
        ("not read with a blank reason", '{"paths": {"a": {"status": "not read", "reason": "  "}}, "lenses": {}}'),
        ("a reason that is not a string", '{"paths": {"a": {"status": "not read", "reason": 3}}, "lenses": {}}'),
        ("a lens state that is neither", '{"paths": {}, "lenses": {"l": "maybe"}}'),
        ("NaN", '{"paths": {}, "lenses": {}, "n": NaN}'),
        ("a newline in a path", json.dumps({"paths": {"a\nb": {"status": "read"}}, "lenses": {}})),
        ("a control character in a path", json.dumps({"paths": {"a\x1bb": {"status": "read"}}, "lenses": {}})),
        ("an empty path", '{"paths": {"": {"status": "read"}}, "lenses": {}}'),
        ("a newline in a lens", json.dumps({"paths": {}, "lenses": {"a\nb": "applied"}})),
        ("a huge block", json.dumps({"paths": {f"p{i}": {"status": "read"} for i in range(rc.MAX_BLOCK_CHARS // 10)}, "lenses": {}})),
        ("a huge reason", json.dumps({"paths": {"a": {"status": "not read", "reason": "x" * 1001}}, "lenses": {}})),
        ("a deeply nested value", "[" * 100000 + "]" * 100000),
    ):
        check(f"{label}: refused", refused(text) != "", text[:60])
    check("a path with a backquote run is data, not a fence",
          refused(json.dumps({"paths": {"a```b": {"status": "read"}}, "lenses": {}})) == "")

    print("the one block of a body: exactly one, closed, in a fence of its own")
    body = f"findings\n\n{block(read_all('a.py'))}\n"
    cov, span = rc.read_block(body)
    check("one block reads, with its span", list(cov.paths) == ["a.py"] and span == (2, len(body.split("\n")) - 2), span)
    check("without_block takes it out and keeps the findings", rc.without_block(body, span) == "findings", rc.without_block(body, span))

    def block_refusal(text: str) -> str:
        try:
            rc.read_block(text)
            return ""
        except rc.CoverageError as e:
            return str(e)

    one = block(read_all("a.py"))
    for label, text in (
        ("no block", "findings"),
        ("two blocks", f"{one}\n\n{one}"),
        ("a second block in a longer fence", f"{one}\n\n````text\n{one}\n````"),
        ("a second block behind a quote marker", f"{one}\n\n> {one.replace(chr(10), chr(10) + '> ')}"),
        ("a second block opened in a list item", f"{one}\n\n- {one.splitlines()[0]}\n  {{}}\n  ```"),
        ("a block never closed", one.rsplit("\n", 1)[0]),
        ("a block only inside another fence", f"````text\n{one}\n````"),
        ("tilde fence naming it twice", f"{block(read_all('a'), fence='~~~')}\n{block(read_all('a'), fence='~~~')}"),
        ("another info string", one.replace("v1", "v2")),
    ):
        check(f"{label}: refused", block_refusal(text) != "", text[:50])
    check("tildes and a longer fence read", block_refusal(block(read_all("a"), fence="~~~")) == ""
          and block_refusal(block(read_all("a"), fence="`````")) == "")
    # A closing line of fewer backticks does not close a four-backtick block, so the JSON swallows it and is refused.
    check("…it is part of the JSON, which then does not read",
          block_refusal(f"````{rc.BLOCK_INFO}\n{json.dumps({'paths': {}, 'lenses': {}})}\n```\n````") != "")
    check("a block indented four spaces is code, not a block", block_refusal("    " + one.replace("\n", "\n    ")) != "")

    print("the posted block is the parsed data re-written")
    hostile = rc.Coverage({"a```b.py": ("read", ""), "c d": ("not read", "why `x`")}, {"l": "applied"})
    text = rc.render_block(hostile)
    check("a fence longer than any backtick run of the data", text.startswith("````" + rc.BLOCK_INFO) and text.endswith("\n````"), text)
    check("it reads back to the same data", rc.read_block(text)[0] == hostile)
    check("non-ASCII is escaped, so a separator stays visible", " " not in text and "\\u2028" in text)
    check("one line holds no raw newline of a value", all(rc.parse_block(text.split("\n", 1)[1].rsplit("\n", 1)[0]).paths))
    check("a plain block uses three backticks", rc.render_block(rc.Coverage({"a": ("read", "")}, {})).startswith("```" + rc.BLOCK_INFO))

    print("what a review reads as (the readers' one question)")
    full = f"{MARKER}\n**Blind review**\n\nfindings\n\n{block(read_all('a.py', 'b.py'))}\n"
    r = rc.read_review(full)
    check("complete: counts, no reason", r.counts and r.why_not == "" and r.marker.head == HEAD, r)
    partial = full.replace('"status": "read"', '"status": "not read", "reason": "too large"', 1)
    r = rc.read_review(partial)
    check("one path not read: does not count, says how many", not r.counts and r.why_not == "partial coverage: 1 path(s) not read", r)
    check("v1, unmarked and other markers are not v2", all(rc.read_review(b) is None for b in (
        "<!-- agent-fabric-review v1 -->\nx", "x", "", "<!-- agent-fabric-engine-unavailable v1 -->", "  " + MARKER)))
    for label, b in (("a marker that does not read", MARKER.replace(BASE, "z" * 40) + "\n" + block(read_all("a"))),
                     ("a v2 prefix and nothing else", "<!-- agent-fabric-review v2 -->\n" + block(read_all("a"))),
                     ("no block", MARKER + "\nfindings"),
                     ("two blocks", MARKER + f"\n{one}\n{one}"),
                     ("a bad block", MARKER + "\n```agent-fabric-coverage v1\n{\n```")):
        r = rc.read_review(b)
        check(f"{label}: read as not counted, never raised", r is not None and not r.counts and r.why_not != "", r)
    check("a marker-like line later in the body does not make a review v2", rc.read_review("findings\n" + MARKER + "\n" + one) is None)
    check("marker_like_lines finds one at any depth, any version",
          rc.marker_like_lines(f"a\n  {MARKER}\n> x\n<!-- agent-fabric-review v1 -->") == [2, 4]
          and rc.marker_like_lines("<!-- something else -->") == [] and rc.marker_like_lines("no") == [])

    print("the paths of a range")
    check("both directions: all named, none extra", rc.check_paths(rc.Coverage({"a": ("read", ""), "b": ("read", "")}, {}), ["a", "b"]) == "")
    check("a path omitted", "omits 1" in rc.check_paths(rc.Coverage({"a": ("read", "")}, {}), ["a", "b"]))
    check("a path outside the range", "outside the range" in rc.check_paths(rc.Coverage({"a": ("read", ""), "z": ("read", "")}, {}), ["a"]))
    check("an empty range with an empty block", rc.check_paths(rc.Coverage({}, {}), []) == "")
    try:
        rc.check_paths(rc.Coverage({}, {}), ["a\nb"])
        check("a changed path with a newline is refused, not recorded", False)
    except rc.CoverageError:
        check("a changed path with a newline is refused, not recorded", True)

    print("git: the range's paths and ancestry, in a real repository")
    with tempfile.TemporaryDirectory() as tmp:
        env = git_env()

        def git(*args: str, input: bytes | None = None) -> str:
            r = subprocess.run(["git", "-C", tmp, *args], capture_output=True, env=env, timeout=60, input=input)
            if r.returncode:
                raise RuntimeError(f"git {args}: {r.stderr.decode()}")
            return r.stdout.decode().strip()

        def commit(msg: str, files: dict[str, str | None]) -> str:
            for name, text in files.items():
                path = os.path.join(tmp, name)
                if text is None:
                    os.remove(path)
                    continue
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "w", encoding="utf-8") as f:
                    f.write(text)
            git("add", "-A")
            git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", msg)
            return git("rev-parse", "HEAD")

        git("init", "-q", "-b", "main")
        c0 = commit("c0", {"a.py": "one\n", "sub/b.py": "two\n"})
        c1 = commit("c1", {"a.py": "one\nmore\n", "sub/c.py": "three\n"})
        odd = "we ird\"name\n.py"
        c2 = commit("c2", {odd: "x\n"})
        git("checkout", "-q", "-b", "other", c0)
        side = commit("side", {"d.py": "d\n"})
        git("checkout", "-q", "main")
        check("the changed paths, NUL-separated, sorted by git", rc.diff_paths(tmp, c0, c1) == ["a.py", "sub/c.py"], rc.diff_paths(tmp, c0, c1))
        check("a path with a newline and a quote is one entry, unquoted", rc.diff_paths(tmp, c1, c2) == [odd], rc.diff_paths(tmp, c1, c2))
        check("an empty range has no paths", rc.diff_paths(tmp, c1, c1) == [])
        # A rename is one path, as the reviewer's `git diff` shows it, whatever the user's diff.renames says.
        before = os.path.join(tmp, "sub", "b.py")
        c3 = commit("rename", {"sub/b2.py": open(before, encoding="utf-8").read(), "sub/b.py": None})
        for setting in ("true", "false"):
            subprocess.run(["git", "-C", tmp, "config", "diff.renames", setting], check=True, env=env, timeout=30)
            check(f"a rename is read the same under diff.renames={setting}", rc.diff_paths(tmp, c2, c3) == ["sub/b2.py"], rc.diff_paths(tmp, c2, c3))
        try:
            rc.diff_paths(tmp, "9" * 40, c1)
            check("a commit the clone lacks: refused", False)
        except rc.CoverageError:
            check("a commit the clone lacks: refused", True)
        check("an ancestor is one", rc.is_ancestor(tmp, c0, c2) and rc.is_ancestor(tmp, c2, c2))
        check("a descendant, and a side branch, are not", not rc.is_ancestor(tmp, c2, c0) and not rc.is_ancestor(tmp, side, c2))
        try:
            rc.is_ancestor(tmp, "9" * 40, c2)
            check("an object the clone lacks is an error, not 'no'", False)
        except rc.CoverageError:
            check("an object the clone lacks is an error, not 'no'", True)

    print("git in a partial clone: a missing object is refused, never fetched")
    with tempfile.TemporaryDirectory() as scratch:
        env = git_env()

        def run(repo: str, *args: str, extra: dict[str, str] | None = None) -> subprocess.CompletedProcess:
            return subprocess.run(["git", "-C", repo, *args], capture_output=True, env={**env, **(extra or {})}, timeout=120, check=False)

        def out(repo: str, *args: str) -> str:
            r = run(repo, *args)
            if r.returncode:
                raise RuntimeError(f"git {args}: {r.stderr.decode()}")
            return r.stdout.decode().strip()

        src = os.path.join(scratch, "src")
        os.mkdir(src)
        out(src, "init", "-q", "-b", "main")
        out(src, "config", "uploadpack.allowFilter", "true")
        out(src, "config", "uploadpack.allowAnySHA1InWant", "true")
        body = "".join(f"line {i}\n" for i in range(40))
        for i, files in enumerate(({"old.txt": body}, {"old.txt": None, "new.txt": body + "tail\n"}, {"x.txt": "x\n"})):
            for name, text in files.items():
                if text is None:
                    os.remove(os.path.join(src, name))
                else:
                    with open(os.path.join(src, name), "w", encoding="utf-8") as f:
                        f.write(text)
            out(src, "add", "-A")
            out(src, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", f"p{i}")
        p0, p1, p2 = (out(src, "rev-parse", f"HEAD~{n}") for n in (2, 1, 0))
        # blob:none misses the blobs a similarity-detected rename must read; depth 1 on a tree:0 clone misses p0 and p1 as commits.
        made = 0

        def clone(*filters: str) -> str:
            """A fresh partial clone: a lazy fetch fills the clone it runs in, so no two trials may share one."""
            nonlocal made
            made += 1
            dest = os.path.join(scratch, f"clone{made}")
            out(scratch, "clone", "-q", "--no-checkout", *filters, f"file://{src}", dest)
            return dest

        def blobless() -> str:
            return clone("--filter=blob:none")

        def shallow() -> str:
            return clone("--filter=tree:0", "--depth=1")

        trace = os.path.join(scratch, "trace")

        def trace_lines() -> list[str]:
            return open(trace, encoding="utf-8", errors="replace").read().splitlines() if os.path.exists(trace) else []

        def fetch_children(lines: list[str]) -> int:
            return sum(1 for ln in lines if "run_command" in ln and " fetch" in ln)

        def traced(repo: str, *args: str) -> list[str]:
            if os.path.exists(trace):
                os.remove(trace)
            run(repo, *args, extra={"GIT_TRACE": trace})
            return trace_lines()

        d = traced(blobless(), "diff", "--name-only", f"{p0}..{p1}")
        check("positive control: plain git diff in the blobless clone starts a fetch child", fetch_children(d) > 0, d[-3:])
        a = traced(shallow(), "merge-base", "--is-ancestor", p0, p2)
        check("positive control: plain git merge-base in the shallow clone starts a fetch child", fetch_children(a) > 0, a[-3:])
        d = traced(blobless(), "--no-lazy-fetch", "diff", "--name-only", f"{p0}..{p1}")
        check("negative control: --no-lazy-fetch makes the same diff start none, with a live trace", bool(d) and fetch_children(d) == 0, d[-3:])

        saved = {k: os.environ.get(k) for k in ("GIT_TRACE", "GIT_NO_LAZY_FETCH")}
        os.environ["GIT_TRACE"] = trace
        os.environ.pop("GIT_NO_LAZY_FETCH", None)
        try:
            for label, call in (("diff_paths", lambda: rc.diff_paths(blobless(), p0, p1)),
                                ("is_ancestor", lambda: rc.is_ancestor(shallow(), p0, p2))):
                if os.path.exists(trace):
                    os.remove(trace)
                try:
                    call()
                    refusal = ""
                except rc.CoverageError as e:
                    refusal = str(e)
                lines = trace_lines()
                check(f"{label}: an object the promisor clone lacks is a named refusal", bool(refusal), "no refusal")
                check(f"{label}: and it starts no fetch child", bool(lines) and fetch_children(lines) == 0,
                      f"{fetch_children(lines)} fetch child(ren) of {len(lines)} trace lines")
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

        # Each switch is proved alone: the argv flag and the environment say it twice so a git that reads only one still refuses.
        bl, sh = blobless(), shallow()
        seen: list[tuple[list[str], dict[str, str]]] = []
        real_run = subprocess.run

        def spy(argv, *a, **kw):
            seen.append((list(argv), dict(kw.get("env") or os.environ)))
            return real_run(argv, *a, **kw)
        rc.subprocess.run = spy
        try:
            for label, call in (("diff_paths", lambda: rc.diff_paths(bl, p0, p1)), ("is_ancestor", lambda: rc.is_ancestor(sh, p0, p2))):
                seen.clear()
                try:
                    call()
                except rc.CoverageError:
                    pass
                check(f"{label}: every git it runs carries --no-lazy-fetch", bool(seen) and all("--no-lazy-fetch" in a for a, _ in seen), seen)
                check(f"{label}: and GIT_NO_LAZY_FETCH=1 in its environment", bool(seen) and all(e.get("GIT_NO_LAZY_FETCH") == "1" for _, e in seen), seen)
        finally:
            rc.subprocess.run = real_run

    print(f"\ntest_review_coverage: {'OK' if not fails else f'FAILED — {fails} check(s)'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
