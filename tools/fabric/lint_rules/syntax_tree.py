"""tools/fabric/lint_rules/syntax_tree.py — the one place the lint's syntax-tree rules get a module's tree from, so a module read by ten
rules is parsed once per lint run and not once per rule (j830: 5,413 parses of 886 files)."""
from __future__ import annotations

import ast
import warnings

# Keyed on the source text itself, not the path: tests call the finding functions in process on trees they rewrite between
# calls, and a path key (even with size and mtime) answers for the old file the moment a write lands inside one mtime tick.
# A changed file is a different key, so no run boundary is needed for correctness; lint.main() clears it only to bound memory.
# Rules share the trees and must not mutate them (tests/test_syntax_tree.py holds that).
_TREES: dict[str, ast.Module] = {}


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


def clear() -> None:
    _TREES.clear()
