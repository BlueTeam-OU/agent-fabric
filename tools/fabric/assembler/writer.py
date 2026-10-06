"""tools/fabric/assembler/writer.py — the slices written: merge mode, the budget split, part one, carried copies.
A part of tools/fabric/assemble.py, whose docstring is the contract."""
from __future__ import annotations

import functools
import json
import os
import re
from collections import defaultdict
from typing import Callable, Any
from assembler.core import layout, TIER1, CHARS_PER_TOKEN, CLASS_FILES, origin_key, render_frontmatter, hygiene_check, hygiene_substitute, DESCRIPTION_MAX, Run, base_for, in_report
from assembler.slices import retire_in_siblings, remove_sections, read_existing_slice, OBSERVED_RE, undated, claim_heading, absorbed, claim_block
from assembler.targets import existing_sections, is_budget_part, slice_candidates, is_carried


def clip_description(run: Run, description: str, where: str) -> str:
    """The description is the retrieval cue an index shows; the schema
    caps it. A cue that runs on is clipped at a word boundary and the
    clip reported, rather than failing the whole drain on lint."""
    if len(description) <= DESCRIPTION_MAX:
        return description
    cut = description[: DESCRIPTION_MAX - 1].rsplit(" ", 1)[0].rstrip(" ,;:—-")
    if os.path.isabs(where):
        where = in_report(run, where)
    run.clipped_descriptions.append(f"{where}: description clipped from {len(description)} to {len(cut) + 1} characters")
    return cut + "…"


def write_slice(
    run: Run, directory: str, filename: str, role: str, klass: str, claims: list[dict[str, Any]],
    description: str, shared_with: list[str] | None = None, topic: str | None = None,
) -> None:
    """`topic` is recorded in the frontmatter of every file that is one
    topic's (is_budget_part reads it); the flat class file, which holds
    several memories, is written without one."""
    os.makedirs(directory, exist_ok=True)
    description = clip_description(run, description, os.path.join(directory, filename))
    evidence = sorted({h for c in claims for h in c.get("evidence", [])})
    origin_set = {
        origin_key(run.origins.get(h) or {"agent": "unresolved", "host": "unknown"})
        for h in evidence
    }
    scope = "domain-only" if all(
        c.get("knowledge_scope") == "domain-only" for c in claims
    ) else "full"
    meta = {
        "role": role,
        "class": klass,
        "description": description,
        "tier": 1 if klass in TIER1 else 2,
        "knowledge_scope": scope,
        "distilled_at": run.args.stamp,
        "origin": [dict(k) for k in sorted(origin_set)],
        "derived_from": evidence,
    }
    if shared_with:
        meta["shared_with"] = sorted(shared_with)
    if topic is not None:
        meta["topic"] = topic
    path = os.path.join(directory, filename)

    # MERGE MODE. A drain renders only what it admitted this cycle, so
    # writing that alone would delete everything earlier cycles learned.
    # Sections already on disk are carried forward; a claim naming an
    # existing heading in `merge_target` replaces that section (the rubric
    # prefers strengthening a claim over adding beside it); anything else
    # is appended. Provenance unions, so a merged claim keeps the evidence
    # both drains found for it.
    previous_meta, previous_sections = read_existing_slice(path)
    collided: list[str] = []
    resolved: list[str] = []
    blocks: dict[str, str] = dict(previous_sections)
    order: list[str] = list(previous_sections)
    def retire_elsewhere(target: str) -> bool:
        """THE SECTION LIVES IN ANOTHER PART of this topic (a slice
        split by budget): the owner's supersede retires it there and
        the superseding text lands here. Authorising only a target in
        the part being written exited 0 with both texts standing in
        two files (connected reviewer, 2026-09-20). Every sibling
        touched is written and reported."""
        if topic is None:
            touched = retire_in_siblings(directory, filename, target, clip=functools.partial(clip_description, run))
        else:
            owner = None if role == "shared" else role
            touched = retire_in_siblings(
                directory, filename, target, clip=functools.partial(clip_description, run),
                stem=f"{klass}-{topic}" if owner is None else topic,
                is_part=lambda p: is_budget_part(run, owner, klass, p, topic))
        for tpath, what in touched:
            run.retired_in.append(f"{in_report(run, tpath)}: '{target}' {what}")
            # `written` counts files on disk once: a rewritten
            # sibling joins it, a removed one leaves it.
            if what == "rewritten" and tpath not in run.written:
                run.written.append(tpath)
            if what == "removed" and tpath in run.written:
                run.written.remove(tpath)
            # A sibling this run already indexed keeps a stale
            # line otherwise — a link to a removed file, or the
            # old cue: drop it, and the on-disk sweep re-lists a
            # rewritten part by its frontmatter.
            rel = layout.link_rel(tpath, run.project)
            if role == "shared":
                for owner in list(run.shared_index):
                    run.shared_index[owner] = [e for e in run.shared_index[owner] if e["path"] != rel]
            else:
                run.index_entries[role] = [e for e in run.index_entries[role] if e["path"] != rel]
        return bool(touched)

    for claim in claims:
        heading = claim_heading(claim)
        legacy = absorbed(blocks, claim)
        if legacy:
            # The claim as a pre-demotion slice split it: put it back
            # together, keeping a date only the old text recorded.
            whole = claim_block(claim).split("\n", 1)[1].strip()
            old_date = OBSERVED_RE.search(blocks[legacy[-1]])
            if old_date and not OBSERVED_RE.search(whole):
                whole += "\n\n" + old_date.group(0).strip()
            for stale in legacy[1:]:
                del blocks[stale]
                order.remove(stale)
            blocks[heading] = whole
        retire = claim.get("_retire") or []
        if retire:
            # A retitle the owner superseded: the old sections go
            # wherever they sit, and the new heading takes the place of
            # the first one this part holds, so the slice keeps its order.
            slot = next((h for h in retire if h in blocks), None)
            for old in retire:
                if old in blocks:
                    del blocks[old]
                    if old != slot:
                        order.remove(old)
                else:
                    retire_elsewhere(old)
            if slot is not None:
                order[order.index(slot)] = heading
            resolved.extend(retire)
        target = (claim.get("merge_target") or "").strip()
        authorised = bool(target and target in blocks)
        if target and not authorised and retire_elsewhere(target):
            authorised = True
            resolved.append(target)
        if authorised:
            # Replacement is opt-in, and this is the opt-in. The claim's
            # own heading takes the target's place: keeping the target's
            # left a corrected section under its stale cue ("#851 is
            # merged" over "Released."), disagreeing with the slice's own
            # description (a drain's review, 2026-09-26).
            # A target retired from another part leaves nothing here to
            # rename: the claim's heading is appended under its own
            # name (writing it as the target put the stale cue back,
            # a drain's blind review, 2026-09-26). The target's name
            # is kept only where the claim's own heading already holds
            # another section of this part, which it must not overwrite.
            if heading != target and heading not in blocks:
                if target in blocks:
                    blocks[heading] = blocks.pop(target)
                    order[order.index(target)] = heading
            else:
                heading = target
            # CONSOLIDATION RETIRES THE SUFFIXED SIBLINGS.
            #
            # A collision leaves "X" and "X (2)" side by side and
            # records "X" so the drain report can ask for a
            # merge_target. Naming it rewrote "X" alone: "X (2)"
            # stayed in the body forever and the recorded collision
            # was unioned forward on every later drain, so the
            # remedy the report prescribes could never clear the
            # report. An explicit merge_target, an owner's supersede or
            # the same-agent rule reaches here — each an instruction to
            # replace the heading, and the rule only for text no older
            # than any sibling it retires.
            sibling = 2
            while f"{target} ({sibling})" in blocks:
                stale = f"{target} ({sibling})"
                del blocks[stale]
                if stale in order:
                    order.remove(stale)
                sibling += 1
            resolved.append(target)
        base_heading = heading
        rendered = claim_block(claim).split("\n", 1)[1].strip()
        if not authorised and heading in blocks and undated(blocks[heading]) != undated(rendered):
            # A heading that already holds DIFFERENT text is a second
            # claim, not this one again. Overwriting on a bare title match
            # made replacement implicit and silent — a drain deleting a
            # finding nobody asked it to touch. Keep both and report it.
            # (Identical text is simply the same claim re-rendered, which
            # must stay a no-op or re-assembly would duplicate everything;
            # identical text under a new or moved date is the same claim
            # and takes the date.)
            suffix = 2
            while f"{heading} ({suffix})" in blocks and undated(blocks[f"{heading} ({suffix})"]) != undated(rendered):
                suffix += 1
            collided.append(base_heading)
            heading = f"{heading} ({suffix})"
        if heading not in order:   # a retitle already put it in its predecessor's place
            order.append(heading)
        # Equal text arriving WITHOUT a date (a bundle from before sections
        # were dated) keeps the date the corpus already recorded; a
        # recorded value is never dropped silently.
        if heading in blocks and not OBSERVED_RE.search(rendered) and OBSERVED_RE.search(blocks[heading]) \
           and undated(blocks[heading]) == undated(rendered):
            rendered = blocks[heading]
        blocks[heading] = rendered

    # SCOPE UNIONS WITH WHAT IS CARRIED, and `full` wins.
    #
    # `scope` above is computed from THIS drain's claims alone, because
    # the file on disk had not been read yet. A cycle contributing only
    # domain-only claims to a slice that already holds a full-scope
    # section therefore relabelled the whole file `domain-only` while
    # the system-specific text was still sitting in it — defeating the
    # cross-project boundary the field exists to draw.
    #
    # Erring toward `full` is the safe direction: it over-restricts what
    # may cross a project boundary, where the opposite leaks.
    if previous_sections and previous_meta.get("knowledge_scope") == "full":
        meta["knowledge_scope"] = "full"

    carried = [h for h in previous_meta.get("derived_from", []) or []
               if isinstance(h, str)]
    meta["derived_from"] = sorted(set(evidence) | set(carried))
    # Origins must union with the carried evidence they belong to,
    # otherwise a preserved hash lists no clone or host and the trail it
    # exists to provide is broken exactly when the store has been cleared.
    prior_origin = {
        origin_key(o) for o in previous_meta.get("origin", []) or [] if isinstance(o, dict)
    }
    meta["origin"] = [dict(k) for k in sorted(origin_set | prior_origin)]
    # An unresolved collision is recorded in the slice that has it, so the
    # warning is a fact the file states rather than a shape inferred from
    # its headings — an authored document may legitimately carry "X" and
    # "X (2)" without anything having collided.
    carried_collisions = [c for c in previous_meta.get("collisions", []) or []
                          if isinstance(c, str)]
    # A resolved title stops being reported. Without this the record
    # was write-only: unioned forward every drain, with no path that
    # ever removed one, so `title_collisions` in the drain report
    # named pairs that no longer existed.
    outstanding = (set(collided) | set(carried_collisions)) - set(resolved)
    if outstanding:
        meta["collisions"] = sorted(outstanding)

    body = "\n\n".join(f"## {h}\n\n{blocks[h]}" for h in order) + "\n"
    # Carried text (a slice written before a pattern existed) is
    # substituted the same way, and named.
    body, notes = hygiene_substitute(body, in_report(run, path))
    run.redactions.extend(notes)
    if isinstance(meta.get("description"), str):
        meta["description"], notes = hygiene_substitute(meta["description"], in_report(run, path) + " description")
        run.redactions.extend(notes)
    text = render_frontmatter(meta) + "\n\n" + body
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text.rstrip() + "\n")
    if path not in run.written:   # a retire may have rewritten this part earlier in the run
        run.written.append(path)
    run.problems.extend(hygiene_check(body, in_report(run, path)))


def carried_chars(claims: list[dict[str, Any]], *candidates: str) -> int:
    """How much text merge mode will carry into the FIRST part, BEYOND
    what this drain's claims already are.

    Sized from whichever candidate path actually exists: the layout of a
    slice depends on whether it ever split, so the same topic can live at
    `<class>.md` or `<class>/<topic>.md` and only the tree knows which.

    A section that IS one of this drain's claims re-rendered — same
    heading, same text, the rule write_slice applies — costs nothing:
    write_slice writes it once. Counting it here as well counted every
    re-assembled claim twice, so a slice past half its budget split on
    the second run of the same drain, and the second part received the
    same claims as new sections — the `-2` copies of 2026-09-17. Text
    alone is not identity: two claims with the same body under
    different titles are two sections, and both are carried.

    A section a claim REPLACES — its merge_target (the owner's
    supersede included), or a retitle's old heading — is not carried
    either. Counted, it pushed its own replacement into part two,
    whose supersede then retired part one's only section and removed
    `<topic>.md` (a drain of 2026-09-25).
    """
    incoming = {(claim_heading(c), undated(claim_block(c).split("\n", 1)[1])) for c in claims}
    replaced = {(c.get("merge_target") or "").strip() for c in claims} | \
        {h for c in claims for h in c.get("_retire") or []}
    for path in candidates:
        _meta, sections = read_existing_slice(path)
        if sections:
            itself = {h for c in claims for h in absorbed(sections, c)}
            return sum(len(h) + len(t) + 8 for h, t in sections.items()
                       if (h, undated(t)) not in incoming and h not in replaced and h not in itself)
    return 0


def holds_one_of(claims: list[dict[str, Any]]) -> Callable[[str], bool]:
    """Before writing, a numbered part is this topic's when it holds
    a section one of the topic's incoming claims names — its heading,
    its merge_target or a retitle's old heading."""
    names = {claim_heading(c) for c in claims} | {(c.get("merge_target") or "").strip() for c in claims} \
        | {h for c in claims for h in c.get("_retire") or []}
    return lambda path: bool(names & set(read_existing_slice(path)[1]))


def restore_part_one(run: Run, directory: str, stem: str, topic: str, role: str,
                     eligible: Callable[[str], bool]) -> None:
    """PART ONE IS ALWAYS `<stem>.md` while the topic has any section:
    it is the name every `[[topic]]` link and cue points at. A part
    one removed by a retire (or lost by an earlier drain) is restored
    by moving the lowest remaining part into its place, reported.
    Only a part `eligible` says is this topic's moves: `<stem>-<n>.md`
    may as well be another memory whose name ends in a number, and
    renaming it would take that topic's file away; a part whose
    frontmatter names another topic is that topic's, whatever it says."""
    first = os.path.join(directory, f"{stem}.md")
    if os.path.exists(first) or not os.path.isdir(directory):
        return
    parts = sorted((int(m.group(1)), n) for n in os.listdir(directory)
                   if (m := re.fullmatch(re.escape(stem) + r"-(\d+)\.md", n))
                   and read_existing_slice(os.path.join(directory, n))[0].get("topic") in (None, topic)
                   and eligible(os.path.join(directory, n)))
    if not parts:
        return
    lowest = os.path.join(directory, parts[0][1])
    os.replace(lowest, first)
    run.migrated.append(f"{role}: {parts[0][1]} -> {stem}.md (part one restored)")
    if lowest in run.written:
        run.written[run.written.index(lowest)] = first
    old, new = layout.link_rel(lowest, run.project), layout.link_rel(first, run.project)
    for entries in list(run.index_entries.values()) + list(run.shared_index.values()):
        for entry in entries:
            if entry["path"] == old:
                entry["path"] = new


def split_by_budget(
    run: Run, claims: list[dict[str, Any]], carried: int = 0
) -> list[list[dict[str, Any]]]:
    """Keep a slice inside its budget; a file nobody can afford to read is
    the same as a file nobody reads.

    `carried` is what merge mode will re-emit from the file on disk.
    Sizing this drain's claims ALONE is what let a slice grow without
    bound: each cycle split its own contribution correctly, then
    write_slice added every earlier section back underneath, so the file
    crept past the budget across drains while no single run looked wrong
    — until the mandatory lint budget check failed on a tree nobody had
    touched.
    """
    limit = run.args.budget * CHARS_PER_TOKEN
    groups: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    size = carried
    for claim in claims:
        claim_size = len(claim["body"]) + len(claim.get("title") or "") + 40
        # `carried` counts toward the first group, so a file already at
        # its limit pushes the next claim into a new part instead of
        # overflowing — which is why an EMPTY first group is a legitimate
        # outcome here, meaning "part one is full of carried text".
        if size + claim_size > limit and (current or carried):
            groups.append(current)
            current, size = [], 0
        current.append(claim)
        size += claim_size
    if current or not groups:
        groups.append(current)
    return groups


def described(path: str, fallback: str) -> str:
    with open(path, encoding="utf-8") as fh:
        head = fh.read(2000)
    match = re.search(r"^description:\s*(.+)$", head, re.M)
    description = match.group(1).strip() if match else fallback
    if description.startswith('"'):
        try:
            description = json.loads(description)
        except json.JSONDecodeError:
            description = description.strip('"')
    return description


def drop_carried_copies(run: Run, role: str, klass: str, directory: str, topic: str) -> None:
    """A section standing both in the topic's own file and, word for
    word, in a carried file is one claim written twice — what a drain
    before the carried file was visible to the pre-pass left behind.
    The carried copy goes; a carried file left with no section goes
    too, and both are reported in `migrated`."""
    mine = existing_sections(slice_candidates(run, role, klass, topic))
    if not mine or not os.path.isdir(directory):
        return
    for name in sorted(os.listdir(directory)):
        if not name.endswith(".md") or not is_carried(klass, name[:-3]):
            continue
        path = os.path.join(directory, name)
        _meta, sections = read_existing_slice(path)
        copies = [h for h, t in sections.items() if h in mine and undated(mine[h]) == undated(t)]
        if not copies:
            continue
        what = remove_sections(path, copies, copies, functools.partial(clip_description, run))
        rel = f"{CLASS_FILES[klass]}/{name}"
        for h in copies:
            run.migrated.append(f"{role}/{klass}: {h!r} dropped from {rel}, it stands in {CLASS_FILES[klass]}/{topic}.md")
        if what == "removed":
            run.migrated.append(f"{role}/{klass}: {rel} removed, no section left")
            if path in run.written:
                run.written.remove(path)
            run.index_entries[role] = [e for e in run.index_entries[role]
                                   if e["path"] != layout.link_rel(path, run.project)]
        elif path not in run.written:
            run.written.append(path)


def write_shared(run: Run) -> None:
    # Shared slices first, so role indexes can point at them. A shared slice
    # lives with its class: field knowledge under memory/shared/, project
    # knowledge under the project's shared/.
    for (klass, topic), claims in sorted(run.shared.items()):
        if not claims:
            continue   # every claim dropped by the owner: the slice stays as it was
        owners = sorted(run.shared_owners[(klass, topic)])
        shared_dir = layout.shared_home(klass, run.project)
        restore_part_one(run, shared_dir, f"{klass}-{topic}", topic, "shared", holds_one_of(claims))
        prior = carried_chars(claims, os.path.join(shared_dir, f"{klass}-{topic}.md"))
        for part, group in enumerate(split_by_budget(run, claims, prior), start=1):
            suffix = "" if part == 1 else f"-{part}"
            filename = f"{klass}-{topic}{suffix}.md"
            description = clip_description(run,
                (group[0].get("title") if group else None)
                or f"{topic.replace('-', ' ')} ({klass})",
                os.path.join(shared_dir, filename))
            write_slice(run, shared_dir, filename, "shared", klass, group, description, owners, topic=topic)
            for owner in owners:
                run.shared_index[owner].append(
                    {"path": layout.link_rel(os.path.join(shared_dir, filename), run.project),
                     "description": description, "class": klass}
                )
        restore_part_one(run, shared_dir, f"{klass}-{topic}", topic, "shared", lambda p: p in run.written)


def write_role(run: Run, role: str) -> None:
    buckets = run.per_role.get(role, {})
    proj_dir = layout.project_dir(run.project, role)
    os.makedirs(proj_dir, exist_ok=True)
    by_class: dict[str, list[tuple[str, list[dict[str, Any]]]]] = defaultdict(list)
    for (klass, topic), claims in sorted(buckets.items()):
        by_class[klass].append((topic, claims))

    for klass, topics in sorted(by_class.items()):
        base = base_for(run, role, klass)
        # The layout is a property of the TREE, not of this drain. Deciding
        # it from `len(topics)` means a class that already has a `<class>/`
        # directory gains a flat `<class>.md` the moment a later drain
        # touches exactly one topic in it — and the activator takes the
        # directory branch and skips the flat file, so a tier-1 workflow
        # slice written that way is never loaded at activation. That is the
        # defect 08dd4164 fixed in code and this reintroduced through
        # content: two roles shipped workflow.md files no session would read.
        plan = run.class_plan[(role, klass)]
        multi = plan["split"]
        # SWITCHING TO THE DIRECTORY SHAPE MOVES THE FLAT FILE IN. The
        # activator loads only the directory once it exists, so a flat
        # `<class>.md` left beside `<class>/` is unreachable knowledge,
        # and its size was being counted as carried text for whatever
        # topic came first — which produced an empty "part one" with no
        # provenance. The flat file may hold several topics' sections
        # (the crossref says which), so it is not split: it moves whole,
        # named for the one topic when there is one, else as the carried
        # file of its class, and its description keeps it findable.
        flat = os.path.join(base, f"{CLASS_FILES[klass]}.md")
        if multi and os.path.exists(flat):
            name = f"{plan['flat_topic']}.md"
            os.makedirs(os.path.join(base, CLASS_FILES[klass]), exist_ok=True)
            os.replace(flat, os.path.join(base, CLASS_FILES[klass], name))
            run.migrated.append(f"{role}/{klass}: {CLASS_FILES[klass]}.md -> {CLASS_FILES[klass]}/{name}")
        for topic, claims in topics:
            if not claims:
                continue   # every claim dropped by the owner: the slice stays as it was
            if multi:
                restore_part_one(run, os.path.join(base, CLASS_FILES[klass]), topic, topic, role, holds_one_of(claims))
            # Both candidate layouts, because only the tree knows whether
            # this topic has split before.
            prior = carried_chars(
                claims,
                os.path.join(base, f"{CLASS_FILES[klass]}.md"),
                os.path.join(base, CLASS_FILES[klass], f"{topic}.md"),
            )
            groups = split_by_budget(run, claims, prior)
            # An empty group means "part one is full of carried text":
            # legitimate when the file on disk exists, a phantom header
            # otherwise. A claim larger than the budget cannot be split
            # (claims are atomic); it is written whole and REPORTED, so
            # the author splits the memory — lint says the same thing.
            limit = run.args.budget * CHARS_PER_TOKEN
            for claim in claims:
                if len(claim["body"]) > limit:
                    run.oversized.append(f"{role}/{klass}:{topic}: one claim is ~{len(claim['body']) // CHARS_PER_TOKEN} tokens, "
                                     f"over the {run.args.budget} budget; split the memory it came from")
            for part, group in enumerate(groups, start=1):
                suffix = "" if part == 1 else f"-{part}"
                if not group:
                    exists = (os.path.exists(os.path.join(base, CLASS_FILES[klass], f"{topic}{suffix}.md"))
                              or os.path.exists(os.path.join(base, f"{CLASS_FILES[klass]}.md")))
                    if not exists:
                        continue
                if multi or len(groups) > 1:
                    directory = os.path.join(base, CLASS_FILES[klass])
                    filename = f"{topic}{suffix}.md"
                else:
                    directory = base
                    filename = f"{CLASS_FILES[klass]}.md"
                description = clip_description(run,
                    (group[0].get("title") if group else None)
                    or f"{topic.replace('-', ' ')} ({klass})",
                    os.path.join(directory, filename))
                if is_carried(klass, topic) and os.path.exists(os.path.join(directory, filename)):
                    # The carried file's cue is the one it moved with:
                    # it names several topics, never one claim's title.
                    description = described(os.path.join(directory, filename), description)
                write_slice(run, directory, filename, role, klass, group, description,
                            topic=topic if directory != base else None)
                run.index_entries[role].append(
                    {"path": layout.link_rel(os.path.join(directory, filename), run.project),
                     "description": description, "class": klass}
                )
            restore_part_one(run, os.path.join(base, CLASS_FILES[klass]), topic, topic, role, lambda p: p in run.written)
            if multi and not is_carried(klass, topic):
                drop_carried_copies(run, role, klass, os.path.join(base, CLASS_FILES[klass]), topic)
