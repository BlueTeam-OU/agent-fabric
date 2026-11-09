"""tools/fabric/assembler/anchorkeep.py — an anchor that resolves is not replaced by one that does not.
A part of tools/fabric/assemble.py, whose docstring is the contract.

A section is a claim rendered with its anchors (ADR-050 rule 1). A repair of an anchor made in the corpus (the drain of
2026-11-08 turned about thirty `path::text` into `<project>:path::text`) is undone by the next harvest of the memory, which
still writes the old anchor: the claim then differs from the section only by that line, and the same-agent rule or the
owner's supersede replaced the repaired anchor with the one that names nothing. Before the pre-pass judges the claims,
each incoming anchor that does not resolve is replaced by the corpus's anchor of the same file and string that does, and
the report names the one dropped, with its author. An incoming anchor of another file or string is left as the claim has it,
and the report names the corpus anchor that resolves and the one that is gone (anchors_lost).

Judged the way memory_check judges (judge_anchor, in the checkouts the slice's origin names): only an incoming anchor that
is gone (stale-hard) is replaced, and only by a corpus anchor that is there. An anchor that cannot be looked at (no checkout
beside the tree, none given by --working-copy PROJECT=DIR) is unknown, never gone, and stands as the claim wrote it. An anchor of another file or string is another
anchor: the author's new anchor is not replaced by the old one for being older.
"""
from __future__ import annotations

import os
import sys
from typing import Any

import anchors
import memory_check
import roots
from assembler.core import layout, Run
from assembler.slices import anchors_of, claim_heading, read_existing_slice
from assembler.targets import slice_candidates

# memory_check.judge_anchor's verdicts: an anchor that resolves, and one that names something that is gone.
RESOLVES = ("exists", "maybe-stale")
GONE = "stale-hard"


def corpus_of(run: Run, path: str) -> tuple[str, str | None]:
    """(the tree a slice's paths are relative to, the project that tree is or None) for a slice file."""
    project_root = os.path.abspath(layout.project_memory_root(run.project))
    if os.path.abspath(path).startswith(project_root + os.sep):
        corpus = project_root
    else:
        corpus = os.path.abspath(roots.memory_dir(root=layout.FABRIC_ROOT))
    return memory_check.tree_of(corpus) or layout.FABRIC_ROOT, memory_check.own_project_of(corpus, None)


def verdict(run: Run, anchor: str, path: str, meta: dict[str, Any], history: Any) -> str:
    tree, own = corpus_of(run, path)
    project = anchors.split(anchor)[0]
    # A bare anchor is the corpus's own project's (a project corpus has no other origin to look in), so only a named one
    # can be in a checkout the caller was told of: --working-copy PROJECT=DIR, as lint is told.
    given = getattr(run.args, "checkouts", None) or {}
    trees, missing = (memory_check.named_trees(project, meta, tree, own, given) if project
                      else memory_check.origin_trees(meta, tree, own))
    return memory_check.judge_anchor(anchor, trees, missing, None, history)["status"]


def settle_topic(run: Run, role: str | None, label: str, klass: str, topic: str, group: list[dict[str, Any]],
                 history: Any) -> None:
    if klass not in anchors.ANCHOR_CLASSES or not any(c.get("anchors") for c in group):
        return
    held: dict[str, tuple[str, dict[str, Any], str]] = {}     # heading -> (file, its meta, the section as it stands)
    for path in slice_candidates(run, role, klass, topic):
        meta, sections = read_existing_slice(path)
        for heading, text in sections.items():
            held[heading] = (path, meta, text)
    for claim in group:
        wanted = claim.get("anchors")
        target = (claim.get("merge_target") or "").strip()
        heading = target if target in held else claim_heading(claim)
        if not wanted or heading not in held:
            continue
        path, meta, text = held[heading]
        standing = {(anchors.split(a)[1], anchors.split(a)[2]): a for a in anchors_of(text)}
        settled: list[str] = []
        for anchor in wanted:
            same = standing.get((anchors.split(anchor)[1], anchors.split(anchor)[2]))
            if same and same != anchor and verdict(run, anchor, path, meta, history) == GONE \
                    and verdict(run, same, path, meta, history) in RESOLVES:
                origin = run.origins.get((claim.get("evidence") or [""])[0]) or {}
                run.anchors_kept.append({
                    "slice": f"{label}/{klass}:{topic}", "heading": heading, "dropped": anchor, "kept": same,
                    "agent": origin.get("agent") or "unresolved", **({"host": origin["host"]} if origin.get("host") else {}),
                    "memory": claim["topic"]})
                anchor = same
            if anchor not in settled:
                settled.append(anchor)
        claim["anchors"] = settled
        # Another file or string is another anchor, so nothing pairs the two safely and the claim stays as written; but an author
        # whose newer anchor names nothing, over a corpus anchor that resolves, has to be told, as anchors_kept tells (drain of
        # 2026-11-08: six memories had a repaired anchor replaced by one that is gone).
        lost = [a for a in anchors_of(text) if a not in settled and verdict(run, a, path, meta, history) in RESOLVES]
        gained = [a for a in settled if a not in anchors_of(text) and verdict(run, a, path, meta, history) == GONE]
        if lost and gained:
            origin = run.origins.get((claim.get("evidence") or [""])[0]) or {}
            for anchor in lost:
                run.anchors_lost.append({
                    "slice": f"{label}/{klass}:{topic}", "heading": heading, "lost": anchor, "gained": ", ".join(gained),
                    "agent": origin.get("agent") or "unresolved", **({"host": origin["host"]} if origin.get("host") else {}),
                    "memory": claim["topic"]})


def keep_resolving_anchors(run: Run) -> None:
    history = memory_check.History()
    for role, topics in run.per_role.items():
        for (klass, topic), group in topics.items():
            settle_topic(run, role, role, klass, topic, group, history)
    for (klass, topic), group in run.shared.items():
        settle_topic(run, None, "shared", klass, topic, group, history)
    if run.anchors_lost:
        print("ANCHORS LOST (the corpus's anchor resolves, the memory's new one names nothing; both written as the memory has it — "
              "fix the memory):", file=sys.stderr)
        for row in run.anchors_lost:
            print(f"  {row['slice']}#{row['heading']} ({row['agent']}, memory {row['memory']}): {row['lost']} -> {row['gained']}",
                  file=sys.stderr)
    if run.anchors_kept:
        print("ANCHORS KEPT (the corpus's anchor resolves, the memory's does not; the memory's was dropped — "
              "fix the memory so the next harvest needs none):", file=sys.stderr)
        for row in run.anchors_kept:
            print(f"  {row['slice']}#{row['heading']} ({row['agent']}, memory {row['memory']}): "
                  f"{row['dropped']} -> {row['kept']}", file=sys.stderr)
