#!/usr/bin/env python3
"""runtime/claude-code/hooks/memory-write-check.py: a session writing one
of its own drain-bound memories is told what the drain would do with it;
everything else is silent, and nothing ever blocks."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOK = os.path.join(ROOT, "runtime", "claude-code", "hooks", "memory-write-check.py")


def memory(dirpath: str, name: str, description: str, meta: str, body: str) -> str:
    path = os.path.join(dirpath, f"{name}.md")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(f'---\nname: {name}\ndescription: "{description}"\nmetadata:\n  type: project\n{meta}---\n{body}\n')
    return path


def run(path: str, raw: str | None = None) -> tuple[int, str]:
    data = raw if raw is not None else json.dumps({"tool_name": "Write", "tool_input": {"file_path": path}})
    p = subprocess.run([sys.executable, HOOK], input=data, capture_output=True, text=True)
    if not p.stdout.strip():
        return p.returncode, ""
    doc = json.loads(p.stdout)
    assert doc["hookSpecificOutput"]["hookEventName"] == "PostToolUse", doc
    return p.returncode, doc["hookSpecificOutput"]["additionalContext"]


def main() -> int:
    fails = 0
    with tempfile.TemporaryDirectory() as tmp:
        mem = os.path.join(tmp, ".claude", "projects", "slug", "memory")
        os.makedirs(mem)
        cases = [
            ("private: no roles_class", memory(mem, "p", "a note", "", "body"), None),
            ("clean: the drain takes it", memory(mem, "g", "a fact", "  roles_class: solution\n", "body"), None),
            ("an unknown class", memory(mem, "b", "x", "  roles_class: notaclass\n", "body"), "is not a claim class"),
            ("a hand-authored class", memory(mem, "h", "x", "  roles_class: charter\n", "body"), "hand-authored"),
            ("shared_with naming no role", memory(mem, "s", "x", "  roles_class: solution\n  shared_with: Web Dev!\n", "body"),
             "not role slugs"),
            ("over the slice budget", memory(mem, "big", "big", "  roles_class: threads\n", "word " * 2000), "slice budget"),
            ("a workflow memory has the larger budget", memory(mem, "wf", "wf", "  roles_class: workflow\n", "word " * 2000), None),
            ("another language, no rendering", memory(mem, "ru", "факт по-русски", "  roles_class: domain\n",
                                                     "Это факт на русском языке без перевода."), "'## English' rendering"),
            ("a credential by shape", memory(mem, "c", "c", "  roles_class: solution\n", "token ghp_" + "A" * 36),
             "by shape"),
        ]
        for label, path, expect in cases:
            rc, out = run(path)
            good = rc == 0 and ((not out) if expect is None else (expect in out))
            if expect and "ghp_" in out:
                good = False                     # never the credential itself
            print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {out!r}"))
            fails += not good
        with open(os.path.join(mem, "MEMORY.md"), "w", encoding="utf-8") as fh:
            fh.write("- [x](x.md)\n")
        for label, path, raw in (("MEMORY.md is the index, not a memory", os.path.join(mem, "MEMORY.md"), None),
                                 ("a path outside the memory directory", os.path.join(ROOT, "CLAUDE.md"), None),
                                 ("an unreadable payload never blocks", "", "not json")):
            rc, out = run(path, raw)
            good = rc == 0 and not out
            print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": rc={rc} {out!r}"))
            fails += not good
    print(f"\n{'FAILED' if fails else 'all passed'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
