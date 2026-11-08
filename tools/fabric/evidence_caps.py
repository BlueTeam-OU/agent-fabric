#!/usr/bin/env python3
"""tools/fabric/evidence_caps.py — the check that GitHub's list caps have one owner (agent-fabric j119, owner's rule of
2026-11-08), as one predicate, on state_writes.py's pattern.

GitHub cuts a pull request's file list at 3000 and its commit list at 250 without an error, so every reader of either
must treat a list of that length as possibly cut. That is done once, in tools/fabric/github/evidence.py over the
constants of tools/fabric/github/common.py. In any other module of tools/fabric/github/, two findings:

- **cap**: the integer literal 250 or 3000 as an assigned value or a comparison operand — a local copy of a cap (arm's
  PR_COMMITS_CAP, pr_counts' REST_COMMIT_CAP and the two COMMIT_LIST_CAPs were four). Another number is another list's
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

GITHUB_DIR = "tools/fabric/github"
OWNERS = frozenset({f"{GITHUB_DIR}/common.py", f"{GITHUB_DIR}/evidence.py"})
CAPS = frozenset({250, 3000})
PR_LIST_PATH = re.compile(r"/pulls/[^/]*/(?:files|commits)(?:[?/]|$)")


def judged_path(rel: str) -> bool:
    return rel.startswith(GITHUB_DIR + "/") and rel.endswith(".py") and "/" not in rel[len(GITHUB_DIR) + 1:] \
        and rel not in OWNERS


def _cap(node: ast.AST | None) -> bool:
    return isinstance(node, ast.Constant) and type(node.value) is int and node.value in CAPS


def _text(node: ast.AST) -> str | None:
    """A string argument as text, an f-string's placeholders as `x`."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(v.value if isinstance(v, ast.Constant) else "x" for v in node.values)
    return None


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
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)) and _cap(node.value):
            out.append(f"{rel}:{node.lineno}: cap: a local copy of GitHub's list cap; use common.PR_COMMIT_LIST_CAP or "
                       "PR_FILE_LIST_CAP through github/evidence.py")
        elif isinstance(node, ast.Compare) and any(_cap(c) for c in [node.left, *node.comparators]):
            out.append(f"{rel}:{node.lineno}: cap: compared against GitHub's list cap; ask github/evidence.py")
        elif isinstance(node, ast.Call):
            for arg in [*node.args, *(k.value for k in node.keywords)]:
                for part in ast.walk(arg):
                    t = _text(part)
                    if t is not None and PR_LIST_PATH.search(t):
                        out.append(f"{rel}:{node.lineno}: read: a pull request's files or commits read outside "
                                   "github/evidence.py")
                        break
                else:
                    continue
                break
    return out


def findings(root: str) -> list[str]:
    """Every finding under root's tools/fabric/github/, sorted by module."""
    out = []
    base = os.path.join(root, GITHUB_DIR)
    for name in sorted(os.listdir(base)):
        rel = f"{GITHUB_DIR}/{name}"
        if not judged_path(rel):
            continue
        with open(os.path.join(base, name), encoding="utf-8") as fh:
            out += scan(rel, fh.read())
    return out
