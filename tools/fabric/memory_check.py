#!/usr/bin/env python3
"""tools/fabric/memory_check.py (bin/fabric-memory-check) — is a curated
slice section still true of its tree? A slice describes a tree as of a date
and loses to the tree (layout.py); this reads each section's anchors and
cited repository paths and says which are gone or have changed since the
section was observed, so the section is corrected where it lives instead of
misleading the next session (ADR-050 rule 2). It judges nothing: it sorts.

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
           memory/ records another project's). Its front matter `origin`
           names each project and working_copy: a path is judged by the corpus's
           own tree and by the checkout `../<working_copy>` of every origin
           project that is not the tree's own (`--project` names it; the
           fabric's memory/ is agent-fabric, a .agent-fabric/memory is its working
           copy). A slice with no origin is judged by the corpus's tree.
  ANCHORS  a section's `*Anchors: `<path>::<symbol or literal>`, …*` line (written by
           the assembler from the memory's `anchors:`, ADR-050 rule 1): the path must
           exist, and when `::` follows, the file must contain that string (a symbol
           name or a literal, matched as plain text). The path is looked for as a cited
           path is, in the tree and in each origin's checkout. OBSERVED is the date in
           the section's `*Observed YYYY-MM-DD (role)*` tail.
  VERDICT  per path: `exists` (in the tree or an origin's checkout), `stale-hard`
           (in none of them, and every origin's checkout was here to look in),
           `unchecked` (absent where it was looked, and an origin's checkout is not
           beside the tree, or a `../NAME/…` sibling is not; unknown, never stale).
           Per anchor, the same, and also `stale-hard` when its file lacks the symbol
           or literal, and `maybe-stale` when its file has a commit after OBSERVED's
           day (git, in the checkout the file is in; the finding names the newest such
           commit). Per section, in this order: stale-hard if any path or anchor is;
           else maybe-stale if any anchor is; else unchecked if any path or anchor is,
           or the section has anchors and no OBSERVED date to judge a change by, or the
           git history is shallow or missing; else fresh if it cites a path or has an
           anchor; else no-anchor. Only stale-hard and maybe-stale are flags (ADR-050
           rule 2). A slice or a directory that cannot be read is `unreadable` with the
           reason, and the rest is still reported; a corpus root that cannot be read is
           a refusal.
  stdout   one line per finding, tab-separated:
             stale-hard  <slice>  <heading>  <path>
             stale-hard  <slice>  <heading>  <path>::<symbol>  <why>
             maybe-stale <slice>  <heading>  <anchor>  <commit> <date> <subject>
             unchecked   <slice>  <heading>  <path or anchor>  <why>
             unreadable  <slice>  <why>
           (--all adds `fresh  <slice>  <heading>  <n> path(s)` and
           `no-anchor  <slice>  <heading>`), then `summary` and the counts.
           <slice> is relative to CORPUS. --json prints one document instead:
           {"corpus", "tree", "sections": [{"slice", "heading", "verdict", "role"?,
           "observed"?, "paths": [{"path", "status", "why"?}], "anchors": [{"anchor",
           "path", "status", "why"?, "commit"?, "date"?, "subject"?}], "why"?}],
           "counts": {verdict: n}}.
  stderr   `fabric-memory-check: ` and one line on a refusal.
  exit     0 whatever it found: a report, not a gate; 2 usage or an
           unreadable corpus or tree.

WHAT IT DOES NOT DO  no model, no network, nothing written; git is only read (log and
rev-parse, an argument list, a timeout, a minimal environment). It does not
judge a changed file: maybe-stale says the file moved since the section was
written, and the section's holder says whether the section still holds; the
day is the grain (a change on OBSERVED's own day is not seen). It does not see
a path relative to anything but the tree root; a citation whose first
directory is gone and not named by --known-dir is not seen as a path; and
two `## X` sections of one slice count as one, because
slices.read_existing_slice keys a section by its heading; and a path of an
origin whose checkout is not here, with a first directory this tree lacks,
is not recognised as a path at all (a word pair like `a/b` could be anything).
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import subprocess
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
VERDICTS = ("stale-hard", "maybe-stale", "unchecked", "fresh", "no-anchor", "unreadable")
FLAGS = ("stale-hard", "maybe-stale")
NOT_SLICES = frozenset({"README.md", "RUBRIC.md", "INDEX.md"})
ANCHOR_FILE_MAX = 4 * 1024 * 1024         # a file larger than this is not searched for a symbol: unchecked, not stale
GIT_TIMEOUT_S = 30


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
                os.stat(path)                 # a dangling link: read_existing_slice would call it an empty slice
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
                missing.append(f"origin {project}: no checkout {wc!r} beside the tree" if isinstance(wc, str) and wc
                               else f"origin {project}: names no working_copy to look in")
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


class NoHistory(Exception):
    """The git history that would answer cannot be read here: unknown, never stale. `why` is one line."""

    def __init__(self, why: str):
        super().__init__(why)
        self.why = why


class History:
    """What git says of a tree, read-only and asked once. A subprocess has an argument list, a timeout and
    a minimal environment (no GIT_DIR of the caller's, no pager, no system or user config); `run` is
    subprocess.run's own signature so a test can hand in a fake of it."""

    def __init__(self, run=subprocess.run):
        self.run = run
        self._ready: dict[str, str | None] = {}

    def _git(self, tree: str, *args: str) -> subprocess.CompletedProcess:
        env = {"PATH": os.environ.get("PATH") or "/usr/bin:/bin", "LC_ALL": "C", "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
               "GIT_TERMINAL_PROMPT": "0", "GIT_PAGER": "cat"}
        try:
            return self.run(["git", "-C", tree, *args], capture_output=True, text=True, timeout=GIT_TIMEOUT_S, env=env, check=False,
                            stdin=subprocess.DEVNULL, errors="replace")
        except FileNotFoundError:
            raise NoHistory("git is not installed") from None
        except subprocess.TimeoutExpired:
            raise NoHistory(f"git did not answer within {GIT_TIMEOUT_S} s") from None
        except OSError as e:
            raise NoHistory(f"git could not run ({e.strerror or e})") from None

    def ready(self, tree: str) -> None:
        """Raises NoHistory unless `tree` is a repository whose history is whole."""
        if tree not in self._ready:
            r = self._git(tree, "rev-parse", "--is-shallow-repository")
            if r.returncode != 0:
                self._ready[tree] = "no git history: " + ((r.stderr or "").strip().split("\n")[0][:120] or f"git exited {r.returncode}")
            elif r.stdout.strip() != "false":
                self._ready[tree] = "the git history is shallow: a change since the section was written may be missing from it"
            else:
                self._ready[tree] = None
        if self._ready[tree]:
            raise NoHistory(self._ready[tree])

    def changed_after(self, tree: str, path: str, day: str) -> dict | None:
        """The newest commit that touched `path` after the end of `day` (YYYY-MM-DD, UTC), or None."""
        self.ready(tree)
        end = datetime.datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=datetime.timezone.utc) + datetime.timedelta(days=1)
        r = self._git(tree, "log", "-1", "--format=%h%x09%cs%x09%s", f"--since={int(end.timestamp())} +0000", "--", path)
        if r.returncode != 0:
            raise NoHistory("git log failed: " + ((r.stderr or "").strip().split("\n")[0][:120] or f"exit {r.returncode}"))
        line = r.stdout.strip().split("\n")[0]
        if not line:
            return None
        commit, _, rest = line.partition("\t")
        date, _, subject = rest.partition("\t")
        return {"commit": commit, "date": date, "subject": subject[:100]}


def _in_tree(root: str, path: str) -> str:
    """"ok", "absent" or "escape": whether `path` exists under `root` and, once links are followed, stays inside it.
    An anchor is text from a slice; what it names is opened only inside the tree it belongs to."""
    full = os.path.normpath(os.path.join(root, path))
    if not os.path.lexists(full):
        return "absent"
    real, top = os.path.realpath(full), os.path.realpath(root)
    return "ok" if real == top or real.startswith(top + os.sep) else "escape"


def judge_anchor(anchor: str, trees: list[str], missing: list[str], observed: str | None, history: History) -> dict:
    """One anchor `<path>[::<symbol or literal>]` of a section, sorted: stale-hard when its path or its string is
    gone, maybe-stale when its file has a commit after the section's Observed day, unchecked when that cannot be
    looked at, exists otherwise. It is judged where the slice's origin says it lives, in `trees` (the checkouts the
    slice's origin names, the corpus's own tree when it names none): a file of the same name in another project's
    tree says nothing, and a checkout that is not here makes what it would have held unknown, never gone."""
    path, _, symbol = anchor.partition("::")
    row: dict = {"anchor": anchor, "path": path}
    found = {t: _in_tree(t, path) for t in trees}
    present = [t for t in trees if found[t] == "ok"]
    if not present:
        if any(v == "escape" for v in found.values()):
            return {**row, "status": "unchecked", "why": "the path leaves its tree through a link"}
        if missing:
            return {**row, "status": "unchecked", "why": "; ".join(missing)}
        return {**row, "status": "stale-hard", "why": "the path is gone"}
    where = present[0]
    if symbol:
        unknown: list[str] = []
        holders: list[str] = []
        for t in present:
            full = os.path.normpath(os.path.join(t, path))
            if not os.path.isfile(full):
                continue
            try:
                with open(full, "rb") as fh:
                    data = fh.read(ANCHOR_FILE_MAX + 1)
            except OSError as e:
                unknown.append(f"cannot read the file: {e.strerror or e}")
                continue
            if len(data) > ANCHOR_FILE_MAX:
                unknown.append(f"the file is larger than {ANCHOR_FILE_MAX} bytes")
            elif symbol in data.decode("utf-8", errors="replace"):
                holders.append(t)
        if holders:
            where = holders[0]
        elif unknown:
            return {**row, "status": "unchecked", "why": unknown[0]}
        elif missing:
            return {**row, "status": "unchecked", "why": "the file lacks it here, and " + "; ".join(missing)}
        elif not any(os.path.isfile(os.path.normpath(os.path.join(t, path))) for t in present):
            return {**row, "status": "stale-hard", "why": "the path is not a file, so it holds no symbol"}
        else:
            return {**row, "status": "stale-hard", "why": f"the file no longer holds {symbol!r}"}
    if observed is None:
        return {**row, "status": "exists"}
    try:
        changed = history.changed_after(where, path, observed)
    except NoHistory as e:
        return {**row, "status": "unchecked", "why": e.why}
    return {**row, "status": "maybe-stale", **changed} if changed else {**row, "status": "exists"}


def verdict_of(paths: list[dict], anchors: list[dict] | None = None, observed: str | None = None) -> str:
    anchors = anchors or []
    states = {p["status"] for p in paths} | {a["status"] for a in anchors}
    if "stale-hard" in states:
        return "stale-hard"
    if "maybe-stale" in states:
        return "maybe-stale"
    if "unchecked" in states or (anchors and observed is None):
        return "unchecked"                  # a change since the section was written cannot be judged without its date
    return "fresh" if paths or anchors else "no-anchor"


def check(corpus: str, tree: str, extra_dirs: list[str] | None = None, project: str | None = None,
          history: History | None = None) -> list[dict]:
    if not os.path.isdir(corpus):
        raise Refused(f"no corpus at {corpus}")
    history = history or History()
    own = own_project_of(corpus, project)
    rows = []
    tops: dict[str, set[str]] = {tree: known_dirs(tree)}      # a tree that cannot be read is a refusal, slices or none
    for sl in read_corpus(corpus):
        if "why" in sl:
            rows.append({"slice": sl["rel"], "heading": "", "verdict": "unreadable", "paths": [], "why": sl["why"]})
            continue
        trees, missing = origin_trees(sl["meta"], tree, own)
        usable = []
        for t_ in trees:
            if t_ not in tops:
                try:
                    tops[t_] = known_dirs(t_)
                except Refused:
                    tops[t_] = None           # found by readable_dir, then not listable (a race, an ACL): unknown
            if tops[t_] is None:
                missing = [*missing, f"origin checkout {os.path.basename(t_)!r}: cannot read it"]
            else:
                usable.append(t_)
        trees = usable
        # What is a path is what any tree the slice may belong to has at its top level.
        known = set(extra_dirs or []).union(tops[tree], *(tops[t_] for t_ in trees))
        for heading, text in sl["sections"].items():
            paths = []
            for p in cited(text, known):
                state, why = status(p, tree, trees, missing)
                paths.append({"path": p, "status": state, **({"why": why} if why else {})})
            observed, role = observed_of(text)
            anchors = [judge_anchor(a, trees, missing, observed, history) for a in slices.anchors_of(text)]
            row = {"slice": sl["rel"], "heading": heading, "verdict": verdict_of(paths, anchors, observed), "paths": paths, "anchors": anchors,
                   **({"observed": observed} if observed else {}), **({"role": role} if role else {})}
            if anchors and observed is None and row["verdict"] == "unchecked" and not any(a["status"] == "unchecked" for a in anchors):
                row["why"] = "the section has anchors and no Observed date, so a change since it was written cannot be judged"
            rows.append(row)
    return rows


def observed_of(text: str) -> tuple[str | None, str | None]:
    """(date, role) of a section's `*Observed YYYY-MM-DD (role)*` tail, either None when absent."""
    m = slices.OBSERVED_RE.search(text)
    return (m.group(1), m.group(2)) if m else (None, None)


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
        for a in r.get("anchors", []):
            if a["status"] == "stale-hard":
                out.append("\t".join((a["status"], r["slice"], r["heading"], a["anchor"], a["why"])) if "why" in a
                           else "\t".join((a["status"], r["slice"], r["heading"], a["anchor"])))
            elif a["status"] == "maybe-stale":
                out.append("\t".join((a["status"], r["slice"], r["heading"], a["anchor"], f"{a['commit']} {a['date']} {a['subject']}")))
            elif a["status"] == "unchecked":
                out.append("\t".join((a["status"], r["slice"], r["heading"], a["anchor"], a["why"])))
        if r["verdict"] == "unchecked" and r.get("why"):
            out.append("\t".join(("unchecked", r["slice"], r["heading"], "-", r["why"])))
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
