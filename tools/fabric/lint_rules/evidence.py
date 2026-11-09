"""tools/fabric/lint_rules/evidence.py — GitHub's list caps have one owner (agent-fabric ADR-067, j119): a module under
tools/fabric/ that holds a cap literal or reads a pull request's files or commits outside github/evidence.py and
common.py is a finding unless policies/evidence-caps.json names it with its reason; an entry that admits nothing is a
finding. tools/fabric/evidence_caps.py is the definition, and the pre-commit hook asks it about the staged modules. A part
of tools/fabric/lint.py, the entry point."""
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


evidence_caps = _load("evidence_caps")
POLICY = evidence_caps.POLICY


def evidence_cap_findings(root: str) -> list[str]:
    try:
        with open(os.path.join(root, POLICY), encoding="utf-8") as fh:
            admitted = evidence_caps.parse_modules(fh.read())
    except FileNotFoundError:
        admitted = {}       # instance data (ADR-045 rule 2): a stripped engine copy still judges every module
    except (OSError, ValueError) as exc:
        return [f"{POLICY}: cannot be read as JSON ({exc.__class__.__name__}); GitHub's list caps are not judged"]
    tracked = set(_tracked(root))
    not_ours = _not_ours(root)
    out = evidence_caps.policy_findings(admitted, tracked)
    for rel in sorted(r for r in tracked if evidence_caps.judged_path(r) and not _is_under(r, not_ours)):
        try:
            with open(os.path.join(root, rel), encoding="utf-8") as fh:
                text = fh.read()
        except FileNotFoundError:
            continue   # tracked and deleted in the work tree: the index is judged by the commit hook
        except (OSError, UnicodeDecodeError) as exc:
            out.append(f"{rel}: cannot be read as UTF-8 ({exc.__class__.__name__}); GitHub's list caps are not judged")
            continue
        found = evidence_caps.scan(rel, text)
        if rel in admitted:
            if not found:
                out.append(f"{POLICY}: {rel} admits nothing — the module no longer holds a cap or reads the list; "
                           "remove the entry")
            continue
        out += [f"{f} (ADR-067 rule 1; or name the module and why in {POLICY})" for f in found]
    return out
