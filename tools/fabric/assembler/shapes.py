"""tools/fabric/assembler/shapes.py — corrections of a shape no author meant are refused, before the write and after it.
A part of tools/fabric/assemble.py, whose docstring is the contract.

The 2026-10-31 drain wrote three corrections that nothing refused (#437 round 5, F10-F12). A correction replaces a section
and puts its own text and title in the section's place, so a body or a title that is a truncation of what it stands for
loses the section's knowledge with no collision to ask about:

  one-word body       five corrections with the body "project" replaced five sections; the report held one applied_key.
  equal bodies        the same body written over sections that were different.
  title is a prefix   seven titles cut at 100 characters became the headings, and the full headings were gone.
  replaced heading stands after the write
                      a section a correction had replaced was in its slice again.

The first three are judged before anything is written and stop the drain like a collision does; none of them is a question
the owner can answer with a decision, because the fix is the memory's text. The last is read from the files written, since
only the writer knows what it left; it names the files already written, and the drain is discarded, as for a hygiene
failure."""
from __future__ import annotations

import glob
import json
import os
import re
import sys
from collections import defaultdict
from typing import Any
from assembler.core import layout, CLASS_FILES, Run, in_report, hygiene_substitute, patterns_for
from corrections import demote_headings, section_key
from assembler.slices import read_existing_slice, claim_heading, claim_block, undated, is_retire
from assembler.targets import existing_sections, slice_candidates


def _groups(run: Run) -> list[tuple[str | None, str, str, str, list[dict[str, Any]]]]:
    """(role or None for shared, label, class, topic, claims) for every group of the drain, in the order the collision pre-pass reads them."""
    found = [(role, role, klass, topic, group) for role, topics in run.per_role.items() for (klass, topic), group in topics.items()]
    found += [(None, "shared", klass, topic, group) for (klass, topic), group in run.shared.items()]
    return found


def claim_key(label: str, klass: str, topic: str, claim: dict[str, Any]) -> str:
    """The claim's key as the collision pre-pass prints it, so one claim has one name in every refusal."""
    return f"{label}/{klass}:{topic}#{claim_heading(claim)}@{(claim.get('evidence') or ['?'])[0][:12]}"


def _words(claim: dict[str, Any]) -> list[str]:
    """The body's words alone: the rendered block adds References, Anchors and a scope note a one-word body does not make text."""
    return undated(demote_headings(claim["body"].strip())).split()


def _earlier(run: Run) -> dict[str, list[dict[str, Any]]]:
    """The report's records of earlier corrections (applied_corrections, replaced_sections), entries that are not objects left out.
    An unreadable report has none: it is the first run's, or the drain's before these keys existed."""
    try:
        with open(layout.project_report_path(run.project), encoding="utf-8") as fh:
            report = json.load(fh)
    except (OSError, ValueError, AttributeError):
        report = {}
    return {key: [e for e in (report.get(key) or []) if isinstance(e, dict)] for key in ("applied_corrections", "replaced_sections")}


def check_correction_shapes(run: Run) -> int | None:
    """Refuse a correction whose body is one word, whose body another correction of the run, writing a different section, also
    has, or whose title is a strict prefix of the heading it replaces. Nothing is written."""
    refused: list[str] = []
    # A revert titles its claim with the heading an earlier correction replaced, which is a prefix of the lengthened heading
    # it replaces back ("The finding" for "The finding, corrected"): not a title cut short.
    undone = {(e["replaced"], e["heading"]) for e in _earlier(run)["applied_corrections"]
              if isinstance(e.get("replaced"), str) and isinstance(e.get("heading"), str)}
    corrections: list[tuple[str, str, tuple[str | None, str, str], list[str]]] = []   # key, target, (scope, class, target), words
    for role, label, klass, topic, group in _groups(run):
        present: dict[str, str] | None = None
        for claim in group:
            target = (claim.get("merge_target") or "").strip()
            if not target or is_retire(claim):
                continue
            key = claim_key(label, klass, topic, claim)
            words = _words(claim)
            if len(words) == 1:
                refused.append(f"{key}   (rule: correction body is one word)\n"
                               f"    it replaces {target!r} with the body {words[0]!r}; a correction is the section's new text, "
                               "not a label — write the whole text, or retire the section with an empty body")
            if present is None:
                present = existing_sections(slice_candidates(run, role, klass, topic))
            heading = claim_heading(claim)
            if target in present and heading != target and target.startswith(heading) and (heading, target) not in undone:
                refused.append(f"{key}   (rule: correction title is a prefix of the heading it replaces)\n"
                               f"    title {heading!r} is the first {len(heading)} of the {len(target)} characters of {target!r}; "
                               "a title cut short would become the section's heading and lose the rest")
            corrections.append((key, target, (role, klass, target), words))
    by_body: dict[tuple[str, ...], list[tuple[str, tuple[str | None, str, str]]]] = defaultdict(list)
    for key, _target, where, words in corrections:
        by_body[tuple(words)].append((key, where))
    for words, claimants in by_body.items():
        # The same body over one section twice is a correction repeated, not two sections overwritten with one text.
        if len(words) > 1 and len({where for _key, where in claimants}) > 1:
            for key, where in claimants:
                refused.append(f"{key}   (rule: correction body equals another correction's in this run)\n"
                               f"    it replaces {where[2]!r}; {len(claimants)} corrections of sections that differ carry the body "
                               f"{' '.join(words)[:80]!r}")
    # A one-word body is also "equal to another" when several share it; the single-word rule above names those already.
    if not refused:
        return None
    print("CORRECTION REFUSED — a correction has a shape that loses the section it replaces. "
          "This run wrote NOTHING and exits 1.", file=sys.stderr)
    for note in refused:
        print(f"  {note}", file=sys.stderr)
    print("\nThe memory's author fixes the memory (its body or its title); there is no decision to give.", file=sys.stderr)
    return 1


def _sections_around(path: str) -> dict[str, str]:
    """The sections of the slice file and of its budget parts `<stem>-<n>.md`, which a replacement may have left a copy in.
    A part is the file that records the same topic: `deploy-2026-09-18` is a topic of its own beside `deploy-2026-09-17`, and
    `foo-2` beside `foo` (targets.is_budget_part, which cannot be called here: the replaced heading's role and topic are not
    kept). A file that records no topic (an older slice) is read by its name, beside files that record none either."""
    directory, name = os.path.split(path)
    recorded = read_existing_slice(path)[0].get("topic")
    stem = name[:-3]
    if isinstance(recorded, str) and recorded and recorded in stem:
        # The last occurrence: a shared slice is `<class>-<topic>`, and a topic may itself be a word of the class's name.
        stem = stem[:stem.rindex(recorded) + len(recorded)]
    else:
        stem = re.sub(r"-\d+$", "", stem)
    found: dict[str, str] = {}
    for file in sorted({path, *glob.glob(os.path.join(glob.escape(directory), glob.escape(stem) + "*.md"))}):
        if file != path and not re.fullmatch(re.escape(stem) + r"-\d+\.md", os.path.basename(file)):
            continue
        meta, sections = read_existing_slice(file)
        if file == path or meta.get("topic") == recorded:
            found.update(sections)
    return found


def verify_replacements(run: Run) -> int | None:
    """After the write: a section a correction replaced is not in its slice. The writer replaces by heading, so what stands
    is a section some other claim of the drain wrote again (or an earlier run of the same drain's correction, undone by this
    run's claim), and the knowledge the correction removed is back beside its replacement."""
    standing: list[str] = []
    for key, path, target in run.replacements:
        if os.path.isfile(path) and target in _sections_around(path):
            standing.append(f"{key}   (rule: replaced heading stands after the write)\n"
                            f"    {target!r} is still a section of {in_report(run, path)}")
    # Corrections an earlier run of this drain applied, which this run may have undone: the report keeps them while they hold.
    # Only the report of this drain's own stamp: a heading reused by a later drain's claim is that drain's section, not
    # an undone correction (whether an old text is harvested back across drains is the harvest's, corrections.py).
    try:
        with open(layout.project_report_path(run.project), encoding="utf-8") as fh:
            previous = json.load(fh)
        earlier = (previous.get("applied_corrections") or []) if previous.get("stamp") == run.args.stamp else []
    except (OSError, ValueError, AttributeError):
        earlier = []
    seen = {(path, target) for _key, path, target in run.replacements}
    # A correction of this run that writes the heading back is a revert, which the earlier correction's replaced heading
    # standing again is the point of.
    reverted = {key.split("#", 1)[1].rsplit("@", 1)[0] for key, _path, _target in run.replacements}
    for entry in earlier:
        if not isinstance(entry, dict) or not isinstance(entry.get("slice"), str) or not isinstance(entry.get("replaced"), str):
            continue
        if entry["replaced"] == entry.get("heading") or entry["replaced"] in reverted:
            continue
        for base in [layout.working_copy_for(run.project), layout.FABRIC_ROOT]:
            path = os.path.join(base, entry["slice"]) if base else ""
            if path and os.path.isfile(path):
                if (path, entry["replaced"]) not in seen and entry["replaced"] in _sections_around(path):
                    standing.append(f"{entry['slice']}#{entry['replaced']}@{entry.get('memory', '?')}   "
                                    "(rule: replaced heading stands after the write)\n"
                                    f"    an earlier run of this drain replaced it ({entry.get('memory')!r}); it is a section again")
                break
    if not standing:
        return None
    print("REPLACED SECTION STANDS — a correction replaced a section and the section is in its slice again. "
          "The files of this run are WRITTEN: discard the working tree, fix the claim that wrote it back, and re-run. "
          "Exits 1.", file=sys.stderr)
    for note in standing:
        print(f"  {note}", file=sys.stderr)
    # Report() does not run after this refusal; the notes are what tells a reworded memory from a drop that failed to match.
    for note in run.reharvested_replaced:
        print(f"  {note}", file=sys.stderr)
    return 1


def report_home(run: Run, role: str | None, klass: str) -> str:
    """The class's files as the report names them, without an extension: a record keyed by it survives a flat file moving into
    its directory and a slice splitting into parts, which a slice's own path does not."""
    if role is None:
        return in_report(run, os.path.join(layout.shared_home(klass, run.project), klass))
    return in_report(run, os.path.join(layout.class_home(klass, role, run.project), CLASS_FILES[klass]))


def _in_home(home: str, path: str) -> bool:
    return path == home + ".md" or path.startswith(home + "/") or path.startswith(home + "-")


def _home_sections(home: str, project: str) -> dict[str, list[str]]:
    """Every section of the class's files at `home`, by heading, as the files hold them now."""
    found: dict[str, list[str]] = defaultdict(list)
    for base in [layout.working_copy_for(project), layout.FABRIC_ROOT]:
        if not base:
            continue
        stem = os.path.join(base, home)
        for path in sorted({*glob.glob(glob.escape(stem) + ".md"), *glob.glob(glob.escape(stem) + "/*.md"), *glob.glob(glob.escape(stem) + "-*.md")}):
            try:
                for heading, text in read_existing_slice(path)[1].items():
                    found[heading].append(text)
            except (OSError, UnicodeDecodeError):
                continue
    return found


def still_replaced(run: Run, entries: list[dict[str, str]]) -> list[dict[str, str]]:
    """The replaced texts the report keeps: one stays until its text is a section again (a revert put it back, and a pass over
    the old bundle is then the corpus's own text, a no-op) or its class has no files left."""
    kept = []
    for entry in entries:
        sections = _home_sections(entry["home"], run.project)
        if sections and not any(section_key(t) == entry["key"] for t in sections.get(entry["heading"], [])):
            kept.append(entry)
    return kept


def drop_replayed(run: Run) -> None:
    """A claim whose text an earlier replacement took out is that replacement, harvested again: a second pass over one drain's
    bundles (or a later drain over a memory nobody updated) brought the original back beside, or over, its correction
    (j82; the 2026-10-31 drain: 12 files changed by a second pass). It is not written, and the report names it
    (`superseded_harvests`) as it names a predecessor of a same-run correction. A correction whose merge_target still stands
    is a real replacement and stays: a revert is one, and the report names it (`reharvested_replaced`)."""
    earlier = _earlier(run)
    applied = earlier["applied_corrections"]
    entries = [e for e in earlier["replaced_sections"] if all(isinstance(e.get(k), str) for k in ("home", "heading", "key"))]
    # A correction applied before replaced_sections existed (one of the 2026-10-18 drain) is recorded only here: the slice it
    # wrote, the heading and the key of the text it replaced. Its home is read from the slice path, as _in_home reads it.
    legacy = [e for e in applied if all(isinstance(e.get(k), str) for k in ("slice", "replaced", "replaced_key"))]
    if not entries and not legacy:
        return
    for role, label, klass, topic, group in _groups(run):
        home = report_home(run, role, klass)
        mine = [e for e in entries if e["home"] == home] + [
            {"heading": e["replaced"], "key": e["replaced_key"]} for e in legacy if _in_home(home, e["slice"])]
        if not mine:
            continue
        present = existing_sections(slice_candidates(run, role, klass, topic))
        for claim in list(group):
            if is_retire(claim):
                continue
            key = section_key(claim_block(claim).split("\n", 1)[1].strip())
            heading = hygiene_substitute(claim_heading(claim), "replaced section heading", patterns_for(klass))[0]
            same_heading = [e for e in mine if e["heading"] == heading]
            if not same_heading:
                continue
            if "_body_as_written" in claim and not any(e["key"] == key for e in same_heading):
                # Its links were pointed at renamed topics by this run; the replaced text's key predates that.
                written = section_key(claim_block({**claim, "body": claim["_body_as_written"]}).split("\n", 1)[1].strip())
                if any(e["key"] == written for e in same_heading):
                    key = written
            where = f"{label}/{klass}:{topic}#{claim_heading(claim)}: memory {claim['topic']!r}"
            if (claim.get("merge_target") or "").strip() in present:
                # Replaying a correction after a revert and a revert's first run are one claim to the corpus: nothing in it says
                # which (the revert's own record is pruned once its text stands). Written, and said, so the pass is not silent.
                if any(e["key"] == key for e in same_heading):
                    run.reharvested_replaced.append(f"{where} re-applies a text an earlier replacement took out; written (a revert, or "
                                                    "a correction replayed after its revert)")
            elif any(e["key"] == key for e in same_heading):
                group.remove(claim)
                run.superseded_harvests.append(
                    f"{where} is text an applied correction or supersede replaced (last-drain-report.json replaced_sections or "
                    f"applied_corrections); not written — update or delete {claim['topic']!r}")
            else:
                # The heading was replaced and this text is not the text it replaced: written, and the replaced heading stands
                # again, which verify_replacements refuses for a run of this drain. Named here so the key says why it was no replay.
                run.reharvested_replaced.append(
                    f"{where} carries other text than the section {heading!r} a correction replaced (claim key {key}, replaced "
                    f"{', '.join(sorted({e['key'] for e in same_heading}))}); written")
