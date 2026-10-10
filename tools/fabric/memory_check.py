#!/usr/bin/env python3
"""tools/fabric/memory_check.py (bin/fabric-memory-check) — does a curated
slice still cite paths that exist? A slice describes a tree as of a date
and loses to the tree (layout.py); this reads each slice section's cited
repository paths and says which are gone, so the slice is corrected where
it lives instead of misleading the next session.

    fabric-memory-check [CORPUS] [--tree DIR] [--known-dir NAME]… [--all] [--json]

CONTRACT
  CORPUS   a corpus root: the fabric's memory/ (default: the operator's, roots.memory_dir())
           or a working copy's .agent-fabric/memory/. The tree its paths are
           checked in is the checkout the corpus belongs to: the parent of
           memory/, or of .agent-fabric/; --tree names it for any other root.
  SLICES   every .md file under the corpus whose front matter has a `class`
           other than `index` (README.md, RUBRIC.md and INDEX.md are not
           slices). A SECTION is a `## ` heading and its text, as
           slices.read_existing_slice splits it.
  CITES    a repository path in a section's text, backticked or bare, fenced
           code included: a run of path characters with a `/` whose first
           directory is one the tree has at its top level (or a --known-dir:
           how a directory that no longer exists at all is still recognised
           as a path), with a trailing `/`, `:LINE`, `#Lx` or punctuation
           dropped. Not a citation: a run followed by `*`, `<`, `{`, `$`, `[`
           (a pattern or a placeholder), a URL, an absolute path, `~/…`, a
           word pair like `HELLO/GOODBYE` or `P1/P2` (no such top-level
           directory). `../NAME/rest` is a path into the sibling checkout
           NAME of this tree.
  VERDICT  per path: `exists`, `stale-hard` (the tree lacks it), `unchecked`
           (a sibling path whose checkout is not beside the tree). Per
           section: stale-hard if any path is, else unchecked if any is,
           else fresh if it cites a path, else no-anchor.
  stdout   one line per finding, tab-separated:
             stale-hard  <slice>  <heading>  <path>
             unchecked   <slice>  <heading>  <path>
           (--all adds `fresh  <slice>  <heading>  <n> path(s)` and
           `no-anchor  <slice>  <heading>`), then `summary` and the counts.
           <slice> is relative to CORPUS. --json prints one document instead:
           {"corpus", "tree", "sections": [{"slice", "heading", "verdict",
           "paths": [{"path", "status"}]}], "counts": {verdict: n}}.
  stderr   `fabric-memory-check: ` and one line on a refusal.
  exit     0 whatever it found: a report, not a gate; 2 usage or an
           unreadable corpus or tree.

WHAT IT DOES NOT DO  no model, no network, no git (the tree is read as it is
on disk), nothing written. It does not see `path::symbol` anchors, dates, or
a path relative to anything but the tree root; a citation whose first
directory is gone and not named by --known-dir is not seen as a path.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)
import roots  # noqa: E402
from assembler import slices  # noqa: E402

# A run of path characters that does not start inside a longer one, a URL
# (after `:`) or an absolute path (after `/`).
CANDIDATE = re.compile(r"(?<![\w./:~@%+-])((?:\.\./)*\.?[A-Za-z0-9_][A-Za-z0-9_.@+-]*(?:/[A-Za-z0-9_.@+-]+)+/?)")
NOT_A_PATH_NEXT = frozenset("*<>{}$[]|…=")
VERDICTS = ("stale-hard", "unchecked", "fresh", "no-anchor")


class Refused(Exception):
    """One line, exit 2."""


class _Parser(argparse.ArgumentParser):
    def error(self, message: str):         # argparse prints its own usage block and exits; one line is the contract
        raise Refused(f"usage: fabric-memory-check [CORPUS] [--tree DIR] [--known-dir NAME]... [--all] [--json] ({message})")


def tree_of(corpus: str) -> str | None:
    """The checkout a corpus root belongs to, or None when the layout does not say."""
    corpus = os.path.abspath(corpus)
    if os.path.basename(corpus) != "memory":
        return None
    parent = os.path.dirname(corpus)
    return os.path.dirname(parent) if os.path.basename(parent) == ".agent-fabric" else parent


def slice_files(corpus: str) -> list[str]:
    out = []
    for directory, dirs, files in os.walk(corpus):
        dirs.sort()
        for name in sorted(files):
            if not name.endswith(".md"):
                continue
            path = os.path.join(directory, name)
            meta, _ = slices.read_existing_slice(path)
            if meta.get("class") not in (None, "index"):
                out.append(path)
    return out


def known_dirs(tree: str, extra: list[str]) -> set[str]:
    try:
        names = {e for e in os.listdir(tree) if os.path.isdir(os.path.join(tree, e))}
    except OSError as e:
        raise Refused(f"cannot read the tree {tree}: {e.strerror or e}") from None
    return names | set(extra)


def cited(text: str, known: set[str]) -> list[str]:
    """The repository paths a section cites, in order of appearance, once each."""
    found: dict[str, None] = {}
    for m in CANDIDATE.finditer(text):
        raw, end = m.group(1), m.end()
        if text[end:end + 1] in NOT_A_PATH_NEXT or (text[end:end + 1] == "/" and text[end + 1:end + 2] in NOT_A_PATH_NEXT):
            continue                          # a pattern or a placeholder, not a path
        # The run stops at `:` and `#`, so `file.py:12` and `file.py#L3` are `file.py` already;
        # what is left to drop is a sentence's own dots, slashes and commas (`dir/.`).
        path = re.sub(r"[./,;:!?)]+$", "", raw)
        parts = path.split("/")
        lead = 0
        while parts[lead:lead + 1] == [".."]:
            lead += 1
        rest = parts[lead:]
        if len(rest) < 2 and not lead:
            continue
        if lead == 0 and rest[0] not in known:
            continue                          # `HELLO/GOODBYE`, `P1/P2`, `origin/main`: not a directory of the tree
        if ".." in rest or (lead and (lead != 1 or len(rest) < 2)):
            continue                          # only a leading `../NAME/rest` is a path; a `..` inside one is not one we resolve
        found.setdefault(path, None)
    return list(found)


def status(tree: str, path: str) -> str:
    if path.startswith("../"):
        sibling = os.path.normpath(os.path.join(tree, "..", path.split("/")[1]))
        if not os.path.isdir(sibling):
            return "unchecked"                # the sibling checkout is not here: unknown, not stale
    return "exists" if os.path.lexists(os.path.normpath(os.path.join(tree, path))) else "stale-hard"


def verdict_of(paths: list[dict]) -> str:
    states = {p["status"] for p in paths}
    if "stale-hard" in states:
        return "stale-hard"
    if "unchecked" in states:
        return "unchecked"
    return "fresh" if paths else "no-anchor"


def check(corpus: str, tree: str, extra_dirs: list[str] | None = None) -> list[dict]:
    if not os.path.isdir(corpus):
        raise Refused(f"no corpus at {corpus}")
    known = known_dirs(tree, extra_dirs or [])
    rows = []
    for path in slice_files(corpus):
        _, sections = slices.read_existing_slice(path)
        for heading, text in sections.items():
            paths = [{"path": p, "status": status(tree, p)} for p in cited(text, known)]
            rows.append({"slice": os.path.relpath(path, corpus), "heading": heading, "verdict": verdict_of(paths), "paths": paths})
    return rows


def counts(rows: list[dict]) -> dict[str, int]:
    return {v: sum(1 for r in rows if r["verdict"] == v) for v in VERDICTS}


def lines(rows: list[dict], show_all: bool) -> list[str]:
    out = []
    for r in rows:
        for p in r["paths"]:
            if p["status"] in ("stale-hard", "unchecked"):
                out.append("\t".join((p["status"], r["slice"], r["heading"], p["path"])))
        if show_all and r["verdict"] == "fresh":
            out.append("\t".join(("fresh", r["slice"], r["heading"], f"{len(r['paths'])} path(s)")))
        elif show_all and r["verdict"] == "no-anchor":
            out.append("\t".join(("no-anchor", r["slice"], r["heading"])))
    c = counts(rows)
    stale_slices = len({r["slice"] for r in rows if r["verdict"] == "stale-hard"})
    out.append("summary\t" + ", ".join(f"{c[v]} {v}" for v in VERDICTS) + f"; {stale_slices} slice(s) cite a path that is gone")
    return out


def main(argv: list[str]) -> int:
    ap = _Parser(prog="fabric-memory-check", add_help=False)
    ap.add_argument("corpus", nargs="?")
    ap.add_argument("--tree")
    ap.add_argument("--known-dir", action="append", default=[])
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("-h", "--help", action="store_true")
    try:
        a = ap.parse_args(argv)
    except Refused as e:
        print(f"fabric-memory-check: {e}", file=sys.stderr)
        return 2
    if a.help:
        print(__doc__.split("CONTRACT")[0].rstrip())
        return 0
    try:
        corpus = os.path.abspath(a.corpus or roots.memory_dir())
        tree = os.path.abspath(a.tree) if a.tree else tree_of(corpus)
        if tree is None:
            raise Refused(f"{corpus} is not a memory/ directory: name the tree its paths belong to with --tree")
        rows = check(corpus, tree, a.known_dir)
    except Refused as e:
        print(f"fabric-memory-check: {e}", file=sys.stderr)
        return 2
    if a.json:
        print(json.dumps({"corpus": corpus, "tree": tree, "sections": rows, "counts": counts(rows)}, ensure_ascii=False))
    else:
        print("\n".join(lines(rows, a.all)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
