"""tools/fabric/assembler/report.py — the drain report written and said.
A part of tools/fabric/assemble.py, whose docstring is the contract."""
from __future__ import annotations

import functools
import importlib.util
import json
import os
import subprocess
import sys
from typing import Any
import roots
import memory_horizons
from assembler.core import layout, Run, UNKNOWN_ORIGIN, in_report, hygiene_substitute, patterns_for
from assembler.slices import merge_reports, scan_collisions, drop_held, read_existing_slice
from corrections import section_key
from assembler.shapes import still_replaced
from assembler.links import unresolved_links


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


def memory_use_of(run: Run, hr: dict, source: str) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    """({section id: [mark rows]}, {source: counts}) from the drain's marks.jsonl and harvest-report.json. A note is
    committed text and goes through the same hygiene as any other; a row that is not a mark is not carried."""
    marks: dict[str, list[dict[str, Any]]] = {}
    path = os.path.join(run.args.drain, "marks.jsonl")
    try:
        with open(path, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    except OSError:
        lines = []
    for line in lines:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if not (isinstance(row, dict) and isinstance(row.get("id"), str) and row.get("verdict") in memory_use_verdicts
                and isinstance(row.get("t"), str)):
            continue
        note = row.get("note") if isinstance(row.get("note"), str) else ""
        # A project section (p:) is held to the project's own list, a fabric one (f:) to the fabric's.
        note, notes = hygiene_substitute(note, "memory mark note", patterns_for("solution" if row["id"].startswith("p:") else "domain"))
        run.redactions.extend(notes)
        marks.setdefault(row["id"], []).append({"agent": hr.get("agent"), "t": row["t"], "verdict": row["verdict"], "note": note})
    use = hr.get("memory_use")
    return marks, ({source: use} if isinstance(use, dict) else {})


memory_use_verdicts = ("helpful", "wrong", "stale")


def reads_state_path(run: Run) -> str:
    """Where this drain keeps its per-section last-read dates: the agent state directory of the login that drains, never the
    tree (a clone reads the tree; the dates are this drain's own memory, ADR-050 rule 8)."""
    if run.args.reads_state:
        return os.path.abspath(run.args.reads_state)
    spec = importlib.util.spec_from_file_location("fabric_identity", os.path.join(roots.code_root(), "runtime", "identity.py"))
    assert spec and spec.loader
    identity = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(identity)
    return os.path.join(identity.agent_state_dir(), memory_horizons.STATE_FILE)


def review_horizons(run: Run, memory_use: dict[str, Any]) -> dict[str, Any]:
    """The drain report's `review_horizons` (ADR-050 rule 8): sections older than their class's horizon and sections no
    memory_read returned in 8 weeks, listed and never expired. The reads this drain carried are recorded first, the state
    is written on every drain; a state that cannot be read or written leaves the unread list empty and says so."""
    corpora = {"f": roots.memory_dir(root=layout.FABRIC_ROOT), "p": layout.project_memory_root(run.project)}
    key_of = {p: (lambda rel, root=root: in_report(run, os.path.join(root, rel))) for p, root in corpora.items()}
    path = reads_state_path(run)
    state, status = memory_horizons.load_state(path)
    ids_read: dict[str, Any] = {}
    for use in memory_use.values():
        ids = use.get("ids_read") if isinstance(use, dict) else None
        if isinstance(ids, dict):          # harvest content is untrusted: a list or a string is no counts
            ids_read.update(ids)
    rows = memory_horizons.rows_of(corpora, key_of)
    memory_horizons.observe(state, run.project, rows, run.args.stamp)
    memory_horizons.record_reads(state, run.project, ids_read, corpora, run.args.stamp, key_of)
    out = memory_horizons.horizons(rows, state, run.project, run.args.stamp)
    live = {p: {r["key"] for r in rows if r["scope"] == p} for p in corpora}
    try:
        memory_horizons.save_reads(path, state, run.project, live)
    except OSError as e:
        status = "unwritable"
        print(f"memory-drain-reads.json could not be written ({e.strerror or e}); the unread list is not trusted this drain", file=sys.stderr)
    if status in ("unreadable", "unwritable"):
        out["unread"], out["unread_from"] = [], None
    return {**out, "reads_state": status}


def helpful_counts(memory_marks: dict[str, list[dict[str, Any]]]) -> dict[str, int]:
    """Per section id, how many readers marked it helpful (ADR-050 rule 5). Counted from the merged marks, which a re-run of
    a bundle does not grow, so a mark is counted once; an id with none is absent, not 0, and stale/wrong are routed, not counted."""
    out: dict[str, int] = {}
    for ident, rows in memory_marks.items():
        n = sum(1 for row in rows if isinstance(row, dict) and row.get("verdict") == "helpful")
        if n:
            out[ident] = n
    return dict(sorted(out.items()))


def retrieval_summary(memory_use: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Per login, what the owner reads to see whether memory_find is used (ADR-049 rule 7): from the counts of the harvest
    bundles (memory_use, keyed agent@host[#store], one window each), summed over a login's hosts. Counts and shares only: no
    query text is in the harvest to carry, and no section id (that is memory_use.ids_read). A share is None, not 0, when there
    was no find to share over: unknown stays unknown."""
    out: dict[str, dict[str, Any]] = {}
    for source, use in memory_use.items():
        if not isinstance(use, dict) or not isinstance(use.get("calls"), dict):
            continue
        login, _, host = source.partition("@")
        row = out.setdefault(login, {"finds": 0, "zero_hit_finds": 0, "finds_followed_by_read": 0, "reads": 0, "indexes": 0,
                                     "marks": 0, "refused": 0, "hosts": [], "since_ms": None, "until_ms": None})
        calls = use["calls"]
        row["finds"] += int(calls.get("memory_find") or 0)
        row["reads"] += int(calls.get("memory_read") or 0)
        row["indexes"] += int(calls.get("memory_index") or 0)
        row["zero_hit_finds"] += int(use.get("zero_hit_finds") or 0)
        row["finds_followed_by_read"] += int(use.get("finds_followed_by_read") or 0)
        row["marks"] += int(use.get("marks") or 0)
        row["refused"] += int(use.get("errors") or 0)
        hostname = host.partition("#")[0]
        if hostname and hostname not in row["hosts"]:
            row["hosts"] = sorted([*row["hosts"], hostname])
        for key, pick in (("since_ms", min), ("until_ms", max)):
            value = use.get(key)
            if isinstance(value, int) and not isinstance(value, bool):
                row[key] = value if row[key] is None else pick(row[key], value)
    for row in out.values():
        finds = row["finds"]
        row["zero_hit_share"] = round(row["zero_hit_finds"] / finds, 3) if finds else None
        row["read_through"] = round(row["finds_followed_by_read"] / finds, 3) if finds else None
    return dict(sorted(out.items()))


def fabric_commit() -> str | None:
    """The agent-fabric commit the indexes were built against, or None when it cannot be asked: a message that said
    a plausible commit would be worse than one that says unknown."""
    try:
        done = subprocess.run(["git", "-C", layout.FABRIC_ROOT, "rev-parse", "HEAD"], capture_output=True, text=True,
                              timeout=20, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    sha = done.stdout.strip()
    return sha if done.returncode == 0 and sha else None


def oversized_by_origin(details: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """The oversized claims grouped by the login who may split the memory (a claim resting on several logins' observations
    is listed under each), each group with the one split request to send that login. The assembler only emits it: sending
    is the drain operator's."""
    groups: dict[str, list[dict[str, Any]]] = {}
    for item in details:
        for login in item.get("origins") or [UNKNOWN_ORIGIN]:
            groups.setdefault(login, []).append({k: v for k, v in item.items() if k != "origins"})
    return {login: {"claims": claims, "split_request": split_request(login, claims)}
            for login, claims in sorted(groups.items())}


def split_request(login: str, claims: list[dict[str, Any]]) -> str:
    lines = [f"Your memories below were drained as one claim each, larger than the slice budget of {claims[0]['budget']} tokens. "
             "A claim is atomic and cannot be split by the drain, so the slice is written whole and the prompts lint fails "
             "until you split each memory into smaller ones (one fact each, each with its own roles_class):"]
    lines += [f"- {c['source_file']}: ~{c['tokens']} tokens against {c['budget']} (slice {c['slice']})" for c in claims]
    if login == UNKNOWN_ORIGIN:
        lines.append("(No readable origin login: the drain operator finds the author before sending.)")
    return "\n".join(lines)


def commit_message(report: dict[str, Any], built_against: str | None) -> str:
    """The commit body for a project's drain, from the report alone: a line the report gives no reason for is not
    written, so a drain with no collisions and nothing held back names neither (a review of 2026-10-18: one hand-written
    message was said of seven different drains). A collision decision carrying a `rule` was the same-agent rule's,
    not the owner's; only the owner's file is said to be the owner's."""
    files = report.get("files") or []
    slices = [f for f in files if f.endswith(".md") and os.path.basename(f) != "INDEX.md"]
    roles = report.get("roles") or []
    lines = [f"{report.get('project')}: memory drain {report.get('stamp')}", "",
             f"Files written: {len(files)}, of which {len(slices)} are slices.",
             f"Roles indexed: {len(roles)}" + (f" ({', '.join(roles)})" if roles else "") + "."]
    decisions = report.get("collision_decisions") or []
    if decisions:
        owner = sum(1 for d in decisions if isinstance(d, dict) and not d.get("rule"))
        lines.append(f"Collision decisions: {len(decisions)}, {owner} decided by the owner (--collision-decisions), "
                     f"{len(decisions) - owner} by the same-agent rule.")
    rehomed = report.get("rehomed") or []
    if rehomed:
        lines.append(f"Re-homed to the control plane's corpus: {len(rehomed)} ({', '.join(r['slice'] for r in rehomed)}).")
    held = report.get("held_back") or []
    if held:
        lines.append(f"Held back: {len(held)} ({', '.join(held)}).")
    oversized = report.get("oversized_claims") or []
    if oversized:
        lines.append(f"Oversized claims: {len(oversized)}, written whole; lint fails until the memory is split.")
    lines.append(f"Indexes built against agent-fabric {built_against or 'unknown (its commit could not be read)'}.")
    return "\n".join(lines) + "\n"


def correction_holds(project: str, entry: dict[str, Any]) -> bool:
    """Whether the slice an applied correction names still holds the text it applied."""
    for base in [layout.working_copy_for(project), layout.FABRIC_ROOT]:
        path = os.path.join(base, entry["slice"]) if base else ""
        if path and os.path.isfile(path):
            try:
                _meta, sections = read_existing_slice(path)
            except (OSError, UnicodeDecodeError):
                return False
            return entry.get("heading") in sections and section_key(sections[entry["heading"]]) == entry.get("applied_key")
    return False


# What a re-home pass writes into agent-fabric's report: the ledger of its own decisions, nothing of a drain's reading.
REHOME_RECORD_KEYS = ("section_writers", "applied_corrections", "replaced_sections", "collision_decisions", "retitles")


def record_rehomed(other: Run) -> None:
    """What the control plane's pass of a re-home wrote and decided, into agent-fabric's own last-drain-report.json, merged as
    any run of a stamp is. It has no report of its own otherwise, and its replacements, applied corrections and section writers
    lived nowhere: a replay of the bundle then wrote the replaced text back into the corpus (ADR-050 rules 3 and 10; j82), and
    a collision decision the owner gave was forgotten by the next run. The pass is no harvest: watermarks, memory use and
    the harvest record are the project's report's, never this one's.

    A report already there (agent-fabric's own drain, at its own stamp: the ordinary case) is updated in place, only in the
    keys the pass is the writer of (REHOME_RECORD_KEYS). Taking merge_reports' whole result replaced it: an other-stamp merge
    keeps only the watermarks and the record, so harvest, memory marks, review horizons, held-back claims and flags were
    dropped, the report took the project's stamp and the project's roles entered agent-fabric's telemetry (j227 review round 2,
    F6)."""
    files = [in_report(other, p) for p in other.written]
    current = {
        "stamp": other.args.stamp, "project": other.project, "roles": other.owning_roles, "files": files, "files_written": len(files),
        "shared_topics": sorted(f"{k}:{t}" for (k, t) in other.shared), "shared_slices": len(other.shared),
        "telemetry": other.telemetry, "telemetry_sources": {}, "retired_in_siblings": other.retired_in,
        "section_writers": other.section_writers, "section_writers_gone": other.section_writers_gone,
        "section_moves": other.section_moves, "applied_corrections": other.applied_corrections,
        "replaced_sections": other.replaced_sections, "collision_decisions": other.applied_decisions, "retitles": other.retitles,
        "anchors_kept": other.anchors_kept, "anchors_lost": other.anchors_lost, "titles_one_lined": other.titles_one_lined,
    }
    path = layout.project_report_path(other.project)
    try:
        with open(path, encoding="utf-8") as fh:
            previous = json.load(fh)
        if not isinstance(previous, dict):
            previous = {}
    except (OSError, ValueError):
        previous = {}
    merged = merge_reports(previous, current, lambda rel: any(os.path.exists(os.path.join(root, rel))
                                                              for root in (layout.working_copy_for(other.project), layout.FABRIC_ROOT) if root))
    if previous:
        merged = {**previous, **{k: merged[k] for k in REHOME_RECORD_KEYS if k in merged}}
    merged["applied_corrections"] = [e for e in merged.get("applied_corrections") or [] if correction_holds(other.project, e)]
    merged["replaced_sections"] = still_replaced(other, merged.get("replaced_sections") or [])
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(merged, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")


def report(run: Run) -> int:
    # An unresolved collision is a property of the corpus, not of the drain
    # that happened to create it. Deriving it from the tree is what makes the
    # warning survive a drain with an empty delta for that slice — a valid and
    # expected outcome — instead of going quiet while both sections sit there.
    collisions = scan_collisions([
        # Where layout.py writes the domain slices (its FABRIC_ROOT, --fabric): a collision
        # is looked for where the drain puts them. layout.py is not yet on roots.
        roots.memory_dir("domains", root=layout.FABRIC_ROOT),
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
            # Memories drained as claims with origin: reflection (ADR-058 rule 5); absent in a report an older harvest wrote.
            "reflection": counts.get("reflection"),
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
    memory_marks, memory_use = memory_use_of(run, hr if harvest_meta is not None else {}, source)
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
        "assembled_without_hygiene": run.args.without_hygiene,
        "rejected_hygiene": run.rejected_hygiene,
        "redactions": run.redactions,
        "retired_in_siblings": run.retired_in,
        "section_writers": run.section_writers,
        "section_writers_gone": run.section_writers_gone,
        "section_moves": run.section_moves,
        "applied_corrections": run.applied_corrections,
        "replaced_sections": run.replaced_sections,
        "oversized_claims": run.oversized,
        "oversized_claim_details": run.oversized_details,
        "clipped_descriptions": run.clipped_descriptions,
        "migrated": run.migrated,
        "title_collisions": collisions,
        "collision_decisions": run.applied_decisions,
        "retitles": run.retitles,
        "merge_target_unresolved": run.unresolved_targets,
        "superseded_harvests": run.superseded_harvests,
        "reharvested_replaced": run.reharvested_replaced,
        "harvest": harvest_meta,
        "harvest_sources": {source: harvest_meta} if harvest_meta is not None else {},
        "watermarks": watermarks,
        "held_back": sorted(run.held_back),
        "rehomed": run.rehomed,
        "rehomed_files": run.rehomed_files,
        "anchors_kept": run.anchors_kept,
        "anchors_lost": run.anchors_lost,
        "titles_one_lined": run.titles_one_lined,
        # What the memory server recorded in the account's state (harvest_memory.py carries it): the marks by section
        # id, and the counts of calls per source. Read, not routed: no slice changes by them yet.
        "memory_marks": memory_marks,
        "memory_use": memory_use,
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
    # Derived from the corpus and the drain's reads each time, like the collisions: never carried from an earlier report.
    report["review_horizons"] = review_horizons(run, memory_use)
    # After the merge: the sources of earlier runs of this stamp are in memory_use by now.
    report["memory_retrieval"] = retrieval_summary(report.get("memory_use") or {})
    report["memory_helpful"] = helpful_counts(report.get("memory_marks") or {})
    if run.held_files or run.held_back:
        drop_held(report, run.held_back, run.held_files - set(files))
    # After drop_held: a held slice's claim is not this drain's to report.
    report["oversized_by_origin"] = oversized_by_origin(report.get("oversized_claim_details") or [])
    # A correction stays listed only while its slice still holds the text it applied: a later correction, a revert or a hand
    # edit ends it (else the harvest would name a live memory superseded, or skip a correction asserting live text again).
    report["applied_corrections"] = [e for e in report.get("applied_corrections") or [] if correction_holds(run.project, e)]
    report["replaced_sections"] = still_replaced(run, report.get("replaced_sections") or [])
    # A key an earlier run of the stamp held stays held only while no run
    # has written its slice since: this run writing it ends the hold.
    def written_now(key: str) -> bool:
        label, _, rest = key.partition("/")
        klass, _, topic = rest.partition(":")
        return bool(run.shared.get((klass, topic)) if label == "shared" else run.per_role.get(label, {}).get((klass, topic)))
    report["held_back"] = sorted(k for k in report.get("held_back") or [] if k in run.held_back or not written_now(k))
    # Derived from the corpus as it stands, like the collisions: a link a later drain made good leaves the list. Reported, never
    # rewritten, and never a failure: lint (lint_rules/slices.link_warnings) names what the whole committed corpus carries.
    undrained = {n.removesuffix(".md") for src in [*(report.get("harvest_sources") or {}).values(), harvest_meta]
                 for n in (src or {}).get("skipped_no_roles_class") or []}
    report["unresolved_links"] = unresolved_links(
        report["files"], [b for b in (layout.working_copy_for(run.project), layout.FABRIC_ROOT) if b], layout.FABRIC_ROOT,
        layout.project_memory_root(run.project),
        [layout.project_memory_root(p) for p in layout.list_projects() if p != run.project], undrained)
    # The re-homed files are the control plane's corpus: their links are read as that project's, not the drained project's.
    report["unresolved_links"] += unresolved_links(
        report.get("rehomed_files") or [], [layout.FABRIC_ROOT], layout.FABRIC_ROOT,
        layout.project_memory_root(layout.FABRIC_PROJECT_ID),
        [layout.project_memory_root(p) for p in layout.list_projects() if p != layout.FABRIC_PROJECT_ID], undrained)
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
    for login, row in report["memory_retrieval"].items():
        share = lambda v: "n/a" if v is None else f"{v:.0%}"  # noqa: E731 - a label for a line
        print(f"memory: {login} {row['finds']} finds, zero-hit {share(row['zero_hit_share'])}, read-through {share(row['read_through'])}, "
              f"{row['reads']} reads, {row['marks']} marks")
    if run.args.without_hygiene:
        print("\nNO HYGIENE LIST (--allow-missing-hygiene: these projects' banned names were not applied):", file=sys.stderr)
        for pid in run.args.without_hygiene:
            print(f"  {pid}", file=sys.stderr)
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
        for login, group in report["oversized_by_origin"].items():
            print(f"  split request for {login}:", file=sys.stderr)
            for line in group["split_request"].splitlines():
                print(f"    {line}", file=sys.stderr)
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
    if run.rehomed:
        print(f"\nRE-HOMED ({len(run.rehomed)}: the role is not bound by {run.project}'s taxonomy, so the claim went to agent-fabric's "
              "own corpus, which that role's remit covers):", file=sys.stderr)
        for row in run.rehomed:
            print(f"  {row['slice']} (role {row['role']}, from project {row['from_project']} to {row['to_project']}, "
                  f"from {', '.join(row['source']) or 'unknown'})", file=sys.stderr)
    lined = [row for row in run.titles_one_lined if row["slice"] not in run.held_back]
    if lined:
        print("\nTITLES MADE ONE LINE (a line break in the title became a space; fix the memory's description if the break was an escape "
              "meant literally):", file=sys.stderr)
        for row in lined:
            print(f"  {row['slice']}: {row['breaks']} break(s) in {row['title']!r}", file=sys.stderr)
    if run.superseded_harvests:
        print("\nSUPERSEDED HARVESTS (a memory whose text is a section a correction replaced, in this run or an earlier "
              "one; not written — update or delete the memory):", file=sys.stderr)
        for note in run.superseded_harvests:
            print(f"  {note}", file=sys.stderr)
    if run.reharvested_replaced:
        print("\nREHARVESTED UNDER A REPLACED HEADING (written; each note says why the text was no replay of the one a "
              "correction replaced):", file=sys.stderr)
        for note in run.reharvested_replaced:
            print(f"  {note}", file=sys.stderr)
    if run.empty_crossrefs:
        print("\nCROSSREF EMPTY (written with no entry: no observation behind the role's slices "
              "cites an artifact in this drain's references.json, and none was carried; "
              "fabric-query answers nothing from it):", file=sys.stderr)
        for note in run.empty_crossrefs:
            print(f"  {note}", file=sys.stderr)
    if report["unresolved_links"]:
        print("\nUNRESOLVED LINKS (written as they are; fix the memory, or draft the memory they name):", file=sys.stderr)
        for row in report["unresolved_links"]:
            print(f"  {row['slice']}#{row['heading']}: [[{row['target']}]] ({row['in']}): {row['why']}", file=sys.stderr)
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
    if run.args.commit_message:
        with open(run.args.commit_message, "w", encoding="utf-8") as fh:
            fh.write(commit_message(report, fabric_commit()))
    return 0
