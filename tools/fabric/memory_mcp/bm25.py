"""BM25 over short documents, in memory, standard library only (ADR-049 rule 4)."""
from __future__ import annotations

import math
import re
from collections import Counter

K1, B = 1.5, 0.75
WORD = re.compile(r"[a-z0-9_]+")


def tokens(text: str) -> list[str]:
    """Words, and an identifier (snake_case, a path, a --flag, kebab-case) as itself and as its parts: a query
    for `merge target` finds `merge_target`, and one for `merge_target` finds the two words."""
    out: list[str] = []
    for word in WORD.findall(text.lower()):
        out.append(word)
        parts = [p for p in word.split("_") if p]
        if len(parts) > 1:
            out.extend(parts)
    return out


class Index:
    def __init__(self, docs: list[list[str]]) -> None:
        self.tf = [Counter(d) for d in docs]
        self.len = [len(d) for d in docs]
        self.avg = (sum(self.len) / len(docs)) if docs else 0.0
        df: Counter[str] = Counter()
        for tf in self.tf:
            df.update(tf.keys())
        n = len(docs)
        # The +1 inside the log keeps a term found in every document from scoring below zero.
        self.idf = {t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in df.items()}

    def score(self, query: list[str], doc: int) -> float:
        tf, norm = self.tf[doc], K1 * (1 - B + B * self.len[doc] / (self.avg or 1.0))
        return sum(self.idf.get(t, 0.0) * tf[t] * (K1 + 1) / (tf[t] + norm) for t in set(query) if t in tf)

    def ranked(self, query: list[str]) -> list[tuple[int, float]]:
        """(document, score) for every document that matches at least one term, best first; ties keep corpus order."""
        hits = [(i, s) for i in range(len(self.tf)) if (s := self.score(query, i)) > 0]
        return sorted(hits, key=lambda h: (-h[1], h[0]))
