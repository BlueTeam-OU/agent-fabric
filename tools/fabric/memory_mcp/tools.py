"""The four tools (ADR-049 rule 3), cheapest first, as text over an Index (memory_index.py) and a Session. Only
memory_mark writes, and only to the login's own state."""
from __future__ import annotations

import difflib
from dataclasses import dataclass

import memory_index as mi
from memory_index import INDEX_LINE, Index, section_id, slice_ref
from memory_mcp import marks

DEFAULT_LIMIT, MAX_LIMIT = 8, 20
FIND_TOKENS, READ_TOKENS, MAX_TOKENS = 200, 1500, 8000
RELATED = 2
WEAK_NOTICE = "weak match: read only if the cue fits"
TAIL_TOKENS = 15       # the "+N more" line: counted in the budget, or a reply of the budget's size overruns it
HEADING_CLIP, CUE_CLIP = 60, 110
TOKENS_PER_CHAR = 0.25
# A solution slice describes the tree as of a date and loses to the tree (ADR-013).
DECAY = "verify against the tree"


@dataclass(frozen=True)
class Session:
    role: str | None = None
    project: str | None = None
    working_copy: str | None = None
    state_dir: str | None = None


class ToolError(Exception):
    """A call the caller got wrong: said in one line, as the tool's own error result."""


def clip(text: str, n: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= n else text[:n - 1] + "…"


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


def _hit_line(hit: mi.Hit) -> str:
    s = hit.section
    line = (f"{section_id(s)} | {clip(s.heading, HEADING_CLIP)} | {s.kind} | {s.observed or '-'} | {s.scope} | "
            f"~{s.tokens}t | {hit.score:.1f} {hit.band}")
    return line + (f" | {DECAY}" if s.kind == "solution" else "")


def _try(index: Index, query: str) -> str:
    """What a query that found nothing is pointed at: the cue words nearest to its own, else the most used ones."""
    vocab = index.vocabulary()
    near: list[str] = []
    for word in mi.tokens(query):
        for close in difflib.get_close_matches(word, vocab[:2000], n=2, cutoff=0.75):
            if close != word and close not in near:
                near.append(close)
    return "no sections match; try: " + ", ".join((near or vocab)[:6])


def find(index: Index, session: Session, args: dict) -> tuple[str, list[str]]:
    query = _text(args.get("query"), "query", True) or ""
    role = _text(args.get("role"), "role") or session.role
    project = _text(args.get("project"), "project") or session.project
    limit = _int(args.get("limit"), "limit", DEFAULT_LIMIT, 1, MAX_LIMIT)
    budget = _int(args.get("max_tokens"), "max_tokens", FIND_TOKENS, 1, MAX_TOKENS)
    hits = index.find(query, role, project)
    if not hits:
        return _try(index, query), []
    shown: list[mi.Hit] = []
    rest: list[mi.Hit] = []
    spent = _cost(WEAK_NOTICE)
    for hit in hits:
        cost = _cost(_hit_line(hit))
        if len(shown) >= limit or (shown and spent + cost > budget - TAIL_TOKENS):
            rest.append(hit)
            continue
        shown.append(hit)
        spent += cost
    lines = [_hit_line(h) for h in shown]
    if shown[0].band != "strong":
        lines.insert(0, WEAK_NOTICE)
    if rest:
        scopes: dict[str, int] = {}
        for h in rest:
            scopes[h.section.scope] = scopes.get(h.section.scope, 0) + 1
        lines.append(f"+{len(rest)} more: " + ", ".join(f"{scope} {n}" for scope, n in sorted(scopes.items())))
    return "\n".join(lines), [section_id(h.section) for h in shown]


def read(index: Index, session: Session, args: dict) -> tuple[str, list[str]]:
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
            sections = index.slice_sections(mi.slice_id_of(ref))
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
            related = "".join(f"\nrelated: {section_id(r)} | {clip(r.heading, HEADING_CLIP)}" for r in index.related(s, RELATED))
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


def index(index: Index, session: Session, args: dict) -> tuple[str, list[str]]:
    role = _text(args.get("role"), "role") or session.role
    project = _text(args.get("project"), "project") or session.project
    if not role:
        raise ToolError("role is required: this session has none bound")
    text = index.indexes.get(role)
    if text is None:
        return f"no index for role {role} in this working copy", []
    known = {s.slice_id: s for s in index.sections}
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


VERDICTS = ("helpful", "wrong", "stale")
NOTE_CLIP = 300


def mark(index: Index, session: Session, args: dict) -> tuple[str, list[str]]:
    """A verdict on a section a session used, for the next drain to route (stale and wrong to the section's owning
    role). Appended to the login's own state; nothing under the corpus is touched."""
    ident = _text(args.get("id"), "id", True) or ""
    verdict = _text(args.get("verdict"), "verdict", True)
    note = _text(args.get("note"), "note")
    if verdict not in VERDICTS:
        raise ToolError("verdict must be one of " + " | ".join(VERDICTS))
    ref, _, position = ident.partition("#")
    if not any(str(s.position) == position for s in index.slice_sections(mi.slice_id_of(ref))):
        raise ToolError(f"id {ident!r}: not a section memory_find returned")
    if not session.state_dir:
        raise ToolError("mark not recorded: this session has no state directory")
    failed = marks.record(session.state_dir, ident, verdict, clip(note, NOTE_CLIP) if note else "")
    if failed:
        raise ToolError(f"mark not recorded: {failed}")
    return f"marked {ident} {verdict}", [ident]


TOOLS = {
    "memory_find": (find, "Ranked section hits over the curated memory index: one line each, no body, within a token budget. "
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
    "memory_mark": (mark, "Say whether a section helped, is wrong, or is stale (verdict helpful | wrong | stale, an optional note). "
                          "Recorded in this login's state for the next drain; nothing in the corpus changes.",
                    {"id": {"type": "string"}, "verdict": {"type": "string", "enum": list(VERDICTS)}, "note": {"type": "string"}},
                    ["id", "verdict"]),
}
