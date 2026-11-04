"""tools/fabric/corrections.py — how a memory's text and a corpus section's text are recognised as the same (agent-fabric
ADR-050 rule 10), in one place, stdlib only: the harvest (on an account, with no corpus beside it) and the assembler (which
renders the section) must compute one key from the two forms the text takes.

  section_key(section)  a short hash of a corpus section's text with the tail lines it carries (`*Observed …*`,
                  `*Anchors: …*`, `*References: …*`) taken off and whitespace collapsed: the same words, whatever date they
                  were written or how they were wrapped.
  memory_key(body)  the same for a memory's body: its headings demoted once first, as the assembler renders it, so that a
                  memory and the section it became have one key (a section's own headings are already demoted).
  demote_headings(text)  every `## `-or-deeper heading one level down: a slice's sections are its `## ` lines.
  applied_stems(entries) / unique_stems(found)  the memory name -> slice stem map a drain's links are pointed with, and
                  point_text(text, names), which points them: one pointing, for the assembler that renders a body and the
                  harvest that must recognise one as rendered.

A key says "this text", never "this meaning": an edited word is another text. Two sections that say the same thing in
different words are not found by it, by design — a hash that guessed would retire a memory its author still means."""
from __future__ import annotations

import hashlib
import os
import re
from collections import defaultdict
from collections.abc import Iterable, Mapping
from typing import Any

BODY_HEADING = re.compile(r"(?m)^(#{2,})(?=[ \t]|$)")
# The three tails claim_block writes, in their exact shapes: an italic line of the text that merely starts with the word
# ("*Observed on staging only*") is text.
TAIL_LINE = re.compile(r"(?:^|\n)[ \t]*\*(?:Observed \d{4}-\d{2}-\d{2}(?: \([a-z0-9-]+\))?|Anchors: [^\n]*|References: [^\n]*)\*\s*$")


def demote_headings(text: str) -> str:
    """Every heading of level two or deeper one level down. A slice's sections are its `## ` lines — read_existing_slice
    splits there — so a claim body that keeps the `## ` headings its memory had opened sections of its own: the first part
    lost its dated footer, and re-assembling the same bundle was refused as a collision with itself (a drain's blind
    review, 2026-09-25). Fenced code is demoted too: the reader does not know fences, and a split inside one is the same
    break."""
    return BODY_HEADING.sub(r"#\1", text)


def section_key(section: str) -> str:
    """The key of a corpus section's text, as it stands in a slice: already demoted, with its tail lines."""
    body = section.strip()
    while True:
        stripped = TAIL_LINE.sub("", body)
        if stripped == body:
            break
        body = stripped
    return hashlib.sha256(" ".join(body.split()).encode("utf-8")).hexdigest()[:16]


def memory_key(body: str) -> str:
    """The key of a memory's body: the text the assembler would render, so its headings demoted once, as a section's are."""
    return section_key(demote_headings(body.strip()))


REFERENCES_RE = re.compile(r"^\*References: (.*)\*$", re.M)


def point_text(text: str, names: dict[str, str]) -> str:
    """`text` with every `[[name]]` and every name on a `*References: …*` line pointed at the slice it was written into.
    The References line lists the memories a claim links (harvest_memory), so a link repointed and its citation left naming
    the old topic would disagree inside one section. A rewritten line is sorted and deduplicated as
    claim_block renders it; a line naming none of `names` is untouched."""
    if not names:
        return text
    link = re.compile(r"\[\[(" + "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True)) + r")\]\]")

    def references(found: re.Match[str]) -> str:
        items = found.group(1).split(", ")
        if not any(i in names for i in items):
            return found.group(0)
        return "*References: " + ", ".join(sorted({names.get(i, i) for i in items})) + "*"
    return REFERENCES_RE.sub(references, link.sub(lambda m: f"[[{names[m.group(1)]}]]", text))


def applied_stems(entries: Iterable[Any]) -> list[tuple[str | None, str, str]]:
    """(role, memory name, file stem) of each applied_corrections entry of a report: the memory was written into that
    slice, whichever run its links arrive in. The role is the slice path's (None for shared). An entry that has no
    `memory` and `slice` strings is not one."""
    found: list[tuple[str | None, str, str]] = []
    for entry in entries:
        if not (isinstance(entry, dict) and isinstance(entry.get("memory"), str) and isinstance(entry.get("slice"), str)):
            continue
        m = re.search(r"memory/(?:domains/)?([^/]+)/", entry["slice"])
        role = None if not m or m.group(1) == "shared" else m.group(1)
        found.append((role, entry["memory"], os.path.basename(entry["slice"]).removesuffix(".md")))
    return found


def unique_stems(found: Iterable[tuple[str | None, str, str]]) -> dict[tuple[str | None, str], str]:
    """{(role, name): stem} for each memory that moved to exactly one stem other than its own name: a name two slices
    claim is left as written, because pointing at either would guess."""
    stems: dict[tuple[str | None, str], set[str]] = defaultdict(set)
    for role, name, stem in found:
        if name != stem:
            stems[(role, name)].add(stem)
    return {key: next(iter(s)) for key, s in stems.items() if len(s) == 1}


def names_in(unique: Mapping[tuple[str | None, str], str], scopes: tuple[str | None, ...]) -> dict[str, str]:
    """The {name: stem} map for the roles in `scopes` (a role's own and the shared one: another role's memory of the
    same name is not that one)."""
    return {name: stem for (r, name), stem in unique.items() if r in scopes}
