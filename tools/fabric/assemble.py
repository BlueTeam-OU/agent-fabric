#!/usr/bin/env python3
"""tools/fabric/assemble.py

>>> help
Turn distiller claims into the knowledge corpus, filed by scope.

    tools/fabric/assemble.py --claims DIR --drain DIR --project <project> --stamp DATE
    tools/fabric/assemble.py --bundle FILE|- --project <project> --stamp DATE

A BUNDLE is the drain as one tar with a manifest (harvest_memory.py
--bundle; bin/fabric-host <host> drain <login> streams one from the
account's own host). It is verified before anything is read from it:
every file the manifest names present with the digest it records, the
agent and host the same in manifest and report, nothing in the tar the
manifest does not name. A bundle that was cut short or changed on the
way is refused with the file named.

Where a slice lands is decided by tools/fabric/layout.py from its class:
domain knowledge under memory/domains/<role>/, everything learned about
the project under <working copy>/.agent-fabric/memory/<role>/ (the
project's own repository; fabric-coordinator's to write), multi-owner
slices under the matching shared/. The generated INDEX.md for each
(project, role) lists all of it with paths relative to the working copy
(fabric-side slices through ../agent-fabric/), plus the role's authored
charter and recall from identities/roles/<role>/.

Distillers judge; this assembles. A distiller emits claims and nothing
else — no files, no frontmatter, no index — because everything mechanical
belongs here where it is deterministic: same claims in, byte-identical
tree out. That property is what makes a drain reviewable as a content
diff rather than a diff of formatting noise.

What it does:

  * Places each claim in its class/topic slice, splitting a slice when it
    outgrows its token budget so no single file can quietly become
    enormous.
  * Writes provenance frontmatter: which observations a slice came from,
    and which clone and host produced them, so a claim stays auditable
    after the observation store has been archived and emptied.
  * Regenerates every role INDEX.md from slice frontmatter. The index is
    the only thing a session reads before deciding to load a slice, so it
    is generated rather than maintained — a hand-written index drifts.
  * Routes a claim owned by two or more roles to `memory/shared/` (or the
    project's own `shared/`), so
    knowledge two roles need lives once instead of in two copies that
    will disagree later.
  * Merges the citation graph into each role's crossref.json.
  * Runs the hygiene checks that must never reach a commit.

Merge mode is the default: existing slices are read, and a claim whose
`merge_target` names an existing section updates it instead of appending
beside it. Regenerating from scratch would discard accumulated curation,
so it is never done implicitly.
<<< help
"""

from __future__ import annotations

import functools
import json
import os
import sys
from collections import defaultdict
from typing import Any

# The parts are found beside this file however it is run: as the command,
# or by its path (tests/test_harvest_memory.py, tests/test_assemble.py).
sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))

from assembler.core import layout, CLASS_FILES, normalize_artifact, render_frontmatter, Run, base_for, in_report  # noqa: E402
from assembler.slices import merge_reports, scan_collisions, read_existing_slice  # noqa: E402
from assembler.intake import parse_args, open_layout, read_claims, screen_hygiene, bucket_claims, load_decisions  # noqa: E402
from assembler.targets import plan_classes, resolve_all_targets  # noqa: E402
from assembler.collisions import check_collisions  # noqa: E402
from assembler.writer import described, write_shared, write_role  # noqa: E402


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


def report(run: Run) -> int:
    # An unresolved collision is a property of the corpus, not of the drain
    # that happened to create it. Deriving it from the tree is what makes the
    # warning survive a drain with an empty delta for that slice — a valid and
    # expected outcome — instead of going quiet while both sections sit there.
    collisions = scan_collisions([
        os.path.join(layout.FABRIC_ROOT, "memory", "domains"),
        layout.project_memory_root(run.project),
        layout.shared_dir(),
    ], functools.partial(in_report, run))

    # The harvest's own provenance has to survive into the COMMITTED record,
    # because the drain directory it lives in is temporary. Two things were
    # being lost with it:
    #
    #   * the watermark. Without it the next drain cannot answer "since when",
    #     and the only anchor left is the stamp date — which has to be turned
    #     back into an epoch by hand, per store, every cycle.
    #   * the provisional-binding tally. A row whose (host, label, timestamp)
    #     resolves to no clone is reported provisional and never guessed, but
    #     nothing downstream read that number, so a drain in which EVERY row
    #     was unattributable landed looking exactly like a clean one.
    #
    # `database` is deliberately not carried: it is an absolute path into
    # somebody's home directory, and committing it would pin an environment
    # literal into a file every clone reads.
    harvest_meta: dict[str, Any] | None = None
    watermarks: dict[str, int] = {}
    harvest_report = os.path.join(run.args.drain, "harvest-report.json")
    if os.path.exists(harvest_report):
        with open(harvest_report, encoding="utf-8") as fh:
            hr = json.load(fh)
        counts = hr.get("counts") or {}
        harvest_meta = {
            "host": hr.get("host"),
            "since_watermark": hr.get("since_watermark"),
            "next_watermark": hr.get("next_watermark"),
            "provisional_agent": counts.get("provisional_agent", counts.get("provisional_clone")),
            "in_scope": counts.get("in_scope"),
        }
        # Keyed agent@host: each account on a host has its own store, and
        # its harvest reads this key back (harvest_memory.previous_watermark).
        if hr.get("host") is not None and hr.get("next_watermark") is not None:
            watermarks[f"{hr.get('agent') or 'unattributed'}@{hr['host']}"] = hr["next_watermark"]

    source = f"{hr.get('agent') or 'unattributed'}@{hr.get('host') or 'unknown'}" \
        if harvest_meta is not None else "unattributed"
    files = [in_report(run, p) for p in run.written]
    report = {
        "stamp": run.args.stamp,
        "project": run.project,
        "roles": run.owning_roles,
        "files": files,
        "files_written": len(files),
        "shared_topics": sorted(f"{k}:{t}" for (k, t) in run.shared),
        "shared_slices": len(run.shared),
        "telemetry": run.telemetry,
        "telemetry_sources": {source: run.telemetry},
        "hygiene_problems": run.problems,
        "rejected_hygiene": run.rejected_hygiene,
        "redactions": run.redactions,
        "retired_in_siblings": run.retired_in,
        "oversized_claims": run.oversized,
        "clipped_descriptions": run.clipped_descriptions,
        "migrated": run.migrated,
        "title_collisions": collisions,
        "collision_decisions": run.applied_decisions,
        "merge_target_unresolved": run.unresolved_targets,
        "harvest": harvest_meta,
        "harvest_sources": {source: harvest_meta} if harvest_meta is not None else {},
        "watermarks": watermarks,
    }
    report_path = layout.project_report_path(run.project)
    try:
        with open(report_path, encoding="utf-8") as fh:
            previous = json.load(fh)
        if not isinstance(previous, dict):
            previous = {}
    except (OSError, ValueError):
        previous = {}
    def still_there(rel: str) -> bool:
        roots = [layout.working_copy_for(run.project), layout.FABRIC_ROOT]
        return any(root and os.path.exists(os.path.join(root, rel)) for root in roots)
    report = merge_reports(previous, report, still_there)
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")

    for role in run.owning_roles:
        counts = run.telemetry.get(role, {})
        print(
            f"{role:16} claims={sum(len(v) for v in run.per_role.get(role, {}).values()):>3} "
            f"slices={sum(1 for p in run.written if f'/{role}/' in p):>3} "
            f"admitted={counts.get('admitted', '?')} rejected={counts.get('rejected', '?')}"
        )
    print(f"\n{len(run.written)} files, {len(run.shared)} shared slices")
    if run.redactions:
        print("\nREDACTED (hygiene — the slice carries the substitute; fix the memory so the next drain needs none):", file=sys.stderr)
        for note in run.redactions:
            print(f"  {note}", file=sys.stderr)
    if run.rejected_hygiene:
        print("\nREJECTED (hygiene — fix the memory, the corpus did not receive it; this run exits 1):", file=sys.stderr)
        for note in run.rejected_hygiene:
            print(f"  {note}", file=sys.stderr)
    if run.retired_in:
        print("\nRETIRED in another part of the topic (a supersede reached the section where it lived):", file=sys.stderr)
        for note in run.retired_in:
            print(f"  {note}", file=sys.stderr)
    if run.oversized:
        print("\nOVER BUDGET (written whole; lint will fail until the memory is split):", file=sys.stderr)
        for note in run.oversized:
            print(f"  {note}", file=sys.stderr)
    if run.clipped_descriptions:
        print("\nDESCRIPTIONS CLIPPED to the schema limit (shorten the memory's description to choose the cue):", file=sys.stderr)
        for note in run.clipped_descriptions:
            print(f"  {note}", file=sys.stderr)
    if run.migrated:
        print("\nLAYOUT: flat class file moved into its directory:", file=sys.stderr)
        for note in run.migrated:
            print(f"  {note}", file=sys.stderr)
    if run.unresolved_targets:
        # Loud because the author meant to replace something: the stale
        # section it named, if it exists under another heading, still
        # stands beside the correction until someone retargets the memory.
        print("\nMERGE TARGET UNRESOLVED (the correction names no section of its class; the claim stands as "
              "it is — retarget the memory if a stale section remains, drop the target if it was applied):",
              file=sys.stderr)
        for note in run.unresolved_targets:
            print(f"  {note}", file=sys.stderr)
    if run.empty_crossrefs:
        print("\nCROSSREF EMPTY (written with no entry: no observation behind the role's slices "
              "cites an artifact in this drain's references.json, and none was carried; "
              "query.sh answers nothing from it):", file=sys.stderr)
        for note in run.empty_crossrefs:
            print(f"  {note}", file=sys.stderr)
    if collisions:
        print("\nTITLE COLLISIONS (both claims kept):", file=sys.stderr)
        for note in collisions:
            print(f"  {note}", file=sys.stderr)
    # A WARNING, not a failure: an unattributable row is still knowledge, and
    # the harvest reports it provisional rather than guessing. But the tally
    # used to exist only in the transient harvest report, so a drain of a
    # clone that had never registered — every row provisional — landed
    # looking exactly like a clean one. Loud here, and never a gate: gating
    # would refuse valid knowledge for a registry gap it cannot itself fix.
    provisional = (harvest_meta or {}).get("provisional_agent") or 0
    if provisional:
        in_scope = (harvest_meta or {}).get("in_scope") or 0
        share = f" of {in_scope}" if in_scope else ""
        print(
            f"\nPROVISIONAL BINDINGS: {provisional}{share} observation(s) resolved "
            f"to no agent.\n"
            "  Their knowledge is kept; only the agent attribution is missing.\n"
            "  harvest_memory.py stamps the agent at source; a drain built from\n"
            "  anything else must carry the agent in each observation.",
            file=sys.stderr,
        )
    if run.problems:
        # Carried text can still trip hygiene (a slice written before the
        # check existed): reported the same way, and the run is not clean.
        print("\nHYGIENE PROBLEMS in carried text:", file=sys.stderr)
        for problem in run.problems:
            print(f"  {problem}", file=sys.stderr)
    if run.problems or run.rejected_hygiene:
        return 1
    return 0


def main() -> int:
    args = parse_args()
    run = Run(args=args, project=open_layout(args))
    if read_claims(run):
        return 1
    screen_hygiene(run)
    bucket_claims(run)
    load_decisions(run)
    plan_classes(run)
    if resolve_all_targets(run):
        return 1
    if check_collisions(run):
        return 1
    write_shared(run)
    # Every role that owns anything gets a project directory and an index —
    # including one whose claims all live in shared slices, which would
    # otherwise end up with knowledge and no way to find it.
    run.owning_roles = sorted(set(run.per_role) | set(run.shared_index) | set(run.all_claims))
    for role in run.owning_roles:
        write_role(run, role)
        index_role(run, role)
    return report(run)


if __name__ == "__main__":
    sys.exit(main())
