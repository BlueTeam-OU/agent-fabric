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


def regex_dollar_findings(root: str) -> list[str]:
    """`$` also matches before one final "\\n", so `re.compile(r"^x$").match(s)`
    accepts "x\\n"; .fullmatch (or \\Z) does not. A finding per .match call on
    a name bound in the same file to such a pattern, and per direct
    re.match(r"...$", ...). A pattern imported from another file is not
    followed."""
    findings = []
    for rel in sorted(r for r in _tracked(root) if r.endswith(".py")):
        full = os.path.join(root, rel)
        try:
            with open(full, encoding="utf-8") as fh:
                tree = ast.parse(fh.read(), filename=rel)
        except (OSError, SyntaxError, ValueError):
            continue
        bound: dict[str, int] = {}
        found: list[tuple[int, str]] = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value is not None and _is_re_call(node.value, "compile") \
                    and _literal_dollar_pattern(node.value, 1):
                for t in (node.targets if isinstance(node, ast.Assign) else [node.target]):
                    if isinstance(t, ast.Name):
                        bound[t.id] = node.lineno
        for node in ast.walk(tree):
            if _is_re_call(node, "match") and _literal_dollar_pattern(node, 2):
                found.append((node.lineno, f"{rel}:{node.lineno}: re.match with a pattern ending in `$` accepts one trailing newline "
                                "— use re.fullmatch (or end the pattern in \\Z)"))
            elif (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "match"
                    and isinstance(node.func.value, ast.Name) and node.func.value.id in bound):
                name = node.func.value.id
                found.append((node.lineno, f"{rel}:{node.lineno}: {name}.match, and {name} (line {bound[name]}) ends in `$`, which accepts "
                                "one trailing newline — use fullmatch (or end the pattern in \\Z)"))
        findings += [f for _, f in sorted(found)]
    return findings
