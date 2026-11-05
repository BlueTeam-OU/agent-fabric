"""tools/fabric/github/arm_rules.py — the project's rules for arm and the
gates that are plain reads of the PR body or of arm.json: the two exception
classes the arm gates raise, the owner's-word phrase, the AWAITING-SUPPLY
and Class: lines, the arm.json loader, and what a record PR is (read by arm
and by pr-gate alike, so the two never disagree on one). Split out of
arm.py; the contract and the order of the gates are that module's header."""
from __future__ import annotations

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
import gh  # noqa: E402
from github import common  # noqa: E402


class Refused(Exception):
    """Gate refusal: exit 1."""


class Unanswered(Exception):
    """A question nobody could answer, or usage: exit 2."""


def has_owner_word(basis: str) -> bool:
    # A fixed phrase, not any sentence with "owner" in it ("the owner has
    # not been asked yet" is not consent — a managed project's PR #894 review): straight
    # or curly apostrophe.
    return re.search(r"owner('|’)s word", basis, re.I) is not None


def has_no_ci_word(basis: str) -> bool:
    # A word of its own, not a longer form of the owner's word: "owner's word" must not lift the checks gate, and this
    # one must not lift the count gate (has_owner_word's pattern does not match it, and that is kept).
    return re.search(r"owner('|’)s no-CI word", basis, re.I) is not None


def head_lines(lines: list[str], n: int = 3) -> str:
    """The first n, as `head -3 | tr '\\n' ' '` wrote them."""
    return "".join(f"{l} " for l in lines[:n])


def config_path() -> str:
    return common.project_config_path("AGENT_FABRIC_ARM_CONFIG", "arm.json")


def load_config(path: str) -> tuple[re.Pattern, re.Pattern | None, dict[str, re.Pattern], str | None]:
    if not path:
        raise Unanswered("no project found for this working copy, so no arm.json to read the security boundary from"
                         " (projects/<id>/integration/gh/arm.json in agent-fabric, or AGENT_FABRIC_ARM_CONFIG)")
    try:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
        b = doc["boundary"]
        paths = re.compile(b["paths"], re.I)
        exempt = re.compile(b["exempt"]) if b.get("exempt") else None
        classes = {str(k).lower(): re.compile(v) for k, v in (doc.get("classes") or {}).items()}
        waiver_role = doc.get("waiver_role")
        if waiver_role is not None and not (isinstance(waiver_role, str) and waiver_role.strip()):
            raise TypeError("waiver_role is not a role's slug")
        # The project's own statement of what must stay boundary: a case the
        # patterns no longer match is a boundary narrowed by mistake, and
        # arming on it would judge with rules the project did not mean
        # (lint holds the same, and that no case is dropped unretired).
        missed = [c for c in (b.get("cases") or []) if (exempt and exempt.search(c)) or not paths.search(c)]
    except FileNotFoundError:
        raise Unanswered(f"this project declares no arm.json ({path}); the security boundary cannot be judged") from None
    except (OSError, ValueError, KeyError, TypeError, AttributeError, re.error) as e:
        raise Unanswered(f"{path} is not a usable arm.json ({type(e).__name__}: {e})") from None
    if missed:
        raise Unanswered(f"{path}: boundary case(s) not boundary under its own patterns — {', '.join(missed[:3])}"
                         " — the security boundary cannot be judged")
    return paths, exempt, classes, waiver_role


def unmet_supply(body: str) -> list[str]:
    """Each AWAITING-SUPPLY login with no `<sha>..<sha>: <login>` range
    line in the body — the reading fabric-pr owed-supply makes."""
    out = []
    for line in body.split("\n"):
        m = re.match(r"^\s*-?\s*AWAITING-SUPPLY:\s*(\S+)", line)
        if not m:
            continue
        who = m.group(1).split("/")[-1]
        if not re.search(r"[0-9a-f]{7,40}\.\.[0-9a-f]{7,40}:\s*" + re.escape(who) + r"([^A-Za-z0-9_-]|$)", body):
            out.append(who)
    return out


def stated_class(body: str, classes: dict[str, re.Pattern]) -> str:
    if not classes:
        return ""
    names = "|".join(re.escape(c) for c in sorted(classes, key=len, reverse=True))
    for line in body.split("\n"):
        m = re.match(r"^[\s*_-]*Class:[\s*_]*(" + names + ")", line, re.I)
        if m:
            return m.group(1).lower()
    return ""


# ── the record path (agent-fabric ADR-019 §5 rule 1, A 2026-11-05) ────


RECORD_NOTE = "Record path: no review-class review (agent-fabric ADR-019 rule 1, A 2026-11-05)"
# The one mode a record has: a regular file. The rule names the executable mode (100755) as what sends a file to a
# PR; a symlink (120000) or a submodule (160000) named like a record is no record either, and falls back to the
# review gate, which is the safe side of the question.
RECORD_MODE = "100644"


def load_record_rules(path: str) -> tuple[re.Pattern, re.Pattern | None] | None:
    """arm.json's direct.record_paths and direct.pr_paths, case-insensitive as pre-push reads pr_paths, or None for a
    project that names no record path. Unanswered when the file or a pattern cannot be read."""
    try:
        with open(path, encoding="utf-8") as fh:
            direct = json.load(fh).get("direct") or {}
        if not isinstance(direct, dict) or not direct.get("record_paths"):
            return None
        return (re.compile(direct["record_paths"], re.I),
                re.compile(direct["pr_paths"], re.I) if direct.get("pr_paths") else None)
    except FileNotFoundError:
        # load_config has already refused a missing arm.json at this path, so here the rules came from elsewhere (a
        # loader replaced in a test). No record path is the side that keeps every gate.
        return None
    except (OSError, ValueError, TypeError, AttributeError, re.error) as e:
        raise Unanswered(f"{path}: direct.record_paths cannot be read ({type(e).__name__}: {e})") from None


def head_modes(repo: str, head: str, paths: list[str]) -> dict[str, str | None]:
    """Each path's git mode in the tree of commit `head` on GitHub, None where the path is not there. Walked one
    directory at a time, never ?recursive=1, whose answer GitHub cuts on a large tree. Unanswered when a tree cannot
    be read whole: a mode that cannot be read is never taken for a regular file."""
    trees: dict[str, dict] = {}

    def listing(sha: str) -> dict:
        if sha not in trees:
            try:
                t = gh.api(f"repos/{repo}/git/trees/{sha}")
            except gh.GhError as e:
                raise Unanswered(f"cannot read the tree {sha[:8]} of {repo} to tell a record's mode ({e.reason})") from None
            if not isinstance(t, dict) or t.get("truncated") is not False or not isinstance(t.get("tree"), list):
                raise Unanswered(f"the tree {sha[:8]} of {repo} did not read whole: a record's mode cannot be told")
            trees[sha] = {e.get("path"): e for e in t["tree"] if isinstance(e, dict)}
        return trees[sha]

    modes: dict[str, str | None] = {}
    for path in paths:
        sha, entry = head, None
        for part in path.split("/"):
            if sha is None:
                entry = None
                break
            entry = listing(sha).get(part)
            sha = entry.get("sha") if entry and entry.get("type") == "tree" else None
        modes[path] = str(entry.get("mode")) if entry else None
    return modes


def record_pr(listed: list[dict], rules: tuple[re.Pattern, re.Pattern | None] | None, boundary: re.Pattern,
              exempt: re.Pattern | None, modes) -> tuple[bool, str]:
    """(True, "") when the pull request whose files GitHub lists as `listed` is a record PR: every name it changes (a
    rename by both) matches record_paths, none matches pr_paths or the security boundary (paths minus exempt), and
    every file it leaves at the head is a regular file (`modes(paths)`, head_modes, asked only once the names
    qualify). Otherwise (False, why not). The caller decides only on a direct repository."""
    if rules is None:
        return False, "this project's arm.json names no direct.record_paths"
    record, pr_paths = rules
    names = [f.get("filename", "") for f in listed] + [f["previous_filename"] for f in listed if f.get("previous_filename")]
    if not names:
        return False, "it changes no file"
    for n in names:
        if not record.search(n):
            return False, f"{n} is not a record (direct.record_paths)"
        if pr_paths and pr_paths.search(n):
            return False, f"{n} matches direct.pr_paths"
        if not (exempt and exempt.search(n)) and boundary.search(n):
            return False, f"{n} is inside the security boundary"
    # A removed file has no mode at the head; a rename's old name is judged by its name alone.
    kept = [f.get("filename", "") for f in listed if f.get("status") != "removed"]
    for n, mode in (modes(kept) if kept else {}).items():
        if mode != RECORD_MODE:
            return False, f"{n} has mode {mode or 'unknown'} at the head, not a regular file's {RECORD_MODE}"
    return True, ""
