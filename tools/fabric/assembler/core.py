"""tools/fabric/assembler/core.py — the layout, the constants, provenance, frontmatter and hygiene; the drain's Run.
A part of tools/fabric/assemble.py, whose docstring is the contract."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import hashlib
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any


_spec = importlib.util.spec_from_file_location(
    "fabric_layout", os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "layout.py"))


layout = importlib.util.module_from_spec(_spec)


_spec.loader.exec_module(layout)


_wc_spec = importlib.util.spec_from_file_location(
    "fabric_workingcopy", os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "workingcopy.py"))


workingcopy = importlib.util.module_from_spec(_wc_spec)


_wc_spec.loader.exec_module(workingcopy)


TIER1 = {"charter", "workflow", "index"}


DEFAULT_SLICE_BUDGET_TOKENS = 1800


CHARS_PER_TOKEN = 4  # rough, and only used to decide when to split a slice


CLASS_FILES = {
    "domain": "domain",
    "solution": "solution",
    "intersection": "intersection",
    "rationale": "rationale",
    "workflow": "workflow",
    "threads": "threads",
}


# Hygiene: the generic patterns live in layout.load_hygiene_patterns; a
# project's own (deployment names, sibling projects — that project's to
# keep) come from its working copy's .agent-fabric/hygiene.json, loaded
# once the project is known (intake.open_layout), in place: every part
# reads this one list.
BANNED_PATTERNS: list = []


# Italian function words that would not appear in ordinary English prose.
ITALIAN_MARKERS = re.compile(
    r"(?<![a-z])(perch[eé]|per[oò]|quindi|anche|questo|questa|quello|quella|"
    r"dovrebbe|bisogna|abbiamo|siamo|sono|essere|fare|molto|senza|dopo|prima di|"
    r"nella|nelle|negli|dello|della|delle|degli)(?![a-z])",
    re.I,
)


_SCRATCHPAD = re.compile(r"(?:^|/)scratchpad/")


_SESSION_TEMP = re.compile(r"^/?tmp/")


def normalize_artifact(kind: str, value: str) -> str:
    """Rewrite a `files` reference into one that still resolves later.

    The crossref index earns its keep by outliving the observation
    buffer: ADRs, PRs, commits and migrations resolve against git and
    GitHub, so an entry stays answerable long after the session that
    recorded it is gone. A path into a session's scratchpad resolves
    against nothing. It names a directory that belongs to ONE session
    on ONE machine — `/tmp/claude-1000/<clone>/<session-uuid>/...` —
    and is already dead by the time anyone reads the index, while
    still looking like a file someone could open.

    Such references are collapsed to a `scratch:` pseudo-path. That
    keeps the provenance fact worth keeping (this knowledge came from
    a throwaway probe, not from tracked code, so there is no source to
    go read) while dropping the session identity that made it a lie.
    Non-`files` kinds pass through untouched.

    TWO THINGS THIS DELIBERATELY DOES NOT DO, each found by review:

    A `scratchpad/` segment is ephemeral only UNDER a session-temp
    root. `docs/scratchpad/decision.md` is a tracked file someone can
    open, and rewriting it to `scratch:decision.md` would delete a
    valid repository path from the citation graph — the opposite of
    what this exists for. The temp root is checked FIRST, and a path
    that is not under one is returned untouched whatever it is named.

    And two dead paths that share a basename are not the same
    artifact. `/tmp/run-a/probe.cs` and `/tmp/run-b/probe.cs` both
    reduced to `scratch:probe.cs`, so the assembler merged their
    observation and slice lists into one node and conflated unrelated
    provenance. A short digest of the ORIGINAL path distinguishes them
    and stays stable across drains — without reintroducing the session
    identity, which is the thing being dropped.
    """
    if kind != "files":
        return value
    if not _SESSION_TEMP.match(value):
        # Tracked, whatever it is called. A `scratchpad/` segment under
        # the repo is a real directory with real files in it.
        return value
    match = _SCRATCHPAD.search(value)
    tail = value[match.end():] if match else value.rsplit("/", 1)[-1]
    # Distinguishes same-named artifacts; says nothing about where they
    # were, which is the point.
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:8]
    return f"scratch:{tail}#{digest}"


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-")
    return slug or "general"


# A YAML scalar that LOOKS like a number, bool or null is read back as one.
# Content hashes are hex, so roughly one in every few thousand is all digits
# plus an `e` — `23258632804400e6` parses as 2.3e+19 and the hash is gone.
# That is not hypothetical: it reached a committed slice and the lint caught
# it as "derived_from/0 is not of type 'string'".
YAML_AMBIGUOUS = re.compile(
    r"""(?xi)
    ^(?:
        [-+]?(?:\d[\d_]*)                      # int
      | [-+]?(?:\d[\d_]*)?\.\d*(?:[eE][-+]?\d+)?   # float, .5, 1.5e3
      | [-+]?(?:\d[\d_]*)(?:[eE][-+]?\d+)      # 1e6, and hex hashes shaped like it
      | 0[bo][0-7_01]+ | 0x[0-9a-f_]+           # other integer bases
      | [-+]?\.(?:inf|nan)
      | true|false|yes|no|on|off|y|n
      | null|~
    )$"""
)


def yaml_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    if (
        re.search(r"[:#\-\[\]{}&*!|>'\"%@`]", text)
        or re.search(r"[\n\r\t]", text)
        or text.strip() != text
        or text == ""
        or YAML_AMBIGUOUS.match(text)
    ):
        return json.dumps(text, ensure_ascii=False)
    return text


# An origin record says who produced the evidence and where. New records
# name the AGENT (the Linux login) with host, project and working copy;
# records written by the old clone-bound system name a `clone_id` and are
# preserved verbatim as historical provenance. Rendered in this key order.
ORIGIN_KEYS = ("agent", "clone_id", "host", "project", "working_copy")


def origin_of_row(row: dict[str, Any]) -> dict[str, str]:
    """The origin record for one observation row."""
    if row.get("agent") or "clone_id" not in row:
        origin = {"agent": row.get("agent") or "unresolved", "host": row.get("host") or "unknown"}
        for key in ("project", "working_copy"):
            if row.get(key):
                origin[key] = str(row[key])
        return origin
    return {"clone_id": row.get("clone_id") or "unresolved", "host": row.get("host") or "unknown"}


def origin_key(origin: dict[str, Any]) -> tuple:
    return tuple(sorted((k, str(v)) for k, v in origin.items() if v is not None))


def render_origin(item: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for key in ORIGIN_KEYS:
        if item.get(key) is None:
            continue
        prefix = "  - " if not lines else "    "
        lines.append(f"{prefix}{key}: {yaml_scalar(str(item[key]))}")
    return lines


def render_frontmatter(meta: dict[str, Any]) -> str:
    lines = ["---"]
    for key in ("role", "class", "topic", "description", "tier", "knowledge_scope",
                "shared_with", "token_budget", "corpus", "distilled_at",
                "collisions", "origin", "derived_from"):
        if key not in meta:
            continue
        value = meta[key]
        if isinstance(value, list):
            if not value:
                continue
            if key == "origin":
                lines.append(f"{key}:")
                for item in value:
                    lines.extend(render_origin(item))
            else:
                lines.append(f"{key}:")
                for item in value:
                    lines.append(f"  - {yaml_scalar(item)}")
        else:
            lines.append(f"{key}: {yaml_scalar(value)}")
    lines.append("---")
    return "\n".join(lines)


REDACTED = "[redacted]"


def hygiene_check(text: str, where: str) -> list[str]:
    problems = []
    for pattern, label, _refer_as in BANNED_PATTERNS:
        hit = pattern.search(text)
        if hit:
            problems.append(f"{where}: {label} -- {hit.group(0)!r}")
    italian = ITALIAN_MARKERS.findall(text)
    if len(set(w.lower() for w in italian)) >= 3:
        problems.append(f"{where}: reads as non-English (markers: {sorted(set(italian))[:5]})")
    return problems


def hygiene_substitute(text: str, where: str) -> tuple[str, list[str]]:
    """Replace every banned hit: with the entry's refer_as (a person becomes
    "the CEO"), else with "[redacted]" (a secret, a deployment's name).
    The knowledge stays; what must not travel does not (decided
    2026-09-16: substitute in place rather than refuse the claim). Every
    substitution is named, so the memory's owner fixes the source."""
    notes: list[str] = []
    for pattern, label, refer_as in BANNED_PATTERNS:
        replacement = refer_as or REDACTED
        def sub(m, label=label, replacement=replacement):
            notes.append(f"{where}: {label} -- {m.group(0)!r} -> {replacement!r}")
            # "the CEO" opens a sentence as "The CEO".
            before = text[:m.start()].rstrip()
            if not before or before[-1] in ".!?:" or text[:m.start()].endswith("\n\n") or before.endswith("#"):
                return replacement[:1].upper() + replacement[1:]
            return replacement
        text = pattern.sub(sub, text)
    return text, notes


def report_rel(path: str, project: str | None) -> str:
    """A path as the drain report and its stderr name it: relative to the
    project's working copy for a project file, to the fabric root for a
    fabric file. The report is committed into the project, and an
    absolute path pinned the directory one coordinator happened to drain
    in (a scratch checkout) into a file every clone reads."""
    path = os.path.abspath(path)
    wc = layout.working_copy_for(project) if project else None
    for base in ([os.path.abspath(wc)] if wc else []) + [os.path.abspath(layout.FABRIC_ROOT)]:
        if os.path.commonpath([path, base]) == base:
            return os.path.relpath(path, base)
    return os.path.basename(path)


DESCRIPTION_MAX = 240  # identities/schemas/role-template.schema.json


@dataclass
class Run:
    """What one drain carries from phase to phase: what main() once held in
    its locals, read and written by the phases in main()'s order."""
    args: argparse.Namespace
    project: str
    references: dict[str, Any] = field(default_factory=dict)
    origins: dict[str, dict[str, str]] = field(default_factory=dict)
    all_claims: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    telemetry: dict[str, Any] = field(default_factory=dict)
    shared: dict[tuple[str, str], list[dict[str, Any]]] = field(default_factory=lambda: defaultdict(list))
    per_role: dict[str, dict[tuple[str, str], list[dict[str, Any]]]] = field(
        default_factory=lambda: defaultdict(lambda: defaultdict(list)))
    shared_owners: dict[tuple[str, str], set[str]] = field(default_factory=lambda: defaultdict(set))
    rejected_hygiene: list[str] = field(default_factory=list)
    redactions: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    oversized: list[str] = field(default_factory=list)
    migrated: list[str] = field(default_factory=list)
    decisions: dict[str, str] = field(default_factory=dict)
    class_plan: dict[tuple[str, str], dict[str, Any]] = field(default_factory=dict)
    arrived: dict[tuple[str | None, str], set[str]] = field(default_factory=lambda: defaultdict(set))
    ambiguous_targets: list[str] = field(default_factory=list)
    unresolved_targets: list[str] = field(default_factory=list)
    applied_decisions: list[dict[str, str]] = field(default_factory=list)
    written: list[str] = field(default_factory=list)
    retired_in: list[str] = field(default_factory=list)   # sibling parts a supersede touched: path, section, rewritten|removed
    index_entries: dict[str, list[dict[str, str]]] = field(default_factory=lambda: defaultdict(list))
    clipped_descriptions: list[str] = field(default_factory=list)
    # A role whose crossref this run writes with an empty index. Said, not
    # just written: harvest_memory.py emits an empty references.json (memories
    # cite each other by name, not by git object), so every memory drain
    # writes an empty graph, and a file that exists reads as one that answers.
    empty_crossrefs: list[str] = field(default_factory=list)
    shared_index: dict[str, list[dict[str, str]]] = field(default_factory=lambda: defaultdict(list))
    owning_roles: list[str] = field(default_factory=list)


def base_for(run: Run, role: str, klass: str) -> str:
    """The directory a slice of `klass` for `role` lives in."""
    return layout.class_home(klass, role, run.project)


def in_report(run: Run, path: str) -> str:
    return report_rel(path, run.project)
