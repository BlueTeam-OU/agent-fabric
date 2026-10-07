"""tools/fabric/lint_rules/base.py — the paths and shared words every rule module reaches: layout and workingcopy by path, the frontmatter and payload shapes, the git helpers.
A part of tools/fabric/lint.py, the entry point."""
from __future__ import annotations

import importlib.util
import os
import re

_spec = importlib.util.spec_from_file_location(
    "fabric_layout", os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "layout.py"))
layout = importlib.util.module_from_spec(_spec)
_wc_spec = importlib.util.spec_from_file_location(
    "fabric_workingcopy", os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "workingcopy.py"))
workingcopy = importlib.util.module_from_spec(_wc_spec)
_spec.loader.exec_module(layout)
_wc_spec.loader.exec_module(workingcopy)


FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.S)


PAYLOAD_DIRS = frozenset({"skills", "commands"})


# sibling_working_copies moved to workingcopy.py (2026-09-18): the
# assembler needs the same reach for the hygiene lists.
sibling_working_copies = workingcopy.sibling_working_copies


def _git():
    """tools/fabric/git.py (ADR-040 §5 rule 6), loaded by path: lint runs
    as a script and as a module the tests load under another name."""
    spec = importlib.util.spec_from_file_location("fabric_git", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "git.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _tracked(root: str) -> list[str]:
    r = _git().run(root, "ls-files", "-z", check=False, timeout=60)
    return [f for f in r.stdout.split("\0") if f] if r.returncode == 0 else []
