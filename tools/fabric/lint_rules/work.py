"""tools/fabric/lint_rules/work.py — the work lifecycle has one owner (agent-fabric ADR-037 rule 14, ADR-067, j101): a module
that writes a job's state or a pool claim outside tools/fabric/work/ is named in tools/fabric/work-writes.json with its reason, or
is a finding; an entry that admits nothing is a finding. tools/fabric/work_writes.py is the definition, and the pre-commit hook
asks it about the staged modules. A part of tools/fabric/lint.py, the entry point."""
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


work_writes = _load("work_writes")


def work_write_findings(root: str) -> list[str]:
    # Not narrowed by ruff's exclude (base._not_ours): the pre-commit hook judges every path judged_path names, and the two
    # must judge one set (#516 F1).
    tracked = _tracked(root)
    try:
        with open(os.path.join(root, work_writes.POLICY), encoding="utf-8") as fh:
            policy_text: str | None = fh.read()
    except FileNotFoundError:
        policy_text = None   # a tree without the engine's list (a fixture): admits nothing and judges all
    except (OSError, UnicodeDecodeError) as exc:
        return [f"{work_writes.POLICY}: cannot be read ({exc.__class__.__name__}); work writes are not judged"]
    return work_writes.tree_findings(root, tracked, policy_text)
