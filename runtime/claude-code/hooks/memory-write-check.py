#!/usr/bin/env python3
"""runtime/claude-code/hooks/memory-write-check.py — PostToolUse on Write|Edit.

When a session writes one of its own Claude memories
(~/.claude/projects/<slug>/memory/<name>.md) that opts into the drain with
a `roles_class`, this runs the drain's own judgement on that one file and
tells the session, in one line per problem, what the next drain would do
with it: refuse it (a hand-authored or generated class, an unknown class,
a credential by shape, `shared_with` naming no role), hold it (another
language without its English rendering), or refuse the slice it becomes
(over the budget lint allows one section). The author fixes it while the
fact is fresh, instead of the coordinator finding it at the drain, weeks
later (agent-fabric ADR-013).

Silent for anything else: another path, MEMORY.md, a memory without a
`roles_class` (private by choice), and a memory the drain would take.
The decision is the harvester's own (`judge_memory`) and the budget
lint's (its constants), imported; nothing here restates a rule.
A credential is named by its kind, never shown. Never blocks: any
failure is silence and exit 0.
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import sys

FABRIC_ROOT = os.environ.get("AGENT_FABRIC_ROOT") or os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__)))))
MEMORY_PATH_RE = re.compile(r"/\.claude/projects/[^/]+/memory/(?!MEMORY\.md$)[^/]+\.md$")


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, os.path.join(FABRIC_ROOT, rel))
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, os.path.dirname(os.path.join(FABRIC_ROOT, rel)))
    spec.loader.exec_module(mod)
    return mod


def problems(path: str) -> list[str]:
    hm = _load("fabric_harvest", "tools/fabric/harvest_memory.py")
    parsed = hm.parse_memory(path)
    if not parsed or not parsed["roles_class"]:
        return []
    judged = hm.judge_memory(parsed)
    if judged["verdict"] == "refused":
        return [f"{judged['reason']}: the drain refuses it"]
    if judged["verdict"] == "held":
        return [f"{judged['reason']}: the drain holds it until rendered"]
    lint = _load("fabric_lint", "tools/fabric/lint.py")
    budget = lint.TIER1_BUDGET_TOKENS if parsed["roles_class"] == "workflow" else lint.BUDGET_TOKENS
    approx = len(judged["text"]) // lint.CHARS_PER_TOKEN
    if approx > budget * lint.BUDGET_TOLERANCE:
        return [f"~{approx} tokens: one memory is one section, over the {budget}-token slice budget lint "
                "allows — condense it, or split it into several memories"]
    return []


def main() -> int:
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
        path = ((payload.get("tool_input") or {}).get("file_path") or "") if isinstance(payload, dict) else ""
        if not MEMORY_PATH_RE.search(path) or not os.path.isfile(path):
            return 0
        found = problems(path)
    # SystemExit too: the harvester exits at import when its schema is
    # unreadable (a checkout mid-update, a stale root), and a hook that
    # promised silence would otherwise print its message and exit 1.
    except (Exception, SystemExit):  # noqa: BLE001 — a check must never cost the session its write
        return 0
    if found:
        name = os.path.basename(path)
        text = "\n".join(f"agent-fabric memory check ({name}): {p}." for p in found)
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": text}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
