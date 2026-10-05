"""tools/fabric/assembler/collisions.py — the pre-pass: a claim that disagrees with the corpus stops the drain.
A part of tools/fabric/assemble.py, whose docstring is the contract."""
from __future__ import annotations

import os
import re
import sys
from collections import defaultdict
from typing import Any
from assembler.core import layout, CLASS_FILES, Run
from assembler.slices import read_existing_slice, OBSERVED_RE, undated, claim_heading, absorbed, claim_block
from assembler.targets import existing_sections, slice_candidates, is_carried


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
