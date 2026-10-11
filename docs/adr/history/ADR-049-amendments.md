# ADR-049 — amendments

The full notes; the ADR's body reads current and its Amendments table lists them.

### Amendment 2026-10-12 — Memory find can expand to linked sections

`memory_find` takes `expand: 0|1` (default 0, so opt-in). With 1 it adds, below the hits and never in place of one, the sections linked to the top three strong hits (tools/fabric/memory_index.py `Index.neighbours`, shown by `memory_mcp/tools.py`): one hop, at most two per hit and four in all, each from a slice no hit and no other neighbour comes from, ranked by the seed's rank and then the weight of the edges (a direct link weighs most, a rarer key more), and shown within a further 130 tokens, so the hits keep their whole budget. A weak hit seeds nothing.

Measured in #210 on the offline expected-hit set (`tests/memory_expand_measure.py`, which leaves one expected section out of the hits, as a missed query would, and counts what the expansion from the rest brings back): of 12 expected sections, 3 were recovered only by expansion, all by direct links; co-citation and shared test paths added noise. That is too little to make it a default, so it stays opt-in. When used, trust direct links from strong seeds; the other edge kinds are guesses of a guess.
