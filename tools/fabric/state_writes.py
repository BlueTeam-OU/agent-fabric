#!/usr/bin/env python3
"""tools/fabric/state_writes.py — what agent-fabric ADR-003 rule 1 forbids, as
one predicate lint and the pre-commit hook both ask (j535).

Rule 1: no caller writes a file under `agents/<login>/` itself; it goes
through runtime/identity.py, or it is a writer class the record names. A
static reader cannot see where a path points, so this over-reports, by
design: a module that resolves the per-agent state directory AND writes a
file is judged, whatever it writes, until `policies/state-writers.json`
names it with the record's clause that admits it. Three findings:

- **copy**: the module reads AGENT_FABRIC_STATE_DIR itself — a copy of
  identity.state_root()'s resolution, which drifts from it (fabric_writes.py
  and gh_ledger.py each carried one, j487). Setting it for a child is not
  reading it.
- **write**: the module resolves the state directory (calls
  `agent_state_dir`, `state_root` or `agent_lock`, takes a parameter named
  `state_dir`, or is a copy) and opens a file for writing (builtin, `os` or
  any `.open` given a writing mode), makes a temporary, renames, copies,
  moves or links into place, or connects to SQLite, and the policy does not
  name it. The judgement is per module: a module that only passes a state
  directory to a function elsewhere is seen only where that function takes
  it as `state_dir`.
- **lock**: anywhere, a `.lock` file opened by builtin `open` (it takes the
  umask, 0644), or by `os.open` with `O_TRUNC` or a mode other than 0o600:
  a lock file is outside rule 1 only on those terms (ADR-003 §2,
  A 2026-10-31).

A listed module is admitted whole, every finding in it. An entry that
admits nothing is lint's finding (lint_rules/state.py), so an entry
leaves the policy when its job lands, and the module is held to all three.

runtime/identity.py is the writer and is not judged for copy or write."""
from __future__ import annotations

import ast
import json

POLICY = "policies/state-writers.json"
IDENTITY = "runtime/identity.py"
ENV = "AGENT_FABRIC_STATE_DIR"
RESOLVERS = frozenset({"agent_state_dir", "state_root", "agent_lock"})
WRITE_FLAGS = frozenset({"O_WRONLY", "O_RDWR", "O_CREAT", "O_APPEND", "O_TRUNC"})
WRITE_CALLS = frozenset({"mkstemp", "NamedTemporaryFile", "write_text", "write_bytes"})
STATE_PARAM = "state_dir"
OS_WRITES = frozenset({"replace", "rename", "link", "symlink", "mkfifo"})
SHUTIL_WRITES = frozenset({"copy", "copy2", "copyfile", "copytree", "move"})
_MODE_CHARS = set("rwaxbt+")


def _writing_mode(node: ast.AST | None) -> bool:
    return isinstance(node, ast.Constant) and isinstance(node.value, str) and bool(node.value) \
        and set(node.value) <= _MODE_CHARS and bool(set(node.value) & set("wax+"))


def parse_writers(text: str) -> dict[str, str]:
    """{module path: why it is admitted} from the policy's text; ValueError when it is not JSON. An entry that is not a
    string pair admits nothing."""
    doc = json.loads(text)
    writers = doc.get("writers") if isinstance(doc, dict) else None
    return {k: v for k, v in writers.items() if isinstance(k, str) and isinstance(v, str)} \
        if isinstance(writers, dict) else {}


def _name(fn: ast.AST) -> str:
    return fn.attr if isinstance(fn, ast.Attribute) else fn.id if isinstance(fn, ast.Name) else ""


def _owner(fn: ast.AST) -> str:
    return _name(fn.value) if isinstance(fn, ast.Attribute) else ""


def _names(node: ast.AST) -> set[str]:
    return {_name(n) for n in ast.walk(node) if isinstance(n, (ast.Attribute, ast.Name))}


def _lock_constants(tree: ast.Module) -> set[str]:
    """Module-level names bound to a string literal ending in `.lock` (`LOCK_FILE = "resume.lock"`)."""
    return {t.id for n in tree.body if isinstance(n, ast.Assign) and isinstance(n.value, ast.Constant)
            and isinstance(n.value.value, str) and n.value.value.endswith(".lock")
            for t in n.targets if isinstance(t, ast.Name)}


def _mentions_lock(node: ast.AST, constants: set[str]) -> bool:
    """A path expression that names a `.lock` file: `p + ".lock"`, an f-string ending in it, a literal, or a
    module constant holding one. A lock reached any other way is not seen: this over-reports writes, not locks."""
    return any((isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value.endswith(".lock"))
               or (isinstance(n, ast.Name) and n.id in constants) for n in ast.walk(node))


def _arg(call: ast.Call, pos: int, kw: str) -> ast.AST | None:
    if len(call.args) > pos:
        return call.args[pos]
    return next((k.value for k in call.keywords if k.arg == kw), None)


def _reads_env(node: ast.AST) -> bool:
    """os.environ.get(ENV) (or .get on a mapping named env or environment), os.getenv(ENV), environ[ENV] read (not
    stored), ENV in environ."""
    if isinstance(node, ast.Call) and _name(node.func) in ("get", "getenv") and node.args:
        a = node.args[0]
        return isinstance(a, ast.Constant) and a.value == ENV and (
            _name(node.func) == "getenv" or _name(node.func.value) in ("environ", "env", "environment")
            if isinstance(node.func, ast.Attribute) else False)
    if isinstance(node, ast.Compare) and isinstance(node.left, ast.Constant) and node.left.value == ENV:
        return any(isinstance(op, (ast.In, ast.NotIn)) for op in node.ops) and \
            any(_name(c) == "environ" for c in node.comparators)
    if isinstance(node, ast.Subscript) and isinstance(node.ctx, ast.Load):
        s = node.slice
        return isinstance(s, ast.Constant) and s.value == ENV and _name(node.value) == "environ"
    return False


def _write_kind(call: ast.Call) -> str | None:
    fn, name = call.func, _name(call.func)
    if name == "open" and (isinstance(fn, ast.Name) or _owner(fn) in ("io", "builtins")):
        mode = _arg(call, 1, "mode")
        if isinstance(mode, ast.Constant) and isinstance(mode.value, str):
            return f"open(..., {mode.value!r})" if set(mode.value) & set("wax+") else None
        return "open(..., <mode>)" if mode is not None else None
    if name == "open" and _owner(fn) == "os":
        path, flags = _arg(call, 0, "path"), _arg(call, 1, "flags")
        if isinstance(path, ast.Attribute) and path.attr == "devnull" and _name(path.value) == "os":
            return None   # a child's or a closed pipe's stdout pointed at os.devnull
        return "os.open for writing" if flags is not None and _names(flags) & WRITE_FLAGS else None
    if name in OS_WRITES and _owner(fn) == "os":
        return f"os.{name}"
    if name in SHUTIL_WRITES and _owner(fn) == "shutil":
        return f"shutil.{name}"
    if name == "open" and isinstance(fn, ast.Attribute):   # Path(...).open("w"), tarfile.open(p, "w"), …
        modes = [_arg(call, 0, "mode"), call.args[1] if len(call.args) > 1 else None]
        return f".open(..., {next(m.value for m in modes if _writing_mode(m))!r})" \
            if any(_writing_mode(m) for m in modes) else None
    if name == "connect" and _owner(fn) == "sqlite3":
        return "sqlite3.connect"
    if name in WRITE_CALLS and isinstance(fn, ast.Attribute):
        return f".{name}"
    return None


def _lock_finding(call: ast.Call, constants: set[str]) -> str | None:
    """Why a `.lock` open is not on the lock file's terms; None when it is, or when the open is not of a lock."""
    fn, name = call.func, _name(call.func)
    if name == "open" and (isinstance(fn, ast.Name) or _owner(fn) in ("io", "builtins")):
        path = _arg(call, 0, "file")
        if path is not None and _mentions_lock(path, constants):
            return "a .lock file opened by builtin open() takes the umask (0644); os.open(path, O_WRONLY | O_CREAT, 0o600)"
    if name == "open" and _owner(fn) == "os":
        path, flags, mode = _arg(call, 0, "path"), _arg(call, 1, "flags"), _arg(call, 2, "mode")
        if path is None or not _mentions_lock(path, constants):
            return None
        if flags is not None and "O_TRUNC" in _names(flags):
            return "a .lock file opened with O_TRUNC: a lock file is never truncated"
        if not (isinstance(mode, ast.Constant) and mode.value == 0o600):
            return "a .lock file opened without mode 0o600: it would take the umask's default (0644)"
    return None


def scan(rel: str, text: str, writers: dict[str, str]) -> list[str]:
    """Findings for one Python module, each `<rel>:<line>: <what> (ADR-003 rule 1)`."""
    try:
        tree = ast.parse(text, filename=rel)
    except SyntaxError:
        return []   # ruff refuses it in CI; a commit of a half-merged module is not this rule's to stop
    judged = rel != IDENTITY
    constants = _lock_constants(tree)
    copies: list[int] = []
    resolves = False
    writes: list[tuple[int, str]] = []
    locks: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.arg) and node.arg == STATE_PARAM:
            resolves = True
        if judged and _reads_env(node):
            copies.append(node.lineno)
        if not isinstance(node, ast.Call):
            continue
        if _name(node.func) in RESOLVERS:
            resolves = True
        kind = _write_kind(node)
        lock = _lock_finding(node, constants)
        if lock:
            locks.append(f"{rel}:{node.lineno}: {lock} (ADR-003 §2, rule 1)")
        elif kind == "os.open for writing" and _mentions_lock(_arg(node, 0, "path") or ast.Constant(None), constants):
            kind = None  # a lock file on its terms is not state (ADR-003 §2, A 2026-10-31)
        if kind:
            writes.append((node.lineno, kind))
    if rel in writers:
        return []
    out = locks
    if judged:
        out += [f"{rel}:{line}: reads {ENV} itself — a copy of identity.state_root(); call identity.agent_state_dir() "
                f"(ADR-003 rule 1)" for line in sorted(copies)]
        if resolves or copies:
            out += [f"{rel}:{line}: {kind} in a module that resolves the per-agent state directory — write through "
                    f"runtime/identity.py, or name the module and the record's clause in {POLICY} (ADR-003 rule 1)"
                    for line, kind in sorted(writes)]
    return sorted(out, key=lambda s: int(s.split(":")[1]) if s.split(":")[1].isdigit() else 0)


REASONS = ("ADR-003 ", "not state: ")


def policy_findings(writers: dict[str, str], present: set[str]) -> list[str]:
    """An entry for a module that is gone would admit the next file at that path unread; an entry that does not say
    which of the three it is admits on no stated ground."""
    out = [f"{POLICY}: {m} is listed as a state writer but is not a tracked file" for m in sorted(writers)
           if m not in present]
    out += [f"{POLICY}: {m}'s reason starts with none of {', '.join(repr(r) for r in REASONS)}"
            for m, why in sorted(writers.items()) if not why.startswith(REASONS)]
    return out


def removed_entries(before: dict[str, str], after: dict[str, str]) -> list[str]:
    """The modules an entry admitted before and does not now: a commit that only drops an entry still changes what they
    may do, so they are judged with it."""
    return sorted(set(before) - set(after))


def judged_path(rel: str) -> bool:
    """The fabric's own Python, the tests aside: a fixture writes a scratch state directory on purpose."""
    return rel.endswith(".py") and not rel.startswith("tests/")
