"""tools/fabric/lint_rules/mechanisms.py — agent-fabric ADR-067 rule 3 over the tracked tree: tools/fabric/mechanisms.json
names each cross-cutting mechanism's owning module and status, and a claim it makes that the tree does not bear out is a
finding. An `enforced` entry is held to what a guard is (rule 2): its checker loaded by a lint rule that lint.py runs,
by the pre-commit hook, and by a case under tests/. A part of tools/fabric/lint.py, the entry point."""
from __future__ import annotations

import ast
import json
import os
import re

from .base import _tracked, syntax_tree

POLICY = "tools/fabric/mechanisms.json"
STATUSES = ("enforced", "pending", "planned")
JOB = re.compile(r"[a-z][a-z0-9-]*/j[0-9]+")
ADR = re.compile(r"ADR-[0-9]{3}")
LINT = "tools/fabric/lint.py"
LINT_RULES = "tools/fabric/lint_rules"
PRE_COMMIT = "tools/fabric/guards/commit_hooks.py"


def _tree(root: str, rel: str) -> ast.AST | None:
    try:
        with open(os.path.join(root, rel), encoding="utf-8") as fh:
            return syntax_tree.parse(fh.read())
    except (OSError, UnicodeDecodeError, SyntaxError, ValueError):
        return None


def _loaded_stems(tree: ast.AST | None) -> frozenset[str]:
    """Every stem the module loads: imports it, or calls `_load("<stem>")`, lint's by-path loader. Read from the syntax
    tree, so a comment or a docstring that names the checker is not a load. One walk answers for every mechanism."""
    stems: set[str] = set()
    for node in syntax_tree.walk(tree) if tree is not None else ():
        if isinstance(node, ast.Import):
            stems.update(a.name.split(".")[-1] for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            stems.add(str(node.module or "").split(".")[-1])
            stems.update(a.name for a in node.names)
        elif isinstance(node, ast.Call) and getattr(node.func, "id", getattr(node.func, "attr", None)) == "_load" \
                and node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
            stems.add(node.args[0].value)
    return frozenset(stems)


def _loads(tree: ast.AST | None, stem: str) -> bool:
    return stem in _loaded_stems(tree)


def _run_rules(root: str) -> list[str]:
    """The lint rule modules lint.py imports, in any of the three spellings of a package's module: a rule module nothing
    imports never runs."""
    names: set[str] = set()
    lint = _tree(root, LINT)
    for n in syntax_tree.walk(lint) if lint is not None else ():
        if isinstance(n, ast.ImportFrom) and str(n.module or "").startswith("fabric_lint_rules."):
            names.add(str(n.module).split(".")[-1])
        elif isinstance(n, ast.ImportFrom) and n.module == "fabric_lint_rules":
            names.update(a.name for a in n.names)
        elif isinstance(n, ast.Import):
            names.update(a.name.split(".")[-1] for a in n.names if a.name.startswith("fabric_lint_rules."))
    return [f"{LINT_RULES}/{n}.py" for n in sorted(names)]


def _names_tracked(path: object, tracked: set[str], package: bool) -> bool:
    """A file the tree tracks; for an owner also a package, named as its directory with the trailing slash (tools/fabric/work/
    is one owner of many modules). The slash is required, so a typo'd file name never passes as a prefix."""
    if not isinstance(path, str):
        return False
    if package and path.endswith("/") and len(path) > 1:
        return any(t.startswith(path) for t in tracked)
    return path in tracked


def mechanism_findings(root: str) -> list[str]:
    try:
        with open(os.path.join(root, POLICY), encoding="utf-8") as fh:
            doc = json.load(fh)
    except FileNotFoundError:
        return []           # a fixture tree without the catalogue has nothing to judge
    except (OSError, ValueError) as exc:
        return [f"{POLICY}: cannot be read as JSON ({exc.__class__.__name__}); ADR-067 is not judged"]
    entries = doc.get("mechanisms") if isinstance(doc, dict) else None
    if not isinstance(entries, dict) or not entries:
        return [f"{POLICY}: needs a non-empty \"mechanisms\" object (ADR-067 rule 2)"]
    tracked = set(_tracked(root))
    rules = [r for r in _run_rules(root) if r in tracked]
    tests = [t for t in tracked if t.startswith("tests/") and os.path.basename(t).startswith("test_") and t.endswith(".py")]
    stems_of: dict[str, frozenset[str]] = {}

    def loads(rel: str, stem: str) -> bool:
        if rel not in stems_of:
            stems_of[rel] = _loaded_stems(_tree(root, rel))
        return stem in stems_of[rel]

    out: list[str] = []
    for name, e in sorted(entries.items()):
        where = f"{POLICY}: {name}"
        if not isinstance(e, dict):
            out.append(f"{where}: an entry is an object")
            continue
        if not ADR.fullmatch(str(e.get("adr") or "")):
            out.append(f"{where}: \"adr\" names the record it comes from, ADR-NNN")
        status = e.get("status")
        if status not in STATUSES:
            out.append(f"{where}: status {status!r} is not one of {', '.join(STATUSES)}")
            continue
        # A planned mechanism's owner is not built yet (rule 2); any path an entry does name must exist.
        for key in ("owner", "checker", "exceptions"):
            path = e.get(key)
            if path is None and (key == "owner" and status != "planned" or key != "owner" and status == "enforced"):
                out.append(f"{where}: {'an' if status[0] in 'aeiou' else 'a'} {status} mechanism must name its {key} (ADR-067 rule 2)")
            elif path is not None and not _names_tracked(path, tracked, package=key == "owner"):
                out.append(f"{where}: {key} {path!r} is not a tracked file"
                           + (" or a directory/ holding one" if key == "owner" else ""))
        checker = e.get("checker")
        if status == "enforced" and isinstance(checker, str) and checker in tracked:
            stem = os.path.splitext(os.path.basename(checker))[0]
            if not any(loads(r, stem) for r in rules):
                out.append(f"{where}: enforced, but no lint rule that {LINT} imports loads {checker}")
            if not loads(PRE_COMMIT, stem):
                out.append(f"{where}: enforced, but the pre-commit hook ({PRE_COMMIT}) does not load {checker}")
            if not any(loads(t, stem) for t in tests):
                out.append(f"{where}: enforced, but no tests/test_*.py loads {checker}")
        if status == "pending" and not JOB.fullmatch(str(e.get("job") or "")):
            out.append(f"{where}: a pending mechanism names the job building its checker as <login>/j<n>")
        if status == "planned" and not str(e.get("waits_on") or "").strip():
            out.append(f"{where}: a planned mechanism says what it waits on (\"waits_on\")")
    return out
