#!/usr/bin/env python3
"""tools/fabric/lint.py

>>> help
Guard the committed corpus the way the contract validators guard the
wire surface.

    tools/fabric/lint.py                 # lints this agent-fabric checkout
    tools/fabric/lint.py --fabric PATH

The corpus is written by tools and read by sessions, so the failures
worth catching are the quiet ones: an index that no longer matches the
slices it points at, a slice that grew past what a session can afford to
load, provenance that points at nothing, or content that should never
have been committed at all.

Checks:
  schemas    the role catalogue, every project taxonomy, the routing
             profiles and every slice's frontmatter validate
  identity   every role directory is catalogued; charter, brief and recall
             are the only authored classes; payload is well-shaped
  index      every (project, role) index lists every slice the role has —
             its domain slices, its project slices, its charter and recall,
             its shared slices — and every index line resolves
  budgets    no slice exceeds its token budget
  shared     a shared slice really is shared (two or more owners)
  profiles   every review-grade gate in routing/profiles.json holds, and
             every role row names a catalogued role
  hygiene    no person's name (people by role: the CEO, the owner, an
             agent by its login — policies/hygiene.json), no city or
             country names, no external project names (each project's
             .agent-fabric/hygiene.json), no credentials, no non-English
             prose
  prompt     the launch-prompt sections (identities/prompt/) exist, carry
             the {role} placeholder, are hygiene-clean and within budget

Exit 0 clean, 1 on findings, 2 on usage error. Uses jsonschema when it is
importable and falls back to a built-in structural check otherwise, so a
clean machine can still run it.
<<< help
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
from collections import defaultdict
from typing import Any

_spec = importlib.util.spec_from_file_location(
    "fabric_layout", os.path.join(os.path.dirname(os.path.realpath(__file__)), "layout.py"))
layout = importlib.util.module_from_spec(_spec)
_wc_spec = importlib.util.spec_from_file_location(
    "fabric_workingcopy", os.path.join(os.path.dirname(os.path.realpath(__file__)), "workingcopy.py"))
workingcopy = importlib.util.module_from_spec(_wc_spec)
_spec.loader.exec_module(layout)
_wc_spec.loader.exec_module(workingcopy)

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
# identities/roles/<role>/locale/<suffix>/: a locale's translation of the
# charter and the locale's worker prompt — authored files with their own
# rules (locale_translation_findings, locale_worker_findings), skipped by
# the generic slice walk like payload is.
LOCALE_DIRNAME = "locale"

# The generic patterns plus every visible project's own list (its working
# copy's .agent-fabric/hygiene.json), loaded in main() once the working
# copies are known: layout.load_hygiene_patterns.
BANNED_PATTERNS: list = []

ITALIAN_MARKERS = re.compile(
    r"(?<![a-z])(perch[eé]|per[oò]|quindi|anche|questo|questa|quello|quella|"
    r"dovrebbe|bisogna|abbiamo|siamo|essere|molto|senza|nella|nelle|negli|"
    r"dello|della|delle|degli)(?![a-z])",
    re.I,
)

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.S)


PAYLOAD_DIRS = frozenset({"skills", "commands"})


# sibling_working_copies moved to workingcopy.py (2026-09-18): the
# assembler needs the same reach for the hygiene lists.
sibling_working_copies = workingcopy.sibling_working_copies

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


# runtime/claude-code/harness/en.md: the harness's own system prompt,
# captured from a live build, kept as the English source a locale
# translates (runtime/claude-code/harness/README.md). Fabric-wide, not a
# role's; absent in a fixture fabric, present in this one.
HARNESS_SOURCE = os.path.join("runtime", "claude-code", "harness", "en.md")
HARNESS_PLACEHOLDER = "{memory_dir}"


def adr_findings(root: str | None = None) -> list[str]:
    """docs/adr/: tools/fabric/adr.py's check, as lint findings (agent-fabric
    ADR-001). Absent in a fixture fabric that has no records, which is fine."""
    root = root or layout.FABRIC_ROOT
    if not os.path.isdir(os.path.join(root, "docs", "adr")):
        return []
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import adr  # noqa: E402 — a sibling module, loaded only when there are records
    return [f"adr: {f}" for f in adr.check(root)]


# A path to one of the fabric's own documents, cited from any tracked text
# file, must resolve — from the repository root or from the citing file's
# own directory: a moved relay-setup note left a dangling pointer in
# inbox.mjs for weeks, and nothing looked. Warnings while
# the documents move into decision records (agent-fabric ADR-001 §7); the
# evidence (live checks), the amendment history, knowledge slices (they
# cite what was true when written) and test fixtures are exempt.
# Where the fabric keeps documents: a note at docs/<name>.md, the decision
# records and the live checks, the policies, the protocol and its transports.
# A deeper docs/ path (docs/scratchpad/…) is a project's, named in an example.
DOC_PATH_RE = re.compile(r"(?<![\w/.-])((?:docs/(?:adr/(?:history/)?|live-checks/)?|policies/(?:[\w-]+/)?|communication/gzcoord/(?:protocol|docs)/)[A-Za-z0-9_.-]+\.md)(?![\w/-])")
FABRIC_ADR_RE = re.compile(r"agent-fabric ADR-(\d{3})(?!\d)")
DOC_PATH_EXEMPT = ("docs/live-checks/", "docs/adr/history/", "docs/adr/ADR-TEMPLATE.md", "memory/", ".agent-fabric/memory/", "tests/", "communication/gzcoord/history/")


def doc_path_findings(root: str | None = None) -> list[str]:
    root = root or layout.FABRIC_ROOT
    try:
        files = subprocess.run(["git", "-C", root, "ls-files"], capture_output=True, text=True, check=True).stdout.split()
    except (OSError, subprocess.CalledProcessError):
        return []
    adr_dir = os.path.join(root, "docs", "adr")
    numbers = {f[4:7] for f in os.listdir(adr_dir) if f.startswith("ADR-") and f[4:7].isdigit()} if os.path.isdir(adr_dir) else set()
    out: list[str] = []
    for rel in files:
        if rel.startswith(DOC_PATH_EXEMPT) or "/test_" in f"/{rel}" or "/tests/" in f"/{rel}":
            continue
        if not rel.endswith((".md", ".py", ".sh", ".mjs", ".js", ".json", ".service")) and "/" in rel and not rel.startswith("bin/"):
            continue
        try:
            with open(os.path.join(root, rel), encoding="utf-8") as fh:
                text = fh.read()
        except (OSError, UnicodeDecodeError):
            continue
        here = os.path.dirname(os.path.join(root, rel))
        for m in DOC_PATH_RE.finditer(text):
            target = m.group(1)
            if not (os.path.exists(os.path.join(root, target)) or os.path.exists(os.path.join(here, target))):
                out.append(f"{rel}: cites {target}, which does not exist")
        for m in FABRIC_ADR_RE.finditer(text):
            if m.group(1) not in numbers:
                out.append(f"{rel}: cites agent-fabric ADR-{m.group(1)}, which does not exist")
    return sorted(set(out))


def harness_source_findings(root: str | None = None) -> list[str]:
    """The capture's shape: frontmatter with its class, the build it was
    captured from, the date, and the live check it came from (which must
    exist — the capture is a claim about a build, and the live check is
    its evidence); the memory-directory placeholder exactly once; hygiene."""
    root = root or layout.FABRIC_ROOT   # at call time: --fabric may have moved it
    path = os.path.join(root, HARNESS_SOURCE)
    if not os.path.isfile(path):
        return []
    out: list[str] = []
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    meta = parse_frontmatter(text)
    if meta is None:
        return [f"{HARNESS_SOURCE}: no frontmatter — class, build, captured_at, source"]
    if meta.get("class") != "harness-source":
        out.append(f"{HARNESS_SOURCE}: class {meta.get('class')!r}; the capture is class harness-source")
    for key in ("build", "captured_at", "source"):
        if not meta.get(key):
            out.append(f"{HARNESS_SOURCE}: no `{key}` — the build it was captured from, when, and the live check that shows it")
    source = str(meta.get("source") or "")
    if source and (not source.startswith("docs/live-checks/") or not os.path.isfile(os.path.join(root, source))):
        out.append(f"{HARNESS_SOURCE}: source {source!r} is not an existing docs/live-checks/ note")
    body = FRONTMATTER_RE.sub("", text)
    n = body.count(HARNESS_PLACEHOLDER)
    if n != 1:
        out.append(f"{HARNESS_SOURCE}: {HARNESS_PLACEHOLDER} appears {n} time(s); the memory directory is the one login-specific span and must be the placeholder exactly once")
    out += hygiene_findings(HARNESS_SOURCE, body)
    return out


def hygiene_findings(where: str, text: str) -> list[str]:
    """Banned patterns and the language check — for slices AND payload.

    Payload is exempt from the slice judgements; it is never exempt from
    this. lint.py is the only CI pass over the corpus, and role.py copies
    payload verbatim into `.claude/` in every workspace that adopts the role, so
    this is the only thing between a pasted credential and every one of them.
    """
    out: list[str] = []
    for pattern, label, _refer_as in BANNED_PATTERNS:
        hit = pattern.search(text)
        if hit:
            out.append(f"{where}: {label} -- {hit.group(0)!r}")
    italian = {w.lower() for w in ITALIAN_MARKERS.findall(text)}
    if len(italian) >= 3:
        out.append(
            f"{where}: reads as non-English ({sorted(italian)[:5]}) — translate it"
        )
    return out


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
# en-US login has no such rule (communication/gzcoord/scripts/i18n.mjs).
LOCALE_FILE_OPTIONAL = ("reminder",)


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
        for key, pattern in LOCALE_FILE_RE.items():
            value = data.get(key)
            if not isinstance(value, str) or not pattern.match(value):
                out.append(f"{rel}: {key} {value!r} does not match {pattern.pattern}")
        reminder = data.get("reminder")
        if reminder is not None:
            if not isinstance(reminder, str) or not reminder.strip():
                out.append(f"{rel}: reminder {reminder!r} — a non-empty line, or absent")
            elif not _is_mostly_non_latin(reminder):
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
            elif not _is_mostly_non_latin(desc):
                out.append(f"{rel}: {engine}.tool_description is not in the locale — its reader is the holder, who reasons in the locale")
            label = block.get("label")
            if label is not None and (not isinstance(label, str) or not label.strip() or not _is_mostly_non_latin(label)):
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


FABRIC_REF_NAME = "fabric-ref"
FABRIC_REF_RE = re.compile(r"^[0-9a-f]{40}$")


def fabric_ref_findings(pid: str, wc: str) -> list[str]:
    """<working copy>/.agent-fabric/fabric-ref names the agent-fabric commit
    the project's indexes were assembled against — the one its CI checks
    out, so the fabric moving cannot turn the project's check red
    (memory/README.md, "Landing a drain"; 2026-09-18, after three reds in
    a day). Optional; when present it is one line, one full commit id."""
    path = os.path.join(wc, layout.PROJECT_DIRNAME, FABRIC_REF_NAME)
    if not os.path.isfile(path):
        return []
    where = f"{pid}:{layout.PROJECT_DIRNAME}/{FABRIC_REF_NAME}"
    try:
        text = open(path, encoding="utf-8").read()
    except OSError as e:
        return [f"{where}: unreadable ({e})"]
    lines = text.split("\n")
    if len(lines) != 2 or lines[1] != "":
        return [f"{where}: must be exactly one line ending in a newline"]
    if not FABRIC_REF_RE.match(lines[0]):
        return [f"{where}: {lines[0]!r} is not a full lowercase commit id (40 hex)"]
    return []


def payload_shape_findings(role: str, role_path: str) -> list[str]:
    """Assert what role.py can actually install, where it is authored.

    role.py installs a DIRECTORY under skills/ and a .md FILE under
    commands/, and skips anything else without a word. Exempting payload
    from the slice checks would otherwise make misplaced payload invisible
    twice over: silent here, silently dropped at install time.
    """
    out: list[str] = []
    if role == "shared":
        for name in sorted(PAYLOAD_DIRS):
            if os.path.isdir(os.path.join(role_path, name)):
                out.append(
                    f"shared/{name}/: shared ships no payload — role.py "
                    "resolves it as no role and never installs from it"
                )
        return out
    skills_dir = os.path.join(role_path, "skills")
    if os.path.isdir(skills_dir):
        for name in sorted(os.listdir(skills_dir)):
            entry = os.path.join(skills_dir, name)
            if not os.path.isdir(entry):
                out.append(
                    f"{role}/skills/{name}: not a directory — role.py "
                    "installs only directories here, and skips the rest silently"
                )
            elif not os.path.isfile(os.path.join(entry, "SKILL.md")):
                out.append(f"{role}/skills/{name}/: no SKILL.md to be discovered by")
    commands_dir = os.path.join(role_path, "commands")
    if os.path.isdir(commands_dir):
        for name in sorted(os.listdir(commands_dir)):
            entry = os.path.join(commands_dir, name)
            if not (os.path.isfile(entry) and name.endswith(".md")):
                out.append(
                    f"{role}/commands/{name}: not a .md file — role.py "
                    "installs only .md files here, and skips the rest silently"
                )
    return out


def parse_frontmatter(text: str) -> dict[str, Any] | None:
    """Parse the small YAML subset the assembler emits (no external dep)."""
    match = FRONTMATTER_RE.match(text)
    if not match:
        return None
    meta: dict[str, Any] = {}
    key: str | None = None
    for raw in match.group(1).split("\n"):
        if not raw.strip():
            continue
        if raw.startswith("  - ") or raw.startswith("    "):
            if key is None:
                continue
            item = raw.strip().lstrip("- ").strip()
            if ":" in item and not item.startswith('"'):
                sub, _, value = item.partition(":")
                if isinstance(meta.get(key), list) and meta[key] and isinstance(meta[key][-1], dict):
                    meta[key][-1][sub.strip()] = value.strip()
                else:
                    meta.setdefault(key, []).append({sub.strip(): value.strip()})
            else:
                try:
                    item = json.loads(item)
                except json.JSONDecodeError:
                    pass
                meta.setdefault(key, []).append(item)
            continue
        if ":" in raw:
            key, _, value = raw.partition(":")
            key = key.strip()
            value = value.strip()
            if value == "":
                meta[key] = []
            else:
                try:
                    meta[key] = json.loads(value)
                except json.JSONDecodeError:
                    # MATCH assemble.decode_scalar's fallback, which strips the
                    # outer quotes when json.loads fails. Keeping them here made
                    # the two parsers disagree about the same file: a
                    # description written with unescaped inner quotes — which
                    # yaml_scalar would never emit, so it is hand-edited or
                    # pre-dates the current assembler — came back quoted to lint
                    # and unquoted to assemble. Every length, pattern and
                    # equality judgement lint makes on that field was therefore
                    # made on a different string than the index was generated
                    # from. Found because the INDEX description check below fired
                    # on three slices that were not actually drifted.
                    meta[key] = value.strip('"') if value.startswith('"') else value
    return meta


SESSION_TEMP_REFERENCE = re.compile(r"(^|/)(tmp/claude|scratchpad/)|^/tmp/")


def check_durable_references(role: str, crossref: dict[str, Any]) -> list[str]:
    """A crossref key must still resolve after its session is gone.

    The index's whole value is outliving the observation buffer: ADRs,
    PRs, commits and migrations resolve against git and GitHub. A path
    into a session scratchpad resolves against nothing — it names a
    directory belonging to one session on one machine, dead by the
    time anyone reads it, yet still shaped like a file to open. Three
    such keys reached the repo from other sessions before this check
    existed; `assemble.normalize_artifact` now collapses them to a
    `scratch:` pseudo-path on the way in, and this catches any that
    arrive by another route (a hand edit, an older generator).

    Both `scratch:name` and `scratch:name#<digest>` are valid. The
    digest was added later, to keep two dead paths that share a basename
    from merging into one node; it hashes the ORIGINAL path, which no
    buffer still holds for the keys written before it, so those keep the
    bare form permanently. This check is about the session path being
    gone, which is true of both.
    """
    findings: list[str] = []
    for kind, values in (crossref.get("index") or {}).items():
        for value in values:
            if SESSION_TEMP_REFERENCE.search(value):
                findings.append(
                    f"{role}/crossref.json: index.{kind} key {value!r} is a "
                    "session-local temp path and will not resolve for anyone "
                    "else — use the 'scratch:' form"
                )
    return findings


def validate_json(schema: dict[str, Any], doc: Any, where: str) -> list[str]:
    try:
        import jsonschema  # type: ignore
    except ImportError:
        return _structural_check(schema, doc, where)
    validator = jsonschema.Draft202012Validator(schema)
    return [
        f"{where}: {'/'.join(str(p) for p in err.path) or '<root>'}: {err.message}"
        for err in sorted(validator.iter_errors(doc), key=lambda e: list(e.path))
    ]


def _structural_check(schema: dict[str, Any], doc: Any, where: str, path: str = "",
                      root: dict[str, Any] | None = None) -> list[str]:
    """The no-dependency validator: type, required, properties, items, enum,
    pattern — and the two composition keywords the schemas here use,
    local `$ref` (#/$defs/…) and `allOf`. Anything else is jsonschema's."""
    root = root if root is not None else schema
    if "$ref" in schema:
        ref = schema["$ref"]
        if ref.startswith("#/"):
            target: Any = root
            for part in ref[2:].split("/"):
                target = target.get(part, {}) if isinstance(target, dict) else {}
            merged = {k: v for k, v in schema.items() if k != "$ref"}
            problems = _structural_check(target, doc, where, path, root)
            return problems + (_structural_check(merged, doc, where, path, root) if merged else [])
    if "allOf" in schema:
        problems: list[str] = []
        for sub in schema["allOf"]:
            problems += _structural_check(sub, doc, where, path, root)
        rest = {k: v for k, v in schema.items() if k != "allOf"}
        return problems + (_structural_check(rest, doc, where, path, root) if rest else [])
    """Enough of JSON Schema to be useful without the dependency."""
    problems: list[str] = []
    expected = schema.get("type")
    if expected:
        kinds = {
            "object": dict, "array": list, "string": str,
            "integer": int, "number": (int, float), "boolean": bool,
        }
        types = expected if isinstance(expected, list) else [expected]
        allowed = tuple(kinds[t] for t in types if t in kinds)
        if allowed and not isinstance(doc, allowed):
            if not (doc is None and "null" in types):
                return [f"{where}{path}: expected {expected}"]
    if isinstance(doc, dict):
        for key in schema.get("required", []):
            if key not in doc:
                problems.append(f"{where}{path}: missing required '{key}'")
        props = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            pattern_props = schema.get("patternProperties", {})
            for key in doc:
                if key in props:
                    continue
                if any(re.search(p, key) for p in pattern_props):
                    continue
                problems.append(f"{where}{path}: unexpected property '{key}'")
        for key, sub in props.items():
            if key in doc:
                problems += _structural_check(sub, doc[key], where, f"{path}/{key}", root)
        extra = schema.get("additionalProperties")
        if isinstance(extra, dict):
            for key, value in doc.items():
                if key not in props:
                    problems += _structural_check(extra, value, where, f"{path}/{key}", root)
    if isinstance(doc, list):
        items = schema.get("items")
        if isinstance(items, dict):
            for i, value in enumerate(doc):
                problems += _structural_check(items, value, where, f"{path}[{i}]", root)
        if schema.get("uniqueItems") and len({json.dumps(v, sort_keys=True) for v in doc}) != len(doc):
            problems.append(f"{where}{path}: duplicate items")
    if "enum" in schema and doc not in schema["enum"]:
        problems.append(f"{where}{path}: {doc!r} not in {schema['enum']}")
    if "pattern" in schema and isinstance(doc, str) and not re.search(schema["pattern"], doc):
        problems.append(f"{where}{path}: {doc!r} does not match {schema['pattern']}")
    return problems


def model_profile_findings(root: str, doc: dict[str, Any], known_roles: set[str]) -> list[str]:
    """Invariants the schema cannot express for routing/profiles.json.

    The file is layered — defaults <- roles.<role> <- agents.<login> — over
    routing/capabilities.json, and the launcher resolves each capability
    by merging the layers. So the review gate is on the MERGED review
    model of every row, not on each layer's own value: a row that sets no
    review model inherits the provider's and is fine; one that sets a
    cheaper model is the defect this exists to catch, because a review's
    failure mode is a green PR that merges. Role rows must name roles the
    catalogue knows; agent rows are keyed by login, never by a directory.
    The rest of the routing consistency — classes, providers, shims,
    aliases, the declared review id — is tools/fabric/routing.py's check().
    """
    findings: list[str] = []
    where = "routing/profiles.json"
    routing_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), "routing.py")
    spec = importlib.util.spec_from_file_location("fabric_routing", routing_path)
    routing = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(routing)
    findings += [f"routing: {f}" for f in routing.check(root)]
    grade = routing.load_review_grade(root)
    gated = grade.get("capability", "code-review")
    try:
        routing.load_capabilities(root)
    except (OSError, KeyError, ValueError):
        return findings
    rows = [("defaults", None, None)]
    rows += [("roles", name, None) for name in (doc.get("roles") or {})]
    rows += [("agents", None, name) for name in (doc.get("agents") or {})]
    for layer, role, agent in rows:
        label = layer if layer == "defaults" else f"{layer}.{role or agent}"
        for provider in routing.PROVIDERS:
            try:
                model = routing.resolve(gated, provider, role, agent, None, root)["model"]
            except (KeyError, ValueError) as exc:
                findings.append(f"{where}: {label} on {provider}: {exc}")
                continue
            if not routing.ADAPTERS[provider].is_model(model):
                continue  # an alias is the harness's choice, ungated
            if not routing.review_grade_ok(model, root):
                findings.append(f"{where}: {label} resolves {gated} on {provider} to {model!r}, which is not in "
                                "routing/policies/review-grade.json; the review class would run on it")
    # The bottom layer must give every provider a session: the launcher
    # refuses a path with none rather than guess one.
    for provider in routing.PROVIDERS:
        try:
            routing.resolve_session(root=root, provider=provider)
        except (KeyError, ValueError) as exc:
            findings.append(f"{where}: defaults name no session for {provider}: {exc}")
    if known_roles:
        for name in (doc.get("roles") or {}):
            if name not in known_roles:
                findings.append(f"{where}: roles.{name} is not a role in identities/roles/catalog.json")
    for name in (doc.get("agents") or {}):
        if "/" in name or name.startswith("clone-"):
            findings.append(f"{where}: agents.{name} is not a Linux login")
    return findings


def license_findings(root: str) -> list[str]:
    """This repository is one license, Apache-2.0, throughout — REUSE.toml
    assigns nothing else, and every identifier it does use has its text
    under LICENSES/. projects/registry.json names each project's OWN
    license as information about that project's tree; it is required (a
    project with no stated license cannot be reasoned about) but binds
    nothing here. A project's knowledge never lives here at all."""
    findings: list[str] = []
    reg_path = os.path.join(root, "projects", "registry.json")
    reuse_path = os.path.join(root, "REUSE.toml")
    if not os.path.exists(reg_path):
        return findings
    try:
        registry = json.load(open(reg_path, encoding="utf-8"))
    except (OSError, ValueError):
        return findings  # the registry's own parse is reported elsewhere
    for pid, entry in sorted((registry.get("projects") or {}).items()):
        lic = entry.get("license")
        if not isinstance(lic, str) or not lic:
            findings.append(f"projects/registry.json: project {pid!r} names no license")
        if os.path.isdir(os.path.join(root, "memory", "projects", pid)):
            findings.append(f"memory/projects/{pid}/: a project's knowledge lives in the project's repository "
                            "(<working copy>/.agent-fabric/memory/), not here")
    if not os.path.exists(reuse_path):
        findings.append("REUSE.toml: missing; the repository states its license there")
        return findings
    try:
        import tomllib
        reuse = tomllib.load(open(reuse_path, "rb"))
    except Exception as exc:  # noqa: BLE001 - any parse failure is the finding
        return [f"REUSE.toml: does not parse ({exc})"]
    licenses_dir = os.path.join(root, "LICENSES")
    for ann in reuse.get("annotations") or []:
        lic = ann.get("SPDX-License-Identifier", "")
        if lic != "Apache-2.0":
            findings.append(f"REUSE.toml: assigns {lic!r} to {ann.get('path')}; this repository is Apache-2.0 throughout")
        if lic and not os.path.exists(os.path.join(licenses_dir, lic + ".txt")):
            findings.append(f"REUSE.toml: {lic!r} has no LICENSES/{lic}.txt")
    return findings


CLASS_DOCS = {
    # Where the class list is written out for a reader; each must name every
    # class in routing/capabilities.json and nothing that is not one — the
    # README said `review` for a class named code-review until 2026-09-16.
    "README.md": r"`routing/capabilities.json` classes:([^|\n]*)",
    "CLAUDE.md": r"name a capability class in `subagent_type`[^.]*?the five\s+are (.*?)— and",
}


def class_doc_findings(root: str) -> list[str]:
    """The capability class names a document lists must be exactly the
    classes routing/capabilities.json defines."""
    findings: list[str] = []
    cap_path = os.path.join(root, "routing", "capabilities.json")
    try:
        classes = set((json.load(open(cap_path, encoding="utf-8")).get("classes") or {}).keys())
    except (OSError, ValueError):
        return findings  # the file's own parse is reported by the routing check
    if not classes:
        return findings
    for rel, pattern in CLASS_DOCS.items():
        path = os.path.join(root, rel)
        try:
            text = open(path, encoding="utf-8").read()
        except OSError:
            continue
        m = re.search(pattern, text, flags=re.S)
        if not m:
            findings.append(f"{rel}: the capability class list was not found (lint looks for {pattern!r})")
            continue
        named = set(re.findall(r"`([a-z][a-z0-9-]*)`", m.group(1)))
        for extra in sorted(named - classes):
            findings.append(f"{rel}: names capability class {extra!r}, which routing/capabilities.json does not define "
                            f"(classes: {', '.join(sorted(classes))})")
        for missing in sorted(classes - named):
            findings.append(f"{rel}: does not name capability class {missing!r} (routing/capabilities.json defines it)")
    return findings


def agent_source_findings(root: str) -> list[str]:
    """A committed agent definition carries no routed value.

    `model:` and `effort:` are written into the installed copy by
    runtime/claude-code/install-agent-files.sh, from routing/. A value
    hand-written into the source here would be the second place a class's
    model or thinking is decided, and the one nobody updates — the source's
    `model:` is the tier alias the class rides, never a resolved id."""
    findings: list[str] = []
    # Every committed source of an INSTALLED agent file, not only the
    # class files: the locale worker is installed the same way and was
    # outside this scan, so a hand-written level there had no second
    # writer to refuse it (review of 2026-09-23).
    sources: list[tuple[str, str]] = []
    agents = os.path.join(root, "runtime", "claude-code", "agents")
    for name in sorted(os.listdir(agents)) if os.path.isdir(agents) else []:
        if name.endswith(".md"):
            sources.append((os.path.join("runtime", "claude-code", "agents", name),
                            os.path.join(agents, name)))
    locales = os.path.join(root, "identities", "roles", "language-culture", "locale")
    for suffix in sorted(os.listdir(locales)) if os.path.isdir(locales) else []:
        worker = os.path.join(locales, suffix, "worker.md")
        if os.path.isfile(worker):
            sources.append((os.path.join("identities", "roles", "language-culture",
                                         "locale", suffix, "worker.md"), worker))
    for rel, path in sources:
        try:
            text = open(path, encoding="utf-8").read()
        except OSError:
            continue
        head = text.split("---", 2)[1] if text.startswith("---") and "---" in text[3:] else text
        if re.search(r"^effort:", head, flags=re.M):
            findings.append(f"{rel}: carries a hand-written 'effort:'. The level is routing/effort.json's and is "
                            "written into the installed copy by install-agent-files.sh; a second source here is "
                            "the one that goes stale.")
    return findings


# Generic surfaces: what every managed project shares. A project's name
# there is project truth in the control plane — the review of 2026-09-16
# found one project's port variable in a role skill, its gpg wrapper in
# the provisioner, its channel as a GZCoord default.
GENERIC_DIRS = ("identities/roles", "runtime/provisioning", "runtime/claude-code", "runtime/hostexec",
                "runtime/openrouter", "runtime/github", "tools/fabric", "bin", "communication/gzcoord/scripts",
                "communication/gzcoord/skills")
GENERIC_SKIP = ("history/", "/test_", "/tests/", "README.md")
# The fabric's own remote is not a managed project's name.
FABRIC_SELF = ("gzapi-org/agent-fabric",)


def project_name_findings(root: str) -> list[str]:
    """A managed project's id (projects/registry.json) must not appear in
    a generic file: a role's skills, the provisioning, the harness
    adapters, the tools, the GZCoord runtime. What a project needs said
    goes in its own integration (projects/<id>/) or its working copy's
    .agent-fabric/ remit. The fabric's own id and remote are exempt; so
    are tests, READMEs and history."""
    findings: list[str] = []
    try:
        ids = sorted((json.load(open(os.path.join(root, "projects", "registry.json"), encoding="utf-8")).get("projects") or {}).keys())
    except (OSError, ValueError):
        return findings
    ids = [i for i in ids if i != layout.FABRIC_PROJECT_ID]
    if not ids:
        return findings
    pats = []
    for pid in ids:
        pats.append(re.compile(r"(?<![A-Za-z0-9])" + re.escape(pid) + r"(?![A-Za-z0-9.])", re.I))
        pats.append(re.compile(r"\b" + re.escape(re.sub(r"[^A-Za-z0-9]", "_", pid).upper()) + r"_"))
    for rel in GENERIC_DIRS:
        base = os.path.join(root, rel)
        if not os.path.isdir(base):
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = sorted(d for d in dirnames if d not in ("node_modules", "__pycache__", ".git"))
            for name in sorted(filenames):
                full = os.path.join(dirpath, name)
                relpath = os.path.relpath(full, root)
                if any(x in relpath + ("/" if os.path.isdir(full) else "") for x in GENERIC_SKIP) or name.startswith("test_") or name.endswith((".png", ".jpg", ".txt", ".lock")):
                    continue
                try:
                    with open(full, encoding="utf-8") as fh:
                        for n, line in enumerate(fh, 1):
                            probe = line
                            for exempt in FABRIC_SELF:
                                probe = probe.replace(exempt, "")
                            for pat in pats:
                                m = pat.search(probe)
                                if m:
                                    findings.append(f"{relpath}:{n}: names a managed project ({m.group(0)!r}) in a generic file; "
                                                    "project truth goes in projects/<id>/ or the project's .agent-fabric/ remit")
                                    break
                except (OSError, UnicodeDecodeError):
                    continue
    return findings


LENS_BODY_CAP = 1500
LENS_DESCRIPTION_CAP = 120
LENS_NAME_RE = re.compile(r"^[a-z][a-z0-9-]*$")


def review_lens_findings(root: str) -> list[str]:
    """runtime/claude-code/review/lenses/<name>.md: the review lens
    vocabulary IS this directory (bin/fabric-review lenses lists it, the
    brief renderer inlines a named one). Each file: `name:` equal to the
    filename, a one-line `description:`, a body under the cap — a lens
    biases a review and is paid on every dispatch that names it."""
    findings: list[str] = []
    base = os.path.join(root, "runtime", "claude-code", "review", "lenses")
    if not os.path.isdir(base):
        return findings
    names = sorted(os.listdir(base))
    if "general.md" not in names:
        findings.append("runtime/claude-code/review/lenses/: no general.md — the renderer adds `general` to every brief")
    for fn in names:
        rel = f"runtime/claude-code/review/lenses/{fn}"
        if not fn.endswith(".md"):
            findings.append(f"{rel}: not a lens (.md)")
            continue
        text = open(os.path.join(base, fn), encoding="utf-8").read()
        m = FRONTMATTER_RE.match(text)
        if not m:
            findings.append(f"{rel}: no frontmatter (name:, description:)")
            continue
        meta = dict(line.split(":", 1) for line in m.group(1).split("\n") if ":" in line)
        meta = {k.strip(): v.strip() for k, v in meta.items()}
        stem = fn[:-3]
        if meta.get("name") != stem or not LENS_NAME_RE.match(stem):
            findings.append(f"{rel}: name {meta.get('name')!r} must equal the filename and be a lowercase slug")
        desc = meta.get("description", "")
        if not desc or len(desc) > LENS_DESCRIPTION_CAP:
            findings.append(f"{rel}: description missing or over {LENS_DESCRIPTION_CAP} characters (one line, shown by fabric-review lenses)")
        body = text[m.end():]
        if len(body.encode()) > LENS_BODY_CAP:
            findings.append(f"{rel}: body is {len(body.encode())} bytes; the cap is {LENS_BODY_CAP} (a lens is paid on every dispatch that names it)")
        if not body.strip():
            findings.append(f"{rel}: empty body")
    return findings


def host_registry_findings(root: str) -> list[str]:
    """runtime/hosts/registry.json: a host id is its short hostname, so ids
    are unique by construction and an ssh destination reaches one host;
    exactly one host is the one this registry is read on (ssh null); a
    placement names a known host. Placement is where an account is, never
    who it is — the schema forbids anything else in a host entry."""
    findings: list[str] = []
    path = os.path.join(root, "runtime", "hosts", "registry.json")
    if not os.path.exists(path):
        return findings
    where = "runtime/hosts/registry.json"
    try:
        reg = json.load(open(path, encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [f"{where}: does not parse ({exc})"]
    schema = load_schema(root, os.path.join("runtime", "hosts", "schema"), "hosts")
    if schema:
        findings += validate_json(schema, reg, where)
        if findings:
            return findings
    hosts = reg.get("hosts") or {}
    local = [h for h, e in hosts.items() if e.get("ssh") is None]
    if len(local) != 1:
        findings.append(f"{where}: exactly one host has ssh null (the one this registry is read on); found {len(local)}: {', '.join(sorted(local)) or 'none'}")
    seen: dict[str, str] = {}
    for hid, e in sorted(hosts.items()):
        dest = e.get("ssh")
        if dest is None:
            continue
        if dest in seen:
            findings.append(f"{where}: hosts {seen[dest]} and {hid} share the ssh destination {dest!r}; one destination is one host")
        seen[dest] = hid
    for login, hid in sorted((reg.get("placement") or {}).items()):
        if hid not in hosts:
            findings.append(f"{where}: placement of {login!r} names host {hid!r}, which is not registered")
    return findings


def candidate_role_findings(root: str, catalog: dict[str, Any] | None,
                            taxonomy_roles: dict[str, set[str]]) -> list[str]:
    """`candidate: true` in the catalogue means the role has not yet proved
    it carries its own weight. The proof is structural, not remembered
    (architect-cto's proposal, narrowed by the owner, 2026-09-18): a
    project's taxonomy binds the role AND a login named for it is placed
    on a host (runtime/hosts/registry.json). Such a role is not a
    candidate; the flag must go in the same change that made it true."""
    if not catalog:
        return []
    path = os.path.join(root, "runtime", "hosts", "registry.json")
    try:
        placement = (json.load(open(path, encoding="utf-8")).get("placement") or {})
    except (OSError, ValueError):
        return []
    bound: dict[str, list[str]] = {}
    for pid, roles in taxonomy_roles.items():
        for rid in roles:
            bound.setdefault(rid, []).append(pid)
    out: list[str] = []
    for r in catalog.get("roles", []) or []:
        if not isinstance(r, dict) or not r.get("candidate"):
            continue
        rid = r.get("id") or ""
        logins = sorted(l for l in placement if l == rid or l.startswith(rid + "-"))
        if rid in bound and logins:
            out.append(f"identities/roles/catalog.json: role {rid!r} is a candidate, yet "
                       f"{', '.join(sorted(bound[rid]))} binds it and {', '.join(logins)} holds it — "
                       "a proved role; drop `candidate`")
    return out


def load_schema(root: str, subdir: str, name: str) -> dict[str, Any] | None:
    path = os.path.join(root, subdir, f"{name}.schema.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def load_json(path: str, where: str, findings: list[str]) -> Any:
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except ValueError as exc:
        findings.append(f"{where}: not valid JSON ({exc})")
        return None


CLASS_DIRS = ("domain", "solution", "intersection", "rationale", "workflow", "threads")


def lint_slices(base: str, where_prefix: str, template_schema: dict[str, Any] | None,
                findings: list[str], shared_owner_count: dict[str, set[str]],
                descriptions: dict[str, str], project: str | None = None) -> list[str]:
    """Judge every slice under `base`; return their paths as an index links
    them (relative to the fabric root, or to the project's working copy
    when `project` names one whose memory lives in its repository)."""
    slices: list[str] = []
    if not os.path.isdir(base):
        return slices
    for dirpath, dirnames, filenames in os.walk(base):
        # Payload is exempt only at the ROOT of a role identity directory:
        # `identities/roles/<role>/skills/`. A `skills/` nested anywhere
        # else is a directory of slices like any other.
        if dirpath == base and where_prefix.startswith("identities/"):
            dirnames[:] = [d for d in dirnames if d not in PAYLOAD_DIRS and d != LOCALE_DIRNAME]
        for filename in sorted(filenames):
            # README.md is documentation of a directory, never a slice.
            if not filename.endswith(".md") or filename in ("INDEX.md", "README.md"):
                continue
            full = os.path.join(dirpath, filename)
            rel = layout.link_rel(full, project)
            with open(full, encoding="utf-8") as fh:
                text = fh.read()
            slices.append(rel)
            meta = parse_frontmatter(text)
            if meta is None:
                findings.append(f"{rel}: no provenance frontmatter")
                continue
            if template_schema:
                findings += validate_json(template_schema, meta, rel)
            if isinstance(meta.get("description"), str):
                descriptions[rel] = meta["description"]
            # charter, brief and recall are authored, not distilled: they define
            # the role rather than assert anything about the system, so
            # they carry no evidence by nature — and they live ONLY under
            # identities/roles/; a slice of that class anywhere in memory/
            # is a hand-authored claim smuggled past provenance.
            klass = meta.get("class")
            if klass in layout.IDENTITY_CLASSES and not where_prefix.startswith("identities/"):
                findings.append(f"{rel}: class {klass!r} is authored role identity and "
                                "belongs under identities/roles/, not in memory/")
            if not meta.get("derived_from") and klass not in layout.IDENTITY_CLASSES:
                findings.append(f"{rel}: no derived_from — a claim with no evidence")
            for owner in meta.get("shared_with", []) or []:
                shared_owner_count[rel].add(owner)
            body = FRONTMATTER_RE.sub("", text)
            budget = TIER1_BUDGET_TOKENS if meta.get("tier") == 1 else BUDGET_TOKENS
            approx = len(body) // CHARS_PER_TOKEN
            if approx > budget * 1.35:
                findings.append(f"{rel}: ~{approx} tokens exceeds the {budget} budget; split the slice")
            findings += hygiene_findings(rel, body)
            # The cue is English like the body: an index line and a heading
            # are what every holder of the role reads before choosing a
            # slice. The Italian check above missed a whole drain of Russian
            # and Georgian cues (a drain's blind review, 2026-09-25).
            prose = re.sub(r"^```.*?^```", "", body, flags=re.MULTILINE | re.DOTALL)   # a fenced block is quoted text
            cues = [("description", meta.get("description"))] + \
                   [("heading", h) for h in re.findall(r"^#{1,6} (.+)$", prose, re.MULTILINE)]
            for kind, cue in cues:
                # Italian is the fleet's one other Latin-script language;
                # the body's marker check now reaches the cues too.
                if isinstance(cue, str) and (_is_mostly_non_latin(cue)
                                             or len({w.lower() for w in ITALIAN_MARKERS.findall(cue)}) >= 3):
                    findings.append(f"{rel}: {kind} is not English ({cue[:60]!r}); "
                                    "the holder renders it — description_en in the memory")
    return slices


def flat_and_dir_findings(base: str, label: str) -> list[str]:
    """A class is either a flat file or a directory, never both. The
    activator takes the directory branch and skips the flat file, so the
    flat one is unreachable — and at tier 1 that silently retires knowledge
    the index promises loads at activation."""
    out: list[str] = []
    for klass_dir in CLASS_DIRS:
        if (os.path.isdir(os.path.join(base, klass_dir))
                and os.path.exists(os.path.join(base, f"{klass_dir}.md"))):
            out.append(f"{label}: has both {klass_dir}.md and {klass_dir}/ — the flat file is "
                       "unreachable, the activator loads only the directory")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Lint the committed corpus.")
    ap.add_argument("--fabric", default=None, help="agent-fabric root (default: this checkout)")
    ap.add_argument("--tokens", metavar="FILE", help="print FILE's protected tokens (what a translation keeps byte-identical) and exit")
    ap.add_argument("--digest", metavar="FILE", help="print FILE's body digest (what a translation records as translates_digest) and exit")
    ap.add_argument("--working-copy", action="append", default=[], metavar="[PROJECT=]DIR",
                    help="a managed project's checkout whose .agent-fabric/memory/ is linted too "
                         "(repeatable; the project is resolved from the checkout's remote unless "
                         "named as PROJECT=DIR)")
    ap.add_argument("--no-siblings", action="store_true",
                    help="do not lint the registered working copies found beside this checkout")
    args = ap.parse_args()
    if args.fabric:
        layout.FABRIC_ROOT = os.path.abspath(args.fabric)
    root = layout.FABRIC_ROOT
    if args.tokens or args.digest:
        target = args.tokens or args.digest
        with open(target, encoding="utf-8") as fh:
            body = FRONTMATTER_RE.sub("", fh.read())
        if args.digest:
            print(_source_digest(target))
            return 0
        for (category, token), n in sorted(_protected_tokens(body).items()):
            print(f"{n:3d}  {category:16s} {token}")
        return 0
    if not os.path.isdir(os.path.join(root, "identities")):
        print(f"lint: no agent-fabric checkout at {root}", file=sys.stderr)
        return 2
    for wc in args.working_copy:
        pid, sep, path = wc.partition("=")
        if not sep:
            pid, path = workingcopy.resolve(wc).get("project"), wc
        if not pid:
            print(f"lint: {wc} is not a working copy of a registered project "
                  "(name it as PROJECT=DIR)", file=sys.stderr)
            return 2
        layout.set_working_copy(pid, path)
    # The working copies beside this checkout are linted too, unasked: a
    # project's CI lints its .agent-fabric/ against a fresh clone of this
    # repository, so a charter edited here with the project's index left
    # describing the old one passes a fabric-only run and fails every PR
    # of that project (2026-09-17, a morning of one project's CI). What sits
    # beside the fabric is what the fabric's own run must see.
    if not args.no_siblings:
        for pid, path in sibling_working_copies(root).items():
            if pid not in layout.explicit_working_copies():
                layout.set_working_copy(pid, path)

    findings: list[str] = []
    schemas = os.path.join("identities", "schemas")
    # Every project whose working copy this run knows contributes its
    # hygiene list — whether or not that working copy holds memory yet.
    BANNED_PATTERNS[:] = layout.load_hygiene_patterns(
        sorted(set(layout.list_projects()) | set(layout.explicit_working_copies())))

    # --- the role catalogue ------------------------------------------------
    known_roles: set[str] = set()
    catalog: dict[str, Any] | None = None   # stays None when the catalogue is missing; the candidate check then has nothing to judge
    catalog_schema = load_schema(root, schemas, "catalog")
    catalog_path = layout.catalog_path()
    if os.path.exists(catalog_path):
        catalog = load_json(catalog_path, "identities/roles/catalog.json", findings)
        if catalog is not None:
            if catalog_schema:
                findings += validate_json(catalog_schema, catalog, "identities/roles/catalog.json")
            known_roles = {r.get("id") for r in catalog.get("roles", []) if isinstance(r, dict)}
    else:
        findings.append("identities/roles/catalog.json: missing")

    # --- project bindings --------------------------------------------------
    # A project's taxonomy lives in its working copy (.agent-fabric/
    # taxonomy.json) — the fabric's own included — or, for a project not
    # yet moved, under projects/<id>/ here. Judged for every project whose
    # taxonomy this run can reach.
    taxonomy_schema = load_schema(root, os.path.join("projects", "schemas"), "taxonomy")
    projects_root = os.path.join(root, "projects")
    project_ids: list[str] = []
    taxonomy_roles: dict[str, set[str]] = {}   # project id -> the roles its taxonomy binds
    registry_ids: list[str] = []
    try:
        registry_ids = sorted((json.load(open(os.path.join(projects_root, "registry.json"), encoding="utf-8"))
                               .get("projects") or {}).keys())
    except (OSError, ValueError):
        pass
    bound_here_ids = [d for d in (sorted(os.listdir(projects_root)) if os.path.isdir(projects_root) else [])
                      if os.path.isfile(os.path.join(projects_root, d, "taxonomy.json"))]
    for pid in sorted(set(registry_ids) | set(bound_here_ids) | set(layout.explicit_working_copies())):
        if True:
            tax_path = layout.project_taxonomy_path(pid)
            if not tax_path:
                continue
            project_ids.append(pid)
            where = (f"projects/{pid}/taxonomy.json" if tax_path.startswith(root)
                     else f"{pid}:{layout.PROJECT_DIRNAME}/taxonomy.json")
            wc_root = layout.working_copy_for(pid)
            if wc_root:
                findings += fabric_ref_findings(pid, wc_root)
            tax = load_json(tax_path, where, findings)
            if tax is None:
                continue
            if taxonomy_schema:
                findings += validate_json(taxonomy_schema, tax, where)
            if tax.get("project") not in (None, pid):
                findings.append(f"{where}: names project {tax.get('project')!r} but lives under {pid}/")
            for r in tax.get("roles", []) or []:
                rid = r.get("id") if isinstance(r, dict) else None
                if rid:
                    taxonomy_roles.setdefault(pid, set()).add(rid)
                if known_roles and rid not in known_roles:
                    findings.append(f"{where}: role {rid!r} is not in identities/roles/catalog.json")
                for prefix in (r.get("paths") if isinstance(r, dict) else None) or []:
                    if os.path.isabs(prefix) or prefix.startswith("~"):
                        findings.append(f"{where}: role {rid!r} path {prefix!r} is machine-specific; "
                                        "paths must be repository-relative")

    # --- a candidate that a project binds and a login holds is proved ------
    findings += candidate_role_findings(root, catalog, taxonomy_roles)

    # --- licenses ----------------------------------------------------------
    findings += license_findings(root)

    # --- the class list a reader sees --------------------------------------
    findings += class_doc_findings(root)
    findings += agent_source_findings(root)

    # --- the hosts and where each account lives -----------------------------
    findings += host_registry_findings(root)

    # --- no project's name in a generic file --------------------------------
    findings += project_name_findings(root)

    # --- the review lenses ---------------------------------------------------
    findings += review_lens_findings(root)

    findings += i18n_default_dictionary_findings()

    # --- routing profiles --------------------------------------------------
    profiles_schema = load_schema(root, os.path.join("routing", "schemas"), "model-profiles")
    profiles_path = os.path.join(root, "routing", "profiles.json")
    if profiles_schema and os.path.exists(profiles_path):
        profiles = load_json(profiles_path, "routing/profiles.json", findings)
        if profiles is not None:
            schema_findings = validate_json(profiles_schema, profiles, "routing/profiles.json")
            findings += schema_findings
            if not schema_findings:
                findings += model_profile_findings(root, profiles, known_roles)

    # --- role identities ---------------------------------------------------
    template_schema = load_schema(root, schemas, "role-template")
    crossref_schema = load_schema(root, schemas, "crossref")
    shared_owner_count: dict[str, set[str]] = defaultdict(set)
    descriptions: dict[str, str] = {}
    identity_slices: dict[str, list[str]] = {}
    roles_dir = layout.roles_dir()
    role_ids = [d for d in sorted(os.listdir(roles_dir))
                if os.path.isdir(os.path.join(roles_dir, d))] if os.path.isdir(roles_dir) else []
    for role in role_ids:
        role_path = os.path.join(roles_dir, role)
        if known_roles and role not in known_roles:
            findings.append(f"identities/roles/{role}: not in identities/roles/catalog.json")
        if not os.path.isfile(os.path.join(role_path, "charter.md")):
            findings.append(f"identities/roles/{role}: no charter.md — a role without a charter has no boundary")
        findings += payload_shape_findings(role, role_path)
        for sub in sorted(PAYLOAD_DIRS):
            payload = os.path.join(role_path, sub)
            if os.path.isdir(payload):
                for dirpath, _d, filenames in os.walk(payload):
                    for filename in sorted(filenames):
                        if filename.endswith(".md"):
                            full = os.path.join(dirpath, filename)
                            with open(full, encoding="utf-8") as fh:
                                findings += hygiene_findings(layout.root_rel(full), fh.read())
        identity_slices[role] = lint_slices(role_path, f"identities/roles/{role}", template_schema,
                                            findings, shared_owner_count, descriptions)
        findings += locale_translation_findings(role, role_path, template_schema)
        findings += locale_worker_findings(role, role_path)
        findings += locale_file_findings(role, role_path)
        findings += i18n_dictionary_findings(role, role_path)
        for rel in identity_slices[role]:
            klass = (parse_frontmatter(open(os.path.join(root, rel), encoding="utf-8").read()) or {}).get("class")
            if klass not in layout.IDENTITY_CLASSES:
                findings.append(f"{rel}: class {klass!r} is knowledge, not identity — it belongs under memory/")
    for role in known_roles - set(role_ids):
        findings.append(f"identities/roles/catalog.json: role {role!r} has no identities/roles/{role}/ directory")

    # --- domain memory -----------------------------------------------------
    domain_slices: dict[str, list[str]] = {}
    domains_root = os.path.join(root, "memory", "domains")
    if os.path.isdir(domains_root):
        for domain in sorted(os.listdir(domains_root)):
            base = os.path.join(domains_root, domain)
            if not os.path.isdir(base):
                continue
            findings += flat_and_dir_findings(base, f"memory/domains/{domain}")
            domain_slices[domain] = lint_slices(base, f"memory/domains/{domain}", template_schema,
                                                findings, shared_owner_count, descriptions)

    # --- project memory, and the indexes ------------------------------------
    # A project's memory lives in ITS repository (<working copy>/.agent-fabric/
    # memory/); this run sees the projects whose working copy it knows.
    # Index links are relative to the working copy; fabric-side slices
    # reach back through ../agent-fabric/, which resolve_link maps onto
    # this checkout.
    indexed_domains: set[str] = set()
    for pid in layout.list_projects():
        pbase = layout.project_memory_root(pid)
        plabel = f"{pid}:{layout.PROJECT_MEMORY_SUBDIR}"
        if project_ids and pid not in project_ids:
            findings.append(f"{plabel}: no projects/{pid}/taxonomy.json binds this project")
        for role in sorted(os.listdir(pbase)):
            rbase = os.path.join(pbase, role)
            if not os.path.isdir(rbase):
                continue
            label = f"{plabel}/{role}"
            if role == "shared":
                lint_slices(rbase, label, template_schema, findings, shared_owner_count, descriptions, pid)
                continue
            if known_roles and role not in known_roles:
                findings.append(f"{label}: not a role in identities/roles/catalog.json")
            findings += flat_and_dir_findings(rbase, label)
            slices = lint_slices(rbase, label, template_schema, findings, shared_owner_count, descriptions, pid)
            # Fabric-side slices as THIS project's index links them.
            fabric_side = {layout.link_rel(os.path.join(root, r), pid): r
                           for r in domain_slices.get(role, []) + identity_slices.get(role, [])}
            expected = list(slices) + list(fabric_side)
            indexed_domains.add(role)

            index_path = os.path.join(rbase, "INDEX.md")
            if not os.path.exists(index_path):
                if expected:
                    findings.append(f"{label}: has slices but no INDEX.md")
                continue
            with open(index_path, encoding="utf-8") as fh:
                index_text = fh.read()
            linked = set(re.findall(r"\]\(([^)]+)\)", index_text))
            for rel in expected:
                if rel not in linked:
                    findings.append(f"{label}/INDEX.md: does not list {rel} — the index has drifted")
            for target in linked:
                if not os.path.exists(layout.resolve_link(target, pid)):
                    findings.append(f"{label}/INDEX.md: links {target}, which does not exist")

            # THE DESCRIPTION, NOT ONLY THE PATH. INDEX.md is generated from
            # slice frontmatter (assemble.py), and it is the only thing a
            # session reads before deciding whether to load a slice. Checking
            # paths alone let a slice's description change while the index
            # kept the old wording: lint reported clean and the index quietly
            # described something else. The line shape is assemble.py's:
            #     - [`path`](path) — description
            index_described: dict[str, str] = {}
            for line in index_text.splitlines():
                m = re.match(r"^- \[`([^`]+)`\]\(([^)]+)\) — (.*)$", line)
                if m and m.group(1) == m.group(2):
                    index_described[m.group(2)] = m.group(3).strip()
            for rel in sorted(expected):
                listed = index_described.get(rel)
                described = descriptions.get(fabric_side.get(rel, rel))
                if listed is None or described is None:
                    continue
                if listed != described.strip():
                    findings.append(
                        f"{label}/INDEX.md: the entry for {rel} describes it as "
                        f"{listed!r} but the slice's frontmatter says "
                        f"{described.strip()!r} — the index has drifted; "
                        f"re-run tools/fabric/assemble.py"
                    )

            crossref_path = os.path.join(rbase, "crossref.json")
            if os.path.exists(crossref_path):
                crossref_doc = load_json(crossref_path, f"{label}/crossref.json", findings)
                if crossref_doc is not None:
                    if crossref_schema:
                        findings += validate_json(crossref_schema, crossref_doc, f"{label}/crossref.json")
                    findings += check_durable_references(label, crossref_doc)

    # A domain's slices are listed by the project indexes of the role that
    # owns them. That can only be judged for roles some VISIBLE project
    # files knowledge for: once a project's memory lives in its repository,
    # a lint run that cannot see that working copy sees no index for it —
    # which is absence of evidence, not drift.
    # So: judged for a domain only when some VISIBLE project's taxonomy
    # binds that role — that project's index is where the slices must be
    # listed. A project this run cannot see (another repository's CI passes
    # only its own working copy) says nothing about the roles it does not
    # bind: one project's merge queue failed on every PR the day a new
    # role's slices landed here, indexed by a repository that project's
    # lint never sees (flutter-dev's observation, relay seq 1076,
    # 2026-09-17).
    visible = [pid for pid in layout.list_projects() if pid != layout.FABRIC_PROJECT_ID]
    for domain, slices in domain_slices.items():
        bound_by = [pid for pid in visible if domain in taxonomy_roles.get(pid, set())]
        if slices and domain not in indexed_domains and bound_by:
            findings.append(f"memory/domains/{domain}: {len(slices)} slice(s) indexed by no project — "
                            f"{', '.join(bound_by)} binds the role and its "
                            f".agent-fabric/memory/{domain}/INDEX.md does not list them")

    # --- shared ----------------------------------------------------------------
    shared_root = layout.shared_dir()
    if os.path.isdir(shared_root):
        lint_slices(shared_root, "memory/shared", template_schema, findings, shared_owner_count, descriptions)
    for where, owners in shared_owner_count.items():
        if len(owners) < 2:
            findings.append(f"{where}: shared slice owned by {len(owners)} role(s); "
                            "fold it back into its single owner")

    # --- launch prompt sections --------------------------------------------
    findings += prompt_template_findings()
    findings += harness_source_findings()

    # --- decision records and the paths that cite documents ----------------
    findings += adr_findings()
    WARNINGS.extend(doc_path_findings())

    for warning in WARNINGS:
        print(f"  warning: {warning}", file=sys.stderr)
    if findings:
        print(f"corpus lint: {len(findings)} finding(s)\n", file=sys.stderr)
        for finding in findings:
            print(f"  {finding}", file=sys.stderr)
        return 1
    print(f"corpus lint: clean ({len(role_ids)} roles, {len(domain_slices)} domains, "
          f"{len(layout.list_projects())} project(s)"
          + (f", {len(WARNINGS)} warning(s)" if WARNINGS else "") + ")")
    return 0


if __name__ == "__main__":
    sys.exit(main())
