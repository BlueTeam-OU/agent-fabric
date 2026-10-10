#!/usr/bin/env python3
"""tools/fabric/memory_check.py (bin/fabric-memory-check) — does a curated
slice still cite paths that exist? A slice describes a tree as of a date
and loses to the tree (layout.py); this reads each slice section's cited
repository paths and says which are gone, so the slice is corrected where
it lives instead of misleading the next session.

    fabric-memory-check [CORPUS] [--tree DIR] [--project ID] [--known-dir NAME]… [--all] [--json]

CONTRACT
  CORPUS   a corpus root: the fabric's memory/ (default: the operator's, roots.memory_dir())
           or a working copy's .agent-fabric/memory/. The tree its paths are
           checked in is the checkout the corpus belongs to: the parent of
           memory/, or of .agent-fabric/; --tree names it for any other root.
  SLICES   every .md file under the corpus, other than README.md, RUBRIC.md and
           INDEX.md, whose front matter has a non-empty `class` other than
           `index`. A SECTION is a `## ` heading and its text, as
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
  WHOSE     a slice's paths are relative to the project it came from, not
           always to the tree it is kept in (a domain slice of the fabric's
           memory/ records gzapp's or InterWeave's). Its front matter `origin`
           names each project and working_copy: a path is judged by the corpus's
           own tree and by the checkout `../<working_copy>` of every origin
           project that is not the tree's own (`--project` names it; the
           fabric's memory/ is agent-fabric, a .agent-fabric/memory is its working
           copy). A slice with no origin is judged by the corpus's tree.
  VERDICT  per path: `exists` (in the tree or an origin's checkout),
           `stale-hard` (in none of them, and every origin's checkout was here to
           look in), `unchecked` (absent where it was looked, and an origin's
           checkout is not beside the tree, or a `../NAME/…` sibling is not;
           unknown, never stale). Per section: stale-hard if any path is, else
           unchecked if any is, else fresh if it cites a path, else no-anchor. A
           slice or a directory that cannot be read is `unreadable` with the
           reason, and the rest is still reported; a corpus root that cannot be
           read is a refusal.
  stdout   one line per finding, tab-separated:
             stale-hard  <slice>  <heading>  <path>
             unchecked   <slice>  <heading>  <path>  <why>
             unreadable  <slice>  <why>
           (--all adds `fresh  <slice>  <heading>  <n> path(s)` and
           `no-anchor  <slice>  <heading>`), then `summary` and the counts.
           <slice> is relative to CORPUS. --json prints one document instead:
           {"corpus", "tree", "sections": [{"slice", "heading", "verdict",
           "paths": [{"path", "status", "why"?}], "why"?}], "counts": {verdict: n}}.
  stderr   `fabric-memory-check: ` and one line on a refusal.
  exit     0 whatever it found: a report, not a gate; 2 usage or an
           unreadable corpus or tree.

WHAT IT DOES NOT DO  no model, no network, no git (the tree is read as it is
on disk), nothing written. It does not see `path::symbol` anchors, dates, or
a path relative to anything but the tree root; a citation whose first
directory is gone and not named by --known-dir is not seen as a path; and
two `## X` sections of one slice count as one, because
slices.read_existing_slice keys a section by its heading.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)
import layout  # noqa: E402
import roots  # noqa: E402
from assembler import slices  # noqa: E402

# A run of path characters that does not start inside a longer one, a URL
# (after `:`) or an absolute path (after `/`).
CANDIDATE = re.compile(r"(?<![\w./:~@%+-])((?:\./|(?:\.\./)*)\.?[A-Za-z0-9_][A-Za-z0-9_.@+-]*(?:/[A-Za-z0-9_.@+-]+)+/?)")
NOT_A_PATH_NEXT = frozenset("*<>{}$[]|…=")
VERDICTS = ("stale-hard", "unchecked", "fresh", "no-anchor", "unreadable")
NOT_SLICES = frozenset({"README.md", "RUBRIC.md", "INDEX.md"})


class Refused(Exception):
    """One line, exit 2."""


class _Parser(argparse.ArgumentParser):
    def error(self, message: str):         # argparse prints its own usage block and exits; one line is the contract
        raise Refused(f"usage: fabric-memory-check [CORPUS] [--tree DIR] [--project ID] [--known-dir NAME]... [--all] [--json] ({message})")


def tree_of(corpus: str) -> str | None:
    """The checkout a corpus root belongs to, or None when the layout does not say."""
    corpus = os.path.abspath(corpus)
    if os.path.basename(corpus) != "memory":
        return None
    parent = os.path.dirname(corpus)
    return os.path.dirname(parent) if os.path.basename(parent) == ".agent-fabric" else parent


def own_project_of(corpus: str, given: str | None) -> str | None:
    """The project the corpus's own tree is. The fabric's memory/ is agent-fabric's; a
    working copy's .agent-fabric/memory is that working copy's whatever it is called, and
    None says so: every origin of its slices is the tree."""
    if given:
        return given
    corpus = os.path.abspath(corpus)
    return None if os.path.basename(os.path.dirname(corpus)) == ".agent-fabric" else layout.FABRIC_PROJECT_ID


def readable_dir(path: str) -> bool:
    return os.path.isdir(path) and os.access(path, os.R_OK | os.X_OK)


def read_corpus(corpus: str) -> list[dict]:
    """Every slice of the corpus as {path, rel, meta, sections} or, where it could not be
    read, {path, rel, why}: an unreadable directory or file is a row, never silence. A corpus
    root that cannot be read at all is a refusal."""
    try:
        os.listdir(corpus)
    except OSError as e:
        raise Refused(f"cannot read the corpus {corpus}: {e.strerror or e}") from None
    out: list[dict] = []
    stumbles: list[tuple[str, str]] = []
    walk = os.walk(corpus, onerror=lambda e: stumbles.append((e.filename, e.strerror or str(e))))
    for directory, dirs, files in walk:
        dirs.sort()
        for name in sorted(files):
            if not name.endswith(".md") or name in NOT_SLICES:
                continue
            path = os.path.join(directory, name)
            try:
                meta, sections = slices.read_existing_slice(path)
            except (OSError, UnicodeDecodeError) as e:
                out.append({"path": path, "rel": os.path.relpath(path, corpus), "why": f"cannot read it: {getattr(e, 'strerror', None) or e}"})
                continue
            klass = meta.get("class")
            if isinstance(klass, str) and klass and klass != "index":
                out.append({"path": path, "rel": os.path.relpath(path, corpus), "meta": meta, "sections": sections})
    for filename, why in stumbles:
        out.append({"path": filename, "rel": os.path.relpath(filename, corpus), "why": f"cannot read the directory: {why}"})
    return sorted(out, key=lambda s: s["rel"])


def known_dirs(tree: str) -> set[str]:
    try:
        return {e for e in os.listdir(tree) if os.path.isdir(os.path.join(tree, e))}
    except OSError as e:
        raise Refused(f"cannot read the tree {tree}: {e.strerror or e}") from None


def origin_trees(meta: dict, tree: str, own_project: str | None) -> tuple[list[str], list[str]]:
    """(the trees this slice's paths may belong to that are here, why each other is not).
    A slice says where it came from (front matter `origin`: project and working_copy):
    the tree's own project's paths are the tree's, another project's are in the checkout
    beside the tree that working_copy names, if there is one. No origin: the tree."""
    origins = [o for o in (meta.get("origin") or []) if isinstance(o, dict)]
    if not origins:
        return [tree], []
    here: list[str] = []
    missing: list[str] = []
    for o in origins:
        project, wc = o.get("project"), o.get("working_copy")
        if own_project is None or project is None or project == own_project:
            found = tree
        else:
            found = None
            if isinstance(wc, str) and wc and "/" not in wc and wc not in (".", ".."):
                beside = os.path.normpath(os.path.join(tree, "..", wc))
                found = beside if readable_dir(beside) else None
            if found is None:
                missing.append(f"origin {project}: no checkout {wc!r} beside the tree")
                continue
        if found not in here:
            here.append(found)
    return here, sorted(set(missing))


def cited(text: str, known: set[str]) -> list[str]:
    """The repository paths a section cites, in order of appearance, once each."""
    found: dict[str, None] = {}
    for m in CANDIDATE.finditer(text):
        raw, end = m.group(1), m.end()
        if text[end:end + 1] in NOT_A_PATH_NEXT or (text[end:end + 1] == "/" and text[end + 1:end + 2] in NOT_A_PATH_NEXT):
            continue                          # a pattern or a placeholder, not a path
        # The run stops at `:` and `#`, so `file.py:12` and `file.py#L3` are `file.py` already;
        # what is left to drop is a sentence's own dots, slashes, commas and dashes (`dir/.`).
        path = re.sub(r"[./,;:!?)-]+$", "", raw.removeprefix("./"))
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


def status(path: str, tree: str, trees: list[str], missing: list[str]) -> tuple[str, str | None]:
    """(status, why-unchecked) of one cited path."""
    if path.startswith("../"):                # a sibling checkout of the corpus's tree, by name
        beside = os.path.normpath(os.path.join(tree, "..", path.split("/")[1]))
        if not readable_dir(beside):
            return "unchecked", f"no checkout {path.split('/')[1]!r} beside the tree"
        return ("exists" if os.path.lexists(os.path.normpath(os.path.join(tree, path))) else "stale-hard"), None
    if any(os.path.lexists(os.path.normpath(os.path.join(t, path))) for t in [tree, *trees]):
        return "exists", None                 # it is there, in the corpus's tree or in an origin's
    if missing:
        return "unchecked", "; ".join(missing)
    return "stale-hard", None


def verdict_of(paths: list[dict]) -> str:
    states = {p["status"] for p in paths}
    if "stale-hard" in states:
        return "stale-hard"
    if "unchecked" in states:
        return "unchecked"
    return "fresh" if paths else "no-anchor"


def check(corpus: str, tree: str, extra_dirs: list[str] | None = None, project: str | None = None) -> list[dict]:
    if not os.path.isdir(corpus):
        raise Refused(f"no corpus at {corpus}")
    own = own_project_of(corpus, project)
    rows = []
    tops: dict[str, set[str]] = {tree: known_dirs(tree)}      # a tree that cannot be read is a refusal, slices or none
    for sl in read_corpus(corpus):
        if "why" in sl:
            rows.append({"slice": sl["rel"], "heading": "", "verdict": "unreadable", "paths": [], "why": sl["why"]})
            continue
        trees, missing = origin_trees(sl["meta"], tree, own)
        # What is a path is what any tree the slice may belong to has at its top level.
        known = set(extra_dirs or [])
        for t in {tree, *trees}:
            known |= tops.setdefault(t, known_dirs(t))
        for heading, text in sl["sections"].items():
            paths = []
            for p in cited(text, known):
                state, why = status(p, tree, trees, missing)
                paths.append({"path": p, "status": state, **({"why": why} if why else {})})
            rows.append({"slice": sl["rel"], "heading": heading, "verdict": verdict_of(paths), "paths": paths})
    return rows


def counts(rows: list[dict]) -> dict[str, int]:
    return {v: sum(1 for r in rows if r["verdict"] == v) for v in VERDICTS}


def lines(rows: list[dict], show_all: bool) -> list[str]:
    out = []
    for r in rows:
        if r["verdict"] == "unreadable":
            out.append("\t".join(("unreadable", r["slice"], r["why"])))
        for p in r["paths"]:
            if p["status"] == "stale-hard":
                out.append("\t".join((p["status"], r["slice"], r["heading"], p["path"])))
            elif p["status"] == "unchecked":
                out.append("\t".join((p["status"], r["slice"], r["heading"], p["path"], p["why"])))
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
    ap.add_argument("--project")
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
        rows = check(corpus, tree, a.known_dir, a.project)
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
