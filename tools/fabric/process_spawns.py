#!/usr/bin/env python3
"""tools/fabric/process_spawns.py — process lifetime has one owner, tools/fabric/process.py (the owner's 2026-11-08 ask,
j125); this is the predicate for everything else. Wiring it into lint and
the pre-commit hook, and the allowlist it reads (policies/process-spawns.json), are the control plane's.

A module that starts a command in a session or group of its own, or signals a group, owns a lifetime it does not
test the same way twice: 14 modules did, each with its own answer to "the interrupt landed between Popen and the try",
"the helper called setsid" and "the timeout left the pipe open". Three findings, anywhere outside process.py:

- **signal**: a call to `killpg`, `setsid`, `setpgid` or `setpgrp` (os.killpg, os.setsid, …);
- **spawn**: a call with a `start_new_session` or `process_group` keyword that is not the literal False (Popen, run,
  check_call; a wrapper that forwards **kwargs is not seen — the literal at the call is what is judged).

It is a static reader: `kill = os.killpg` called as `kill(...)` is not seen, which is the usual under-report.

A listed module is admitted whole, every finding in it, with a reason that says why it cannot call process.py
(`policies/process-spawns.json`). An entry that admits nothing is a finding, so an exception leaves the list when its
module moves. process.py is the owner and is not judged. Tests are not judged: a fixture starts a process group on
purpose.

Stdlib only; runnable as `python3 tools/fabric/process_spawns.py [--root DIR] [--policy FILE]`: prints one finding per
line, exit 1 when there is any, 2 when the policy or a module cannot be read."""
from __future__ import annotations

import argparse
import ast
import json
import os
import subprocess
import sys

POLICY = "policies/process-spawns.json"
OWNER = "tools/fabric/process.py"
SIGNALS = frozenset({"killpg", "setsid", "setpgid", "setpgrp"})
SPAWN_KEYWORDS = frozenset({"start_new_session", "process_group"})


def parse_allowed(text: str) -> dict[str, str]:
    """{module path: why it is admitted} from the policy's text; ValueError when it is not JSON. An entry that is not a
    string pair admits nothing."""
    doc = json.loads(text)
    spawns = doc.get("spawns") if isinstance(doc, dict) else None
    return {k: v for k, v in spawns.items() if isinstance(k, str) and isinstance(v, str)} \
        if isinstance(spawns, dict) else {}


def _name(fn: ast.AST) -> str:
    return fn.attr if isinstance(fn, ast.Attribute) else fn.id if isinstance(fn, ast.Name) else ""


def _off(value: ast.AST) -> bool:
    """The literal False (or None): the keyword is spelled and does nothing."""
    return isinstance(value, ast.Constant) and (value.value is False or value.value is None)


def sites(text: str, rel: str = "<module>") -> list[tuple[int, str]]:
    """[(line, what)] of every call that starts or signals a group; [] for a module that does not parse (ruff refuses it
    in CI, and a half-merged module is not this rule's to stop)."""
    try:
        tree = ast.parse(text, filename=rel)
    except SyntaxError:
        return []
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _name(node.func)
        if name in SIGNALS:
            found.append((node.lineno, f"{name}()"))
        for kw in node.keywords:
            if kw.arg in SPAWN_KEYWORDS and not _off(kw.value):
                found.append((node.lineno, f"{kw.arg}= in a call to {name or '<call>'}()"))
    return sorted(found)


def scan(rel: str, text: str, allowed: dict[str, str]) -> list[str]:
    """Findings for one module, each `<rel>:<line>: <what> …`."""
    if rel == OWNER or rel in allowed:
        return []
    return [f"{rel}:{line}: {what} outside {OWNER} — start and end the process through it (process.group, "
            f"run_bounded, popen_group, spawn_service, signal_group), or name the module and why it cannot in {POLICY}"
            for line, what in sites(text, rel)]


def policy_findings(allowed: dict[str, str], present: set[str]) -> list[str]:
    """An entry for a module that is gone would admit the next file at that path unread; one without a reason admits on
    no stated ground."""
    out = [f"{POLICY}: {m} is listed but is not a tracked file" for m in sorted(allowed) if m not in present]
    out += [f"{POLICY}: {m} has no reason" for m, why in sorted(allowed.items()) if not why.strip()]
    return out


def judged_path(rel: str) -> bool:
    """The fabric's own Python, the tests aside."""
    return rel.endswith(".py") and not rel.startswith("tests/") and rel != OWNER


def tree_findings(root: str, tracked: list[str], policy_text: str | None) -> list[str]:
    """Every finding over `tracked` (paths relative to root). `policy_text` None: no policy file, nothing admitted."""
    try:
        allowed = parse_allowed(policy_text) if policy_text is not None else {}
    except ValueError as exc:
        # Said once, not as one finding per module the list would have admitted.
        return [f"{POLICY}: cannot be read as JSON ({exc.__class__.__name__}); process spawns are not judged"]
    out = policy_findings(allowed, set(tracked))
    judged = {r for r in tracked if judged_path(r)}
    out += [f"{POLICY}: {m} admits nothing — that path is not judged (a test, not Python, or the owner); remove the entry"
            for m in sorted(allowed) if m in set(tracked) and m not in judged]
    for rel in sorted(judged):
        try:
            with open(os.path.join(root, rel), encoding="utf-8") as fh:
                text = fh.read()
        except FileNotFoundError:
            continue   # tracked and deleted in the work tree: the index is judged by the commit hook
        except (OSError, UnicodeDecodeError) as exc:
            out.append(f"{rel}: cannot be read as UTF-8 ({exc.__class__.__name__}); process spawns are not judged")
            continue
        out += scan(rel, text, allowed)
        if rel in allowed and not sites(text, rel):
            out.append(f"{POLICY}: {rel} admits nothing — the module no longer starts or signals a group; remove the entry")
    return out


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Findings: a process group started or signalled outside tools/fabric/process.py.")
    ap.add_argument("--root", default=os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__)))))
    ap.add_argument("--policy", help=f"the allowlist (default <root>/{POLICY}; absent admits nothing)")
    args = ap.parse_args(argv)
    ls = subprocess.run(["git", "-C", args.root, "ls-files", "-z", "--", "*.py"], capture_output=True, timeout=60,
                        stdin=subprocess.DEVNULL, check=False)
    if ls.returncode != 0:
        print(f"process_spawns: git ls-files failed in {args.root}", file=sys.stderr)
        return 2
    tracked = [p for p in os.fsdecode(ls.stdout).split("\0") if p]
    path = args.policy or os.path.join(args.root, POLICY)
    try:
        with open(path, encoding="utf-8") as fh:
            policy_text: str | None = fh.read()
    except FileNotFoundError:
        policy_text = None
    except (OSError, UnicodeDecodeError) as exc:
        print(f"process_spawns: {path}: {exc.__class__.__name__}", file=sys.stderr)
        return 2
    found = tree_findings(args.root, tracked, policy_text)
    for line in found:
        print(line)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
