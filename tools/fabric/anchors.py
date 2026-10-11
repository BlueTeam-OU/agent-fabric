"""tools/fabric/anchors.py — what an anchor is (agent-fabric ADR-050 rule 1), in one place: stdlib only, so the
harvest, the assembler's intake and the staleness check (memory_check.py) all ask the same question of the same
text, and a line of a slice that no harvest ever validated is held to it too.

An ANCHOR is `<path>` or `<path>::<symbol or literal>`: a repository path that stays inside its tree, and after
`::` a string that file must contain. A memory carries them in its metadata block as one inline list,

    anchors: [tools/fabric/harvest_memory.py::parse_memory, "memory/README.md::a literal, with a comma"]

and a slice's section carries them on a line of its own (`*Anchors: `a::b`, `c`*`). An anchor never holds a backtick
or a line break, which the section's rendering could not carry, and is bounded in number and length.
"""
from __future__ import annotations

ANCHOR_CLASSES = frozenset({"solution", "workflow"})
ANCHORS_MAX = 20
ANCHOR_MAX_LEN = 300


def split_inline_list(value: str) -> list[str] | None:
    """The items of a YAML inline list `[a, "b, c", 'd', 'it''s']`, unquoted; None when the value is no list. A
    comma splits only outside quotes, because a literal an anchor names may contain one; inside single quotes a
    doubled quote is one quote, as YAML reads it."""
    v = value.strip()
    if not (v.startswith("[") and v.endswith("]")):
        return None
    items: list[str] = []
    cur: list[str] = []
    quote = ""
    i, inner = 0, v[1:-1]
    while i < len(inner):
        ch = inner[i]
        if quote:
            if ch == "\\" and quote == '"' and i + 1 < len(inner):
                cur.append(inner[i + 1])
                i += 2
                continue
            if ch == quote:
                if quote == "'" and inner[i + 1:i + 2] == "'":
                    cur.append("'")
                    i += 2
                    continue
                quote = ""
            else:
                cur.append(ch)
        elif ch in "\"'":
            quote = ch
        elif ch == ",":
            items.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
        i += 1
    items.append("".join(cur).strip())
    return [x for x in items if x]


def problem(anchor: str) -> str | None:
    """Why `anchor` is not `<repository path>` or `<repository path>::<symbol or literal>`, or None. The path is
    relative and stays inside its tree; the part after `::` is non-empty; and nothing in it is a backtick, a
    control character or a line break."""
    path, sep, rest = anchor.partition("::")
    if len(anchor) > ANCHOR_MAX_LEN:
        return f"longer than {ANCHOR_MAX_LEN} characters"
    if "`" in anchor or any(ord(c) < 32 or 127 <= ord(c) <= 159 for c in anchor):
        return "holds a backtick or a control character"
    if not path or path.startswith("/") or "\\" in path or any(c.isspace() for c in path):
        return "its path is empty, absolute, or holds a backslash or a space"
    if any(part in ("", ".", "..") for part in path.rstrip("/").split("/")):
        return "its path leaves the tree or is not normal"
    if sep and not rest.strip():
        return "nothing follows `::`"
    return None
