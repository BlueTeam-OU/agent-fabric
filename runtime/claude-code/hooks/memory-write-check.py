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
`roles_class` (private by choice), and a memory the drain would take that
draws none of the advice above. The drain's decision is the harvester's own
(`judge_memory`) and the budget lint's (its constants), imported; the one
rule restated here is ADR-050 rule 7's pattern (EVENT_RE), which
tests/test_memory_write_check.py pins.
A credential is named by its kind, never shown. Never blocks: any
failure is silence and exit 0.
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
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


def owning_working_copy(hm, path: str) -> tuple[str, str] | None:
    """(project, working copy) of the working copy whose memory directory holds `path`, as the drain judges it
    (harvest_memory resolves the project from the working copy, never from the session's cwd); None when the
    slug names no known working copy or working copies of different projects. The slug is lossy, so a
    name that fits nothing, or fits two projects, is not guessed. Candidates: the session's own checkout, the
    one its binding names, then the ones the fabric already knows of."""
    slug = os.path.basename(os.path.dirname(os.path.dirname(path)))
    wcmod = hm.identity._workingcopy()
    candidates = [wcmod.toplevel(os.getcwd()), hm.identity.binding_record().working_copy,
                  hm.layout.FABRIC_ROOT, *hm.layout.explicit_working_copies().values(),
                  *(hm.layout.working_copy_for(pid) for pid in hm.layout.project_ids()),
                  *wcmod.sibling_working_copies(hm.layout.FABRIC_ROOT).values()]
    owners = {}
    for candidate in candidates:
        if candidate and hm.layout.memory_slug(candidate) == slug:
            project = hm.identity.resolve_context(cwd=candidate).get("project")
            owners.setdefault(project, os.path.abspath(candidate))
    if len(owners) != 1 or None in owners:
        return None
    return next(iter(owners.items()))


def _git(working_copy: str, *args: str) -> bytes | None:
    """stdout of one local git read, None when git fails or hangs: the caller treats None as "not readable".
    Never the network: in a partial clone git fetches a missing object on its own and would hold the hook for the
    timeout on every read (the review_mcp scope.git_env switches; the rest of the session's environment stays, git needs it)."""
    env = {**os.environ, "GIT_NO_LAZY_FETCH": "1", "GIT_TERMINAL_PROMPT": "0"}
    try:
        done = subprocess.run(["git", "-C", working_copy, *args], capture_output=True, timeout=10, check=False, env=env)
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout if done.returncode == 0 else None


def committed_headings(working_copy: str, directory: str, flat: str, parse) -> set[str] | None:
    """Headings of the slices at `directory` (or the flat file `flat`) as the remote's default branch holds them,
    read from the local `origin/HEAD` or `origin/main` ref: no fetch, a hook must not wait on the network. The
    drain assembles against the remote's corpus, so a checkout behind it has a heading on the remote that its
    own tree lacks (a true merge_target read as missing). Empty when no such ref or path exists; None when the ref
    exists but a tree or blob of it cannot be read (a partial clone without the object): unknown, never "absent"."""
    top = _git(working_copy, "rev-parse", "--show-toplevel")
    if not top:
        return set()
    top = os.path.realpath(top.decode("utf-8", "replace").strip())
    found: set[str] = set()
    for ref in ("origin/HEAD", "origin/main"):
        if _git(top, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}") is None:
            continue
        rels = []
        for path in (directory, flat):
            rel = os.path.relpath(os.path.realpath(path), top)
            if not rel.startswith(os.pardir):
                rels.append(rel)
        listing = _git(top, "ls-tree", "-r", "--name-only", "-z", ref, "--", *rels) if rels else None
        if rels and listing is None:
            return None
        for name in (listing or b"").decode("utf-8", "replace").split("\0"):
            if not name.endswith(".md"):
                continue
            blob = _git(top, "show", f"{ref}:{name}")
            if blob is None:
                return None
            found.update(parse(blob.decode("utf-8", "replace"))[1])
        break
    return found


def unresolved_merge_target(hm, parsed: dict, path: str) -> str | None:
    """ADR-050 rule 9: the warning for a `merge_target` that names no section of the writing role's own slices
    of the memory's class, in the working copy or on the remote's default branch (the drain's corpus) and has no `shared_with`; None when it holds, or when the slices cannot be read
    (the role or project unbound, no working copy, no slice of the class): nothing is said then, never a guess.
    The directories are the layout's and the headings the assembler's own reading, as `resolve_targets` looks."""
    target = parsed["merge_target"]
    if not target or parsed["shared_with"]:
        return None
    try:
        role = hm.identity.resolve_context(cwd=os.getcwd()).get("role")
        owner = owning_working_copy(hm, path)
        if not role or not owner:
            return None
        project, working_copy = owner
        # class_home finds the project's slices through the layout's working copy for it, which the binding or
        # the environment may name differently from the one that owns this memory directory.
        hm.layout.set_working_copy(project, working_copy)
        sys.path.insert(0, os.path.join(FABRIC_ROOT, "tools", "fabric"))
        from assembler.core import CLASS_FILES  # noqa: E402 — needs the path above
        from assembler.slices import parse_slice, read_existing_slice  # noqa: E402
        klass = parsed["roles_class"]
        base = hm.layout.class_home(klass, role, project)
        directory = os.path.join(base, CLASS_FILES[klass])
        files = [os.path.join(directory, n) for n in sorted(os.listdir(directory)) if n.endswith(".md")] \
            if os.path.isdir(directory) else []
        flat = os.path.join(base, f"{CLASS_FILES[klass]}.md")
        files += [flat] if os.path.isfile(flat) else []
        if any(target in read_existing_slice(f)[1] for f in files):
            return None
        # The checkout may be behind the remote the drain reads (a job worktree cut from an older main).
        remote = committed_headings(working_copy, directory, flat, parse_slice)
        if remote is None or target in remote:
            return None
        if not files and not remote:
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
                     "to its metadata, `<project>:<path>::…` for a path in another registered project, so the next "
                     "check can tell when the tree outgrows it (ADR-050 rule 1)"
                     + "".join(f"; {w}" for w in parsed["anchor_problems"]))
    target = unresolved_merge_target(hm, parsed, path)
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
