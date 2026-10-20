"""tools/fabric/addenda_check.py — the validator of a holder's addenda (ADR-060 of the holder-addenda plan, §5 rules 1, 6 and 9).

A holder's specialization of role R is `settings/roles/R/` in the agent's
store: `charter-addendum.md`, `brief-addendum.md`, `holder.json`, and an
English gloss beside an addendum written in another language,
`charter-addendum.gloss.en.md` / `brief-addendum.gloss.en.md`. This module
says whether one file, or the whole set, may be installed or rendered. The
install command, the launcher's loader and the lint rule over the
coordinator's mirrors all call it, so it imports no lint and writes nothing.

>>> contract
    validate(role, aid, name, raw) -> list[str]
        `name` is the file name inside settings/roles/<role>/, `raw` its
        bytes, `aid` the store's .agent-id. The findings, one line each;
        empty means valid. A finding never quotes the text (a credential
        hit must not be echoed into a log).
    validate_set(role, aid, files) -> dict[str, list[str]]
        `files` maps a name to its bytes. Every file's findings, plus what
        only a set shows: a gloss whose glosses_digest is not the body
        digest of the addendum it glosses, or that glosses no addendum.
    body_digest(text) -> str
        sha256:<hex> over the text with its frontmatter removed, the rule
        of lint_rules/prompts.py _source_digest.
<<< contract

THE FRONTMATTER is `---` / `key: value` lines / `---`, scalars only, and
the keys are exactly:
  an addendum  class, role, agent_id, lang, against_digest
  a gloss      class, role, agent_id, lang (= en), glosses_digest
`class` is charter-addendum or brief-addendum and agrees with the file
name; a gloss carries the class of the addendum it glosses. A digest is
`sha256:` and 64 lowercase hex digits. Whether against_digest names the
current shared piece is a warning at render (rule 6), not a validity
matter, and is not checked here.

THE SIZE is counted in characters of the whole file (rule 6), a gloss
included: it is never rendered, but it sits in the store.

HYGIENE: layout.load_hygiene_patterns raises HygieneError for a list it
cannot read, and that propagates: a validator that cannot tell a leak
from a clean text must not say "valid".

holder.json: identities/schemas/role-holder.schema.json is the shape: an
object with `locale` (a short lowercase tag, required), `timezone` (an IANA
name) and `search.country` (two lowercase letters), the last two optional,
and no other key. The checks below are written by hand so the module needs
nothing but the standard library; where `jsonschema` is importable and the
schema file is there, the schema is applied as well (a drift between the two
is a finding, never a reason to skip a hand check), and a finding names the
path and the rule, never the value.

    frontmatter(text) -> dict[str, str]
        The fields `validate` reads, by the same parser: the one reader of an
        addendum's frontmatter (against_digest included), so what install
        accepts, render reads the same way.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import zoneinfo

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import hidden_unicode  # noqa: E402
import layout  # noqa: E402

MAX_CHARS = 4000
CLASSES = ("charter-addendum", "brief-addendum")
HOLDER_FILE = "holder.json"
ADDENDUM_NAMES = tuple(c + ".md" for c in CLASSES)
GLOSS_NAMES = tuple(c + ".gloss.en.md" for c in CLASSES)
ALLOWED_NAMES = ADDENDUM_NAMES + GLOSS_NAMES + (HOLDER_FILE,)

ADDENDUM_KEYS = {"class", "role", "agent_id", "lang", "against_digest"}
GLOSS_KEYS = {"class", "role", "agent_id", "lang", "glosses_digest"}
HOLDER_KEYS = {"locale", "timezone", "search"}

# Same rule as lint_rules/prompts.py FRONTMATTER_RE: a block at the very
# start, closed by a line of its own; the body is whatever follows.
FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n", re.S)
DIGEST_RE = re.compile(r"sha256:[0-9a-f]{64}")
LOCALE_RE = re.compile(r"[a-z]{2,3}(?:-[a-z0-9]{2,8})*")
COUNTRY_RE = re.compile(r"[a-z]{2}")
KEY_LINE_RE = re.compile(r"([a-z_]+): (.*)")

# A pin makes the addendum choose the model a launch routes (ADR-006).
MODEL_PIN_PATTERNS = (
    re.compile(r"\bclaude-(?:opus|sonnet|haiku|fable|instant|\d)", re.I),
    re.compile(r"\b(?:opus|sonnet|haiku|fable)[ -]?\d", re.I),
    re.compile(r"\b(?:anthropic|openai|google|deepseek|meta-llama|mistralai|qwen|x-ai|moonshotai)/[\w.:-]+", re.I),
    re.compile(r"\b(?:gpt|gemini|deepseek|qwen|llama|mistral|grok|kimi)-?[\w.-]*\d", re.I),
)
PLACEHOLDER_RE = re.compile(r"\{[A-Za-z_][A-Za-z0-9_]*\}")
INCLUDE_RES = (
    re.compile(r"^[ \t]*@\S", re.M),                       # Claude Code's @file include
    re.compile(r"\{\{|\{%"),                                # template tags
    re.compile(r"^[ \t]*(?:#include|!include|<!--\s*include)\b", re.M | re.I),
)
# Every "](" opens a destination, wherever its link text began: deriving the destination from the text needed a pattern
# in which a bracket could belong to two parts (exponential backtracking on a run of "[[]") or one that stopped at an
# inner "[" and missed a file link nested in another link's text. The lookahead matches at each "](" on its own, so
# captures overlap, and an unclosed destination cannot swallow the link after it. The destination stops at "]" as well
# as at ")": a destination that could run on through a run of "](" would be rescanned from each of them (quadratic);
# with the stop each position costs a constant and the whole is linear. A reference
# definition's destination may start on the next line, and a footnote label ([^1]) is no link. Autolinks and raw
# HTML href/src are links too.
LINK_RE = re.compile(r"(?=\]\(\s*<?([^)\s>\]]*))")
REF_DEF_RE = re.compile(r"^[ \t]{0,3}\[(?!\^)[^\]\n]+\]:\s*<?(\S+)", re.M)
AUTOLINK_RE = re.compile(r"<([A-Za-z][A-Za-z0-9+.-]*:[^>\s]*|[./][^>\s]*)>")
HTML_ATTR_RE = re.compile(r"\b(?:href|src)\s*=\s*[\"']?([^\"'\s>]*)", re.I)
# Unicode hyphens are folded before the model-pin patterns look.
HYPHENS = dict.fromkeys(range(0x2010, 0x2016), "-")
WIKILINK_RE = re.compile(r"\[\[[^\]\n]+\]\]")
URL_SCHEME_RE = re.compile(r"(?:https?:|mailto:|#)", re.I)


def body_digest(text: str) -> str:
    return "sha256:" + hashlib.sha256(FRONTMATTER_RE.sub("", text).encode("utf-8")).hexdigest()


def validate(role: str, aid: str, name: str, raw: bytes) -> list[str]:
    if name not in ALLOWED_NAMES:
        return [f"{name}: not an allowed file name (allowed: {', '.join(ALLOWED_NAMES)})"]
    text, findings = _decode(name, raw)
    if text is None or len(text) > MAX_CHARS:
        return findings   # the patterns below never run over more than the cap
    findings += _hygiene(name, text) + _model_pins(name, text)
    if name == HOLDER_FILE:
        return findings + _holder(name, text)
    return findings + _markdown(role, aid, name, text)


def validate_set(role: str, aid: str, files: dict[str, bytes]) -> dict[str, list[str]]:
    out = {name: validate(role, aid, name, raw) for name, raw in files.items()}
    for name in files:
        if name not in GLOSS_NAMES:
            continue
        target = name.replace(".gloss.en.md", ".md")
        if target not in files:
            out[name].append(f"{name}: glosses {target}, which is not in the set")
        elif not out[name] and not out[target]:
            # Both files decode and carry a well-formed digest here.
            gloss_digest = _frontmatter(files[name].decode("utf-8"))[0]["glosses_digest"]
            if gloss_digest != body_digest(files[target].decode("utf-8")):
                out[name].append(f"{name}: glosses_digest is not the body digest of {target} (stale gloss)")
    for target in ADDENDUM_NAMES:
        # Rule 1 allows a gloss only beside an addendum in another language, and rule 9 requires one there.
        if target not in files or out[target]:
            continue
        gloss = target.replace(".md", ".gloss.en.md")
        lang = _frontmatter(files[target].decode("utf-8"))[0]["lang"]
        if lang != "en" and gloss not in files:
            out[target].append(f"{target}: lang is not en, so it needs its English gloss {gloss}")
        if lang == "en" and gloss in files:
            out[gloss].append(f"{gloss}: glosses an addendum that is already in English")
    return out


def _decode(name: str, raw: bytes) -> tuple[str | None, list[str]]:
    if raw.startswith(b"\xef\xbb\xbf"):
        return None, [f"{name}: begins with a byte order mark"]
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as err:
        return None, [f"{name}: not valid UTF-8 (byte {err.start})"]
    if len(text) > MAX_CHARS:
        return text, [f"{name}: {len(text)} characters, the limit is {MAX_CHARS}"]   # no pattern runs over more than the cap
    findings = []
    if "\r" in text:
        findings.append(f"{name}: carriage return (LF line endings only)")
    # What a reader or an auditor of the gloss sees differs from what a model reads: hidden_unicode owns the
    # classes. The BOM was refused on the bytes above, so none is allowed at offset 0 here either.
    hidden = hidden_unicode.scan(text, allow_bom=False)
    if hidden:
        first = hidden[0]
        findings.append(f"{name}: a control character, a line separator other than LF, a bidi override or a hidden "
                        f"format character (first: {first})")
    return text, findings


def _hygiene(name: str, text: str) -> list[str]:
    return [f"{name}: credential hygiene: {label}" for pattern, label, _ in layout.load_hygiene_patterns()
            if pattern.search(text)]


def _model_pins(name: str, text: str) -> list[str]:
    if any(p.search(text.translate(HYPHENS)) for p in MODEL_PIN_PATTERNS):
        return [f"{name}: names a model (routing chooses the model, not an addendum)"]
    return []


def frontmatter(text: str) -> dict[str, str]:
    return _frontmatter(text)[0]


def _frontmatter(text: str) -> tuple[dict[str, str], list[str]]:
    """(fields, problems); problems say what is not `key: value` scalars."""
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}, ["no frontmatter block at the start"]
    fields: dict[str, str] = {}
    problems = []
    for line in m.group(1).split("\n"):
        kv = KEY_LINE_RE.fullmatch(line)
        if not kv:
            problems.append("a frontmatter line that is not `key: value`")
            continue
        key, value = kv.group(1), kv.group(2).strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key in fields:
            problems.append("a frontmatter key twice")
        fields[key] = value
    return fields, problems


def _markdown(role: str, aid: str, name: str, text: str) -> list[str]:
    is_gloss = name in GLOSS_NAMES
    fields, problems = _frontmatter(text)
    findings = [f"{name}: {p}" for p in problems]
    keys = GLOSS_KEYS if is_gloss else ADDENDUM_KEYS
    missing, extra = sorted(keys - fields.keys()), sorted(fields.keys() - keys)
    if missing:
        findings.append(f"{name}: frontmatter lacks {', '.join(missing)}")
    if extra:
        findings.append(f"{name}: frontmatter has {len(extra)} key(s) outside {', '.join(sorted(keys))}")
    want_class = name.split(".")[0]
    for key, want in (("class", want_class), ("role", role), ("agent_id", aid)):
        if key in fields and fields[key] != want:
            findings.append(f"{name}: {key} is not the expected {want!r}")
    if "lang" in fields:
        if is_gloss and fields["lang"] != "en":
            findings.append(f"{name}: lang of a gloss is en")
        elif not LOCALE_RE.fullmatch(fields["lang"]):
            findings.append(f"{name}: lang is not a short lowercase language tag")
    for key in ("against_digest", "glosses_digest"):
        if key in fields and not DIGEST_RE.fullmatch(fields[key]):
            findings.append(f"{name}: {key} is not sha256:<64 lowercase hex digits>")
    body = FRONTMATTER_RE.sub("", text)
    if PLACEHOLDER_RE.search(body):
        findings.append(f"{name}: a {{placeholder}} (an addendum is rendered as written)")
    if any(r.search(body) for r in INCLUDE_RES):
        findings.append(f"{name}: an include or a template tag")
    targets = LINK_RE.findall(body) + REF_DEF_RE.findall(body) + AUTOLINK_RE.findall(body) + HTML_ATTR_RE.findall(body)
    if WIKILINK_RE.search(body) or any(not URL_SCHEME_RE.match(t) for t in targets):
        findings.append(f"{name}: a link to a file (only http(s) and mailto links are allowed)")
    return findings


SCHEMA_PATH = os.path.join(HERE, "..", "..", "identities", "schemas", "role-holder.schema.json")


def _schema_findings(name: str, data: object, schema_path: str | None = None) -> list[str]:
    """What the schema refuses; nothing where it cannot be applied (no jsonschema, no file): the hand checks stand alone."""
    try:
        import jsonschema
        with open(schema_path or SCHEMA_PATH, encoding="utf-8") as fh:
            schema = json.load(fh)
    except (ImportError, OSError):
        return []
    validator = jsonschema.Draft202012Validator(schema)
    return [f"{name}: the schema refuses {'/'.join(str(p) for p in err.absolute_path) or 'the object'} ({err.validator})"
            for err in sorted(validator.iter_errors(data), key=lambda e: list(map(str, e.absolute_path)))]


def _holder(name: str, text: str) -> list[str]:
    def no_duplicates(items):
        keys = [k for k, _ in items]
        if len(keys) != len(set(keys)):
            raise ValueError("a key twice")
        return dict(items)
    try:
        data = json.loads(text, object_pairs_hook=no_duplicates)
    except ValueError as err:
        return [f"{name}: not JSON ({err})"]
    if not isinstance(data, dict):
        return [f"{name}: not a JSON object"]
    findings = []
    if "locale" not in data:
        findings.append(f"{name}: lacks locale")
    for key in sorted(data.keys() - HOLDER_KEYS):
        findings.append(f"{name}: a key outside {', '.join(sorted(HOLDER_KEYS))}")
    locale = data.get("locale")
    if "locale" in data and not (isinstance(locale, str) and LOCALE_RE.fullmatch(locale)):
        findings.append(f"{name}: locale is not a short lowercase tag")
    if "timezone" in data and not _is_iana(data["timezone"]):
        findings.append(f"{name}: timezone is not an IANA name")
    if "search" in data:
        search = data["search"]
        if not isinstance(search, dict) or set(search) - {"country"}:
            findings.append(f"{name}: search is an object with country only")
        elif "country" in search and not (isinstance(search["country"], str) and COUNTRY_RE.fullmatch(search["country"])):
            findings.append(f"{name}: search.country is not two lowercase letters")
    return findings or _schema_findings(name, data)


def _is_iana(value: object) -> bool:
    zones = zoneinfo.available_timezones()
    if not zones:
        # No tz database on this host: every name would read as unknown, and
        # unknown must not become "invalid" (or "valid") by default.
        raise RuntimeError("no IANA time zone database on this host (install tzdata)")
    return isinstance(value, str) and value in zones
