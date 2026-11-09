#!/usr/bin/env python3
"""tools/fabric/context_reads.py — who may read an agent's binding, as one predicate lint asks (j212).

One owner per cross-cutting mechanism (the owner, 2026-11-08): what an agent is bound to — its role, project and
working copy — is read by `identity.resolve_context`, which answers a frozen `AgentContext` whose `.binding` is
`identity.BindingRecord`. A caller that opens binding.json itself carries its own copy of the file's name, its
validation (not JSON, another login's, another host's) and its defaults, and the copies drift (query.py read a
binding identity would have refused; gzmsg.py read one beside its own whoami). So a module outside
`runtime/identity.py` and `tools/fabric/workingcopy.py` is a finding when it:

- **names the file**: a string that is `binding.json` or ends in `/binding.json` (a path being built), outside a
  docstring; or
- **asks for its path**: references `binding_path`, the identity function that hands out the file's place, to open it.

`read_binding` is not a finding: it is identity's own validated reader (not JSON, another login's, another host's
refused), the one `resolve_context` is built on. Its callers get a raw dictionary and say their own defaults; moving
them onto the typed record is the next step, not this rule's. `update_binding` and `write_binding` are the state
layer's writers (ADR-003 rule 1, tools/fabric/state_writes.py), which read under the agent lock to write.

A finding is cleared by moving the caller onto the context, or by an entry in `policies/context-reads.json` that
says why this module reads the file itself. An entry admits the whole module, so it names a reason, not a promise.
Like state_writes.py this is syntax, not data flow: a path handed to a function as a parameter (`whoami()["binding"]`)
is not seen, only the module that built it.

Tests are not judged: a fixture writes a binding on purpose."""
from __future__ import annotations

import ast
import json
import re
import warnings

POLICY = "policies/context-reads.json"
HOMES = frozenset({"runtime/identity.py", "tools/fabric/workingcopy.py"})
ACCESSORS = frozenset({"binding_path"})
_FILE = re.compile(r"(?:^|/)binding\.json$")


def parse_readers(text: str) -> dict[str, str]:
    """{module path: why it reads the binding itself} from the policy's text; ValueError when it is not JSON. An entry
    that is not a string pair admits nothing."""
    doc = json.loads(text)
    readers = doc.get("readers") if isinstance(doc, dict) else None
    return {k: v for k, v in readers.items() if isinstance(k, str) and isinstance(v, str) and v.strip()} \
        if isinstance(readers, dict) else {}


def judged_path(rel: str) -> bool:
    return rel.endswith(".py") and not rel.startswith("tests/") and rel not in HOMES


def _docstrings(tree: ast.Module) -> set[int]:
    """ids of the string nodes that are a module's, class's or function's docstring."""
    out: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                out.add(id(body[0].value))
    return out


def raw_findings(rel: str, text: str) -> list[str]:
    """Every read in a module, admitted or not, each `<rel>:<line>: <what>`; [] for a path that is not judged or a
    module that does not parse (ruff refuses it in CI)."""
    if not judged_path(rel):
        return []
    try:
        with warnings.catch_warnings():
            # A scanned file's own invalid escape is its own lint's to report, not noise in this one's output.
            warnings.simplefilter("ignore", SyntaxWarning)
            tree = ast.parse(text, filename=rel)
    except SyntaxError:
        return []
    docs = _docstrings(tree)
    out: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docs \
                and _FILE.search(node.value):
            out.append((node.lineno, "names binding.json"))
        elif isinstance(node, ast.Attribute) and node.attr in ACCESSORS:
            out.append((node.lineno, f"calls identity.{node.attr}, the file's place"))
        elif isinstance(node, ast.Name) and node.id in ACCESSORS:
            out.append((node.lineno, f"uses {node.id}"))
    return [f"{rel}:{line}: {what}" for line, what in sorted(set(out))]


def scan(rel: str, text: str, readers: dict[str, str]) -> list[str]:
    """Findings for one module that the policy does not admit, each `<rel>:<line>: <what> — read the binding through
    identity.resolve_context(), or name the module and why in policies/context-reads.json`."""
    if rel in readers:
        return []
    return [f"{f} — read the binding through identity.resolve_context().binding, or name the module and why in "
            f"{POLICY}" for f in raw_findings(rel, text)]


def policy_findings(readers: dict[str, str], present: set[str]) -> list[str]:
    """An entry for a module that is gone would admit the next file at that path unread; one for a home admits nothing."""
    out = [f"{POLICY}: {m} is listed as a binding reader but is not a tracked file" for m in sorted(readers)
           if m not in present]
    out += [f"{POLICY}: {m} is identity's own and needs no entry" for m in sorted(readers) if m in HOMES]
    return out
