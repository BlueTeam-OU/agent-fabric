"""tools/fabric/memory_index.py — the curated memory corpus as a ranked index (agent-fabric ADR-049).

The library under the fabric-memory MCP server (tools/fabric/memory_mcp/), importable on its own so a hook can
query the same index without the MCP layer: build() reads the corpus, Index.find() ranks it, band() says how
far a hit can be trusted.

CONTRACT
  build(memory_dir, working_copy)  reads exactly two roots: the fabric's memory/ and the working copy's
                                   .agent-fabric/memory/. Nothing else is opened, nothing is written, no network,
                                   no model. A link leading out of a root is not followed.
  Index.find(query, role, project) the matching sections, best first: the asker's role and project before the
                                   rest, BM25 within; one best section per slice; a cue shown once. Each is a Hit
                                   with its score, its coverage of the query and its band.
  slice ids                        "memory/…" for the fabric's, ".agent-fabric/memory/…" for the working copy's;
                                   a caller's id is looked up among those loaded and never joined to a path.
  What a merge_target correction replaced is gone from the files at drain time (assembler.slices), so serving
  what is on disk never returns it."""
from __future__ import annotations

import math
import os
import re
import sys
from collections import Counter
from dataclasses import dataclass, field

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from assembler.slices import OBSERVED_RE, read_existing_slice  # noqa: E402

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


class Bm25:
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


KINDS = ("domain", "solution", "intersection", "rationale", "workflow", "threads")
# Not slices: the generated map, the READMEs and the drain's records.
SKIP = {"INDEX.md", "README.md", "RUBRIC.md"}
TOKENS_PER_CHAR = 0.25


@dataclass(frozen=True)
class Section:
    slice_id: str
    heading: str
    cue: str
    kind: str
    scope: str
    role: str
    title: str
    position: int
    shared_with: tuple[str, ...]
    projects: tuple[str, ...]
    observed: str
    text: str

    @property
    def tokens(self) -> int:
        return max(1, round(len(self.text) * TOKENS_PER_CHAR))


# Bands (ADR-049 follow-up): how far a hit can be trusted, from its BM25 score, its margin over the next hit and
# the share of the query's weight it covers. Chosen on the real corpus (2026-10-10, 330 sections) with the queries
# in tests/test_memory_mcp.py EXPECTED_HITS and these: a right slice scored 15.6-30.5 at coverage 0.58-1.0; an
# off-topic query ("how do I bake a sourdough bread", "css grid layout") scored 5.3-10.2 at coverage 0.18-0.33; a
# query whose words are all present but scattered ("queued branch refuses a push") scored 9.2 at coverage 1.0.
STRONG_SCORE, STRONG_COVERAGE = 12.0, 0.55
WEAK_COVERAGE = 0.30
# A dead heat (margin under 1%) on a partial match is a guess between two slices, not a finding.
TIE_MARGIN, TIE_COVERAGE = 1.01, 0.75


@dataclass(frozen=True)
class Hit:
    section: Section
    score: float
    coverage: float
    band: str = "none"           # strong | weak | none


def band(score: float, coverage: float, margin: float) -> str:
    if score >= STRONG_SCORE and coverage >= STRONG_COVERAGE and (margin >= TIE_MARGIN or coverage >= TIE_COVERAGE):
        return "strong"
    return "weak" if coverage >= WEAK_COVERAGE else "none"


def slice_ref(slice_id: str) -> str:
    """The id a caller sees: short, and the one a read takes. f: the fabric's memory/, p: the working copy's."""
    if slice_id.startswith("memory/"):
        return "f:" + slice_id[len("memory/"):].removesuffix(".md")
    return "p:" + slice_id[len(".agent-fabric/memory/"):].removesuffix(".md")


def section_id(s: Section) -> str:
    return f"{slice_ref(s.slice_id)}#{s.position}"


def slice_id_of(ref: str) -> str | None:
    if ref.startswith("f:"):
        return "memory/" + ref[2:] + ".md"
    if ref.startswith("p:"):
        return ".agent-fabric/memory/" + ref[2:] + ".md"
    return None


@dataclass
class Index:
    sections: list[Section] = field(default_factory=list)
    indexes: dict[str, str] = field(default_factory=dict)       # "<role>" -> INDEX.md text of the working copy
    _bm25: Bm25 | None = None

    @staticmethod
    def fields(s: Section) -> list[str]:
        """The cue (the section heading) weighs three, the slice's title and description two, the body one: the
        author's own words for what the text is about outweigh its running text (ADR-049 rule 4)."""
        return tokens(f"{s.heading} " * 3 + f"{s.title} {s.cue} " * 2 + s.text)

    def _model(self) -> Bm25:
        if self._bm25 is None:
            self._bm25 = Bm25([self.fields(s) for s in self.sections])
        return self._bm25

    def search(self, query: str) -> list[tuple[Section, float]]:
        return [(self.sections[i], score) for i, score in self._model().ranked(tokens(query))]

    def _coverage(self, query: list[str], doc: int) -> float:
        """The share of the query's weight (idf) the section's fields hold; a word the corpus has never seen weighs most."""
        model, words = self._model(), set(query)
        unseen = math.log(1 + (len(self.sections) + 0.5) / 0.5)
        total = sum(model.idf.get(w, unseen) for w in words)
        return sum(model.idf[w] for w in words if w in model.tf[doc]) / total if total else 0.0

    def find(self, query: str, role: str | None = None, project: str | None = None) -> list[Hit]:
        """Best first: the asker's role and project before the rest (0 both, 1 one, 2 neither; a criterion not
        asked for matches everything, a slice naming no project matches any), BM25 within a tier. One best section
        per slice, a cue shown once."""
        def tier(s: Section) -> int:
            by_role = not role or s.role == role or role in s.shared_with
            by_project = not project or not s.projects or project in s.projects
            return int(not by_role) + int(not by_project)
        words = tokens(query)
        found = [(i, score) for i, score in self._model().ranked(words)]
        found.sort(key=lambda h: (tier(self.sections[h[0]]), -h[1]))
        picked: list[tuple[int, float]] = []
        slices: set[str] = set()
        cues: set[str] = set()
        for i, score in found:
            s = self.sections[i]
            cue = " ".join(s.heading.lower().split())
            if s.slice_id in slices or cue in cues:
                continue
            slices.add(s.slice_id)
            cues.add(cue)
            picked.append((i, score))
        hits = []
        for n, (i, score) in enumerate(picked):
            coverage = self._coverage(words, i)
            margin = score / picked[n + 1][1] if n + 1 < len(picked) else float("inf")
            hits.append(Hit(self.sections[i], score, coverage, band(score, coverage, margin)))
        return hits

    def related(self, s: Section, n: int = 2) -> list[Section]:
        """Other slices whose cue and title share the section's words: what to read next."""
        out: list[Section] = []
        for other, _score in self.search(f"{s.heading} {s.title}"):
            if other.slice_id != s.slice_id and all(o.slice_id != other.slice_id for o in out):
                out.append(other)
            if len(out) == n:
                break
        return out

    def vocabulary(self) -> list[str]:
        """The words of every cue, most frequent first: what a failed query can be pointed at."""
        seen: dict[str, int] = {}
        for s in self.sections:
            for w in tokens(f"{s.heading} {s.title} {s.cue}"):
                if len(w) >= 4 and not w.isdigit():
                    seen[w] = seen.get(w, 0) + 1
        return sorted(seen, key=lambda w: (-seen[w], w))

    def slice_sections(self, slice_id: str | None) -> list[Section]:
        return [s for s in self.sections if s.slice_id == slice_id] if slice_id else []


def _scope(slice_id: str) -> str:
    if slice_id.startswith("memory/domains/"):
        return "field"
    if slice_id.startswith("memory/agents/"):
        return "agent"
    if slice_id.startswith("memory/shared/") or "/shared/" in slice_id:
        return "shared"
    return "project"


def _as_list(value: object) -> tuple[str, ...]:
    return tuple(str(v) for v in value) if isinstance(value, list) else ()


def _slices(root: str, prefix: str):
    """(slice id, absolute path) of every file under root, in a fixed order; a link out of root is not followed."""
    real_root = os.path.realpath(root)
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for name in sorted(filenames):
            path = os.path.join(dirpath, name)
            if not name.endswith(".md") or name in SKIP:
                continue
            if os.path.commonpath([real_root, os.path.realpath(path)]) != real_root:
                continue
            yield f"{prefix}/{os.path.relpath(path, root)}", path


def _load_root(corpus: Index, root: str, prefix: str) -> None:
    for slice_id, path in _slices(root, prefix):
        try:
            meta, sections = read_existing_slice(path)
        except (OSError, UnicodeDecodeError):
            continue
        kind = str(meta.get("class", ""))
        if kind not in KINDS:
            continue
        origin = meta.get("origin") if isinstance(meta.get("origin"), list) else []
        projects = tuple(sorted({str(o["project"]) for o in origin if isinstance(o, dict) and o.get("project")}))
        for position, (heading, text) in enumerate(sections.items(), 1):
            found = OBSERVED_RE.search(text)
            corpus.sections.append(Section(
                slice_id=slice_id, heading=heading, cue=str(meta.get("description", "")), kind=kind, scope=_scope(slice_id),
                role=str(meta.get("role", "")), title=str(meta.get("topic", "")).replace("-", " "), position=position,
                shared_with=_as_list(meta.get("shared_with")), projects=projects,
                observed=found.group(1) if found else "", text=text))


def build(memory_dir: str, working_copy: str | None) -> Index:
    """memory_dir is the fabric's memory/ (roots.memory_dir()); working_copy the session's checkout, or None."""
    corpus = Index()
    if os.path.isdir(memory_dir):
        _load_root(corpus, memory_dir, "memory")
    if working_copy:
        wc_memory = os.path.join(working_copy, ".agent-fabric", "memory")
        if os.path.isdir(wc_memory):
            _load_root(corpus, wc_memory, ".agent-fabric/memory")
            for name in sorted(os.listdir(wc_memory)):
                index = os.path.join(wc_memory, name, "INDEX.md")
                if os.path.isfile(index):
                    with open(index, encoding="utf-8") as fh:
                        corpus.indexes[name] = fh.read()
    return corpus


INDEX_LINE = re.compile(r"^- \[`([^`]+)`\]\([^)]*\) — (.*)$")
