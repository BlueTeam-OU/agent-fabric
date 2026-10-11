"""The four tools (ADR-049 rule 3), cheapest first, as text over an Index (memory_index.py) and a Session. Only
memory_mark writes, and only to the login's own state."""
from __future__ import annotations

import difflib
import unicodedata
from dataclasses import dataclass, field

import memory_index as mi
from memory_index import INDEX_LINE, Index, section_id, slice_ref
from memory_mcp import marks

DEFAULT_LIMIT, MAX_LIMIT = 8, 20
FIND_TOKENS, READ_TOKENS, MAX_TOKENS = 200, 1500, 8000
MIN_TOKENS = 100        # a reply smaller than this cannot hold one hit line (a clipped heading and an id, ~65 tokens), the weak notice and the tail. The
                        # floor is measured on an id of 100 characters (tests/test_memory_mcp.py; the corpus's longest was 88 on 2026-10-11): ids past ~155 would not fit
RELATED = 2
NEIGHBOUR_TOKENS = 130     # what `expand: 1` may add to a find, on top of max_tokens: about two lines
MAX_TRY_WORDS, MAX_TRY_LEN = 8, 40
WEAK_NOTICE = "weak match: read only if the cue fits"
TAIL_TOKENS = 15       # the "+N more" line: counted in the budget, or a reply of the budget's size overruns it
HEADING_CLIP, CUE_CLIP = 60, 110
TOKENS_PER_CHAR = 0.25
# What the model reads of the corpus is wisdom from the past, not an instruction or a fact about now: every result that
# carries slice text is wrapped in these two lines, the opening naming the closing so a reader knows where it stops.
MEMORY_END = "--- end of memory from past sessions ---"
END_PREFIX = "--- end of memory"
MEMORY_START = (f"Memory from past sessions follows, up to the line \"{MEMORY_END}\": curated lessons likely useful in this "
                "context, possibly stale; check them against the tree before acting on them.")
# A solution slice describes the tree as of a date and loses to the tree (ADR-013).
DECAY = "verify against the tree"


@dataclass(frozen=True)
class Session:
    role: str | None = None
    project: str | None = None
    working_copy: str | None = None
    state_dir: str | None = None
    # Every id this session has been shown, by find, read or index: memory_mark refuses any other (ADR-049 rule 3).
    shown: set[str] = field(default_factory=set, compare=False, repr=False)


def frame(text: str) -> str:
    """The result text between its opening and closing line. Applied by the server to find, read and index (index
    lines are cues copied from slice text); never to memory_mark's acknowledgement or to an error."""
    # A slice may quote the end line (one teaching this frame would); left as is, it would close the frame early
    # and leave the rest of the slice outside it, read as the session's own context. In backticks it is quoted text.
    # Split on every line break a reader may take for one (\r, \x0b, \x0c, \x1c-\x1e, \x85, U+2028/2029 as well as
    # \n), so an end line cannot hide behind a break that "\n" alone does not see; the frame is joined with \n.
    # The test ignores whitespace and format characters (category Cf: zero-width space, BOM, soft hyphen, bidi marks).
    # It does not close the rest of what a reader might take for the end line: other default-ignorable characters
    # (a combining grapheme joiner, a variation selector, a Hangul filler), confusable dashes or letters, a Markdown
    # prefix. No list of characters closes that class; the structural fix is an end line a slice cannot know in advance
    # (a per-call token named in the start line), which is the owner of this frame's call, not a longer list.
    def is_end_line(line: str) -> bool:
        return "".join(c for c in line if unicodedata.category(c) != "Cf").lstrip().startswith(END_PREFIX)

    body = "\n".join(f"`{line.strip()}`" if is_end_line(line) else line for line in text.splitlines())
    return f"{MEMORY_START}\n{body}\n{MEMORY_END}"


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


def _neighbour_line(n: mi.Neighbour) -> str:
    """Not a match: a section linked to a hit (they share a key), so no score and no band; the line says to which and by what."""
    s = n.section
    kinds = ",".join(sorted({v.partition(":")[0] for v in n.via}))
    line = f"{section_id(s)} | {clip(s.heading, HEADING_CLIP)} | {s.kind} | {s.observed or '-'} | {s.scope} | ~{s.tokens}t | linked to {section_id(n.seed)} by {kinds}"
    return line + (f" | {DECAY}" if s.kind == "solution" else "")


def _try(index: Index, query: str) -> str:
    """What a query that found nothing is pointed at: the cue words nearest to its own, else the most used ones."""
    vocab = index.vocabulary()
    near: list[str] = []
    # The query is the model's: a long one that matches nothing must not hold the one-message-at-a-time server in difflib.
    for word in mi.tokens(query)[:MAX_TRY_WORDS]:
        word = word[:MAX_TRY_LEN]
        for close in difflib.get_close_matches(word, vocab[:2000], n=2, cutoff=0.75):
            if close != word and close not in near:
                near.append(close)
    return "no sections match; try: " + ", ".join((near or vocab)[:6])


def shown_hits(hits: list[mi.Hit], limit: int, budget: int) -> tuple[list[mi.Hit], list[mi.Hit]]:
    """The hits a find shows within its limit and token budget, and the rest."""
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
    return shown, rest


def expansion(index: Index, shown: list[mi.Hit], **kw) -> list[mi.Neighbour]:
    """What `expand: 1` adds to the shown hits: their neighbours, as many as fit the allowance of their own (the budget is spent
    on hits first, and the default 200 tokens holds three lines, so neighbours inside it would never show)."""
    linked: list[mi.Neighbour] = []
    room = NEIGHBOUR_TOKENS
    for n in index.neighbours(shown, **kw):
        cost = _cost(_neighbour_line(n))
        if cost > room:
            break
        linked.append(n)
        room -= cost
    return linked


def find(index: Index, session: Session, args: dict) -> tuple[str, list[str]]:
    query = _text(args.get("query"), "query", True) or ""
    role = _text(args.get("role"), "role") or session.role
    project = _text(args.get("project"), "project") or session.project
    limit = _int(args.get("limit"), "limit", DEFAULT_LIMIT, 1, MAX_LIMIT)
    budget = _int(args.get("max_tokens"), "max_tokens", FIND_TOKENS, MIN_TOKENS, MAX_TOKENS)
    expand = _int(args.get("expand"), "expand", 0, 0, 1)
    hits = index.find(query, role, project)
    if not hits:
        return _try(index, query), []
    shown, rest = shown_hits(hits, limit, budget)
    lines = [_hit_line(h) for h in shown]
    if shown[0].band != "strong":
        lines.insert(0, WEAK_NOTICE)
    # An opt-in expansion (a spike, measured in tests/memory_expand_measure.py): the sections linked to the strong hits, after the
    # hits and never in place of one.
    linked = expansion(index, shown) if expand else []
    lines.extend(_neighbour_line(n) for n in linked)
    if rest:
        scopes: dict[str, int] = {}
        for h in rest:
            scopes[h.section.scope] = scopes.get(h.section.scope, 0) + 1
        lines.append(f"+{len(rest)} more: " + ", ".join(f"{scope} {n}" for scope, n in sorted(scopes.items())))
    ids = [section_id(h.section) for h in shown] + [section_id(n.section) for n in linked]
    session.shown.update(ids)
    return "\n".join(lines), ids


def read(index: Index, session: Session, args: dict) -> tuple[str, list[str]]:
    ids = args.get("ids")
    if isinstance(ids, str):
        ids = [ids]
    if not isinstance(ids, list) or not ids or not all(isinstance(i, str) and i.strip() for i in ids):
        raise ToolError("ids is required: one or more ids memory_find returned")
    budget = _int(args.get("max_tokens"), "max_tokens", READ_TOKENS, MIN_TOKENS, MAX_TOKENS)
    # (text, the ids the call logs as read, every id the part shows the model): a listing reads the slice, not its sections.
    parts: list[tuple[str, list[str], list[str]]] = []
    for ident in ids:
        ref, _, position = ident.partition("#")
        sections = index.slice_sections(mi.slice_id_of(ref))
        if not sections:
            parts.append((f"{ident}: no such slice", [], []))
        elif not position:
            listing = [section_id(s) for s in sections]
            parts.append(("\n".join(f"{section_id(s)} | {clip(s.heading, 100)} | ~{s.tokens}t" for s in sections), [ref], [ref, *listing]))
        else:
            wanted = [s for s in sections if str(s.position) == position]
            if not wanted:
                parts.append((f"{ident}: no such section", [], []))
                continue
            s = wanted[0]
            head = f"{section_id(s)} · {s.kind} · {s.scope} · {s.role}" + (f" · observed {s.observed}" if s.observed else "")
            head += f" · {DECAY}" if s.kind == "solution" else ""
            related = "".join(f"\nrelated: {section_id(r)} | {clip(r.heading, HEADING_CLIP)}" for r in index.related(s, RELATED))
            parts.append((f"{head}\n## {s.heading}\n{s.text}{related}", [section_id(s)], [section_id(s)]))
    if not any(read_ids for _t, read_ids, _s in parts):
        raise ToolError("; ".join(t for t, _r, _s in parts))
    cut = f"\n[cut at max_tokens {budget}]"
    kept: list[str] = []
    served: list[str] = []
    text = ""
    for part, read_ids, shown_ids in parts:
        if _cost(text + part) > budget:
            room = max(0, int(budget / TOKENS_PER_CHAR) - len(text) - len(cut))      # the marker is inside the budget too
            kept.append(part[:room].rstrip() + cut)
            break
        kept.append(part)
        text += part + "\n\n"
        served.extend(read_ids)             # only what the reply holds: a part the budget dropped was not read
        session.shown.update(shown_ids)
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
        m = INDEX_LINE.fullmatch(line)
        if not m or m.group(1) in seen:
            continue
        seen.add(m.group(1))
        s = known.get(m.group(1))
        if s is None or (project and s.projects and project not in s.projects):
            continue
        out.append((slice_ref(s.slice_id), f"{slice_ref(s.slice_id)} | {s.kind} | {clip(m.group(2), CUE_CLIP)}"))
    session.shown.update(o[0] for o in out)
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
        raise ToolError(f"id {ident!r}: not a section of the corpus")
    # ADR-049 rule 3: only what find, read or index showed this session; a slice id from the index covers its sections.
    if ident not in session.shown and ref not in session.shown:
        raise ToolError(f"id {ident!r}: not shown in this session by memory_find, memory_read or memory_index")
    if not session.state_dir:
        raise ToolError("mark not recorded: this session has no state directory")
    failed = marks.record(session.state_dir, ident, verdict, clip(note, NOTE_CLIP) if note else "", session.project)
    if failed:
        raise ToolError(f"mark not recorded: {failed}")
    return f"marked {ident} {verdict}", [ident]


FRAMED = frozenset({"memory_find", "memory_read", "memory_index"})

TOOLS = {
    "memory_find": (find, "Ranked section hits over the curated memory index: one line each, no body, within a token budget. "
                          "Ask before changing something the fleet may already know.",
                    {"query": {"type": "string"}, "role": {"type": "string"}, "project": {"type": "string"},
                     "limit": {"type": "integer", "minimum": 1, "maximum": MAX_LIMIT},
                     "max_tokens": {"type": "integer", "minimum": MIN_TOKENS, "maximum": MAX_TOKENS},
                     "expand": {"type": "integer", "minimum": 0, "maximum": 1,
                                "description": "1 adds, after the hits, the sections linked to the strong ones (a shared path, a [[link]]); default 0"}},
                    ["query"]),
    "memory_read": (read, "Sections by id (from memory_find), each with its provenance and its related slices' cue lines, cut at "
                          "max_tokens; a slice id alone lists its sections.",
                    {"ids": {"type": "array", "items": {"type": "string"}}, "max_tokens": {"type": "integer", "minimum": MIN_TOKENS,
                                                                                            "maximum": MAX_TOKENS}}, ["ids"]),
    "memory_index": (index, "The index cue lines for a role (default: this session's) and project.",
                     {"role": {"type": "string"}, "project": {"type": "string"}}, []),
    "memory_mark": (mark, "Say whether a section helped, is wrong, or is stale (verdict helpful | wrong | stale, an optional note). "
                          "Recorded in this login's state for the next drain; nothing in the corpus changes.",
                    {"id": {"type": "string"}, "verdict": {"type": "string", "enum": list(VERDICTS)}, "note": {"type": "string"}},
                    ["id", "verdict"]),
}
