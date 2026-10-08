#!/usr/bin/env python3
"""runtime/github/scan-semantic-collisions.sh [--root <dir>]

Detect SEMANTIC collisions between parallel contributions that a
textually-clean git merge cannot flag.

Sessions coordinate only through origin and allocate sequence numbers
independently, so two branches can each mint the same number in
DIFFERENT files — a migration, a decision record — or write the
byte-identical heading into the same file, and merge with zero
conflicts: the merged tree is broken while git reports success.

Checks, over the merged tree, as the project's collisions.json says:
  1. In each numbered family (a directory and a file-name pattern), no
     two files carry the same number.
  2. No file of the amendment set holds two identical amendment
     headings: amendments are cited by heading, and byte-identical
     headings from parallel sessions make every reference point at both.

On a hit, the fix is to RENUMBER YOUR OWN (newer) entry past the one
that reached origin first — never to delete or renumber work that
already landed. Run it after folding origin/main into your branch and
before pushing: that is the moment the collision exists and the moment
it is cheapest to fix.

  --root <dir>   the repository to scan (default: the working
                 directory's toplevel)
  -h, --help     this text

The project's rules: projects/<id>/integration/gh/collisions.json in
agent-fabric, for the project --root's working copy belongs to, or the
file AGENT_FABRIC_COLLISIONS_CONFIG names.

Exit codes:
  0  no collisions
  1  one or more collisions found
  2  invocation problem (a required directory missing, no config)
"""
# The docstring is --help, whole. Ported from two managed projects'
# tools/checks/scan_semantic_collisions.sh (ADR-040; both tests, run
# unchanged against the shim, the oracle): one scan, each project's
# families, headings and wording in its own config.
#
# THE CONTRACT, frozen from devex-tooling's port contract 6/8 and its
# ruling of 2026-10-08:
#   argv    [--root <dir>] [-h|--help], cli_root's refusals, exit 2.
#   config  {"required": [dir, …], "families": [{dir, pattern, message,
#           advice}], "amendments": {files: [{dir, pattern, optional}],
#           heading, advice}, "footer": [line, …]}. A pattern is a regex
#           over the file name; a family's has one group, the number,
#           compared as TEXT ("014" and "0014" are different numbers).
#           "{number}" in a message and "{hits}" in the footer are filled.
#   stdout  per collision "FAIL: <message>", its detail lines indented
#           three spaces, a blank line; then the footer, exit 1; else the
#           OK line, exit 0.
#   stderr  "scan_semantic_collisions: <why>", exit 2.
# Departures from both copies, agreed with devex-tooling: files listed in
# bytewise order, every member of a number listed (the bash's
# "<N>_*.sql" dropped a "0014.sql"); headings joined by " | " (one copy's
# `tr '\n' ' | '` joined with one space, the other's with "|").
from __future__ import annotations

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from github.cli_root import Refused, parse_root, project_config, toplevel  # noqa: E402

PROG = "scan_semantic_collisions"
SETTING = "AGENT_FABRIC_COLLISIONS_CONFIG"
# head -3 of the duplicated headings, as both copies cut it.
HEADINGS_SHOWN = 3


def config_path(root: str) -> str:
    return project_config(root, "collisions.json", SETTING)


def load_config(path: str, root: str) -> dict:
    if not path:
        raise Refused(f"no collisions config for {root} (projects/<id>/integration/gh/collisions.json in agent-fabric,"
                      f" or {SETTING})")
    try:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
        cfg = {
            "required": [str(d) for d in doc.get("required", [])],
            "families": [{"dir": f["dir"], "pattern": re.compile(f["pattern"]), "message": f["message"],
                          "advice": f["advice"]} for f in doc.get("families", [])],
            "amendments": None,
            "footer": [str(l) for l in doc["footer"]],
        }
        a = doc.get("amendments")
        if a:
            cfg["amendments"] = {"files": [{"dir": f["dir"], "pattern": re.compile(f["pattern"]),
                                            "optional": bool(f.get("optional"))} for f in a["files"]],
                                 "heading": re.compile(a["heading"].encode()), "advice": a["advice"]}
        for f in cfg["families"]:
            if f["pattern"].groups != 1:
                raise ValueError(f"family {f['dir']}: its pattern needs exactly one group, the number")
    except (OSError, ValueError, KeyError, TypeError, AttributeError, re.error) as e:
        raise Refused(f"cannot read {path}: {e}") from None
    return cfg


def _names(directory: str) -> list[str]:
    """The directory's entries, bytewise sorted; a missing one is empty."""
    try:
        return sorted(os.listdir(directory), key=os.fsencode)
    except (FileNotFoundError, NotADirectoryError):
        return []


def family_hits(root: str, family: dict) -> list[tuple[str, list[str]]]:
    by_number: dict[str, list[str]] = {}
    for name in _names(os.path.join(root, family["dir"])):
        m = family["pattern"].search(name)
        if m:
            by_number.setdefault(m.group(1), []).append(name)
    return [(family["message"].replace("{number}", n), [" ".join(files), family["advice"]])
            for n, files in sorted(by_number.items(), key=lambda kv: os.fsencode(kv[0])) if len(files) > 1]


def amendment_hits(root: str, amendments: dict) -> list[tuple[str, list[str]]]:
    hits = []
    for spec in amendments["files"]:
        directory = os.path.join(root, spec["dir"])
        if not os.path.isdir(directory):
            # An optional directory belongs to a layout some trees predate
            # (a history/ split, say); any other is part of the scan, and
            # scanning nothing there would be a silent pass.
            if spec["optional"]:
                continue
            raise Refused(f"expected path not found: {directory}")
        for name in _names(directory):
            path = os.path.join(directory, name)
            if not spec["pattern"].search(name) or not os.path.isfile(path):
                continue
            # Bytes, as grep reads them: a heading is compared whole,
            # whatever its encoding.
            with open(path, "rb") as fh:
                lines = fh.read().split(b"\n")
            seen: dict[bytes, int] = {}
            for line in lines:
                if amendments["heading"].search(line):
                    seen[line] = seen.get(line, 0) + 1
            dups = sorted(line for line, n in seen.items() if n > 1)
            if dups:
                shown = " | ".join(d.decode("utf-8", "surrogateescape") for d in dups[:HEADINGS_SHOWN])
                hits.append((f"identical amendment headings in {name} — cross-references are ambiguous.",
                             [shown, amendments["advice"]]))
    return hits


def scan(root: str, cfg: dict) -> int:
    for d in cfg["required"]:
        path = os.path.join(root, d)
        if not os.path.exists(path):
            raise Refused(f"expected path not found: {path}")
    hits = []
    for family in cfg["families"]:
        hits += family_hits(root, family)
    if cfg["amendments"]:
        hits += amendment_hits(root, cfg["amendments"])
    for message, details in hits:
        print(f"FAIL: {message}")
        for line in details:
            print(f"   {line}")
        print()
    if hits:
        for line in cfg["footer"]:
            print(line.replace("{hits}", str(len(hits))))
        return 1
    print(f"{PROG}: OK — no numbering collisions in the merged tree.")
    return 0


def main() -> int:
    # A file name or heading that is not UTF-8 is printed as its bytes.
    sys.stdout.reconfigure(encoding="utf-8", errors="surrogateescape")
    sys.stderr.reconfigure(encoding="utf-8", errors="surrogateescape")
    try:
        root = parse_root(sys.argv[1:])
        if root is None:
            print(__doc__.strip("\n"))
            return 0
        root = root or toplevel()
        return scan(root, load_config(config_path(root), root))
    except Refused as e:
        print(f"{PROG}: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
