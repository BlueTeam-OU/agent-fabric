"""tools/fabric/lint_rules/prompts.py — the prompt budgets and the protected tokens a translation must keep, the harness budget and the locale source digests.
A part of tools/fabric/lint.py, the entry point."""
from __future__ import annotations

import collections
import hashlib
import os
import re

from .base import FRONTMATTER_RE, layout
from .docs import HARNESS_SOURCE, hygiene_findings


BUDGET_TOKENS = 1800


CHARS_PER_TOKEN = 4


# A body written mostly in a non-Latin script tokenizes worse than the flat
# four-characters-a-token estimate. Measured on the first Georgian charter
# (docs/live-checks/2026-09-17-language-culture-bridge.md): 11 041
# characters cost 7 584 tokens — 1.46 a token, against 4.1 for the English
# body it renders — so a full rendering is about three times the tokens
# of its source. That is the cost the CEO accepted for the role; a locale
# charter is budgeted at LOCALE_BUDGET_FACTOR times the tier-1 budget,
# with the measured divisor, so a faithful rendering passes and a padded
# one does not. The guess before the measurement was 2 a token and 1.35
# times the budget, which no full rendering could meet.
NON_LATIN_CHARS_PER_TOKEN = 1.5


WARNINGS: list[str] = []   # named, not failing: a translation lagging its source (see locale_translation_findings)


# The locale worker's one tool: inert, so the harness spawns it and it reads nothing.
WORKER_TOOL = "TaskStop"


LOCALE_BUDGET_FACTOR = 3


TIER1_BUDGET_TOKENS = 3000


# How far over its budget a slice may run before lint refuses it; the
# memory-write check applies the same factor to one memory's section.
BUDGET_TOLERANCE = 1.35


# identities/roles/<role>/locale/<suffix>/: a locale's translation of the
# charter and the locale's worker prompt — authored files with their own
# rules (locale_translation_findings, locale_worker_findings), skipped by
# the generic slice walk like payload is.
LOCALE_DIRNAME = "locale"


def prompt_template_findings() -> list[str]:
    """The sections every launch prompt appends after the role's own files
    (tools/fabric/launch_prompt.py): each must exist, carry `{role}` so it
    is rendered for a role rather than read generically, pass hygiene, and
    the set must fit its budget — every session pays for these bytes."""
    findings: list[str] = []
    total = 0
    for name, placeholders in layout.PROMPT_TEMPLATE_PLACEHOLDERS.items():
        path = layout.prompt_template_path(name)
        rel = os.path.join(layout.PROMPT_DIR_NAME, name)
        if not os.path.isfile(path):
            findings.append(f"{rel}: missing — every launch prompt renders it")
            continue
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        if not text.strip():
            findings.append(f"{rel}: empty")
        for placeholder in placeholders:
            if placeholder not in text:
                findings.append(f"{rel}: no {placeholder} placeholder — it would read the same for every login")
        findings += hygiene_findings(rel, text)
        total += len(text)
    approx = total // CHARS_PER_TOKEN
    if approx > layout.PROMPT_TEMPLATE_BUDGET_TOKENS:
        findings.append(f"{layout.PROMPT_DIR_NAME}: ~{approx} tokens across {', '.join(layout.PROMPT_TEMPLATE_PLACEHOLDERS)} "
                        f"exceeds the {layout.PROMPT_TEMPLATE_BUDGET_TOKENS} budget every session pays")
    return findings


PLACEHOLDER_RE = re.compile(r"\{[a-z_]+\}")


def _is_mostly_non_latin(text: str) -> bool:
    """True when at least half the letters of `text` are outside the Latin
    range — a body written in Georgian, Cyrillic, Arabic, CJK …

    A `{placeholder}` is stripped first: its name is an identifier the
    translation must keep byte-identical, so counting it as Latin letters
    made a real translation read as English. "ᲨᲔᲛᲝᲡᲣᲚᲘ {who}: {mine}/
    {others}, {channel}" is eight Georgian letters against twenty Latin
    ones (a blind review hit this building a fixture)."""
    letters = [ch for ch in PLACEHOLDER_RE.sub(" ", text) if ch.isalpha()]
    if not letters:
        return False
    non_latin = sum(1 for ch in letters if ord(ch) > 0x024F)
    return non_latin * 2 >= len(letters)


def _source_digest(path: str) -> str:
    """sha256 over an authored file's BODY (frontmatter stripped), the digest
    a translation records in `translates.digest`."""
    with open(path, encoding="utf-8") as fh:
        body = FRONTMATTER_RE.sub("", fh.read())
    return "sha256:" + hashlib.sha256(body.encode("utf-8")).hexdigest()


# THE PROTECTED TOKENS. A translated prompt may reword every sentence
# and must keep byte-identical every literal the harness or a reader
# matches by name: tool and skill names in backticks, slash commands,
# paths, UPPER_SNAKE names, model ids, tags such as <system-reminder>,
# [[links]], dotted file names, the fenced frontmatter example, and the
# {placeholders} the renderer fills. Read back from the docs and a live
# session on 2026-09-17: a tool is dispatched by its name against the
# schemas the harness sends beside the prompt, never by prose — so prose
# is free and identifiers are the whole risk. Each category is its own
# pattern so a finding names which kind moved; a translation keeps every
# token the same number of times as its source.
PROTECTED_PATTERNS: tuple[tuple[str, "re.Pattern[str]"], ...] = (
    ("fenced block", re.compile(r"```[\s\S]*?```")),
    ("backticked span", re.compile(r"`[^`]{1,200}`")),   # may wrap a line; whitespace inside is normalised
    # ASCII words joined by dashes: an inflected locale glues a suffix to a
    # name with a dash ("/fast-ით", the ge holder, 2026-09-17), and the
    # suffix is prose, not part of the command or the path.
    ("slash command", re.compile(r"(?<!\S)/[A-Za-z][A-Za-z0-9_]*(?:-[A-Za-z0-9_]+)*")),
    ("path", re.compile(r"~?/[A-Za-z0-9_.~]+(?:-[A-Za-z0-9_.~]+)*(?:/[A-Za-z0-9_.~]+(?:-[A-Za-z0-9_.~]+)*)+")),
    # A name with an underscore, or a short acronym (CLI, CTF, IDE); an
    # emphasised word (IMPORTANT) is prose and free.
    ("UPPER_SNAKE name", re.compile(r"\b(?:[A-Z][A-Z0-9]*_[A-Z0-9_]+|[A-Z]{2,4})\b")),
    # The harness's tool names as the text quotes them, backticked or not
    # (Skill, Agent, ToolSearch("select:EndConversation")): a reader's cue
    # to a name the harness matches; CamelCase covers the rest.
    ("tool name", re.compile(r"\b(?:Agent|Artifact|AskUserQuestion|Bash|Edit|Glob|Grep|Read|Skill|ToolSearch|Write|WebFetch|WebSearch|Workflow|Monitor|NotebookEdit|SendMessage|TaskStop|EndConversation|SubagentHandback)\b|\b[A-Z][a-z]+(?:[A-Z][a-z]+)+\b")),
    ("model id", re.compile(r"\bclaude-[a-z0-9.-]+\b")),
    ("tag", re.compile(r"<[A-Za-z][\w-]*>")),
    ("[[link]]", re.compile(r"\[\[[^\]]+\]\]")),
    ("file name", re.compile(r"\b[A-Za-z][\w-]*\.(?:md|json|py|sh|mjs)\b")),
    ("placeholder", re.compile(r"\{[a-z_]+\}")),
)


def _protected_tokens(text: str, extra: tuple[tuple[str, "re.Pattern[str]"], ...] = ()) -> "collections.Counter[tuple[str, str]]":
    """Every protected token of `text` with its category, counted. A fenced
    block is one token and its contents are not matched again; a
    backticked span likewise."""
    counts: "collections.Counter[tuple[str, str]]" = collections.Counter()
    rest = text
    for category, pattern in PROTECTED_PATTERNS[:2]:
        for m in pattern.findall(rest):
            counts[(category, re.sub(r"\s+", " ", m))] += 1   # a span wrapped at another column is the same span
        rest = pattern.sub(" ", rest)
    for category, pattern in PROTECTED_PATTERNS[2:] + extra:
        for m in pattern.findall(rest):
            counts[(category, m)] += 1
    return counts


def protected_token_findings(rel: str, source_body: str, translation_body: str,
                            extra: tuple[tuple[str, "re.Pattern[str]"], ...] = ()) -> list[str]:
    """One finding per protected token whose count differs between the
    English source and the translation, naming the category and both counts."""
    want, got = _protected_tokens(source_body, extra), _protected_tokens(translation_body, extra)
    out: list[str] = []
    for key in sorted(set(want) | set(got)):
        if want[key] != got[key]:
            category, token = key
            shown = token if len(token) <= 60 else token[:57] + "..."
            out.append(f"{rel}: {category} {shown!r} appears {got[key]} time(s), {want[key]} in the source — "
                       "an identifier the harness or a reader matches by name stays byte-identical")
    return out


# THE TRANSLATIONS a locale may carry under identities/roles/<role>/locale/
# /<suffix>/: each names its English source and the digest of the source's
# body; a digest that no longer matches is the lag finding — the
# translation is still served (a launch never fails on a day's lag), and
# this is where the lag is seen. The class a translation declares, the
# schema it must pass (the charter's), and its budget — the measured
# non-Latin divisor against LOCALE_BUDGET_FACTOR times the source's budget,
# or a flat cap for the harness text (measured ~7 700 tokens in Georgian).
HARNESS_BUDGET_TOKENS = 9000


LOCALE_TRANSLATIONS: dict[str, tuple[str, str, str, bool]] = {
    # name: (source path with {role}, class the translation declares, budget key, schema-validated)
    "header": (os.path.join(layout.PROMPT_DIR_NAME, "header.md"), "prompt-translation", "template", False),
    "brief-missing": (os.path.join(layout.PROMPT_DIR_NAME, "brief-missing.md"), "prompt-translation", "template", False),
    "team": (os.path.join(layout.PROMPT_DIR_NAME, "team.md"), "prompt-translation", "template", False),
    "memory": (os.path.join(layout.PROMPT_DIR_NAME, "memory.md"), "prompt-translation", "template", False),
    "charter": ("identities/roles/{role}/charter.md", "charter", "tier1", True),
    "brief": ("identities/roles/{role}/brief.md", "brief", "tier1", True),
    "harness": (HARNESS_SOURCE, "harness-translation", "harness", False),
}


def _locale_budget(key: str) -> int:
    if key == "harness":
        return HARNESS_BUDGET_TOKENS
    if key == "template":
        return layout.PROMPT_TEMPLATE_BUDGET_TOKENS * LOCALE_BUDGET_FACTOR
    return TIER1_BUDGET_TOKENS * LOCALE_BUDGET_FACTOR
