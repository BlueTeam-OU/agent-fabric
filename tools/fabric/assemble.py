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
import glob
import re
import sys
from collections import defaultdict
from typing import Callable, Any

# The parts are found beside this file however it is run: as the command,
# or by its path (tests/test_harvest_memory.py, tests/test_assemble.py).
sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))

from assembler.core import layout, TIER1, CHARS_PER_TOKEN, CLASS_FILES, normalize_artifact, origin_key, render_frontmatter, hygiene_check, hygiene_substitute, DESCRIPTION_MAX, Run, base_for, in_report  # noqa: E402
from assembler.slices import merge_reports, scan_collisions, retire_in_siblings, remove_sections, read_existing_slice, OBSERVED_RE, undated, claim_heading, absorbed, claim_block  # noqa: E402
from assembler.intake import parse_args, open_layout, read_claims, screen_hygiene, bucket_claims, load_decisions  # noqa: E402


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


def observed_of(text: str) -> str:
    m = OBSERVED_RE.search(text)
    return m.group(1) if m else "undated"


def excerpt(text: str) -> str:
    line = " ".join(OBSERVED_RE.sub("", text).split())
    return line if len(line) <= 160 else line[:157] + "..."


def sole_author(run: Run, role: str | None, klass: str, topic: str, paths: list[str], own_only: bool = True) -> str | None:
    """The one agent every section of the topic came from, or None.

    Only the topic's OWN files answer: `<class>/<topic>.md` and its
    budget parts (or the shared `<class>-<topic>.md` and its parts),
    which no other memory is ever written into. The flat class file
    is shared by every memory of its class until the class splits,
    and a carried file by every memory it moved with; one agent
    having written all of either says nothing about which memory a
    section was. Reading the flat file as the topic's — guarded by
    the crossref, which names only slices whose evidence had
    references — made a second memory of one agent a "retitle" of
    the first, and the same-agent rule deleted the first (a drain's
    blind review, 2026-09-26). An origin with no agent (a clone
    record, an unresolved row) cannot be the same author as anyone.

    `own_only=False` answers for a file shared by several memories: it
    serves the same-HEADING supersede, which replaces one section and
    cannot touch another memory's — only the retitle inference, which
    retires every section it reads, needs the topic's own files (the
    re-review of #41, 2026-09-26)."""
    if not paths:
        return None
    if own_only and role is not None and is_carried(klass, topic):
        return None
    if role is None:
        own_dir, stem = layout.shared_home(klass, run.project), f"{klass}-{topic}"
    else:
        own_dir, stem = os.path.join(layout.class_home(klass, role, run.project), CLASS_FILES[klass]), topic
    own = re.compile(re.escape(stem) + r"(-\d+)?\.md")
    if own_only and any(os.path.dirname(p) != own_dir or not own.fullmatch(os.path.basename(p)) for p in paths):
        return None
    agents: set[str] = set()
    for path in paths:
        meta, _sections = read_existing_slice(path)
        for item in meta.get("origin") or []:
            agent = item.get("agent") if isinstance(item, dict) else None
            if not agent or agent == "unresolved":
                return None
            agents.add(agent)
    return agents.pop() if len(agents) == 1 else None


def check_collisions(run: Run) -> int | None:
    refused_collisions: list[str] = []
    groups_to_check: list[tuple[str | None, str, tuple[str, str], list[dict[str, Any]]]] = []
    for role, topics in run.per_role.items():
        for key, group in topics.items():
            groups_to_check.append((role, role, key, group))
    for key, group in run.shared.items():
        groups_to_check.append((None, "shared", key, group))
    same_agent_supersedes: list[str] = []
    for role, label, (klass, topic), group in groups_to_check:
        candidates = slice_candidates(run, role, klass, topic)
        present = existing_sections(candidates)
        author = sole_author(run, role, klass, topic, candidates) if present else None
        author_any = sole_author(run, role, klass, topic, candidates, own_only=False) if present else None
        # A HEADING TWO CLAIMS OF THIS DRAIN DISAGREE UNDER is contested
        # whichever comes first: judged claim by claim, a pair whose second
        # claim equalled the corpus passed as a no-op after the first had
        # superseded it, and the old text came back as "X (2)" (the
        # re-review of #41, 2026-09-26).
        texts_by_heading: dict[str, list[str]] = defaultdict(list)
        for c in group:
            t = undated(claim_block(c).split("\n", 1)[1])
            if t not in texts_by_heading[claim_heading(c)]:
                texts_by_heading[claim_heading(c)].append(t)
        contested = {h for h, ts in texts_by_heading.items() if len(ts) > 1}
        for claim in list(group):
            heading = claim_heading(claim)
            rendered = undated(claim_block(claim).split("\n", 1)[1])
            target = (claim.get("merge_target") or "").strip()
            if target and target in present:
                continue   # the author's own supersession: authorised
            # TWO CLAIMS OF THIS DRAIN UNDER ONE HEADING are asked about
            # whether or not the corpus holds the heading too. Looked for
            # only where the corpus did not, a pair under a heading the
            # corpus held was superseded twice by the same-agent rule and
            # the later claim won silently (a drain's blind review,
            # 2026-09-26). The pair is found over the whole group
            # (`contested`, above), so its order does not matter; a pair
            # whose texts all stand already (kept both, re-emitted) is no
            # question.
            # Present already — under its heading or as a kept-both
            # sibling "X (n)" — is the same claim again, whatever its date.
            siblings = [heading] + [k for k in present if re.fullmatch(re.escape(heading) + r" \(\d+\)", k)]
            standing = {undated(present[k]) for k in siblings if k in present}
            # A pair whose every text already stands (kept both, re-emitted)
            # is no question; otherwise the first claim under the heading is
            # judged against the corpus WITHOUT the same-agent shortcut, and
            # every later one against the first.
            open_pair = heading in contested and not set(texts_by_heading[heading]) <= standing
            first_of_pair = open_pair and next(c for c in group if claim_heading(c) == heading) is claim
            in_drain = open_pair and not first_of_pair
            if not in_drain and rendered in standing:
                continue
            if not in_drain and absorbed(present, claim):
                continue   # itself, as a slice written before body headings were demoted split it
            if in_drain:
                other = next(c for c in group if claim_heading(c) == heading)
                rival = undated(claim_block(other).split("\n", 1)[1])
                rival_date = other.get("observed_at") or "undated"
                if rival == rendered:
                    # The first claim's text again: nothing to decide, and
                    # nothing to write — that claim carries it and the
                    # owner's decision on it governs. Left in the group,
                    # it escaped the decision and came back as "X (2)"
                    # (the re-review of #41, 2026-09-26). Its EVIDENCE is
                    # not a repeat: folded into the first claim's (after
                    # its first hash, which keys it), so the slice still
                    # records every agent that asserted the text and a
                    # later drain does not read a two-agent topic as one's.
                    other["evidence"] = list(other.get("evidence") or []) + [
                        e for e in (claim.get("evidence") or []) if e not in (other.get("evidence") or [])]
                    group.remove(claim)
                    continue
            else:
                rival = present.get(heading)
                rival_date = observed_of(rival) if rival is not None else None
            agent = (run.origins.get((claim.get("evidence") or [""])[0]) or {}).get("agent", "unresolved")
            # A RETITLED MEMORY IS THE SAME MEMORY. A topic is a memory's
            # file name and its heading the memory's description; an agent
            # that rewrites a tracker ("#851 OPEN" -> "#851 MERGED") brings
            # a new heading into a topic whose every section it wrote
            # itself, and appending left the stale section standing with
            # both cues in the index (a drain's blind review, 2026-09-25).
            # Which one is true is the owner's call, asked like any other
            # collision; a claim whose merge_target named a section was
            # authorised above, and a topic several agents wrote is several
            # memories, where a new heading is simply new.
            retitled = rival is None and heading not in present and author is not None and agent == author
            if rival is None and not retitled:
                continue
            key_id = f"{label}/{klass}:{topic}#{heading}"
            # A key per incoming claim as well as per heading: with three
            # claims under one heading the owner may supersede with one
            # and drop another, which one key for the pair cannot say.
            # The claim's key is its first evidence hash; the heading key
            # is the default for every pair under it.
            claim_key = f"{key_id}@{(claim.get('evidence') or ['?'])[0][:12]}"
            decision = run.decisions.get(claim_key) or run.decisions.get(key_id)
            # AN AGENT'S NEWER TEXT REPLACES ITS OWN OLDER TEXT (the owner,
            # 2026-09-26). Every same-agent pair the owner was asked about
            # was the author's later version — a tracker closed, a count
            # updated — and was superseded, 34 times out of 34. So a
            # collision whose every corpus section the incoming claim's own
            # agent wrote supersedes without asking; it is printed and
            # recorded like any decision. Two agents' texts still stop the
            # drain, and so do two claims of this drain under one heading,
            # where which is newer is not the corpus's to say.
            # NEWER, as the rule says: a replayed or delayed bundle whose
            # claim is dated before the section it would replace is asked
            # about, not applied (the review of #41, 2026-09-26). An undated
            # side cannot be compared and does not block the rule.
            incoming_date = claim.get("observed_at") or ""
            # Every section the supersede would remove: the heading and its
            # kept-both siblings "X (n)", which the replace retires too; a
            # retitle retires the whole topic (the re-review of #41).
            replaced = [k for k in siblings if k in present] if heading in present else list(present)
            corpus_dates = [observed_of(present[h]) for h in replaced]
            older = bool(incoming_date) and any(d != "undated" and incoming_date < d for d in corpus_dates)
            same_agent = not open_pair and not older and ((retitled and author is not None and agent == author)
                                           or (heading in present and author_any is not None and agent == author_any))
            rule = None
            if decision is None and same_agent:
                decision, rule = "supersede", "same-agent"
                same_agent_supersedes.append(f"{key_id}  ({agent})")
            if decision == "supersede" and retitled:
                # The new title wins: every section of the topic is retired
                # and the claim takes the first one's place.
                claim["_retire"] = list(present)
            elif decision == "supersede":
                claim["merge_target"] = heading
            elif decision == "drop":
                group.remove(claim)
            elif decision == "keep-both":
                pass
            elif retitled:
                refused_collisions.append(
                    f"{claim_key}   (retitled? every section of the topic is {agent}'s)\n"
                    + "".join(f"    in the corpus (observed {observed_of(present[h])}) as {h!r}: {excerpt(present[h])}\n"
                              for h in present)
                    + f"    incoming      (observed {claim.get('observed_at') or 'undated'}, {agent}) "
                      f"as {heading!r}: {excerpt(rendered)}"
                )
                continue
            else:
                refused_collisions.append(
                    f"{claim_key}   (or {key_id} for every pair under the heading)\n"
                    f"    {'in this drain ' if in_drain else 'in the corpus '}(observed {rival_date}): {excerpt(rival)}\n"
                    f"    incoming      (observed {claim.get('observed_at') or 'undated'}, {agent}): {excerpt(rendered)}"
                )
                continue
            run.applied_decisions.append({"key": claim_key if claim_key in run.decisions else key_id, "decision": decision,
                                      "agent": agent, "observed_at": claim.get("observed_at") or "",
                                      **({"rule": rule} if rule else {})})
    if same_agent_supersedes and not refused_collisions:
        print("SUPERSEDED, same agent (an agent's newer text replaces its own older text; the owner, 2026-09-26):",
              file=sys.stderr)
        for note in same_agent_supersedes:
            print(f"  {note}", file=sys.stderr)
    if refused_collisions:
        print("SUPERSEDING? — a claim disagrees with a section already in the corpus; the owner decides "
              "which is true. This run wrote NOTHING and exits 1.", file=sys.stderr)
        for note in refused_collisions:
            print(f"  {note}", file=sys.stderr)
        print("\nRe-run with --collision-decisions FILE, one entry per line above (the claim's own key,\n"
              "or the heading's key for every pair under it):\n"
              "  {\"<role>/<class>:<topic>#<heading>[@<evidence>]\": \"supersede\" | \"keep-both\" | \"drop\"}\n"
              "  supersede: the incoming text replaces the section and retires its siblings;\n"
              "  keep-both: both stand, side by side, dated;  drop: the incoming claim is wrong.", file=sys.stderr)
        return 1


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
