#!/usr/bin/env python3
"""tools/fabric/evidence_caps.py — the check that GitHub's list caps have one owner (agent-fabric j119, owner's rule of
2026-11-08), as one predicate, on state_writes.py's pattern.

GitHub cuts a pull request's file list at 3000 and its commit list at 250 without an error, so every reader of either
must treat a list of that length as possibly cut. That is done once, in tools/fabric/github/evidence.py over the
constants of tools/fabric/github/common.py. In any other module of tools/fabric/ (results.py reads commits outside github/), two findings:

- **cap**: (in github/ and in a module that imports gh or github) the integer literal 250 or 3000 as an assigned value or a comparison operand — a local copy of a cap (arm's
  PR_COMMITS_CAP, pr_counts' REST_COMMIT_CAP, the two COMMIT_LIST_CAPs and results' REST_COMMITS_CAP were five). Another number is another list's
  cap (pr_gate_base.LIST_CAP) and is not judged.
- **read**: a call that names the REST path of a pull request's files or commits (`.../pulls/<n>/files`,
  `.../commits`), paginated or not: the read goes through evidence.PrEvidence, which returns the list whole or as
  Incomplete.

It is syntax, so it over-reports a literal that happens to be 250 (a number that is not a cap); such a line is
rewritten, or the number named, not excused. The lint and CI wiring is the owner's."""
from __future__ import annotations

import ast
import os
import re

FABRIC_DIR = "tools/fabric"
GITHUB_DIR = FABRIC_DIR + "/github"
OWNERS = frozenset({f"{GITHUB_DIR}/common.py", f"{GITHUB_DIR}/evidence.py"})
CAPS = frozenset({250, 3000})
PR_LIST_PATH = re.compile(r"/pulls/[^/]*/(?:files|commits)(?:[?/]|$)")


def judged_path(rel: str) -> bool:
    return rel.startswith(FABRIC_DIR + "/") and rel.endswith(".py") and rel not in OWNERS


def _cap(node: ast.AST | None) -> bool:
    return isinstance(node, ast.Constant) and type(node.value) is int and node.value in CAPS


def _text(node: ast.AST) -> str | None:
    """A string expression as text: an f-string's placeholders, and any non-literal operand of a `+`, as `x`. A path
    built in a variable or by concatenation before the call is read as the call's own argument would be."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(v.value if isinstance(v, ast.Constant) else "x" for v in node.values)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = _text(node.left), _text(node.right)
        return None if left is None and right is None else (left or "x") + (right or "x")
    return None


def _reads_pr_list(expr: ast.AST) -> bool:
    return any((t := _text(part)) is not None and PR_LIST_PATH.search(t) for part in ast.walk(expr))


def _cap_findings(rel: str, node: ast.AST) -> list[str]:
    if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)) and _cap(node.value):
        return [f"{rel}:{node.lineno}: cap: a local copy of GitHub's list cap; use common.PR_COMMIT_LIST_CAP or "
                "PR_FILE_LIST_CAP through github/evidence.py"]
    if isinstance(node, ast.Compare) and any(_cap(c) for c in [node.left, *node.comparators]):
        return [f"{rel}:{node.lineno}: cap: compared against GitHub's list cap; ask github/evidence.py"]
    return []


def scan(rel: str, text: str) -> list[str]:
    """`path:line: <finding>` lines for one module's source; none when rel is not judged or the source does not parse
    (a syntax error is the compiler's finding)."""
    if not judged_path(rel):
        return []
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    out = []
    # A literal 250 is a cap only where GitHub is read: in github/, or in a module that imports gh or github.
    caps_judged = rel.startswith(GITHUB_DIR + "/") or any(
        (isinstance(n, ast.Import) and any(a.name.split(".")[0] in ("gh", "github") for a in n.names))
        or (isinstance(n, ast.ImportFrom) and (n.module or "").split(".")[0] in ("gh", "github"))
        for n in ast.walk(tree))
    for node in ast.walk(tree):
        if caps_judged:
            out += _cap_findings(rel, node)
        # A call's argument, or the value a name is given (the path built before the call): a docstring's example is
        # neither.
        exprs = [*node.args, *(k.value for k in node.keywords)] if isinstance(node, ast.Call) \
            else [node.value] if isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value is not None else []
        if any(_reads_pr_list(x) for x in exprs):
            out.append(f"{rel}:{node.lineno}: read: a pull request's files or commits read outside github/evidence.py")
    return list(dict.fromkeys(out))


def findings(root: str) -> list[str]:
    """Every finding under root's tools/fabric/, sorted by module."""
    out = []
    for dirpath, dirs, names in os.walk(os.path.join(root, FABRIC_DIR)):
        dirs[:] = sorted(d for d in dirs if d != "__pycache__")
        for name in sorted(names):
            rel = os.path.relpath(os.path.join(dirpath, name), root)
            if judged_path(rel):
                with open(os.path.join(root, rel), encoding="utf-8") as fh:
                    out += scan(rel, fh.read())
    return out
