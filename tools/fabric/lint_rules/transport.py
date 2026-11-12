"""tools/fabric/lint_rules/transport.py — message delivery has one owner (agent-fabric ADR-067, message-transport): a module
that calls the relay's api() or imports the carrier's adapter outside tools/fabric/gzcoord/transport/ is named in
tools/fabric/transport-calls.json with its reason, or is a finding; an entry that admits nothing is a finding.
tools/fabric/transport_calls.py is the definition and reads the policy itself; the pre-commit hook asks it about the staged
modules. A part of tools/fabric/lint.py, the entry point."""
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


transport_calls = _load("transport_calls")


def transport_call_findings(root: str) -> list[str]:
    # Not narrowed by ruff's exclude (base._not_ours): the pre-commit hook judges every path judged_path names, and the two
    # must judge one set (#516 F1).
    return transport_calls.tree_findings(root, _tracked(root))
