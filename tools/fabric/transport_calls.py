#!/usr/bin/env python3
"""tools/fabric/transport_calls.py — what agent-fabric ADR-067 forbids outside tools/fabric/gzcoord/transport/, as one
predicate (message-transport in policies/mechanisms.json). Delivery has one owner: the inbox and the sender take a transport
from its factory and name neither the relay nor the second carrier. Two findings, anywhere else in the fabric's Python:

- **relay**: a call to `api` (bare, or `x.api`, but not `gh.api`) that is a call of the relay's HTTP client: an argument holds
  a path that starts `/api/`, or the call names a `relay_url`.
- **carrier**: an import of the carrier's adapter (`from .carrier import adapter`, `from gzcoord.carrier.adapter import …`,
  `import gzcoord.carrier.adapter`).

A static reader cannot see where a function came from, so this over-reports, by design: a module that does either is judged
until `policies/transport-calls.json` names it with the reason it is allowed. A listed module is admitted whole. The relay
client's own module and the carrier's adapter define the calls and are not judged for what they define. An entry that admits
nothing, or names a file that is not tracked, is a finding, so a gap's entry leaves the policy with its fix.

    tools/fabric/transport_calls.py [<root>]     findings, one per line, on the tracked tree; exit 1 when there are any"""
from __future__ import annotations

import ast
import json
import os
import subprocess
import sys

POLICY = "policies/transport-calls.json"
OWNER = "tools/fabric/gzcoord/transport/"
# The modules that define the calls: judged for nothing, so the policy need not name them.
DEFINING = frozenset({"tools/fabric/gzcoord/inbox_parts/relay.py", "tools/fabric/gzcoord/carrier/adapter.py"})
PATH_PREFIX = "/api/"


def judged_path(rel: str) -> bool:
    """The fabric's own Python, the transport package and the tests aside: a fixture plays the relay on purpose."""
    return rel.endswith(".py") and not rel.startswith(("tests/", OWNER)) and rel not in DEFINING


def parse_calls(text: str) -> dict[str, str]:
    """{module path: why it is allowed} from the policy's text; ValueError when it is not JSON. An entry that is not a string
    pair, or whose reason is empty, admits nothing."""
    doc = json.loads(text)
    calls = doc.get("calls") if isinstance(doc, dict) else None
    return {k: v for k, v in calls.items() if isinstance(k, str) and isinstance(v, str) and v.strip()} \
        if isinstance(calls, dict) else {}


def _name(fn: ast.AST) -> str:
    return fn.attr if isinstance(fn, ast.Attribute) else fn.id if isinstance(fn, ast.Name) else ""


def _owner(fn: ast.AST) -> str:
    return _name(fn.value) if isinstance(fn, ast.Attribute) else ""


def _names_relay_path(node: ast.AST) -> bool:
    """A string constant that starts with `/api/` anywhere in the expression: a literal, an f-string's first part, the left
    side of a concatenation."""
    return any(isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value.startswith(PATH_PREFIX)
               for n in ast.walk(node))


def _relay_call(call: ast.Call) -> bool:
    if _name(call.func) != "api" or _owner(call.func) == "gh":
        return False
    return any(_names_relay_path(a) for a in call.args) \
        or any(k.arg == "relay_url" or _names_relay_path(k.value) for k in call.keywords)


def _carrier_import(node: ast.AST) -> bool:
    if isinstance(node, ast.ImportFrom):
        mod = node.module or ""
        if mod.endswith("carrier.adapter") or (node.level > 0 and mod == "adapter"):
            return True
        return (mod in ("", "carrier") or mod.endswith(".carrier")) and any(a.name == "adapter" for a in node.names)
    if isinstance(node, ast.Import):
        return any(a.name.endswith("carrier.adapter") for a in node.names)
    return False


def scan(rel: str, text: str, allowed: dict[str, str]) -> list[str]:
    """Findings for one Python module, each `<rel>:<line>: <what> (ADR-067)`."""
    if rel in allowed or not judged_path(rel):
        return []
    try:
        tree = ast.parse(text, filename=rel)
    except SyntaxError:
        return []   # ruff refuses it in CI; a commit of a half-merged module is not this rule's to stop
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _relay_call(node):
            what = "a call of the relay's api()"
        elif _carrier_import(node):
            what = "an import of the carrier's adapter"
        else:
            continue
        out.append((node.lineno, f"{rel}:{node.lineno}: {what} outside {OWNER} — take a transport from "
                                 f"gzcoord.transport.open_transport, or name the module and why in {POLICY} (ADR-067)"))
    return [line for _, line in sorted(out)]


def policy_findings(allowed: dict[str, str], present: set[str]) -> list[str]:
    """An entry for a module that is gone would admit the next file at that path unread."""
    return [f"{POLICY}: {m} is listed but is not a tracked file" for m in sorted(allowed) if m not in present]


def tree_findings(root: str, tracked: list[str]) -> list[str]:
    """Every finding over `tracked` (paths relative to `root`): the undeclared sites, and the entries that admit nothing."""
    try:
        with open(os.path.join(root, POLICY), encoding="utf-8") as fh:
            allowed = parse_calls(fh.read())
    except FileNotFoundError:
        allowed = {}
    except (OSError, ValueError) as exc:
        # Said once, not as one finding per module the list would have admitted.
        return [f"{POLICY}: cannot be read as JSON ({exc.__class__.__name__}); ADR-067 is not judged"]
    present = set(tracked)
    out = policy_findings(allowed, present)
    out += [f"{POLICY}: {m} admits nothing — the transport package and the defining modules are not judged; remove the entry"
            for m in sorted(allowed) if m in present and not judged_path(m)]
    for rel in sorted(r for r in tracked if judged_path(r)):
        try:
            with open(os.path.join(root, rel), encoding="utf-8") as fh:
                text = fh.read()
        except FileNotFoundError:
            continue   # tracked and deleted in the work tree: the index is judged by the commit hook
        except (OSError, UnicodeDecodeError) as exc:
            out.append(f"{rel}: cannot be read as UTF-8 ({exc.__class__.__name__}); ADR-067 is not judged")
            continue
        out += scan(rel, text, allowed)
        if rel in allowed and not scan(rel, text, {}):
            out.append(f"{POLICY}: {rel} admits nothing — the module no longer calls the relay or imports the adapter; "
                       "remove the entry")
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
        print(f"transport_calls: cannot list {root}'s tracked files ({exc.__class__.__name__}); ADR-067 is not judged",
              file=sys.stderr)
        return 2
    for line in found:
        print(line)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
