"""tools/fabric/anchors.py — what an anchor is (agent-fabric ADR-050 rule 1), in one place: stdlib only, so the
harvest, the assembler's intake and the staleness check (memory_check.py) all ask the same question of the same
text, and a line of a slice that no harvest ever validated is held to it too.

An ANCHOR is `<path>` or `<path>::<symbol or literal>`: a repository path that stays inside its tree, and after
`::` a string that file must contain. The path is the origin project's unless it is prefixed `<project>:`, a
projects/registry.json id (ADR-050 rule 1 as amended 2026-10-20): `other-project:src/x.py::a literal`. A memory carries them in its metadata block as one inline list,

    anchors: [tools/fabric/harvest_memory.py::parse_memory, "memory/README.md::a literal, with a comma"]

or as the YAML block list a harness that normalises front matter writes back (`anchors:` and `- item` lines, a wrapped item
joined back onto one line), and a slice's section carries them on a line of its own (`*Anchors: `a::b`, `c`*`). An anchor never holds a backtick
or a line break, which the section's rendering could not carry, and is bounded in number and length.
"""
from __future__ import annotations

import re

ANCHOR_CLASSES = frozenset({"solution", "workflow"})
ANCHORS_MAX = 20
ANCHOR_MAX_LEN = 300
# The single colon cannot be taken for `::`, and no path ever held a colon (the claims schema refused one), so an
# anchor written before the prefix existed reads the same. The id's shape is the registry's and the claims schema's:
# it becomes a directory name beside the fabric's checkout, so nothing with a slash or a leading dot gets through.
PROJECT_RE = re.compile(r"[a-z0-9][a-z0-9._-]*")


def split(anchor: str) -> tuple[str | None, str, str]:
    """(project or None, path, symbol or "") of an anchor. `<project>:` is read only before the first `::`, so a
    colon in the symbol or literal is never a project; a prefix that is not an id stays in the path, where
    `problem` refuses it."""
    head, _, symbol = anchor.partition("::")
    project, colon, path = head.partition(":")
    if colon and PROJECT_RE.fullmatch(project):
        return project, path, symbol
    return None, head, symbol


def registry_problem(anchor: str, known: "set[str] | frozenset[str]") -> str | None:
    """Why the project an anchor names is not one the registry (`known`, its ids) names, or None. Asked by the
    harvest and the intake, which have the registry; the staleness check and the section reader do not and need
    not. An empty `known` is a registry that could not be read, which is said as that, not as an unknown name."""
    project = split(anchor)[0]
    if project is None or project in known:
        return None
    if not known:
        return f"names project {project!r}, and projects/registry.json could not be read to check it"
    return f"names project {project!r}, which projects/registry.json does not"


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


def read_list(inline: str | None, block: list[str] | None) -> tuple[list[str] | None, str | None]:
    """(the items, the raw text they came from) of an `anchors:` value in either YAML form: `anchors: [a, "b"]` (inline) or
    `anchors:` followed by `- a` lines (block, which a harness that normalises a memory's front matter writes back). The items
    are None when the value is neither, which the caller says; a block item is one anchor, so it is not split on commas.
    An inline value wins when both appear (the caller says the block was not read). The raw text is what the credential fence reads; None says the
    key is absent (or bare, with nothing under it), which is no anchors and not a problem."""
    if inline:
        return split_inline_list(inline), inline
    if block:
        return list(block), "\n".join(block)
    return None, inline


def problem(anchor: str) -> str | None:
    """Why `anchor` is not `[<project>:]<repository path>` or that with `::<symbol or literal>`, or None. The path is
    relative and stays inside its tree; the part after `::` is non-empty; and nothing in it is a backtick, a
    control character or a line break."""
    _project, path, rest = split(anchor)
    sep = "::" in anchor
    if len(anchor) > ANCHOR_MAX_LEN:
        return f"longer than {ANCHOR_MAX_LEN} characters"
    if re.match(r"[|>][+-]?[0-9]?(\s|$)", anchor):
        return "reads as a YAML block scalar (`|` or `>`): write the anchor on one line"
    if "`" in anchor or any(ord(c) < 32 or 127 <= ord(c) <= 159 for c in anchor):
        return "holds a backtick or a control character"
    if ":" in path:
        return "its path holds a colon: a project is named `<project>:<path>`, by a registry id"
    if not path or path.startswith("/") or "\\" in path or any(c.isspace() for c in path):
        return "its path is empty, absolute, or holds a backslash or a space"
    if any(part in ("", ".", "..") for part in path.rstrip("/").split("/")):
        return "its path leaves the tree or is not normal"
    if sep and not rest.strip():
        return "nothing follows `::`"
    return None
