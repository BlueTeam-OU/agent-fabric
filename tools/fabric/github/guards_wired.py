#!/usr/bin/env python3
"""runtime/github/check-guards-are-wired.sh [--root <dir>]

Prove every guard is REACHABLE — run by a workflow, and paired with a
self-test that a workflow runs too.

Why this exists: a guard that runs nowhere passes silently-green
forever. A check written, tested by hand and committed proves the
script works; it says nothing about whether anything will ever call it.
Verifying the artifact is not verifying its reachability.

What is checked, for each directory the project's guards.json names:
  1. a guard (or ci) member is run by some .github/workflows/*.yml; a
     script member — a helper a person runs — need not be;
  2. every member has a self-test beside it, test_<stem>.<ext>, unless
     the exemption list names it;
  3. every test_* in those directories, and every other test_*.sh in
     the tree, is run by some workflow;
  4. every workflow command that runs a bash self-test of those
     directories runs it through the project's runner (run_suite.sh):
     run bare, a suite whose assertion calls an undefined helper
     passes. A bare run is not excused by a wrapped one elsewhere, nor
     on the same line; a for-loop over self-tests must hand its loop
     variable to the runner before its done.

What counts as RUN: a path in the text a workflow executes — a run:
value, one line or a block — as any argument, directly or through a
wrapper, or matched by a glob there (tools/gh/test_*.sh). A name in a
comment, a commented-out command, a `name:` label or an echo does not,
nor does one behind a command this cannot read with certainty (a
prefix's option: `env -u X …`): unknown is reported, never passed.
With package_scripts, a `pnpm --filter <pkg> <script>` a workflow runs
reaches that package script's body, one hop, the filter resolved through
a for-loop over a matrix.

NOT checked here: whether the paths a guard protects trigger the job
that runs it. "Runs at all" and "runs on the right changes" are
different failures with different fixes.

  --root <dir>   the repository to check (default: the working
                 directory's toplevel)
  -h, --help     this text

The project's rules: projects/<id>/integration/gh/guards.json in
agent-fabric, for the project --root's working copy belongs to, or the
file AGENT_FABRIC_GUARDS_CONFIG names.

Exit codes:
  0  every guard is wired and self-tested (or explicitly exempt)
  1  a guard or self-test is unreachable or untested, or a self-test is
     run without the runner
  2  invocation problem (no workflows directory, no exemption list, a
     workflow or package script that cannot be read, no config)
"""
# The docstring is --help, whole. Ported from two managed projects'
# tools/checks/check_guards_are_wired.sh (ADR-040; both suites, run
# unchanged against the shim, the oracle): one copy's reading of what a
# workflow runs, the other's directory roles and globs, each project's
# report in its own form and wording.
#
# THE CONTRACT, frozen from devex-tooling's port contract 8/8 and its
# rulings of 2026-10-08:
#   argv    [--root <dir>] [-h|--help], cli_root's refusals, exit 2.
#   config  {dirs: [{dir, role guard|ci|script, members regex, names
#           path|basename}], exempt_file, exempt_required (default true),
#           exempt_excuses_wiring, runner,
#           package_scripts null|"pnpm", tree_excludes, report
#           "grouped"|"lines", text: the report's lines}.
#   stdout  the report; the OK line.
#   stderr  "check_guards_are_wired: <why>", exit 2; the lines form's
#           summary.
#   exit    0, 1, 2 as --help says.
# PINNED LIMIT (devex-tooling, 2026-10-08): the runner rule covers the
# configured directories only, as both copies did; the whole-tree rule
# checks wiring alone. A bash self-test elsewhere run bare passes here.
# Widening it waits on the projects' own bare suites being wired first.
from __future__ import annotations

import json
import os
import re
import shlex
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from github.cli_root import Refused, parse_root, project_config, toplevel  # noqa: E402

PROG = "check_guards_are_wired"
SETTING = "AGENT_FABRIC_GUARDS_CONFIG"
WORKFLOWS = os.path.join(".github", "workflows")
ROLES = ("guard", "ci", "script")
GLOB_CHARS = re.compile(r"[*?\[]")


# ── the project's rules ──────────────────────────────────────────────

def load_config(path: str, root: str) -> dict:
    if not path:
        raise Refused(f"no guards config for {root} (projects/<id>/integration/gh/guards.json in agent-fabric,"
                      f" or {SETTING})")
    try:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
        dirs = [{"dir": d["dir"].rstrip("/"), "role": d["role"], "members": re.compile(d["members"]),
                 "names": d.get("names", "path")} for d in doc["dirs"]]
        for d in dirs:
            if d["role"] not in ROLES:
                raise ValueError(f"{d['dir']}: role {d['role']!r} is none of {', '.join(ROLES)}")
        cfg = {"dirs": dirs, "exempt_file": doc["exempt_file"], "runner": doc["runner"],
               "exempt_excuses_wiring": bool(doc.get("exempt_excuses_wiring")),
               "exempt_required": bool(doc.get("exempt_required", True)),
               "package_scripts": doc.get("package_scripts"),
               "tree_excludes": list(doc.get("tree_excludes", [".git", "node_modules", ".claude/worktrees"])),
               "report": doc["report"], "text": doc["text"]}
        if cfg["package_scripts"] not in (None, "pnpm"):
            raise ValueError(f"package_scripts {cfg['package_scripts']!r} is neither null nor \"pnpm\"")
        if cfg["report"] not in ("grouped", "lines"):
            raise ValueError(f"report {cfg['report']!r} is neither \"grouped\" nor \"lines\"")
    except (OSError, ValueError, KeyError, TypeError, AttributeError, re.error) as e:
        raise Refused(f"cannot read {path}: {e}") from None
    return cfg


def exemptions(path: str) -> list[str]:
    """The list's entries: a comment cut at its #, blanks dropped."""
    with open(path, encoding="utf-8") as fh:
        return [e for e in (line.split("#", 1)[0].strip() for line in fh) if e]


# ── what the workflows run ───────────────────────────────────────────

def _why(e: Exception) -> str:
    return e.strerror if isinstance(e, OSError) and e.strerror else str(e)


RUN_KEY = re.compile(r'^(\s*)(?:-\s+)?run:\s*(.*)$')


def run_commands(workflows: str) -> list[str]:
    """Only the text a workflow actually EXECUTES: the value of each run:,
    the body of a block scalar included. Line-based rather than a YAML
    parse, deliberately: a YAML dependency to answer a question about text
    is not worth having. A line that is a shell comment or an echo runs
    nothing that this could be asked about, and is dropped: a commented-out
    step is the step as it was, not as it is."""
    out = []
    for dirpath, dirnames, files in os.walk(workflows):
        dirnames.sort()
        for name in sorted(files):
            if not name.endswith((".yml", ".yaml")):
                continue
            path = os.path.join(dirpath, name)
            try:
                with open(path, encoding="utf-8") as fh:
                    lines = fh.read().split("\n")
            except (OSError, ValueError) as e:
                # Skipped, its steps would read as "never run": the
                # verdict this check exists to give, fabricated.
                raise Refused(f"could not read the workflow run commands: {path}: {_why(e)}") from None
            i = 0
            while i < len(lines):
                m = RUN_KEY.match(lines[i])
                if not m:
                    i += 1
                    continue
                indent, rest = len(m.group(1)), m.group(2).strip()
                i += 1
                if rest and rest[0] not in "|>":
                    # A quoted one-line value is the same shell once
                    # unquoted, so it is judged, and matched, without quotes.
                    body = rest.strip("'\"").lstrip()
                    if not body.startswith(("echo ", "#")):
                        out.append(body)
                    continue
                while i < len(lines):
                    line = lines[i]
                    if line.strip() and (len(line) - len(line.lstrip())) <= indent:
                        break
                    if not line.lstrip().startswith(("echo ", "#")):
                        out.append(line)
                    i += 1
    return out


def matrix_values(text: str) -> dict[str, set[str]]:
    """Every value of each key in a workflow's matrix: blocks — include:
    rows, plain lists, a block scalar's lines — split on whitespace: a
    row's `apps: admin_web status_web` is two packages."""
    values: dict[str, set[str]] = {}
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        m = re.match(r"^(\s*)matrix:\s*$", lines[i])
        if not m:
            i += 1
            continue
        indent = len(m.group(1))
        i += 1
        while i < len(lines):
            line = lines[i]
            if line.strip() and not line.lstrip().startswith("#") and len(line) - len(line.lstrip()) <= indent:
                break
            kv = re.match(r"^\s*(?:-\s+)?([A-Za-z_][\w-]*):\s*(.*?)\s*$", line)
            if kv and re.match(r"^[|>][+-]?$", kv.group(2)):
                own = len(line) - len(line.lstrip())
                j = i + 1
                while j < len(lines) and (not lines[j].strip() or len(lines[j]) - len(lines[j].lstrip()) > own):
                    values.setdefault(kv.group(1), set()).update(lines[j].split())
                    j += 1
            elif kv and kv.group(2) != "":
                values.setdefault(kv.group(1), set()).update(re.sub(r"[\[\],'\"]", " ", kv.group(2)).split())
            elif kv:
                j = i + 1
                while j < len(lines) and re.match(r"^\s*-\s+[^:\s][^:]*$", lines[j]):
                    values.setdefault(kv.group(1), set()).update(re.sub(r"['\"]", "", lines[j].split("-", 1)[1]).split())
                    j += 1
            i += 1
    return values


def loop_bindings(text: str, matrix: dict[str, set[str]]) -> dict[str, set[str]]:
    """Each for-loop variable bound to the words of its list, a
    ${{ matrix.<k> }} — spliced in, or reaching the loop through a step's
    env: (the form zizmor's template-injection audit asks for) — read as
    the matrix's values for <k>."""
    bound: dict[str, set[str]] = {}
    env_matrix = dict(re.findall(r"^\s*(\w+):\s*\$\{\{\s*matrix\.(\w+)\s*\}\}\s*$", text, re.M))
    for var, lst in re.findall(r"for\s+(\w+)\s+in\s+(.+?);?\s*(?:do\b|$)", text, re.M):
        lst = re.sub(r"\$\{?(\w+)\}?",
                     lambda mm: "${{ matrix.%s }}" % env_matrix[mm.group(1)] if mm.group(1) in env_matrix
                     else mm.group(0), lst)
        # The expression carries spaces inside its braces: replaced with
        # its values BEFORE the list splits.
        lst = re.sub(r"\$\{\{\s*matrix\.(\w+)\s*\}\}", lambda mm: " ".join(sorted(matrix.get(mm.group(1), set()))),
                     lst)
        bound.setdefault(var, set()).update(w.strip("\"'") for w in lst.split())
    return bound


PNPM = re.compile(r"pnpm\s+(?:--filter|-F)\s+(\S+)\s+(?:run\s+)?([A-Za-z0-9_:.-]+)")


def package_commands(root: str, workflows: str, excludes: set[str]) -> list[str]:
    """For every `pnpm --filter <pkg> <script>` a workflow runs, that
    script's body: ONE hop, the one the projects use; deeper would be
    guessing at reachability rather than reading it. pnpm runs a script in
    its package's directory, so each *.sh path in the body is rewritten
    against it, in place — the runner in front of it stays visible."""
    by_name = {}
    for dirpath, dirnames, files in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in excludes)
        if "package.json" not in files:
            continue
        path = os.path.join(dirpath, "package.json")
        try:
            with open(path, encoding="utf-8") as fh:
                doc = json.load(fh)
        except (OSError, ValueError) as e:
            raise Refused(f"could not read package scripts: {path}: {_why(e)}") from None
        if not isinstance(doc, dict):
            raise Refused(f"could not read package scripts: {path}: not a JSON object")
        name, scripts = doc.get("name"), doc.get("scripts")
        if isinstance(name, str) and isinstance(scripts, dict):
            by_name[name] = (os.path.relpath(dirpath, root), scripts)
    invoked = set()
    for dirpath, dirnames, files in os.walk(workflows):
        dirnames.sort()
        for fn in sorted(files):
            if not fn.endswith((".yml", ".yaml")):
                continue
            path = os.path.join(dirpath, fn)
            try:
                with open(path, encoding="utf-8") as fh:
                    text = fh.read()
            except (OSError, ValueError) as e:
                raise Refused(f"could not read the workflow run commands: {path}: {_why(e)}") from None
            code = "\n".join(strip_comment(l) for l in text.split("\n"))
            bound = loop_bindings(code, matrix_values(code))
            for line in code.split("\n"):
                for token, script in PNPM.findall(line):
                    m = re.match(r"^[\"']?\$\{?(\w+)\}?[\"']?$", token)
                    for pkg in (bound.get(m.group(1), set()) if m else {token.strip("\"'")}):
                        invoked.add((pkg, script))
    out = []
    for pkg, script in sorted(invoked):
        entry = by_name.get(pkg)
        if not entry:
            continue
        pkgdir, scripts = entry
        body = scripts.get(script)
        if body:
            out.append(re.sub(r"[\w./-]+\.sh", lambda m: os.path.normpath(os.path.join(pkgdir, m.group(0))), body))
    return out


# ── is it run, and how ───────────────────────────────────────────────

def glob_regex(pattern: str) -> re.Pattern:
    """A shell glob as a regex over a path: * and ? never cross a /."""
    out, i = [], 0
    while i < len(pattern):
        c = pattern[i]
        if c == "*":
            out.append("[^/]*")
        elif c == "?":
            out.append("[^/]")
        elif c == "[":
            j = pattern.find("]", i + 2)
            if j < 0:
                out.append(re.escape(c))
            else:
                body = pattern[i + 1:j]
                out.append("[" + ("^" + body[1:] if body.startswith("!") else body) + "]")
                i = j
        else:
            out.append(re.escape(c))
        i += 1
    try:
        return re.compile("".join(out))
    except re.error:
        # Not a pattern bash could expand either ([z-a]): it names
        # nothing, so it wires nothing — never a traceback that reads as
        # a finding.
        return re.compile(r"(?!)")


def _globs(line: str) -> list[str]:
    return [t for t in (w.strip("'\"").rstrip(";") for w in line.split()) if GLOB_CHARS.search(t)]


def glob_matches(glob: str, rel: str) -> bool:
    """The glob, or its tail from any /, matches the whole path: as a
    literal may carry a prefix (./tools/x.sh, $ROOT/tools/x.sh), so may a
    glob, but never a different directory."""
    starts = [0] + [i + 1 for i, c in enumerate(glob) if c == "/"]
    return any(glob_regex(glob[s:]).fullmatch(rel) for s in starts)


def _literal(rel: str) -> re.Pattern:
    # Path-qualified, as ANY argument: `tools/checks/x.sh` cannot be
    # satisfied by `tools/checks/test_x.sh`, and a suite run through a
    # wrapper is still run.
    return re.compile(r"(^|\s)\S*" + re.escape(rel) + r"(\s|$)")


FOR_HEAD = re.compile(r"\bfor\s+([A-Za-z_]\w*)\s+in\s")


def _runs_bare(segment: str, ref: set[str], runner: str) -> bool:
    """The segment runs the loop's suite without the runner: `"$t"`,
    `./"$t"`, or bash/sh with $t among its arguments and no runner there.
    A command this cannot read that names $t counts as bare: unknown is
    never a pass."""
    cmd = command(segment)
    if not cmd:
        return False
    if cmd == [UNREADABLE]:
        return any(r in segment for r in ref)
    if cmd[0] in ref or (cmd[0].startswith("./") and cmd[0][2:] in ref):
        return True
    if os.path.basename(cmd[0]) in ("bash", "sh"):
        return any(a in ref for a in cmd[1:]) and not any(os.path.basename(a) == runner for a in cmd[1:])
    return False


# Words that open a compound command before the command itself.
KEYWORDS = {"then", "do", "else", "elif", "if", "while", "until", "{", "(", "!", "time"}


# Words that run the word after them as the command (by basename:
# /usr/bin/env is env); timeout's first argument is its duration.
PREFIXES = {"env", "command", "builtin", "exec", "nohup", "timeout"}
# What command() answers for a command it cannot read with certainty —
# an option to a prefix, whose argument count it does not know. It is
# never "echo" and never a path, so nothing behind it counts as run.
UNREADABLE = "\0unreadable"


def words(segment: str) -> list[str]:
    """A segment's words as the shell splits and unquotes them; a segment
    shlex cannot read (an unclosed quote) splits on whitespace."""
    try:
        return shlex.split(segment, comments=False)
    except ValueError:
        return segment.split()


def command(segment: str) -> list[str]:
    """The command a segment runs and its arguments: past its leading
    keywords, VAR=value assignments and prefixes (env, command, exec…).
    [UNREADABLE] when a prefix carries an option: what it runs then
    depends on an argument count this does not know."""
    ws, i, prefixed = words(segment), 0, False
    while i < len(ws):
        w = ws[i]
        if w in KEYWORDS or re.fullmatch(r"[A-Za-z_]\w*=.*", w, re.S):
            i += 1
        elif os.path.basename(w) in PREFIXES:
            prefixed = True
            if os.path.basename(w) == "timeout":
                # Its duration, unless an option comes first: then how
                # many words it takes is unknown, and so is the command.
                if i + 1 < len(ws) and ws[i + 1].startswith("-"):
                    return [UNREADABLE]
                i += 1
            i += 1
        elif prefixed and w.startswith("-"):
            return [UNREADABLE]
        else:
            return ws[i:]
    return []


def command_word(segment: str) -> str:
    cmd = command(segment)
    return cmd[0] if cmd else ""


def strip_comment(line: str) -> str:
    """The line without its shell comment: a # that starts a word, outside
    quotes. `true # bash tools/checks/x.sh` runs nothing of x; a # inside
    ${#arr} or a quoted string is no comment."""
    quote, escaped = "", False
    for i, c in enumerate(line):
        if escaped:
            escaped = False
        elif c == "\\" and quote != "'":
            escaped = True
        elif quote:
            if c == quote:
                quote = ""
        elif c in "'\"":
            quote = c
        elif c == "#" and (i == 0 or line[i - 1].isspace()):
            return line[:i]
    return line
DONE = re.compile(r"(^|[;\s])done([;\s]|$)")


class Runs:
    """The run text, read once: the guard asks dozens of names of it."""

    def __init__(self, commands: list[str], runner: str):
        # Only what runs: a comment after a command runs nothing.
        self.lines = [strip_comment(l) for l in commands]
        # Every command of every line on a line of its own, for the
        # per-segment rule: a second command after ;, &&, || or | does
        # not excuse the first.
        text = "\n".join(self.lines)
        for sep in ("&&", "||", ";", "|"):
            text = text.replace(sep, "\n")
        self.segments = text.split("\n")
        # ...and an echo prints a name it does not run, also behind a
        # keyword (`then echo …`, `do echo …`).
        self.executed = [s for s in self.segments if command_word(s) not in ("echo", UNREADABLE)]
        self.runner_path = runner
        self.runner = re.escape(os.path.basename(runner))
        self.loops = self._loops()

    def _loops(self) -> list[tuple[str, list[str], bool]]:
        """Each for-loop over self-test globs: its head, its globs, and
        whether its body, read through its done, runs the runner."""
        loops, i = [], 0
        while i < len(self.lines):
            line = self.lines[i]
            m = FOR_HEAD.search(line)
            globs = [g for g in _globs(line[m.end():].split(";")[0])
                     if os.path.basename(g).startswith("test_")] if m else []
            if not globs:
                i += 1
                continue
            # The body is what lies between the head and its done, and the
            # runner must be handed the loop's own variable there: a runner
            # elsewhere in it, or after the done, runs some other suite.
            body, j = [], i
            while j < len(self.lines):
                text = self.lines[j] if j > i else self.lines[j][m.end():]
                end = DONE.search(text)
                body.append(text[:end.start()] if end else text)
                if end:
                    break
                j += 1
            var = re.escape(m.group(1))
            ref = r"[\"']?\$(\{" + var + r"\}|" + var + r"\b)"
            hands = re.compile(r"(^|[\s/])" + self.runner + r"\s+" + ref)
            # ...and never also runs it bare: `bash "$t"` beside a wrapped
            # run of the same $t is a bare run all the same.
            segments = [s for b in body for s in re.split(r"&&|\|\||;|\|", b)]
            loop_ref = {"$" + m.group(1), "${" + m.group(1) + "}"}
            bare_run = any(_runs_bare(s, loop_ref, os.path.basename(self.runner_path)) for s in segments)
            wrapped = any(hands.search(b) for b in body) and not bare_run
            loops.append((line.strip(), globs, wrapped))
            i = j + 1
        return loops

    def wired(self, rel: str) -> bool:
        lit = _literal(rel)
        return any(lit.search(s) or any(glob_matches(g, rel) for g in _globs(s)) for s in self.executed)

    def bare(self, rel: str) -> bool:
        """Run, somewhere, without the runner: a literal on a segment that
        does not hand it to the runner, or a glob outside a loop likewise.
        A loop's glob is the loop's to answer (bare_loops)."""
        lit = _literal(rel)
        wrapped = re.compile(r"(^|\s)\S*" + self.runner + r"\s+\S*" + re.escape(rel) + r"(\s|$)")
        heads = {g for _h, gs, _w in self.loops for g in gs}
        for seg in self.executed:
            if lit.search(seg) and not wrapped.search(seg):
                return True
            for g in _globs(seg):
                if g in heads or not glob_matches(g, rel):
                    continue
                if not re.search(r"(^|\s)\S*" + self.runner + r"\s+\S*" + re.escape(g) + r"(\s|$)", seg):
                    return True
        return False

    def bare_loops(self) -> list[str]:
        return [head for head, _g, wrapped in self.loops if not wrapped]


# ── the check ────────────────────────────────────────────────────────

def _files(directory: str) -> list[str]:
    try:
        names = os.listdir(directory)
    except (FileNotFoundError, NotADirectoryError):
        return []
    return sorted((n for n in names if os.path.isfile(os.path.join(directory, n))), key=os.fsencode)


def _excluded(rel: str, excludes: list[str]) -> bool:
    padded = "/" + rel + "/"
    return any("/" + e.strip("/") + "/" in padded for e in excludes)


def check(root: str, cfg: dict) -> dict:
    """The findings, as the report forms read them."""
    workflows = os.path.join(root, WORKFLOWS)
    if not os.path.isdir(workflows):
        raise Refused(f"workflows directory not found at {workflows}")
    exempt_path = os.path.join(root, cfg["exempt_file"])
    exempt: list[str] = []
    if os.path.isfile(exempt_path):
        try:
            exempt = exemptions(exempt_path)
        except (OSError, ValueError) as e:
            raise Refused(f"cannot read {exempt_path}: {e}") from None
    elif cfg["exempt_required"]:
        # Required where the list is the record of what may skip a
        # self-test: absent, nothing says the tree was meant to have none.
        raise Refused(f"exemption list not found at {exempt_path}")
    # A FAILED READ MUST BE LOUD: every verdict below asks "is this name in
    # the run text", so a failed read would surface as "these guards can
    # never fail a build", fabricated. An EMPTY one is fine: a workflow
    # whose steps all echo legitimately runs nothing.
    commands = run_commands(workflows)
    if cfg["package_scripts"]:
        commands += package_commands(root, workflows, set(os.path.basename(e) for e in cfg["tree_excludes"]))
    runs = Runs(commands, cfg["runner"])

    def is_exempt(rel: str) -> bool:
        return any(e == rel or ("/" not in e and e == os.path.basename(rel)) for e in exempt)

    f = {"events": [], "unwired": [], "untested": [], "unwired_tests": [], "bare": [], "guards": 0,
         "exempt": len(exempt)}
    scanned = set()
    for d in cfg["dirs"]:
        directory = os.path.join(root, d["dir"])
        scanned.add(os.path.normpath(d["dir"]))
        files = _files(directory)
        for name in files:
            rel = f"{d['dir']}/{name}"
            shown = name if d["names"] == "basename" else rel
            if name.startswith("test_"):
                # Every self-test, of any extension: one that satisfies a
                # member and that no workflow runs is the loophole itself.
                if not runs.wired(rel):
                    f["unwired_tests"].append(shown)
                    f["events"].append(("test_unwired", rel, d["dir"]))
                if name.endswith(".sh") and runs.bare(rel):
                    f["bare"].append(rel)
                    f["events"].append(("test_bare", rel, d["dir"]))
                continue
            if not d["members"].search(name):
                continue
            stem = name.rsplit(".", 1)[0]
            if d["role"] in ("guard", "ci"):
                f["guards"] += 1
            if not any(n.startswith(f"test_{stem}.") for n in files) and not is_exempt(rel):
                f["untested"].append(shown)
                f["events"].append(("member_untested", rel, d["dir"]))
            if d["role"] in ("guard", "ci") and not (cfg["exempt_excuses_wiring"] and is_exempt(rel)) \
                    and not runs.wired(rel):
                f["unwired"].append(shown)
                f["events"].append(("member_unwired", rel, d["dir"]))
    # EVERY OTHER test_*.sh IN THE TREE: a list of directories is the same
    # narrowness one level out, and the next self-test put somewhere new
    # would be invisible again. Hidden directories are not walked, as
    # bash's ** never entered them.
    for dirpath, dirnames, files in os.walk(root):
        reldir = os.path.relpath(dirpath, root)
        dirnames[:] = sorted((n for n in dirnames if not n.startswith(".")
                              and not _excluded(os.path.normpath(os.path.join(reldir, n)), cfg["tree_excludes"])),
                             key=os.fsencode)
        # A configured directory's own files are its listing's; a
        # subdirectory of it is the tree's like any other, or a self-test
        # put one level down would be the invisible one.
        if os.path.normpath(reldir) in scanned:
            continue
        for name in sorted(files, key=os.fsencode):
            if name.startswith("test_") and name.endswith(".sh"):
                rel = os.path.normpath(os.path.join(reldir, name))
                if not runs.wired(rel):
                    f["unwired_tests"].append(rel)
                    f["events"].append(("test_unwired", rel, reldir))
    for head in runs.bare_loops():
        f["bare"].append(head)
        f["events"].append(("loop_bare", head, ""))
    return f


# ── the report, in the project's form ────────────────────────────────

def _fill(line: str, **kw) -> str:
    for k, v in kw.items():
        line = line.replace("{" + k + "}", str(v))
    return line


def report(f: dict, cfg: dict) -> int:
    text, exempt_name = cfg["text"], os.path.basename(cfg["exempt_file"])
    if cfg["report"] == "grouped":
        failed = False
        for key in ("unwired", "unwired_tests", "bare", "untested"):
            if f[key]:
                failed = True
                for line in text[key]:
                    print(_fill(line, n=len(f[key]), exempt_name=exempt_name))
                for name in f[key]:
                    print(f"        {name}")
                print()
        # The footer is advice for an unwired or untested guard; a self-test
        # run bare has its fix in its own block, and fails all the same.
        if f["unwired"] or f["unwired_tests"] or f["untested"]:
            for line in text["footer"]:
                print(_fill(line, exempt_name=exempt_name))
        if failed:
            return 1
        print(_fill(text["ok"], guards=f["guards"], exempt=f["exempt"]))
        return 0
    for kind, what, d in f["events"]:
        stem = os.path.basename(what).rsplit(".", 1)[0]
        print(_fill(text[kind], path=what, loop=what, dir=d, stem=stem))
    if f["events"]:
        sys.stdout.flush()
        print(_fill(text["summary"], n=len(f["events"])), file=sys.stderr)
        return 1
    print(_fill(text["ok"], guards=f["guards"], exempt=f["exempt"]))
    return 0


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="surrogateescape")
    sys.stderr.reconfigure(encoding="utf-8", errors="surrogateescape")
    try:
        root = parse_root(sys.argv[1:])
        if root is None:
            print(__doc__.strip("\n"))
            return 0
        root = root or toplevel()
        cfg = load_config(project_config(root, "guards.json", SETTING), root)
        return report(check(root, cfg), cfg)
    except Refused as e:
        print(f"{PROG}: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
