"""tools/fabric/lint_rules/roots.py — the engine finds a tree and reads instance data only through tools/fabric/roots.py
(agent-fabric ADR-045 §5 rule 1, j222): a module that reads AGENT_FABRIC_ROOT/AGENT_FABRIC_OPERATOR, builds
<home>/projects/agent-fabric by hand, or joins an instance-data path onto a root it found is a finding unless
tools/fabric/roots_bypass.json names it with its reason. tools/fabric/roots_bypass.py is the definition. A part of
tools/fabric/lint.py, the entry point."""
from __future__ import annotations

import importlib.util
import os

from .base import _tracked

_FABRIC = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))


def _load(name: str):
    # By path, as lint loads every module it trusts: a directory on sys.path would let a fixture fabric answer for it.
    spec = importlib.util.spec_from_file_location(f"fabric_{name}", os.path.join(_FABRIC, f"{name}.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


roots_bypass = _load("roots_bypass")


def roots_bypass_findings(root: str) -> list[str]:
    # The same predicate the pre-commit hook asks (roots_bypass.judged_path); not narrowed by ruff's exclude (#516 F1).
    return roots_bypass.tree_findings(root, list(_tracked(root)))
