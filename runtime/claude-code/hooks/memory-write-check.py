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

Beyond the drain's verdict it advises, never refusing (ADR-050): a description
shaped like an event (rule 7), a `solution` or `workflow` memory without
anchors (rule 1), a `merge_target` naming no section of the role's own
slices when no `shared_with` is given (rule 9).

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


# ADR-050 rule 7: a description shaped like an event is a record, not a lesson (rubric test 6). Exact and
# case-sensitive on purpose: "Fixed the cache" is prose a lesson may open with, "FIXED:" is a changelog line.
EVENT_RE = re.compile(r"(?:(?:FIXED|MERGED|CLOSED|DONE)[: ]|#\d+|PR \d+|\d{4}-\d{2}-\d{2}:)")


def unresolved_merge_target(hm, parsed: dict) -> str | None:
    """ADR-050 rule 9: the warning for a `merge_target` that names no section of the writing role's own slices
    of the memory's class and has no `shared_with`; None when it holds, or when the slices cannot be read
    (the role or project unbound, no working copy, no slice of the class): nothing is said then, never a guess.
    The directories are the layout's and the headings the assembler's own reading, as `resolve_targets` looks."""
    target = parsed["merge_target"]
    if not target or parsed["shared_with"]:
        return None
    try:
        ctx = hm.identity.resolve_context(cwd=os.getcwd())
        role, project = ctx.get("role"), ctx.get("project")
        if not role or not project:
            return None
        sys.path.insert(0, os.path.join(FABRIC_ROOT, "tools", "fabric"))
        from assembler.core import CLASS_FILES  # noqa: E402 — needs the path above
        from assembler.slices import read_existing_slice  # noqa: E402
        klass = parsed["roles_class"]
        base = hm.layout.class_home(klass, role, project)
        directory = os.path.join(base, CLASS_FILES[klass])
        files = [os.path.join(directory, n) for n in sorted(os.listdir(directory)) if n.endswith(".md")] \
            if os.path.isdir(directory) else []
        flat = os.path.join(base, f"{CLASS_FILES[klass]}.md")
        files += [flat] if os.path.isfile(flat) else []
        if not files or any(target in read_existing_slice(f)[1] for f in files):
            return None
    except (Exception, SystemExit):  # noqa: BLE001 — unreadable slices say nothing; the other warnings still stand
        return None
    return (f"merge_target {target!r} names no section of the {klass} slices of {role}, and no shared_with: if the "
            "section is in a shared slice, name the roles that own it in shared_with, or the drain files this "
            "beside it, not in its place")


def problems(path: str) -> list[str]:
    hm = _load("fabric_harvest", "tools/fabric/harvest_memory.py")
    parsed = hm.parse_memory(path)
    if not parsed or not parsed["roles_class"]:
        return []
    judged = hm.judge_memory(parsed)
    if judged["verdict"] == "refused":
        # A refusal stops the account's whole harvest, not only this memory.
        return [f"{judged['reason']}: the drain refuses this account's whole harvest until it is fixed"]
    if judged["verdict"] == "held":
        return [f"{judged['reason']}: the drain holds it until rendered"]
    lint = _load("fabric_lint", "tools/fabric/lint.py")
    budget = lint.TIER1_BUDGET_TOKENS if parsed["roles_class"] == "workflow" else lint.BUDGET_TOKENS
    approx = len(judged["text"]) // lint.CHARS_PER_TOKEN
    if approx > budget * lint.BUDGET_TOLERANCE:
        return [f"~{approx} tokens: one memory is one section, over the {budget}-token slice budget lint "
                "allows — condense it, or split it into several memories"]
    # Below here only advice: the drain takes the memory as it is.
    found = []
    if EVENT_RE.match(parsed["description"]):
        found.append("the description reads as an event (FIXED, MERGED, CLOSED, DONE, a #number, a PR number or a "
                     "dated line): git and the PR hold events, so write the lesson it taught (rubric test 6)")
    if parsed["roles_class"] in hm.ANCHOR_CLASSES and not parsed["anchors"]:
        found.append(f"a {parsed['roles_class']} memory with no anchors: add `anchors: [<path>::<symbol or literal>]` "
                     "to its metadata so the next check can tell when the tree outgrows it (ADR-050 rule 1)"
                     + "".join(f"; {w}" for w in parsed["anchor_problems"]))
    target = unresolved_merge_target(hm, parsed)
    if target:
        found.append(target)
    return found


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
