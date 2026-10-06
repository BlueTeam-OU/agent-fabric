#!/usr/bin/env python3
"""The i18n suite's function cases, ported case for case from
communication/gzcoord/tests/i18n.test.mjs to the Python tools
(tools/fabric/gzcoord/, agent-fabric ADR-040 §7, Wave 7). The lines the
tools print are in the language of the login that reads them; a locale
reaches the fabric's own lines and stops at the wire's. The command cases
stay in that file and run unchanged against the shims. Two cases read the
source, and read the modules now (ADR-040's 2026-10-01 amendment: a case
reading the source reads the module). Plain script: prints ok/FAIL, exit 1
on any failure."""
from __future__ import annotations

import ast
import json
import os
import pwd
import re
import shutil
import subprocess
import sys
import tempfile
import traceback
from typing import Any, Callable

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
from gzcoord import gzmsg, i18n, inbox  # noqa: E402

MODULES = os.path.join(HERE, "tools", "fabric", "gzcoord")
FABRIC = HERE
with open(os.path.join(HERE, "communication", "gzcoord", "i18n", "i18n.schema.json"), encoding="utf-8") as _fh:
    # The key shape is the schema's, read — not a third copy of the rule
    # (blind review F6 on PR #28).
    SLUG = re.compile(json.load(_fh)["propertyNames"]["pattern"])

CASES: list[tuple[str, Callable[[], None]]] = []
SCRATCH: list[str] = []


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


def scratch(prefix: str) -> str:
    d = tempfile.mkdtemp(prefix=prefix)
    SCRATCH.append(d)
    return d


@case("the default dictionary is the house i18n shape: dotted slugs, non-empty strings")
def _():
    en = i18n.default_dictionary()
    eq(os.path.basename(i18n.DEFAULT_PATH), f"{i18n.DEFAULT_LOCALE}.json")
    for k, v in en.items():
        ok(SLUG.search(k), f"key {k}")
        eq(type(v), str, f"value of {k}")
        ok(v != "", f"value of {k}")


@case("the locale a login reads is the launcher's rule: what follows the last dash")
def _():
    eq(i18n.suffix("language-culture-ge"), "ge")
    eq(i18n.suffix("language-culture-ru"), "ru")
    eq(i18n.suffix("brand-comms-01"), "01")   # no locale/01: the default
    eq(i18n.suffix("user"), "user")


@case("the suffix names its tag in locale.json — ge is Georgian, not German")
def _():
    def d(s: str) -> str:
        return os.path.join(FABRIC, "identities", "roles", "language-culture", "locale", s)
    eq(i18n.locale_tag(d("ge")), "ka-GE")
    eq(i18n.locale_tag(d("ru")), "ru-RU")
    eq(i18n.locale_tag(d("nothing-here")), None)


def _sources() -> dict[str, str]:
    out = {}
    for name in ("inbox.py", "gzmsg.py", "send.py"):
        with open(os.path.join(MODULES, name), encoding="utf-8") as fh:
            out[name] = fh.read()
    return out


@case("every key the code prints is in en-US.json, and en-US.json has no key nothing prints")
def _():
    en = i18n.default_dictionary()
    used: set[str] = set()
    # Every module that prints a dictionary line, not just the inbox: the
    # validator's diagnostics are keys too, and a guard scoped to one file
    # would call every one of them dead (the automated review's claim 2).
    for src in _sources().values():
        used.update(m.group(1) for m in re.finditer(r"""\bt\(\s*["']([a-z][a-z.-]+)["']""", src))
        used.update(m.group(1) for m in re.finditer(r"""\ben\(\)\(\s*["']([a-z][a-z.-]+)["']""", src))
    eq(sorted(k for k in used if k not in en), [], "printed but not in en-US.json")
    eq(sorted(k for k in en if k not in used), [], "in en-US.json but nothing prints it")


@case("a helper that defaults its printer to English is handed the caller's at every call")
def _():
    # send called integration_config and assert_not_control_channel without its
    # printer, so on a login with an active locale two refusals were an English
    # body in a translated frame (review of #29). The defaults exist for
    # callers with no locale at all; every module here has one. Read by the
    # syntax tree, not by text: a helper's printer is the parameter named t,
    # positional, defaulting to None; every call names it — at its position
    # or as t= — and a call that wants English says en().
    tree = ast.parse(_sources()["inbox.py"])
    helpers: dict[str, int] = {}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            names = [a.arg for a in node.args.args]
            if "t" in names and node.args.defaults:
                helpers[node.name] = names.index("t")
    ok("integration_config" in helpers and "assert_not_control_channel" in helpers, f"helpers found: {sorted(helpers)}")
    bare = []
    for file, src in _sources().items():
        for node in ast.walk(ast.parse(src)):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            name = fn.attr if isinstance(fn, ast.Attribute) else fn.id if isinstance(fn, ast.Name) else None
            if name not in helpers:
                continue
            given = len(node.args) > helpers[name] or any(k.arg == "t" for k in node.keywords)
            if not given:
                bare.append(f"{file}:{node.lineno}: {name}(…)")
    eq(bare, [], "called without the caller's printer")


def active(body: str | None, tag: str = "ka-GE", locale: dict | None | bool = True) -> tuple[str, str, dict]:
    root = scratch("locale-")
    d = os.path.join(root, "identities", "roles", "language-culture", "locale", "ge")
    os.makedirs(d)
    if locale is True:
        locale = {"tag": tag}
    if locale:
        with open(os.path.join(d, "locale.json"), "w", encoding="utf-8") as fh:
            json.dump(locale, fh)
    if body is not None:
        with open(os.path.join(d, f"{tag}.json"), "w", encoding="utf-8") as fh:
            fh.write(body)
    return root, d, {"agent": "language-culture-ge", "role": "language-culture"}


@case("a login with no active dictionary reads the default locale")
def _():
    root = scratch("locale-")
    eq(i18n.dictionary_path({"agent": "user", "role": "fabric-coordinator"}, root, {}), None)
    eq(i18n.dictionary_path({"agent": "language-culture-ge"}, root, {}), None, "no role bound")
    r1, _d, me = active(None)
    eq(i18n.dictionary_path(me, r1, {}), None, "a tag with no dictionary file")
    r2, _d, _me = active("{}", locale=None)
    eq(i18n.dictionary_path({"agent": "language-culture-ge", "role": "language-culture"}, r2, {}), None, "no tag")


@case("an active locale is found by its tag")
def _():
    root, d, me = active("{}")
    eq(i18n.dictionary_path(me, root, {}), os.path.join(d, "ka-GE.json"))


@case("an active locale covers the keys it carries; the default stands for the rest")
def _():
    root, _d, me = active(json.dumps({
        "inbox.others-header": "ᲗᲐᲠᲒᲛᲐᲜᲘ (SPEC §17):",
        "inbox.head": "",                     # not a localization value
        "nothing.like-this": "invented",      # not a key of the default
    }))
    d, en = i18n.dictionary(me, root=root, env={}), i18n.default_dictionary()
    eq(d["inbox.others-header"], "ᲗᲐᲠᲒᲛᲐᲜᲘ (SPEC §17):")
    eq(d["inbox.head"], en["inbox.head"], "an empty value is not a translation")
    eq(d["delivery.title"], en["delivery.title"], "a key it lacks falls back, never invented")
    ok("nothing.like-this" not in d, "a key the default does not have is not added")


@case("an unreadable dictionary leaves the default standing — a session start never fails on it")
def _():
    root, _d, me = active("{ this is not json")
    eq(i18n.dictionary(me, root=root, env={}), i18n.default_dictionary())


@case("a placeholder the caller did not supply is left standing, not blanked")
def _():
    eq(i18n.fill("seq {first}–{last}", {"first": 1, "last": 9}), "seq 1–9")
    eq(i18n.fill("a {who} and {missing}", {"who": "x"}), "a x and {missing}")


@case("an unknown key prints as itself: a bug report, not a crash")
def _():
    eq(i18n.printer(i18n.default_dictionary())("no.such-key"), "no.such-key")


def fixture() -> dict:
    def body(mid: str, to: str) -> str:
        return (f"[GZCOORD/1] OBSERVATION\nFROM: h/sender\nROLE: backend-dev\nPROJECT: gzapp\nMESSAGE-ID: {mid}\n{to}\n"
                f"SUBJECT: a subject\n\nNOTES:\nthe body, as its sender wrote it\n")

    def rec(seq: int, content: str) -> dict:
        return {"seq": seq, "id": f"r{seq}", "sender": "h/sender", "timestamp": "2026-09-21T08:00:00Z", "content": content}
    return {"delivered": True, "classified": [
        {"rec": rec(1, body("01a0-1", "TO: h/me")),
         "msg": {"type": "OBSERVATION", "metadata": {"MESSAGE-ID": "01a0-1", "TO": "h/me", "SUBJECT": "a subject"}}, "isMine": True},
        {"rec": rec(2, body("01a0-2", "TO: h/other")),
         "msg": {"type": "OBSERVATION", "metadata": {"MESSAGE-ID": "01a0-2", "TO": "h/other", "SUBJECT": "other"}}, "isMine": False},
    ]}


ME = {"address": "h/me", "instance": "me", "slug": "language-culture"}


@case("the locale reaches the fabric's own lines and stops at the wire")
def _():
    root, _d, me = active(json.dumps({
        "inbox.head": "ᲨᲔᲛᲝᲡᲣᲚᲘ {who}: {mine} / {others}, {channel}",
        "inbox.others-header": "ᲐᲠ ᲐᲠᲘᲡ ᲨᲔᲜᲗᲕᲘᲡ (SPEC §17):",
    }))
    out = inbox.render(fixture(), ME, "gzapp:gzcoord", None, t=i18n.printer(i18n.dictionary(me, root=root, env={})))
    ok(re.search(r"^ᲨᲔᲛᲝᲡᲣᲚᲘ h/me \(language-culture\): 1 / 1, gzapp:gzcoord$", out, re.M), out)
    ok(re.search(r"^ᲐᲠ ᲐᲠᲘᲡ ᲨᲔᲜᲗᲕᲘᲡ \(SPEC §17\):$", out, re.M), out)
    # The wire, untouched: the sender's body, the metadata keys, the type,
    # and the addressing vocabulary a reader matches by name.
    ok(re.search(r"^\[GZCOORD/1\] OBSERVATION$", out, re.M))
    ok(re.search(r"^MESSAGE-ID: 01a0-1$", out, re.M))
    ok(re.search(r"^the body, as its sender wrote it$", out, re.M))
    ok(re.search(r"01a0-2 {2}OBSERVATION {2}TO h/other {2}other", out), out)


@case("the locale's standing reminder rides the head line, and only it")
def _():
    root, _d, me = active(json.dumps({"inbox.head": "ᲨᲔᲛᲝᲡᲣᲚᲘ {who}, {channel}"}),
                          locale={"tag": "ka-GE", "reminder": " - ᲘᲤᲘᲥᲠᲔ"})
    reminder = i18n.locale_reminder(me, root, {})
    eq(reminder, " - ᲘᲤᲘᲥᲠᲔ")
    out = inbox.render(fixture(), ME, "gzapp:gzcoord", None, t=i18n.printer(i18n.dictionary(me, root=root, env={})),
                       reminder=reminder)
    ok(re.search(r"^ᲨᲔᲛᲝᲡᲣᲚᲘ h/me \(language-culture\), gzapp:gzcoord - ᲘᲤᲘᲥᲠᲔ$", out, re.M), out)
    eq(len([x for x in out.split("\n") if "ᲘᲤᲘᲥᲠᲔ" in x]), 1, "the head line and no other")


@case("no locale, no reminder: nothing is appended for a default-locale login")
def _():
    root = scratch("locale-")
    eq(i18n.locale_reminder({"agent": "user", "role": "fabric-coordinator"}, root, {}), "")
    eq(i18n.locale_reminder({"agent": "language-culture-ge"}, root, {}), "", "no role bound")
    r, _d, _me = active("{}", locale={"tag": "ka-GE"})
    eq(i18n.locale_reminder({"agent": "language-culture-ge", "role": "language-culture"}, r, {}), "",
       "a locale that declares none")


@case("the reminder each real locale carries is the owner's, in that locale")
def _():
    def of(s: str) -> str:
        return i18n.locale_reminder({"agent": f"language-culture-{s}", "role": "language-culture"}, FABRIC, {})
    for s in ("ge", "ru"):
        ok(of(s) != "", f"{s} carries one")
        ok(of(s).startswith(" - "), f"{s} appends to the head line")
        ok(re.search(r"[^\u0000-ɏ]", of(s)), f"{s} is in its own script")


@case("a keyword refusal reads in the login's own language")
def _():
    ka = i18n.printer({**i18n.default_dictionary(), "keyword.too-short": "ᲛᲝᲙᲚᲔᲐ {keyword} — {min}"})
    try:
        inbox.check_keywords(["ab"], ka)
        raise Failed("accepted")
    except inbox.KeywordError as e:
        ok(re.search(r'ᲛᲝᲙᲚᲔᲐ "ab" — 3', str(e)), str(e))
    ka2 = i18n.printer({**i18n.default_dictionary(), "keyword.too-many": "ᲖᲔᲓᲐ ᲖᲦᲕᲐᲠᲘ {max}"})
    try:
        inbox.check_keywords([f"kw{i}" for i in range(9)], ka2)
        raise Failed("accepted")
    except inbox.KeywordError as e:
        ok(re.search(r"ᲖᲔᲓᲐ ᲖᲦᲕᲐᲠᲘ 8", str(e)), str(e))


@case("a validator diagnostic reaches a locale reader whole, not just its prefix")
def _():
    root, _d, me = active(json.dumps({
        "delivery.invalid": "ᲐᲠᲐᲡᲬᲝᲠᲘ: {detail}",
        "validate.missing": "ᲐᲙᲚᲘᲐ {key}",
        "validate.no-addressing": "ᲐᲠᲐᲕᲘᲡᲗᲕᲘᲡ: TO, TO-ROLE ᲐᲜ BROADCAST: true",
    }))
    t = i18n.printer(i18n.dictionary(me, root=root, env={}))
    # FROM is malformed on purpose: validate.from-shape is a key this locale
    # does NOT carry, so the same call proves both halves at once.
    v = gzmsg.validate("[GZCOORD/1] INFO\nFROM: not-an-address\nROLE: backend-dev\nPROJECT: gzapp\n", t=t, max_columns=0)
    # The substance, not only the wrapper — the whole point of the finding.
    ok("ᲐᲙᲚᲘᲐ MESSAGE-ID" in v["errors"], " | ".join(v["errors"]))
    ok("ᲐᲠᲐᲕᲘᲡᲗᲕᲘᲡ: TO, TO-ROLE ᲐᲜ BROADCAST: true" in v["errors"], " | ".join(v["errors"]))
    # A key the locale lacks falls back to en-US, never to invented text.
    ok(i18n.default_dictionary()["validate.from-shape"] in v["errors"], " | ".join(v["errors"]))


@case("the assignment diagnostic agrees with its own number")
def _():
    # The old code built both from one template with a plural on the noun
    # only, so the singular read "REQUEST section make this an assignment".
    # Splitting the key fixed the verb; these pin both.
    def msg(n: str) -> str:
        return f"[GZCOORD/1] INFO\nFROM: h/s\nROLE: backend-dev\nPROJECT: gzapp\nMESSAGE-ID: x\nTO-ROLE: backend-dev\n\n{n}"
    one = " | ".join(gzmsg.validate(msg("REQUEST:\na\n"), max_columns=0)["errors"])
    two = " | ".join(gzmsg.validate(msg("REQUEST:\na\n\nACCEPTANCE:\nb\n"), max_columns=0)["errors"])
    ok(re.search(r"REQUEST section makes this an assignment", one), one)
    ok(re.search(r"REQUEST and ACCEPTANCE sections make this an assignment", two), two)


@case("the default locale still produces the validator's English, byte for byte")
def _():
    v = gzmsg.validate("[GZCOORD/1] INFO\nFROM: h/s\nROLE: backend-dev\nPROJECT: gzapp\n", max_columns=0)
    ok("missing MESSAGE-ID" in v["errors"], " | ".join(v["errors"]))
    ok("missing TO, TO-ROLE or BROADCAST: true" in v["errors"], " | ".join(v["errors"]))
    eq(gzmsg.validate("nonsense")["errors"], ["invalid GZCOORD/1 first line"])


ROLE = "language-culture"


def live_locale() -> tuple[str, dict]:
    """A scratch fabric root whose locale belongs to the login running the
    suite: the login is whatever runs it, so the fixture supplies the role
    through the BINDING (CI's login has none)."""
    agent = pwd.getpwuid(os.geteuid()).pw_name
    root = scratch("live-locale-")
    d = os.path.join(root, "identities", "roles", ROLE, "locale", i18n.suffix(agent))
    os.makedirs(d)
    with open(os.path.join(d, "locale.json"), "w", encoding="utf-8") as fh:
        json.dump({"tag": "xx-XX", "reminder": " - ᲛᲘᲜᲘᲨᲜᲔᲑᲐ"}, fh)
    en = i18n.default_dictionary()
    with open(os.path.join(d, "xx-XX.json"), "w", encoding="utf-8") as fh:
        json.dump({k: f"ᲗᲐᲠᲒᲛᲐᲜᲘ {v}" for k, v in en.items()}, fh)
    return root, {"agent": agent, "role": ROLE}


@case("the switch silences the standing reminder too, and only for exactly 1")
def _():
    root, me = live_locale()
    eq(i18n.locale_reminder(me, root, {}), " - ᲛᲘᲜᲘᲨᲜᲔᲑᲐ")
    eq(i18n.locale_reminder(me, root, {"GZCOORD_DEFAULT_LOCALE_ONLY": "1"}), "")
    eq(i18n.dictionary_path(me, root, {"GZCOORD_DEFAULT_LOCALE_ONLY": "1"}), None)
    # A value that reads as "no" must not pin.
    for off in ("0", "false", "no", "off", ""):
        eq(i18n.locale_reminder(me, root, {"GZCOORD_DEFAULT_LOCALE_ONLY": off}), " - ᲛᲘᲜᲘᲨᲜᲔᲑᲐ", off)
        ok(i18n.dictionary_path(me, root, {"GZCOORD_DEFAULT_LOCALE_ONLY": off}), off)


@case("a default-locale login renders exactly what it rendered before a dictionary existed")
def _():
    out = inbox.render(fixture(), ME, "gzapp:gzcoord", None)
    ok(re.search(r"^gzcoord inbox for h/me \(language-culture\): 1 for you, 1 not addressed to you, on gzapp:gzcoord$", out, re.M),
       out)
    ok(re.search(r"^Not addressed to you — listed, bodies not read \(SPEC §17\):$", out, re.M), out)
    ok(re.search(r"^--- relay seq 1, from h/sender, 2026-09-21T08:00:00Z$", out, re.M), out)


# ── cases that run a command beside a function: ported whole ─────────

INBOX_CMD = os.path.join(HERE, "communication", "gzcoord", "scripts", "inbox.mjs")


def last_line(text: str) -> str:
    """A tool may print a diagnostic before the line under test — the
    pinned-locale notice does, on a login that has a dictionary."""
    return text.strip().split("\n")[-1]


def replay_usage(env: dict) -> "subprocess.CompletedProcess[str]":
    return subprocess.run(["node", INBOX_CMD, "--replay"], env=env, capture_output=True, text=True, timeout=60,
                          stdin=subprocess.DEVNULL)


@case("--replay with no value is a usage line and exit 1")
def _():
    # Pinned to the default locale: the case is about the usage line, and a
    # login with a dictionary of its own (a ru holder) prints it translated.
    r = replay_usage({**os.environ, "GZCOORD_DEFAULT_LOCALE_ONLY": "1"})
    eq(r.returncode, 1, r.stderr)
    eq(last_line(r.stderr), i18n.default_dictionary()["replay.usage"])


USAGE_KA = "ᲒᲐᲛᲝᲧᲔᲜᲔᲑᲐ: inbox.mjs --replay <seq|message-id>"


def live_env(values: dict) -> tuple[str, dict, dict]:
    """The tools run AS a login with a dictionary: a scratch fabric root
    holding the locale, and a binding giving the role. A scratch root has
    no identity.py, so whoami() falls back to the login plus this binding."""
    agent = pwd.getpwuid(os.geteuid()).pw_name
    root, state = scratch("live-locale-"), scratch("live-state-")
    os.makedirs(os.path.join(state, "agents", agent))
    with open(os.path.join(state, "agents", agent, "binding.json"), "w", encoding="utf-8") as fh:
        json.dump({"role": ROLE, "project": "agent-fabric"}, fh)
    d = os.path.join(root, "identities", "roles", ROLE, "locale", i18n.suffix(agent))
    os.makedirs(d)
    with open(os.path.join(d, "locale.json"), "w", encoding="utf-8") as fh:
        json.dump({"tag": "xx-XX", "reminder": " - ᲛᲘᲜᲘᲨᲜᲔᲑᲐ"}, fh)
    en = i18n.default_dictionary()
    with open(os.path.join(d, "xx-XX.json"), "w", encoding="utf-8") as fh:
        json.dump({k: values.get(k, f"ᲗᲐᲠᲒᲛᲐᲜᲘ {v}") for k, v in en.items()}, fh)
    env = {**os.environ, "AGENT_FABRIC_ROOT": root, "AGENT_FABRIC_STATE_DIR": state}
    return root, {"agent": agent, "role": ROLE}, env


@case("the tools run as a login that HAS a dictionary, and print it")
def _():
    _root, _me, env = live_env({"replay.usage": USAGE_KA})
    r = replay_usage({**env, "GZCOORD_DEFAULT_LOCALE_ONLY": ""})
    eq(r.returncode, 1, r.stderr)
    eq(last_line(r.stderr), USAGE_KA)


@case("a locale dictionary that cannot be read falls back to English, and says so")
def _():
    root, me, env = live_env({})
    with open(os.path.join(root, "identities", "roles", me["role"], "locale", i18n.suffix(me["agent"]), "xx-XX.json"), "w") as fh:
        fh.write("{ not json")
    r = replay_usage({**env, "GZCOORD_DEFAULT_LOCALE_ONLY": ""})
    eq(r.returncode, 1, r.stderr)
    eq(last_line(r.stderr), i18n.default_dictionary()["replay.usage"])
    ok(re.search(r"xx-XX\.json could not be read .*; printing the default locale", r.stderr), r.stderr)


@case("and the same run pinned to the default locale prints English, whoever runs it")
def _():
    _root, _me, env = live_env({"replay.usage": USAGE_KA})
    r = replay_usage({**env, "GZCOORD_DEFAULT_LOCALE_ONLY": "1"})
    eq(r.returncode, 1, r.stderr)
    # The English line, and the notice that a configured locale was pinned
    # away — silence there is what the switch's threat model asks about.
    ok(re.search(f"^{re.escape(i18n.default_dictionary()['replay.usage'])}$", r.stderr, re.M), r.stderr)
    ok(re.search(r"GZCOORD_DEFAULT_LOCALE_ONLY=1 — printing the default locale, not ", r.stderr), r.stderr)
    ok(USAGE_KA not in r.stderr, r.stderr)


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
    print(f"test_gzcoord_i18n: {'OK' if not fails else f'FAILED — {fails}'} ({len(CASES)} cases)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
