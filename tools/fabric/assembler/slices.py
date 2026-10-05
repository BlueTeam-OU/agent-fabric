"""tools/fabric/assembler/slices.py — a slice file read, its sections edited, the corpus's collisions and the drain report merged.
A part of tools/fabric/assemble.py, whose docstring is the contract."""
from __future__ import annotations

import json
import os
import re
from typing import Callable, Any
from assembler.core import layout, yaml_scalar


REPORT_LISTS = ("files", "hygiene_problems", "rejected_hygiene", "redactions", "retired_in_siblings",
                "oversized_claims", "clipped_descriptions", "migrated", "merge_target_unresolved")


def merge_reports(previous: dict[str, Any], current: dict[str, Any],
                  exists: Callable[[str], bool] = lambda _path: True) -> dict[str, Any]:
    """The drain report this run leaves, given the one already on disk.

    A drain across accounts is one run per bundle into the same working
    copy, and each run rewrote the report whole: the committed report
    described the last bundle alone, every earlier run's decisions, roles,
    moves and files gone, and an index-only run (no claims) wrote empty
    watermarks (a drain's blind review, 2026-09-25). A report of the SAME
    stamp is therefore the same drain and is merged into: roles and
    shared topics unioned, the lists appended without repeats, one
    decision per key (the later run's, as the tree now reflects it), the
    telemetry kept per source (agent@host) so re-running a bundle
    replaces its counts instead of adding them twice. A report of another
    stamp is an earlier drain, replaced — except its watermarks: each says
    where one account's store (agent@host) was read up to. A run replaces
    only the marks of the stores it harvested, with what that harvest
    says — lower too, since the harvester holds a mark below a memory it
    could not render yet, so the memory is read again — and a run that
    harvested nothing changes none. `title_collisions` is read from the tree,
    which already holds every run's result.

    The harvest record is kept per source too (`harvest_sources`), since
    each bundle read its own host's store; `harvest` stays the latest
    run's, for a reader of one. `files` keeps only what `exists` finds:
    a later run of the stamp may retire or move a file an earlier run
    wrote, and a report naming it counted it in `files_written` (a
    drain's blind review, 2026-09-26)."""
    marks = {h: v for h, v in (previous.get("watermarks") or {}).items() if isinstance(v, (int, float))}
    for host, mark in (current.get("watermarks") or {}).items():
        marks[host] = mark
    if previous.get("stamp") != current["stamp"]:
        merged = dict(current, watermarks=marks)
        merged["files"] = [f for f in current["files"] if exists(f)]
        merged["files_written"] = len(merged["files"])
        return merged
    merged = dict(current, watermarks=marks)
    merged["roles"] = sorted(set(previous.get("roles") or []) | set(current["roles"]))
    merged["shared_topics"] = sorted(set(previous.get("shared_topics") or []) | set(current["shared_topics"]))
    merged["shared_slices"] = len(merged["shared_topics"])
    for key in REPORT_LISTS:
        seen = list(previous.get(key) or [])
        seen += [item for item in current.get(key) or [] if item not in seen]
        merged[key] = seen
    merged["files"] = [f for f in merged["files"] if exists(f)]
    merged["files_written"] = len(merged["files"])
    decisions = {d.get("key"): d for d in previous.get("collision_decisions") or [] if isinstance(d, dict)}
    for d in current["collision_decisions"]:
        decisions.pop(d["key"], None)
        decisions[d["key"]] = d
    merged["collision_decisions"] = list(decisions.values())
    sources = dict(previous.get("telemetry_sources") or {})
    sources.update(current["telemetry_sources"])
    merged["telemetry_sources"] = sources
    telemetry: dict[str, dict[str, Any]] = {}
    for per_role in sources.values():
        for role, counts in (per_role or {}).items():
            into = telemetry.setdefault(role, {})
            for name, value in (counts or {}).items():
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    into[name] = into.get(name, 0) + value
                else:
                    into.setdefault(name, value)
    merged["telemetry"] = telemetry
    if current.get("harvest") is None:
        merged["harvest"] = previous.get("harvest")
    harvests = dict(previous.get("harvest_sources") or {})
    harvests.update(current.get("harvest_sources") or {})
    merged["harvest_sources"] = harvests
    return merged


def scan_collisions(dirs: list[str], rel: Callable[[str], str] = layout.root_rel) -> list[str]:
    """Report title collisions still recorded in the committed corpus.

    Read from the `collisions` frontmatter the assembler writes, not from the
    shape of the headings: an authored document may legitimately contain "X"
    and "X (2)", and so may a claim whose real title ends that way. Reading a
    recorded fact keeps the warning alive across drains that admit nothing —
    the file states it — without inventing one where nothing collided.
    """
    found: list[str] = []
    for base in dirs:
        for dirpath, _dirnames, filenames in os.walk(base):
            for name in sorted(filenames):
                if not name.endswith(".md"):
                    continue
                path = os.path.join(dirpath, name)
                meta, _sections = read_existing_slice(path)
                for title in meta.get("collisions", []) or []:
                    found.append(
                        f"{rel(path)}: {title!r} appears twice "
                        "— set merge_target to resolve"
                    )
    return sorted(found)


def decode_scalar(text: str) -> str:
    """Undo what `yaml_scalar` did.

    A value with punctuation is written JSON-quoted, so reading it back by
    stripping the outer quotes leaves the escapes behind. For a field that is
    unioned across drains — collisions — that means the same title returns
    slightly more escaped every cycle and accumulates a fresh entry each time,
    without bound.
    """
    text = text.strip()
    if text.startswith('"'):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text.strip('"')
    return text


def retire_in_siblings(directory: str, filename: str, target: str,
                       clip: Callable[[str, str], str] = lambda d, _where: d,
                       stem: str | None = None,
                       is_part: Callable[[str], bool] | None = None) -> list[tuple[str, str]]:
    """Remove the section `target` (and its "(n)" siblings) from every
    OTHER budget part of the same topic in `directory`. `filename` is the
    part being written: `<topic>.md`, `<topic>-<n>.md`,
    `<class>-<topic>(-n).md` for a shared slice, or the flat `<class>.md`.
    Returns what was touched: (path, "rewritten" | "removed").

    The frontmatter is kept VERBATIM and edited textually — the
    `collisions:` list loses the target, the `description:` follows the
    first remaining heading — never parsed and re-rendered: the parser
    reads every scalar as a string, and a round trip wrote `tier: "2"`,
    which the schema refuses (review, 2026-09-20). A part left with no
    section is removed; the index sweep then stops pointing at an empty
    file whose cue named the section that moved.

    `stem` and `is_part`, when the caller knows the topic, say which
    files are its parts: read off the file name alone, a separate topic
    named `<topic>-2` is a part of `<topic>`, and `<topic>-2.md` as that
    topic's part one is a part of `<topic>` too."""
    if stem is None:
        stem = re.sub(r"(-\d+)?\.md$", "", filename)
    if is_part is None:
        def is_part(path: str) -> bool:
            return bool(re.fullmatch(re.escape(stem) + r"-\d+\.md", os.path.basename(path)))
    touched: list[tuple[str, str]] = []
    for name in sorted(os.listdir(directory)) if os.path.isdir(directory) else []:
        if name == filename or not name.endswith(".md"):
            continue
        if name != f"{stem}.md" and not is_part(os.path.join(directory, name)):
            continue
        path = os.path.join(directory, name)
        _meta, sections = read_existing_slice(path)
        victims = [h for h in sections if h == target or re.fullmatch(re.escape(target) + r" \(\d+\)", h)]
        if victims:
            touched.append((path, remove_sections(path, victims, [target], clip)))
    return touched


def remove_sections(path: str, victims: list[str], resolved: list[str],
                    clip: Callable[[str, str], str] = lambda d, _where: d) -> str:
    """Remove the sections `victims` from the slice at `path`; the titles
    in `resolved` leave its `collisions:` record. Returns "removed" when
    no section is left (the file goes), else "rewritten". The frontmatter
    is edited textually — see retire_in_siblings for why."""
    _meta, sections = read_existing_slice(path)
    for h in victims:
        sections.pop(h, None)
    if not sections:
        os.remove(path)
        return "removed"
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    front = m.group(1) if m else ""
    # collisions: drop the resolved entries; drop the key when empty.
    def prune(block: str) -> str:
        lines = [ln for ln in block.split("\n")]
        kept = [ln for ln in lines[1:] if decode_scalar(ln.strip()[2:]) not in resolved]
        return "\n".join([lines[0]] + kept) if kept else ""
    # (?m) alone: with (?s) the item pattern ran to the end of the
    # frontmatter, the list never read as empty, and a bare
    # `collisions:` key was left behind.
    front = re.sub(r"(?m)^collisions:\n((?:  - .*\n?)+)", lambda mm: (prune(mm.group(0).rstrip("\n")) + "\n") if prune(mm.group(0).rstrip("\n")) else "", front + "\n").rstrip("\n")
    first = next(iter(sections))
    # The cue is clipped as every description the assembler writes is.
    front = re.sub(r"(?m)^description: .*$", "description: " + yaml_scalar(clip(first, path)), front, count=1)
    body = "\n\n".join(f"## {h}\n\n{t}" for h, t in sections.items()) + "\n"
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(("---\n" + front + "\n---\n\n" + body).rstrip() + "\n")
    return "rewritten"


def read_existing_slice(path: str) -> tuple[dict[str, Any], dict[str, str]]:
    """Return (frontmatter, {heading: section-text}) for a slice already on disk.

    Merge mode needs the previous drain's claims back in hand: a drain writes
    only what it admitted this cycle, so rendering that alone would silently
    delete everything earlier cycles had learned.
    """
    if not os.path.exists(path):
        return {}, {}
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    meta: dict[str, Any] = {}
    match = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    body = text
    if match:
        body = text[match.end():]
        current = None
        for line in match.group(1).split("\n"):
            stripped = line.strip()
            if line.startswith("  - ") and current:
                item = line[4:].strip()
                # `origin` is a list of small mappings (agent or clone_id,
                # host, project, working_copy). Keeping it is what makes a
                # carried claim still say who produced it and where — the
                # audit trail has to survive the drain that inherits the
                # section, not just the one that wrote it.
                if current == "origin" and ":" in item:
                    k, _, v = item.partition(":")
                    meta.setdefault("origin", []).append({k.strip(): decode_scalar(v)})
                else:
                    meta.setdefault(current, []).append(decode_scalar(item))
            elif current == "origin" and line.startswith("    ") and ":" in stripped and meta.get("origin"):
                k, _, v = stripped.partition(":")
                meta["origin"][-1][k.strip()] = decode_scalar(v)
            elif ":" in line and not line.startswith(" "):
                key, _, value = line.partition(":")
                current = key.strip()
                value = value.strip()
                meta[current] = [] if value == "" else decode_scalar(value)
    sections: dict[str, str] = {}
    for part in re.split(r"^## ", body, flags=re.M)[1:]:
        heading, _, rest = part.partition("\n")
        sections[heading.strip()] = rest.strip()
    return meta, sections


OBSERVED_RE = re.compile(r"\s*\*Observed (\d{4}-\d{2}-\d{2})(?: \(([a-z0-9-]+)\))?\*\s*$")


def undated(text: str) -> str:
    """A section's text with its dated tail removed — the identity a
    section is compared by. The date is when the memory was written, not
    what it says: the same claim re-emitted with a moved mtime, or
    arriving with a date where the corpus has none, is the same claim,
    and a comparison that included the tail refused it as a collision
    with two identical excerpts (review of 2026-09-20, F1)."""
    return OBSERVED_RE.sub("", text).strip()


def claim_heading(claim: dict[str, Any]) -> str:
    """The section heading a claim renders under — one rule, used by the
    writer, the budget and the collision pre-pass alike."""
    return (claim.get("title") or claim["topic"].replace("-", " ").capitalize()).strip()


SECTION_BREAK = re.compile(r"(?m)^## ")


BODY_HEADING = re.compile(r"(?m)^(#{2,})(?=[ \t]|$)")


def demote_headings(text: str) -> str:
    """Every heading of level two or deeper one level down. A slice's
    sections are its `## ` lines — read_existing_slice splits there — so
    a claim body that keeps the `## ` headings its memory had opened
    sections of its own: the first part lost its dated footer, and
    re-assembling the same bundle was refused as a collision with itself
    (a drain's blind review, 2026-09-25). Fenced code is demoted too: the
    reader does not know fences, and a split inside one is the same break."""
    return BODY_HEADING.sub(r"#\1", text)


def absorbed(sections: dict[str, str], claim: dict[str, Any]) -> list[str]:
    """The sections that are this claim as a slice written BEFORE body
    headings were demoted holds it: its own heading and the sections its
    `## ` lines opened after it, when together — rejoined, demoted, with
    whitespace and date aside — they are the claim's rendering. Empty when
    they are not. Such a slice is only recognised when its claim arrives
    again; until then its split sections stand as they were read, and the
    next write of the claim puts it back together."""
    heading = claim_heading(claim)
    count = len(SECTION_BREAK.findall(claim["body"]))
    keys = list(sections)
    if not count or heading not in sections:
        return []
    start = keys.index(heading)
    following = keys[start + 1:start + 1 + count]
    if len(following) < count:
        return []
    joined = sections[heading] + "".join(f"\n\n## {h}\n\n{sections[h]}" for h in following)
    rendered = undated(claim_block(claim).split("\n", 1)[1])
    if " ".join(undated(demote_headings(joined)).split()) != " ".join(rendered.split()):
        return []
    return [heading] + following


def claim_block(claim: dict[str, Any]) -> str:
    title = claim_heading(claim)
    body = demote_headings(claim["body"].strip())
    cites = claim.get("citations") or {}
    flat = [c for values in cites.values() for c in values]
    tail = ""
    if flat:
        tail = "\n\n*References: " + ", ".join(sorted(set(flat))) + "*"
    # WHEN the fact was written, and by which role. Two sections on one
    # topic that disagree — a workflow that changed — read in time order
    # only if each carries its date; the slice's distilled_at is the last
    # drain's, not the fact's. The role, never the login: a slice travels
    # into every repository.
    if claim.get("observed_at"):
        who = f" ({claim['_role']})" if claim.get("_role") else ""
        tail += f"\n\n*Observed {claim['observed_at']}{who}*"
    scope = ""
    if claim.get("knowledge_scope") == "domain-only":
        scope = "\n\n> Learned outside this system; it describes the field, not our implementation.\n"
    return f"## {title}\n{scope}\n{body}{tail}\n"
