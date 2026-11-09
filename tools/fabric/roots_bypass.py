#!/usr/bin/env python3
"""tools/fabric/roots_bypass.py — what agent-fabric ADR-045 §5 rule 1 forbids in the engine, as one predicate: the engine
reads instance data only through tools/fabric/roots.py. Three findings in the fabric's own Python (tools/, runtime/, the
Python commands in bin/; tests and fixtures aside), each a way of finding a tree without asking roots:

- **env**: a read of AGENT_FABRIC_ROOT or AGENT_FABRIC_OPERATOR — `.get("…")`, `.pop("…")`, `os.getenv("…")`, `x["…"]`,
  `"…" in x`. Writing the variable (an export into a child's environment, a key of an env dict) is not a read.
- **fallback**: a path joined onto `projects`, `agent-fabric` by hand (`os.path.join(home, "projects", "agent-fabric")`,
  `Path(...)`, an f-string `{home}/projects/agent-fabric`): the account's clone has roots.account_clone, and the
  environment-or-clone choice roots.checkout_root.
- **instance**: an instance-data path joined onto a root the module found itself: a join whose argument is a string that
  spells one (`os.path.join(root, "policies/x.json")`), or a name bound at module level to such a string and joined
  (`POLICY = "policies/x.json"` … `os.path.join(root, POLICY)`). tests/test_roots_seam.py judges the other spelling, a
  join of separate components.

A static reader cannot tell a workspace path or a repository-relative name handed to git from an instance path, so this
over-reports by design: a module is judged until `tools/fabric/roots_bypass.json` names it with the reason it is allowed.
A listed module is admitted whole. roots.py defines the lookups and is not judged. An entry that admits nothing, or names a
file that is not tracked, is a finding, so a gap's entry leaves the list with its fix.

    tools/fabric/roots_bypass.py [<root>]     findings, one per line, on the tracked tree; exit 1 when there are any"""
from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
import warnings

POLICY = "tools/fabric/roots_bypass.json"
DEFINING = frozenset({"tools/fabric/roots.py"})
ENV_NAMES = frozenset({"AGENT_FABRIC_ROOT", "AGENT_FABRIC_OPERATOR"})
JOINS = frozenset({"join", "joinpath", "Path", "PurePath", "PurePosixPath"})
# Instance data (roots.py's list) spelled as one root-relative string.
INSTANCE = re.compile(
    r"^(policies/[^/]+\.json|identities/(roles|keys|personas)(/|$)|identities/recovery\.asc$|projects/(registry|clients)\.json$|"
    r"projects/[^/]+/integration(/|$)|runtime/hosts/registry\.json$|routing/(profiles\.json|policies(/|$))|"
    r"memory/.|docs/(adr|live-checks)(/|$))")
# An f-string that BEGINS with a placeholder: `~/projects/agent-fabric/…` inside a message or a command handed to an account's
# shell names a place for a person or that shell, not a path this process opens.
SPELLED_FALLBACK = re.compile(r"^\{\}/projects/agent-fabric(/|$)")
PYTHON_SHEBANG = re.compile(rb"^#!.*\bpython|^#!.*fabric-python")


def judged_path(rel: str) -> bool:
    """The fabric's own Python, the tests aside (a fixture builds the trees on purpose) and roots.py itself."""
    if rel in DEFINING or rel.startswith("tests/") or "/tests/" in rel or "/testdata/" in rel:
        return False
    return rel.endswith(".py") and rel.startswith(("tools/", "runtime/", "communication/gzcoord/scripts/")) \
        or (rel.startswith("bin/") and rel.count("/") == 1)


def is_python_command(rel: str, head: bytes) -> bool:
    """bin/ holds shell shims and Python commands; only the latter is read."""
    return rel.endswith(".py") or bool(PYTHON_SHEBANG.match(head))


def parse_modules(text: str) -> dict[str, str]:
    """{module path: why it is allowed}; ValueError when the text is not JSON. An entry that is not a string pair, or whose
    reason is empty, admits nothing."""
    doc = json.loads(text)
    mods = doc.get("modules") if isinstance(doc, dict) else None
    return {k: v for k, v in mods.items() if isinstance(k, str) and isinstance(v, str) and v.strip()} \
        if isinstance(mods, dict) else {}


def _call_name(fn: ast.AST) -> str:
    return fn.attr if isinstance(fn, ast.Attribute) else fn.id if isinstance(fn, ast.Name) else ""


def _const_str(node: ast.AST) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _env_name(node: ast.AST) -> str | None:
    s = _const_str(node)
    return s if s in ENV_NAMES else None


def _module_constants(tree: ast.Module) -> dict[str, str]:
    """Names bound once at module level to a string that spells instance data."""
    out: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            value = _const_str(node.value)
            if value is not None and INSTANCE.match(value):
                out[node.targets[0].id] = value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value is not None:
            value = _const_str(node.value)
            if value is not None and INSTANCE.match(value):
                out[node.target.id] = value
    return out


def _fstring_text(node: ast.JoinedStr) -> str:
    return "".join(v.value if isinstance(v, ast.Constant) and isinstance(v.value, str) else "{}" for v in node.values)


def scan(rel: str, text: str) -> list[str]:
    """Findings for one Python module, each `<rel>:<line>: <what> (ADR-045 §5 rule 1)`."""
    if not judged_path(rel):
        return []
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")   # under -W error a module's own invalid escape would read as a syntax error
            tree = ast.parse(text, filename=rel)
    except SyntaxError:
        return []   # ruff refuses it in CI; a commit of a half-merged module is not this rule's to stop
    consts = _module_constants(tree)
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = _call_name(node.func)
            if name in ("get", "pop", "getenv") and node.args and (var := _env_name(node.args[0])):
                found.append((node.lineno, f"a read of {var}"))
            if name in JOINS:
                parts = [_const_str(a) for a in node.args]
                if any(a == "projects" and b == "agent-fabric" for a, b in zip(parts, parts[1:])):
                    found.append((node.lineno, "a hand-built <home>/projects/agent-fabric"))
                for arg in node.args[1:] if name != "Path" else node.args:
                    if (s := _const_str(arg)) is not None and INSTANCE.match(s):
                        found.append((node.lineno, f"{s} joined onto a root found here"))
                    elif isinstance(arg, ast.Name) and arg.id in consts and arg is not node.args[0]:
                        found.append((node.lineno, f"{consts[arg.id]} (via {arg.id}) joined onto a root found here"))
        elif isinstance(node, ast.Subscript) and isinstance(node.ctx, ast.Load) and (var := _env_name(node.slice)):
            found.append((node.lineno, f"a read of {var}"))
        elif isinstance(node, ast.Compare) and any(isinstance(op, (ast.In, ast.NotIn)) for op in node.ops) \
                and (var := _env_name(node.left)):
            found.append((node.lineno, f"a read of {var}"))
        elif isinstance(node, ast.JoinedStr) and SPELLED_FALLBACK.search(_fstring_text(node)):
            found.append((node.lineno, "a hand-built {…}/projects/agent-fabric path"))
    return [f"{rel}:{ln}: {what} — ask tools/fabric/roots.py, or name the module and why in {POLICY} (ADR-045 §5 rule 1)"
            for ln, what in sorted(set(found))]


def policy_findings(allowed: dict[str, str], present: set[str]) -> list[str]:
    """An entry for a module that is gone would admit the next file at that path unread."""
    return [f"{POLICY}: {m} is listed but is not a tracked file" for m in sorted(allowed) if m not in present]


def tree_findings(root: str, tracked: list[str]) -> list[str]:
    """Every finding over `tracked` (paths relative to `root`): the undeclared sites, and the entries that admit nothing."""
    try:
        with open(os.path.join(root, POLICY), encoding="utf-8") as fh:
            allowed = parse_modules(fh.read())
    except FileNotFoundError:
        allowed = {}
    except (OSError, ValueError) as exc:
        # Said once, not as one finding per module the list would have admitted.
        return [f"{POLICY}: cannot be read as JSON ({exc.__class__.__name__}); ADR-045 rule 1 is not judged"]
    present = set(tracked)
    out = policy_findings(allowed, present)
    for rel in sorted(r for r in tracked if judged_path(r)):
        try:
            with open(os.path.join(root, rel), "rb") as fh:
                raw = fh.read()
        except FileNotFoundError:
            continue   # tracked and deleted in the work tree: the index is judged by the commit hook
        except OSError as exc:
            out.append(f"{rel}: cannot be read ({exc.__class__.__name__}); ADR-045 rule 1 is not judged")
            continue
        if not is_python_command(rel, raw[:200]):
            if rel in allowed:
                out.append(f"{POLICY}: {rel} admits nothing — it is not Python; remove the entry")
            continue
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            out.append(f"{rel}: cannot be read as UTF-8 ({exc.__class__.__name__}); ADR-045 rule 1 is not judged")
            continue
        found = scan(rel, text)
        if rel in allowed:
            if not found:
                out.append(f"{POLICY}: {rel} admits nothing — the module no longer bypasses roots; remove the entry")
            continue
        out += found
    out += [f"{POLICY}: {m} admits nothing — roots.py and the tests are not judged; remove the entry"
            for m in sorted(allowed) if m in present and not judged_path(m)]
    return out


def tracked_files(root: str) -> list[str]:
    done = subprocess.run(["git", "-C", root, "ls-files", "-z"], stdin=subprocess.DEVNULL, capture_output=True, timeout=60,
                          check=True)
    return [p for p in done.stdout.decode("utf-8", "surrogateescape").split("\0") if p]


def main(argv: list[str]) -> int:
    root = os.path.abspath(argv[0] if argv else os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", ".."))
    try:
        found = tree_findings(root, tracked_files(root))
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"roots_bypass: cannot list {root}'s tracked files ({exc.__class__.__name__}); ADR-045 rule 1 is not judged",
              file=sys.stderr)
        return 2
    for line in found:
        print(line)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
