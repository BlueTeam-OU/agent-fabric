#!/usr/bin/env python3
"""Hidden Unicode in text an agent reads: one scanner (owner, 2026-10-20).

    scan(text) -> list[Finding]        line, column, code point, Unicode name, class
    hidden_unicode.py PATH...          one line per finding; exit 0 clean, 1 found, 2 unreadable

Why: a character the reader's eye does not see but the model's tokenizer
does can carry an instruction (tag characters, zero-width runs) or change
which text a human reviewer thinks was read (bidi overrides and isolates).
Three places each checked some of it their own way (addenda_check,
gzcoord send, the locales lint); this is the one definition.

Refused classes (each has a test that fails when its check is removed):
  bidi     U+202A-202E, U+2066-2069, and the marks U+200E, U+200F, U+061C
  format   every Cf character (zero-width space, joiners, word joiner,
           soft hyphen, BOM inside text, Unicode tag characters), plus
           U+180E, which Unicode data before 6.3 called Zs; the clause is kept for
           such data and never fires on a supported interpreter
  control  every Cc but TAB and LF (CR included: LF line endings only), and
           the line and paragraph separators U+2028, U+2029
  variation selectors other than VS16, and the ideographic fillers that
           render blank (U+115F, U+1160, U+3164, U+FFA0)
  private  private-use and surrogate code points: no meaning a reader can
           check

Allowances, the only ones, each because a real file needs it:
  * TAB and LF: the text's own layout.
  * A BOM at offset 0 (allow_bom, default True): a file signature, not
    content, and invisible only where nothing precedes it. Elsewhere it is
    a zero-width no-break space and is refused. Callers whose format
    forbids even that (addenda_check checks the bytes) refuse it first.
  * ZWJ (U+200D) between two emoji symbols (So, a skin-tone modifier or
    VS16 before the next symbol): the glue of family and profession
    emoji. Between anything else it is refused.
  * VS16 (U+FE0F) after a symbol (So), a digit, # or *: the emoji
    presentation selector and the keycap sequence. After a letter or
    space it is refused.
  * ZWNJ (U+200C) is NOT allowed. Persian and several Indic scripts need
    it for correct spelling; our locales are ru, ge and en, none does.
    A locale that needs it adds an allowance here, with the pair of
    scripts it may sit between and a test, not an exemption in a caller.
  * Unicode tag characters are refused even inside the subdivision-flag
    emoji (England, Scotland, Wales): they are the one carrier of
    invisible ASCII, and no text of ours uses those flags.

Not a rule about what text may say, only what it may hide: a visible
character from any script passes.

Adapted from the approach of microsoft/apm's install-time scan for hidden
Unicode (MIT licence, Copyright (c) Microsoft Corporation): the idea of
classing bidi controls, zero-width and tag characters apart. No code was
copied; the classification and the allowances are this module's.

Exit codes: 0 no finding, 1 at least one finding, 2 a path unreadable or
not UTF-8 (reported on stderr, scanning goes on to the other paths; 2
wins over 1).
"""
from __future__ import annotations

import sys
import unicodedata
from typing import NamedTuple

BIDI = frozenset(list(range(0x202A, 0x202F)) + list(range(0x2066, 0x206A)) + [0x200E, 0x200F, 0x061C])
LINE_SEPARATORS = frozenset((0x2028, 0x2029))
FILLERS = frozenset((0x115F, 0x1160, 0x3164, 0xFFA0))
ZWJ = 0x200D
VS16 = 0xFE0F
BOM = 0xFEFF
EMOJI_MODIFIERS = range(0x1F3FB, 0x1F400)
# VS1-15 and the supplementary selectors; VS16 is judged by context.
VARIATION = frozenset(list(range(0xFE00, 0xFE0F)) + list(range(0xE0100, 0xE01F0)))
KEYCAP_BASE = frozenset("#*0123456789")


class Finding(NamedTuple):
    line: int          # 1-based
    column: int        # 1-based, in code points
    codepoint: int
    name: str
    kind: str          # bidi | format | control | variation | filler | private

    def __str__(self) -> str:
        return f"{self.line}:{self.column}: U+{self.codepoint:04X} {self.name} ({self.kind})"


def is_format(c: str) -> bool:
    """One character a reader sees nothing of: Cf, and U+180E in case the Unicode data is older than 6.3. Context
    allowances (ZWJ in an emoji) do not apply: a caller asking this wants every such character gone."""
    return unicodedata.category(c) == "Cf" or ord(c) == 0x180E


def _name(c: str) -> str:
    cp = ord(c)
    return unicodedata.name(c, "") or ("CONTROL" if cp < 0x20 or 0x7F <= cp < 0xA0 else "UNNAMED")


def _is_symbol(c: str) -> bool:
    # So only: Sk would admit ASCII ^ and the backtick, each a carrier of one hidden bit in Markdown.
    return unicodedata.category(c) == "So" or ord(c) in EMOJI_MODIFIERS


def _kind(text: str, i: int, allow_bom: bool) -> str | None:
    c = text[i]
    cp = ord(c)
    if c in "\t\n":
        return None
    if cp < 0x80 and cp >= 0x20 and cp != 0x7F:
        return None   # the common case, before any table lookup
    if cp in BIDI:
        return "bidi"
    if cp == BOM:
        return None if (i == 0 and allow_bom) else "format"
    if cp == ZWJ:
        before = text[i - 1] if i > 0 else ""
        if before and ord(before) == VS16 and i > 1:
            before = text[i - 2]
        after = text[i + 1] if i + 1 < len(text) else ""
        return None if (before and after and _is_symbol(before) and unicodedata.category(after) == "So") else "format"
    if cp == VS16:
        before = text[i - 1] if i > 0 else ""
        return None if before and (_is_symbol(before) or before in KEYCAP_BASE) else "variation"
    if cp in VARIATION:
        return "variation"
    cat = unicodedata.category(c)
    if is_format(c):
        return "format"
    if cat == "Cc" or cp in LINE_SEPARATORS:
        return "control"
    if cp in FILLERS:
        return "filler"
    if cat in ("Co", "Cs"):
        return "private"
    return None


def scan(text: str, *, allow_bom: bool = True) -> list[Finding]:
    """Every offending character of text, in order. Lines split at LF only,
    the one line ending the text may have; a CR or U+2028 is a finding, not
    a break."""
    out: list[Finding] = []
    line, col = 1, 0
    for i, c in enumerate(text):
        col += 1
        kind = _kind(text, i, allow_bom)
        if kind:
            out.append(Finding(line, col, ord(c), _name(c), kind))
        if c == "\n":
            line, col = line + 1, 0
    return out


def main(argv: list[str]) -> int:
    paths = argv[1:]
    if not paths or paths[0] in ("-h", "--help"):
        print("usage: hidden_unicode.py PATH...   (exit 0 clean, 1 found, 2 unreadable)")
        return 0 if paths else 2
    found = unreadable = False
    for path in paths:
        try:
            with open(path, "rb") as f:
                text = f.read().decode("utf-8")
        except (OSError, UnicodeDecodeError) as err:
            print(f"{path}: unreadable: {err.__class__.__name__}: {err}", file=sys.stderr)
            unreadable = True
            continue
        for finding in scan(text):
            print(f"{path}:{finding}")
            found = True
    return 2 if unreadable else 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
