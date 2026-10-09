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


def _pattern_text(node: ast.AST) -> tuple[str, str] | None:
    """(the literal text, its literal tail) of a string or f-string, the
    interpolated parts left out: an f-string's anchor is in its last
    literal part, and a `(?m)` in any literal part. None for anything else."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value, node.value
    if isinstance(node, ast.JoinedStr) and node.values:
        parts = [v.value for v in node.values if isinstance(v, ast.Constant) and isinstance(v.value, str)]
        last = node.values[-1]
        tail = last.value if isinstance(last, ast.Constant) and isinstance(last.value, str) else ""
        return "".join(parts), tail
    return None


def _literal_dollar_pattern(call: ast.Call, flags_pos: int) -> bool:
    """True for a call whose first argument is a string or f-string literal
    ending in an anchoring `$`, with no multiline flag: with re.M the `$` is
    a line end and .match is what the author means."""
    text = _pattern_text(call.args[0]) if call.args else None
    if text is None:
        return False
    whole, tail = text
    if not _ends_in_dollar(tail) or re.search(r"\(\?[a-z]*m[a-z]*[:)]", whole):
        return False
    flags = [a for i, a in enumerate(call.args) if i == flags_pos] + [k.value for k in call.keywords if k.arg == "flags"]
    return not any(isinstance(n, (ast.Name, ast.Attribute)) and getattr(n, "attr", getattr(n, "id", "")) in ("M", "MULTILINE")
                   for f in flags for n in ast.walk(f))


def _is_re_call(node: ast.AST, attr: str) -> bool:
    return (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == attr
            and isinstance(node.func.value, ast.Name) and node.func.value.id == "re")


def _assigned(node: ast.AST) -> list[tuple[list[str], ast.AST]]:
    """([target names], value) for an assignment statement, else []."""
    if isinstance(node, ast.Assign):
        return [([t.id for t in node.targets if isinstance(t, ast.Name)], node.value)]
    if isinstance(node, ast.AnnAssign) and node.value is not None and isinstance(node.target, ast.Name):
        return [([node.target.id], node.value)]
    return []


def _own_statements(fn: ast.AST) -> list[ast.AST]:
    """The nodes of a function's or class's own body in source order, not
    crossing into the functions, lambdas and classes nested in it."""
    out: list[ast.AST] = []
    stack = list(ast.iter_child_nodes(fn))
    while stack:
        node = stack.pop()
        out.append(node)
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
            stack.extend(ast.iter_child_nodes(node))
    return sorted(out, key=lambda n: (getattr(n, "lineno", 0), getattr(n, "col_offset", 0)))


def _final_bindings(nodes: list[ast.AST]) -> dict[str, tuple[int, bool]]:
    """name -> (line, is a $-pattern) of its last binding among `nodes`,
    taken in source order: a later binding replaces an earlier one."""
    final: dict[str, tuple[int, bool]] = {}
    for node in nodes:
        for names, value in _assigned(node):
            for n in names:
                final[n] = (node.lineno, _is_dollar_compile(value))
    return final


def _is_dollar_compile(value: ast.AST) -> bool:
    return _is_re_call(value, "compile") and _literal_dollar_pattern(value, 1)


class _Module:
    """What one file says about names that could be a `$`-ended pattern:
    its module-level bindings, its classes' attributes, what it imports,
    plain re-bindings, and each .match call with the scope it is made in.
    Bindings are scoped: a function's parameter or local of the same name
    hides the module's (a pattern bound in one function says nothing of a
    parameter in another, review of #140), and a function's own pattern
    binding counts in that function."""

    def __init__(self, tree: ast.AST):
        # (call, the patterns in force in its function, the names that hide
        # the module's there, the class whose methods resolve self./cls.)
        self.matches: list[tuple[ast.Call, dict[str, int], frozenset[str], str | None]] = []
        self.bound: dict[str, int] = {}
        # every module-level binding of a name, in source order: a call made
        # at module level sees the one in force at its line, a call in a
        # function (run later) the last
        self.module_bindings: dict[str, list[tuple[int, bool]]] = {}
        # (class, X) -> (line, is a $-pattern) of X's last binding in that
        # class's body: the class's own binding decides before its bases
        self.class_final: dict[tuple[str, str], tuple[int, bool]] = {}
        self.class_names = {n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)}
        # a class's bases that are classes of this module, for inherited patterns
        self.class_bases: dict[str, list[str]] = {}
        # asname -> (level, module, name) for `from module import name`
        self.froms: dict[str, tuple[int, str, str]] = {}
        # asname -> dotted module for `import module`
        self.imports: dict[str, str] = {}
        # `A = B` and `A = mod.B`: the right-hand side
        self.aliases: dict[str, tuple[str, ...]] = {}
        self._scope(tree, None, {}, frozenset())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                for a in node.names:
                    self.froms[a.asname or a.name] = (node.level, node.module or "", a.name)
            elif isinstance(node, ast.Import):
                for a in node.names:
                    # `import a.b` binds `a`; only the plain and aliased forms name the module itself
                    if a.asname or "." not in a.name:
                        self.imports[a.asname or a.name] = a.name


    def _scope(self, node: ast.AST, fn: ast.AST | None, local: dict[str, int], hidden: frozenset[str],
               cls: str | None = None, in_class_body: bool = False) -> None:
        """Walk one scope: the module's (fn None), a class body's, or a
        function's, with the names in force there. A nested function sees
        its enclosing function's patterns and hidden names (a closure), and
        its own bindings stop at the functions nested in it. `cls` is the
        class whose methods resolve self. and cls."""
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                params = {a.arg for a in ast.walk(child.args) if isinstance(a, ast.arg)}
                final = _final_bindings(_own_statements(child))
                own = {n: line for n, (line, dollar) in final.items() if dollar and n not in params}
                others = set(params) | {n for n, (_, dollar) in final.items() if not dollar}
                inner_local = {k: v for k, v in local.items() if k not in others} | own
                inner_hidden = frozenset((set(hidden) | others) - set(own))
                self._scope(child, child, inner_local, inner_hidden, cls)
                continue
            if isinstance(child, ast.ClassDef):
                self.class_bases[child.name] = [b.id for b in child.bases if isinstance(b, ast.Name)]
                # the class body's own statements, an if or a try inside it
                # included, not the methods or classes nested in it
                for n, binding in _final_bindings(_own_statements(child)).items():
                    self.class_final[(child.name, n)] = binding
                # a class body's names are its attributes, not the module's
                self._scope(child, fn, local, hidden, child.name, in_class_body=True)
                continue
            if fn is None and not in_class_body:
                for names, value in _assigned(child):
                    dollar = _is_dollar_compile(value)
                    for n in names:
                        self.module_bindings.setdefault(n, []).append((child.lineno, dollar))
                        if dollar:
                            self.bound[n] = child.lineno
                        else:
                            self.bound.pop(n, None)
                            self.aliases.pop(n, None)
                    if dollar:
                        continue
                    if isinstance(value, ast.Name):
                        for n in names:
                            self.aliases[n] = (value.id,)
                    elif isinstance(value, ast.Attribute) and isinstance(value.value, ast.Name):
                        for n in names:
                            self.aliases[n] = (value.value.id, value.attr)
            if isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute) and child.func.attr == "match":
                self.matches.append((child, local, hidden, cls, fn is None and not in_class_body))
            # an if, a try or a with in a class body is still the class body
            self._scope(child, fn, local, hidden, cls, in_class_body)


    def at_line(self, name: str, line: int) -> tuple[int, bool] | None:
        """The module-level binding of `name` in force at `line`, or None
        when the module has bound it nowhere before that line."""
        before = [b for b in self.module_bindings.get(name, []) if b[0] < line]
        return before[-1] if before else None

    def class_pattern(self, cls: str, attr: str, seen: frozenset = frozenset()) -> int | None:
        """The line of `attr`'s $-pattern as `cls` has it: its own last
        binding decides; with none, a base class of this module it inherits
        from (review of #143)."""
        if cls in seen:
            return None
        if (cls, attr) in self.class_final:
            line, dollar = self.class_final[(cls, attr)]
            return line if dollar else None
        for base in self.class_bases.get(cls, []):
            line = self.class_pattern(base, attr, seen | {cls})
            if line:
                return line
        return None


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
    (importlib), and a pattern built by anything but a literal or f-string
    re.compile. A function's own names hide the module's; a class body's
    pattern is followed through self., cls. and the class's name."""
    findings = []
    tracked = _tracked(root)
    resolver = _Resolver(root, set(tracked))
    for rel in sorted(r for r in tracked if r.endswith(".py")):
        mod = resolver.module(rel)
        if mod is None:
            continue
        found: list[tuple[int, str]] = []
        for node, local, hidden, cls, at_module in mod.matches:
            if _is_re_call(node, "match") and _literal_dollar_pattern(node, 2):
                found.append((node.lineno, f"{rel}:{node.lineno}: re.match with a pattern ending in `$` accepts one trailing newline "
                                "— use re.fullmatch (or end the pattern in \\Z)"))
                continue
            target, name, hit = node.func.value, "", None
            if _is_dollar_compile(target):  # re.compile(r"...$").match(s)
                name, hit = "re.compile(...)", (rel, node.lineno)
            elif isinstance(target, ast.Name):
                name = target.id
                if name in local:
                    hit = (rel, local[name])
                elif name not in hidden:
                    now = mod.at_line(name, node.lineno) if at_module else None
                    if now is not None:  # run at import: the binding in force at this line
                        hit = (rel, now[0]) if now[1] else None
                    else:
                        hit = resolver.pattern(rel, name)
            elif isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name):
                name = f"{target.value.id}.{target.attr}"
                owner = cls if target.value.id in ("self", "cls") else target.value.id
                if target.value.id in ("self", "cls") or target.value.id in mod.class_names:
                    line = mod.class_pattern(owner, target.attr) if owner else None
                    hit = (rel, line) if line else None
                else:
                    hit = resolver.attribute(rel, target.value.id, target.attr)
            if hit:
                where = f"line {hit[1]}" if hit[0] == rel else f"{hit[0]}:{hit[1]}"
                found.append((node.lineno, f"{rel}:{node.lineno}: {name}.match, and {name} ({where}) ends in `$`, which accepts "
                                "one trailing newline — use fullmatch (or end the pattern in \\Z)"))
        findings += [f for _, f in sorted(found)]
    return findings
