"""tools/fabric/assembler/collisions.py — the pre-pass: a claim that disagrees with the corpus stops the drain.
A part of tools/fabric/assemble.py, whose docstring is the contract."""
from __future__ import annotations

import os
import re
import sys
from collections import defaultdict
from typing import Any
from assembler.core import layout, CLASS_FILES, Run, in_report
from assembler.slices import read_existing_slice, OBSERVED_RE, undated, claim_heading, absorbed, claim_block, shares_cue, is_retire
from assembler.targets import existing_sections, slice_candidates, is_carried, pointed


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


def _target(claim: dict[str, Any]) -> str:
    return (claim.get("merge_target") or "").strip()


def _text(claim: dict[str, Any]) -> str:
    return undated(claim_block(claim).split("\n", 1)[1])


def _agent(run: Run, claim: dict[str, Any]) -> str:
    return (run.origins.get((claim.get("evidence") or [""])[0]) or {}).get("agent", "unresolved")


def _siblings(present: dict[str, str], heading: str) -> list[str]:
    """The heading and its kept-both siblings "X (n)" the corpus holds."""
    return [k for k in present if k == heading or re.fullmatch(re.escape(heading) + r" \(\d+\)", k)]


def settle_same_run(run: Run, label: str, klass: str, topic: str, group: list[dict[str, Any]],
                    present: dict[str, str], refused: list[str]) -> None:
    """Two claims of ONE drain that meet in one topic, judged against each other as well as against the corpus.

    The rest of the pre-pass judges a claim against the corpus as it stood before the run, and an authorised
    merge_target is waved through ("the author's own supersession"). Both lost knowledge in a project's drain of
    2026-10-28 (j481, review 5716071440, F1 and F2):

    - A MEMORY'S TEXT THE RUN'S OWN CORRECTION REPLACES is the correction's predecessor, harvested again. Read as
      "standing" it passed as a no-op, and the writer then put it in another budget part, where it came back as the
      corrected text. It is not written, and the report names it and its corrector (`superseded_harvests`).
    - TWO CLAIMS THAT BOTH WRITE ONE HEADING — one under its own heading (which the same-agent rule turns into a
      replacement of the corpus's section), one naming it in merge_target — were applied one over the other, and
      the first one's text left the run with no trace but a correction row for a text that never stood. That is a
      contested heading like the in-drain pair, asked on the claim that names the heading (its key; the other
      claim's key is printed so each is identifiable).
    A retire renders nothing and is not a writer here: it takes part only as the correction that replaces."""
    named = [c for c in group if _target(c) in present]   # the author's own supersession, or a retire
    replaced: dict[str, dict[str, Any]] = {}              # section heading in the corpus -> the claim that removes it
    for c in named:
        for k in ([_target(c)] if is_retire(c) else _siblings(present, _target(c))):   # a retire takes only its heading
            replaced.setdefault(k, c)
    named_ids = {id(c) for c in named}
    for claim in list(group):
        if id(claim) in named_ids:
            continue
        copies = [k for k in _siblings(present, claim_heading(claim)) if undated(present[k]) == _text(claim)]
        if copies and all(k in replaced for k in copies):
            corrector = replaced[copies[0]]
            group.remove(claim)
            run.superseded_harvests.append(
                f"{label}/{klass}:{topic}#{claim_heading(claim)}: memory {claim['topic']!r} is the text of the section "
                f"memory {corrector['topic']!r} {'retires' if is_retire(corrector) else 'corrects'} "
                f"({_target(corrector)!r}) in this drain; not written — update or delete {claim['topic']!r}")
    writers: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for claim in group:
        if is_retire(claim):
            continue
        if _target(claim) in present:
            writers[_target(claim)].append(claim)
        elif not _target(claim) and claim_heading(claim) in present \
                and _text(claim) not in {undated(present[k]) for k in _siblings(present, claim_heading(claim))}:
            writers[claim_heading(claim)].append(claim)
    for heading, claimants in writers.items():
        pivot = next((c for c in reversed(claimants) if _target(c)), None)
        rivals = [c for c in claimants if c is not pivot and _text(c) != _text(pivot)] if pivot else []
        if not rivals:
            continue
        key_id = f"{label}/{klass}:{topic}#{heading}"
        key_of = lambda c: f"{key_id}@{(c.get('evidence') or ['?'])[0][:12]}"   # noqa: E731 — the claim's key, as below
        pivot_key = key_of(pivot)
        decision = run.decisions.get(pivot_key) or run.decisions.get(key_id)
        if decision is None:
            refused.append(
                f"{pivot_key}   (or {key_id} for every pair under the heading; decide on this key)\n"
                f"    two claims of this drain both write {heading!r}; the corpus holds it as: {excerpt(present[heading])}\n"
                + "".join(f"    {key_of(r)}  (observed {r.get('observed_at') or 'undated'}, {_agent(run, r)}, memory {r['topic']!r}"
                          f"{', merge_target' if _target(r) else ', under its own heading'}): {excerpt(_text(r))}\n"
                          for r in rivals)
                + f"    incoming      (observed {pivot.get('observed_at') or 'undated'}, {_agent(run, pivot)}, memory "
                  f"{pivot['topic']!r}, merge_target): {excerpt(_text(pivot))}")
            continue
        row = {"key": pivot_key if pivot_key in run.decisions else key_id, "decision": decision, "agent": _agent(run, pivot),
               "observed_at": pivot.get("observed_at") or "", "memory": pivot["topic"]}
        if decision == "supersede":
            # The pivot stands; each rival's text leaves the run, and the report says so by memory (a rival never
            # reaches the writer, which would have laid the pivot over it with no trace).
            for r in rivals:
                group.remove(r)
                run.applied_decisions.append({"key": key_of(r), "decision": "superseded", "by": pivot_key,
                                              "agent": _agent(run, r), "observed_at": r.get("observed_at") or "",
                                              "memory": r["topic"]})
        elif decision == "drop":
            group.remove(pivot)
        elif decision == "keep-both":
            pivot.pop("merge_target", None)   # a correction written beside the claim, not over it
        run.applied_decisions.append(row)


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
        present = {h: pointed(run, role, t) for h, t in existing_sections(candidates).items()}
        author = sole_author(run, role, klass, topic, candidates) if present else None
        author_any = sole_author(run, role, klass, topic, candidates, own_only=False) if present else None
        settle_same_run(run, label, klass, topic, group, present, refused_collisions)
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
            # ADR-050 rule 11: only the sections that share a cue with the new heading are the retitle's; a claim
            # that shares none is a new section of the topic, however sole the author.
            cue_mates = [h for h in present if shares_cue(heading, h)] if rival is None and heading not in present else []
            retitled = rival is None and heading not in present and author is not None and agent == author and bool(cue_mates)
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
            replaced = [k for k in siblings if k in present] if heading in present else cue_mates
            corpus_dates = [observed_of(present[h]) for h in replaced]
            older = bool(incoming_date) and any(d != "undated" and incoming_date < d for d in corpus_dates)
            same_agent = not open_pair and not older and ((retitled and author is not None and agent == author)
                                           or (heading in present and author_any is not None and agent == author_any))
            rule = None
            if decision is None and same_agent:
                decision, rule = "supersede", "same-agent"
                same_agent_supersedes.append(f"{key_id}  ({agent})")
            if decision == "supersede" and retitled:
                # The new title wins: the sections that share its cue are retired
                # and the claim takes the first one's place.
                claim["_retire"] = list(cue_mates)
                for old in cue_mates:
                    home = next((p for p in candidates if old in read_existing_slice(p)[1]), None)
                    run.retitles.append({"key": key_id, "old_heading": old, "new_heading": heading, "agent": agent,
                                         "project": run.project, "slice": in_report(run, home) if home else "",
                                         "decided_by": rule or "owner"})
            elif decision == "supersede":
                claim["merge_target"] = heading
                claim["_inferred_target"] = True      # the owner's or the same-agent rule's, not the author's: no rule 10 record
            elif decision == "drop":
                group.remove(claim)
            elif decision == "keep-both":
                pass
            elif retitled:
                refused_collisions.append(
                    f"{claim_key}   (retitled? it shares a cue with {agent}'s {', '.join(map(repr, cue_mates))})\n"
                    + "".join(f"    in the corpus (observed {observed_of(present[h])}) as {h!r}: {excerpt(present[h])}\n"
                              for h in cue_mates)
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
