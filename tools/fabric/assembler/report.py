"""tools/fabric/assembler/report.py — the drain report written and said.
A part of tools/fabric/assemble.py, whose docstring is the contract."""
from __future__ import annotations

import functools
import json
import os
import sys
from typing import Any
from assembler.core import layout, Run, in_report, hygiene_substitute
from assembler.slices import merge_reports, scan_collisions, drop_held


def store_of(hr: dict) -> str:
    """The store a harvest read: its own key when it names one, else
    agent@host. Also the source its harvest and telemetry are kept under."""
    store = hr.get("store")
    if isinstance(store, str) and store:
        return store
    return f"{hr.get('agent') or 'unattributed'}@{hr.get('host') or 'unknown'}"


def held_mark(run: Run, next_mark: int) -> int | None:
    """The store's mark when claims were held: below the oldest memory a
    held claim stands on, as the harvest keeps it below an unrendered one,
    so the next harvest reads it again and a hold is never a drop (#100's
    review, P2). The harvest's mtime_ms is at least created_at_epoch * 1000,
    so one millisecond below that is below the memory. A held claim whose
    memory has no time recorded leaves the mark where it was (None): no
    bound is known that keeps it in the next harvest."""
    if not run.held_evidence:
        return next_mark
    epochs = [run.evidence_epoch.get(h) for h in run.held_evidence]
    if not all(isinstance(e, int) and not isinstance(e, bool) for e in epochs):
        return None
    return min(next_mark, min(epochs) * 1000 - 1)


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
            # The memories the harvest left out for want of a roles_class:
            # in the committed record, so the owner sees them after the
            # drain directory is gone. Names an agent chose, held to the
            # same hygiene as any committed text.
            "skipped_no_roles_class": [],
        }
        for name in hr.get("skipped_no_roles_class") or []:
            if isinstance(name, str):
                kept, notes = hygiene_substitute(name, "harvest skipped_no_roles_class")
                run.redactions.extend(notes)
                harvest_meta["skipped_no_roles_class"].append(kept)
        harvest_meta["skipped_no_roles_class"].sort()
        # Keyed by store: agent@host for a working copy's own memory, with
        # #<store> (--store, e.g. projects-root) for another (harvest_memory.
        # store_key, checked as the account's own by core.store_error), so two stores of
        # one account never share a mark; the harvest reads it back
        # (harvest_memory.previous_watermark). A report without "store" is
        # an older harvest's, keyed agent@host as it always was.
        if hr.get("host") is not None and hr.get("next_watermark") is not None:
            mark = held_mark(run, hr["next_watermark"])
            if mark is not None:
                watermarks[store_of(hr)] = mark

    source = store_of(hr) if harvest_meta is not None else "unattributed"
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
        "held_back": sorted(run.held_back),
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
    if run.held_files or run.held_back:
        drop_held(report, run.held_back, run.held_files - set(files))
    # A key an earlier run of the stamp held stays held only while no run
    # has written its slice since: this run writing it ends the hold.
    def written_now(key: str) -> bool:
        label, _, rest = key.partition("/")
        klass, _, topic = rest.partition(":")
        return bool(run.shared.get((klass, topic)) if label == "shared" else run.per_role.get(label, {}).get((klass, topic)))
    report["held_back"] = sorted(k for k in report.get("held_back") or [] if k in run.held_back or not written_now(k))
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
