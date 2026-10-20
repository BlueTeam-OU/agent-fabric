"""tools/fabric/memory_index.py — the curated memory corpus as a ranked index (agent-fabric ADR-049).

The library under the fabric-memory MCP server (tools/fabric/memory_mcp/), importable on its own so a hook can
query the same index without the MCP layer: build() reads the corpus, Index.find() ranks it, band() says how
far a hit can be trusted.

CONTRACT
  build(memory_dir, working_copy)  reads exactly two roots: the fabric's memory/ and the working copy's
                                   .agent-fabric/memory/, from git's COMMITTED tree (committed_tree.py): an uncommitted
                                   slice, which no lint has seen, is not served, and a link has no path to follow. A root
                                   git cannot give is not served, said on stderr and in Index.unread. Nothing is written,
                                   no network, no model.
  Index.find(query, role, project) the matching sections, best first: the asker's role and project before the
                                   rest, BM25 within; one best section per slice; a cue shown once. Each is a Hit
                                   with its score, its coverage of the query and its band.
  slice ids                        "memory/…" for the fabric's, ".agent-fabric/memory/…" for the working copy's;
                                   a caller's id is looked up among those loaded and never joined to a path.
  What a merge_target correction replaced is gone from the files at drain time (assembler.slices), so serving
  what is committed never returns it."""
from __future__ import annotations

import math
import os
import re
import sys
from collections import Counter
from dataclasses import dataclass, field

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import anchors as anchor_syntax  # noqa: E402
import committed_tree  # noqa: E402
import layout  # noqa: E402
from assembler.slices import OBSERVED_RE, anchors_of, parse_slice  # noqa: E402

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

    def score(self, terms: set[str], doc: int) -> float:
        tf, norm = self.tf[doc], K1 * (1 - B + B * self.len[doc] / (self.avg or 1.0))
        return sum(self.idf.get(t, 0.0) * tf[t] * (K1 + 1) / (tf[t] + norm) for t in terms if t in tf)

    def ranked(self, query: list[str]) -> list[tuple[int, float]]:
        """(document, score) for every document that matches at least one term, best first; ties keep corpus order."""
        terms = set(query)           # once: a set built per document made a long query cost sections times its length
        hits = [(i, s) for i in range(len(self.tf)) if (s := self.score(terms, i)) > 0]
        return sorted(hits, key=lambda h: (-h[1], h[0]))


KINDS = ("domain", "solution", "intersection", "rationale", "workflow", "threads")
# Not slices: the generated map, the READMEs and the drain's records.
SKIP = {"INDEX.md", "README.md", "RUBRIC.md"}
TOKENS_PER_CHAR = 0.25
MAX_QUERY_TOKENS = 64


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
    # The project an unnamed path of a slice with no `origin` belongs to: the fabric's for memory/, the working copy's for
    # .agent-fabric/memory/. "" when it cannot be told, which gives such a path no project and so no link to a named one.
    home_project: str = ""

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
class Neighbour:
    section: Section
    seed: Section                # the hit it is linked to
    via: tuple[str, ...]         # the keys they share
    score: float


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


# Linked sections (a spike, ADR-049 follow-up): two sections are linked when they share what they are about without sharing
# words. A section carries a few normalised keys: path:<project>:<p> for a path it is anchored to or cites in backticks (the project an anchor names, else the slice's origin or home project), symbol:<name>
# for the part after :: of an anchor, link:<name> for each [[name]] it links, name:<name> for its own slice's file name (as the
# memory it was drained from was called), topic:<role>/<topic>. The edges are of five kinds: "direct" (one links the memory the
# other is named for), "cocite" (both link the same third), "path", "symbol" and "topic" (the same key held). A key held by
# more than KEY_DF_CAP sections links everything to everything and gives no edge, a link too: a memory cited by more than that is cited by
# habit, and the edge builder is bounded by the cap squared per key, not by the corpus.
KEY_DF_CAP = 8
PATH_EXT = r"(?:py|sh|md|json|mjs|js|ts|yml|yaml|toml|txt|cfg|ini|service|timer)"
CITED_PATH = re.compile(rf"`([A-Za-z0-9_.][A-Za-z0-9_./-]*/[A-Za-z0-9_.-]+\.{PATH_EXT})(?:::[^`]*|:\d+)?`")
LINK = re.compile(r"\[\[([A-Za-z0-9][A-Za-z0-9._-]*)\]\]")
CLASS_PREFIX = re.compile(r"^(?:workflow|solution|domain|intersection|rationale|threads)-")
KEY_KINDS = ("direct", "cocite", "path", "symbol", "topic")
# What an expansion follows unless asked otherwise: measured on #210, direct links carried all the recovered and all the useful
# neighbours; co-citation, shared paths and topics were mostly noise.
DEFAULT_KINDS = ("direct",)
EDGE_WEIGHT = {"direct": 4.0, "cocite": 1.0, "path": 3.0, "symbol": 3.0, "topic": 1.0}
EXPAND_FROM, PER_HIT, MAX_NEIGHBOURS = 3, 2, 4


def path_keys(s: Section, project: str | None, path: str) -> set[str]:
    """`path:<project>:<path>`, the project an anchor resolves to: the one it names, else the slice's origin project(s), else its
    home. A slice drained from two projects gives an unnamed path a key for each, as memory_check judges it in each; a path whose
    project is unknown keeps the bare `path:<path>`, which no named anchor shares."""
    path = path.removeprefix("./")
    owners = (project,) if project else (s.projects or ((s.home_project,) if s.home_project else ()))
    return {f"path:{o}:{path}" for o in owners} or {"path:" + path}


def section_keys(s: Section) -> frozenset[str]:
    """The normalised keys of one section (see above)."""
    keys: set[str] = set()
    for anchor in anchors_of(s.text):
        project, path, symbol = anchor_syntax.split(anchor)
        keys |= path_keys(s, project, path)
        if symbol.strip():
            keys.add("symbol:" + symbol.strip().lower())
    for m in CITED_PATH.finditer(s.text):
        if ".." not in m.group(1).split("/"):
            keys |= path_keys(s, None, m.group(1))
    stem = os.path.basename(s.slice_id).removesuffix(".md").lower()
    own = {stem, CLASS_PREFIX.sub("", stem)}            # a project slice's file name carries its class
    keys.update("link:" + m.group(1).lower() for m in LINK.finditer(s.text) if m.group(1).lower() not in own)
    keys.update("name:" + n for n in own)
    if s.role and s.title:
        keys.add(f"topic:{s.role}/{s.title}")
    return frozenset(keys)


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
    unread: list[str] = field(default_factory=list)             # roots git could not give: not served, said
    _bm25: Bm25 | None = None
    _graph: dict[int, dict[int, list[tuple[str, str, int]]]] | None = None

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
        words = tokens(query)[:MAX_QUERY_TOKENS]       # the query is the model's: the first words are the question
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

    def _edges(self) -> dict[int, dict[int, list[tuple[str, str, int]]]]:
        """section -> neighbour section -> [(kind, key, holders)]: every edge of the link graph, once from each side."""
        if self._graph is not None:
            return self._graph
        keys = [section_keys(s) for s in self.sections]
        holders: dict[str, list[int]] = {}
        for i, ks in enumerate(keys):
            for k in ks:
                holders.setdefault(k, []).append(i)
        graph: dict[int, dict[int, list[tuple[str, str, int]]]] = {}

        def add(i: int, j: int, kind: str, key: str, held: int) -> None:
            if i != j:
                graph.setdefault(i, {}).setdefault(j, []).append((kind, key, held))
                graph.setdefault(j, {}).setdefault(i, []).append((kind, key, held))
        for key, held in holders.items():
            kind, _, name = key.partition(":")
            if kind == "link" and len(held) <= KEY_DF_CAP:      # who cites it, against who is named for it and who else cites it
                named = holders.get("name:" + name, [])
                for i in held:
                    for j in named[:KEY_DF_CAP]:
                        add(i, j, "direct", name, 2)
                if 2 <= len(held):
                    for n, i in enumerate(held):
                        for j in held[n + 1:]:
                            add(i, j, "cocite", name, len(held))
            elif kind in ("path", "symbol", "topic") and 2 <= len(held) <= KEY_DF_CAP:
                for n, i in enumerate(held):
                    for j in held[n + 1:]:
                        add(i, j, kind, name, len(held))
        self._graph = graph
        return graph

    def neighbours(self, hits: list[Hit], from_top: int = EXPAND_FROM, per_hit: int = PER_HIT, total: int = MAX_NEIGHBOURS,
                   kinds: tuple[str, ...] = DEFAULT_KINDS, seed_bands: tuple[str, ...] = ("strong",)) -> list[Neighbour]:
        """One hop out from the top strong hits (a weak hit is a guess, and its neighbours a guess of a guess): the sections
        linked to one, from other slices than any hit's or than each other's, ranked below the hits (by the seed's rank, then
        by the weight of the edges, a rarer key weighing more). An opt-in expansion of find(); the hits are untouched."""
        graph = self._edges()
        index_of = {id(s): i for i, s in enumerate(self.sections)}
        taken = {h.section.slice_id for h in hits}
        out: list[Neighbour] = []
        for hit in [h for h in hits if h.band in seed_bands][:from_top]:
            scored: dict[int, tuple[float, list[str]]] = {}
            for j, edges in graph.get(index_of[id(hit.section)], {}).items():
                if self.sections[j].slice_id in taken:
                    continue
                for kind, key, held in edges:
                    if kind in kinds:
                        score, via = scored.get(j, (0.0, []))
                        scored[j] = (score + EDGE_WEIGHT[kind] / max(1, held - 1), via + [f"{kind}:{key}"])
            best_per_slice: dict[str, int] = {}
            for j, (score, _via) in scored.items():
                slice_id = self.sections[j].slice_id
                if slice_id not in best_per_slice or score > scored[best_per_slice[slice_id]][0]:
                    best_per_slice[slice_id] = j
            added = 0
            for j in sorted(best_per_slice.values(), key=lambda j: (-scored[j][0], j)):
                if added == per_hit or len(out) == total:
                    break
                taken.add(self.sections[j].slice_id)
                out.append(Neighbour(self.sections[j], hit.section, tuple(sorted(scored[j][1])), scored[j][0]))
                added += 1
        return out

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


def _load_root(corpus: Index, files: dict[str, bytes], prefix: str, home_project: str = "") -> None:
    """The slices among a root's committed files (path relative to the root -> bytes), in a fixed order."""
    for rel in sorted(files):
        if not rel.endswith(".md") or os.path.basename(rel) in SKIP:
            continue
        slice_id = f"{prefix}/{rel}"
        try:
            meta, sections = parse_slice(files[rel].decode("utf-8"))
        except UnicodeDecodeError:
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
                observed=found.group(1) if found else "", text=text, home_project=home_project))


def _committed(corpus: Index, directory: str, what: str) -> dict[str, bytes] | None:
    """The committed files under a root, or None, said once on stderr and in corpus.unread: a root that cannot be read from git
    is not served (an empty corpus would look like one with nothing in it)."""
    try:
        return committed_tree.read(directory)
    except committed_tree.CommittedTreeError as e:
        corpus.unread.append(f"{what}: {e}")
        print(f"fabric-memory: {what} is not served: {e}", file=sys.stderr)
        return None


def _project_of(working_copy: str) -> str:
    """The registry project a checkout is, or "" when the registry cannot say (a marker naming an unknown project is an error
    there): unknown stays unknown, so no project is guessed from the directory's name."""
    try:
        import workingcopy
        return str(workingcopy.resolve(working_copy).get("project") or "")
    except (Exception, SystemExit) as e:  # noqa: BLE001 — workingcopy.resolve exits on a bad marker; a key helper must not end the server
        print(f"fabric-memory: the project of {working_copy} is not known ({e}); its unnamed paths are not linked to a named project", file=sys.stderr)
        return ""


def build(memory_dir: str, working_copy: str | None) -> Index:
    """memory_dir is the fabric's memory/ (roots.memory_dir()); working_copy the session's checkout, or None. Both are read
    from git's committed tree (ADR-049 rule 6), never from the working tree."""
    corpus = Index()
    if os.path.isdir(memory_dir):
        files = _committed(corpus, memory_dir, "the fabric's memory/")
        if files is not None:
            _load_root(corpus, files, "memory", layout.FABRIC_PROJECT_ID)
    if working_copy:
        wc_memory = os.path.join(working_copy, ".agent-fabric", "memory")
        if os.path.isdir(wc_memory):
            files = _committed(corpus, wc_memory, "the working copy's .agent-fabric/memory/")
            if files is not None:
                _load_root(corpus, files, ".agent-fabric/memory", _project_of(working_copy))
                for rel in sorted(files):
                    role, _, name = rel.partition("/")
                    if name == "INDEX.md":
                        try:
                            corpus.indexes[role] = files[rel].decode("utf-8")
                        except UnicodeDecodeError:
                            continue
    return corpus


INDEX_LINE = re.compile(r"- \[`([^`]+)`\]\([^)]*\) — (.*)")      # used with fullmatch
