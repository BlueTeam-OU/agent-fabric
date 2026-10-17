"""tools/fabric/addenda_check.py — the validator of a holder's addenda (agent-fabric ADR-060 §5 rules 1, 6 and 9).

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

holder.json: the role-holder schema is not written yet; until it is, the
contract here is an object with `locale` (a short lowercase tag,
required), `timezone` (an IANA name) and `search.country` (two letters),
the last two optional, and no other key.
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
COUNTRY_RE = re.compile(r"[A-Za-z]{2}")
KEY_LINE_RE = re.compile(r"([a-z_]+): ?(.*)")

# A pin makes the addendum choose the model a launch routes (ADR-006).
MODEL_PIN_PATTERNS = (
    re.compile(r"\bclaude-[a-z0-9.-]+", re.I),
    re.compile(r"\b(?:opus|sonnet|haiku|fable)[ -]?\d", re.I),
    re.compile(r"\b(?:anthropic|openai|google|deepseek|meta-llama|mistralai|qwen|x-ai|moonshotai)/[\w.:-]+", re.I),
    re.compile(r"\b(?:gpt|gemini|deepseek|qwen|llama|mistral|grok|kimi)-?[\w.-]*\d", re.I),
)
PLACEHOLDER_RE = re.compile(r"\{[A-Za-z_][A-Za-z0-9_]*\}")
INCLUDE_RES = (
    re.compile(r"^[ \t]*@\S", re.M),                       # Claude Code's @file include
    re.compile(r"\{\{|\{%|<%"),                            # template tags
    re.compile(r"^[ \t]*(?:#include|!include|<!--\s*include)\b", re.M | re.I),
)
LINK_RE = re.compile(r"!?\[[^\]\n]*\]\(\s*<?([^)\s>]*)")
REF_DEF_RE = re.compile(r"^[ \t]{0,3}\[[^\]\n]+\]:[ \t]*<?(\S+)", re.M)
WIKILINK_RE = re.compile(r"\[\[[^\]\n]+\]\]")
URL_SCHEME_RE = re.compile(r"(?:https?|mailto):", re.I)


def body_digest(text: str) -> str:
    return "sha256:" + hashlib.sha256(FRONTMATTER_RE.sub("", text).encode("utf-8")).hexdigest()


def validate(role: str, aid: str, name: str, raw: bytes) -> list[str]:
    if name not in ALLOWED_NAMES:
        return [f"{name}: not an allowed file name (allowed: {', '.join(ALLOWED_NAMES)})"]
    text, findings = _decode(name, raw)
    if text is None:
        return findings
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
    return out


def _decode(name: str, raw: bytes) -> tuple[str | None, list[str]]:
    if raw.startswith(b"\xef\xbb\xbf"):
        return None, [f"{name}: begins with a byte order mark"]
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as err:
        return None, [f"{name}: not valid UTF-8 (byte {err.start})"]
    findings = []
    if "\r" in text:
        findings.append(f"{name}: carriage return (LF line endings only)")
    if len(text) > MAX_CHARS:
        findings.append(f"{name}: {len(text)} characters, the limit is {MAX_CHARS}")
    return text, findings


def _hygiene(name: str, text: str) -> list[str]:
    return [f"{name}: credential hygiene: {label}" for pattern, label, _ in layout.load_hygiene_patterns()
            if pattern.search(text)]


def _model_pins(name: str, text: str) -> list[str]:
    if any(p.search(text) for p in MODEL_PIN_PATTERNS):
        return [f"{name}: names a model (routing chooses the model, not an addendum)"]
    return []


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
            problems.append(f"frontmatter key {key} twice")
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
        findings.append(f"{name}: frontmatter has keys outside {', '.join(sorted(keys))}: {', '.join(extra)}")
    want_class = name.split(".")[0]
    for key, want in (("class", want_class), ("role", role), ("agent_id", aid)):
        if key in fields and fields[key] != want:
            findings.append(f"{name}: {key} is {fields[key]!r}, expected {want!r}")
    if "lang" in fields:
        if is_gloss and fields["lang"] != "en":
            findings.append(f"{name}: lang of a gloss is en, not {fields['lang']!r}")
        elif not LOCALE_RE.fullmatch(fields["lang"]):
            findings.append(f"{name}: lang {fields['lang']!r} is not a short lowercase language tag")
    for key in ("against_digest", "glosses_digest"):
        if key in fields and not DIGEST_RE.fullmatch(fields[key]):
            findings.append(f"{name}: {key} is not sha256:<64 lowercase hex digits>")
    body = FRONTMATTER_RE.sub("", text)
    if PLACEHOLDER_RE.search(body):
        findings.append(f"{name}: a {{placeholder}} (an addendum is rendered as written)")
    if any(r.search(body) for r in INCLUDE_RES):
        findings.append(f"{name}: an include or a template tag")
    targets = LINK_RE.findall(body) + REF_DEF_RE.findall(body)
    if WIKILINK_RE.search(body) or any(not URL_SCHEME_RE.match(t) for t in targets):
        findings.append(f"{name}: a link to a file (only http(s) and mailto links are allowed)")
    return findings


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
        findings.append(f"{name}: key {key!r} is not one of {', '.join(sorted(HOLDER_KEYS))}")
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
            findings.append(f"{name}: search.country is not two letters")
    return findings


def _is_iana(value: object) -> bool:
    zones = zoneinfo.available_timezones()
    if not zones:
        # No tz database on this host: every name would read as unknown, and
        # unknown must not become "invalid" (or "valid") by default.
        raise RuntimeError("no IANA time zone database on this host (install tzdata)")
    return isinstance(value, str) and value in zones
