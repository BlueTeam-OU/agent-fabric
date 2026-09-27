#!/usr/bin/env python3
"""tools/fabric/adr.py — agent-fabric's decision records (docs/adr/).

    adr.py check [--root R]            every rule below; exit 1 on a finding
    adr.py index --write [--root R]    regenerate index.json and the README table
    adr.py new <slug> "<title>"        the next number, from ADR-TEMPLATE.md
    adr.py amend <NNN> "<title>"       the history note stub and the table row (the DIGEST bullet is yours)
    adr.py lookup <word>...            DIGEST entries mentioning every word
    adr.py range-check <base> [<head>] each commit that edits an ADR's body records it

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
ADR_DIR = os.path.join("docs", "adr")
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
INDEX_START, INDEX_END = "<!-- adr-index:start -->", "<!-- adr-index:end -->"
# A bare ADR-NNN inside docs/adr is this repository's; another project's is
# named with it ("<project>'s ADR-075", "<project> ADR-059") and is not checked here.
CITE_RE = re.compile(r"(?<![\w-])(?:([A-Za-z][\w.-]*?)(?:'s|’s)?\s+)?ADR-(\d{3})(?!\d)")


def foreign_projects(root: str) -> set[str]:
    """The ids projects/registry.json knows, but this one: a citation named
    with one of them ("<project>'s ADR-075") is that project's, not ours."""
    try:
        ids = set((json.load(open(os.path.join(root, "projects", "registry.json"), encoding="utf-8")).get("projects") or {}).keys())
    except (OSError, ValueError):
        ids = set()
    return {i.lower() for i in ids} - {"agent-fabric"}


def real_date(value: str) -> bool:
    """YYYY-MM-DD and a day that exists (2026-13-45 is not one)."""
    if not DATE_RE.match(value):
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


def adr_dir(root: str) -> str:
    return os.path.join(root, ADR_DIR)


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
            m = H1_RE.match(ln)
            if m:
                out["h1"] = (m.group(1), m.group(2))
                continue
        if ln.startswith("## "):
            name = ln[3:].strip()
            out["sections"].append(name)
            in_amend = name == "Amendments"
            continue
        if not out["sections"]:
            m = FIELD_RE.match(ln)
            if m:
                out["fields"][m.group(1)] = m.group(2)
        if ANY_AMENDMENT_HEADING.match(ln):
            out["stray_amendment"] = True
        if in_amend:
            m = ROW_RE.match(ln)
            if m and not set(m.group(1)) <= {"-"}:
                out["rows"].append((m.group(1), m.group(2)))
    return out


def status_word(status: str) -> str:
    return status.split()[0] if status else ""


def pillars(root: str) -> list[str]:
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
        m = AMENDMENT_RE.match(ln)
        if m:
            out.append((m.group(1), m.group(2)))
        elif ANY_AMENDMENT_HEADING.match(ln):
            out.append(("?", ln.strip()))
    return out


def load(root: str) -> tuple[list[dict], list[str]]:
    d = adr_dir(root)
    findings: list[str] = []
    adrs = []
    if not os.path.isdir(d):
        return [], [f"{ADR_DIR}: missing"]
    for f in sorted(os.listdir(d)):
        if not f.startswith("ADR-") or f == "ADR-TEMPLATE.md":
            continue
        m = FILE_RE.match(f)
        if not m:
            findings.append(f"{ADR_DIR}/{f}: not named ADR-NNN-lowercase-kebab.md")
            continue
        a = parse_adr(os.path.join(d, f))
        a["number"], a["slug"], a["file"] = m.group(1), m.group(2), f
        adrs.append(a)
    return adrs, findings


def index_rows(root: str, adrs: list[dict]) -> list[dict]:
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


def check(root: str = ROOT) -> list[str]:
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
            m = RATIFIED_RE.match(rat)
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
            if not within(root, ev):
                findings.append(f"{rel(a)}: **Evidence:** {ev} is not a path inside the repository")
            elif not os.path.exists(os.path.join(root, ev)):
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
        entries: dict[str, dict] = {}
        cur = None
        for ln in read(dp).split("\n"):
            m = DIGEST_RE.match(ln)
            if m:
                cur = m.group(1)
                entries[cur] = {"title": m.group(2), "status": m.group(3), "dates": []}
                continue
            if ln.startswith("### "):
                cur = None
            if cur:
                am = DIGEST_AMEND_RE.match(ln)
                if am:
                    entries[cur]["dates"].append(am.group(1))
        by = {r["number"]: r for r in rows}
        for num, r in by.items():
            e = entries.get(num)
            if not e:
                findings.append(f"{ADR_DIR}/DIGEST.md: no entry '### ADR-{num} — {r['title']} ({r['status']})'")
                continue
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


def write_index(root: str = ROOT) -> None:
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


def cmd_new(root: str, slug: str, title: str) -> str:
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


def cmd_amend(root: str, num: str, title: str, date: str) -> None:
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


def cmd_lookup(root: str, words: list[str]) -> list[str]:
    text = read(os.path.join(adr_dir(root), "DIGEST.md"))
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
    at_base = {m.group(1) for f in listed.stdout.split() if (m := FILE_RE.match(f))} if listed.returncode == 0 else set()
    for sha in git("rev-list", "--reverse", "--no-merges", f"{base}..{head}").split():
        body = git("log", "-1", "--format=%B", sha)
        if re.search(r"^ADR-Editorial:\s*\S", body, re.M):
            continue
        for line in git("diff-tree", "--no-commit-id", "--name-status", "-r", "-M", sha).splitlines():
            parts = line.split("\t")
            kind = parts[0][:1]
            if kind == "M" and len(parts) == 2:
                old, new_path = parts[1], parts[1]
            elif kind == "R" and len(parts) == 3:
                old, new_path = parts[1], parts[2]
            else:
                continue
            # A source is kept verbatim: any change to one is a finding
            # (agent-fabric ADR-001 §5 rule 9).
            if new_path.startswith(f"{ADR_DIR}/sources/") or old.startswith(f"{ADR_DIR}/sources/"):
                findings.append(f"{sha[:8]}: edits {old}, a verbatim source, which is never edited")
                continue
            m = FILE_RE.match(os.path.basename(new_path))
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
            if body_changed and not row_added:
                findings.append(f"{sha[:8]}: edits the body of {new_path} with no new Amendments row and no 'ADR-Editorial:' trailer")
    return findings


def amendment_rows(text: str) -> list[tuple[str, str]]:
    """The (date, title) rows of the `## Amendments` table only."""
    rows, inside = [], False
    for ln in text.split("\n"):
        if ln.startswith("## "):
            inside = ln[3:].strip() == "Amendments"
            continue
        m = ROW_RE.match(ln) if inside else None
        if m:
            rows.append((m.group(1), m.group(2)))
    return rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="adr.py", description=__doc__.split("\n\n")[0])
    ap.add_argument("--root", default=ROOT)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check")
    p = sub.add_parser("index"); p.add_argument("--write", action="store_true", required=True)
    p = sub.add_parser("new"); p.add_argument("slug"); p.add_argument("title")
    p = sub.add_parser("amend"); p.add_argument("number"); p.add_argument("title"); p.add_argument("--date", required=True)
    p = sub.add_parser("lookup"); p.add_argument("words", nargs="+")
    p = sub.add_parser("range-check"); p.add_argument("base"); p.add_argument("head", nargs="?", default="HEAD")
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
        if not DATE_RE.match(a.date):
            raise SystemExit("adr: --date YYYY-MM-DD")
        cmd_amend(a.root, a.number, a.title, a.date); return 0
    if a.cmd == "lookup":
        hits = cmd_lookup(a.root, a.words)
        print("\n\n".join(hits) if hits else "adr: no DIGEST entry mentions all of that"); return 0 if hits else 1
    if a.cmd == "range-check":
        f = range_check(a.root, a.base, a.head)
        for x in f:
            print(f"  {x}")
        print(f"adr range-check: {'clean' if not f else f'{len(f)} commit(s) edit an ADR body unrecorded'}")
        return 1 if f else 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
