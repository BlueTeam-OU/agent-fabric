"""tools/fabric/assembler/links.py — the links of the slices a run wrote, resolved against the corpus the reader has.
A part of tools/fabric/assemble.py, whose docstring is the contract.

Nothing else in the drain looks at a `[[link]]` or a `*References:*` topic, so a link to a memory that was never drained, into
another project's corpus or to a misspelled name shipped silently (blueteam.ee #16 F3; InterWeave #529 round 1 F2). This reports,
never rewrites: the author or the owner decides what a dead link should have been.

A name resolves by a slice's file name, as targets.written_stem builds it, or by its `topic:`; a shared slice is also known without its class prefix.
A project slice reads its own project's corpus and the fabric's; a field slice (`memory/`) is copied into every repository and
reads the fabric's alone, so a link from it to a project's slice is dead anywhere but where that slice is.
"""
from __future__ import annotations

import os
import re

from assembler.core import layout, CLASS_FILES
from assembler.slices import parse_slice

LINK_RE = re.compile(r"\[\[([^\]\n]+)\]\]")
REFERENCES_RE = re.compile(r"^\*References: (.*)\*$", re.M)
FENCE_RE = re.compile(r"^(?P<fence>`{3,}|~{3,}).*?^(?P=fence)[ \t]*$", re.M | re.S)
# A span closes on a run of the same length as the one that opened it (CommonMark), so ``a ` b`` is one span.
SPAN_RE = re.compile(r"(?<!`)(`+)(?!`)(.+?)(?<!`)\1(?!`)", re.S)
CLASS_PREFIX = tuple(f"{k}-" for k in CLASS_FILES)

UNDRAINED = "undrained"
OTHER_CORPUS = "other corpus"
NO_SUCH_TOPIC = "no such topic"


def without_code(text: str) -> str:
    """The text with fenced blocks and inline code spans blanked: a `[[x]]` written there is an example, not a citation."""
    text = FENCE_RE.sub(lambda m: "\n" * m.group(0).count("\n"), text)
    # An unclosed fence quotes everything after it.
    unclosed = re.search(r"^(`{3,}|~{3,})", text, re.M)
    if unclosed:
        text = text[:unclosed.start()]
    return SPAN_RE.sub(lambda m: " " * len(m.group(0)), text)


def names_in(root: str) -> set[str]:
    """Every name a link into the slices under `root` may use: a slice's file name and topic, and a shared slice's without its class."""
    found: set[str] = set()
    for _dir, _dirs, files in os.walk(root):
        for name in files:
            if not name.endswith(".md") or name == "INDEX.md":
                continue
            stem = name.removesuffix(".md")
            found.add(stem)
            # An unsplit class file is named for its class (targets.written_stem); the topic is what a link names.
            try:
                with open(os.path.join(_dir, name), encoding="utf-8") as fh:
                    head = fh.read(4096)
            except (OSError, UnicodeDecodeError):
                head = ""
            topic = re.match(r'---\n(?:.*\n)*?topic: "?([^"\n]+)"?\n', head)
            if topic:
                found.add(topic.group(1))
            if stem.startswith(CLASS_PREFIX):
                found.add(stem.split("-", 1)[1])
    return found


def links_of(text: str) -> list[tuple[str, str, str]]:
    """(heading, target, where) for every link and References topic of a slice's sections, in order, each once."""
    _meta, sections = parse_slice(text)
    seen: set[tuple[str, str]] = set()
    found: list[tuple[str, str, str]] = []
    for heading, body in sections.items():
        for target in LINK_RE.findall(without_code(body)):
            if (heading, target.strip()) not in seen:
                seen.add((heading, target.strip()))
                found.append((heading, target.strip(), "link"))
        for line in REFERENCES_RE.findall(body):
            for topic in (t.strip() for t in line.split(",")):
                if topic and (heading, topic) not in seen:
                    seen.add((heading, topic))
                    found.append((heading, topic, "references"))
    return found


def unresolved_links(files: list[str], bases: list[str], fabric_root: str, project_root: str, other_roots: list[str],
                     undrained: set[str]) -> list[dict[str, str]]:
    """One row per link or References topic of `files` (slices, named as the report names them) that no corpus its reader
    has answers: {slice, heading, target, why, in}. `bases` are what a file's name is relative to. `project_root` is the project's `.agent-fabric/memory`; a file under
    `fabric_root/memory` is a field slice."""
    fabric = names_in(os.path.join(fabric_root, "memory"))
    project = names_in(project_root) if os.path.isdir(project_root) else set()
    elsewhere: set[str] = set()
    for root in other_roots:
        if os.path.isdir(root):
            elsewhere |= names_in(root)
    rows: list[dict[str, str]] = []
    for rel in sorted(set(files)):
        if not rel.endswith(".md") or os.path.basename(rel) == "INDEX.md":
            continue
        path = next((p for p in (os.path.join(b, rel) for b in bases) if os.path.isfile(p)), None)
        if path is None:
            continue
        try:
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
        except (OSError, UnicodeDecodeError):
            continue
        is_field = os.path.abspath(path).startswith(os.path.abspath(os.path.join(fabric_root, "memory")) + os.sep)
        reads = fabric if is_field else fabric | project
        unreachable = (project | elsewhere) if is_field else elsewhere
        for heading, target, source in links_of(text):
            if target in reads:
                continue
            if target in unreachable:
                why = OTHER_CORPUS
            elif target in undrained or target.removesuffix(".md") in undrained:
                why = UNDRAINED
            else:
                why = NO_SUCH_TOPIC
            rows.append({"slice": rel, "heading": heading, "target": target, "why": why, "in": source})
    return rows
