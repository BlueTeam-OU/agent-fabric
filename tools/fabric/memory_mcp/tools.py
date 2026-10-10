"""The three tools (ADR-049 rule 3), cheapest first. Pure over a Corpus and a Session: no I/O."""
from __future__ import annotations

import difflib
from dataclasses import dataclass

from memory_mcp import bm25
from memory_mcp.corpus import INDEX_LINE, Corpus, Section

DEFAULT_LIMIT, MAX_LIMIT = 8, 20
FIND_TOKENS, READ_TOKENS, MAX_TOKENS = 200, 1500, 8000
RELATED = 2
HEADING_CLIP, CUE_CLIP = 60, 110
TOKENS_PER_CHAR = 0.25
# A solution slice describes the tree as of a date and loses to the tree (ADR-013).
DECAY = "verify against the tree"


@dataclass(frozen=True)
class Session:
    role: str | None = None
    project: str | None = None
    working_copy: str | None = None


class ToolError(Exception):
    """A call the caller got wrong: said in one line, as the tool's own error result."""


def slice_ref(slice_id: str) -> str:
    """The id a caller sees: short, and the one memory_read takes. f: the fabric's memory/, p: the working copy's."""
    if slice_id.startswith("memory/"):
        return "f:" + slice_id[len("memory/"):].removesuffix(".md")
    return "p:" + slice_id[len(".agent-fabric/memory/"):].removesuffix(".md")


def section_id(s: Section) -> str:
    return f"{slice_ref(s.slice_id)}#{s.position}"


def slice_id_of(ref: str) -> str:
    if ref.startswith("f:"):
        return "memory/" + ref[2:] + ".md"
    if ref.startswith("p:"):
        return ".agent-fabric/memory/" + ref[2:] + ".md"
    raise ToolError(f"slice_id {ref!r}: not an id memory_find returned (f:… or p:…)")


def clip(text: str, n: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= n else text[:n - 1] + "…"


def _tier(s: Section, role: str | None, project: str | None) -> int:
    """0 the asker's role and project, 1 one of them, 2 neither: they rank first, BM25 orders within a tier. A
    criterion not asked for matches everything, and a slice naming no project (the field's) matches any project."""
    by_role = not role or s.role == role or role in s.shared_with
    by_project = not project or not s.projects or project in s.projects
    return int(not by_role) + int(not by_project)


def _int(value: object, name: str, default: int, low: int, high: int) -> int:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int):
        raise ToolError(f"{name} must be an integer")
    return max(low, min(high, value))


def _text(value: object, name: str, required: bool = False) -> str | None:
    if value is None:
        if required:
            raise ToolError(f"{name} is required")
        return None
    if not isinstance(value, str):
        raise ToolError(f"{name} must be a string")
    if required and not value.strip():
        raise ToolError(f"{name} is required")
    return value


def _cost(text: str) -> int:
    return max(1, round(len(text) * TOKENS_PER_CHAR))


def _hit_line(s: Section, score: float) -> str:
    line = (f"{section_id(s)} | {clip(s.heading, HEADING_CLIP)} | {s.kind} | {s.observed or '-'} | {s.scope} | "
            f"~{s.tokens}t | {score:.1f}")
    return line + (f" | {DECAY}" if s.kind == "solution" else "")


def _try(corpus: Corpus, query: str) -> str:
    """What a query that found nothing is pointed at: the cue words nearest to its own, else the most used ones."""
    vocab = corpus.vocabulary()
    near: list[str] = []
    for word in bm25.tokens(query):
        for close in difflib.get_close_matches(word, vocab[:2000], n=2, cutoff=0.75):
            if close != word and close not in near:
                near.append(close)
    return "no sections match; try: " + ", ".join((near or vocab)[:6])


def find(corpus: Corpus, session: Session, args: dict) -> tuple[str, list[str]]:
    query = _text(args.get("query"), "query", True) or ""
    role = _text(args.get("role"), "role") or session.role
    project = _text(args.get("project"), "project") or session.project
    limit = _int(args.get("limit"), "limit", DEFAULT_LIMIT, 1, MAX_LIMIT)
    budget = _int(args.get("max_tokens"), "max_tokens", FIND_TOKENS, 1, MAX_TOKENS)
    ranked = sorted(corpus.search(query), key=lambda h: (_tier(h[0], role, project), -h[1]))
    if not ranked:
        return _try(corpus, query), []
    shown: list[tuple[Section, float]] = []
    slices: set[str] = set()
    cues: set[str] = set()
    spent = 0
    rest: list[Section] = []
    for s, score in ranked:
        cue = " ".join(s.heading.lower().split())
        if s.slice_id in slices or cue in cues:       # one best section per slice; a cue shown once
            continue
        slices.add(s.slice_id)
        cues.add(cue)
        cost = _cost(_hit_line(s, score))
        if len(shown) >= limit or (shown and spent + cost > budget):
            rest.append(s)
            continue
        shown.append((s, score))
        spent += cost
    lines = [_hit_line(s, score) for s, score in shown]
    if rest:
        scopes: dict[str, int] = {}
        for s in rest:
            scopes[s.scope] = scopes.get(s.scope, 0) + 1
        lines.append(f"+{len(rest)} more: " + ", ".join(f"{scope} {n}" for scope, n in sorted(scopes.items())))
    return "\n".join(lines), [section_id(s) for s, _ in shown]


def _related(corpus: Corpus, s: Section) -> list[Section]:
    own = bm25.tokens(f"{s.heading} {s.title}")
    out: list[Section] = []
    for other, _score in corpus.search(" ".join(own)):
        if other.slice_id != s.slice_id and all(o.slice_id != other.slice_id for o in out):
            out.append(other)
        if len(out) == RELATED:
            break
    return out


def read(corpus: Corpus, session: Session, args: dict) -> tuple[str, list[str]]:
    ids = args.get("ids")
    if isinstance(ids, str):
        ids = [ids]
    if not isinstance(ids, list) or not ids or not all(isinstance(i, str) and i.strip() for i in ids):
        raise ToolError("ids is required: one or more ids memory_find returned")
    budget = _int(args.get("max_tokens"), "max_tokens", READ_TOKENS, 1, MAX_TOKENS)
    parts: list[str] = []
    served: list[str] = []
    for ident in ids:
        ref, _, position = ident.partition("#")
        try:
            sections = corpus.slice_sections(slice_id_of(ref))
        except ToolError as e:
            parts.append(f"{ident}: {e}")
            continue
        if not sections:
            parts.append(f"{ident}: no such slice")
        elif not position:
            parts.append("\n".join(f"{section_id(s)} | {clip(s.heading, 100)} | ~{s.tokens}t" for s in sections))
            served.extend(section_id(s) for s in sections)
        else:
            wanted = [s for s in sections if str(s.position) == position]
            if not wanted:
                parts.append(f"{ident}: no such section")
                continue
            s = wanted[0]
            head = f"{section_id(s)} · {s.kind} · {s.scope} · {s.role}" + (f" · observed {s.observed}" if s.observed else "")
            head += f" · {DECAY}" if s.kind == "solution" else ""
            related = "".join(f"\nrelated: {section_id(r)} | {clip(r.heading, HEADING_CLIP)}" for r in _related(corpus, s))
            parts.append(f"{head}\n## {s.heading}\n{s.text}{related}")
            served.append(section_id(s))
    if not served:
        raise ToolError("; ".join(parts))
    text, kept = "", []
    for part in parts:
        if _cost(text + part) > budget:
            room = max(0, int(budget / TOKENS_PER_CHAR) - len(text))
            kept.append(part[:room].rstrip() + f"\n[cut at max_tokens {budget}]")
            break
        kept.append(part)
        text += part + "\n\n"
    return "\n\n".join(kept), served


def index(corpus: Corpus, session: Session, args: dict) -> tuple[str, list[str]]:
    role = _text(args.get("role"), "role") or session.role
    project = _text(args.get("project"), "project") or session.project
    if not role:
        raise ToolError("role is required: this session has none bound")
    text = corpus.indexes.get(role)
    if text is None:
        return f"no index for role {role} in this working copy", []
    known = {s.slice_id: s for s in corpus.sections}
    out, seen = [], set()
    for line in text.splitlines():
        m = INDEX_LINE.match(line)
        if not m or m.group(1) in seen:
            continue
        seen.add(m.group(1))
        s = known.get(m.group(1))
        if s is None or (project and s.projects and project not in s.projects):
            continue
        out.append((slice_ref(s.slice_id), f"{slice_ref(s.slice_id)} | {s.kind} | {clip(m.group(2), CUE_CLIP)}"))
    return ("\n".join(o[1] for o in out) or f"no indexed slices for role {role}"), [o[0] for o in out]


TOOLS = {
    "memory_find": (find, "Ranked section hits over the curated memory corpus: one line each, no body, within a token budget. "
                          "Ask before changing something the fleet may already know.",
                    {"query": {"type": "string"}, "role": {"type": "string"}, "project": {"type": "string"},
                     "limit": {"type": "integer", "minimum": 1, "maximum": MAX_LIMIT},
                     "max_tokens": {"type": "integer", "minimum": 1, "maximum": MAX_TOKENS}}, ["query"]),
    "memory_read": (read, "Sections by id (from memory_find), each with its provenance and its related slices' cue lines, cut at "
                          "max_tokens; a slice id alone lists its sections.",
                    {"ids": {"type": "array", "items": {"type": "string"}}, "max_tokens": {"type": "integer", "minimum": 1,
                                                                                            "maximum": MAX_TOKENS}}, ["ids"]),
    "memory_index": (index, "The index cue lines for a role (default: this session's) and project.",
                     {"role": {"type": "string"}, "project": {"type": "string"}}, []),
}
