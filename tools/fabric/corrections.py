"""tools/fabric/corrections.py — how a memory's text and a corpus section's text are recognised as the same (agent-fabric
ADR-050 rule 10), in one place, stdlib only: the harvest (on an account, with no corpus beside it) and the assembler (which
renders the section) must compute one key from the two forms the text takes.

  section_key(section)  a short hash of a corpus section's text with the tail lines it carries (`*Observed …*`,
                  `*Anchors: …*`, `*References: …*`) taken off and whitespace collapsed: the same words, whatever date they
                  were written or how they were wrapped.
  memory_key(body)  the same for a memory's body: its headings demoted once first, as the assembler renders it, so that a
                  memory and the section it became have one key (a section's own headings are already demoted).
  demote_headings(text)  every `## `-or-deeper heading one level down: a slice's sections are its `## ` lines.

A key says "this text", never "this meaning": an edited word is another text. Two sections that say the same thing in
different words are not found by it, by design — a hash that guessed would retire a memory its author still means."""
from __future__ import annotations

import hashlib
import re

BODY_HEADING = re.compile(r"(?m)^(#{2,})(?=[ \t]|$)")
TAIL_LINE = re.compile(r"\s*\*(?:Observed|Anchors|References)\b[^\n]*\*\s*$")


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
