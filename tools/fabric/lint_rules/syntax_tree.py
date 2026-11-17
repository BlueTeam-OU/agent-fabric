"""tools/fabric/lint_rules/syntax_tree.py — the one place the lint's syntax-tree rules get a module's tree from, so a module read by ten
rules is parsed once per lint run and not once per rule (j830: 5,413 parses of 886 files)."""
from __future__ import annotations

import ast
import warnings

# Keyed on the source text itself, not the path: tests call the finding functions in process on trees they rewrite between
# calls, and a path key (even with size and mtime) answers for the old file the moment a write lands inside one mtime tick.
# A changed file is a different key, so no run boundary is needed for correctness; lint.main() clears it only to bound memory.
# Rules share the trees and must not mutate them (tests/test_syntax_tree.py holds that).
# The cost is memory: every tree is held until the run ends, about 780 MiB peak for the corpus lint against 66 MiB parsing
# per rule, for about 8 s of its 70 (#624 review, measured in its sandbox). That fits SUITE_MEM_MIB (1024), what the
# test pool assumes per slot, the lint being one of its entries. No eviction: each rule walks every file in turn, so a
# bounded cache would drop each tree before the next rule asks for it and keep only the cost (j910).
_TREES: dict[str, ast.Module] = {}
# ast.walk over a whole module is the dearest step of every rule that scans for a node kind (j914: ~7 walks of the same 2.6M-node
# corpus per lint, each rebuilding the BFS order through iter_child_nodes). The tree is held beside its node list so a recycled id()
# cannot answer for another tree; cleared with _TREES.
_WALKS: dict[int, tuple[ast.AST, list[ast.AST]]] = {}


def parse(text: str, filename: str = "<unknown>") -> ast.Module:
    """The module's tree; SyntaxError (or ValueError) as ast.parse raises it. A failure is not cached, so the error names the
    caller's own filename every time."""
    tree = _TREES.get(text)
    if tree is None:
        with warnings.catch_warnings():
            # A scanned file's own invalid escape is its own lint's to report; under -W error it would read as a syntax error, a clean verdict.
            warnings.simplefilter("ignore")
            tree = _TREES[text] = ast.parse(text, filename=filename)
    return tree


def walk(tree: ast.AST) -> list[ast.AST]:
    """ast.walk(tree) as a list, computed once per tree: the same nodes in the same (breadth-first) order. Whole modules only: a
    subtree walked here would be held until clear() for a rule that asks once."""
    held = _WALKS.get(id(tree))
    if held is None or held[0] is not tree:
        held = _WALKS[id(tree)] = (tree, list(ast.walk(tree)))
    return held[1]


def clear() -> None:
    _TREES.clear()
    _WALKS.clear()
