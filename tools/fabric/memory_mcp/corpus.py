"""The corpus a login can read, as sections (ADR-049 rules 2, 5 and 6).

Two roots and no others: the fabric's memory/ (through roots.py) and the
session's working copy's .agent-fabric/memory/. A slice is named by its
path under its root's parent ("memory/domains/…", ".agent-fabric/memory/…");
a caller's slice id is looked up in what was loaded and is never joined to
a path, so no input names a file outside the roots. Slices are parsed by
the assembler's own reader. What a merge_target correction replaced is gone
from the files at drain time, so serving what is on disk never returns it."""
from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass, field

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from assembler.slices import OBSERVED_RE, read_existing_slice  # noqa: E402

from memory_mcp import bm25  # noqa: E402

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


@dataclass
class Corpus:
    sections: list[Section] = field(default_factory=list)
    indexes: dict[str, str] = field(default_factory=dict)       # "<role>" -> INDEX.md text of the working copy
    _index: bm25.Index | None = None

    @staticmethod
    def fields(s: Section) -> list[str]:
        """The cue (the section heading) weighs three, the slice's title and description two, the body one: the
        author's own words for what the text is about outweigh its running text (ADR-049 rule 4)."""
        return bm25.tokens(f"{s.heading} " * 3 + f"{s.title} {s.cue} " * 2 + s.text)

    def search(self, query: str) -> list[tuple[Section, float]]:
        if self._index is None:
            self._index = bm25.Index([self.fields(s) for s in self.sections])
        return [(self.sections[i], score) for i, score in self._index.ranked(bm25.tokens(query))]

    def vocabulary(self) -> list[str]:
        """The words of every cue, most frequent first: what a failed query can be pointed at."""
        seen: dict[str, int] = {}
        for s in self.sections:
            for w in bm25.tokens(f"{s.heading} {s.title} {s.cue}"):
                if len(w) >= 4 and not w.isdigit():
                    seen[w] = seen.get(w, 0) + 1
        return sorted(seen, key=lambda w: (-seen[w], w))

    def slice_sections(self, slice_id: str) -> list[Section]:
        return [s for s in self.sections if s.slice_id == slice_id]


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


def _load_root(corpus: Corpus, root: str, prefix: str) -> None:
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


def load(memory_dir: str, working_copy: str | None) -> Corpus:
    """memory_dir is the fabric's memory/ (roots.memory_dir()); working_copy the session's checkout, or None."""
    corpus = Corpus()
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
