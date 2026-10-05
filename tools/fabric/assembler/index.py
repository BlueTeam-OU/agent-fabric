"""tools/fabric/assembler/index.py — a role's INDEX.md and crossref.json.
A part of tools/fabric/assemble.py, whose docstring is the contract."""
from __future__ import annotations

import json
import os
from collections import defaultdict
from typing import Any
from assembler.core import layout, CLASS_FILES, normalize_artifact, render_frontmatter, Run, base_for, in_report
from assembler.slices import read_existing_slice
from assembler.writer import described


def index_role(run: Run, role: str) -> None:
    buckets = run.per_role.get(role, {})
    proj_dir = layout.project_dir(run.project, role)
    for entry in run.shared_index.get(role, []):
        run.index_entries[role].append(
            {"path": entry["path"], "description": entry["description"] + " (shared)",
             "class": entry["class"]}
        )
    # ...and every shared slice ON DISK this role owns and this run did
    # not write — the same sweep the role's own directories get. A
    # shared slice untouched by a drain (nothing new for it, or its only
    # incoming claim dropped by the owner) vanished from its owners'
    # indexes, and the index is the only thing a session reads.
    listed_shared = {e["path"] for e in run.index_entries[role]}
    for klass in CLASS_FILES:
        try:
            shared_dir = layout.shared_home(klass, run.project)
        except ValueError:
            continue
        if not os.path.isdir(shared_dir):
            continue
        for name in sorted(os.listdir(shared_dir)):
            if not name.startswith(f"{klass}-") or not name.endswith(".md"):
                continue
            path = os.path.join(shared_dir, name)
            meta, _sections = read_existing_slice(path)
            owners = meta.get("shared_with") or []
            if role not in owners:
                continue
            rel = layout.link_rel(path, run.project)
            if rel in listed_shared:
                continue
            run.index_entries[role].append(
                {"path": rel, "description": described(path, name) + " (shared)", "class": klass}
            )
            listed_shared.add(rel)

    # Authored files (charter, recall) are not distilled from claims, but
    # they are part of the role and the index must account for them — an
    # index that lists only what this tool wrote would read as complete
    # while omitting the first thing a session should open.
    for filename, klass in (("charter.md", "charter"), ("brief.md", "brief"), ("recall.md", "recall")):
        path = os.path.join(layout.role_dir(role), filename)
        if not os.path.exists(path):
            continue
        run.index_entries[role].append(
            {"path": layout.link_rel(path, run.project), "description": described(path, filename),
             "class": klass}
        )

    # Every slice ON DISK, not merely the ones this run wrote. Merge mode
    # rewrites only the slices a claim touched, so from cycle two onward a
    # role's untouched slices would vanish from its own index — and the
    # index is the ONLY thing a session reads before deciding what to load,
    # so losing an entry silently retires the knowledge behind it. On the
    # first drain every slice was written and this could not be seen; the
    # second drain dropped 101 entries across ten roles.
    listed = {e["path"] for e in run.index_entries[role]}
    for klass, subdir in CLASS_FILES.items():
        base = base_for(run, role, klass)
        candidates = (
            sorted(os.path.join(base, subdir, n)
                   for n in os.listdir(os.path.join(base, subdir)) if n.endswith(".md"))
            if os.path.isdir(os.path.join(base, subdir)) else []
        ) + ([os.path.join(base, f"{subdir}.md")]
             if os.path.exists(os.path.join(base, f"{subdir}.md")) else [])
        for path in candidates:
            rel = layout.link_rel(path, run.project)
            if rel in listed:
                continue
            run.index_entries[role].append(
                {"path": rel, "description": described(path, rel), "class": klass}
            )
            listed.add(rel)

    # crossref: artifact -> where it was learned and where it landed,
    # keyed by a reference that still RESOLVES later (see
    # normalize_artifact).
    crossref: dict[str, dict[str, dict[str, list[str]]]] = defaultdict(
        lambda: defaultdict(lambda: {"observations": [], "slices": []})
    )
    # SHARED CLAIMS COUNT AS THIS ROLE'S, and they are not in `buckets`.
    #
    # A claim owned by two or more roles is routed out of `per_role` and
    # into `shared` so it is stored once. The graph iterated `buckets`
    # alone, so every observation, ADR, PR and migration edge behind
    # shared knowledge was missing from BOTH owners' crossref.json — the
    # INDEX pointed at the shared slice correctly, which is exactly what
    # made the omission invisible: only a citation-graph query could see
    # it, and it silently under-reported.
    graph_sources: list[tuple[str, str, list[dict[str, Any]]]] = [
        (klass, f"{klass}:{topic}", claims)
        for (klass, topic), claims in sorted(buckets.items())
    ]
    graph_sources += [
        (klass, f"shared:{klass}:{topic}", claims)
        for (klass, topic), claims in sorted(run.shared.items())
        if role in run.shared_owners[(klass, topic)]
    ]

    for _klass, slice_name, claims in graph_sources:
        for claim in claims:
            for h in claim.get("evidence", []):
                for kind, values in (run.references.get(h) or {}).items():
                    for value in values:
                        node = crossref[kind][normalize_artifact(kind, value)]
                        if h not in node["observations"]:
                            node["observations"].append(h)
                        if slice_name not in node["slices"]:
                            node["slices"].append(slice_name)
    # Carried sections keep their citation edges. Rebuilding the graph from
    # this drain alone would drop every ADR, PR and migration edge belonging
    # to knowledge that is still sitting in the role base.
    crossref_path_existing = os.path.join(proj_dir, "crossref.json")
    if os.path.exists(crossref_path_existing):
        with open(crossref_path_existing, encoding="utf-8") as fh:
            old = json.load(fh).get("index", {})
        for kind, values in old.items():
            for value, node in values.items():
                # Normalized on the way IN as well, so a run also
                # repairs legacy keys already sitting in the file.
                target = crossref[kind][normalize_artifact(kind, value)]
                for h in node.get("observations", []):
                    if h not in target["observations"]:
                        target["observations"].append(h)
                for sl in node.get("slices", []):
                    if sl not in target["slices"]:
                        target["slices"].append(sl)

    crossref_doc = {
        "role": role,
        "generated_at": run.args.stamp,
        "index": {
            kind: {
                value: {
                    "observations": sorted(node["observations"]),
                    "slices": sorted(node["slices"]),
                }
                for value, node in sorted(values.items())
            }
            for kind, values in sorted(crossref.items())
        },
    }
    with open(os.path.join(proj_dir, "crossref.json"), "w", encoding="utf-8") as fh:
        json.dump(crossref_doc, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")
    if not crossref_doc["index"]:
        run.empty_crossrefs.append(in_report(run, os.path.join(proj_dir, "crossref.json")))

    # INDEX.md is generated, never hand-maintained: it is the only thing a
    # session sees before choosing what to load, so it must not drift.
    # Paths are relative to the project's working copy, because that is
    # where a session stands; the slices a role knows live in three
    # places (its identity and its domain in the fabric, this project
    # here), and the fabric ones are reached through ../agent-fabric/ so
    # a reader never reconstructs `../../..`.
    lines = [
        render_frontmatter({
            "role": role,
            "class": "index",
            "description": f"What {role} knows and where it lives.",
            "tier": 1,
            "distilled_at": run.args.stamp,
        }),
        "",
        f"# {role} — knowledge index",
        "",
        # The banner says what a session is actually given, and no more:
        # it once said the session-start hook gave every `workflow` slice,
        # which no hook did (ADR-013). Loading them was measured and
        # rejected — 45–140 KB of workflow slices per role, on every
        # session of every login — so a workflow slice is cued like the
        # rest, and the banner tells the reader to read the matching ones
        # BEFORE the work they govern, not after it has gone wrong.
        "A session is given the charter and brief (in the launch prompt),",
        "and the project's remit with a pointer to this index (from the",
        "session-start hook) — nothing below. Open a slice when its cue",
        "matches what you are doing; a `workflow` slice says how a kind of",
        "work is done here, so read the matching ones before that work.",
        "Paths are relative to this working copy; `../agent-fabric/` is the",
        "control plane checked out beside it.",
        "",
    ]
    by_class_index: dict[str, list[dict[str, str]]] = defaultdict(list)
    for entry in run.index_entries[role]:
        by_class_index[entry["class"]].append(entry)
    for klass in ("charter", "brief", "domain", "solution", "intersection", "rationale",
                  "workflow", "threads", "recall"):
        entries = by_class_index.get(klass)
        if not entries:
            continue
        lines.append(f"## {klass}")
        lines.append("")
        for entry in sorted(entries, key=lambda e: e["path"]):
            lines.append(f"- [`{entry['path']}`]({entry['path']}) — {entry['description']}")
        lines.append("")
    with open(os.path.join(proj_dir, "INDEX.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines).rstrip() + "\n")
    run.written.append(os.path.join(proj_dir, "INDEX.md"))
