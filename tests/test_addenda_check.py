#!/usr/bin/env python3
"""Tests for tools/fabric/addenda_check.py (ADR-060 §5 rules 1, 6, 9). Every refusal is one mutation of a
file the same test shows valid first (the positive control), so a refusal is never the fixture's own fault."""
from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "tools", "fabric"))
import addenda_check as ac  # noqa: E402
from git_env import scrub_process_env  # noqa: E402 — tests/, the script's own directory
from instance_fixtures import own_instance_tree  # noqa: E402 — tests/, the script's own directory
scrub_process_env()
own_instance_tree()

ROLE = "legal-expert"
AID = "01a00000-0000-7000-8000-000000000001"
SHARED = "sha256:" + "ab" * 32
GEORGIAN = "ამ დეტალებით მე ვპასუხობ საქართველოს კანონმდებლობაზე.\n"


def addendum(body: str = "Answer for Estonian law.\n", cls: str = "charter-addendum", **over: str) -> bytes:
    fields = {"class": cls, "role": ROLE, "agent_id": AID, "lang": "en", "against_digest": SHARED}
    fields.update(over)
    head = "".join(f"{k}: {v}\n" for k, v in fields.items() if v is not None)
    return f"---\n{head}---\n{body}".encode()


def gloss(of: bytes, cls: str = "charter-addendum", **over: str) -> bytes:
    fields = {"class": cls, "role": ROLE, "agent_id": AID, "lang": "en",
              "glosses_digest": ac.body_digest(of.decode())}
    fields.update(over)
    head = "".join(f"{k}: {v}\n" for k, v in fields.items() if v is not None)
    return f"---\n{head}---\nIn English: answers for Georgian law.\n".encode()


def check(name: str, raw: bytes) -> list[str]:
    return ac.validate(ROLE, AID, name, raw)


def must_pass(name: str, raw: bytes) -> None:
    found = check(name, raw)
    assert not found, f"{name} should be valid: {found}"


def must_refuse(name: str, raw: bytes, needle: str) -> None:
    must_pass(name, addendum() if name.endswith("addendum.md") else HOLDER_OK)  # the control, same name
    found = check(name, raw)
    assert any(needle in f for f in found), f"{name}: wanted a finding with {needle!r}, got {found}"


HOLDER_OK = b'{"locale": "ge", "timezone": "Asia/Tbilisi", "search": {"country": "ge"}}\n'


def case_valid_english_and_georgian() -> None:
    must_pass("charter-addendum.md", addendum())
    must_pass("brief-addendum.md", addendum(cls="brief-addendum"))
    ge = addendum(GEORGIAN, lang="ka")
    must_pass("charter-addendum.md", ge)
    must_pass("charter-addendum.gloss.en.md", gloss(ge))
    must_pass("holder.json", HOLDER_OK)
    must_pass("holder.json", b'{"locale": "en"}\n')


def case_name_allowed_only() -> None:
    for bad in ("notes.md", "charter.md", "charter-addendum.gloss.ka.md", "../holder.json", "sub/holder.json",
                "charter-addendum.md.bak"):
        assert any("not an allowed file name" in f for f in check(bad, addendum())), bad
    must_pass("charter-addendum.md", addendum())


def case_encoding() -> None:
    must_refuse("charter-addendum.md", b"\xef\xbb\xbf" + addendum(), "byte order mark")
    must_refuse("charter-addendum.md", addendum() + b"\xff\xfe", "UTF-8")
    must_refuse("charter-addendum.md", addendum().replace(b"\n", b"\r\n"), "carriage return")
    must_refuse("charter-addendum.md", addendum("a\rb\n"), "carriage return")
    for odd in ("a\x00b", "a\x1b[31mb", "a\x85b", "a\u2028b", "a\u202eb"):
        must_refuse("charter-addendum.md", addendum(odd + "\n"), "control character")
    must_pass("charter-addendum.md", addendum("a\tb\n"))


def case_size_counts_characters() -> None:
    head = addendum("")
    room = ac.MAX_CHARS - len(head.decode())
    must_pass("charter-addendum.md", head + b"a" * room)
    must_refuse("charter-addendum.md", head + b"a" * (room + 1), "limit is 4000")
    # Georgian is three bytes a letter: 4 000 characters are 12 000 bytes and valid.
    georgian = addendum("ა" * room, lang="ka")
    assert len(georgian) > ac.MAX_CHARS * 2
    must_pass("charter-addendum.md", georgian)
    must_refuse("charter-addendum.md", addendum("ა" * (room + 1), lang="ka"), "limit is 4000")


def case_frontmatter_exact() -> None:
    must_refuse("charter-addendum.md", b"Answer for law.\n", "no frontmatter")
    for key in ("class", "role", "agent_id", "lang", "against_digest"):
        must_refuse("charter-addendum.md", addendum(**{key: None}), f"lacks {key}")
    must_refuse("charter-addendum.md", addendum(extra="x"), "outside")
    must_refuse("charter-addendum.md", addendum().replace(b"lang: en\n", b"lang: en\nlang: en\n"), "twice")
    must_refuse("charter-addendum.md", addendum().replace(b"lang: en\n", b"lang: en\n- item\n"), "key: value")
    must_refuse("charter-addendum.md", addendum().replace(b"lang: en\n", b"lang:en\n"), "key: value")


def case_frontmatter_values() -> None:
    must_refuse("charter-addendum.md", addendum(role="other-role"), "role is")
    must_refuse("charter-addendum.md", addendum(agent_id="01a00000-0000-7000-8000-00000000000f"), "agent_id is")
    must_refuse("charter-addendum.md", addendum(cls="brief-addendum"), "class is")  # a brief's class in the charter's file
    must_refuse("charter-addendum.md", addendum(cls="charter"), "class is")
    must_refuse("charter-addendum.md", addendum(lang="EN"), "language tag")
    must_refuse("charter-addendum.md", addendum(against_digest="sha256:abc"), "against_digest")
    must_refuse("charter-addendum.md", addendum(against_digest="sha256:" + "AB" * 32), "against_digest")


def case_credential_hygiene() -> None:
    leak = "token ghp_" + "a1B2c3D4e5F6g7H8" + "\n"
    found = check("charter-addendum.md", addendum(leak))
    assert any("credential hygiene" in f for f in found), found
    assert not any("ghp_" in f for f in found), "a finding must not echo the secret"
    found = check("holder.json", b'{"locale": "en", "timezone": "ghp_a1B2c3D4e5F6g7H8"}\n')
    assert any("credential hygiene" in f for f in found), found
    must_pass("charter-addendum.md", addendum("A sentence about a token is fine.\n"))


def case_model_pins() -> None:
    for text in ("Use claude-opus-5-5 for this.\n", "Run on Sonnet 5 only.\n", "model anthropic/x-1\n",
                 "prefer gpt-5 here\n"):
        must_refuse("charter-addendum.md", addendum(text), "names a model")
    for pinned in ("claude-3-5 here\n", "claude-instant\n", "claude-haiku\n"):
        must_refuse("charter-addendum.md", addendum(pinned), "names a model")
    must_refuse("charter-addendum.md", addendum("use claude\u2011opus\u20114\n"), "names a model")
    must_pass("charter-addendum.md", addendum("A sonnet is a poem; an opus is a work.\n"))
    must_pass("charter-addendum.md", addendum("Claude-Henri de Saint-Simon wrote on law.\n"))


def case_includes_placeholders_links() -> None:
    must_refuse("charter-addendum.md", addendum("{role} rules\n"), "placeholder")
    must_refuse("charter-addendum.md", addendum("@identities/roles/x/charter.md\n"), "include")
    must_refuse("charter-addendum.md", addendum("{{ include x }}\n"), "include")
    must_refuse("charter-addendum.md", addendum("#include other\n"), "include")
    must_refuse("charter-addendum.md", addendum("see [the charter](../charter.md)\n"), "link to a file")
    must_refuse("charter-addendum.md", addendum("see [x](file:///etc/passwd)\n"), "link to a file")
    must_refuse("charter-addendum.md", addendum("![i](pic.png)\n"), "link to a file")
    must_refuse("charter-addendum.md", addendum("see [x][1]\n\n[1]: docs/a.md\n"), "link to a file")
    must_refuse("charter-addendum.md", addendum("see [[charter]]\n"), "link to a file")
    must_refuse("charter-addendum.md", addendum("{% include x %}\n"), "include")
    must_refuse("charter-addendum.md", addendum("!include x\n"), "include")
    must_refuse("charter-addendum.md", addendum("<!-- include x -->\n"), "include")
    for sneaky in ("see [a [b] c](../charter.md)\n", "see [the\ncharter](../charter.md)\n",
                   "[x][1]\n\n[1]:\n  ../charter.md\n", "<file:///etc/passwd>\n", "<./charter.md>\n",
                   '<a href="../charter.md">x</a>\n', "<img src=pic.png>\n"):
        must_refuse("charter-addendum.md", addendum(sneaky), "link to a file")
    must_pass("charter-addendum.md", addendum("Text.[^1]\n\n[^1]: Civil Code art. 5.\n"))
    must_pass("charter-addendum.md", addendum("see [below](#scope); a rate <%5 is low\n"))
    must_pass("charter-addendum.md", addendum("see [the act](https://www.riigiteataja.ee/en/) and a@b.ee\n"))
    must_pass("charter-addendum.md", addendum("mail [me](mailto:a@b.ee); an email a@b.ee is prose\n"))


def case_holder_json() -> None:
    must_refuse("holder.json", b"{", "not JSON")
    must_refuse("holder.json", b"[]", "not a JSON object")
    must_refuse("holder.json", b'{"locale": "en", "locale": "ge"}', "not JSON")
    must_refuse("holder.json", b"{}", "lacks locale")
    must_refuse("holder.json", b'{"locale": "ge", "login": "x"}', "a key outside")
    for bad in ('"GE"', '"georgian"', '1', '""', '"ge_GE"'):
        must_refuse("holder.json", f'{{"locale": {bad}}}'.encode(), "locale is not")
    for bad in ('"Mars/Olympus"', '"tbilisi"', '3', '""', '"../etc/passwd"'):
        must_refuse("holder.json", f'{{"locale": "ge", "timezone": {bad}}}'.encode(), "IANA")
    for bad in ('"GE"', '"GEO"', '"G"', '1', '"1G"'):
        must_refuse("holder.json", f'{{"locale": "ge", "search": {{"country": {bad}}}}}'.encode(), "two lowercase letters")
    must_refuse("holder.json", b'{"locale": "ge", "search": {"hl": "ka"}}', "country only")
    must_refuse("holder.json", b'{"locale": "ge", "search": "GE"}', "country only")
    must_refuse("holder.json", HOLDER_OK.replace(b"\n", b"\r\n"), "carriage return")
    must_pass("holder.json", b'{"locale": "ka-ge", "timezone": "UTC", "search": {"country": "ge"}}')


def case_frontmatter_is_the_one_reader() -> None:
    digest = "sha256:" + "a" * 64
    # Reviewed #290 F2: a quoted or space-trailed digest was valid here and unreadable to a hand-rolled regex at render.
    for line in (f"against_digest: {digest}", f'against_digest: "{digest}"', f"against_digest: '{digest}'", f"against_digest: {digest}  "):
        text = addendum().decode().replace(next(l for l in addendum().decode().split("\n") if l.startswith("against_digest")), line)
        must_pass("charter-addendum.md", text.encode())
        assert ac.frontmatter(text)["against_digest"] == digest, line
    assert ac.frontmatter("no block\n") == {}


CASES = (HOLDER_OK, b'{"locale": "ka-ge", "timezone": "UTC", "search": {"country": "ge"}}', b'{"locale": "GE"}',
         b'{"locale": "ge", "search": {"country": "GE"}}', b'{"locale": "ge", "x": 1}', b'{}', b'{"locale": "ge", "search": {"hl": "ka"}}')


def case_holder_json_against_the_schema() -> None:
    import json
    import tempfile
    try:
        import jsonschema  # noqa: F401
    except ImportError:
        print("  skip case_holder_json_against_the_schema: jsonschema is not importable here")
        return
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "s.json")
        with open(path, "w") as fh:
            json.dump({"type": "object", "properties": {"locale": {"type": "string", "pattern": "^x"}}}, fh)
        found = ac._schema_findings("holder.json", {"locale": "ge"}, path)
        assert found == ["holder.json: the schema refuses locale (pattern)"], found
        assert not ac._schema_findings("holder.json", {"locale": "xx"}, path)   # the positive control
        assert not ac._schema_findings("holder.json", {"locale": "ge"}, os.path.join(tmp, "absent.json"))
    real = ac.SCHEMA_PATH
    if os.path.exists(real):   # on main the schema is there: it and the hand checks agree on each of these
        ac.SCHEMA_PATH, saved = os.path.join(tempfile.gettempdir(), "absent-schema.json"), ac.SCHEMA_PATH   # hand checks alone
        try:
            hand = {}
            for raw in CASES:
                hand[raw] = bool(ac._holder("holder.json", raw.decode()))
        finally:
            ac.SCHEMA_PATH = saved
        for raw in CASES:
            schema_refuses = bool(ac._schema_findings("holder.json", json.loads(raw)))
            assert schema_refuses == hand[raw], (raw, schema_refuses, hand[raw])


def case_link_pattern_does_not_backtrack() -> None:
    import signal

    def alarm(*_a):
        raise AssertionError("LINK_RE did not return: exponential backtracking")
    old = signal.signal(signal.SIGALRM, alarm)
    signal.alarm(10)
    try:
        for text in ("](" * 1999, "[[]" * 1300, "[" * 3999, "[a" * 1999, "![" + "[]" * 1999, "[[]" * 1000 + "x"):
            ac.LINK_RE.findall(text)
        ac.validate("r", "a", "charter-addendum.md", addendum("[[]" * 1300 + "\n"))   # through the public door too
        # The positive controls: every spelling that hides a file link is still found.
        for text, want in (("a [x [y] z](../f.md)", ["../f.md"]), ("a [x [y](../f.md)", ["../f.md"]),
                           ("see [the act [the charter](../charter.md)](https://www.riigiteataja.ee/en/)", ["../charter.md", "https://www.riigiteataja.ee/en/"]),
                           ("[[x](../f.md)](https://e.ee)", ["../f.md", "https://e.ee"]),
                           ("[a [b [c] d] e](../f.md)", ["../f.md"]), ("[a](https://e[b](../f.md)", ["https://e[b", "../f.md"])):
            assert ac.LINK_RE.findall(text) == want, (text, ac.LINK_RE.findall(text))
            if "../" in text:
                must_refuse("charter-addendum.md", addendum(text + "\n"), "link to a file")
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old)


def case_link_pattern_is_linear_on_a_run_of_destinations() -> None:
    import time

    def best(reps: int) -> float:
        text, runs = "](" * reps, []
        # CPU time, not wall time: a host at load 60 failed this on 103 of 150 wall-clock tries, none on CPU time. The least of
        # nine: a loaded host slows a run, never speeds one.
        for _ in range(9):
            t0 = time.process_time()
            ac.LINK_RE.findall(text)
            runs.append(time.process_time() - t0)
        return min(runs)
    small, large = best(2000), best(16000)
    # 8 times the input: about 8 times the time if linear, about 64 if each "](" rescans the run after it (measured on the
    # pattern whose destination class did not stop at "]": 0.05 s at the cap, 0.4 s at 5000 repetitions).
    assert large < 24 * max(small, 1e-4), f"2000 repetitions {small:.4f} s, 16000 repetitions {large:.4f} s"


def case_every_control_character_is_refused() -> None:
    for code in (list(range(0x00, 0x09)) + list(range(0x0b, 0x20)) + list(range(0x7f, 0xa0)) + [0x2028, 0x2029]
                 + list(range(0x202a, 0x202f)) + list(range(0x2066, 0x206a))):
        must_refuse("charter-addendum.md", addendum(f"a{chr(code)}b\n"), "control")
    # Spaces and format-looking code points that are not controls: refusing them would refuse real text (a no-break
    # space between a number and its unit, a narrow no-break space in French, the unassigned code points beside the bidi ones).
    for ok in ("\n", "\t", "\u00a0", "\u202f", "\u2065", "\u206a"):   # the positive control: these are allowed
        must_pass("charter-addendum.md", addendum(f"a{ok}b\n"))


def case_oversize_file_runs_no_pattern() -> None:
    saved = ac._hygiene, ac._model_pins
    calls = []
    ac._hygiene = ac._model_pins = lambda *a: calls.append(a) or []
    try:
        found = ac.validate(ROLE, AID, "charter-addendum.md", addendum("x" * (ac.MAX_CHARS + 1) + "\n"))
        assert any("the limit is" in f for f in found) and not calls, (found, len(calls))
        ac.validate(ROLE, AID, "charter-addendum.md", addendum("x\n"))
        assert calls   # the control: under the cap the patterns do run
    finally:
        ac._hygiene, ac._model_pins = saved


def case_a_finding_never_echoes_what_it_read() -> None:
    secret = "ghp_" + "A1b2C3d4" * 5
    cases = (addendum(role=secret), addendum(lang=secret), addendum(cls=secret), addendum(agent_id=secret), addendum(extra=secret))
    for raw in cases:
        found = ac.validate(ROLE, AID, "charter-addendum.md", raw)
        assert found, "the control: the planted value is a finding"
        assert not any(secret[:8] in f or secret[-8:] in f for f in found), found
    found = ac.validate(ROLE, AID, "holder.json", f'{{"locale": "ge", "{secret}": 1}}'.encode())
    assert found and not any(secret[:8] in f for f in found), found
    files = {"charter-addendum.md": addendum(lang=secret)}
    assert not any(secret[:8] in f for fs in ac.validate_set(ROLE, AID, files).values() for f in fs)


def case_a_well_formed_value_is_not_echoed_either() -> None:
    # The values that pass the shape checks are the ones a message is most tempted to quote: a lower-case tag, a key name.
    token = "qwertyui"
    found = ac.validate(ROLE, AID, "charter-addendum.gloss.en.md", gloss(addendum(), lang=f"zz-{token}"))
    assert any("lang of a gloss" in f for f in found) and not any(token in f for f in found), found
    files = {"charter-addendum.md": addendum(lang=f"zz-{token}")}
    findings = [f for fs in ac.validate_set(ROLE, AID, files).values() for f in fs]
    assert any("English gloss" in f for f in findings) and not any(token in f for f in findings), findings
    raw = addendum().replace(b"lang: en\n", f"lang: en\n{token}: x\n".encode(), 1)
    found = ac.validate(ROLE, AID, "charter-addendum.md", raw)
    assert any("outside" in f for f in found) and not any(token in f for f in found), found
    raw = addendum().replace(b"lang: en\n", f"lang: en\n{token}: x\n{token}: y\n".encode(), 1)
    assert not any(token in f for f in ac.validate(ROLE, AID, "charter-addendum.md", raw))
    raw = addendum().replace(b"lang: en\n", "lang: en\nlang: en\n".encode(), 1)
    assert any("twice" in f for f in ac.validate(ROLE, AID, "charter-addendum.md", raw))   # the control: still a finding


def case_oversize_file_runs_no_control_scan() -> None:
    saved = ac.CONTROL_RE
    seen = []

    class Spy:
        def search(self, text):
            seen.append(len(text))
            return saved.search(text)
    ac.CONTROL_RE = Spy()
    try:
        ac.validate(ROLE, AID, "charter-addendum.md", addendum("x" * (ac.MAX_CHARS + 1) + "\x01\n"))
        assert not seen, seen
        ac.validate(ROLE, AID, "charter-addendum.md", addendum("x\n"))
        assert seen   # the control: under the cap the scan runs
    finally:
        ac.CONTROL_RE = saved


def case_set_gloss_digest() -> None:
    ge = addendum(GEORGIAN, lang="ka")
    files = {"charter-addendum.md": ge, "charter-addendum.gloss.en.md": gloss(ge), "holder.json": HOLDER_OK}
    assert ac.validate_set(ROLE, AID, files) == {name: [] for name in files}
    stale = dict(files, **{"charter-addendum.md": addendum(GEORGIAN + "More.\n", lang="ka")})
    found = ac.validate_set(ROLE, AID, stale)
    assert any("stale gloss" in f for f in found["charter-addendum.gloss.en.md"]), found
    assert found["charter-addendum.md"] == []
    # The digest is of the body: a frontmatter-only change leaves the gloss current.
    reframed = dict(files, **{"charter-addendum.md": addendum(GEORGIAN, lang="ka", against_digest="sha256:" + "cd" * 32)})
    assert ac.validate_set(ROLE, AID, reframed)["charter-addendum.gloss.en.md"] == []
    # The brief's gloss is checked against the brief, not the charter.
    brief = addendum("Brief.\n", cls="brief-addendum", lang="ka")
    mixed = {"charter-addendum.md": ge, "brief-addendum.md": brief,
             "brief-addendum.gloss.en.md": gloss(ge, cls="brief-addendum")}
    assert any("stale gloss" in f for f in ac.validate_set(ROLE, AID, mixed)["brief-addendum.gloss.en.md"])


def case_gloss_required_for_other_languages_only() -> None:
    ge = addendum(GEORGIAN, lang="ka")
    found = ac.validate_set(ROLE, AID, {"charter-addendum.md": ge})
    assert any("needs its English gloss" in f for f in found["charter-addendum.md"]), found
    assert ac.validate_set(ROLE, AID, {"charter-addendum.md": ge, "charter-addendum.gloss.en.md": gloss(ge)})[
        "charter-addendum.md"] == []
    en = addendum()
    assert ac.validate_set(ROLE, AID, {"charter-addendum.md": en})["charter-addendum.md"] == []
    found = ac.validate_set(ROLE, AID, {"charter-addendum.md": en, "charter-addendum.gloss.en.md": gloss(en)})
    assert any("already in English" in f for f in found["charter-addendum.gloss.en.md"]), found
    # The brief's gloss is not the charter's.
    brief = addendum("Brief.\n", cls="brief-addendum", lang="ka")
    found = ac.validate_set(ROLE, AID, {"brief-addendum.md": brief, "charter-addendum.gloss.en.md": gloss(ge)})
    assert any("needs its English gloss" in f for f in found["brief-addendum.md"]), found


def case_no_tz_database_is_an_error_not_a_verdict() -> None:
    real = ac.zoneinfo.available_timezones
    ac.zoneinfo.available_timezones = lambda: set()
    try:
        try:
            check("holder.json", HOLDER_OK)
        except RuntimeError:
            return
        raise AssertionError("an empty tz database was read as a verdict")
    finally:
        ac.zoneinfo.available_timezones = real


def case_imports_no_lint() -> None:
    import subprocess
    code = ("import sys; sys.path.insert(0, %r); import addenda_check; "
            "sys.exit(any(m.split('.')[0] in ('lint', 'fabric_lint_rules') for m in sys.modules))"
            % os.path.join(ROOT, "tools", "fabric"))
    subprocess.run([sys.executable, "-c", code], check=True, timeout=60)


def case_gloss_shape() -> None:
    ge = addendum(GEORGIAN, lang="ka")
    must_refuse("charter-addendum.md", ge.replace(b"lang: ka", b"lang: ka\nglosses_digest: x"), "outside")
    found = check("charter-addendum.gloss.en.md", gloss(ge, lang="ka"))
    assert any("lang of a gloss" in f for f in found), found
    found = check("charter-addendum.gloss.en.md", gloss(ge, cls="brief-addendum"))
    assert any("class is" in f for f in found), found
    found = check("charter-addendum.gloss.en.md", gloss(ge, glosses_digest="sha256:zz"))
    assert any("glosses_digest" in f for f in found), found
    found = check("charter-addendum.gloss.en.md", gloss(ge).replace(b"glosses_digest", b"against_digest"))
    assert any("lacks glosses_digest" in f for f in found), found
    orphan = ac.validate_set(ROLE, AID, {"charter-addendum.gloss.en.md": gloss(ge)})
    assert any("not in the set" in f for f in orphan["charter-addendum.gloss.en.md"]), orphan


def case_body_digest_rule_matches_lint() -> None:
    # lint_rules/prompts.py _source_digest, the rule this one reimplements, read here on a file.
    import tempfile
    sys.path.insert(0, os.path.join(ROOT, "tools", "fabric"))
    import lint  # noqa: E402,F401  (puts fabric_lint_rules on the path)
    from fabric_lint_rules.prompts import _source_digest
    raw = addendum(GEORGIAN, lang="ka")
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "a.md")
        with open(path, "wb") as fh:
            fh.write(raw)
        assert _source_digest(path) == ac.body_digest(raw.decode())


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
