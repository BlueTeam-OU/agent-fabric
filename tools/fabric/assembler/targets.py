"""tools/fabric/assembler/targets.py — each class's layout planned, a topic's files found, corrections taken to their section.
A part of tools/fabric/assemble.py, whose docstring is the contract."""
from __future__ import annotations

import json
import os
import glob
import re
import sys
from collections import defaultdict
from typing import Any
from assembler.core import layout, CLASS_FILES, Run
from assembler.slices import read_existing_slice, claim_heading


def crossref_slice_ids(run: Run, role: str) -> set[str]:
    """Every `class:topic` id the role's committed crossref names."""
    path = os.path.join(layout.project_dir(run.project, role), "crossref.json")
    try:
        doc = json.load(open(path, encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    ids: set[str] = set()
    for kinds in (doc.get("index") or {}).values():
        for entry in (kinds or {}).values():
            ids.update(x for x in (entry.get("slices") or []) if isinstance(x, str))
    return ids


def existing_sections(paths: list[str]) -> dict[str, str]:
    found: dict[str, str] = {}
    for path in paths:
        _meta, sections = read_existing_slice(path)
        found.update(sections)
    return found


def plan_classes(run: Run) -> None:
    # THE LAYOUT OF EACH CLASS IS DECIDED ONCE, from the drain as it
    # arrived, before any claim moves between topics (a correction whose
    # merge_target lives in another topic, below). Both the pre-pass and
    # the write phase read this plan: deciding it again after the moves
    # could turn a two-topic drain into a one-topic one, and the flat
    # file would then be written in place by one phase and moved into the
    # directory by the other.
    #   split      — the class is written in the `<class>/` directory shape
    #   flat_topic — whose sections the flat `<class>.md` holds this run:
    #                the drain's one topic when the flat file stays, else
    #                the stem it is moved to (the one topic the crossref
    #                names, or `<class>-carried-<stamp>` for several)
    for role, topics in run.per_role.items():
        for klass in sorted({k for (k, _t) in topics}):
            base = layout.class_home(klass, role, run.project)
            here = sorted(t for (k, t) in topics if k == klass)
            split = os.path.isdir(os.path.join(base, CLASS_FILES[klass])) or len(here) > 1
            flat_file = os.path.join(base, f"{CLASS_FILES[klass]}.md")
            flat_topic = None
            if os.path.exists(flat_file):
                prior = sorted({sid.split(":", 1)[1] for sid in crossref_slice_ids(run, role)
                                if sid.startswith(f"{klass}:")})
                if not split:
                    flat_topic = here[0]
                elif len(prior) == 1:
                    flat_topic = prior[0]
                else:
                    stamp = read_existing_slice(flat_file)[0].get("distilled_at") or "earlier"
                    flat_topic = f"{CLASS_FILES[klass]}-carried-{stamp}"
            run.class_plan[(role, klass)] = {"split": split, "flat_topic": flat_topic}

    # The topics each class of this drain arrived with, before any claim
    # moves between topics: evidence that a `<topic>-<n>.md` is that
    # memory's own file and not a budget part of `<topic>`.
    for role, topics in run.per_role.items():
        for (klass, topic) in topics:
            run.arrived[(role, klass)].add(topic)
    for (klass, topic) in run.shared:
        run.arrived[(None, klass)].add(topic)


def is_budget_part(run: Run, role: str | None, klass: str, path: str, topic: str) -> bool:
    """Whether `path` is a budget part (`<stem>-<n>.md`) of `topic`.

    The file name cannot say: a memory named `release-2` is written
    as `release-2.md`, exactly the name part two of `release` gets,
    and read as `release`'s part its sections were `release`'s rivals
    and, under the same-agent rule, retired with it (a drain's blind
    review, 2026-09-26). A slice written since then names its topic
    in its frontmatter, which decides. An older file without one is a
    part only when `<stem>.md` exists (a topic named for a date ends
    in digits too) and neither this drain nor the role's crossref
    names `<topic>-<n>` as a topic of its own; with no such evidence
    the older reading stands."""
    stem = f"{klass}-{topic}" if role is None else topic
    name = os.path.basename(path)
    m = re.fullmatch(re.escape(stem) + r"-(\d+)\.md", name)
    if not m or not os.path.exists(path):
        return False
    recorded = read_existing_slice(path)[0].get("topic")
    if recorded:
        return recorded == topic
    if not os.path.exists(os.path.join(os.path.dirname(path), f"{stem}.md")):
        return False
    own = f"{topic}-{m.group(1)}"
    if own in run.arrived.get((role, klass), set()):
        return False
    return role is None or f"{klass}:{own}" not in crossref_slice_ids(run, role)


def slice_candidates(run: Run, role: str | None, klass: str, topic: str) -> list[str]:
    """Every file the topic's sections may sit in — the pre-pass reads
    exactly what the write phase will write into. The topic file and
    its budget parts (is_budget_part: a sibling topic named
    `<topic>-2026-09-17` or `<topic>-2` is another topic); and the flat class
    file when the plan gives its sections to this topic (it stays and
    this is the drain's one topic, or it moves to this topic's file).
    Read as this topic's regardless, another topic's section under a
    coinciding heading was refused as a collision the write phase
    never has; excluded whenever the crossref named two topics, a
    real collision inside a two-topic flat file went unstopped."""
    if role is None:
        base = layout.shared_home(klass, run.project)
        stem = os.path.join(base, f"{klass}-{topic}")
        flat: list[str] = []
    else:
        base = layout.class_home(klass, role, run.project)
        stem = os.path.join(base, CLASS_FILES[klass], topic)
        flat_file = os.path.join(base, f"{CLASS_FILES[klass]}.md")
        plan = run.class_plan.get((role, klass)) or {}
        flat = [flat_file] if plan.get("flat_topic") == topic else []
    parts = [f"{stem}.md"] + sorted(p for p in glob.glob(f"{stem}-*.md") if is_budget_part(run, role, klass, p, topic))
    return [p for p in flat + parts if os.path.exists(p)]


def topics_on_disk(run: Run, role: str | None, klass: str) -> dict[str, list[str]]:
    """Every topic of the role's class (or of the shared class) on
    disk, with the files its sections sit in; a `<stem>-<n>.md` is
    grouped under `<stem>` only when is_budget_part says so."""
    if role is None:
        base = layout.shared_home(klass, run.project)
        prefix = f"{klass}-"
        names = sorted(n for n in os.listdir(base) if n.startswith(prefix) and n.endswith(".md")) \
            if os.path.isdir(base) else []
        directory = base
    else:
        base = layout.class_home(klass, role, run.project)
        prefix = ""
        directory = os.path.join(base, CLASS_FILES[klass])
        names = sorted(n for n in os.listdir(directory) if n.endswith(".md")) \
            if os.path.isdir(directory) else []
    found: dict[str, list[str]] = defaultdict(list)
    for name in names:
        stem = name[len(prefix):-3]
        m = re.fullmatch(r"(.+)-\d+", stem)
        if m and is_budget_part(run, role, klass, os.path.join(directory, name), m.group(1)):
            stem = m.group(1)
        found[stem].append(os.path.join(directory, name))
    if role is not None:
        plan = run.class_plan.get((role, klass)) or {}
        flat_file = os.path.join(base, f"{CLASS_FILES[klass]}.md")
        if plan.get("flat_topic") and os.path.exists(flat_file):
            found[plan["flat_topic"]].insert(0, flat_file)
    return dict(found)


def is_carried(klass: str, topic: str) -> bool:
    return topic.startswith(f"{CLASS_FILES[klass]}-carried-")


def resolve_targets(run: Run, role: str | None, label: str,
                    buckets: dict[tuple[str, str], list[dict[str, Any]]]) -> None:
    on_disk_by_class: dict[str, dict[str, dict[str, str]]] = {}
    for (klass, topic), group in sorted(buckets.items()):
        for claim in list(group):
            target = (claim.get("merge_target") or "").strip()
            if not target and role is None:
                continue   # shared/ has no carried file
            own = existing_sections(slice_candidates(run, role, klass, topic))
            if target and target in own:
                continue
            if klass not in on_disk_by_class:
                on_disk_by_class[klass] = {t: existing_sections(p)
                                           for t, p in topics_on_disk(run, role, klass).items()}
            on_disk = on_disk_by_class[klass]
            heading = claim_heading(claim)
            if not target:
                # A CLAIM ALREADY IN THE CARRIED FILE STAYS THERE. A flat
                # class file holding several topics moves whole into
                # `<class>/<class>-carried-<stamp>.md`, which no topic
                # names; the same memory harvested again was written a
                # second time as `<class>/<topic>.md` beside its carried
                # copy (a drain's blind review, 2026-09-25). Its heading
                # there makes it that file's claim: the same text is a
                # no-op, a different one a collision asked about there.
                if heading in own:
                    continue
                holders = sorted(t for t, sections in on_disk.items()
                                 if t != topic and is_carried(klass, t) and heading in sections)
                if len(holders) == 1:
                    group.remove(claim)
                    buckets[(klass, holders[0])].append(claim)
                continue
            where = f"{label}/{klass}:{topic}#{heading}"
            holders = sorted(t for t, sections in on_disk.items() if target in sections and t != topic)
            if len(holders) > 1:
                run.ambiguous_targets.append(f"{where}: merge_target {target!r} is a section of "
                                         + ", ".join(f"{klass}:{t}" for t in holders))
                continue
            if not holders and heading in own:
                # Written as its own topic by an earlier drain, the
                # claim is reported on every drain that brings it: the
                # section it meant to replace still stands, and going
                # quiet after the first report hid that (a drain's
                # blind review, 2026-09-26). A correction applied in
                # place inside its own topic looks the same from the
                # tree; its merge_target names nothing either. So this
                # line says only what the tree shows, and asks the
                # author to drop a target already applied (the
                # re-review of #41, 2026-09-26).
                run.unresolved_targets.append(f"{where}: merge_target {target!r} names no section "
                                          f"of {label}/{klass}; the claim stands in its own topic — "
                                          "if it replaced that section before, drop the merge_target")
                continue
            if not holders:
                holders = sorted(t for t, sections in on_disk.items() if heading in sections and t != topic)
                if len(holders) != 1:
                    run.unresolved_targets.append(f"{where}: merge_target {target!r} names no section "
                                              f"of {label}/{klass}; written as its own topic")
                    continue
            # claim["topic"] stays the memory's: an untitled claim's
            # heading is derived from it.
            group.remove(claim)
            buckets[(klass, holders[0])].append(claim)
            if role is None:
                run.shared_owners[(klass, holders[0])] |= run.shared_owners[(klass, topic)]
    for key in [k for k, g in buckets.items() if not g]:
        del buckets[key]


def resolve_all_targets(run: Run) -> int | None:
    # A CORRECTION NAMES A SECTION, NOT A TOPIC. memory/README.md tells an
    # agent to correct a wrong slice by writing a memory that names the
    # slice's section in merge_target; that memory is its own file, so its
    # topic is its own, and the target was looked for in that topic alone
    # — the correction landed as a new slice beside the stale one and
    # nothing said so (a drain's blind review, 2026-09-25). A target
    # absent from the claim's topic is looked for in every topic of the
    # same role and class (or of the shared class): one holder takes the
    # claim, and the supersede path below replaces the section there; two
    # holders are a question only the author can answer, refused before
    # anything is written; none is written as its own topic and reported.
    # A claim already standing in another topic under its own heading is
    # a correction an earlier drain applied, harvested again: it goes back
    # there to be recognised as itself rather than written twice.
    for role in sorted(run.per_role):
        resolve_targets(run, role, role, run.per_role[role])
    resolve_targets(run, None, "shared", run.shared)
    if run.ambiguous_targets:
        print("MERGE TARGET AMBIGUOUS — a correction names a heading more than one topic holds; "
              "the author names the section unambiguously (retitle one of them, or the memory). "
              "This run wrote NOTHING and exits 1.", file=sys.stderr)
        for note in run.ambiguous_targets:
            print(f"  {note}", file=sys.stderr)
        return 1
