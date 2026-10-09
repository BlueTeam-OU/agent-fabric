#!/usr/bin/env python3
"""tools/fabric/query.py — ask the corpus what it knows about an artifact
(ADR-040 Wave 3; `fabric-query` runs it: `fabric-query adr|pr|commit|file <key>`,
`fabric-query obs <hash>`, `fabric-query roles`).

CONTRACT (ADR-040 §5 rule 3):
  argv    adr|arch|pr|commit|contract|error|migration|file <key> (each also
          plural; error also error_codes), obs <hash>, roles, or nothing,
          "", -h, --help, help for the help. What follows the key, the hash
          or `roles` is ignored. `pr` puts a # before a key without one.
          `migration` takes the key as typed: the match is a case-insensitive
          substring, so the `0007` of the help finds `migration-0007`.
  env     AGENT_FABRIC_OPERATOR (default: AGENT_FABRIC_ROOT, else this
          repository; the corpus is <operator>/memory), AGENT_FABRIC_WORKING_COPY, _WORKING_COPIES
          (colon-separated), AGENT_FABRIC_STATE_DIR (default
          ${XDG_STATE_HOME:-$HOME/.local/state}/agent-fabric/agents/<login>,
          whose binding.json names one more working copy); the locale orders
          roots and files.
  stdout  the help; per crossref with hits a blank line, `project/role`,
          then per artifact `  <name, padded to 44 characters> N obs` and
          `      slices: a, b` (`none` when empty); the roles table; the obs
          report; or a one-line "nothing" answer.
  stderr  a refusal `query: …`; a crossref that cannot be used, one line
          naming the file and the reason; a binding that cannot be read.
  exit    0 answered or help; 2 refusal (no corpus, unknown kind, artifact
          or hash missing, a crossref that cannot be opened); 5 a crossref
          that is not JSON (several documents in one file included) or not
          the shape the assembler writes, what the earlier roots printed
          staying printed; 141 stdout closed early.
  help    HELP, byte for byte. The corpus is checked first, so even the help
          refuses when there is none.

A crossref is {"index": {kind: {value: {"observations": [...], "slices":
[...]}}}} (assemble.py), integers only, so no number is formatted here.

Decided against the bash this replaces (it needed jq): an empty slice list
prints `none` and its real count (the bash's `IFS=$'\\t' read` collapsed the
tabs); widths are characters, the output is read by people; the hash of
`obs` is searched as a fixed string, being hex; jq's wording is not kept.
Kept: only ASCII letters fold (jq's ascii_downcase), and a symlinked
directory is not searched into (find did not).
"""
from __future__ import annotations

import json
import locale
import os
import pwd
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import roots  # noqa: E402

HELP = """\
Ask the corpus what it knows about an artifact.

  fabric-query adr ADR-054       # who learned from it, where it landed
  fabric-query pr 428
  fabric-query migration 0007
  fabric-query file apps/status_web
  fabric-query obs <content-hash>
  fabric-query roles             # what roles exist, per project, and how big they are

The citation graph is small — thousands of edges — so it lives in the
committed JSON the assembler writes (<working copy>/.agent-fabric/memory/
<role>/crossref.json in each project's repository; memory/projects/
<project>/ here while a project has not moved), and jq answers everything
in milliseconds. Which working copies are searched: this checkout (for
agent-fabric itself), $AGENT_FABRIC_WORKING_COPY, the working copy the
agent's binding names, and every entry of $AGENT_FABRIC_WORKING_COPIES
(colon-separated). A database
would buy nothing here and would cost the one property that matters
most: the graph is reviewable in a pull request, because it is a diff
like everything else.

If multi-hop queries ever become routine, the next step is a generated
SQLite edge cache rebuilt from these files — derived, never authoritative.
Git stays the source of truth.
"""

KINDS = {
    "adr": "adrs", "arch": "archs", "pr": "prs", "commit": "commits",
    "contract": "contracts", "error": "error_codes",
    "migration": "migrations", "file": "files",
}
KINDS.update({k + "s": v for k, v in list(KINDS.items())})
KINDS["error_codes"] = "error_codes"
del KINDS["errors"]

ASCII_FOLD = {c: c + 32 for c in range(ord("A"), ord("Z") + 1)}


class Failure(Exception):
    def __init__(self, msg: str, code: int = 2):
        super().__init__(msg)
        self.code = code


def sort_u(items: list[str]) -> list[str]:
    """`sort -u`: the locale's order, one of each."""
    out: dict[str, str] = {}
    for s in sorted(set(items), key=locale.strxfrm):
        out.setdefault(locale.strxfrm(s), s)
    return list(out.values())


def say(msg: str) -> None:
    # stdout first, so a caller that merges the streams sees program order
    sys.stdout.flush()
    sys.stderr.write(msg + "\n")
    sys.stderr.flush()


# ── reading ─────────────────────────────────────────────────────────────

def load(path: str) -> object:
    try:
        with open(path, "rb") as fh:
            raw = fh.read()
    except OSError as e:
        raise Failure(f"query: cannot read {path}: {e.strerror}", 2) from None
    try:
        return json.loads(raw)
    except ValueError as e:  # includes "Extra data": one document per file
        raise Failure(f"query: {path} is not JSON: {e}", 5) from None


def shape(path: str, what: str) -> Failure:
    return Failure(f"query: {path} is not a crossref: {what}", 5)


def items(v: object, path: str, what: str) -> list[tuple[object, object]]:
    if isinstance(v, dict):
        return list(v.items())
    if isinstance(v, list):
        return list(enumerate(v))
    raise shape(path, what)


def index_of(doc: object, path: str) -> object:
    if not isinstance(doc, dict):
        raise shape(path, "the top level is not an object")
    return doc.get("index")


def size(v: object, path: str) -> int:
    if v is None:
        return 0
    if isinstance(v, (str, list, dict)):
        return len(v)
    raise shape(path, "a kind that is neither a list nor an object")


def listed(ent: dict, field: str, path: str) -> list:
    v = ent.get(field)
    if v is None:
        return []
    if not isinstance(v, list):
        raise shape(path, f"{field} is not a list")
    return v


def lookup_hits(path: str, key: str, needle: str) -> list[tuple[str, str, int]]:
    index = index_of(load(path), path)
    if index is None:
        return []
    if not isinstance(index, dict):
        raise shape(path, "index is not an object")
    section = index.get(key) or {}
    if not isinstance(section, dict):
        raise shape(path, f"{key} is not an object")
    want = needle.translate(ASCII_FOLD)
    hits = []
    for name, ent in section.items():
        if want not in name.translate(ASCII_FOLD):
            continue
        if not isinstance(ent, dict):
            raise shape(path, f"{name} is not an object")
        slices = listed(ent, "slices", path)
        if not all(isinstance(s, str) for s in slices):
            raise shape(path, f"{name}: slices are not strings")
        hits.append((name, ", ".join(slices), len(listed(ent, "observations", path))))
    return hits


def obs_hits(path: str, h: str) -> list[tuple[str, str]]:
    index = index_of(load(path), path)
    hits = []
    for kind, section in items(index, path, "index is missing or not an object"):
        for name, ent in items(section, path, f"{kind} is not an object"):
            if not isinstance(ent, dict):
                raise shape(path, f"{name} is not an object")
            if h in listed(ent, "observations", path):
                hits.append((str(kind), str(name)))
    return hits


def citations(path: str) -> int:
    index = index_of(load(path), path)
    if isinstance(index, dict):
        index = list(index.values())
    return sum(size(v, path) for v in index) if isinstance(index, list) else 0


# ── where the crossrefs are ─────────────────────────────────────────────

def binding_working_copy(state: str) -> list[str]:
    path = f"{state}/binding.json"
    if not os.path.isfile(path):
        return []
    try:
        with open(path, "rb") as fh:
            wc = json.load(fh).get("working_copy")
    except (OSError, ValueError, AttributeError) as e:
        say(f"query: the binding {path} is not read: {e}")
        return []
    return [wc] if isinstance(wc, str) else []


def subdirs(path: str) -> list[str]:
    """find <path> -mindepth 1 -maxdepth 1 -type d: a symlink is not followed."""
    try:
        with os.scandir(path) as it:
            return [e.path for e in it if e.is_dir(follow_symlinks=False)]
    except OSError:
        return []


def project_roots(root: str, memory: str) -> list[str]:
    """The project-memory roots this run can see: legacy memory/projects/<id>/
    here, and .agent-fabric/memory/ in every working copy we know of."""
    env = os.environ
    wcs = [root, env.get("AGENT_FABRIC_WORKING_COPY", "")]
    wcs += env.get("AGENT_FABRIC_WORKING_COPIES", "").split(":")
    state = env.get("AGENT_FABRIC_STATE_DIR")
    if not state:
        base = env.get("XDG_STATE_HOME") or (f"{env['HOME']}/.local/state" if env.get("HOME") else "")
        if base:
            state = f"{base}/agent-fabric/agents/{pwd.getpwuid(os.geteuid()).pw_name}"
        else:
            say("query: HOME is not set, so the binding is not read")
    if state:
        wcs += binding_working_copy(state)
    found = subdirs(f"{memory}/projects")
    found += [f"{wc}/.agent-fabric/memory" for wc in sort_u([w for w in wcs if w.strip(" \t")])
              if os.path.isdir(f"{wc}/.agent-fabric/memory")]
    return found


def crossrefs(root: str, memory: str) -> list[str]:
    """<project memory root>/<role>/crossref.json"""
    found = [f"{d}/crossref.json" for r in project_roots(root, memory) for d in subdirs(r)
             if os.path.lexists(f"{d}/crossref.json")]
    return sort_u(found)


def label_of(f: str) -> str:
    """project/role: the legacy dir is named for the project; a working copy's
    .agent-fabric/memory/ is labelled by the working copy's basename."""
    d = os.path.dirname(f)
    p = os.path.dirname(d)
    if p.endswith("/.agent-fabric/memory"):
        p = os.path.dirname(os.path.dirname(p))
    return f"{os.path.basename(p)}/{os.path.basename(d)}"


def walk_md(top: str):
    """The .md files under top, symlinks (files and directories) not followed."""
    for dp, _, fns in os.walk(top):
        for fn in fns:
            p = f"{dp}/{fn}"
            if fn.endswith(".md") and not os.path.islink(p):
                yield p


def count_md(top: str) -> int:
    """Every entry named *.md but INDEX.md under top, as `find -name '*.md'
    ! -name INDEX.md` counted them: a symlinked slice is a slice, and so is a
    directory named so; links are not followed into (review of #73). The
    evidence search, walk_md, keeps to real files."""
    # find does not follow its starting point either (no -H): a domain
    # directory that is a link counts nothing (re-review of #73).
    if os.path.islink(top):
        return 0
    n = 0
    for _dp, dns, fns in os.walk(top):
        n += sum(1 for name in dns + fns if name.endswith(".md") and name != "INDEX.md")
    return n


# ── the commands ────────────────────────────────────────────────────────

def cmd_roles(root: str, memory: str) -> None:
    print(f"{'project/role':<28} {'project':<8} {'domain':<8} citations")
    for f in crossrefs(root, memory):
        role = os.path.basename(os.path.dirname(f))
        proj = count_md(os.path.dirname(f))
        dom = count_md(f"{memory}/domains/{role}")
        print(f"{label_of(f):<28} {proj:<8} {dom:<8} {citations(f)}")


def cmd_lookup(root: str, memory: str, key: str, needle: str) -> None:
    found = False
    for f in crossrefs(root, memory):
        hits = lookup_hits(f, key, needle)
        if not hits:
            continue
        found = True
        print(f"\n{label_of(f)}")
        for name, slices, n in hits:
            print(f"  {name:<44} {n} obs\n      slices: {slices or 'none'}")
    if not found:
        print(f"nothing in the corpus cites {needle}")


def cmd_obs(root: str, memory: str, h: str) -> None:
    found = False
    for f in crossrefs(root, memory):
        hits = obs_hits(f, h)
        if not hits:
            continue
        found = True
        print(f"\n{label_of(f)} cites:")
        for kind, name in hits:
            print(f"  {kind:<12} {name}")
    # Provenance runs the other way too: which slices were built from this row.
    want = os.fsencode(h)
    seen = []
    for top in [memory, *project_roots(root, memory)]:
        for p in walk_md(top):
            try:
                with open(p, "rb") as fh:
                    if want in fh.read():
                        # the corpus is the operator's: label it memory/..., whichever root it is under
                        seen.append(p.removeprefix(f"{os.path.dirname(memory)}/" if p.startswith(f"{memory}/") else f"{root}/"))
            except OSError as e:
                say(f"query: cannot read {p}: {e.strerror}")
    if seen:
        found = True
        print("\nevidence for:")
        for p in sort_u(seen):
            print(f"  {p}")
    if not found:
        print(f"observation {h} is not referenced in the corpus")


def run(argv: list[str]) -> None:
    root = roots.engine_root()
    memory = roots.memory_dir()
    if not os.path.isdir(memory):
        raise Failure(f"query: no corpus at {memory}")
    cmd = argv[0] if argv else ""
    if cmd in ("", "-h", "--help", "help"):
        sys.stdout.write(HELP)
    elif cmd == "roles":
        cmd_roles(root, memory)
    elif cmd == "obs":
        if len(argv) < 2:
            raise Failure("query: obs needs a content hash")
        cmd_obs(root, memory, argv[1])
    else:
        if len(argv) < 2:
            raise Failure("query: need an artifact, e.g. 'adr ADR-054'")
        if cmd not in KINDS:
            raise Failure(f"query: unknown artifact kind '{cmd}' (adr arch pr commit contract error migration file)")
        needle = argv[1]
        if KINDS[cmd] == "prs" and not needle.startswith("#"):
            needle = f"#{needle}"
        cmd_lookup(root, memory, KINDS[cmd], needle)


def main() -> int:
    # SIGPIPE stays ignored, as Python leaves it: a closed stdout raises
    # BrokenPipeError and ends the run through the handler below.
    try:
        locale.setlocale(locale.LC_COLLATE, "")
    except locale.Error:
        pass
    for s in (sys.stdout, sys.stderr):
        s.reconfigure(encoding="utf-8", errors="surrogateescape")
    try:
        try:
            run([os.fsdecode(a) for a in sys.argv[1:]])
        except Failure as e:
            say(str(e))
            return e.code
        sys.stdout.flush()
        return 0
    except BrokenPipeError:
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        return 141


if __name__ == "__main__":
    sys.exit(main())
