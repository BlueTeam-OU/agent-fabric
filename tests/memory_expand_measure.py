#!/usr/bin/env python3
"""The measurement behind the linked-sections spike (agent-fabric ADR-049 follow-up): memory_find with and without
`expand: 1`, on the offline expected-hit set (tests/fixtures/memory-expected-hits.json) over the corpus committed at HEAD.
Not a test and not run by the suite: it prints a report, so a number in a PR body can be reproduced. It uses the tool's own functions
(tools.shown_hits, tools.expansion), so what it counts is what memory_find(expand: 1) adds.

    python3 tests/memory_expand_measure.py [--neighbours]      (--neighbours lists every neighbour for a hand label)

What it measures, and what it cannot:
  recall      every expected section is already found without expansion (the set was written from what BM25 returns), so the
              gain of expansion is measured the other way round: leave one expected section out of the hits, as a query that
              missed it would, and count the ones the expansion from the remaining strong hits brings back.
  noise       neighbour lines added per query and their cost in tokens next to the hits'; per key kind and per cap on a key's
              holders. Whether a neighbour is worth a person's next read is a judgement: --neighbours prints the pairs."""
from __future__ import annotations

import json
import os
import statistics
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
sys.path.insert(0, os.path.join(HERE, "runtime"))
import memory_index as mi  # noqa: E402
from memory_mcp import tools  # noqa: E402

FIXTURE = os.path.join(HERE, "tests", "fixtures", "memory-expected-hits.json")
LABELS = os.path.join(HERE, "tests", "fixtures", "memory-expand-labels.json")


def matches(section: mi.Section, want: dict) -> bool:
    return mi.slice_ref(section.slice_id) == want["slice"] and section.heading.startswith(want["heading"])


def run(index: mi.Index, queries: list[dict], **kw) -> dict:
    """What memory_find(expand: 1) adds at its defaults (the hits it shows within limit 8 and 200 tokens seed, the neighbours cost what
    their lines cost and stop at the allowance), by the tool's own functions, with `kw` passed to Index.neighbours."""
    added, tokens, with_any, hit_tokens = [], [], 0, []
    judged: list[str] = []
    unlabelled = 0
    recovered = total = 0
    for q in queries:
        hits = index.find(q["query"], q.get("role"), q.get("project"))
        shown, _rest = tools.shown_hits(hits, tools.DEFAULT_LIMIT, tools.FIND_TOKENS)
        neighbours = tools.expansion(index, shown, **kw)
        for n in neighbours:
            label = LABELLED.get(q["query"], {}).get(mi.section_id(n.section))
            judged.append(label) if label else None
            unlabelled += label is None
        added.append(len(neighbours))
        tokens.append(sum(tools._cost(tools._neighbour_line(n)) for n in neighbours))
        hit_tokens.append(sum(tools._cost(tools._hit_line(h)) for h in shown))
        with_any += bool(neighbours)
        for want in q.get("expect", []):
            total += 1
            kept = [h for h in hits if not matches(h.section, want)]
            seeds, _ = tools.shown_hits(kept, tools.DEFAULT_LIMIT, tools.FIND_TOKENS)
            if any(matches(n.section, want) for n in tools.expansion(index, seeds, **kw)):
                recovered += 1
    return {"queries": len(queries), "with_neighbours": with_any, "mean_added": statistics.mean(added), "max_added": max(added),
            "mean_tokens": statistics.mean(tokens), "mean_hit_tokens": statistics.mean(hit_tokens), "recovered": recovered, "expected": total,
            "useful": judged.count("useful"), "related": judged.count("related"), "noise": judged.count("noise"), "unlabelled": unlabelled}


with open(LABELS, encoding="utf-8") as _fh:
    LABELLED = json.load(_fh)["labels"]


def main() -> int:
    index = mi.build(os.path.join(HERE, "memory"), HERE)
    with open(FIXTURE, encoding="utf-8") as fh:
        queries = json.load(fh)["queries"]
    graph = index._edges()
    counts: dict[str, int] = {}
    for edges in graph.values():
        for kinds_ in edges.values():
            for kind, _key, _held in kinds_:
                counts[kind] = counts.get(kind, 0) + 1
    print(f"corpus: {len(index.sections)} sections, {len({s.slice_id for s in index.sections})} slices; "
          f"{len(graph)} sections have at least one edge")
    print("edges (undirected): " + ", ".join(f"{kind} {counts.get(kind, 0) // 2}" for kind in mi.KEY_KINDS) + f"; a key (a link too) held by more than {mi.KEY_DF_CAP} gives none")
    base = run(index, queries)
    print(f"\n{'variant':30s} {'queries with':>12s} {'neighbours':>16s} {'tokens/query':>12s} {'recovered':>9s} {'useful/related/noise':>21s}")
    print(f"{'':30s} {'neighbours':>12s} {'per query':>16s} {'(hits ~' + str(round(base['mean_hit_tokens'])) + 't)':>12s} {'if missed':>9s} {'(author-judged)':>21s}")

    def row(label: str, r: dict) -> None:
        judged = f"{r['useful']}/{r['related']}/{r['noise']}" + (f" +{r['unlabelled']} unlabelled" if r["unlabelled"] else "")
        print(f"{label:30s} {r['with_neighbours']:>6d}/{r['queries']:<5d} {r['mean_added']:>6.2f} (max {r['max_added']}) {r['mean_tokens']:>12.1f} {r['recovered']:>6d}/{r['expected']:<2d} {judged:>21s}")
    row("no expansion", {**base, "with_neighbours": 0, "mean_added": 0, "max_added": 0, "mean_tokens": 0, "recovered": 0,
                          "useful": 0, "related": 0, "noise": 0, "unlabelled": 0})
    row("expand 1 (defaults)", base)
    row("  seeds: weak hits too", run(index, queries, seed_bands=("strong", "weak")))
    row("  from the top hit only", run(index, queries, from_top=1))
    row("  one per hit", run(index, queries, per_hit=1))
    for kind in mi.KEY_KINDS:
        row(f"  only {kind} keys", run(index, queries, kinds=(kind,)))
    for kind in mi.KEY_KINDS:
        row(f"  without {kind} keys", run(index, queries, kinds=tuple(k for k in mi.KEY_KINDS if k != kind)))
    saved = mi.KEY_DF_CAP
    try:
        for cap in (2, 4, 8, 16, 10_000):
            mi.KEY_DF_CAP = cap
            index._graph = None
            row(f"  key held by at most {cap if cap < 10_000 else 'any number of'}", run(index, queries))
    finally:
        mi.KEY_DF_CAP = saved
        index._graph = None
    if "--neighbours" in sys.argv:
        print()
        for q in queries:
            hits, _ = tools.shown_hits(index.find(q["query"], q.get("role"), q.get("project")), tools.DEFAULT_LIMIT, tools.FIND_TOKENS)
            print(f"Q {q['query']!r}")
            for n in tools.expansion(index, hits):
                label = LABELLED.get(q["query"], {}).get(mi.section_id(n.section), "unlabelled")
                print(f"   [{label}] hit {mi.section_id(n.seed)} -> {mi.section_id(n.section)} | {n.section.heading[:70]} | via {', '.join(n.via)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
