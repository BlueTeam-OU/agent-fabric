#!/usr/bin/env python3
"""The GZCOORD/1 protocol suite's function cases, ported case for case from
communication/gzcoord/tests/protocol.test.mjs to the Python tools
(tools/fabric/gzcoord/, agent-fabric ADR-040 §7, Wave 7). The suite's
command cases stay in that file and run unchanged against the shims; a
case that both calls a function and runs a command is ported whole. Each
case keeps its name and its reason; where the Node's name for a function
differs (camelCase), the Python one is used. Plain script: prints ok/FAIL,
exit 1 on any failure."""
from __future__ import annotations

import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import traceback
from typing import Any, Callable

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
from gzcoord import gzmsg, inbox, send  # noqa: E402
from gzcoord import jsvalues  # noqa: E402

GZCOORD = os.path.join(HERE, "communication", "gzcoord")
# The operator's instance data is a fixture tree (ADR-045 §5 rule 3), never
# this checkout's live catalogue or integration.
FIXTURE_OPERATOR = os.path.join(HERE, "tests", "fixtures", "gzcoord-operator")
CATALOG = os.path.join(FIXTURE_OPERATOR, "identities", "roles", "catalog.json")
taxonomy = gzmsg.load_taxonomy(CATALOG)
validate, parse = gzmsg.validate, gzmsg.parse

CASES: list[tuple[str, Callable[[], None]]] = []
# Every scratch directory a case makes, removed when the run ends.
SCRATCH: list[str] = []

# The protocol is held against a catalogue and the gzapp integration, which
# are instance data (ADR-045): the cases read them from an operator tree of
# their own, a copy of the fixture's, so the result is the same whatever
# AGENT_FABRIC_OPERATOR the run was started with.
OPERATOR = tempfile.mkdtemp(prefix="gzcoord-operator-")
SCRATCH.append(OPERATOR)
for _rel in ("identities/roles/catalog.json", "projects/gzapp/integration/gzcoord/config.json"):
    os.makedirs(os.path.dirname(os.path.join(OPERATOR, _rel)), exist_ok=True)
    shutil.copy(os.path.join(FIXTURE_OPERATOR, _rel), os.path.join(OPERATOR, _rel))
os.environ["AGENT_FABRIC_OPERATOR"] = OPERATOR


def case(name: str) -> Callable:
    def add(fn: Callable[[], None]) -> Callable[[], None]:
        CASES.append((name, fn))
        return fn
    return add


class Failed(AssertionError):
    pass


def eq(a: Any, b: Any, msg: str = "") -> None:
    if a != b:
        raise Failed(f"{msg + ': ' if msg else ''}{a!r} != {b!r}")


def ok(cond: Any, msg: str = "") -> None:
    if not cond:
        raise Failed(msg or "expected a truthy value")


HEAD = "[GZCOORD/1] INFO\nFROM: develop-gzapp/gzapp\nROLE: Application Architect\nPROJECT: gzapp\nMESSAGE-ID: test-0001\n"


@case("every inline GZCOORD example in MESSAGE-FORMAT.md validates")
def _():
    with open(os.path.join(GZCOORD, "protocol", "MESSAGE-FORMAT.md"), encoding="utf-8") as fh:
        doc = fh.read()
    # The §Shape template ("[GZCOORD/1] TYPE", placeholder keys) is the grammar shown, not a message.
    blocks = [m.group(1) for m in re.finditer(r"```text\n(\[GZCOORD/1\] (?!TYPE\b)[^\n]*\n[\s\S]*?)```", doc)]
    ok(len(blocks) >= 2, f"expected the document's inline examples, found {len(blocks)}")
    for b in blocks:
        # [ \t]*, never \s*: with the m flag \s* eats the newline and the blank
        # line that separates metadata from body, gluing NOTES: onto the block.
        text = re.sub(r"^(MESSAGE-ID|IN-REPLY-TO): .*…[ \t]*$",
                      lambda m: f"{m.group(1)}: 01a09fc1-0000-7000-8000-000000000000", b, flags=re.M)
        r = validate(text, taxonomy=taxonomy)
        subject = re.search(r"^SUBJECT: (.*)$", b, re.M)
        eq(r["errors"], [], f"{b.split(chr(10))[0]} / {subject.group(1) if subject else '(no subject)'}")


for _name in ("observation", "observation-diagnosis", "reply", "review"):
    def _example(name: str = _name) -> None:
        with open(os.path.join(GZCOORD, "protocol", "examples", f"{name}.txt"), encoding="utf-8") as fh:
            text = fh.read()
        # Under the deployment's catalogue: the examples are what sessions copy.
        result = validate(text, taxonomy=taxonomy)
        eq(result["errors"], [])
        eq(result["warnings"], [])
    CASES.append((f"{_name} example is valid", _example))


@case("runtime model must not leak into protocol")
def _():
    eq(validate(HEAD + "BROADCAST: true\nMODEL: secret-model\n")["ok"], False)


@case("normal messages require a routing target or broadcast")
def _():
    eq(validate(HEAD)["ok"], False)


@case("address is logical host/instance")
def _():
    text = "[GZCOORD/1] INFO\nFROM: /srv/gzapp/mobile\nROLE: Mobile Engineer\nPROJECT: gzapp\nMESSAGE-ID: test-0001\nBROADCAST: true\n"
    eq(validate(text)["errors"], ["FROM must be <host>/<instance>"])


# One entry per runtime/transport term SPEC.md §14-§15 keeps off the wire, in
# the spelling the spec itself uses — a near-miss spelling in FORBIDDEN
# silently admits the exact field the spec names.
@case("transport-native identifiers are forbidden core metadata")
def _():
    for field in ("TELEGRAM-CHAT-ID", "SLACK-CHANNEL-ID", "DISCORD-GUILD-ID", "TOKEN-BUDGET", "REASONING-BUDGET",
                  "MODEL", "PROVIDER", "WORKING-DIRECTORY", "SUBAGENT-DEPTH"):
        eq(validate(HEAD + f"BROADCAST: true\n{field}: leaked\n")["ok"], False, f"{field} must be rejected")


@case("a malformed metadata line is reported, not silently dropped")
def _():
    # `_` is not a metadata key character, so this never became metadata and
    # the forbidden-field check could not see it — the message validated clean
    # while carrying runtime config the sender believed it had sent.
    result = validate(HEAD + "BROADCAST: true\nTOKEN_BUDGET: leaked\n")
    eq(result["ok"], False)
    ok(any("TOKEN_BUDGET" in e for e in result["errors"]))
    eq(result["message"]["metadata"].get("TOKEN_BUDGET"), None)


@case("body lines after a section marker are never malformed metadata")
def _():
    text = HEAD + "BROADCAST: true\n\nNOTES:\nplain prose, no colon at all\nTOKEN_BUDGET: quoted from another message\n"
    eq(validate(text)["errors"], [])


@case("TO must be a logical address when present")
def _():
    eq(validate(HEAD + "TO: @telegram_username\n")["ok"], False)


@case("a repeated section marker resumes the section instead of replacing it")
def _():
    # MESSAGE-FORMAT.md does not require section names to be unique, so a
    # second marker used to blank the first block and still validate clean —
    # the sender was told the message was good while half its content was gone.
    text = HEAD + "BROADCAST: true\n\nNOTES:\nfirst block\n\nNOTES:\nsecond block\n"
    msg = parse(text)
    ok("first block" in msg["sections"]["NOTES"])
    ok("second block" in msg["sections"]["NOTES"])
    eq(validate(text)["errors"], [])


@case("metadata block ends at the first section marker")
def _():
    text = HEAD + ("BROADCAST: true\n\nREFERENCES:\nPR: #184\n- path: contracts/passenger/eta.yaml\n\nNOTES:\n"
                   "KEY: value shaped lines stay in the body.\n")
    msg = parse(text)
    eq(msg["metadata"].get("PR"), None)
    eq(msg["metadata"].get("KEY"), None)
    ok("PR: #184" in msg["sections"]["REFERENCES"])
    ok("KEY: value shaped lines" in msg["sections"]["NOTES"])
    eq(validate(text)["ok"], True)


# SPEC §7.4: REPLY-EXPECTED is an optional common field, so it must pass as
# ordinary metadata and survive the forbidden-field check untouched.
@case("REPLY-EXPECTED is ordinary optional metadata")
def _():
    result = validate(HEAD + "BROADCAST: true\nREPLY-EXPECTED: no\n")
    eq(result["errors"], [])
    eq(result["message"]["metadata"]["REPLY-EXPECTED"], "no")


# SPEC §7.4 gives REPLY-EXPECTED a closed grammar, and the relay procedure
# makes senders rely on this validator — so a value outside it must fail here,
# not reach the carrier with undefined reply semantics. Lowercase only,
# matching the exact-match convention for BROADCAST: true.
@case("REPLY-EXPECTED rejects a value outside yes | no")
def _():
    for value in ("maybe", "Yes", "NO", "true"):
        result = validate(HEAD + f"BROADCAST: true\nREPLY-EXPECTED: {value}\n")
        eq(result["ok"], False, f"{value} must be rejected")
        ok(any("REPLY-EXPECTED" in e for e in result["errors"]))


@case("REPLY-EXPECTED accepts yes and no")
def _():
    for value in ("yes", "no"):
        eq(validate(HEAD + f"BROADCAST: true\nREPLY-EXPECTED: {value}\n")["errors"], [])


# SPEC §6: a repeated metadata key has no defined meaning, and last-write-wins
# let an invalid earlier value hide behind a valid later one — observed for
# REPLY-EXPECTED and for a malformed FROM, which §18 already MUST reject.
@case("a duplicated metadata key is rejected even when the last value is valid")
def _():
    for dup, first, last in (("REPLY-EXPECTED", "maybe", "no"), ("FROM", "bad", "develop-gzapp/gzapp")):
        base = "" if dup == "FROM" else "FROM: develop-gzapp/gzapp\n"
        text = (f"[GZCOORD/1] INFO\n{base}{dup}: {first}\n{dup}: {last}\nROLE: Application Architect\nPROJECT: gzapp\n"
                f"MESSAGE-ID: test-0001\nBROADCAST: true\n")
        result = validate(text)
        eq(result["ok"], False, f"{dup} duplicate must be rejected")
        ok(any(dup in e and "more than once" in e for e in result["errors"]))


@case("a message with no duplicated key reports none")
def _():
    result = validate(HEAD + "BROADCAST: true\nREPLY-EXPECTED: no\n")
    eq(result["errors"], [])
    eq(result["message"]["duplicateKeys"], [])


# A relay-indented marker is body text by §6 and the message validates, so the
# "ask for a re-send on failure" rule never fires. The validator warns instead
# of failing — content may legitimately look like this — and never promotes
# the line to a marker.
@case("an indented marker-shaped body line warns instead of silently merging")
def _():
    text = HEAD + "BROADCAST: true\n\nNOTES:\n  first body line\n REFERENCES:\n  - path: contracts/passenger/eta.yaml\n"
    result = validate(text)
    eq(result["ok"], True)
    eq(result["errors"], [])
    ok(any("REFERENCES" in w for w in result["warnings"]))
    eq(result["message"]["sections"].get("REFERENCES"), None)


# A header the parser cannot read used to escape validate() as an uncaught
# exception — a stack trace on the CLI, and a caller that could not tell a bad
# header from a crashed validator.
@case("a bad first line is a validation error, not an exception")
def _():
    for first in ("GZCOORD/1 INFO", "[GZCOORD/2] INFO", "[GZCOORD/1] INFO ", "[GZCOORD/1] info"):
        result = validate(f"{first}\nFROM: develop-gzapp/gzapp\nROLE: Application Architect\nPROJECT: gzapp\n")
        eq(result["ok"], False, f"{json.dumps(first)} must be rejected")
        ok(any("first line" in e for e in result["errors"]))
        eq(result["message"], None)


@case("a leading byte-order mark does not invalidate the header")
def _():
    eq(validate("﻿" + HEAD + "BROADCAST: true\n")["errors"], [])


def gzmsg_cli(*args: str) -> "subprocess.CompletedProcess[str]":
    """The command at its contract's path: bin/gzmsg, the name everything inside the fabric uses."""
    return subprocess.run([os.path.join(os.path.dirname(os.path.dirname(GZCOORD)), "bin", "gzmsg"), *args], capture_output=True,
                          text=True, timeout=120, stdin=subprocess.DEVNULL)


def scratch_file(text: str) -> str:
    d = tempfile.mkdtemp(prefix="gzcoord-protocol-")
    SCRATCH.append(d)
    path = os.path.join(d, "m.txt")
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)
    return path


# SPEC §7.1: BROADCAST has one value. Any other spelling either fell through
# to the routing error — which named the wrong fault — or, next to a TO,
# validated clean with a meaning the spec does not define.
@case("BROADCAST rejects a value other than true")
def _():
    for value, routing in (("yes", ""), ("True", ""), ("false", "TO: develop-gzapp/web\n"), ("1", "TO-ROLE: Web Engineer\n")):
        result = validate(HEAD + f"{routing}BROADCAST: {value}\n")
        eq(result["ok"], False, f"{value} must be rejected")
        ok(any(e.startswith("BROADCAST must be true") for e in result["errors"]), f"{value}: {result['errors']}")


@case("BROADCAST: true routes on its own, and absent BROADCAST is not an error")
def _():
    eq(validate(HEAD + "BROADCAST: true\n")["errors"], [])
    eq(validate(HEAD + "TO: develop-gzapp/web\n")["errors"], [])


# Trailing whitespace is the other way a marker stops being one, and the only
# way that is invisible in a terminal. Same warning, same rule: named, never
# promoted.
@case("a marker-shaped body line with trailing whitespace warns instead of silently merging")
def _():
    result = validate(HEAD + "BROADCAST: true\n\nNOTES:\nbody\nREFERENCES: \n- adr: ADR-001\n")
    eq(result["ok"], True)
    ok(any("REFERENCES" in w for w in result["warnings"]))
    eq(result["message"]["sections"].get("REFERENCES"), None)
    ok("- adr: ADR-001" in result["message"]["sections"]["NOTES"])


@case("an empty-valued metadata key warns, and the CLI prints the warning beside the errors")
def _():
    text = HEAD + "BROADCAST: true\nNOTES: \nbody here\n"
    result = validate(text)
    eq(result["ok"], False)
    ok(any(w.startswith("NOTES has an empty value") for w in result["warnings"]))
    run = gzmsg_cli("validate", scratch_file(text))
    eq(run.returncode, 1)
    ok(re.search(r"^warning: NOTES has an empty value", run.stderr, re.M), run.stderr)
    ok(re.search(r"unparsable line in the metadata block: body here", run.stderr), run.stderr)


# HUMAN-RELAY-TRANSPORT.md "Sending" caps lines at 72 because a terminal copy
# re-breaks longer ones and a re-broken metadata line is no longer metadata.
# Nothing enforced it; three of the five examples broke it.
@case("a line over 72 characters warns, naming the line, and stays valid")
def _():
    long = "x" * 73
    text = HEAD + f"BROADCAST: true\nSPECIALTIES: {long}\n\nABOUT:\n{long}\n"
    result = validate(text)
    eq(result["ok"], True)
    lines = [w for w in result["warnings"] if "re-breaks it" in w]
    eq(len(lines), 2)
    ok(re.match(r"line 7 is 86 columns wide; over 72 a terminal copy re-breaks it", lines[0]), lines[0])
    ok(re.match(r"line 10 is 73 columns wide", lines[1]), lines[1])
    # Off (the bridge path): no width warning at any length.
    eq([w for w in validate(text, max_columns=0)["warnings"] if "columns wide" in w], [])
    # Exactly 72 is inside the limit.
    eq(validate(HEAD + "BROADCAST: true\n\nNOTES:\n" + "y" * 72 + "\n")["warnings"], [])


# SPEC §6: the well-formed separator is one space; a tab or nothing is not a
# separator (normative), and a reader MAY accept a run of spaces and trim (an
# allowance — this pins what the reference does, not what a conforming parser
# must). Nothing pinned any of it: a regex that dropped the space requirement
# altogether left every test green.
@case("reference parser: separator is one space, tolerates a run, rejects tab and nothing")
def _():
    base = "ROLE: Application Architect\nPROJECT: gzapp\nMESSAGE-ID: test-0001\nBROADCAST: true\n"
    for line, good in (("FROM: develop-gzapp/gzapp", True), ("FROM:   develop-gzapp/gzapp   ", True),
                       ("FROM:develop-gzapp/gzapp", False), ("FROM:\tdevelop-gzapp/gzapp", False)):
        result = validate(f"[GZCOORD/1] INFO\n{line}\n{base}")
        eq(result["ok"], good, json.dumps(line))
        if good:
            eq(result["message"]["metadata"]["FROM"], "develop-gzapp/gzapp")
        else:
            ok(any(e.startswith("unparsable line in the metadata block: FROM") for e in result["errors"]), json.dumps(line))


# The relay re-breaks on columns, and String.length is UTF-16 code units: 40
# CJK characters counted 49 and rendered at 89, no warning; 40 combining
# sequences counted 89 and rendered at 49, a false warning. Each row is what
# `wc -L` reports for the same line.
@case("columns() approximates terminal width where String.length does not")
def _():
    for line, width in (
        ("SUBJECT: " + "線" * 40, 89),            # CJK: 2 each
        ("SUBJECT: " + "\U0001F68C" * 40, 89),        # wide emoji: 2 each
        ("SUBJECT: " + "©" * 32, 41),            # text-default pictograph ©: 1 each
        ("SUBJECT: instance↔instance", 26),       # ↔ as the repo writes it: 1
        ("SUBJECT: \U0001F1EC\U0001F1EA", 11),         # flag pair: 2 total, not 4
        ("SUBJECT: " + "Ａ" * 32, 73),            # fullwidth Latin: 2 each (was 1)
        ("SUBJECT: 　、。", 15),           # ideographic space and punctuation: 2 each
        ("SUBJECT: " + "ｶ" * 40, 49),            # halfwidth katakana: 1 each (was 2, a false warning)
        ("SUBJECT: " + "\U0001B001" * 40, 89),        # kana supplement: 2, outside the classic table
        ("SUBJECT: " + "\U0001D400" * 40, 49),        # narrow astral: 1 each
        ("SUBJECT: " + "é" * 40, 49),           # combining: 0
        ("SUBJECT: მარშ марш", 18),  # Georgian, Cyrillic: 1 each
        ("SUBJECT: a\tb", 17),                         # tab to next multiple of 8
        ("x" * 72, 72),
        ("SUBJECT: " + "☰" * 36, 81),            # trigrams: Wide since Unicode 16, missed by the classic table
    ):
        eq(gzmsg.columns(line), width, json.dumps(line[:20]))
    # Every boundary of the range table, from both sides, so an off-by-one or a
    # deleted range cannot pass: (code point, width). Rows expecting 0 are
    # combining or format characters decided by the ZERO branch before the
    # table is consulted; they pin that branch, not a boundary.
    for cp, width in (
        (0x10FF, 1), (0x1100, 2), (0x115F, 2), (0x1160, 1),
        (0x2328, 1), (0x2329, 2), (0x232A, 2), (0x232B, 1),
        (0x262F, 1), (0x2630, 2), (0x2637, 2), (0x2638, 1), (0x2689, 1), (0x268A, 2), (0x268F, 2), (0x2690, 1),
        (0x2E7F, 1), (0x2E80, 2), (0x303E, 2), (0x303F, 1), (0x3040, 1), (0x3041, 2), (0x3248, 2), (0x33FF, 2),
        (0x3400, 2), (0x4DBF, 2), (0x4DC0, 2), (0x4DFF, 2), (0x4E00, 2), (0x9FFF, 2), (0xA000, 2), (0xA4CF, 2), (0xA4D0, 1),
        (0xA95F, 1), (0xA960, 2), (0xA97C, 2), (0xA97F, 2), (0xA980, 0), (0xABFF, 1), (0xAC00, 2), (0xD7A3, 2), (0xD7A4, 1),
        (0xF8FF, 1), (0xF900, 2), (0xFAFF, 2), (0xFB00, 1), (0xFE0F, 0), (0xFE10, 2), (0xFE19, 2), (0xFE1A, 1),
        (0xFE2F, 0), (0xFE30, 2), (0xFE4F, 2), (0xFE50, 2), (0xFE6B, 2), (0xFE6C, 1),
        (0xFEFF, 0), (0xFF00, 2), (0xFF60, 2), (0xFF61, 1), (0xFF9F, 1), (0xFFDF, 1), (0xFFE0, 2), (0xFFE6, 2), (0xFFE7, 1),
        (0x16FDF, 1), (0x16FE0, 2), (0x16FF1, 2), (0x16FF2, 2), (0x16FFF, 2), (0x17000, 2), (0x18AFF, 2),
        (0x18B00, 2), (0x18CD5, 2), (0x18CFF, 2), (0x18D00, 2), (0x18D08, 2), (0x18D09, 2),
        (0x18D8F, 2), (0x18D90, 2), (0x18DF2, 2), (0x18DFF, 2), (0x18E00, 1),
        (0x1AFEF, 1), (0x1AFF0, 2), (0x1B000, 2), (0x1B001, 2), (0x1B2FB, 2), (0x1B2FF, 2), (0x1B300, 1),
        (0x1D2FF, 1), (0x1D300, 2), (0x1D376, 2), (0x1D377, 1), (0x1F1FF, 1), (0x1F200, 2), (0x1F26F, 2), (0x1F270, 1),
        (0x1FFFD, 1), (0x20000, 2), (0x2FFFD, 2), (0x2FFFE, 1), (0x30000, 2), (0x3FFFD, 2), (0x3FFFE, 1),
    ):
        eq(gzmsg.columns(chr(cp)), width, f"U+{cp:X}")
    head = "FROM: develop-gzapp/gzapp\nROLE: Application Architect\nPROJECT: gzapp\nBROADCAST: true\n"
    cjk = validate(f"[GZCOORD/1] INFO\n{head}SUBJECT: {chr(0x7DDA) * 40}\n")
    ok(any(w.startswith("line 6 is 89 columns wide") for w in cjk["warnings"]), cjk["warnings"])
    combining = "e\u0301" * 40
    eq(validate(f"[GZCOORD/1] INFO\n{head}SUBJECT: {combining}\n")["warnings"], [])


# The relay indents on paste — every line by two, the first by one, a single
# marker by a third — observed twice on the first day. normalize() is the
# documented two-step rule: metadata block stripped unconditionally, body
# stripped only of a uniform prefix, never a body line reclassified by shape.
@case("normalize undoes paste indentation without reclassifying body text")
def _():
    normalize = gzmsg.normalize
    pasted = (" [GZCOORD/1] INFO\n  FROM: develop-gzapp/gzapp\n  ROLE: Application Architect\n  PROJECT: gzapp\n"
              "MESSAGE-ID: test-0001\n  BROADCAST: true\n  \n  NOTES:\n  first\n   NOTES:\n  second\n  \n  REFERENCES:\n"
              "  - adr: ADR-001\n")
    text = normalize(pasted)
    ok(re.match(r"\[GZCOORD/1\] INFO\nFROM: ", text), text)
    result = validate(text)
    eq(result["errors"], [])
    ok("- adr: ADR-001" in result["message"]["sections"]["REFERENCES"])
    # The odd-one-out marker keeps its one extra space and is warned about, not promoted.
    ok(" NOTES:" in result["message"]["sections"]["NOTES"])
    ok(any("swallowed section marker" in w for w in result["warnings"]))
    # The carrier prefix comes from the metadata block, never from the body: a
    # clean message whose only section is uniformly indented keeps it, and a
    # content line shaped like a marker stays content.
    clean_indented = ("[GZCOORD/1] INFO\nFROM: develop-gzapp/gzapp\nROLE: R\nPROJECT: gzapp\nMESSAGE-ID: test-0001\n"
                      "BROADCAST: true\n\nNOTES:\n  the config we discussed:\n  YAML:\n  key: value\n")
    eq(normalize(clean_indented), clean_indented)
    eq(list(validate(clean_indented)["message"]["sections"]), ["NOTES"])
    # Under a uniform paste the sender's indented marker-shaped line comes back
    # indented and stays body; a marker-shaped line at exactly the carrier
    # prefix was written at column 0 and is a marker.
    uniform = normalize("  [GZCOORD/1] INFO\n  FROM: develop-gzapp/gzapp\n  ROLE: R\n  PROJECT: gzapp\nMESSAGE-ID: test-0001\n"
                        "  BROADCAST: true\n\n  NOTES:\n  flush\n    YAML:\n  key: value\n  REFERENCES:\n  - adr: ADR-001\n")
    eq(uniform, "[GZCOORD/1] INFO\nFROM: develop-gzapp/gzapp\nROLE: R\nPROJECT: gzapp\nMESSAGE-ID: test-0001\n"
                "BROADCAST: true\n\nNOTES:\nflush\n  YAML:\nkey: value\nREFERENCES:\n- adr: ADR-001\n")
    eq(list(validate(uniform)["message"]["sections"]), ["NOTES", "REFERENCES"])
    # The first marker is not the source: a paste that indented it oddly still
    # strips the body by the metadata block's prefix.
    odd_first_marker = normalize(" [GZCOORD/1] INFO\n  FROM: develop-gzapp/gzapp\n  ROLE: R\n  PROJECT: gzapp\n"
                                 "MESSAGE-ID: test-0001\n  BROADCAST: true\n  \n   NOTES:\n  first\n  \n  REFERENCES:\n"
                                 "  - adr: ADR-001\n")
    ok("- adr: ADR-001" in validate(odd_first_marker)["message"]["sections"]["REFERENCES"])
    # Already-clean input is unchanged, and a message with no body is handled.
    for name in ("observation", "observation-diagnosis", "reply", "review"):
        with open(os.path.join(GZCOORD, "protocol", "examples", f"{name}.txt"), encoding="utf-8", newline="") as fh:
            clean = fh.read()
        eq(normalize(clean), clean, name)
    eq(normalize("  [GZCOORD/1] INFO\n  FROM: a/b\n  ROLE: R\n  PROJECT: p\n"), "[GZCOORD/1] INFO\nFROM: a/b\nROLE: R\nPROJECT: p\n")


# SPEC §13: an assignment goes TO one instance. Both holders of a role executed
# one OBSERVATION with a REQUEST: section (2026-09-19, two PRs on the same
# hunk); a REQUEST type or a REQUEST:/ACCEPTANCE:/DELIVER-TO: section addressed
# TO-ROLE is refused, and the same body TO an instance or an
# INFO/DECISION/QUESTION TO-ROLE without those sections passes.
@case("an assignment TO-ROLE is refused; the same TO an instance, and a non-assignment TO-ROLE, pass")
def _():
    def head(t: str) -> str:
        return f"[GZCOORD/1] {t}\nFROM: develop-gzapp/gzapp\nROLE: Application Architect\nPROJECT: gzapp\nMESSAGE-ID: test-0001\n"
    r = validate(f"{head('REQUEST')}TO-ROLE: Web Engineer\n\nREQUEST:\nmove the line\n")
    ok(any("a REQUEST is an assignment" in e for e in r["errors"]), r["errors"])
    eq(validate(f"{head('REQUEST')}TO: develop-gzapp/web\n\nREQUEST:\nmove the line\n")["errors"], [])
    for section in ("REQUEST", "ACCEPTANCE", "DELIVER-TO"):
        r = validate(f"{head('OBSERVATION')}TO-ROLE: Web Engineer\n\nOBSERVATION:\nseen\n\n{section}:\nfix it\n")
        ok(any(f"{section} section" in e and "never TO-ROLE" in e for e in r["errors"]), f"{section}: {r['errors']}")
        eq(validate(f"{head('OBSERVATION')}TO: develop-gzapp/web\n\nOBSERVATION:\nseen\n\n{section}:\nfix it\n")["errors"],
           [], section)
    r = validate(f"{head('OBSERVATION')}TO-ROLE: Web Engineer\n\nOBSERVATION:\nseen\n\nREQUEST:\nfix it\n\nACCEPTANCE:\nit is fixed\n")
    ok(any("REQUEST and ACCEPTANCE sections" in e for e in r["errors"]), r["errors"])
    for typ, body in (("INFO", "INFO:\nfyi\n"), ("DECISION", "DECISION:\nso decided\n"), ("QUESTION", "QUESTION:\nwhich?\n"),
                      ("OBSERVATION", "OBSERVATION:\nseen, no ask\n")):
        eq(validate(f"{head(typ)}TO-ROLE: Web Engineer\n\n{body}")["errors"], [], typ)


# SPEC §7.1: one addressing field, the delivery scope. Live traffic carried TO
# beside a TO-ROLE that matched no recorded role, and nothing noticed, because
# the address had already routed the message; a transport filtering by
# addressee could not obey two.
@case("exactly one of TO, TO-ROLE, BROADCAST")
def _():
    for pair in ("TO: develop-gzapp/web\nTO-ROLE: Web Engineer\n", "TO: develop-gzapp/web\nBROADCAST: true\n",
                 "BROADCAST: true\nTO-ROLE: Web Engineer\n"):
        r = validate(HEAD + pair)
        eq(r["ok"], False, pair)
        ok(any("are exclusive" in e for e in r["errors"]), r["errors"])
    for one in ("TO: develop-gzapp/web\n", "TO-ROLE: Web Engineer\n", "BROADCAST: true\n"):
        eq(validate(HEAD + one)["errors"], [], one)
    ok("missing TO, TO-ROLE or BROADCAST: true" in validate(HEAD)["errors"], "none at all")


# SPEC §8, §18: HELLO and GOODBYE are retired, and a parser rejects one naming
# the type as retired — with or without an addressing field, which the old
# special case forbade — while every other core type still passes.
@case("HELLO and GOODBYE are rejected as retired; every other core type passes")
def _():
    def head(t: str) -> str:
        return f"[GZCOORD/1] {t}\nFROM: develop-gzapp/gzapp\nROLE: Application Architect\nPROJECT: gzapp\nMESSAGE-ID: test-0001\n"
    for typ in ("HELLO", "GOODBYE"):
        for addressing in ("", "BROADCAST: true\n", "TO: develop-gzapp/web\n"):
            r = validate(head(typ) + addressing)
            eq(r["ok"], False, f"{typ} {json.dumps(addressing)}")
            ok(f"{typ} is retired (SPEC §8): whether an instance is running is presence, not an announcement" in r["errors"],
               r["errors"])
            ok(not any(e.startswith("unknown type") for e in r["errors"]), r["errors"])
    cli = gzmsg_cli("validate", "--no-taxonomy", scratch_file(head("HELLO") + "BROADCAST: true\n"))
    eq(cli.returncode, 1)
    ok(re.search(r"^HELLO is retired \(SPEC §8\)", cli.stderr, re.M), cli.stderr)
    for typ in ("INFO", "OBSERVATION", "QUESTION", "REQUEST", "REVIEW", "DECISION", "HANDOFF", "REPLY"):
        eq(validate(head(typ) + "TO: develop-gzapp/web\n")["errors"], [], typ)


# SPEC §4 deployment catalogue: ROLE and TO-ROLE are taxonomy slugs, matched by
# equality. One role was live in three spellings on the relay's first day. The
# address is NOT bound to the role: a role can change without the address
# changing (§4), and a legacy clone directory is a live clone holding
# backend-dev with no slug in its name — an earlier cut of this rule silenced it.
@case("with a taxonomy, ROLE and TO-ROLE are slugs; the address is not bound to the role")
def _():
    good = validate("[GZCOORD/1] INFO\nFROM: develop-qzapp/architect-cto-01\nROLE: architect-cto\nPROJECT: gzapp\n"
                    "MESSAGE-ID: architect-cto-01-0033\nTO: develop-qzapp/gzapp-devex-tooling\n", taxonomy=taxonomy)
    eq(good["errors"], [])
    eq(good["warnings"], [], "a well-formed message under the profile warns about nothing")
    for role in ("Application Architect", "Architect / CTO"):
        r = validate(f"[GZCOORD/1] INFO\nFROM: develop-qzapp/architect-cto-01\nROLE: {role}\nPROJECT: gzapp\n"
                     f"MESSAGE-ID: test-0001\nBROADCAST: true\n", taxonomy=taxonomy)
        ok(any(e.startswith(f'ROLE "{role}" is not a role slug') for e in r["errors"]), f"{role}: {r['errors']}")
    # A role change without a rename: valid, with a warning naming the disagreement.
    switched = validate("[GZCOORD/1] INFO\nFROM: develop-qzapp/architect-cto-01\nROLE: backend-dev\nPROJECT: gzapp\n"
                        "MESSAGE-ID: test-0001\nBROADCAST: true\n", taxonomy=taxonomy)
    eq(switched["errors"], [])
    ok(any(w.startswith("FROM names architect-cto but ROLE is backend-dev") for w in switched["warnings"]), switched["warnings"])
    # A clone named for no role is a session like any other, as sender and as addressee.
    eq(validate("[GZCOORD/1] INFO\nFROM: develop-qzapp/gzapp-claude2\nROLE: backend-dev\nPROJECT: gzapp\nMESSAGE-ID: test-0001\n"
                "BROADCAST: true\n", taxonomy=taxonomy)["errors"], [])
    eq(validate("[GZCOORD/1] INFO\nFROM: develop-qzapp/db-admin\nROLE: db-admin\nPROJECT: gzapp\nMESSAGE-ID: test-0001\n"
                "TO: develop-qzapp/gzapp-claude2\n", taxonomy=taxonomy)["errors"], [])
    for bad in ("Architect / CTO", "Application Architect"):
        r = validate(f"[GZCOORD/1] INFO\nFROM: develop-qzapp/db-admin\nROLE: db-admin\nPROJECT: gzapp\nMESSAGE-ID: test-0001\n"
                     f"TO-ROLE: {bad}\n", taxonomy=taxonomy)
        ok(any(e.startswith(f'TO-ROLE "{bad}" is not a role slug') for e in r["errors"]), r["errors"])
    eq(validate("[GZCOORD/1] INFO\nFROM: develop-qzapp/db-admin\nROLE: db-admin\nPROJECT: gzapp\nMESSAGE-ID: test-0001\n"
                "TO-ROLE: architect-cto\n", taxonomy=taxonomy)["errors"], [])
    # Without a taxonomy none of this applies: the wire grammar is generic.
    eq(validate("[GZCOORD/1] INFO\nFROM: develop-qzapp/gzapp-claude2\nROLE: Anything\nPROJECT: gzapp\nMESSAGE-ID: test-0001\n"
                "TO-ROLE: Whoever\n")["errors"], [])


@case("slugOf finds the longest whole-token slug an instance carries")
def _():
    eq(gzmsg.slug_of("agent-fabric-coordinator", taxonomy), "fabric-coordinator")
    eq(gzmsg.slug_of("legacy-old-role", taxonomy), None)   # renamed role: the old slug is not in the catalogue
    eq(gzmsg.slug_of("architect-cto-01", taxonomy), "architect-cto")
    eq(gzmsg.slug_of("db-admin", taxonomy), "db-admin")
    eq(gzmsg.slug_of("legacy-clone-2", taxonomy), None)
    eq(gzmsg.slug_of("web-developer", taxonomy), None)   # token match, not substring
    ok(gzmsg.find_taxonomy(os.path.dirname(os.path.abspath(__file__))).endswith("/identities/roles/catalog.json"))
    # The catalogue is the operator's, through roots: the fixture's own role,
    # which no live catalogue holds, is there; the engine root's would not be.
    eq(gzmsg.find_taxonomy(), os.path.join(OPERATOR, "identities", "roles", "catalog.json"))
    ok("fixture-only-role" in gzmsg.load_taxonomy(gzmsg.find_taxonomy()).roles)


# A fixture for the derivation cases: a throwaway agent-fabric STATE directory
# holding this agent's binding (or none, or a broken one), with
# AGENT_FABRIC_STATE_DIR pointing at it for the duration so whoami() is kept
# off the developer's real binding. The catalogue is a temporary copy. System
# temp, not the tests directory: a run interrupted between the mkdtemp and the
# cleanup would otherwise leave an untracked file in a tree whose workflow
# blesses `git add -A`.
LOGIN = __import__("pwd").getpwuid(os.geteuid()).pw_name


def with_fixture(state: str | None, fn: Callable[[str, str], Any]) -> Any:
    root = tempfile.mkdtemp(prefix="gzcoord-fixture-")
    os.makedirs(f"{root}/state/agents/{LOGIN}")
    shutil.copyfile(CATALOG, f"{root}/catalog.json")
    if state is not None:
        with open(f"{root}/state/agents/{LOGIN}/binding.json", "w", encoding="utf-8") as fh:
            fh.write(state)
    saved = os.environ.get("AGENT_FABRIC_STATE_DIR")
    os.environ["AGENT_FABRIC_STATE_DIR"] = f"{root}/state"
    try:
        return fn(root, f"{root}/catalog.json")
    finally:
        if saved is None:
            os.environ.pop("AGENT_FABRIC_STATE_DIR", None)
        else:
            os.environ["AGENT_FABRIC_STATE_DIR"] = saved
        shutil.rmtree(root, ignore_errors=True)


def bound(role: str) -> str:
    return json.dumps({"agent": LOGIN, "host": "h", "role": role, "updated_at": "x"})


@case("whoami: the agent is the effective login, never the directory")
def _():
    me = gzmsg.whoami()
    eq(me["agent"], LOGIN)
    base = os.path.basename(os.getcwd())
    ok(me["agent"] != ("x" if base == LOGIN else base))


# The derivation a session's identity runs on (inbox identity(), which the
# control plane's presence also reads), against a real binding file read
# through the real resolver: whoami() runs in-process under the fixture's
# AGENT_FABRIC_STATE_DIR. The login is overridden AFTER the binding is read,
# so a slug-carrying account name can be exercised from whatever login runs
# the suite.
def as_login(agent: str, me: dict | None = None) -> dict:
    return {**(gzmsg.whoami() if me is None else me), "agent": agent}


@case("identity derives the slug from the login when no role is recorded")
def _():
    def run(root: str, tax: str) -> None:
        me = inbox.identity(as_login("architect-cto-01"), gzmsg.load_taxonomy(tax))
        eq(me["slug"], "architect-cto")
        eq(me["address"], f"{gzmsg.whoami()['host']}/architect-cto-01")
        eq(inbox.identity(as_login("gzapp-claude2"), gzmsg.load_taxonomy(tax))["slug"], None,
           "a login naming no role derives none")
    with_fixture(None, run)


# The record wins over the login; a record the catalogue does not know is an
# error naming the file and the value; a malformed record warns, and the
# login's slug is what identity() is left with.
@case("the recorded role wins over the login, and a recorded role outside the catalogue is an error")
def _():
    def backend(root: str, tax: str) -> None:
        eq(inbox.identity(as_login("architect-cto-01"), gzmsg.load_taxonomy(tax))["slug"], "backend-dev")
        eq(inbox.identity(as_login("architect-cto-01"), gzmsg.load_taxonomy(tax)).get("roleError"), None)
        eq(gzmsg.recorded_role(gzmsg.load_taxonomy(tax))["role"], "backend-dev")
        ok(re.search(r"binding\.json$", gzmsg.recorded_role(gzmsg.load_taxonomy(tax))["file"]))
    with_fixture(bound("backend-dev"), backend)

    def unknown(root: str, tax: str) -> None:
        rec = gzmsg.recorded_role(gzmsg.load_taxonomy(tax))
        eq(rec["role"], None)
        ok(re.search(r'binding\.json records role "security-engineer", which is not in .*catalog\.json; the login\'s role '
                     r"is used instead", rec["error"]), rec["error"])
        # The fallback is said: the error travels with the identity every caller prints.
        ok(re.search(r'records role "security-engineer"',
                     inbox.identity(as_login("architect-cto-01"), gzmsg.load_taxonomy(tax))["roleError"]))
    with_fixture(bound("security-engineer"), unknown)
    for state in ("not json", json.dumps({"agent": LOGIN, "host": "h", "updated_at": "x"})):
        def broken(root: str, tax: str, state: str = state) -> None:
            cause = "could not be read" if state == "not json" else "records no role"
            eq(gzmsg.recorded_role(gzmsg.load_taxonomy(tax))["role"], None)
            ok(cause in gzmsg.recorded_role(gzmsg.load_taxonomy(tax))["warning"])
            eq(inbox.identity(as_login("architect-cto-01"), gzmsg.load_taxonomy(tax))["slug"], "architect-cto")
            eq(inbox.identity(as_login("gzapp-claude2"), gzmsg.load_taxonomy(tax))["slug"], None)
        with_fixture(state, broken)
    # With a binding, the address and the role both come from the agent (login
    # + host) and what it is bound to.

    def bound_web(root: str, tax: str) -> None:
        me = inbox.identity(gzmsg.whoami(), gzmsg.load_taxonomy(tax))
        eq(me["address"], f"{__import__('socket').gethostname().split('.')[0]}/{LOGIN}")
        eq(me["slug"], "web-dev")
        # The project is the WORKING COPY's when the suite runs inside a
        # registered one (agent-fabric is a managed project itself); the
        # binding's project applies only outside any.
        eq(me["project"], gzmsg.whoami().get("project") or "gzapp")
    with_fixture(json.dumps({"agent": LOGIN, "host": "h", "role": "web-dev", "project": "gzapp", "updated_at": "x"}),
                 bound_web)


# Reported from live use: a message with no MESSAGE-ID, and one whose id sat
# under a bogus `ID:` key, both validated clean -- so nothing caught the
# error. MESSAGE-ID is now REQUIRED (§7.1): absence is an error, and a
# misspelled key still warns, never rejects (§6 preserves unknown metadata --
# that is how the protocol extends).
@case("a missing MESSAGE-ID is an error; a key that misspells one is named")
def _():
    head = "[GZCOORD/1] INFO\nFROM: develop-qzapp/db-admin\nROLE: db-admin\nPROJECT: gzapp\nBROADCAST: true\n"
    none = validate(head)
    eq(none["ok"], False, "required since #641")
    ok("missing MESSAGE-ID" in none["errors"], none["errors"])
    bogus = validate(f"{head}ID: db-admin-0007\n")
    eq(bogus["ok"], False, "the bogus key does not satisfy the required field")
    ok("missing MESSAGE-ID" in bogus["errors"], bogus["errors"])
    ok("ID is not a known field — did you mean MESSAGE-ID?" in bogus["warnings"], bogus["warnings"])
    # Caught by the value's shape rather than the key's spelling.
    msgid = validate(f"{head}MSG-ID: db-admin-0007\n")
    ok(any(w.startswith("MSG-ID carries an id-shaped value") for w in msgid["warnings"]), msgid["warnings"])
    # A real id silences everything.
    eq(validate(f"{head}MESSAGE-ID: db-admin-0007\n")["warnings"], [])
    # The converse, seen live (seq 3445): the id field holds the shell
    # variable's NAME. Valid — §7.2 keeps the id opaque — but said.
    unexpanded = validate(f"{head}MESSAGE-ID: $ID\n")
    eq(unexpanded["ok"], True, "the grammar admits any identifier")
    ok("MESSAGE-ID is the literal $ID — the shell variable was not expanded; mint the id with gzmsg new-id and write"
       " its value" in unexpanded["warnings"], unexpanded["warnings"])
    odd = validate(f"{head}MESSAGE-ID: 01a09fc1-0000-7000-8000-000000000001\nIN-REPLY-TO: yesterday's message\n")
    ok(any(w.startswith("IN-REPLY-TO is yesterday's message, not an identifier this deployment mints") for w in odd["warnings"]),
       odd["warnings"])


@case("unknown fields that are real extensions stay silent — §6 preserves them")
def _():
    head = "[GZCOORD/1] INFO\nFROM: develop-qzapp/db-admin\nROLE: db-admin\nPROJECT: gzapp\nBROADCAST: true\nMESSAGE-ID: db-admin-0007\n"
    for key in ("X-PRIORITY", "X-TRACE", "SEVERITY", "DEADLINE", "ATTN", "THREAD", "LOCALE"):
        r = validate(f"{head}{key}: something\n")
        eq(r["warnings"], [], f"{key} must not warn")
        eq(r["message"]["metadata"][key], "something", f"{key} must be preserved")
    for key, want in (("ID", "MESSAGE-ID"), ("MESSAGEID", "MESSAGE-ID"), ("IN-REPLY", "IN-REPLY-TO"), ("SUBJET", "SUBJECT")):
        eq(gzmsg.nearest_known_key(key), want, key)
    for key in ("FROM", "TO-ROLE", "X-PRIORITY", "MSG-ID"):
        eq(gzmsg.nearest_known_key(key), None, key)


# MESSAGE-ID is minted UUIDv7 (RFC 9562): time-ordered, unique without
# coordination, no shared counter state. The counter this replaces existed for
# loss visibility on the lossy human relay; the durable carrier has no gap to
# detect, and the counter was the subsystem's largest defect source — five
# incidents. SPEC §7.2 says "opaque identifier": the format is a convention.
@case("mintId: RFC 9562 v7 shape, unique across calls, time-ordered")
def _():
    ids = [gzmsg.mint_id() for _ in range(5)]
    for i in ids:
        ok(re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}", i), i)
    eq(len(set(ids)), len(ids), "distinct")
    # The 48-bit ms timestamp is the ordering guarantee: non-decreasing across
    # mints. Within one millisecond the random part is random, so full
    # lexicographic order is NOT a v7 property and is not asserted.
    ts = [int(i[:13].replace("-", ""), 16) for i in ids]
    for a, b in zip(ts, ts[1:]):
        ok(b >= a, "timestamp regressed")


# A checkout that predated --peek once accepted `next-id --peek` (the retired
# counter command) in silence and took a number: a gap nothing could fill.
# Every flag a command takes is now declared, and an unrecognised one is
# refused BEFORE any side effect.
@case("parseArgs: unknown, valueless, repeated and surplus arguments are refused")
def _():
    spec = {"valued": ["instance", "seed"], "boolean": ["peek"], "positional": 0}
    eq(gzmsg.parse_args(["--instance", "x", "--peek"], spec), {"flags": {"instance": "x", "peek": True}, "positional": []})

    def refused(argv: list[str], s: dict, pattern: str, msg: str = "") -> None:
        try:
            gzmsg.parse_args(argv, s)
        except gzmsg.UsageError as e:
            ok(re.search(pattern, str(e)), f"{msg} {e}")
            return
        raise Failed(f"{argv} was accepted {msg}")
    refused(["--instance", "x", "--seeed", "9"], spec, r"unknown flag --seeed; this command takes --instance, --seed, --peek")
    refused(["--instance", "x", "--seed"], spec, r"--seed needs a value")
    refused(["--seed", "--peek"], spec, r"--seed needs a value", "a following flag is not a value")
    refused(["--instance", "a", "--instance", "b"], spec, r"--instance given twice")
    refused(["stray"], spec, r"unexpected argument: stray")
    one = {"valued": [], "boolean": [], "positional": 1}
    eq(gzmsg.parse_args(["file.txt"], one), {"flags": {}, "positional": ["file.txt"]})
    refused(["a", "b"], one, r"unexpected argument: b")
    refused(["--nope"], one, r"this command takes no flags")


# inbox applies SPEC §7.1 addressing and the §17 reading rule at delivery: the
# body of a message not addressed to this session is never printed. for_me()
# is that decision, kept pure so it can be pinned.
DB_ADMIN = {"address": "develop-qzapp/db-admin", "instance": "db-admin", "slug": "db-admin"}


def mine_of(me: dict) -> Callable[[dict], bool]:
    return lambda msg: inbox.for_me(msg, me)


@case("inbox forMe: exactly the messages SPEC §7.1 addresses to this session")
def _():
    me = DB_ADMIN

    def mk(typ: str, extra: str) -> dict:
        return parse(f"[GZCOORD/1] {typ}\nFROM: develop-qzapp/x\nROLE: architect-cto\nPROJECT: gzapp\nMESSAGE-ID: x-0001\n{extra}")
    eq(inbox.for_me(mk("INFO", "TO: develop-qzapp/db-admin\n"), me), True, "TO is my address")
    eq(inbox.for_me(mk("INFO", "TO: develop-qzapp/web-dev-01\n"), me), False, "TO is someone else")
    eq(inbox.for_me(mk("INFO", "TO-ROLE: db-admin\n"), me), True, "TO-ROLE is my slug")
    eq(inbox.for_me(mk("INFO", "TO-ROLE: backend-dev\n"), me), False, "TO-ROLE is another slug")
    eq(inbox.for_me(mk("INFO", "BROADCAST: true\n"), me), True, "broadcast reaches everyone")
    eq(inbox.for_me(mk("HELLO", ""), me), False, "a retired HELLO carries no addressing field: addressed to nobody")
    eq(inbox.for_me(mk("INFO", ""), me), False, "no addressing field at all: not for anyone")
    # A session with no resolvable role never matches a TO-ROLE.
    eq(inbox.for_me(mk("INFO", "TO-ROLE: db-admin\n"), {**me, "slug": None}), False)


@case("inbox identity: address is <host>/<login>; the slug comes from the binding, then from the login")
def _():
    # The resolver's answer is what identity() consumes; the working copy the
    # process runs in is not an input at all.
    host = "box"
    no_role = {"agent": "architect-cto-01", "host": host, "role": None, "binding": "/nonexistent/binding.json"}
    eq(inbox.identity(no_role, taxonomy),
       {"address": "box/architect-cto-01", "instance": "architect-cto-01", "slug": "architect-cto", "project": None})
    # a binding wins over the login's slug
    eq(inbox.identity({**no_role, "role": "backend-dev", "project": "gzapp"}, taxonomy)["slug"], "backend-dev")
    eq(inbox.identity({**no_role, "role": "backend-dev", "project": "gzapp"}, taxonomy)["project"], "gzapp")
    # a generic login carries no slug; the address still derives
    eq(inbox.identity({"agent": "user", "host": host, "binding": "/nonexistent"}, taxonomy),
       {"address": "box/user", "instance": "user", "slug": None, "project": None})
    # no catalogue at all: address still derives, slug does not
    eq(inbox.identity(no_role, None), {"address": "box/architect-cto-01", "instance": "architect-cto-01", "slug": None,
                                       "project": None})
    # and the real resolver names this process's login
    eq(inbox.identity(gzmsg.whoami(), None)["instance"], LOGIN)


def wrec(rid: str, typ: str, extra: str) -> dict:
    return {"id": rid, "sender": "develop-qzapp/x", "timestamp": "t",
            "content": f"[GZCOORD/1] {typ}\nFROM: develop-qzapp/x\nROLE: architect-cto\nPROJECT: gzapp\nMESSAGE-ID: x-{rid}\n{extra}"}


# The wait exits ONLY on a message addressed to this session: a slice holding
# only others' traffic is acknowledged and the arm CONTINUES — waking a session
# for its neighbours' messages is the noise the tool exists to remove.
# Injected fetch/ack pages make the loop deterministic.
@case("waitLoop exits only on an addressed message; others pass acknowledged")
def _():
    me = DB_ADMIN
    for_you = wrec("m3", "INFO", "BROADCAST: true\n")
    others = {"messages": [wrec("m1", "INFO", "TO: develop-qzapp/web-dev-01\n"),
                           wrec("m2", "OBSERVATION", "TO-ROLE: backend-dev\n")]}
    acked: list = []
    pages = [others, {"messages": [for_you]}]
    fetches = [0]

    def counting(_slice, _abort):
        fetches[0] += 1
        return pages.pop(0)
    r = inbox.wait_loop(counting, acked.append, 1800, mine_of(me))
    eq(r["delivered"], True, "exits on the addressed message, not the neighbours' one")
    eq(fetches[0], 2, "two slices: the passed one and the delivering one")
    eq(r["waited"], 110, "budget accounting: two 55 s slices")
    eq(next(c for c in r["classified"] if c["rec"]["id"] == "m3")["isMine"], True)
    eq(sorted(acked), ["m1", "m2", "m3"], "every shown message is acknowledged")
    # A page of nothing-but-others at budget end: quiet exit, counted.
    r2 = inbox.wait_loop(lambda *_: {"messages": [wrec("m9", "INFO", "TO: develop-qzapp/web-dev-01\n")]},
                         lambda _id: None, 4, mine_of(me))
    eq(r2["delivered"], False)
    eq(r2["othersPassed"], 1)
    eq(r2["waited"], 4, "spent the whole budget")
    # Drain mode returns the first page whatever it holds.
    r3 = inbox.wait_loop(lambda *_: {"messages": [wrec("m1", "INFO", "TO: develop-qzapp/web-dev-01\n")]},
                         lambda _id: None, 0, mine_of(me))
    eq(r3["delivered"], False, "drain does not exit early — it lists")
    eq(len(r3["classified"]), 1)
    # A retired HELLO or GOODBYE an old session still sends is acknowledged and
    # never delivered, not even listed: presence is the control plane's (ADR-030).
    acked4: list = []
    r4 = inbox.wait_loop(lambda *_: {"messages": [wrec("h", "HELLO", ""), wrec("g", "GOODBYE", "NOTES:\nsession ended\n")]},
                         acked4.append, 4, mine_of(me))
    eq([r4["delivered"], len(r4["classified"]), r4["othersPassed"]], [False, 0, 0], "a HELLO wakes nobody and is not listed")
    eq(acked4, ["h", "g"], "but the cursor moves past it")


def jrec(rid: str, seq: Any, extra: str) -> dict:
    return {"id": rid, "seq": seq, "content": f"[GZCOORD/1] INFO\nFROM: develop-qzapp/x\nROLE: r\nMESSAGE-ID: x-{rid}\n{extra}"}


# The episodic journal (ADR-041 rule 4): what is addressed to this session is
# journaled before the page is acknowledged; a journal that cannot take it
# holds the messages — unacknowledged, unshown — and says why.
@case("waitLoop journals the addressed records before acknowledging, and only those")
def _():
    order: list = []

    def journal(recs):
        order.append("journal " + ",".join(x["id"] for x in recs))
        return {"ok": True}
    r = inbox.wait_loop(lambda *_: {"messages": [jrec("other", 5, "TO: develop-qzapp/web-dev-01\n"),
                                                 jrec("mine", 4, "TO: develop-qzapp/db-admin\n")]},
                        lambda i: order.append(f"ack {i}"), 4, mine_of(DB_ADMIN), journal=journal)
    eq(r["delivered"], True)
    eq(order, ["journal mine", "ack other", "ack mine"], "only the addressed record is journaled, and before any ack")


@case("a journal that cannot keep them: the addressed records are held — not acknowledged, not shown — said once, retried after a pause")
def _():
    page = {"messages": [jrec("other", 1, "TO: develop-qzapp/web-dev-01\n"), jrec("mine", 2, "BROADCAST: true\n")]}
    acked, said, slept, tries = [], [], [], [0]

    def journal(_recs):
        tries[0] += 1
        return {"ok": False, "reason": "episodic: disk full"} if tries[0] < 3 else {"ok": True}
    r = inbox.wait_loop(lambda *_: page, acked.append, 3600, mine_of(DB_ADMIN), sleep=slept.append, journal=journal,
                        on_journal_fail=lambda reason, n: said.append([reason, n]))
    eq(r["delivered"], True, "shown once the journal could keep it")
    eq([i for i in acked if i == "mine"], ["mine"], "acknowledged once, only after it was kept")
    eq(said, [["episodic: disk full", 1], ["episodic: disk full", 1]],
       "each failure reported to the caller, which says it once per cause")
    eq(slept, [inbox.JOURNAL_RETRY_MS, inbox.JOURNAL_RETRY_MS], "a pause before the carrier is asked again")
    drained = inbox.wait_loop(lambda *_: page, lambda i: acked.append(f"drain {i}"), 0, mine_of(DB_ADMIN),
                              journal=lambda _r: {"ok": False, "reason": "episodic: x"})
    eq([drained["delivered"], drained["journalFailed"]], [False, "episodic: x"], "a drain returns at once, held")
    ok("drain mine" not in acked and "drain other" in acked, "others acknowledged; the addressed one not")


# The relay's acknowledgement is a cursor (claude_bridge advance_cursor: one
# last_seq per consumer, moved forward only), so this fake honours one: a page
# is every record above it, and an ack of seq N passes all below.
class CursorRelay:
    def __init__(self, records: list[dict]):
        self.records, self.cursor = records, 0

    def fetch_page(self, _slice, _abort) -> dict:
        return {"messages": [r for r in self.records if not (r.get("seq") is not None and r["seq"] <= self.cursor)]}

    def ack(self, rid: str) -> None:
        seq = next(r for r in self.records if r["id"] == rid).get("seq")
        self.cursor = max(self.cursor, self.cursor if seq is None else seq)


@case("a held record is not passed by acknowledging a later one: the relay's cursor stays before it (review of #78)")
def _():
    relay = CursorRelay([jrec("before", 1, "TO: develop-qzapp/web-dev-01\n"), jrec("mine", 2, "TO: develop-qzapp/db-admin\n"),
                         {"id": "retired", "seq": 3, "content": "[GZCOORD/1] HELLO\nFROM: develop-qzapp/x\n"},
                         jrec("after", 4, "TO: develop-qzapp/web-dev-01\n")])
    tries, kept = [0], []

    def journal(recs):
        tries[0] += 1
        if tries[0] == 1:
            eq(relay.cursor, 0)
            return {"ok": False, "reason": "episodic: x"}
        kept.extend(x["id"] for x in recs)
        return {"ok": True}
    r = inbox.wait_loop(relay.fetch_page, relay.ack, 3600, mine_of(DB_ADMIN), sleep=lambda _ms: None, journal=journal)
    eq(tries[0], 2, "the held record came back and was journaled")
    eq([r["delivered"], kept], [True, ["mine"]], "then shown")
    eq(relay.cursor, 4, "and the page acknowledged only after it was kept")
    relay2 = CursorRelay([jrec("mine", 1, "TO: develop-qzapp/db-admin\n"), jrec("after", 2, "TO: develop-qzapp/web-dev-01\n")])
    d = inbox.wait_loop(relay2.fetch_page, relay2.ack, 0, mine_of(DB_ADMIN),
                        journal=lambda _r: {"ok": False, "reason": "episodic: x"})
    eq([d["journalFailed"], relay2.cursor], ["episodic: x", 0], "a drain held first in the page acknowledges nothing after it")
    nos = {"id": "nos", "content": jrec("mine", 0, "TO: develop-qzapp/db-admin\n")["content"]}
    relay3 = CursorRelay([nos, {**jrec("after", 0, "TO: develop-qzapp/web-dev-01\n"), "seq": 5}])
    inbox.wait_loop(relay3.fetch_page, relay3.ack, 0, mine_of(DB_ADMIN), journal=lambda _r: {"ok": False, "reason": "episodic: x"})
    eq(relay3.cursor, 0, "a held record with no comparable seq: nothing acknowledged")


@case("a keyword among records acknowledged before a held one is the exit reason (review of #78)")
def _():
    relay = CursorRelay([
        {"id": "kw", "seq": 1, "content": "[GZCOORD/1] INFO\nFROM: develop-qzapp/x\nROLE: r\nTO: develop-qzapp/web-dev-01\n"
                                          "MESSAGE-ID: x-1\n\nINFO:\nthe geocode outage\n"},
        {"id": "mine", "seq": 2, "content": "[GZCOORD/1] INFO\nFROM: develop-qzapp/x\nROLE: r\nTO: develop-qzapp/db-admin\n"
                                            "MESSAGE-ID: x-2\n"}])

    def no_sleep(_ms):
        raise Failed("waited instead of exiting on the keyword")
    r = inbox.wait_loop(relay.fetch_page, relay.ack, 3600, mine_of(DB_ADMIN), ["geocode"], DB_ADMIN["address"],
                        sleep=no_sleep, journal=lambda _r: {"ok": False, "reason": "episodic: x"})
    eq([(r["keywordHit"] or {}).get("id"), r["journalFailed"], relay.cursor], ["kw", "episodic: x", 1],
       "the passed keyword record is named, the held one stays unacknowledged")


@case("--wait ends within its budget while the journal stays broken, the hold reported (review of #78)")
def _():
    relay = CursorRelay([{"id": "mine", "seq": 1, "content": "[GZCOORD/1] INFO\nFROM: develop-qzapp/x\nROLE: r\n"
                                                             "TO: develop-qzapp/db-admin\nMESSAGE-ID: x-1\n"}])
    tries, slept = [0], []

    def journal(_r):
        tries[0] += 1
        if tries[0] > 20:
            raise Failed("never ended")
        return {"ok": False, "reason": "episodic: x"}
    r = inbox.wait_loop(relay.fetch_page, relay.ack, 70, mine_of(DB_ADMIN), sleep=slept.append, journal=journal)
    eq([r["delivered"], r["journalFailed"], relay.cursor], [False, "episodic: x", 0], "held, said, unacknowledged")
    # A 55 s slice, one failed attempt, a pause of the 15 s left: then back,
    # with no fetch or journal attempt past the budget (re-review of #78).
    eq([r["waited"], tries[0], slept], [70, 1, [15000]], f"returned at the budget (waited {r['waited']}, {tries[0]} tries)")
    ok(all(ms <= inbox.JOURNAL_RETRY_MS for ms in slept))


# Ported with one departure, by design: the journal now runs in this process
# (ADR-040 §7), so there is no interpreter to name — the Node's `call.py ===
# '/py'` has nothing to assert. The arguments, the JSON lines, a failure read
# from the journal's own last line, and a journal that raises are kept.
@case("journalInbound sends the records as JSON lines and reads a failure from the journal's own last line")
def _():
    call: dict = {}

    def run(args, stdin):
        call.update(args=args, input=stdin)
        return {"status": 0, "stderr": ""}
    good = inbox.journal_inbound([{"content": "C", "seq": 7, "ts_full": "T"}], {"project": "p", "working_copy": "/w"}, run)
    eq(good["ok"], True)
    eq(call["args"], ["gzcoord-in", "--project", "p", "--working-copy", "/w"])
    eq(json.loads(call["input"].strip()), {"content": "C", "seq": 7, "ts": "T"})
    bad = inbox.journal_inbound([{"content": "C"}], {}, lambda *_: {"status": 1, "stderr": "noise\nepisodic: the store has no id\n"})
    eq(bad, {"ok": False, "reason": "episodic: the store has no id"})
    thrown = inbox.journal_inbound([{"content": "C"}], {}, lambda *_: inbox.run_episodic(["no-such-command"], ""))
    eq(thrown["ok"], False)
    ok("no-such-command" in thrown["reason"], thrown["reason"])

    def raising(_args, _stdin):
        raise OSError("ENOENT")
    real = inbox._episodic
    try:
        inbox._episodic = lambda: (_ for _ in ()).throw(OSError("ENOENT"))
        raised = inbox.journal_inbound([{"content": "C"}], {})
    finally:
        inbox._episodic = real
    eq(raised["ok"], False)
    ok("ENOENT" in raised["reason"], raised["reason"])


# --keyword: reasons to stop waiting on a message NOT addressed to this session.
# Guardrails exist because the abusable shape — a keyword that fires on every
# message — is the address-blind wake with extra steps.
@case("checkKeywords: minimum length, hard cap, dedup")
def _():
    eq(inbox.check_keywords(["663", "geocode"]), ["663", "geocode"])
    eq(inbox.check_keywords(["663", "663"]), ["663"], "deduplicated")

    def refused(kws: list, pattern: str) -> None:
        try:
            inbox.check_keywords(kws)
        except inbox.KeywordError as e:
            ok(re.search(pattern, str(e)), str(e))
            return
        raise Failed(f"{kws} accepted")
    for bad in ("ab", "6", "", "a"):
        refused([bad], r"shorter than 3 characters")
    refused(["aaa", "bbb", "ccc", "ddd", "eee", "fff", "ggg", "hhh", "iii"], r"at most 8 keywords")
    inbox.check_keywords(["aaa", "bbb", "ccc", "ddd", "eee", "fff", "ggg", "hhh"])   # exactly 8 is allowed


@case("keywordHit: whole-token, case-insensitive, full text; own echo never hits")
def _():
    text = ("[GZCOORD/1] INFO\nFROM: develop-qzapp/x\nPROJECT: gzapp\nMESSAGE-ID: x-0001\nBROADCAST: true\n"
            "SUBJECT: PR 663 discussion\n\nNOTES:\nsee REFERENCES - github-pr: #663 and #2663\n")
    own = "develop-qzapp/x"
    for kw, want in (("663", True), ("pr", True), ("2663", True), ("references", True), ("6", False), ("66", False),
                     ("GEQ", False), ("266", False), ("663-x", False)):
        eq(inbox.keyword_hit(text, [kw], own), want, kw)
    # multiple keywords: any hit wakes
    eq(inbox.keyword_hit(text, ["zzz", "geocode"], own), False)
    eq(inbox.keyword_hit(text, ["zzz", "pr-"], own), False, "whole-token, not substring")
    # the armed session's own messages never wake it — the echo exemption
    eq(inbox.keyword_hit(text, ["663"], None), True, "no ownAddress known: token match stands")
    eq(inbox.keyword_hit(text, ["develop-qzapp"], own), False, "own FROM token removed")
    eq(inbox.keyword_hit(text, ["pr"], None), True, "PR token matches without own address too")
    eq(inbox.keyword_hit("", ["anything"], None), False, "empty text never hits")


@case("waitLoop --keyword: a passing non-addressed message ends the arm with code-3 data")
def _():
    me = DB_ADMIN
    # a message addressed to SOMEONE ELSE whose body mentions the keyword
    pages = [
        {"messages": [wrec("m1", "INFO", "TO: develop-qzapp/web-dev-01\n"),
                      wrec("m2", "OBSERVATION", "TO-ROLE: backend-dev\nSUBJECT: unrelated schema review\n")]},
        {"messages": [wrec("m3", "REPLY", "TO: develop-qzapp/web-dev-01\n\nREFERENCES:\n- github-pr: #663\n")]},
    ]
    fetches, acked = [0], []

    def fetch(*_):
        fetches[0] += 1
        return pages.pop(0)
    r = inbox.wait_loop(fetch, acked.append, 1800, mine_of(me), inbox.check_keywords(["663"]), me["address"])
    eq(r["delivered"], False, "never addressed to me")
    eq(r["keywordHit"]["id"], "m3", "the keyword message is the exit reason")
    eq(fetches[0], 2, "the first slice (no hit) continued the arm")
    eq(sorted(acked), ["m1", "m2", "m3"], "passed messages are acknowledged too")
    eq(r["othersPassed"], 1, "one other in the delivering slice is passed")
    # the echo exemption inside wait_loop: a message FROM my address never ends the arm
    echo = wrec("echo", "INFO", "BROADCAST: true\n")
    echo["sender"] = me["address"]
    echo["content"] = echo["content"].replace("develop-qzapp/x", me["address"], 1)
    r2 = inbox.wait_loop(lambda *_: {"messages": [echo]}, lambda _i: None, 1800, mine_of(me),
                         inbox.check_keywords(["663"]), me["address"])
    eq(r2["keywordHit"], None, "own echo: no hit")
    eq(r2["delivered"], True, "a broadcast from self is still addressed to me (unchanged)")
    # budget expiry with a keyword set and no hit: quiet, counted
    r3 = inbox.wait_loop(lambda *_: {"messages": [wrec("m9", "INFO", "TO: develop-qzapp/web-dev-01\n")]}, lambda _i: None, 4,
                         mine_of(me), inbox.check_keywords(["663"]), me["address"])
    eq([r3["keywordHit"], r3["delivered"], r3["waited"]], [None, False, 4])


# The inbox reads its token and integration from the project's working copy. A
# session started in the workspace (projects/, no git toplevel) still has one:
# the binding names the checkout the role was activated in. Found live on
# architect-cto-01, 2026-09-14: the workspace launch drained nothing because
# the root fell back to the cwd.
@case("inboxRoot uses the binding working copy outside a checkout")
def _():
    tmp = os.path.realpath(tempfile.mkdtemp(prefix="inbox-root-"))
    SCRATCH.append(tmp)
    wc = os.path.join(tmp, "clone")
    os.mkdir(wc)
    binding = os.path.join(tmp, "binding.json")
    with open(binding, "w", encoding="utf-8") as fh:
        json.dump({"working_copy": wc}, fh)
    cwd = os.getcwd()
    try:
        os.chdir(tmp)   # tmp is outside any repository
        eq(inbox.inbox_root({"working_copy": None, "binding": binding}), wc)
        eq(inbox.inbox_root({"working_copy": wc, "binding": "/nonexistent"}), wc)
        shutil.rmtree(wc)
        eq(inbox.inbox_root({"working_copy": None, "binding": binding}), tmp, "a vanished working copy falls back to the cwd")
    finally:
        os.chdir(cwd)


# The relay's runtime (venv, token, database) is host state and lives in the
# workspace — the projects/ directory the fabric checkout sits in — never inside
# a working copy: a repository, gitignored or not, is the wrong owner for the
# channel's only record and a secret.
@case("relay runtime dir resolves against the workspace, not a working copy")
def _():
    eq(inbox.workspace(), os.path.dirname(os.environ.get("AGENT_FABRIC_ROOT") or HERE))
    eq(inbox.relay_runtime_dir({"relay_runtime_dir": ".gzcoord"}, "/ws"), "/ws/.gzcoord")
    eq(inbox.relay_runtime_dir({}, "/ws"), "/ws/.gzcoord")
    eq(inbox.relay_runtime_dir({"relay_runtime_dir": "/var/lib/gzcoord"}, "/ws"), "/var/lib/gzcoord")
    ok("/gzapp/" not in inbox.relay_runtime_dir({"relay_runtime_dir": ".gzcoord"}))


# A project with no integration, and no environment naming one, is NOT
# configured: the defaults were gzapp's until 2026-09-16, so any other
# project's working copy joined gzapp's channel with gzapp's token file.
@case("integrationConfig comes from the project or the environment, never a default of another project")
def _():
    none = inbox.integration_config("no-such-project", {})
    eq(none["configured"], False)
    ok(re.search(r"projects/no-such-project/integration/gzcoord/config.json", none["reason"]), none["reason"])
    ok(re.search(r"CLAUDE_BRIDGE_URL and GZCOORD_CHANNEL", none["reason"]), none["reason"])
    eq(none.get("channel"), None, "no channel is ever guessed")
    eq(inbox.integration_config(None, {})["configured"], False, "no project: not configured either")
    from_env = inbox.integration_config("no-such-project", {"CLAUDE_BRIDGE_URL": "http://127.0.0.1:1", "GZCOORD_CHANNEL": "x:y"})
    eq([from_env["configured"], from_env["source"], from_env["relay_url"], from_env["channel"], from_env.get("token_env_file")],
       [True, "environment", "http://127.0.0.1:1", "x:y", None])
    eq(inbox.integration_config("no-such-project", {"CLAUDE_BRIDGE_URL": "http://127.0.0.1:1"})["configured"], False,
       "half an environment override configures nothing")
    gz = inbox.integration_config("gzapp", {})
    eq(gz["configured"], True)
    ok(re.search(r"projects/gzapp/integration/gzcoord/config.json$", gz["source"]), gz["source"])
    eq(gz["channel"], "gzapp:gzcoord")
    eq(inbox.integration_config("gzapp", {"GZCOORD_CHANNEL": "over:ride"})["channel"], "over:ride",
       "the environment overrides a project file")


# The hold: while the session plans, the watch polls nothing.
@case("holdStatus: held iff some marker names a live harness of this login")
def _():
    d = tempfile.mkdtemp(prefix="hold-")
    SCRATCH.append(d)

    def f(pid: int) -> str:
        return os.path.join(d, f"{pid}.json")

    def put(pid: int, doc: Any) -> None:
        with open(f(pid), "w", encoding="utf-8") as fh:
            fh.write(doc if isinstance(doc, str) else json.dumps(doc))
    uid = os.getuid()
    eq(inbox.hold_status(os.path.join(d, "none"))["held"], False, "no directory")
    eq(inbox.hold_status(d)["held"], False, "empty directory")
    put(11, "not json")
    ok(re.search(r"11\.json: unreadable", inbox.hold_status(d)["reason"]))
    put(12, {"session_id": "s"})
    ok(re.search(r"12\.json: names no pid", inbox.hold_status(d)["reason"]))
    put(os.getpid(), {"session_id": "me", "pid": os.getpid(), "start": inbox.pid_start(os.getpid()), "since": "t"})
    h = inbox.hold_status(d)
    eq(h["held"], True, "our own pid, alive, same start time")
    eq([x["pid"] for x in h["sessions"]], [os.getpid()])
    # liveness is "answers a signal as this login": EPERM (another login's process) is not a hold
    eq(inbox.hold_status(d, is_alive=lambda _p: False)["held"], False, "a dead pid is not a hold")
    ok(re.search(r"is gone", inbox.hold_status(d, is_alive=lambda _p: False)["reason"]))
    # the production liveness: pid 1 answers EPERM to an unprivileged login and is nobody's harness
    if os.getuid() != 0:
        eq(inbox.pid_alive(1), False, "EPERM is not alive")
        put(1, {"session_id": "forged", "pid": 1, "start": ""})
        eq([x["pid"] for x in inbox.hold_status(d)["sessions"]], [os.getpid()],
           "a forged marker naming pid 1 does not hold, with the default is_alive")
        os.unlink(f(1))
    eq(inbox.pid_alive(4194304000), False, "ESRCH is not alive")
    eq(inbox.pid_alive(os.getpid()), True)
    # a reused pid: the start time differs
    eq(inbox.hold_status(d, start_of=lambda _p: "other")["held"], False, "a pid with another start time is not the harness")
    ok(re.search(r"reused", inbox.hold_status(d, start_of=lambda _p: "other")["reason"]))
    eq(inbox.hold_status(d, start_of=lambda _p: "")["held"], True, "an unknown start time (off Linux) falls back to the pid")
    # two sessions: held while either is live
    put(4194304000, {"session_id": "gone", "pid": 4194304000})
    eq(inbox.hold_status(d)["held"], True, "one live marker among dead ones holds")
    # ownership: the directory and each file must be this login's
    eq(inbox.hold_status(d, uid=uid + 1)["held"], False)
    ok(re.search(r"not this login's", inbox.hold_status(d, uid=uid + 1)["reason"]))
    link_dir = tempfile.mkdtemp(prefix="hold-link-")
    SCRATCH.append(link_dir)
    link = os.path.join(link_dir, "link")
    os.symlink(d, link)
    ok(re.search(r"not a directory", inbox.hold_status(link)["reason"]), "a symlinked directory is refused")
    # the path is under the login's home, overridable for tests
    saved = os.environ.pop("AGENT_FABRIC_HOLD_DIR", None)
    try:
        eq(inbox.hold_dir("/h"), "/h/.cache/agent-fabric/hold")
        os.environ["AGENT_FABRIC_HOLD_DIR"] = d
        eq(inbox.hold_dir(), d)
    finally:
        os.environ.pop("AGENT_FABRIC_HOLD_DIR", None)
        if saved is not None:
            os.environ["AGENT_FABRIC_HOLD_DIR"] = saved


@case("waitLoop: held polls nothing, a hold mid-slice cuts the slice, release delivers")
def _():
    me = DB_ADMIN

    def rec(rid: str) -> dict:
        return {"id": rid, "sender": "develop-qzapp/x", "timestamp": "t",
                "content": f"[GZCOORD/1] INFO\nFROM: develop-qzapp/x\nROLE: architect-cto\nPROJECT: gzapp\nMESSAGE-ID: x-{rid}\n"
                           f"BROADCAST: true\n"}
    # 1. Held from the start: the fetch is never called until the hold clears.
    state = {"held": True, "ticks": 0, "fetches": 0}
    transitions: list = []

    def held1() -> bool:
        state["ticks"] += 1
        if state["ticks"] > 5:
            state["held"] = False
        return state["held"]

    def fetch1(*_):
        state["fetches"] += 1
        return {"messages": [rec("m1")]}
    r = inbox.wait_loop(fetch1, lambda _i: None, 1800, mine_of(me), held=held1, on_hold=transitions.append,
                        sleep=lambda _ms: None)
    eq(r["delivered"], True, "delivered once released")
    eq(state["fetches"], 1, "no poll while held")
    ok(state["ticks"] > 5, "the hold was checked repeatedly")
    eq(transitions, [True, False], "told once on hold and once on release")
    # 2. A hold that begins during a slice cuts it; nothing is acknowledged;
    #    the message waits on the relay (the fake re-serves it) and lands after release.
    s2 = {"hold": False, "served": 0, "checks": 0}
    acked: list = []

    def fetch2(_slice, abort):
        s2["served"] += 1
        if s2["served"] == 1:
            # a long poll that would deliver m2 after a while; the hold arrives first
            threading.Timer(0.005, lambda: s2.__setitem__("hold", True)).start()
            abort.wait(30)
            raise RuntimeError("aborted")
        return {"messages": [rec("m2")]}

    def held2() -> bool:
        if s2["hold"]:
            s2["checks"] += 1
            if s2["checks"] > 3:
                s2["hold"] = False
        return s2["hold"]
    r2 = inbox.wait_loop(fetch2, acked.append, 1800, mine_of(me), held=held2, hold_poll_ms=1)
    eq(r2["delivered"], True)
    eq(s2["served"], 2, "the cut slice was retried after release")
    eq(acked, ["m2"], "nothing was acknowledged for the cut slice")
    # 3. A page that lands as the hold begins is dropped unread: nothing acked, re-shown after release.
    s3 = {"calls": 0, "after": 0}
    acked3: list = []

    def fetch3(*_):
        s3["calls"] += 1
        return {"messages": [rec("m3")]}

    def held3() -> bool:
        if s3["calls"] < 1:
            return False
        s3["after"] += 1
        return s3["after"] <= 4
    r3 = inbox.wait_loop(fetch3, acked3.append, 1800, mine_of(me), held=held3, hold_poll_ms=1, sleep=lambda _ms: None)
    eq(r3["delivered"], True)
    eq(acked3, ["m3"], "the page that landed with the hold was not acknowledged; the retry was")
    ok(s3["calls"] >= 2, "fetched again after release")
    # 4. A fetch that fails for its own reason still raises (the watch reports the relay).
    try:
        inbox.wait_loop(lambda *_: (_ for _ in ()).throw(RuntimeError("relay down")), lambda _i: None, 4, lambda _m: False)
    except RuntimeError as e:
        ok("relay down" in str(e))
    else:
        raise Failed("a failing fetch did not raise")


# The notification cap: what one --follow event carries.
@case("render under a cap: metadata whole, body cut at a line, the replay command last")
def _():
    me = {"address": "develop-qzapp/user", "slug": "fabric-coordinator"}
    cap = inbox.NOTIFICATION_CAP
    render, length = inbox.render, jsvalues.length

    def meta(rid: str, to: str = "develop-qzapp/user") -> str:
        return (f"[GZCOORD/1] OBSERVATION\nFROM: develop-qzapp/x\nROLE: architect-cto\nPROJECT: gzapp\nTO: {to}\n"
                f"REPLY-EXPECTED: no\nMESSAGE-ID: 01a0a9dd-e876-73e2-a329-c5b7cf28ba{rid}\nSUBJECT: subject {rid}")
    long_body = ("OBSERVATION:\n" + "\n".join(f"line {i} of a long body" for i in range(150))
                 + "\nREQUEST:\nthe ask at the very end\n")

    def rec(seq: int, content: str) -> dict:
        return {"id": f"r{seq}", "seq": seq, "sender": "develop-qzapp/x", "timestamp": "T", "content": content}

    def mine(seq: int, content: str) -> dict:
        return {"rec": rec(seq, content), "msg": parse(content), "isMine": True}

    def other(seq: int) -> dict:
        c = meta(str(seq).zfill(2), "develop-qzapp/z") + "\n"
        return {"rec": rec(seq, c), "msg": parse(c), "isMine": False}
    # a short delivery is untouched by the cap
    short = render({"classified": [mine(1, meta("01") + "\n\nNOTES:\nshort\n")]}, me, "c", None, cap=cap)
    eq(short, render({"classified": [mine(1, meta("01") + "\n\nNOTES:\nshort\n")]}, me, "c", None),
       "under the cap, the same text as without one")
    ok("--replay" not in short)
    # a long one is cut by us, not by the harness
    long = render({"classified": [mine(405, meta("05") + "\n\n" + long_body), other(406), other(407)]}, me, "c", None, cap=cap)
    ok(length(long) <= cap, f"over the cap: {length(long)}")
    ok("SUBJECT: subject 05\n\nOBSERVATION:\nline 0 of a long body\n" in long, "metadata whole, body from its first line")
    ok("the ask at the very end" not in long, "the tail was cut")
    ok(re.search(r"\nline \d+ of a long body\n\n\[gzcoord: body cut here to fit one notification — the whole message: "
                 r"gzcoord-inbox --replay 405\]\n```", long), "cut at a line boundary; the replay command names the seq")
    ok(re.search(r"Not addressed to you — listed, bodies not read \(SPEC §17\):\n  01a0a9dd-e876-73e2-a329-c5b7cf28ba406  "
                 r"OBSERVATION  TO develop-qzapp/z  subject 406\n  01a0a9dd-e876-73e2-a329-c5b7cf28ba407", long),
       "others keep their metadata lines while they fit")
    # others fall back to a count naming their seqs only when even their lines do not fit
    crowded = render({"classified": [mine(405, meta("05") + "\n\n" + long_body), *[other(600 + i) for i in range(40)]]},
                     me, "c", None, cap=cap)
    ok(length(crowded) <= cap)
    ok(re.search(r"40 not addressed to you \(seq 600–639\), not listed here: over the notification cap\.", crowded), crowded[-300:])
    ok("output file" not in crowded, "nothing is claimed to be somewhere it is not")
    # F1: a wide line in an arrived message is not a warning, and cannot displace the metadata
    wide_body = "NOTES:\n" + "\n".join(f"line {i} " + "w" * 90 for i in range(30)) + "\n"
    wide = render({"classified": [mine(430, meta("30") + "\n\n" + wide_body)]}, me, "c", None, cap=cap)
    ok("columns wide" not in wide, "no width warning on the receive side")
    ok("SUBJECT: subject 30\n\nNOTES:\nline 0 " in wide, "metadata whole, body from its first line")
    # validator lines are capped only under a cap: the drain shows them all
    invalid = "[GZCOORD/1] INFO\nFROM: nobody\n\nNOTES:\nstray one\nstray two\nstray three\nstray four\nstray five\n"
    inv = {"rec": rec(460, invalid), "msg": {"type": "INFO", "metadata": {"BROADCAST": "true"}}, "isMine": True}
    drained = render({"classified": [inv]}, me, "c", None)
    watched = render({"classified": [inv]}, me, "c", None, cap=cap)
    ok("more validator lines" not in drained and drained.count("INVALID:") > 4, "the drain shows every validator line")
    ok("more validator lines" in watched and watched.count("INVALID:") == 4, "the watch caps them")
    # F2: no blank line after the metadata (SPEC §6 MAY), and CRLF — still split at the section marker
    eq(inbox.split_message("A: 1\nB: 2\nNOTES:\nx\n\ny\n"), {"meta": "A: 1\nB: 2", "body": "NOTES:\nx\n\ny"})
    eq(inbox.split_message("A: 1\r\nB: 2\r\n\r\nNOTES:\r\nx\r\n"), {"meta": "A: 1\nB: 2", "body": "NOTES:\nx"})
    eq(inbox.split_message("A: 1\nB: 2\n"), {"meta": "A: 1\nB: 2", "body": ""})
    no_blank = render({"classified": [mine(440, meta("40") + "\n" + long_body)]}, me, "c", None, cap=cap)
    ok(length(no_blank) <= cap)
    ok("SUBJECT: subject 40\n\nOBSERVATION:\nline 0 of a long body" in no_blank and "--replay 440]" in no_blank,
       "metadata and body head present without a blank line in the source")
    # F5: the cut is always at a line boundary — a first line longer than the budget keeps nothing of the body
    one = render({"classified": [mine(450, meta("50") + "\n\nNOTES:\n" + "z" * 5000 + "\n")]}, me, "c", None, cap=cap)
    ok(length(one) <= cap)
    ok("zzzzzzzz" not in one, "no mid-line slice")
    ok("SUBJECT: subject 50\n\nNOTES:\n\n[gzcoord: body cut here" in one, "metadata, the section marker that fits, then the notice")
    eq(inbox.REPLAY_CMD, "gzcoord-inbox --replay")
    # two long messages share the budget; each carries its own replay line
    two = render({"classified": [mine(410, meta("10") + "\n\n" + long_body), mine(411, meta("11") + "\n\n" + long_body)]},
                 me, "c", None, cap=cap)
    ok(length(two) <= cap)
    ok("--replay 410]" in two and "--replay 411]" in two)
    ok("SUBJECT: subject 10\n\nOBSERVATION:\nline 0" in two and "SUBJECT: subject 11\n\nOBSERVATION:\nline 0" in two)
    # a short and a long one: the short one is whole, the long one gets the rest
    mixed = render({"classified": [mine(420, meta("20") + "\n\nNOTES:\nwhole\n"), mine(421, meta("21") + "\n\n" + long_body)]},
                   me, "c", None, cap=cap)
    ok(length(mixed) <= cap)
    ok("NOTES:\nwhole\n```" in mixed and "--replay 420]" not in mixed, "the short message is whole and carries no cut notice")
    ok("--replay 421]" in mixed)
    # more messages than the metadata alone allows: one line each
    many = render({"classified": [mine(500 + i, meta(str(i).zfill(2)) + "\n\n" + long_body) for i in range(20)]},
                  me, "c", None, cap=cap)
    ok(length(many) <= cap)
    ok(re.search(r"\(over the notification cap: each message by its seq", many))
    ok("  seq 500  01a0a9dd-e876-73e2-a329-c5b7cf28ba00  OBSERVATION  TO develop-qzapp/user  subject 00" in many)
    ok("  seq 519  " in many, "twenty one-liners fit")
    ok("… and" not in many, "nothing was dropped from the listing")
    # F4: when even the one-liners do not fit, the tail says how many and which seqs
    fifty = render({"classified": [mine(700 + i, meta(str(i).zfill(2)) + "\n\n" + long_body) for i in range(50)]},
                   me, "c", None, cap=cap)
    ok(length(fifty) <= cap)
    ok(re.search(r"\n  … and \d+ more for you \(seq 7\d\d–749\), each read with --replay <seq>$", fifty),
       f"a listing that dropped lines says so: {fifty[-200:]}")


# agent-fabric ADR-037 rule 5: the automatic request intake is built and off.
# Nothing runs without AGENT_FABRIC_JOBS_AUTO_INTAKE=1; with it, only a REPLY
# naming the message it answers reaches fabric-jobs.
@case("send: the automatic job intake is off unless switched on, and then takes only a REPLY")
def _():
    calls, opts = [], []

    class Done:
        returncode, stdout, stderr = 0, "added j1\n", ""

    def run(argv, **kw):
        calls.append(argv)
        opts.append(kw)
        return Done()
    reply = {"type": "REPLY", "metadata": {"IN-REPLY-TO": "01a09fc1-0000-7000-8000-00000000000a"}}
    eq(send.auto_intake(reply, {}, run), None, "off by default")
    eq(send.auto_intake(reply, {"AGENT_FABRIC_JOBS_AUTO_INTAKE": "0"}, run), None, "off unless exactly 1")
    eq(send.auto_intake({"type": "REQUEST", "metadata": {}}, {"AGENT_FABRIC_JOBS_AUTO_INTAKE": "1"}, run), None)
    eq(send.auto_intake({"type": "REPLY", "metadata": {}}, {"AGENT_FABRIC_JOBS_AUTO_INTAKE": "1"}, run), None)
    eq(len(calls), 0)
    eq(send.auto_intake(reply, {"AGENT_FABRIC_JOBS_AUTO_INTAKE": "1"}, run)["stdout"], "added j1\n")
    eq(len(calls), 1)
    eq(calls[0][:1] + calls[0][2:], ["python3", "add", "--request", "01a09fc1-0000-7000-8000-00000000000a", "--auto"])
    ok(re.search(r"tools/fabric/jobs\.py$", calls[0][1]), calls[0][1])
    ok(0 < opts[0]["timeout"] <= 30, "bounded: a hung relay must not hold a send that succeeded")
    # The launcher never sets the switch. Since Wave 4 (ADR-040) the launcher is
    # a module behind a shim: both are read, and a source that moves fails the
    # read rather than passing it by finding nothing.
    parts = sorted(glob.glob(os.path.join(HERE, "tools", "fabric", "launcher", "*.py")))
    ok(parts, "the launcher's parts are where this test reads them (tools/fabric/launcher/)")
    for rel in ("runtime/openrouter/launch", "tools/fabric/launch.py", *(os.path.relpath(p, HERE) for p in parts)):
        with open(os.path.join(HERE, rel), encoding="utf-8") as fh:
            ok("AGENT_FABRIC_JOBS_AUTO_INTAKE" not in fh.read(), rel)


@case("a trimmed sent ledger starts with one watermark, the oldest kept entry's time (review of #84)")
def _():
    d = tempfile.mkdtemp(prefix="ledger-trim-")
    SCRATCH.append(d)
    ledger = os.path.join(d, "gzcoord-sent.jsonl")
    import datetime

    def at(i: int) -> str:
        t = datetime.datetime(2026, 10, 1, tzinfo=datetime.timezone.utc) + datetime.timedelta(seconds=i)
        return t.isoformat(timespec="milliseconds").replace("+00:00", "Z")
    # The ledger is written under the agent's lock: its state directory is
    # this case's, never the runner's.
    saved = os.environ.get("AGENT_FABRIC_STATE_DIR")
    os.environ["AGENT_FABRIC_STATE_DIR"] = d
    try:
        for i in range(9):
            send.record_sent(ledger, {"id": f"m-{i}", "sha256": f"h{i}", "seq": i, "at": at(i)}, 3)
        with open(ledger, encoding="utf-8") as fh:
            ok("trimmed_before" not in fh.read(), "under the bound: no trim, no mark")
        # Past keep + 1000 twice: the second trim must carry the first mark away.
        for i in range(9, 2020):
            send.record_sent(ledger, {"id": f"m-{i}", "sha256": f"h{i}", "seq": i, "at": at(i)}, 3)
    finally:
        if saved is None:
            os.environ.pop("AGENT_FABRIC_STATE_DIR", None)
        else:
            os.environ["AGENT_FABRIC_STATE_DIR"] = saved
    with open(ledger, encoding="utf-8") as fh:
        lines = [x for x in fh.read().split("\n") if x]
    marks = [x for x in lines if "trimmed_before" in x]
    eq(len(marks), 1, "one watermark, however many trims")
    eq(lines[0], marks[0], "and it is the first line")
    first_kept = json.loads(lines[1])
    eq(json.loads(marks[0])["trimmed_before"], first_kept["at"], "it names the oldest kept entry's time")
    eq(send.spent_elsewhere(ledger, first_kept["id"], "other"), first_kept, "entries are still read past it")


# ── cases that run a command beside a function: ported whole ─────────

BIN = os.path.join(os.path.dirname(os.path.dirname(GZCOORD)), "bin")
INBOX_CMD = os.path.join(BIN, "gzcoord-inbox")
SEND_CMD = os.path.join(BIN, "gzcoord-send")
AGENT_ID = "01a0f782-7e06-7dee-811f-0a860ed93bf3"


def scratch(prefix: str) -> str:
    d = tempfile.mkdtemp(prefix=prefix)
    SCRATCH.append(d)
    return d


def id_store() -> str:
    """A scratch secrets store holding an agent id: the journal has an owner."""
    d = scratch("send-store-")
    with open(os.path.join(d, ".agent-id"), "w", encoding="utf-8") as fh:
        fh.write(AGENT_ID + "\n")
    return d


class Stub:
    """A relay stub on a thread: `answer(handler, method, path, body)` writes
    the response. A handler that returns None stalls until the stub stops,
    as a long poll that never answers."""

    def __init__(self, answer: Callable):
        import http.server
        stub = self
        self.stop_event = threading.Event()

        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *_a):
                pass

            def _do(self, method: str) -> None:
                n = int(self.headers.get("content-length") or 0)
                body = self.rfile.read(n).decode("utf-8") if n else ""
                out = answer(self, method, self.path, body)
                if out is None:
                    stub.stop_event.wait(30)
                    return
                status, payload = out
                data = payload.encode("utf-8")
                self.send_response(status)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(data)))
                self.send_header("connection", "close")
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):  # noqa: N802 — the stdlib's name
                self._do("GET")

            def do_POST(self):  # noqa: N802
                self._do("POST")
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.server.daemon_threads = True
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.stop_event.set()
        self.server.shutdown()
        self.server.server_close()


def cmd_env(**extra: str) -> dict:
    # The workspace a command sees is AGENT_FABRIC_ROOT's parent, and its
    # .gzcoord is where a hosting account keeps the relay: left at the
    # checkout's, a case on such an account asked the real relay's status
    # and, were it down, would start it (review of #93, round 3). A scratch
    # workspace whose agent-fabric is the checkout, by a link.
    ws = scratch("ws-")
    os.symlink(HERE, os.path.join(ws, "agent-fabric"))
    return {**os.environ, "HOME": scratch("home-"), "AGENT_FABRIC_SECRET_STORE": id_store(),
            "AGENT_FABRIC_ROOT": os.path.join(ws, "agent-fabric"), **extra}


@case("normalize CLI prints the normalised message for validate to read")
def _():
    f = scratch_file("  [GZCOORD/1] INFO\n  FROM: develop-gzapp/gzapp\n  ROLE: Tester\n  PROJECT: gzapp\nMESSAGE-ID: test-0001\n"
                     "  BROADCAST: true\n")
    run = gzmsg_cli("normalize", f)
    eq(run.returncode, 0)
    eq(run.stdout, "[GZCOORD/1] INFO\nFROM: develop-gzapp/gzapp\nROLE: Tester\nPROJECT: gzapp\nMESSAGE-ID: test-0001\nBROADCAST: true\n")
    eq(validate(run.stdout)["errors"], [])


# SPEC §7.2: a retransmission keeps its MESSAGE-ID. The watch shows the copy —
# the first may never have been read — marked with the earlier seq.
@case("a retransmitted delivery is marked with the seq of the earlier copy; a first copy is not")
def _():
    def text(mid: str, frm: str = "x/y") -> str:
        return (f"[GZCOORD/1] INFO\nFROM: {frm}\nROLE: backend-dev\nPROJECT: fixture\nBROADCAST: true\nMESSAGE-ID: {mid}\n"
                f"SUBJECT: s\n\nNOTES:\nn\n")

    def rec(seq: int, mid: str, frm: str | None = None) -> dict:
        return {"seq": seq, "id": f"r{seq}", "sender": frm or "x/y", "timestamp": f"T{seq}", "content": text(mid, frm or "x/y")}
    a, b = "01a09fc1-0000-7000-8000-0000000000a1", "01a09fc1-0000-7000-8000-0000000000b1"
    recent = {"messages": [rec(4, a), rec(6, b, "other/z"), rec(9, a), rec(10, b)]}

    def classify(r: dict) -> dict:
        return {"rec": r, "msg": parse(r["content"]), "isMine": True}
    got = [classify(rec(9, a)), classify(rec(10, b))]
    inbox.mark_retransmissions(got, lambda _d: recent)
    eq(got[0].get("retransmitOf"), 4)
    eq(got[1].get("retransmitOf"), None, "the same id from another FROM is another message")
    out = inbox.render({"classified": got}, {"address": "h/me"}, "fixture:chan", None)
    ok(re.search(r"retransmission: the same FROM and MESSAGE-ID arrived before as relay seq 4", out), out)
    eq(len(re.findall(r"retransmission:", out)), 1)
    failed = [classify(rec(9, a))]
    inbox.mark_retransmissions(failed, lambda _d: (_ for _ in ()).throw(RuntimeError("relay down")))
    eq(failed[0].get("retransmitOf"), None)
    inbox.mark_retransmissions(failed, lambda _d: {})
    eq(failed[0].get("retransmitOf"), None, "an answer that is not a list marks nothing")
    # A relay that never answers: the lookup gives up at its bound, marking nothing.
    import time
    t0 = time.monotonic()
    inbox.mark_retransmissions(failed, lambda done: done.wait(60), 200)
    ok(time.monotonic() - t0 < 1.5, f"the lookup waited {time.monotonic() - t0:.2f} s")
    eq(failed[0].get("retransmitOf"), None)
    # A lookup that settles at once leaves nothing behind: a process that ran it
    # with a ten-second bound exits at once, not when the bound expires.
    t1 = time.monotonic()
    child = subprocess.run([sys.executable, "-c",
                            "import sys; sys.path.insert(0, sys.argv[1]); from gzcoord import inbox\n"
                            "inbox.mark_retransmissions([], lambda d: {'messages': []}, 10000)\n"
                            "inbox.mark_retransmissions([{'isMine': True, 'rec': {'seq': 2}, 'msg': {'metadata': "
                            "{'FROM': 'a', 'MESSAGE-ID': 'x'}}}], lambda d: {'messages': []}, 10000)",
                            os.path.join(HERE, "tools", "fabric")], capture_output=True, text=True, timeout=9)
    eq(child.returncode, 0, child.stderr)
    ok(time.monotonic() - t1 < 5, f"the process lingered {time.monotonic() - t1:.2f} s after the lookup settled")


def follow_until(env: dict, done: Callable[[str], bool], seconds: float = 8.0) -> str:
    """inbox --follow, read until `done(out)` or the time is up, then killed
    as the harness kills it (SIGKILL, the shim first)."""
    import time
    child = subprocess.Popen([INBOX_CMD, "--follow"], env=env, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                             stdin=subprocess.DEVNULL)
    os.set_blocking(child.stdout.fileno(), False)
    out, deadline = b"", time.monotonic() + seconds
    try:
        while time.monotonic() < deadline:
            chunk = child.stdout.read() or b""
            out += chunk
            if done(out.decode("utf-8", "replace")):
                time.sleep(0.2)
                out += child.stdout.read() or b""
                break
            time.sleep(0.05)
    finally:
        child.kill()
        child.wait(10)
    return out.decode("utf-8", "replace")


@case("inbox --follow bounds a long delivery to one notification and names the replay")
def _():
    body = "\n".join(f"line {i} LONG-BODY" for i in range(200)) + "\nTHE-END\n"
    mine = ("[GZCOORD/1] INFO\nFROM: x/y\nROLE: backend-dev\nPROJECT: fixture\nBROADCAST: true\n"
            f"MESSAGE-ID: 01a09fc1-0000-7000-8000-00000000002f\nSUBJECT: long\n\nNOTES:\n{body}")
    served = [False]

    def answer(_h, _method, path, _body):
        if path == "/status":
            return 200, "{}"
        if path.startswith("/api/wait"):
            if not served[0]:
                served[0] = True
                return 200, json.dumps({"messages": [{"seq": 77, "id": "r77", "ts": "T", "sender": "x/y", "content": mine}],
                                        "next_cursor": "c"})
            return None
        return 200, "{}"
    stub = Stub(answer)
    try:
        out = follow_until(cmd_env(CLAUDE_BRIDGE_URL=stub.url, CLAUDE_BRIDGE_AUTH_TOKEN="tok", GZCOORD_CHANNEL="fixture:chan"),
                           lambda o: "--replay 77]" in o)
    finally:
        stub.close()
    ok(jsvalues.length(out) <= inbox.NOTIFICATION_CAP + 1, f"the event is bounded: {jsvalues.length(out)}")
    ok("SUBJECT: long\n\nNOTES:\nline 0 LONG-BODY" in out, f"metadata and the body head are there: {out[:300]}")
    ok("THE-END" not in out, "the tail is not")
    ok("[gzcoord: body cut here to fit one notification — the whole message: gzcoord-inbox --replay 77]" in out)


@case("inbox --follow polls nothing while the hold marker names a live pid")
def _():
    import time
    mine = ("[GZCOORD/1] INFO\nFROM: x/y\nROLE: backend-dev\nPROJECT: fixture\nBROADCAST: true\n"
            "MESSAGE-ID: 01a09fc1-0000-7000-8000-00000000001f\nSUBJECT: live\n\nNOTES:\nHELD-BODY\n")
    waits = [0]

    def answer(_h, _method, path, _body):
        if path == "/status":
            return 200, "{}"
        if path.startswith("/api/wait"):
            waits[0] += 1
            return 200, json.dumps({"messages": [{"seq": 5, "id": "r5", "ts": "T", "sender": "x/y", "content": mine}],
                                    "next_cursor": "c"})
        return 200, "{}"
    stub = Stub(answer)
    hold = scratch("hold-")
    os.chmod(hold, 0o700)
    marker = os.path.join(hold, f"{os.getpid()}.json")

    def put_marker() -> None:
        with open(marker, "w", encoding="utf-8") as fh:
            json.dump({"session_id": "plan", "pid": os.getpid(), "start": inbox.pid_start(os.getpid()), "since": "T"}, fh)
    put_marker()
    env = cmd_env(AGENT_FABRIC_HOLD_DIR=hold, CLAUDE_BRIDGE_URL=stub.url, CLAUDE_BRIDGE_AUTH_TOKEN="tok",
                  GZCOORD_CHANNEL="fixture:chan")
    child = subprocess.Popen([INBOX_CMD, "--follow"], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             stdin=subprocess.DEVNULL)
    for fd in (child.stdout, child.stderr):
        os.set_blocking(fd.fileno(), False)
    out = err = b""
    try:
        time.sleep(2.5)
        out += child.stdout.read() or b""
        err += child.stderr.read() or b""
        waits_while_held, out_while_held = waits[0], out
        os.unlink(marker)   # the plan is approved
        deadline = time.monotonic() + 8
        while b"HELD-BODY" not in out and time.monotonic() < deadline:
            time.sleep(0.05)
            out += child.stdout.read() or b""
        err += child.stderr.read() or b""
    finally:
        child.kill()
        child.wait(10)
        stub.close()
    eq(waits_while_held, 0, "the relay was not polled while held")
    eq(out_while_held, b"", "nothing on stdout while held")
    ok(re.search(rb"inbox held", err), err)
    ok(b"HELD-BODY" in out, "delivered once the marker was gone")
    # --held answers from the same marker
    put_marker()
    h = subprocess.run([INBOX_CMD, "--held"], env=env, capture_output=True, text=True, timeout=60)
    eq(h.returncode, 0)
    ok(re.match(r"held: .* session plan \(pid \d+\)", h.stdout), h.stdout)
    os.unlink(marker)
    with open(os.path.join(hold, "4194304000.json"), "w", encoding="utf-8") as fh:
        json.dump({"session_id": "plan", "pid": 4194304000, "since": "T"}, fh)
    n = subprocess.run([INBOX_CMD, "--held"], env=env, capture_output=True, text=True, timeout=60)
    eq(n.returncode, 1)
    ok(re.match(r"not held: 4194304000\.json: session 4194304000 is gone", n.stdout), n.stdout)


def valid_message() -> str:
    me = gzmsg.whoami()
    return (f"[GZCOORD/1] INFO\nFROM: {me['host']}/{me['agent']}\nROLE: backend-dev\nPROJECT: fixture\nBROADCAST: true\n"
            f"MESSAGE-ID: 01a09fc1-0000-7000-8000-000000000001\nSUBJECT: fixture\n\nNOTES:\nhello\n")


# The control channel: machine records, never a session's.
@case("a :control channel is refused by the drain, the watch and send, before any request reaches the relay")
def _():
    for bad in ("fabric:control",):
        try:
            inbox.assert_not_control_channel(bad)
            raise Failed(f"{bad} passed")
        except inbox.ControlChannel as e:
            ok(re.search(r"control channel", str(e)), str(e))
    inbox.assert_not_control_channel("gzapp:gzcoord")
    inbox.assert_not_control_channel("x:controls")
    hits: list = []

    def answer(_h, _method, path, _body):
        hits.append(path)
        return 200, '{"messages":[]}'
    stub = Stub(answer)
    try:
        env = cmd_env(CLAUDE_BRIDGE_URL=stub.url, CLAUDE_BRIDGE_AUTH_TOKEN="tok", GZCOORD_CHANNEL="fabric:control")
        for args in ([], ["--follow"], ["--wait", "1"]):
            r = subprocess.run([INBOX_CMD, *args], env=env, capture_output=True, text=True, timeout=10)
            eq(r.returncode, 2, f"inbox {' '.join(args)}: exit {r.returncode}\n{r.stderr}")
            ok(re.search(r"control channel", r.stderr), r.stderr)
        f = os.path.join(env["HOME"], "m.txt")
        with open(f, "w", encoding="utf-8") as fh:
            fh.write(valid_message())
        sres = subprocess.run([SEND_CMD, f], env=env, capture_output=True, text=True, timeout=10)
    finally:
        stub.close()
    eq(sres.returncode, 2, f"send: exit {sres.returncode}\n{sres.stderr}")
    ok(re.search(r"is a control channel[\s\S]*not sent", sres.stderr), sres.stderr)
    eq([u for u in hits if u.startswith("/api/")], [], f"a request reached the relay: {hits}")


# The hosting account's relay is a user unit once bootstrap installed it:
# ensure_relay starts the unit by name and never spawns beside it; a workspace
# without the venv is a client and hosts nothing; without a unit file (or a
# user manager) the detached spawn stays the fallback.
@case("ensureRelay: a client hosts nothing; with the unit installed the relay is started by name, not spawned")
def _():
    import time
    runtime = scratch("gzc-")
    eq(inbox.ensure_relay(runtime, "http://127.0.0.1:1"), {"hosted": False, "started": False}, "no venv: a client")
    os.makedirs(os.path.join(runtime, "venv", "bin"))
    bridge = os.path.join(runtime, "venv", "bin", "claude-bridge")
    with open(bridge, "w") as fh:   # a "claude-bridge" that would betray itself if spawned
        fh.write('#!/usr/bin/env bash\necho SPAWNED >> "$(dirname "$0")/../../spawned"\nsleep 30\n')
    os.chmod(bridge, 0o755)
    with open(os.path.join(runtime, "bridge-token"), "w") as fh:
        fh.write("tok\n")
    home, binp, xdg = scratch("home-"), scratch("bin-"), scratch("xdg-")
    open(os.path.join(xdg, "bus"), "w").close()
    unit = os.path.join(home, ".config", "systemd", "user", "gzcoord-relay.service")
    os.makedirs(os.path.dirname(unit))
    with open(unit, "w") as fh:
        fh.write("[Service]\n")
    log, spawned = os.path.join(runtime, "systemctl.log"), os.path.join(runtime, "spawned")

    def tool(name: str, body: str) -> None:
        with open(os.path.join(binp, name), "w") as fh:
            fh.write("#!/usr/bin/env bash\n" + body)
        os.chmod(os.path.join(binp, name), 0o755)
    # fake systemctl records the call; fake curl answers the probe only after systemctl ran
    tool("systemctl", f'echo "$*" >> {json.dumps(log)}\n')
    tool("curl", f"[[ -f {json.dumps(log)} ]]\n")
    keys = ("HOME", "PATH", "XDG_RUNTIME_DIR", "GZCOORD_TEST_BUS_ANY")
    saved = {k: os.environ.get(k) for k in keys}
    # the fixture's bus is a plain file, not a socket: the test switch admits it
    os.environ.update(HOME=home, PATH=f"{binp}:{os.environ['PATH']}", XDG_RUNTIME_DIR=xdg, GZCOORD_TEST_BUS_ANY="1")
    pids: list[int] = []
    try:
        r = inbox.ensure_relay(runtime, "http://127.0.0.1:1")
        eq(r, {"hosted": True, "started": True, "unit": "gzcoord-relay"}, json.dumps(r))
        with open(log) as fh:
            eq(fh.read().strip(), "--user start gzcoord-relay")
        ok(not os.path.exists(spawned), "the venv binary was not spawned beside the unit")
        # no unit file: the fallback spawns (and the fake binary says so)
        os.remove(unit)
        os.remove(log)
        tool("curl", f"[[ -f {json.dumps(spawned)} ]]\n")
        f = inbox.ensure_relay(runtime, "http://127.0.0.1:1")
        pids.append(f.get("pid") or 0)
        eq(f["started"], True)
        ok(f.get("pid"), "the fallback spawned and reports a pid")
        ok(os.path.exists(spawned))
        # systemctl itself failing (no manager reachable): the spawn is the fallback, not an 8 s wait on nothing
        with open(unit, "w") as fh:
            fh.write("[Service]\n")
        os.remove(spawned)
        tool("systemctl", "exit 1\n")
        t0 = time.monotonic()
        s2 = inbox.ensure_relay(runtime, "http://127.0.0.1:1")
        pids.append(s2.get("pid") or 0)
        eq(s2["started"], True)
        ok(s2.get("pid") and not s2.get("unit"), "a failed systemctl falls back to the spawn")
        ok(time.monotonic() - t0 < 6, "no eight-second wait on a unit that was never asked")
        # the passed environment: systemctl sees XDG_RUNTIME_DIR even when the shell had none
        tool("systemctl", f'echo "XDG=$XDG_RUNTIME_DIR" >> {json.dumps(log)}\n')
        tool("curl", f"[[ -f {json.dumps(log)} ]]\n")
        del os.environ["XDG_RUNTIME_DIR"]   # the shell has none: the resolved /run/user/<uid> must reach systemctl anyway
        s3 = inbox.ensure_relay(runtime, "http://127.0.0.1:1")
        pids.append(s3.get("pid") or 0)
        eq(s3.get("unit"), "gzcoord-relay", f"the unit path must be taken with no XDG_RUNTIME_DIR in the shell: {s3}")
        with open(log) as fh:
            ok(re.search(r"^XDG=/run/user/\d+$", fh.read(), re.M), "systemctl received the resolved runtime dir")
    finally:
        for pid in pids:
            if pid:
                try:
                    os.killpg(pid, 9)
                except OSError:
                    pass
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def main() -> int:
    fails = 0
    for name, fn in CASES:
        try:
            fn()
            print(f"  ok   {name}")
        except Exception as e:  # noqa: BLE001 — a case that raises is a failure, reported
            fails += 1
            print(f"  FAIL {name}: {e}")
            if not isinstance(e, Failed):
                traceback.print_exc()
    for d in SCRATCH:
        shutil.rmtree(d, ignore_errors=True)
    print(f"test_gzcoord_protocol: {'OK' if not fails else f'FAILED — {fails}'} ({len(CASES)} cases)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
