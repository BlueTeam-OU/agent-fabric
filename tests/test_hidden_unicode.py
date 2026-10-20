#!/usr/bin/env python3
"""Tests for tools/fabric/hidden_unicode.py. One case per refused class and one per allowance, each with its
positive control beside it, so a check removed from the module fails the case that names it."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "tools", "fabric"))
import hidden_unicode as hu  # noqa: E402
from git_env import scrub_process_env  # noqa: E402 — tests/, the script's own directory
scrub_process_env()

MODULE = os.path.join(ROOT, "tools", "fabric", "hidden_unicode.py")


def kinds(text: str, **kw) -> list[str]:
    return [f.kind for f in hu.scan(text, **kw)]


def refused(ch: str, kind: str) -> None:
    found = hu.scan(f"ab{ch}cd")
    assert [(f.line, f.column, f.codepoint, f.kind) for f in found] == [(1, 3, ord(ch), kind)], (hex(ord(ch)), found)
    assert found[0].name, found


def case_clean_text_passes_with_every_script() -> None:
    assert hu.scan("plain\ttext\nline two\n") == []
    assert hu.scan("Привет, мир\nამ დეტალებით\nA B   é é ✔\n") == []   # ru, ka, en, NBSP, combining


def case_bidi_is_refused() -> None:
    for cp in (*range(0x202A, 0x202F), *range(0x2066, 0x206A), 0x200E, 0x200F, 0x061C):
        refused(chr(cp), "bidi")


def case_format_characters_are_refused() -> None:
    for cp in (0x200B, 0x200C, 0x2060, 0x00AD, 0x180E, 0x206A, 0xE0041, 0xE007F):
        refused(chr(cp), "format")
    refused("﻿", "format")   # a BOM inside text is a zero-width no-break space


def case_controls_are_refused() -> None:
    for cp in (*range(0x00, 0x09), *range(0x0B, 0x20), *range(0x7F, 0xA0), 0x2028, 0x2029):
        refused(chr(cp), "control")
    assert kinds("a\r\nb") == ["control"]   # LF line endings only


def case_variation_fillers_and_private_use_are_refused() -> None:
    for cp in (0xFE00, 0xFE0E, 0xE0100):
        refused(chr(cp), "variation")
    for cp in (0x115F, 0x1160, 0x3164, 0xFFA0):
        refused(chr(cp), "filler")
    for ch in ("", "\udc80", "\U000f0000"):
        refused(ch, "private")


def case_lines_and_columns_count_code_points() -> None:
    f = hu.scan("é😀x\n\nab​c\n")
    assert [(x.line, x.column) for x in f] == [(3, 3)], f
    assert str(f[0]) == "3:3: U+200B ZERO WIDTH SPACE (format)"


def case_allowance_tab_and_newline() -> None:
    assert hu.scan("\t\n") == []
    assert kinds("\x0b") == ["control"]   # the control: its neighbours are not


def case_allowance_leading_bom_only() -> None:
    assert hu.scan("﻿a") == []
    assert kinds("﻿a", allow_bom=False) == ["format"]
    assert kinds("a﻿") == ["format"]
    assert kinds("\n﻿") == ["format"]   # offset 0 only, not the start of a line


def case_allowance_zwj_inside_an_emoji_sequence() -> None:
    family = "\U0001F468‍\U0001F469‍\U0001F467"
    assert hu.scan(family) == []
    assert hu.scan("\U0001F469\U0001F3FD‍⚕️") == []   # modifier before ZWJ, VS16 after the symbol
    assert hu.scan("❤️‍\U0001F525") == []   # VS16 before ZWJ
    for bad in ("a‍b", "‍\U0001F469", "\U0001F468‍", "\U0001F468‍a", "\U0001F468 ‍\U0001F469"):
        assert kinds(bad) == ["format"], bad


def case_allowance_vs16_after_symbol_digit_and_hash() -> None:
    for ok in ("✔️", "1️⃣", "#️⃣", "*️⃣"):
        assert hu.scan(ok) == [], ok
    for bad in ("a️", " ️", "️", "\n️"):
        assert kinds(bad) == ["variation"], bad


def case_zwnj_is_not_allowed() -> None:
    # Persian needs it; ru, ka and en do not. A locale that does adds an allowance with a test.
    assert kinds("می‌خواهم") == ["format"]


def case_tag_characters_are_refused_even_in_a_flag() -> None:
    england = "\U0001F3F4" + "".join(chr(0xE0000 + ord(c)) for c in "gbeng") + "\U000E007F"
    assert kinds(england) == ["format"] * 6


def run(*args: str) -> subprocess.CompletedProcess:
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LC_ALL": "C"}
    return subprocess.run([sys.executable, MODULE, *args], capture_output=True, env=env, timeout=60, check=False)


def case_cli_exit_codes_and_lines() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        clean, dirty, binary = (os.path.join(tmp, n) for n in ("clean.md", "dirty.md", "bin.md"))
        open(clean, "w", encoding="utf-8").write("ok\n")
        open(dirty, "w", encoding="utf-8").write("ok\nx‮y​\n")
        open(binary, "wb").write(b"\xff\xfe")
        r = run(clean)
        assert (r.returncode, r.stdout, r.stderr) == (0, b"", b""), r
        r = run(clean, dirty)
        assert r.returncode == 1 and r.stderr == b"", r
        assert r.stdout.decode().splitlines() == [
            f"{dirty}:2:2: U+202E RIGHT-TO-LEFT OVERRIDE (bidi)", f"{dirty}:2:4: U+200B ZERO WIDTH SPACE (format)"], r
        r = run(dirty, binary, os.path.join(tmp, "missing"))
        assert r.returncode == 2, r   # unreadable wins over found, and the other paths were still scanned
        assert b"dirty.md:2:2" in r.stdout and r.stderr.count(b"unreadable") == 2, r
        assert run().returncode == 2


def case_the_fabrics_own_texts_scan_clean() -> None:
    tracked = subprocess.run(["git", "-C", ROOT, "ls-files", "-z"], capture_output=True, timeout=60, check=True,
                             env={"PATH": os.environ.get("PATH", "/usr/bin:/bin")}).stdout.decode().split("\0")
    read = [p for p in tracked if p.endswith(".md") and (
        p.endswith(("CLAUDE.md", "AGENTS.md")) or p.startswith(("identities/", "memory/", ".agent-fabric/"))
        or "/skills/" in p or p.startswith("skills/"))]
    assert len(read) > 50, len(read)   # the control: the filter found the corpus
    bad = []
    for p in read:
        with open(os.path.join(ROOT, p), encoding="utf-8") as fh:
            bad += [f"{p}:{f}" for f in hu.scan(fh.read())]
    assert not bad, bad[:10]


def main() -> int:
    cases = [v for k, v in globals().items() if k.startswith("case_")]
    failures = 0
    for case in cases:
        try:
            case()
            print(f"  ok   {case.__name__}")
        except AssertionError as exc:
            failures += 1
            print(f"  FAIL {case.__name__}: {exc}")
    print(f"\n{len(cases) - failures}/{len(cases)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
