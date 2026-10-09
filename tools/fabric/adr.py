#!/usr/bin/env python3
"""tools/fabric/adr.py — agent-fabric's decision records (docs/adr/).

    adr.py check [--root R]            every rule below; exit 1 on a finding
    adr.py index --write [--root R]    regenerate index.json and the README table
    adr.py new <slug> "<title>"        the next number, from ADR-TEMPLATE.md
    adr.py amend <NNN> "<title>"       the history note stub and the table row (the DIGEST bullet is yours)
    adr.py lookup [<word>...]          DIGEST entries mentioning every word; none: the table
                                       of which record answers what (fabric-adr lookup)
    adr.py range-check [<base> [<head>] | <base>..<head>]
                                       each commit that edits an ADR's body records it;
                                       no range: CI's base..head, else origin/main..HEAD (fabric-adr range-check)

The engine is the first managed project's (its documentation history
model, recorded in its own ADRs), with what
that one leaves to convention made checkable (agent-fabric ADR-001):

- the index is GENERATED from the ADR headers and never hand-edited, so a
  stale one is a finding rather than a comment claiming otherwise;
- one amendment heading form, `### Amendment YYYY-MM-DD — Title`;
- the header fields and the section order are checked;
- `Accepted` needs `**Ratified:** owner, YYYY-MM-DD, <source>` — the
  owner's word reaches an artifact, or the decision is not binding;
- the pillars are read from ADR-000's §5 table, never restated here;
- a commit that edits an ADR's body adds an amendment row or says why not
  (`ADR-Editorial:` trailer) — `range-check`, the CI tripwire;
- `Evidence:` paths resolve; `Superseded` carries a point map to an ADR
  that exists; DIGEST titles, statuses and amendment dates match.

Pure standard library: it runs where lint.py runs, in CI and in the
commit hook, with nothing installed.
"""
from __future__ import annotations

import argparse
import datetime
import collections
import json
import os
import re
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import roots  # noqa: E402

# A label in findings and the path git is asked about; never joined to a root.
ADR_DIR = "docs/adr"
FILE_RE = re.compile(r"^ADR-(\d{3})-([a-z0-9]+(?:-[a-z0-9]+)*)\.md$")
H1_RE = re.compile(r"^# ADR-(\d{3}) — (.+?)\s*$")
FIELD_RE = re.compile(r"^\*\*([A-Za-z ]+):\*\*\s*(.*?)\s*$")
STATUSES = ("Proposed", "Accepted", "Superseded", "Deprecated")
REQUIRED_FIELDS = ("Date", "Status", "Decision Makers", "Scope", "Pillar")
SECTIONS = (
    "1. Context and Problem", "2. Decision", "3. Alternatives Considered",
    "4. Rationale", "5. Binding Rules", "6. Consequences",
    "7. Future Evolution", "8. Decision Status", "References",
)
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
AMENDMENT_RE = re.compile(r"^### Amendment (\d{4}-\d{2}-\d{2}) — (.+?)\s*$")
ANY_AMENDMENT_HEADING = re.compile(r"^#{2,4}\s+Amendment\b")
ROW_RE = re.compile(r"^\|\s*(\d{4}-\d{2}-\d{2})\s*\|\s*(.+?)\s*\|\s*(.*?)\s*\|\s*$")
RATIFIED_RE = re.compile(r"^owner, (\d{4}-\d{2}-\d{2}), (\S.*)$")
PILLAR_ROW_RE = re.compile(r"^\s*\|\s*(P\d+)\s*\|")
DIGEST_RE = re.compile(r"^### ADR-(\d{3}) — (.+) \((Proposed|Accepted|Superseded|Deprecated)\)\s*$")
DIGEST_AMEND_RE = re.compile(r"^- A (\d{4}-\d{2}-\d{2})\b")
# A DIGEST entry is looked up, one or two at a time, never read as a whole
# file (ADR-001 §5): what keeps a lookup cheap is each entry staying short.
# At 250 words the longest entry costs ~350 tokens; the whole DIGEST once
# read first cost ~12,000, twice the launch prompt.
DIGEST_ENTRY_WORDS = 250
INDEX_START, INDEX_END = "<!-- adr-index:start -->", "<!-- adr-index:end -->"
# A bare ADR-NNN inside docs/adr is this repository's; another project's is
# named with it ("<project>'s ADR-075", "<project> ADR-059") and is not checked here.
CITE_RE = re.compile(r"(?<![\w-])(?:([A-Za-z][\w.-]*?)(?:'s|’s)?\s+)?ADR-(\d{3})(?!\d)")


def foreign_projects(root: str) -> set[str]:
    """The ids projects/registry.json knows, but this one: a citation named
    with one of them ("<project>'s ADR-075") is that project's, not ours."""
    try:
        ids = set((json.load(open(roots.projects_registry(root, engine=ROOT), encoding="utf-8")).get("projects") or {}).keys())
    except (OSError, ValueError):
        ids = set()
    return {i.lower() for i in ids} - {"agent-fabric"}


def real_date(value: str) -> bool:
    """YYYY-MM-DD and a day that exists (2026-13-45 is not one)."""
    if not DATE_RE.fullmatch(value):
        return False
    try:
        datetime.date.fromisoformat(value)
        return True
    except ValueError:
        return False


def within(root: str, rel: str) -> bool:
    """A relative path that stays inside root: no absolute path, no escape."""
    if os.path.isabs(rel):
        return False
    real_root = os.path.realpath(root)
    return os.path.realpath(os.path.join(root, rel)).startswith(real_root + os.sep)


def adr_dir(root: str | None = None) -> str:
    """The decision records are the organization's (ADR-045 rule 2): no root
    given, they are the operator's; a root a tool was handed is the tree it means."""
    return roots.adr_dir(root, engine=ROOT)


def tree(root: str | None) -> str:
    """The repository the records live in: what their Evidence paths and their
    history are relative to."""
    return root or roots.operator_root(engine=ROOT)


# Who decided and when are the header's (Date, Decision Makers, Ratified)
# and the history's; a record's body and its DIGEST entry state the decision
# (the owner's rule for records, agent-fabric ADR-001 §5 rule 10). A
# parenthesis that opens on the owner or the CEO is that attribution, across
# a line break too.
ATTRIBUTION_RE = re.compile(r"\((?:the\s+owner|the\s+CEO)\b[^()]*\)", re.I)


# A record reads current: when a rule began is the header's, the Amendments
# table's and the history's (ADR-001 §5 rule 11). §1 may date an incident;
# §2–§8 carry no date outside a path or code span, an "(A YYYY-MM-DD)" rule
# marker or an "(Amendment YYYY-MM-DD)" tombstone — the engine's own marks.
# Its own name: DATE_RE above is the anchored header pattern real_date()
# and amend rely on (review thread on #53).
BODY_DATE_RE = re.compile(r"\b\d{4}-\d\d-\d\d\b")
# A path is a token with a slash, or a bare dated file name with an
# extension; either carries its date as a name, not as a statement.
UNDATED_SPANS = re.compile(r"`[^`]*`|\]\([^)]*\)|\((?:A|Amendment) \d{4}-\d\d-\d\d\)"
                           r"|[\w.-]*/[\w./-]*\d{4}-\d\d-\d\d[\w./-]*|[\w.-]*\d{4}-\d\d-\d\d[\w.-]*\.[a-z]{2,4}\b")


def dated_sections(text: str) -> list[tuple[str, str]]:
    """(section number, date) for each date §2–§8 carries."""
    out, cur, fenced = [], None, False
    for ln in text.split("\n"):
        if ln.lstrip().startswith("```"):
            fenced = not fenced
            continue
        if fenced:
            continue
        if ln.startswith("## "):
            m = re.match(r"## (\d)\.", ln)
            cur = m.group(1) if m and m.group(1) != "1" else None
            continue
        if cur:
            for d in BODY_DATE_RE.findall(UNDATED_SPANS.sub("", ln)):
                out.append((cur, d))
    return out


def attributions(text: str) -> list[str]:
    return [" ".join(m.group(0).split()) for m in ATTRIBUTION_RE.finditer(text)]


def read(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def parse_adr(path: str) -> dict:
    """The header, the sections in order, the amendments table rows."""
    text = read(path)
    lines = text.split("\n")
    out = {"path": path, "text": text, "fields": {}, "sections": [], "rows": [], "h1": None,
           "stray_amendment": False, "has_point_map": "Point map" in text}
    in_amend = False
    for ln in lines:
        if out["h1"] is None:
            m = H1_RE.fullmatch(ln)
            if m:
                out["h1"] = (m.group(1), m.group(2))
                continue
        if ln.startswith("## "):
            name = ln[3:].strip()
            out["sections"].append(name)
            in_amend = name == "Amendments"
            continue
        if not out["sections"]:
            m = FIELD_RE.fullmatch(ln)
            if m:
                out["fields"][m.group(1)] = m.group(2)
        if ANY_AMENDMENT_HEADING.match(ln):
            out["stray_amendment"] = True
        if in_amend:
            m = ROW_RE.fullmatch(ln)
            if m and not set(m.group(1)) <= {"-"}:
                out["rows"].append((m.group(1), m.group(2)))
    return out


def status_word(status: str) -> str:
    return status.split()[0] if status else ""


def pillars(root: str | None) -> list[str]:
    """ADR-000 §5's table is the only list of pillars (agent-fabric ADR-001)."""
    d = adr_dir(root)
    zero = [f for f in os.listdir(d) if f.startswith("ADR-000-")] if os.path.isdir(d) else []
    if not zero:
        return []
    text = read(os.path.join(d, zero[0]))
    sec = text.split("\n## 5. Binding Rules", 1)
    body = sec[1].split("\n## ", 1)[0] if len(sec) == 2 else ""
    return [m.group(1) for ln in body.split("\n") if (m := PILLAR_ROW_RE.match(ln))]


def history_notes(path: str) -> list[tuple[str, str]]:
    out = []
    for ln in read(path).split("\n"):
        m = AMENDMENT_RE.fullmatch(ln)
        if m:
            out.append((m.group(1), m.group(2)))
        elif ANY_AMENDMENT_HEADING.match(ln):
            out.append(("?", ln.strip()))
    return out


def load(root: str | None) -> tuple[list[dict], list[str]]:
    d = adr_dir(root)
    findings: list[str] = []
    adrs = []
    if not os.path.isdir(d):
        return [], [f"{ADR_DIR}: missing"]
    for f in sorted(os.listdir(d)):
        if not f.startswith("ADR-") or f == "ADR-TEMPLATE.md":
            continue
        m = FILE_RE.fullmatch(f)
        if not m:
            findings.append(f"{ADR_DIR}/{f}: not named ADR-NNN-lowercase-kebab.md")
            continue
        a = parse_adr(os.path.join(d, f))
        a["number"], a["slug"], a["file"] = m.group(1), m.group(2), f
        adrs.append(a)
    return adrs, findings


def index_rows(root: str | None, adrs: list[dict]) -> list[dict]:
    rows = []
    for a in adrs:
        hist = os.path.join(adr_dir(root), "history", f"ADR-{a['number']}-amendments.md")
        rows.append({
            "number": a["number"], "file": a["file"],
            "title": a["h1"][1] if a["h1"] else "",
            "status": status_word(a["fields"].get("Status", "")),
            "date": a["fields"].get("Date", ""),
            "pillar": a["fields"].get("Pillar", ""),
            "amendments": len(history_notes(hist)) if os.path.exists(hist) else 0,
        })
    return rows


def render_index(rows: list[dict]) -> str:
    doc = {"$comment": "GENERATED by tools/fabric/adr.py index --write from the ADR headers and history/; never edit by hand — adr.py check fails a stale copy.",
           "adrs": rows}
    return json.dumps(doc, indent=2, ensure_ascii=False) + "\n"


def render_table(rows: list[dict]) -> str:
    lines = [INDEX_START, "| ADR | Title | Pillar | Status | Amendments |", "|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| [ADR-{r['number']}]({r['file']}) | {r['title']} | {r['pillar']} | {r['status']} | {r['amendments']} |")
    lines.append(INDEX_END)
    return "\n".join(lines)


def replace_table(readme: str, table: str) -> str | None:
    if INDEX_START not in readme or INDEX_END not in readme:
        return None
    head, rest = readme.split(INDEX_START, 1)
    _, tail = rest.split(INDEX_END, 1)
    return head + table + tail


def check(root: str | None = None) -> list[str]:
    d = adr_dir(root)
    adrs, findings = load(root)
    if not adrs:
        return findings or [f"{ADR_DIR}: no ADR"]
    rel = lambda a: f"{ADR_DIR}/{a['file']}"  # noqa: E731
    numbers = [int(a["number"]) for a in adrs]
    if len(set(numbers)) != len(numbers):
        dup = [n for n, c in collections.Counter(numbers).items() if c > 1]
        findings.append(f"{ADR_DIR}: number(s) used twice: {', '.join(f'ADR-{n:03d}' for n in dup)}")
    if sorted(set(numbers)) != list(range(len(set(numbers)))):
        missing = sorted(set(range(max(numbers) + 1)) - set(numbers))
        findings.append(f"{ADR_DIR}: numbers are not contiguous from ADR-000 — missing {', '.join(f'ADR-{n:03d}' for n in missing)}")
    known = {a["number"]: a for a in adrs}
    pill = pillars(root)
    foreign = foreign_projects(root)
    if not pill:
        findings.append(f"{ADR_DIR}: ADR-000 §5 has no pillar table (| P1 | … |) — the pillars have one source")

    for a in adrs:
        f = a["fields"]
        if not a["h1"]:
            findings.append(f"{rel(a)}: no '# ADR-NNN — Title' heading")
        elif a["h1"][0] != a["number"]:
            findings.append(f"{rel(a)}: heading says ADR-{a['h1'][0]}, the file name ADR-{a['number']}")
        for field in REQUIRED_FIELDS:
            if not f.get(field):
                findings.append(f"{rel(a)}: header field **{field}:** missing")
        if f.get("Date") and not real_date(f["Date"]):
            findings.append(f"{rel(a)}: **Date:** {f['Date']!r} is not a YYYY-MM-DD date")
        sw = status_word(f.get("Status", ""))
        if f.get("Status") and sw not in STATUSES:
            findings.append(f"{rel(a)}: **Status:** begins with {sw!r}, not one of {', '.join(STATUSES)}")
        if sw == "Accepted":
            rat = f.get("Ratified", "")
            m = RATIFIED_RE.fullmatch(rat)
            if m and not real_date(m.group(1)):
                findings.append(f"{rel(a)}: **Ratified:** {m.group(1)!r} is not a date")
            if not m:
                findings.append(f"{rel(a)}: Accepted without '**Ratified:** owner, YYYY-MM-DD, <source>' — nothing is binding until the owner's word reaches an artifact")
        if sw == "Superseded":
            target = re.search(r"→\s*ADR-(\d{3})", f.get("Status", ""))
            if not target:
                findings.append(f"{rel(a)}: Superseded without '(→ ADR-NNN)'")
            elif target.group(1) not in known:
                findings.append(f"{rel(a)}: superseded by ADR-{target.group(1)}, which does not exist")
            if not a["has_point_map"]:
                findings.append(f"{rel(a)}: Superseded without a point map (where each rule now lives)")
        pv = f.get("Pillar", "")
        if pv and pill:
            for p in [x.strip() for x in pv.split(",")]:
                if p != "all" and p not in pill:
                    findings.append(f"{rel(a)}: **Pillar:** {p} is not in ADR-000 §5 ({', '.join(pill)})")
        for ev in [x.strip() for x in f.get("Evidence", "").split(",") if x.strip()]:
            if not within(tree(root), ev):
                findings.append(f"{rel(a)}: **Evidence:** {ev} is not a path inside the repository")
            elif not os.path.exists(os.path.join(tree(root), ev)):
                findings.append(f"{rel(a)}: **Evidence:** {ev} does not exist")
        secs = [s for s in a["sections"] if s != "Amendments"]
        if secs != list(SECTIONS):
            findings.append(f"{rel(a)}: sections must be, in order: {' · '.join(SECTIONS)} (then Amendments) — found {' · '.join(secs) or 'none'}")
        if "Amendments" in a["sections"] and a["sections"][-1] != "Amendments":
            findings.append(f"{rel(a)}: '## Amendments' must be the last section")
        if a["stray_amendment"]:
            findings.append(f"{rel(a)}: an '### Amendment' heading in the ADR itself — the note goes to history/, the ADR keeps a table row")
        hist = os.path.join(d, "history", f"ADR-{a['number']}-amendments.md")
        notes = history_notes(hist) if os.path.exists(hist) else []
        for dt, title in notes:
            if dt == "?":
                findings.append(f"{ADR_DIR}/history/ADR-{a['number']}-amendments.md: {title!r} is not '### Amendment YYYY-MM-DD — Title'")
            elif not real_date(dt):
                findings.append(f"{ADR_DIR}/history/ADR-{a['number']}-amendments.md: amendment {title!r} is dated {dt}, which is not a date")
        good = collections.Counter(n for n in notes if n[0] != "?")
        rows = collections.Counter(a["rows"])
        if good != rows:
            only_n = list((good - rows).elements())
            only_r = list((rows - good).elements())
            if only_n:
                findings.append(f"{rel(a)}: amendment note(s) with no table row: {only_n}")
            if only_r:
                findings.append(f"{rel(a)}: table row(s) with no history note: {only_r}")
        if good and "Amendments" not in a["sections"]:
            findings.append(f"{rel(a)}: amended, but no '## Amendments' section")
        body = a["text"].split("\n## ", 1)[1] if "\n## " in a["text"] else ""
        body = body.split("\n## Amendments", 1)[0]
        for sec, dated in dated_sections(a["text"]):
            findings.append(f"{rel(a)}: §{sec} dates something ({dated}) — a record reads current; when is the header's and the history's, §1 may date an incident")
        for att in attributions(body):
            findings.append(f"{rel(a)}: an inline attribution {att!r} — who decided and when belong in the header and the history")
        for m in CITE_RE.finditer(a["text"]):
            if m.group(1) and m.group(1).lower() in foreign:
                continue
            if m.group(2) not in known:
                findings.append(f"{rel(a)}: cites ADR-{m.group(2)}, which does not exist")

    hdir = os.path.join(d, "history")
    if os.path.isdir(hdir):
        for f in sorted(os.listdir(hdir)):
            m = re.match(r"^ADR-(\d{3})-amendments\.md$", f)
            if not m or m.group(1) not in known:
                findings.append(f"{ADR_DIR}/history/{f}: belongs to no ADR")
            elif not history_notes(os.path.join(hdir, f)):
                findings.append(f"{ADR_DIR}/history/{f}: no amendment in it — remove it")

    rows = index_rows(root, adrs)
    ip = os.path.join(d, "index.json")
    if not os.path.exists(ip) or read(ip) != render_index(rows):
        findings.append(f"{ADR_DIR}/index.json: stale or missing — run tools/fabric/adr.py index --write")
    rp = os.path.join(d, "README.md")
    if not os.path.exists(rp):
        findings.append(f"{ADR_DIR}/README.md: missing")
    else:
        body = read(rp)
        new = replace_table(body, render_table(rows))
        if new is None:
            findings.append(f"{ADR_DIR}/README.md: no {INDEX_START} … {INDEX_END} markers")
        elif new != body:
            findings.append(f"{ADR_DIR}/README.md: the index table is stale — run tools/fabric/adr.py index --write")

    dp = os.path.join(d, "DIGEST.md")
    if not os.path.exists(dp):
        findings.append(f"{ADR_DIR}/DIGEST.md: missing")
    else:
        for att in attributions(read(dp)):
            findings.append(f"{ADR_DIR}/DIGEST.md: an inline attribution {att!r} — who decided and when belong in the record's header and history")
        entries: dict[str, dict] = {}
        cur = None
        for ln in read(dp).split("\n"):
            m = DIGEST_RE.fullmatch(ln)
            if m:
                cur = m.group(1)
                entries[cur] = {"title": m.group(2), "status": m.group(3), "dates": [], "words": len(ln.split())}
                continue
            if ln.startswith("### "):
                cur = None
            if cur:
                entries[cur]["words"] += len(ln.split())
                am = DIGEST_AMEND_RE.match(ln)
                if am:
                    entries[cur]["dates"].append(am.group(1))
        by = {r["number"]: r for r in rows}
        for num, r in by.items():
            e = entries.get(num)
            if not e:
                findings.append(f"{ADR_DIR}/DIGEST.md: no entry '### ADR-{num} — {r['title']} ({r['status']})'")
                continue
            if e["words"] > DIGEST_ENTRY_WORDS:
                findings.append(f"{ADR_DIR}/DIGEST.md: ADR-{num}'s entry is {e['words']} words, over {DIGEST_ENTRY_WORDS}: "
                                "an entry is looked up, so it states the rules and points to the sections, no more")
            if e["title"] != r["title"] or e["status"] != r["status"]:
                findings.append(f"{ADR_DIR}/DIGEST.md: ADR-{num} reads {e['title']!r} ({e['status']}), the ADR {r['title']!r} ({r['status']})")
            hist = os.path.join(d, "history", f"ADR-{num}-amendments.md")
            hd = sorted(n[0] for n in history_notes(hist)) if os.path.exists(hist) else []
            if sorted(e["dates"]) != hd:
                findings.append(f"{ADR_DIR}/DIGEST.md: ADR-{num}'s amendment bullets {sorted(e['dates'])} are not its history {hd}")
        for num in entries:
            if num not in by:
                findings.append(f"{ADR_DIR}/DIGEST.md: an entry for ADR-{num}, which does not exist")
    return findings


def write_index(root: str | None = None) -> None:
    adrs, _ = load(root)
    rows = index_rows(root, adrs)
    d = adr_dir(root)
    with open(os.path.join(d, "index.json"), "w", encoding="utf-8") as fh:
        fh.write(render_index(rows))
    rp = os.path.join(d, "README.md")
    new = replace_table(read(rp), render_table(rows))
    if new is None:
        raise SystemExit(f"adr: {ADR_DIR}/README.md has no {INDEX_START} … {INDEX_END} markers")
    with open(rp, "w", encoding="utf-8") as fh:
        fh.write(new)


def cmd_new(root: str | None, slug: str, title: str) -> str:
    if not re.match(r"^[a-z0-9]+(?:-[a-z0-9]+)*$", slug):
        raise SystemExit("adr: the slug is lowercase-kebab")
    adrs, _ = load(root)
    n = max((int(a["number"]) for a in adrs), default=-1) + 1
    tpl = read(os.path.join(adr_dir(root), "ADR-TEMPLATE.md"))
    body = tpl.replace("ADR-NNN", f"ADR-{n:03d}").replace("<Title>", title)
    path = os.path.join(adr_dir(root), f"ADR-{n:03d}-{slug}.md")
    with open(path, "x", encoding="utf-8") as fh:
        fh.write(body)
    return path


def cmd_amend(root: str | None, num: str, title: str, date: str) -> None:
    num = f"{int(num):03d}"
    d = adr_dir(root)
    main = [f for f in os.listdir(d) if f.startswith(f"ADR-{num}-")]
    if not main:
        raise SystemExit(f"adr: no ADR-{num}")
    os.makedirs(os.path.join(d, "history"), exist_ok=True)
    hist = os.path.join(d, "history", f"ADR-{num}-amendments.md")
    if not os.path.exists(hist):
        with open(hist, "w", encoding="utf-8") as fh:
            fh.write(f"# ADR-{num} — amendments\n\nThe full notes; the ADR's body reads current and its Amendments table lists them.\n")
    with open(hist, "a", encoding="utf-8") as fh:
        fh.write(f"\n### Amendment {date} — {title}\n\nWhat changed, why, and the owner's word or the evidence that moved it.\n")
    path = os.path.join(d, main[0])
    text = read(path)
    if "\n## Amendments\n" not in text:
        text = text.rstrip("\n") + f"\n\n## Amendments\n\nThe body above reads current; each change's full note is in [history/ADR-{num}-amendments.md](history/ADR-{num}-amendments.md).\n\n| Date | Amendment | Effect |\n|---|---|---|\n"
    text = text.rstrip("\n") + f"\n| {date} | {title} | (say which § and rule) |\n"
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    print(f"adr: amended ADR-{num} — edit §1–§8 in place, fill the note and the Effect cell, add '- A {date} — …' to its DIGEST entry, then adr.py index --write")


def cmd_lookup(root: str | None, words: list[str]) -> list[str]:
    text = read(os.path.join(adr_dir(root), "DIGEST.md"))
    if not words:
        # The table of which record answers what: the part of the DIGEST a
        # session reads to find a record, without every entry below it.
        head = re.split(r"\n(?=### ADR-)", text)[0]
        table = [ln for ln in head.split("\n") if ln.startswith("|")]
        return ["\n".join(table)] if table else []
    out = []
    for block in re.split(r"\n(?=### ADR-)", text):
        if block.startswith("### ADR-") and all(w.lower() in block.lower() for w in words):
            out.append(block.strip())
    return out


# A commit that changes an existing ADR's body — anything past its header —
# records it: a NEW row in its Amendments table in the same commit, or an
# `ADR-Editorial:` trailer saying why none is due (a typo, a renumbered
# citation). Header lines (Status, Ratified) are the ratification's, not an
# amendment's. A dated row elsewhere (a table inside §5) or an edited Effect
# cell is not an amendment row (review of #50, P2-1). Renames are followed
# (-M), so a rename carrying a rewrite is judged too. Plumbing, not porcelain:
# a user's color.diff or diff.external never reaches the parse. A record
# the branch itself adds is still a draft until the merge ratifies it:
# fixing it before then is not an amendment, so only records that exist at
# the base are judged.
def range_check(root: str, base: str, head: str = "HEAD") -> list[str]:
    git = lambda *a: subprocess.run(["git", "-C", root, *a], capture_output=True, text=True, check=True).stdout  # noqa: E731
    findings = []
    # A record is the branch's own draft when its NUMBER is absent from the
    # base — by number, not path, so a rename in one commit and a body edit
    # in the next is still judged (re-review of #50, finding 4).
    # A base with no docs/adr/ at all (the branch that introduces the
    # records) has no records: every one in the branch is new.
    listed = subprocess.run(["git", "-C", root, "ls-tree", "--name-only", f"{base}:{ADR_DIR}"], capture_output=True, text=True)
    at_base = {m.group(1) for f in listed.stdout.split() if (m := FILE_RE.fullmatch(f))} if listed.returncode == 0 else set()
    for sha in git("rev-list", "--reverse", "--no-merges", f"{base}..{head}").split():
        # The trailer excuses a record's body edit only; a source is checked
        # whatever the message says (review of #51).
        editorial = bool(re.search(r"^ADR-Editorial:\s*\S", git("log", "-1", "--format=%B", sha), re.M))
        entries = [ln.split("\t") for ln in git("diff-tree", "--no-commit-id", "--name-status", "-r", "-M", sha).splitlines()]
        # A rename below -M's similarity threshold arrives as a delete and an
        # add of the same record number: pair them, and judge the pair like
        # a rename (re-review of #50).
        deleted = {m.group(1): e[1] for e in entries if e[0][:1] == "D" and len(e) == 2
                   and os.path.dirname(e[1]) == ADR_DIR and (m := FILE_RE.fullmatch(os.path.basename(e[1])))}
        for parts in entries:
            kind = parts[0][:1]
            if kind == "M" and len(parts) == 2:
                old, new_path = parts[1], parts[1]
            elif kind == "R" and len(parts) == 3:
                old, new_path = parts[1], parts[2]
            elif kind == "A" and len(parts) == 2 and os.path.dirname(parts[1]) == ADR_DIR and (m := FILE_RE.fullmatch(os.path.basename(parts[1]))) and m.group(1) in deleted:
                old, new_path = deleted[m.group(1)], parts[1]
            elif kind == "D" and len(parts) == 2 and parts[1].startswith(f"{ADR_DIR}/sources/"):
                findings.append(f"{sha[:8]}: deletes {parts[1]}, a verbatim source, which is never removed")
                continue
            else:
                continue
            # A source is kept verbatim: any change to one is a finding
            # (agent-fabric ADR-001 §5 rule 9).
            if new_path.startswith(f"{ADR_DIR}/sources/") or old.startswith(f"{ADR_DIR}/sources/"):
                findings.append(f"{sha[:8]}: edits {old}, a verbatim source, which is never edited")
                continue
            m = FILE_RE.fullmatch(os.path.basename(new_path))
            if os.path.dirname(new_path) != ADR_DIR or not m or m.group(1) not in at_base:
                continue
            before = git("show", f"{sha}^:{old}")
            after = git("show", f"{sha}:{new_path}")
            b_lines, a_lines = before.split("\n"), after.split("\n")
            b_first = next((i for i, ln in enumerate(b_lines) if ln.startswith("## ")), len(b_lines))
            a_first = next((i for i, ln in enumerate(a_lines) if ln.startswith("## ")), len(a_lines))
            body_changed = b_lines[b_first:] != a_lines[a_first:]
            rows_before = set(amendment_rows(before))
            row_added = bool(set(amendment_rows(after)) - rows_before)
            if body_changed and not row_added and not editorial:
                findings.append(f"{sha[:8]}: edits the body of {new_path} with no new Amendments row and no 'ADR-Editorial:' trailer")
    return findings


def amendment_rows(text: str) -> list[tuple[str, str]]:
    """The (date, title) rows of the `## Amendments` table only."""
    rows, inside = [], False
    for ln in text.split("\n"):
        if ln.startswith("## "):
            inside = ln[3:].strip() == "Amendments"
            continue
        m = ROW_RE.fullmatch(ln) if inside else None
        if m:
            rows.append((m.group(1), m.group(2)))
    return rows


def default_range(root: str) -> tuple[str, str] | None:
    """The range CI or a person means when none is given, in the order
    policies/check_adr_amendment.sh chose it: the pull request's or the
    merge group's own base and head from the GitHub event, when both are
    present here; else AGENT_FABRIC_ADR_BASE, origin/$GITHUB_BASE_REF,
    origin/main or main, against HEAD. None when no base resolves: the
    check is then not enforced, and says so."""
    def has(ref: str) -> bool:
        return subprocess.run(["git", "-C", root, "rev-parse", "--verify", "-q", f"{ref}^{{commit}}"],
                              capture_output=True).returncode == 0
    event = os.environ.get("GITHUB_EVENT_PATH", "")
    if event and os.access(event, os.R_OK):
        try:
            with open(event, encoding="utf-8") as f:
                ev = json.load(f)
            pr, mg = ev.get("pull_request") or {}, ev.get("merge_group") or {}
            b = (pr.get("base") or {}).get("sha") or mg.get("base_sha")
            h = (pr.get("head") or {}).get("sha") or mg.get("head_sha")
            if b and h and has(b) and has(h):
                return b, h
        except (OSError, ValueError, AttributeError):
            pass
    base_ref = os.environ.get("GITHUB_BASE_REF", "")
    for c in (os.environ.get("AGENT_FABRIC_ADR_BASE", ""), f"origin/{base_ref}" if base_ref else "", "origin/main", "main"):
        if c and has(c):
            return c, "HEAD"
    return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="adr.py", description=__doc__.split("\n\n")[0])
    ap.add_argument("--root", default=None)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check")
    p = sub.add_parser("index"); p.add_argument("--write", action="store_true", required=True)
    p = sub.add_parser("new"); p.add_argument("slug"); p.add_argument("title")
    p = sub.add_parser("amend"); p.add_argument("number"); p.add_argument("title"); p.add_argument("--date", required=True)
    p = sub.add_parser("lookup"); p.add_argument("words", nargs="*")
    p = sub.add_parser("range-check"); p.add_argument("base", nargs="?"); p.add_argument("head", nargs="?")
    a = ap.parse_args(argv)
    if a.cmd == "check":
        f = check(a.root)
        for x in f:
            print(f"  {x}")
        print(f"adr check: {'clean' if not f else f'{len(f)} finding(s)'}")
        return 1 if f else 0
    if a.cmd == "index":
        write_index(a.root); print("adr: index.json and the README table regenerated"); return 0
    if a.cmd == "new":
        print(cmd_new(a.root, a.slug, a.title)); return 0
    if a.cmd == "amend":
        if not real_date(a.date):
            raise SystemExit("adr: --date YYYY-MM-DD, a real calendar date")
        cmd_amend(a.root, a.number, a.title, a.date); return 0
    if a.cmd == "lookup":
        hits = cmd_lookup(a.root, a.words)
        print("\n\n".join(hits) if hits else "adr: no DIGEST entry mentions all of that"); return 0 if hits else 1
    if a.cmd == "range-check":
        if a.base is None:
            if not os.path.isdir(adr_dir(a.root)):
                print("adr range-check: no docs/adr/ — nothing to check"); return 0
            found = default_range(tree(a.root))
            if found is None:
                print("adr range-check: no base to compare with — not enforced"); return 0
            a.base, a.head = found
        # "A..B" is how git spells a range, and how people type one: taken
        # as base and head. It crashed git rev-list as "A..B..HEAD".
        if ".." in a.base:
            if a.head is not None:
                print("adr range-check: give either BASE..HEAD or BASE HEAD, not both", file=sys.stderr)
                return 2
            a.base, _, a.head = a.base.partition("..")
        if not a.base:
            # git reads "..X" as HEAD..X, and an empty base lists no records,
            # so every record would count as the branch's own draft.
            print("adr range-check: the range has no base (BASE..HEAD)", file=sys.stderr)
            return 2
        a.head = a.head or "HEAD"
        try:
            f = range_check(tree(a.root), a.base, a.head)
        except subprocess.CalledProcessError as e:
            print(f"adr range-check: git could not read {a.base}..{a.head}: {(e.stderr or '').strip()[-200:]}", file=sys.stderr)
            return 2
        for x in f:
            print(f"  {x}")
        print(f"adr range-check: {'clean' if not f else f'{len(f)} commit(s) edit an ADR body unrecorded'}")
        return 1 if f else 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
