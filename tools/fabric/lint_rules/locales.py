"""tools/fabric/lint_rules/locales.py — the locale rules: translations, worker prompts, locale files and the i18n dictionaries.
A part of tools/fabric/lint.py, the entry point."""
from __future__ import annotations

import json
import os
import re
from typing import Any

from .base import FRONTMATTER_RE, layout
from .docs import hygiene_findings, parse_frontmatter
from .prompts import (
    CHARS_PER_TOKEN,
    LOCALE_DIRNAME,
    LOCALE_TRANSLATIONS,
    NON_LATIN_CHARS_PER_TOKEN,
    WARNINGS,
    WORKER_TOOL,
    _is_mostly_non_latin,
    _locale_budget,
    _source_digest,
    protected_token_findings,
)
from .schema import validate_json


def locale_translation_findings(role: str, role_path: str, template_schema: dict[str, Any] | None) -> list[str]:
    """identities/roles/<role>/locale/<suffix>/<name>.md for every name in
    LOCALE_TRANSLATIONS: a translation launch_prompt renders for a login
    whose name ends in <suffix> in place of the English. The charter and
    the brief are slices (schema, class, role); every translation names
    its source and the source's digest, passes hygiene, keeps every
    protected token, and fits its budget."""
    out: list[str] = []
    base = os.path.join(role_path, LOCALE_DIRNAME)
    if not os.path.isdir(base):
        return out
    root = layout.FABRIC_ROOT
    for suffix in sorted(os.listdir(base)):
        for name, (source_rel, klass, budget_key, with_schema) in LOCALE_TRANSLATIONS.items():
            path = os.path.join(base, suffix, f"{name}.md")
            if not os.path.isfile(path):
                continue
            rel = f"identities/roles/{role}/{LOCALE_DIRNAME}/{suffix}/{name}.md"
            source_rel = source_rel.replace("{role}", role)
            lagging = False
            source = os.path.join(root, source_rel)
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
            meta = parse_frontmatter(text)
            if meta is None:
                out.append(f"{rel}: no frontmatter — a translation carries its source and digest")
                continue
            if with_schema and template_schema:
                out += validate_json(template_schema, meta, rel)
            if meta.get("class") != klass:
                out.append(f"{rel}: class {meta.get('class')!r}; a locale {name} is class {klass}")
            if with_schema and meta.get("role") != role:
                out.append(f"{rel}: role {meta.get('role')!r} but lives under {role}/")
            of, digest = meta.get("translates"), meta.get("translates_digest")
            if not of or not digest:
                out.append(f"{rel}: no `translates` / `translates_digest` — which English source, and at what digest")
            else:
                if of != source_rel:
                    out.append(f"{rel}: translates {of!r}, not {source_rel}")
                if os.path.isfile(source):
                    now = _source_digest(source)
                    if digest != now:
                        # Served, never a failed launch (launch_prompt.py): the
                        # source has to land before its holder can re-render, so
                        # a lag is a warning that names the file, not a finding
                        # that reddens main until the holder's PR (2026-09-18).
                        lagging = True
                        WARNINGS.append(f"{rel}: translates {source_rel} at {digest}, but it is now {now} "
                                        "— the translation lags; the holder re-renders it and its digest")
            body = FRONTMATTER_RE.sub("", text)
            out += hygiene_findings(rel, body)
            if os.path.isfile(source):
                if not lagging:   # tokens are judged against the source it translated, not one that moved under it
                    with open(source, encoding="utf-8") as fh:
                        out += protected_token_findings(rel, FRONTMATTER_RE.sub("", fh.read()), body)
            else:
                out.append(f"{rel}: its source {source_rel} does not exist")
            divisor = NON_LATIN_CHARS_PER_TOKEN if _is_mostly_non_latin(body) else CHARS_PER_TOKEN
            approx = int(len(body) / divisor)
            cap = _locale_budget(budget_key)
            if approx > cap:
                out.append(f"{rel}: ~{approx} tokens (at {divisor} chars/token) exceeds the locale budget {cap} "
                           "— a launch prompt pays every one of them")
    return out


AGENT_FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)


def locale_worker_findings(role: str, role_path: str) -> list[str]:
    """identities/roles/<role>/locale/<suffix>/worker.md: the locale's
    worker — a Claude Code agent file (name, description, model, tools),
    not a slice. install-agent-files.sh installs it as
    ~/.claude/agents/locale-worker.md on a login of this role whose name
    ends in <suffix>, and removes it by the `agent-fabric` marker in its
    description, so the shape is asserted here: the name the dispatcher
    uses, a one-line description in the locale carrying the `agent-fabric`
    marker, exactly one inert tool (it must read nothing, and the harness
    spawns no agent with none), and a body that passes hygiene."""
    out: list[str] = []
    base = os.path.join(role_path, LOCALE_DIRNAME)
    if not os.path.isdir(base):
        return out
    for suffix in sorted(os.listdir(base)):
        path = os.path.join(base, suffix, "worker.md")
        if not os.path.isfile(path):
            continue
        rel = f"identities/roles/{role}/{LOCALE_DIRNAME}/{suffix}/worker.md"
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        m = AGENT_FRONTMATTER_RE.match(text)
        if not m:
            out.append(f"{rel}: no agent frontmatter (name, description, model, tools)")
            continue
        fields: dict[str, str] = {}
        for line in m.group(1).splitlines():
            km = re.match(r"^([A-Za-z_][A-Za-z0-9_-]*):\s*(.*)$", line)
            if km:
                fields[km.group(1)] = km.group(2).strip()
        if fields.get("name") != "locale-worker":
            out.append(f"{rel}: name {fields.get('name')!r}; the installer and the guard know it as locale-worker")
        desc = fields.get("description", "").strip("\"'")
        if not desc:
            out.append(f"{rel}: no description — the dispatcher reads it")
        else:
            if "agent-fabric" not in desc:
                out.append(f"{rel}: description lacks the `agent-fabric` marker the installer removes it by")
            # The description never reaches the worker (the body is its
            # system prompt); its reader is the dispatcher — the holder,
            # who reasons in the locale — so it is written in the locale
            # too, the marker and the name kept as identifiers (the CEO,
            # 2026-09-17). An English description was the first shape.
            if not _is_mostly_non_latin(desc.replace("agent-fabric", "").replace("locale-worker", "")):
                out.append(f"{rel}: description is not in the locale — its only reader is the bridge, which reasons in the locale; keep `agent-fabric` as the marker")
        if fields.get("model", "") not in ("haiku", "sonnet", "opus", "fable"):
            out.append(f"{rel}: model {fields.get('model')!r}; a harness alias (haiku/sonnet/opus/fable)")
        # Read back 2026-09-17 (docs/live-checks/2026-09-17-language-culture-bridge.md):
        # an empty `tools:` inherits EVERY tool, and the harness refuses to
        # spawn an agent whose list resolves to none — so the worker carries
        # exactly one tool that reads and writes nothing.
        if fields.get("tools", "").strip("[] \"'") != WORKER_TOOL:
            out.append(f"{rel}: tools {fields.get('tools')!r}; the worker reads nothing — its one tool is {WORKER_TOOL} "
                       "(an empty list inherits every tool; none at all is refused by the harness)")
        out += hygiene_findings(rel, text[m.end():])
    return out


# What each engine of the locale search tool takes, as it spells it
# (runtime/mcp/websearch-locale): SerpAPI's gl (a country, lower-case ISO
# 3166-1 alpha-2) and hl (the language), Google's own spellings, with
# google_domain and lr where the file names them; Brave's
# country (upper-case, or ALL) and, only where Brave has the language,
# search_lang and ui_lang. Every engine block carries the tool's
# description in the locale.
LOCALE_ENGINES = {
    "serpapi": ({"gl": re.compile(r"^[a-z]{2}$"),
                 "hl": re.compile(r"^[a-z]{2,3}(-[A-Za-z]{2,4})?$")},
                {"google_domain": re.compile(r"^google\.[a-z.]{2,6}$"),
                 "lr": re.compile(r"^lang_[a-z]{2,3}(-[A-Za-z]{2,4})?$")}),
    "brave": ({"country": re.compile(r"^([A-Z]{2}|ALL)$")},
              {"search_lang": re.compile(r"^[a-z]{2,3}(-[a-z]{2,4})?$"),
               "ui_lang": re.compile(r"^[a-z]{2,3}-[A-Z]{2}$")}),
}


# The locale file's own scalars. `tag` is the locale's BCP-47 tag and the
# one place that says what a login's suffix MEANS — `ge` is Georgian
# (ka-GE), not German — so the dictionary that suffix reads is found by
# data and never by reading the directory name (communication/gzcoord/
# i18n/README.md).
LOCALE_FILE_RE = {"timezone": re.compile(r"^[A-Za-z_]+/[A-Za-z_]+(/[A-Za-z_]+)?$"),
                  "tag": re.compile(r"^[a-z]{2,3}-[A-Z]{2}$")}


# Optional, and in the locale: the standing "think in <the language>" the
# holder reads on every drain and every delivery, appended to the inbox's
# head line. Not a dictionary key — it translates no English line, and an
# en-US login has no such rule (tools/fabric/gzcoord/i18n.py).
LOCALE_FILE_OPTIONAL = ("reminder",)

# The fleet's source language: every prompt piece and the tools'
# dictionary are written in it (communication/gzcoord/i18n/en-US.json).
# A locale with this tag translates nothing — its holder works in the
# source, with no bridge worker — so it carries only locale.json, and the
# "is this text in the locale" test, which reads a non-Latin script as the
# locale's, does not apply to it (the owner, 2026-10-07: language-culture-en
# for a project's English copy).
SOURCE_TAG = "en-US"


def _locale_tag(locale_dir: str) -> str | None:
    try:
        with open(os.path.join(locale_dir, "locale.json"), encoding="utf-8") as fh:
            tag = json.load(fh).get("tag")
    except (OSError, ValueError, AttributeError):
        return None
    return tag if isinstance(tag, str) else None


def locale_file_findings(role: str, role_path: str) -> list[str]:
    """identities/roles/<role>/locale/<suffix>/locale.json: what the
    locale search tool fixes for a login of that suffix — an IANA
    timezone and one block per engine (serpapi, brave; at least one), each
    with the parameters that engine takes, the tool's description and,
    optionally, the engine's label — both in the locale, since their
    reader is the holder; no vendor's name reaches it."""
    out: list[str] = []
    base = os.path.join(role_path, LOCALE_DIRNAME)
    if not os.path.isdir(base):
        return out
    for suffix in sorted(os.listdir(base)):
        path = os.path.join(base, suffix, "locale.json")
        if not os.path.isfile(path):
            continue
        rel = f"identities/roles/{role}/{LOCALE_DIRNAME}/{suffix}/locale.json"
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError) as exc:
            out.append(f"{rel}: not JSON ({exc})")
            continue
        if not isinstance(data, dict):
            out.append(f"{rel}: not an object")
            continue
        source = data.get("tag") == SOURCE_TAG

        def in_locale(text: str) -> bool:
            return source or _is_mostly_non_latin(text)
        if source and data.get("reminder") is not None:
            out.append(f"{rel}: reminder in the source locale — it exists to keep a translator thinking in its locale")
        for key, pattern in LOCALE_FILE_RE.items():
            value = data.get(key)
            if not isinstance(value, str) or not pattern.match(value):
                out.append(f"{rel}: {key} {value!r} does not match {pattern.pattern}")
        reminder = data.get("reminder")
        if reminder is not None:
            if not isinstance(reminder, str) or not reminder.strip():
                out.append(f"{rel}: reminder {reminder!r} — a non-empty line, or absent")
            elif not in_locale(reminder):
                out.append(f"{rel}: reminder {reminder!r} is not in the locale — it exists to be read in the locale")
        engines = [e for e in LOCALE_ENGINES if e in data]
        if not engines:
            out.append(f"{rel}: no engine block (serpapi, brave) — the tool would have nothing to search with")
        for engine in engines:
            block = data[engine]
            if not isinstance(block, dict):
                out.append(f"{rel}: {engine} is not an object")
                continue
            required, optional = LOCALE_ENGINES[engine]
            for key, pattern in required.items():
                value = block.get(key)
                if not isinstance(value, str) or not pattern.match(value):
                    out.append(f"{rel}: {engine}.{key} {value!r} does not match {pattern.pattern}")
            for key, pattern in optional.items():
                if key in block and (not isinstance(block[key], str) or not pattern.match(block[key])):
                    out.append(f"{rel}: {engine}.{key} {block[key]!r} does not match {pattern.pattern}")
            desc = block.get("tool_description")
            if not isinstance(desc, str) or not desc.strip():
                out.append(f"{rel}: {engine}.tool_description missing — the holder reads it")
            elif not in_locale(desc):
                out.append(f"{rel}: {engine}.tool_description is not in the locale — its reader is the holder, who reasons in the locale")
            label = block.get("label")
            if label is not None and (not isinstance(label, str) or not label.strip() or not in_locale(label)):
                out.append(f"{rel}: {engine}.label {label!r} — the name the holder sees for the engine, in the locale")
            extra = sorted(set(block) - set(required) - set(optional) - {"tool_description", "label"})
            if extra:
                out.append(f"{rel}: {engine}: unknown field(s) {extra}; the search tool reads none of them")
        extra = sorted(set(data) - set(LOCALE_FILE_RE) - set(LOCALE_ENGINES) - set(LOCALE_FILE_OPTIONAL))
        if extra:
            out.append(f"{rel}: unknown field(s) {extra}; the search tool reads none of them")
    return out


# THE TOOL DICTIONARIES (communication/gzcoord/i18n/README.md, which
# states the house i18n standard and cites it): one flat key -> string
# JSON file per locale, named for the locale's tag, values non-empty,
# `{name}` interpolation, every active locale COMPLETE against the default.
# Completeness is enforced here, before the file lands, because the
# runtime fallback exists so a session start never fails — not so a
# missing key can be shipped.
I18N_DEFAULT_REL = os.path.join("communication", "gzcoord", "i18n", "en-US.json")


I18N_SCHEMA_REL = os.path.join("communication", "gzcoord", "i18n", "i18n.schema.json")


def _i18n_key_re() -> "tuple[re.Pattern[str] | None, str | None]":
    """The key shape, from the schema that states it, or why it could not
    be read. Read rather than restated: the rule had three copies (the
    schema, here, the node suite) and only two could fail, which is how a
    recorded contract drifts from the code. No fallback pattern — a
    default here would BE the third copy, and it would be the branch the
    suite runs while the read path went untested (re-review F-A)."""
    path = os.path.join(layout.FABRIC_ROOT, I18N_SCHEMA_REL)
    try:
        with open(path, encoding="utf-8") as fh:
            return re.compile(json.load(fh)["propertyNames"]["pattern"]), None
    except OSError:
        return None, f"{I18N_SCHEMA_REL}: the key shape is stated here and nothing else states it; it cannot be read"
    except Exception as exc:
        # Deliberately every other failure, not a named few: re.error is
        # not a ValueError, and a schema that is an array raises TypeError
        # — both used to leave lint as a traceback rather than a finding
        # (re-review Finding 2).
        return None, f"{I18N_SCHEMA_REL}: no usable propertyNames.pattern to hold a dictionary's keys to ({exc})"


# Identifiers a dictionary value keeps byte-identical, beyond the ones
# every translation keeps (PROTECTED_PATTERNS). These are the shapes a
# LINE carries and a prompt does not: a long flag, the protocol marker, a
# SPEC reference, the tool's own tag, and the word a reader types after
# --replay. Kept separate so a prompt translation is judged by the rules
# it was written under and gains no new finding from this.
# Every C0 (LF and TAB included), DEL, the C1 block a terminal reads as
# escape introducers, the two Unicode line separators, and the bidi
# overrides and isolates. LF is the one that matters most: a value
# carrying one prints a second line into the reading session's context,
# indistinguishable from a line the tool itself wrote (re-review Finding
# 1). Every line the tools print is one line; nothing in the corpus needs
# an exemption.
I18N_CONTROL_RE = re.compile("[\x00-\x1f\x7f-\x9f\u2028\u2029\u202a-\u202e\u2066-\u2069]")


I18N_EXTRA_PATTERNS: tuple[tuple[str, "re.Pattern[str]"], ...] = (
    ("long flag", re.compile(r"(?<!\S)--[a-z][a-z0-9-]*")),
    ("protocol marker", re.compile(r"\bGZCOORD/\d+\b")),
    ("spec reference", re.compile(r"§\s?\d+(?:\.\d+)?")),
    ("wire word", re.compile(r"\b(?:gzcoord|seq)\b")),
    ("env file", re.compile(r"\b[a-z][\w-]*\.env\b")),
)


def i18n_default_dictionary_findings() -> list[str]:
    """communication/gzcoord/i18n/en-US.json, held to the schema that
    states the key shape. Called once for the tree: the default is one
    file at a fixed path, and checking it inside the per-role walk made
    it conditional on some role owning a locale/ directory and duplicated
    when two did (re-review F-B)."""
    out: list[str] = []
    # A tree that ships no dictionaries at all — an assembler fixture, a
    # checkout without the tools — is asked nothing. That is the ONE
    # gate; inside a tree that has the directory, the schema is judged
    # before the default dictionary and regardless of it, because it
    # states the key shape for every dictionary and a missing default is
    # not an answer about the schema (re-review Finding 2).
    if not os.path.isdir(os.path.join(layout.FABRIC_ROOT, os.path.dirname(I18N_DEFAULT_REL))):
        return out
    key_re, why = _i18n_key_re()
    if why:
        out.append(why)
    default_path = os.path.join(layout.FABRIC_ROOT, I18N_DEFAULT_REL)
    if not os.path.isfile(default_path):
        return out
    try:
        with open(default_path, encoding="utf-8") as fh:
            default = json.load(fh)
    except ValueError as exc:
        out.append(f"{I18N_DEFAULT_REL}: the default locale is not JSON ({exc}) — every dictionary is judged against it")
        return out
    for key in sorted(default):
        if key_re and not key_re.match(key):
            out.append(f"{I18N_DEFAULT_REL}: key {key!r} is not a dotted slug")
        if not isinstance(default[key], str) or not default[key]:
            out.append(f"{I18N_DEFAULT_REL}: {key} is {default[key]!r} — a value is a non-empty string")
        elif I18N_CONTROL_RE.search(default[key]):
            out.append(f"{I18N_DEFAULT_REL}: {key} carries a control character — a line is printed into a session's context")
    return out


def i18n_dictionary_findings(role: str, role_path: str) -> list[str]:
    """identities/roles/<role>/locale/<suffix>/<tag>.json: the GZCoord
    tools' lines in that locale. The shape is the house standard's; the
    key set is the default locale's, exactly, in both directions; every
    identifier inside a value survives; and a dictionary with no
    non-Latin value at all is a copy of the English, not a translation."""
    out: list[str] = []
    base = os.path.join(role_path, LOCALE_DIRNAME)
    if not os.path.isdir(base):
        return out
    default_path = os.path.join(layout.FABRIC_ROOT, I18N_DEFAULT_REL)
    if not os.path.isfile(default_path):
        return out
    try:
        with open(default_path, encoding="utf-8") as fh:
            default = json.load(fh)
    except ValueError:
        return out      # named once, by i18n_default_dictionary_findings
    # Once for the walk, not once per locale directory.
    key_re, _why = _i18n_key_re()
    for suffix in sorted(os.listdir(base)):
        locale_file = os.path.join(base, suffix, "locale.json")
        try:
            with open(locale_file, encoding="utf-8") as fh:
                tag = json.load(fh).get("tag")
        except (OSError, ValueError):
            continue        # locale_file_findings already names it
        if not isinstance(tag, str) or not tag:
            continue
        path = os.path.join(base, suffix, f"{tag}.json")
        rel = f"identities/roles/{role}/{LOCALE_DIRNAME}/{suffix}/{tag}.json"
        if not os.path.isfile(path):
            continue        # not an active locale: the default is served
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError) as exc:
            out.append(f"{rel}: not JSON ({exc})")
            continue
        if not isinstance(data, dict):
            out.append(f"{rel}: not an object — a dictionary is flat key -> string")
            continue
        missing = sorted(set(default) - set(data))
        extra = sorted(set(data) - set(default))
        if missing:
            out.append(f"{rel}: {len(missing)} key(s) of {I18N_DEFAULT_REL} missing, first {missing[:3]} "
                       "— an active locale is complete against the default")
        if extra:
            out.append(f"{rel}: key(s) {extra[:3]} are not in {I18N_DEFAULT_REL}; nothing prints them")
        # Over every key the file carries, not only the ones the default
        # also has: a key checked on the intersection alone can only fire
        # when en-US.json is itself malformed (blind review F6 on PR #28).
        for key in sorted(data):
            if key_re and not key_re.match(key):
                out.append(f"{rel}: key {key!r} is not a dotted slug")
        for key in sorted(set(data) & set(default)):
            value = data[key]
            if not isinstance(value, str) or not value:
                out.append(f"{rel}: {key} is {value!r} — a value is a non-empty string")
                continue
            if I18N_CONTROL_RE.search(value):
                out.append(f"{rel}: {key} carries a control character — a line is printed into a session's context")
            out += protected_token_findings(rel, default[key], value, extra=I18N_EXTRA_PATTERNS)
        values = [v for v in data.values() if isinstance(v, str)]
        if values and not any(_is_mostly_non_latin(v) for v in values):
            out.append(f"{rel}: no value is in the locale — this is the default locale copied, not translated")
    return out


def locale_alignment_findings(role: str, role_path: str) -> list[str]:
    """Every locale of a role carries every artifact another locale of it
    has: a translated prompt piece, the worker, the tools' dictionary.
    Translations are requested of every locale together (the owner,
    2026-10-07): ge had no dictionary while ru had one, and nothing said
    so — a missing dictionary reads as "not an active locale", and a
    Georgian session saw the tools in English. The dictionary is compared
    by its role, not its name, since each is named by its own tag."""
    out: list[str] = []
    base = os.path.join(role_path, LOCALE_DIRNAME)
    if not os.path.isdir(base):
        return out
    held: dict[str, set[str]] = {}
    for suffix in sorted(os.listdir(base)):
        d = os.path.join(base, suffix)
        if not os.path.isdir(d):
            continue
        if _locale_tag(d) == SOURCE_TAG:
            # The source locale translates nothing: it carries locale.json
            # alone, and nothing else is asked of it or of the others for it.
            extra = sorted(n for n in os.listdir(d) if n != "locale.json")
            if extra:
                out.append(f"identities/roles/{role}/{LOCALE_DIRNAME}/{suffix}/: {', '.join(extra)} in the source "
                           f"locale ({SOURCE_TAG}) — it translates nothing; locale.json alone")
            continue
        try:
            with open(os.path.join(d, "locale.json"), encoding="utf-8") as fh:
                tag = json.load(fh).get("tag")
        except (OSError, ValueError):
            tag = None      # locale_file_findings names it
        held[suffix] = {"<the tools' dictionary, <tag>.json>" if tag and name == f"{tag}.json" else name
                        for name in os.listdir(d) if os.path.isfile(os.path.join(d, name))}
    every = set().union(*held.values()) if held else set()
    for suffix, names in held.items():
        for missing in sorted(every - names):
            others = sorted(s for s, n in held.items() if missing in n)
            out.append(f"identities/roles/{role}/{LOCALE_DIRNAME}/{suffix}/: no {missing}, which "
                       f"{', '.join(others)} {'has' if len(others) == 1 else 'have'} — a translation is requested of "
                       "every locale together and kept aligned")
    return out
