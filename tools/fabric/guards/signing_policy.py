"""tools/fabric/guards/signing_policy.py — policies/signing.json read one way for
its three readers: bootstrap (the git settings a working copy signs with), the
checker (ban_unsigned_commits.py: which format a repository admits and from
which commit rule 5 applies) and lint (agent-fabric ADR-057 §5 rules 1, 3, 5).

CONTRACT
  file      {"default": {"format", "since"}, "repositories": {"<owner>/<name>":
            {"format"?, "since"?}}}; identities/schemas/signing.schema.json is
            its shape. A repository entry's missing key is the default's.
  format    "ssh" | "openpgp": the one format git signs in there and the one
            the checker admits.
  since     the full sha, on the repository's default branch, that ends the
            old signing: it and what it reaches keep their signatures, rule 5
            judges everything else. null: not cut over, nothing is refused
            under rule 5.
  covered   a repository is covered when an entry names it, by any of its
            project's registry remotes (projects/registry.json); an uncovered
            one gets the default and bootstrap leaves its working copies'
            settings alone.
  errors    PolicyError, the message the whole answer: a policy that cannot
            be read is never read as "no policy".

Standard library and workingcopy.parse_remote only (both fenced from
contributors, tools/fabric/lint.py CONTRIBUTOR_NEVER): what decides whether a
commit is refused is not a contributor's to change."""
from __future__ import annotations

import json
import os
import re
from typing import Any

FORMATS = ("ssh", "openpgp")
SHA_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
SLUG_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")
FLEET_DEFAULT = {"format": "ssh", "since": None}
# Where fabric-sign's proofs are kept as notes (signing/notes.py REF); bootstrap
# removes a notes.rewriteRef naming it (rule 4).
NOTES_REF = "refs/notes/fabric-ots"


class PolicyError(Exception):
    """The message is the whole answer."""


def load(path: str) -> dict[str, Any]:
    """The policy at `path`; an absent file is the fleet default with no
    repository covered (nothing configured, nothing refused)."""
    if not os.path.exists(path):
        return {"default": dict(FLEET_DEFAULT), "repositories": {}}
    try:
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, ValueError) as e:
        raise PolicyError(f"{path} cannot be read ({type(e).__name__}: {e})") from None
    problems = shape_problems(doc)
    if problems:
        raise PolicyError(f"{path}: {problems[0]}")
    return doc


def _entry_problems(where: str, entry: object, *, partial: bool) -> list[str]:
    if not isinstance(entry, dict):
        return [f"{where} is not an object"]
    out = [f"{where}: unknown key {k!r}" for k in sorted(entry) if k not in ("format", "since")]
    if not partial:
        out += [f"{where}: no {k}" for k in ("format", "since") if k not in entry]
    if "format" in entry and entry["format"] not in FORMATS:
        out.append(f"{where}: format {entry['format']!r} is not one of {', '.join(FORMATS)}")
    if "since" in entry and entry["since"] is not None and not (isinstance(entry["since"], str) and SHA_RE.match(entry["since"])):
        out.append(f"{where}: since {entry['since']!r} is neither null nor a full lowercase commit sha")
    return out


def shape_problems(doc: object) -> list[str]:
    """What the schema says, said again here: the checker and bootstrap run
    on the pinned Python without jsonschema, and must not act on a policy
    lint would refuse."""
    if not isinstance(doc, dict):
        return ["not an object"]
    out = [f"unknown key {k!r}" for k in sorted(doc) if k not in ("$schema", "description", "default", "repositories")]
    out += _entry_problems("default", doc.get("default"), partial=False)
    default = doc.get("default")
    if isinstance(default, dict) and default.get("since") is not None:
        # A sha is one repository's cut-over; as the default it would apply to
        # every repository no entry names, whose history it is not on.
        out.append("default: since must be null (a cut-over commit belongs to one repository)")
    repos = doc.get("repositories", {})
    if not isinstance(repos, dict):
        return out + ["repositories is not an object"]
    for slug, entry in sorted(repos.items()):
        if not SLUG_RE.match(slug):
            out.append(f"repositories: {slug!r} is not <owner>/<name>")
        out += _entry_problems(f"repositories[{slug}]", entry, partial=True)
    return out


def slug_of(url: str | None, parse_remote) -> str | None:
    """`owner/name` of a remote URL, as GitHub names it: the path, no .git."""
    parsed = parse_remote(url) if url else None
    path = (parsed or {}).get("path") or ""
    return path if SLUG_RE.match(path) else None


def _project_slugs(slug: str, registry: dict[str, Any], parse_remote) -> list[str]:
    """Every slug of the project `slug` belongs to (its registry remotes,
    the moved names included); [slug] when no project has it."""
    for entry in (registry.get("projects") or {}).values():
        slugs = [s for s in (slug_of(u, parse_remote) for u in entry.get("remotes") or []) if s]
        if slug.lower() in (s.lower() for s in slugs):
            return slugs
    return [slug]


def entry_for(policy: dict[str, Any], slug: str | None, registry: dict[str, Any], parse_remote) -> tuple[str | None, dict[str, Any]]:
    """(the covering key or None, {"format", "since"}) for a repository."""
    default = {**FLEET_DEFAULT, **(policy.get("default") or {})}
    if not slug:
        return None, default
    repos = policy.get("repositories") or {}
    by_lower = {k.lower(): k for k in repos}
    for candidate in _project_slugs(slug, registry, parse_remote):
        key = by_lower.get(candidate.lower())
        if key is not None:
            return key, {**default, **repos[key]}
    return None, default
