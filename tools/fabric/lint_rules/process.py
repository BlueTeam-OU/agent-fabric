"""tools/fabric/lint_rules/process.py — process lifetime has one owner (agent-fabric ADR-067, j125): a module that starts
or signals a process group outside tools/fabric/process.py is named in policies/process-spawns.json with its reason, or is
a finding; an entry that admits nothing is a finding. tools/fabric/process_spawns.py is the definition, and the
pre-commit hook asks it about the staged modules. A part of tools/fabric/lint.py, the entry point."""
from __future__ import annotations

import importlib.util
import os

from .base import _is_under, _not_ours, _tracked

_FABRIC = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))


def _load(name: str):
    # By path, as lint loads every module it trusts: a directory on sys.path would let a fixture fabric answer for it.
    spec = importlib.util.spec_from_file_location(f"fabric_{name}", os.path.join(_FABRIC, f"{name}.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


process_spawns = _load("process_spawns")


def process_spawn_findings(root: str) -> list[str]:
    not_ours = _not_ours(root)
    tracked = [r for r in _tracked(root) if not _is_under(r, not_ours)]
    try:
        with open(os.path.join(root, process_spawns.POLICY), encoding="utf-8") as fh:
            policy_text: str | None = fh.read()
    except FileNotFoundError:
        policy_text = None   # instance data (ADR-045 rule 2): a stripped engine copy admits nothing and judges all
    except (OSError, UnicodeDecodeError) as exc:
        return [f"{process_spawns.POLICY}: cannot be read ({exc.__class__.__name__}); process spawns are not judged"]
    return process_spawns.tree_findings(root, tracked, policy_text)
