#!/usr/bin/env python3
"""The offline set of expected hits (agent-fabric ADR-049 rule 7): tests/fixtures/memory-expected-hits.json lists queries a person
would type and the sections each must return, how far down, and the weakest band each may carry; this runs it against the
corpus committed at HEAD (the fabric's memory/ and .agent-fabric/memory/, through memory_index: git's committed tree, as the
server reads it). It fails when a listed section stops being found, falls down the list or loses its band, and when a topic
the corpus has nothing on starts to claim a strong match. The checker is shown to fail too: against the same corpus with a
listed section taken out, and against a band the first hit cannot reach. Plain script: prints ok/FAIL, exit 1 on any failure."""
from __future__ import annotations

import copy
import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
import memory_index  # noqa: E402

FIXTURE = os.path.join(HERE, "tests", "fixtures", "memory-expected-hits.json")
ORDER = {"none": 0, "weak": 1, "strong": 2}


def check_expected(index: memory_index.Index, queries: list[dict]) -> list[str]:
    """What the set asks that the index does not give: one line each, empty when the index meets it."""
    problems: list[str] = []
    for q in queries:
        hits = index.find(q["query"], q.get("role"), q.get("project"))
        if q.get("no_better_than") and hits and ORDER[hits[0].band] > ORDER[q["no_better_than"]]:
            problems.append(f"{q['query']!r}: the corpus has nothing on it, yet the first hit is {hits[0].band} "
                            f"({memory_index.section_id(hits[0].section)})")
        for want in q.get("expect", []):
            where = next((i for i, h in enumerate(hits) if memory_index.slice_ref(h.section.slice_id) == want["slice"]
                          and h.section.heading.startswith(want["heading"])), None)
            if where is None:
                problems.append(f"{q['query']!r}: {want['slice']} ({want['heading']!r}) is not among the {len(hits)} hits")
            elif where + 1 > want["within"]:
                problems.append(f"{q['query']!r}: {want['slice']} is hit {where + 1}, expected within {want['within']}")
            elif ORDER[hits[where].band] < ORDER[want["band"]]:
                problems.append(f"{q['query']!r}: {want['slice']} is {hits[where].band}, expected at least {want['band']}")
    return problems


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: str = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}")
        if not good and detail:
            print("      " + detail.replace("\n", "\n      "))
        fails += not good

    with open(FIXTURE, encoding="utf-8") as fh:
        queries = json.load(fh)["queries"]
    index = memory_index.build(os.path.join(HERE, "memory"), HERE)
    check("the corpus at HEAD is readable (both roots served)", index.unread == [] and len(index.sections) > 100,
          f"{index.unread} {len(index.sections)} sections")
    print("the set, against the corpus committed at HEAD")
    problems = check_expected(index, queries)
    check(f"all {sum(len(q.get('expect', [])) for q in queries)} expected sections and {sum('no_better_than' in q for q in queries)} "
          f"claims of nothing hold", not problems, "\n".join(problems))

    print("the checker can fail")
    wanted = queries[0]["expect"][0]
    without = copy.copy(index)
    without.sections = [s for s in index.sections if memory_index.slice_ref(s.slice_id) != wanted["slice"]]
    without._bm25 = None
    gone = check_expected(without, queries[:1])
    check("a listed section that stops being found is reported", len(gone) == 1 and "is not among" in gone[0], str(gone))
    low = copy.deepcopy(queries[0])
    low["expect"][0]["within"] = 0
    check("one that falls below its place is reported", "expected within 0" in "".join(check_expected(index, [low])))
    # A hit that is present but not strong, expected as strong: the band branch itself, not the not-found one.
    hits = index.find(queries[0]["query"])
    weak = next((h for h in hits if h.band != "strong"), None)
    ask = {"query": queries[0]["query"], "expect": [{"slice": memory_index.slice_ref(weak.section.slice_id), "heading": weak.section.heading,
                                                     "within": len(hits), "band": "strong"}]} if weak else None
    weak_hit = check_expected(index, [ask]) if ask else []
    check("a section that loses its band is reported", len(weak_hit) == 1 and "expected at least strong" in weak_hit[0], str(weak_hit))
    claim = {"query": queries[0]["query"], "no_better_than": "weak", "expect": []}
    check("a topic with nothing on it that claims a strong match is reported", len(check_expected(index, [claim])) == 1)

    print("test_memory_expected_hits:", "OK" if not fails else f"{fails} FAILED")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
