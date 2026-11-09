#!/usr/bin/env python3
"""tools/fabric/work_writes.py — the work lifecycle has one owner, tools/fabric/work/ (agent-fabric ADR-037 rule 14, ADR-067 rule 2,
j101); this is the predicate for everything else. Wiring it into lint and the pre-commit hook, the exceptions file it reads
(policies/work-writes.json) and the catalogue entry are the control plane's.

A job's state is moved by a row of rule 14's table and a pool claim by one of its pool rows, and the owner is the only code that
writes either: the rows' needs are checked there, when the transition is made. Anywhere else, a write of
    X["state"] = …          X["claimed"] = …          (an assignment, an augmented one, a delete)
    X.update(state=…)       X.update({"state": …})    X.setdefault("state", …)     (and the same for "claimed")
    {"state": "queued", …}  {"claimed": "open"}       (a dict built with the key)
is a finding when the value is a job's or a pool job's state: a string that names one (queued, active, paused, blocked,
delivered, done, dropped; open, claimed, closed), and for the first two kinds of write also anything the checker cannot read (a
name, a call). A string that names another kind of state ("working", "cleared") is not, and a dict that copies a state it was
given (`{"state": row["state"]}`) writes nothing new.

It is a static reader: a key held in a variable, or a state written through a helper in another module, is not seen, which is
the usual under-report. The writes that look like this and are not a job's (a plan's step, a carrier's record) are named, with
the reason, in the exceptions file; an entry that admits nothing is a finding, so an exception leaves the list when its module
stops writing. Tests are not judged: a fixture forces a state on purpose.

Stdlib only; runnable as `python3 tools/fabric/work_writes.py [--root DIR] [--policy FILE]`: prints one finding per line, exit 1 when
there is any, 2 when the policy or a module cannot be read."""
from __future__ import annotations

import argparse
import ast
import json
import os
import subprocess
import sys

POLICY = "policies/work-writes.json"
OWNER_DIR = "tools/fabric/work/"
KEYS = frozenset({"state", "claimed"})
# What a literal must be to be a job's or a pool job's state; the table's own lists (work/table.py), repeated so that this file
# reads nothing it judges. tests/test_work_writes.py holds the two together.
STATES = frozenset({"queued", "active", "paused", "blocked", "delivered", "done", "dropped", "open", "claimed", "closed"})


def parse_allowed(text: str) -> dict[str, str]:
    """{module path: why it is admitted} from the policy's text; ValueError when it is not JSON. An entry that is not a string pair
    admits nothing."""
    doc = json.loads(text)
    writes = doc.get("writes") if isinstance(doc, dict) else None
    return {k: v for k, v in writes.items() if isinstance(k, str) and isinstance(v, str)} if isinstance(writes, dict) else {}


def _key(node: ast.AST) -> str | None:
    return node.value if isinstance(node, ast.Constant) and node.value in KEYS else None


def _named_state(value: ast.AST | None) -> bool:
    return isinstance(value, ast.Constant) and isinstance(value.value, str) and value.value in STATES


def _could_be_a_state(value: ast.AST | None, key: str = "state") -> bool:
    """A string that names a state, or anything that is not a literal (a name, a call, an expression): unknown is a finding. A pool
    job's `claimed` is the claim itself, whatever is put there, a null that reopens it included."""
    return key == "claimed" or value is None or _named_state(value) or not isinstance(value, ast.Constant)


def sites(text: str, rel: str = "<module>") -> list[tuple[int, str]]:
    """[(line, what)] of every write of a state key that could be a job's; [] for a module that does not parse (ruff refuses it in
    CI, and a half-merged module is not this rule's to stop)."""
    try:
        tree = ast.parse(text, filename=rel)
    except SyntaxError:
        return []
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for t in targets:
                key = _key(t.slice) if isinstance(t, ast.Subscript) else None
                if key and _could_be_a_state(None if isinstance(node, ast.AugAssign) else getattr(node, "value", None), key):
                    found.append((node.lineno, f'a write of ["{key}"]'))
        elif isinstance(node, ast.Delete):
            found += [(node.lineno, f'a delete of ["{_key(t.slice)}"]') for t in node.targets if isinstance(t, ast.Subscript) and _key(t.slice)]
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "setdefault" and node.args and _key(node.args[0]) \
                    and _could_be_a_state(node.args[1] if len(node.args) > 1 else None, _key(node.args[0])):
                found.append((node.lineno, f'setdefault("{_key(node.args[0])}")'))
            if node.func.attr == "update":
                found += [(node.lineno, f"update({kw.arg}=…)") for kw in node.keywords if kw.arg in KEYS and _could_be_a_state(kw.value, kw.arg)]
                for arg in node.args:
                    if isinstance(arg, ast.Dict):
                        found += [(node.lineno, f'update({{"{_key(k)}": …}})') for k, v in zip(arg.keys, arg.values)
                                  if k is not None and _key(k) and _could_be_a_state(v, _key(k))]
        elif isinstance(node, ast.Dict):
            found += [(node.lineno, f'a dict with "{_key(k)}"') for k, v in zip(node.keys, node.values)
                      if k is not None and _key(k) and (_named_state(v) or _key(k) == "claimed")]
    # One finding for a line: `update({"state": …})` is one write, whichever way it is read.
    first: dict[int, str] = {}
    for line, what in sorted(found):
        first.setdefault(line, what)
    return sorted(first.items())


def scan(rel: str, text: str, allowed: dict[str, str]) -> list[str]:
    """Findings for one module, each `<rel>:<line>: <what> …`."""
    if rel.startswith(OWNER_DIR) or rel in allowed:
        return []
    return [f"{rel}:{line}: {what} outside {OWNER_DIR} — a job's state and a pool claim change only through the work module "
            f"(work.transition, work.create, work.claims), or name the module and why its key is not one in {POLICY}"
            for line, what in sites(text, rel)]


def policy_findings(allowed: dict[str, str], present: set[str]) -> list[str]:
    """An entry for a module that is gone would admit the next file at that path unread; one without a reason admits on no stated
    ground."""
    out = [f"{POLICY}: {m} is listed but is not a tracked file" for m in sorted(allowed) if m not in present]
    out += [f"{POLICY}: {m} has no reason" for m, why in sorted(allowed.items()) if not why.strip()]
    return out


def judged_path(rel: str) -> bool:
    """The fabric's own Python, the tests and the owner aside."""
    return rel.endswith(".py") and not rel.startswith("tests/") and not rel.startswith(OWNER_DIR)


def tree_findings(root: str, tracked: list[str], policy_text: str | None) -> list[str]:
    """Every finding over `tracked` (paths relative to root). `policy_text` None: no policy file, nothing admitted."""
    try:
        allowed = parse_allowed(policy_text) if policy_text is not None else {}
    except ValueError as exc:
        # Said once, not as one finding per module the list would have admitted.
        return [f"{POLICY}: cannot be read as JSON ({exc.__class__.__name__}); work writes are not judged"]
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
            out.append(f"{rel}: cannot be read as UTF-8 ({exc.__class__.__name__}); work writes are not judged")
            continue
        out += scan(rel, text, allowed)
        if rel in allowed and not sites(text, rel):
            out.append(f"{POLICY}: {rel} admits nothing — the module no longer writes a state key; remove the entry")
    return out


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Findings: a job's state or a pool claim written outside tools/fabric/work/.")
    ap.add_argument("--root", default=os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__)))))
    ap.add_argument("--policy", help=f"the exceptions (default <root>/{POLICY}; absent admits nothing)")
    args = ap.parse_args(argv)
    ls = subprocess.run(["git", "-C", args.root, "ls-files", "-z", "--", "*.py"], capture_output=True, timeout=60,
                        stdin=subprocess.DEVNULL, check=False)
    if ls.returncode != 0:
        print(f"work_writes: git ls-files failed in {args.root}", file=sys.stderr)
        return 2
    tracked = [p for p in os.fsdecode(ls.stdout).split("\0") if p]
    path = args.policy or os.path.join(args.root, POLICY)
    try:
        with open(path, encoding="utf-8") as fh:
            policy_text: str | None = fh.read()
    except FileNotFoundError:
        policy_text = None
    except (OSError, UnicodeDecodeError) as exc:
        print(f"work_writes: {path}: {exc.__class__.__name__}", file=sys.stderr)
        return 2
    found = tree_findings(args.root, tracked, policy_text)
    for line in found:
        print(line)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
