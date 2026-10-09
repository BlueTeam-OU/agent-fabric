"""tools/fabric/lint_rules/regex.py — a `$`-anchored pattern called with .match.
A part of tools/fabric/lint.py, the entry point."""
from __future__ import annotations

import ast
import os
import re

from .base import _tracked


def _ends_in_dollar(pattern: str) -> bool:
    """A `$` that is an anchor: `\\$` is a literal dollar, `\\\\$` an escaped
    backslash and then the anchor."""
    if not pattern.endswith("$"):
        return False
    slashes = len(pattern) - 1 - len(pattern[:-1].rstrip("\\"))
    return slashes % 2 == 0


def _literal_dollar_pattern(call: ast.Call, flags_pos: int) -> bool:
    """True for a call whose first argument is a string literal ending in an
    anchoring `$`, with no multiline flag: with re.M the `$` is a line end
    and .match is what the author means."""
    if not call.args or not (isinstance(call.args[0], ast.Constant) and isinstance(call.args[0].value, str)):
        return False
    pattern = call.args[0].value
    if not _ends_in_dollar(pattern) or re.search(r"\(\?[a-z]*m[a-z]*[:)]", pattern):
        return False
    flags = [a for i, a in enumerate(call.args) if i == flags_pos] + [k.value for k in call.keywords if k.arg == "flags"]
    return not any(isinstance(n, (ast.Name, ast.Attribute)) and getattr(n, "attr", getattr(n, "id", "")) in ("M", "MULTILINE")
                   for f in flags for n in ast.walk(f))


def _is_re_call(node: ast.AST, attr: str) -> bool:
    return (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == attr
            and isinstance(node.func.value, ast.Name) and node.func.value.id == "re")


class _Module:
    """What one file says about names that could be a `$`-ended pattern:
    its own bindings, what it imports, and plain re-bindings of either."""

    def __init__(self, tree: ast.AST):
        # every .match call, found in the one walk that also reads the bindings
        self.matches: list[ast.Call] = []
        self.bound: dict[str, int] = {}
        # asname -> (level, module, name) for `from module import name`
        self.froms: dict[str, tuple[int, str, str]] = {}
        # asname -> dotted module for `import module`
        self.imports: dict[str, str] = {}
        # `A = B` and `A = mod.B`: the right-hand side
        self.aliases: dict[str, tuple[str, ...]] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "match":
                self.matches.append(node)
            elif isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value is not None:
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                names = [t.id for t in targets if isinstance(t, ast.Name)]
                if _is_re_call(node.value, "compile") and _literal_dollar_pattern(node.value, 1):
                    for n in names:
                        self.bound[n] = node.lineno
                elif isinstance(node.value, ast.Name):
                    for n in names:
                        self.aliases[n] = (node.value.id,)
                elif isinstance(node.value, ast.Attribute) and isinstance(node.value.value, ast.Name):
                    for n in names:
                        self.aliases[n] = (node.value.value.id, node.value.attr)
            elif isinstance(node, ast.ImportFrom):
                for a in node.names:
                    self.froms[a.asname or a.name] = (node.level, node.module or "", a.name)
            elif isinstance(node, ast.Import):
                for a in node.names:
                    # `import a.b` binds `a`; only the plain and aliased forms name the module itself
                    if a.asname or "." not in a.name:
                        self.imports[a.asname or a.name] = a.name


class _Resolver:
    """Follows a name to the tracked file that binds it. Modules resolve
    among tracked files only. An absolute module is looked up beside the
    importing file first (the `sys.path.insert(0, dirname(__file__))` style),
    then from each ancestor directory up to the root (a package import with
    that directory on sys.path); a relative one from its package directory.
    Anything else (the standard library, a package not in the tree, a
    module loaded by path) resolves to nothing and is skipped."""

    def __init__(self, root: str, tracked: set[str]):
        self.root, self.tracked = root, tracked
        self.modules: dict[str, _Module | None] = {}

    def module(self, rel: str) -> _Module | None:
        if rel not in self.modules:
            try:
                with open(os.path.join(self.root, rel), encoding="utf-8") as fh:
                    self.modules[rel] = _Module(ast.parse(fh.read(), filename=rel))
            except (OSError, SyntaxError, ValueError):
                self.modules[rel] = None
        return self.modules[rel]

    def _file(self, base: str, dotted: str) -> str | None:
        path = os.path.join(base, *dotted.split("."))
        for cand in (path + ".py", os.path.join(path, "__init__.py")):
            cand = os.path.normpath(cand)
            if cand in self.tracked:
                return cand
        return None

    def file_of(self, importer: str, level: int, dotted: str) -> str | None:
        here = os.path.dirname(importer)
        if level:
            for _ in range(level - 1):
                here = os.path.dirname(here)
            return self._file(here, dotted) if dotted else None
        while True:
            found = self._file(here, dotted)
            if found:
                return found if found != importer else None
            if not here:
                return None
            here = os.path.dirname(here)

    def pattern(self, rel: str, name: str, seen: frozenset = frozenset()) -> tuple[str, int] | None:
        """(file, line) of the `$`-ended compile that `name` in `rel` ends at."""
        if (rel, name) in seen:
            return None
        seen = seen | {(rel, name)}
        mod = self.module(rel)
        if mod is None:
            return None
        if name in mod.bound:
            return rel, mod.bound[name]
        if name in mod.froms:
            level, dotted, orig = mod.froms[name]
            target = self.file_of(rel, level, dotted)
            return self.pattern(target, orig, seen) if target else None
        alias = mod.aliases.get(name)
        if alias and len(alias) == 1:
            return self.pattern(rel, alias[0], seen)
        if alias:
            return self.attribute(rel, alias[0], alias[1], seen)
        return None

    def attribute(self, rel: str, holder: str, attr: str, seen: frozenset = frozenset()) -> tuple[str, int] | None:
        """`holder.attr` in `rel`, where holder is an imported module."""
        mod = self.module(rel)
        if mod is None:
            return None
        target = None
        if holder in mod.imports:
            target = self.file_of(rel, 0, mod.imports[holder])
        elif holder in mod.froms:  # `from . import lineage as _lineage`
            level, dotted, orig = mod.froms[holder]
            target = self.file_of(rel, level, f"{dotted}.{orig}" if dotted else orig)
        return self.pattern(target, attr, seen) if target else None


def regex_dollar_findings(root: str) -> list[str]:
    """`$` also matches before one final "\\n", so `re.compile(r"^x$").match(s)`
    accepts "x\\n"; .fullmatch (or \\Z) does not. A finding per .match call on
    a name bound to such a pattern, and per direct re.match(r"...$", ...).
    The name is followed across tracked files through `from m import NAME`
    (absolute or relative, any number of re-exporting hops), `import m` then
    `m.NAME`, and plain re-bindings (`A = m.NAME`). Not followed: star
    imports, `import a.b` then `a.b.NAME`, a module loaded by path
    (importlib), a pattern built by anything but a literal re.compile, and a
    name rebound in a function or class scope."""
    findings = []
    tracked = _tracked(root)
    resolver = _Resolver(root, set(tracked))
    for rel in sorted(r for r in tracked if r.endswith(".py")):
        mod = resolver.module(rel)
        if mod is None:
            continue
        found: list[tuple[int, str]] = []
        for node in mod.matches:
            if _is_re_call(node, "match") and _literal_dollar_pattern(node, 2):
                found.append((node.lineno, f"{rel}:{node.lineno}: re.match with a pattern ending in `$` accepts one trailing newline "
                                "— use re.fullmatch (or end the pattern in \\Z)"))
                continue
            target, name, hit = node.func.value, "", None
            if isinstance(target, ast.Name):
                name, hit = target.id, resolver.pattern(rel, target.id)
            elif isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name):
                name, hit = f"{target.value.id}.{target.attr}", resolver.attribute(rel, target.value.id, target.attr)
            if hit:
                where = f"line {hit[1]}" if hit[0] == rel else f"{hit[0]}:{hit[1]}"
                found.append((node.lineno, f"{rel}:{node.lineno}: {name}.match, and {name} ({where}) ends in `$`, which accepts "
                                "one trailing newline — use fullmatch (or end the pattern in \\Z)"))
        findings += [f for _, f in sorted(found)]
    return findings
