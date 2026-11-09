"""tools/fabric/lint_rules/state.py — agent-fabric ADR-003 rule 1 over the tracked tree (j535): a module that resolves
the per-agent state directory and writes a file, or copies the resolution, is named in policies/state-writers.json or is
a finding; a lock file opened off its terms is a finding in any module the list does not name; an entry that admits nothing is a finding, so a
gap's entry leaves with its fix. tools/fabric/state_writes.py is the definition,
and the pre-commit hook asks it about the staged modules. A part of tools/fabric/lint.py, the entry point."""
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


state_writes = _load("state_writes")


def state_write_findings(root: str) -> list[str]:
    tracked = _tracked(root)
    out: list[str] = []
    try:
        with open(os.path.join(root, state_writes.POLICY), encoding="utf-8") as fh:
            writers = state_writes.parse_writers(fh.read())
    except FileNotFoundError:
        writers = {}
    except (OSError, ValueError) as exc:
        # Said once, not as one finding per module the list would have admitted.
        return [f"{state_writes.POLICY}: cannot be read as JSON ({exc.__class__.__name__}); ADR-003 rule 1 is not judged"]
    out += state_writes.policy_findings(writers, set(tracked))
    # Not narrowed by ruff's exclude (base._not_ours): the pre-commit hook judges every path judged_path names, and the two
    # must judge one set, or a vendored module passes one and can satisfy neither once named (#516 F1).
    scanned = {r for r in tracked if state_writes.judged_path(r)}
    out += [f"{state_writes.POLICY}: {m} admits nothing — rule 1 does not judge that path (a test, or not Python); "
            "remove the entry" for m in sorted(writers) if m in set(tracked) and m not in scanned]
    for rel in sorted(scanned):
        try:
            with open(os.path.join(root, rel), encoding="utf-8") as fh:
                text = fh.read()
        except FileNotFoundError:
            continue   # tracked and deleted in the work tree: the index is judged by the commit hook
        except (OSError, UnicodeDecodeError) as exc:
            out.append(f"{rel}: cannot be read as UTF-8 ({exc.__class__.__name__}); ADR-003 rule 1 is not judged")
            continue
        out += state_writes.scan(rel, text, writers)
        if rel in writers and not state_writes.scan(rel, text, {}):
            out.append(f"{state_writes.POLICY}: {rel} admits nothing — the module no longer resolves and writes, or its "
                       "gap closed; remove the entry")
    return out
