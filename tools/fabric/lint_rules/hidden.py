"""tools/fabric/lint_rules/hidden.py — hidden Unicode in text an agent reads (j305).
A character the reader does not see but the model reads can carry an instruction, or change what a reviewer believes was
read. tools/fabric/hidden_unicode.py is the definition (classes and allowances); tools/fabric/agent_text.py says which
files are judged, and the pre-commit hook asks the same two. A part of tools/fabric/lint.py, the entry point."""
from __future__ import annotations

import importlib.util
import os

from .base import _tracked, layout

_FABRIC = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))


def _load(name: str):
    # By path, as lint loads every module it trusts: a directory on sys.path would let a fixture fabric answer for it.
    spec = importlib.util.spec_from_file_location(f"fabric_{name}", os.path.join(_FABRIC, f"{name}.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


hidden_unicode = _load("hidden_unicode")
agent_text = _load("agent_text")


def _file_findings(root: str, label: str, itself: bool) -> list[str]:
    out: list[str] = []
    for path in (p for p in _tracked(root) if agent_text.is_agent_text(p, itself=itself)):
        try:
            # newline="" keeps a CR a CR: universal newlines would turn it into the LF the scanner allows.
            with open(os.path.join(root, path), encoding="utf-8", newline="") as fh:
                text = fh.read()
        except FileNotFoundError:
            continue   # tracked and deleted in the work tree: the index is judged by the commit hook
        except (OSError, UnicodeDecodeError) as exc:
            out.append(f"{label}{path}: cannot be read as UTF-8 ({exc.__class__.__name__}); hidden Unicode is not judged")
            continue
        out += [f"{label}{path}:{f.line}:{f.column}: U+{f.codepoint:04X} {f.name} ({f.kind}): hidden Unicode in text an "
                "agent reads (tools/fabric/hidden_unicode.py)" for f in hidden_unicode.scan(text)]
    return out


def hidden_unicode_findings(root: str) -> list[str]:
    """The fabric's tracked agent text, then each linted working copy's tracked .agent-fabric/ files labelled `<pid>:`."""
    out = _file_findings(root, "", True)
    for pid, path in sorted(layout.explicit_working_copies().items()):
        if pid != layout.FABRIC_PROJECT_ID and os.path.realpath(path) != os.path.realpath(root):
            out += _file_findings(path, f"{pid}:", False)
    return out
