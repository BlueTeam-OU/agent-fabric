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
from assembler.core import layout, CLASS_FILES, Run, in_report
from assembler.slices import is_retire, read_existing_slice, claim_heading


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


def parts_holding(run: Run, role: str | None, klass: str, topic: str, heading: str) -> list[str]:
    """The files of one topic (its budget parts) that hold a section under `heading`."""
    return [p for p in slice_candidates(run, role, klass, topic) if heading in read_existing_slice(p)[1]]


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
    #                the stem it is moved to (the topic the file records;
    #                for an older file that records none, the one topic the
    #                crossref names when it names exactly the drain's topics,
    #                else the carried file, `<class>-carried-<stamp>`)
    for role, topics in run.per_role.items():
        for klass in sorted({k for (k, _t) in topics}):
            base = layout.class_home(klass, role, run.project)
            here = sorted(t for (k, t) in topics if k == klass)
            flat_file = os.path.join(base, f"{CLASS_FILES[klass]}.md")
            prior = sorted({sid.split(":", 1)[1] for sid in crossref_slice_ids(run, role)
                            if sid.startswith(f"{klass}:")})
            # A flat file records the one topic it holds (write_role): the file alone says whose it is when the
            # crossref, which a drain without references leaves empty, does not.
            flat_topic = None
            held = None
            if os.path.exists(flat_file):
                held = read_existing_slice(flat_file)[0].get("topic")
                held = held if isinstance(held, str) and held else None
            # Only a file that records its topic is known to hold that one: an older flat file may hold memories the
            # crossref (referenced slices only) never named, so it is not read as the drain's topic's (see `unclaimed`).
            known = {held} if held else set()
            # A SECOND TOPIC MOVES THE CLASS INTO ITS DIRECTORY. The flat file has one INDEX row and one description,
            # so a topic written into it lost its cue (a drain's blind review, 2026-10-24).
            #
            # A FLAT FILE THAT RECORDS NO TOPIC IS NOT KNOWN TO HOLD THE ONE THE DRAIN BRINGS. Per-bundle runs each see
            # one topic, so a file written before topics were recorded took every unrelated topic of its class as its
            # own: brand-comms' domain.md piled them up in the 2026-10-31 drain (#437 round 5, F13). Only the crossref
            # can say whose it is, and only when it names exactly the drain's topics; otherwise the file moves into the
            # directory as the carried file and the new topic gets a file of its own. Refusing instead would stop every
            # drain of a class whose file predates the field (half of the corpus's flat files).
            unclaimed = bool(os.path.exists(flat_file) and not held and set(here) != set(prior))
            split = (os.path.isdir(os.path.join(base, CLASS_FILES[klass])) or len(here) > 1
                     or bool(known and os.path.exists(flat_file) and not set(here) <= known))
            # Moved as the carried file, never named for a topic from the crossref, which lists referenced slices only: the
            # file may hold memories it never named, and labelling them one topic's wrote them twice (review of #368, F1).
            carry = unclaimed and not split
            split = split or unclaimed
            if os.path.exists(flat_file):
                if not split:
                    flat_topic = here[0]
                elif held:
                    flat_topic = held
                elif len(prior) == 1 and not carry:
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


def held_files(run: Run) -> None:
    """Every file a held slice has or would have, as the report names it:
    its topic file, its parts and, when the hold left its class with
    nothing in this drain, the flat class file. Planned first, so the parts
    are found the way the write phase would find them. The report keeps any
    of them this run wrote all the same (another topic's flat file)."""
    for key in run.held_back:
        label, _, rest = key.partition("/")
        klass, _, topic = rest.partition(":")
        role = None if label == "shared" else label
        paths = slice_candidates(run, role, klass, topic)
        if role is None:
            paths.append(os.path.join(layout.shared_home(klass, run.project), f"{klass}-{topic}.md"))
        else:
            base = layout.class_home(klass, role, run.project)
            paths.append(os.path.join(base, CLASS_FILES[klass], f"{topic}.md"))
            if (role, klass) not in run.class_plan:
                paths.append(os.path.join(base, f"{CLASS_FILES[klass]}.md"))
        run.held_files.update(in_report(run, p) for p in paths)


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


def written_stem(run: Run, role: str | None, klass: str, topic: str) -> str:
    """The file name (without `.md`) a topic's first part has once written: the name a `[[link]]` resolves by."""
    if role is None:
        return f"{klass}-{topic}"
    return topic if run.class_plan[(role, klass)]["split"] else CLASS_FILES[klass]


def resolve_targets(run: Run, role: str | None, label: str,
                    buckets: dict[tuple[str, str], list[dict[str, Any]]]) -> list[tuple[str | None, str, str]]:
    """Returns (role, memory name, file stem) for each claim filed in another topic's slice."""
    moved: list[tuple[str | None, str, str]] = []
    on_disk_by_class: dict[str, dict[str, dict[str, str]]] = {}
    for (klass, topic), group in sorted(buckets.items()):
        for claim in list(group):
            target = (claim.get("merge_target") or "").strip()
            if not target and role is None:
                continue   # shared/ has no carried file
            own = existing_sections(slice_candidates(run, role, klass, topic))
            where = f"{label}/{klass}:{topic}#{claim_heading(claim)}"
            # A HEADING TWO PARTS OF ONE TOPIC HOLD is as ambiguous as one two topics hold. Which part the claim is
            # written into is split_by_budget's grouping, not the target's, and the other part's copy stood: in
            # a project's drain of 2026-10-28 (j481) the correction replaced the heading in part 2 only, and the
            # text it replaced came back from part 1's side. Refused like the two-topic case, nothing written; the
            # author or the owner leaves one copy in the corpus.
            if target and len(parts_holding(run, role, klass, topic, target)) > 1:
                run.ambiguous_targets.append(f"{where}: merge_target {target!r} is a section of more than one part of "
                                             f"{klass}:{topic}: " + ", ".join(in_report(run, p) for p in parts_holding(run, role, klass, topic, target)))
                continue
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
                    moved.append((role, claim["topic"], written_stem(run, role, klass, holders[0])))
                continue
            holders = sorted(t for t, sections in on_disk.items() if target in sections and t != topic)
            if len(holders) == 1 and len(parts_holding(run, role, klass, holders[0], target)) > 1:
                run.ambiguous_targets.append(f"{where}: merge_target {target!r} is a section of more than one part of "
                                             f"{klass}:{holders[0]}: "
                                             + ", ".join(in_report(run, p) for p in parts_holding(run, role, klass, holders[0], target)))
                continue
            if len(holders) > 1:
                run.ambiguous_targets.append(f"{where}: merge_target {target!r} is a section of "
                                         + ", ".join(f"{klass}:{t}" for t in holders))
                continue
            if is_retire(claim) and not holders:
                # A retire (ADR-050 rule 7) of a section no topic holds: retired already, or never there. It renders
                # nothing, so it must not become a topic of its own; said, not an error.
                group.remove(claim)
                run.unresolved_targets.append(f"{where}: retire of {target!r}: no section of {label}/{klass} has "
                                              "that heading; nothing to retire (already retired?)")
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
            moved.append((role, claim["topic"], written_stem(run, role, klass, holders[0])))
            if role is None:
                run.shared_owners[(klass, holders[0])] |= run.shared_owners[(klass, topic)]
    # A CORRECTION FOLLOWS THE CLAIM IT CORRECTS WHEN THAT IS IN THE SAME RUN (j82): another correction (a chain) or the memory
    # itself harvested with it. B names the heading A gives its section, which the corpus holds only once A is applied: in one run B was written as a topic of its own, "unresolved", and the next pass found A's
    # heading and replaced it again, leaving B's text twice. Filed after A in A's slice, B replaces A's section in the order
    # the writer applies them. Repeated until no claim moves, so a chain of any length (and the order of the topics) resolves.
    moving = True
    while moving:
        moving = False
        for (klass, topic), group in sorted(buckets.items()):
            for claim in list(group):
                target = (claim.get("merge_target") or "").strip()
                own = existing_sections(slice_candidates(run, role, klass, topic))
                if not target or is_retire(claim) or target in own or claim_heading(claim) in own:
                    continue   # (its heading standing is a correction already applied, which the pass above sent home)
                if any(target in sections for sections in (existing_sections(p) for p in topics_on_disk(run, role, klass).values())):
                    continue   # a section some topic holds: resolved above, or ambiguous and already refused
                predecessors = sorted({t for (k, t), g in buckets.items() if k == klass and any(
                    c is not claim and claim_heading(c) == target for c in g)} - {topic})
                if len(predecessors) != 1:
                    continue
                label_of = "shared" if role is None else role
                where = f"{label_of}/{klass}:{topic}#{claim_heading(claim)}: merge_target {target!r} names no section"
                run.unresolved_targets[:] = [n for n in run.unresolved_targets if not n.startswith(where)]
                group.remove(claim)
                buckets[(klass, predecessors[0])].append(claim)
                moved.append((role, claim["topic"], written_stem(run, role, klass, predecessors[0])))
                if role is None:
                    run.shared_owners[(klass, predecessors[0])] |= run.shared_owners[(klass, topic)]
                moving = True
    for key in [k for k, g in buckets.items() if not g]:
        del buckets[key]
    return moved


def applied_stems(run: Run) -> list[tuple[str | None, str, str]]:
    """(role, memory name, file stem) of each correction an earlier drain applied and the report still lists: the
    memory was written into that slice, whichever run its links arrive in. The report keeps an entry only while its
    slice holds the text the correction applied."""
    try:
        with open(layout.project_report_path(run.project), encoding="utf-8") as fh:
            previous = json.load(fh)
    except (OSError, ValueError):
        return []
    found: list[tuple[str | None, str, str]] = []
    for entry in (previous.get("applied_corrections") if isinstance(previous, dict) else None) or []:
        if not (isinstance(entry, dict) and isinstance(entry.get("memory"), str) and isinstance(entry.get("slice"), str)):
            continue
        m = re.search(r"memory/(?:domains/)?([^/]+)/", entry["slice"])
        role = None if not m or m.group(1) == "shared" else m.group(1)
        found.append((role, entry["memory"], os.path.basename(entry["slice"]).removesuffix(".md")))
    return found


def point_links(run: Run, moved: list[tuple[str | None, str, str]]) -> None:
    """A `[[memory]]` names a memory, and a claim filed in another topic's slice (a correction) is written under that
    slice's file name, so the link resolved nowhere (a drain's blind review, 2026-10-24). The claims of the role that
    filed it (and of the shared slices) name the slice instead; another role's memory of the same name is not that
    one. The corrections earlier drains applied count as moved too, so a link arriving in a later run, or again, is
    rendered the same way as the run that moved the memory. A name two slices claim is left as written: pointing at
    either would guess."""
    stems: dict[tuple[str | None, str], set[str]] = defaultdict(set)
    for role, name, stem in [*applied_stems(run), *moved]:
        if name != stem:
            stems[(role, name)].add(stem)
    unique = {key: next(iter(found)) for key, found in stems.items() if len(found) == 1}

    def point(claims: list[Any], scopes: tuple[str | None, ...]) -> None:
        names = {name: stem for (r, name), stem in unique.items() if r in scopes}
        if not names:
            return
        pattern = re.compile(r"\[\[(" + "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True)) + r")\]\]")
        for claim in claims:
            claim["body"] = pattern.sub(lambda m: f"[[{names[m.group(1)]}]]", claim["body"])

    def names_for(scopes: tuple[str | None, ...]) -> dict[str, str]:
        return {name: stem for (r, name), stem in unique.items() if r in scopes}

    for role, buckets in run.per_role.items():
        for group in buckets.values():
            point(group, (role, None))
        run.disk_links.append((role, [layout.class_home(k, role, run.project) for k in CLASS_FILES
                                      if k not in layout.IDENTITY_CLASSES], names_for((role, None))))
    for group in run.shared.values():
        point(group, (None,))
    run.disk_links.append((None, sorted({layout.shared_home(k, run.project) for k in CLASS_FILES
                                         if k not in layout.IDENTITY_CLASSES}), names_for((None,))))


def point_disk(run: Run) -> None:
    """Applies the recorded edits (Run.disk_links), after the drain has passed every refusal."""
    for _role, bases, names in run.disk_links:
        point_disk_in(run, bases, names)


def pointed(run: Run, role: str | None, text: str) -> str:
    """`text`, a section on disk, as point_disk will leave it: the pre-pass compares what the drain writes with what the
    section will say, so an unchanged memory arriving in the correction's own run is the same claim, not a collision."""
    for owner, _bases, names in run.disk_links:
        if names and owner == role:   # a role's map already holds the shared names: a second pass would chain them
            text = re.sub(r"\[\[(" + "|".join(re.escape(n) for n in names) + r")\]\]", lambda m: f"[[{names[m.group(1)]}]]", text)
    return text


def point_disk_in(run: Run, bases: list[str], names: dict[str, str]) -> None:
    """The same links in the sections already on disk. A link drained before the correction it names stands raw there,
    and the harvest does not bring an unchanged memory again, so it would stay unresolved; and the memory arriving
    again must read as the text on disk, not as another claim. Only the body is edited, and only a link a map names."""
    if not names:
        return
    pattern = re.compile(r"\[\[(" + "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True)) + r")\]\]")
    for base in sorted(set(bases)):
        for dirpath, _dirs, files in os.walk(base):
            for name in sorted(files):
                path = os.path.join(dirpath, name)
                if not name.endswith(".md") or name == "INDEX.md" or in_report(run, path) in run.held_files:
                    continue
                with open(path, encoding="utf-8") as fh:
                    text = fh.read()
                head = re.match(r"^---\n.*?\n---\n", text, re.S)
                cut = head.end() if head else 0
                body = pattern.sub(lambda m: f"[[{names[m.group(1)]}]]", text[cut:])
                if body == text[cut:]:
                    continue
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(text[:cut] + body)
                if path not in run.written:
                    run.written.append(path)
                run.migrated.append(f"{in_report(run, path)}: links to corrected memories pointed at the slice they were written into")


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
    moved: list[tuple[str | None, str, str]] = []
    for role in sorted(run.per_role):
        moved += resolve_targets(run, role, role, run.per_role[role])
    moved += resolve_targets(run, None, "shared", run.shared)
    point_links(run, moved)
    if run.ambiguous_targets:
        print("MERGE TARGET AMBIGUOUS — a correction names a heading more than one topic, or more than one part of a topic, holds; "
              "the author names the section unambiguously (retitle one of them, or the memory). "
              "This run wrote NOTHING and exits 1.", file=sys.stderr)
        for note in run.ambiguous_targets:
            print(f"  {note}", file=sys.stderr)
        return 1
