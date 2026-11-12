"""tools/fabric/lint_rules/context.py — who may read an agent's binding (j212): a module outside runtime/identity.py and
tools/fabric/workingcopy.py that builds the binding's path or names binding.json is named in tools/fabric/context-reads.json
with its reason, or is a finding; an entry that admits nothing is a finding, so it leaves when its reader moves onto
identity.resolve_context. tools/fabric/context_reads.py is the definition. A part of tools/fabric/lint.py, the entry point."""
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


context_reads = _load("context_reads")


def context_read_findings(root: str) -> list[str]:
    tracked = _tracked(root)
    try:
        with open(os.path.join(root, context_reads.POLICY), encoding="utf-8") as fh:
            readers = context_reads.parse_readers(fh.read())
    except FileNotFoundError:
        readers = {}
    except (OSError, ValueError) as exc:
        return [f"{context_reads.POLICY}: cannot be read as JSON ({exc.__class__.__name__}); the binding's readers are not judged"]
    out = context_reads.policy_findings(readers, set(tracked))
    # Not narrowed by ruff's exclude (base._not_ours): the pre-commit hook judges every path judged_path names, and the two
    # must judge one set, or a vendored module passes one and can satisfy neither once named (#516 F1).
    scanned = {r for r in tracked if context_reads.judged_path(r)}
    for rel in sorted(scanned):
        try:
            with open(os.path.join(root, rel), encoding="utf-8") as fh:
                text = fh.read()
        except FileNotFoundError:
            continue   # tracked and deleted in the work tree
        except (OSError, UnicodeDecodeError) as exc:
            out.append(f"{rel}: cannot be read as UTF-8 ({exc.__class__.__name__}); the binding's readers are not judged")
            continue
        out += context_reads.scan(rel, text, readers)
        if rel in readers and not context_reads.raw_findings(rel, text):
            out.append(f"{context_reads.POLICY}: {rel} admits nothing — the module no longer reads the binding itself; "
                       "remove the entry")
    return out
