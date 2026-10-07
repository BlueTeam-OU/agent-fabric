"""tools/fabric/lint_rules/slices.py — the slice walk: every knowledge slice judged, and the flat-file against directory rule.
A part of tools/fabric/lint.py, the entry point."""
from __future__ import annotations

import os
import re
from typing import Any

from .base import FRONTMATTER_RE, PAYLOAD_DIRS, layout
from .docs import ITALIAN_MARKERS, PROJECT_PATTERNS, hygiene_findings, parse_frontmatter
from .prompts import (
    BUDGET_TOKENS,
    BUDGET_TOLERANCE,
    CHARS_PER_TOKEN,
    LOCALE_DIRNAME,
    TIER1_BUDGET_TOKENS,
    _is_mostly_non_latin,
)
from .schema import validate_json


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
            if approx > budget * BUDGET_TOLERANCE:
                findings.append(f"{rel}: ~{approx} tokens exceeds the {budget} budget; split the slice")
            findings += hygiene_findings(rel, body, PROJECT_PATTERNS.get(project) if project else None)
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
