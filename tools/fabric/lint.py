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
import importlib.util
import json
import os
import re
import sys
from collections import defaultdict
from typing import Any

# The rule modules, a package loaded BY PATH as fabric_lint_rules, as
# launch.py loads its parts: lint runs as a script and as a module the tests
# load under another name, and a directory on sys.path would let a fixture
# fabric answer for its imports. A second lint.py in one process loads its
# own parts, never the first one's from sys.modules: the cached package is
# dropped first.
for _name in [n for n in sys.modules if n == "fabric_lint_rules" or n.startswith("fabric_lint_rules.")]:
    del sys.modules[_name]
_spec = importlib.util.spec_from_file_location(
    "fabric_lint_rules", os.path.join(os.path.dirname(os.path.realpath(__file__)), "lint_rules", "__init__.py"),
    submodule_search_locations=[os.path.join(os.path.dirname(os.path.realpath(__file__)), "lint_rules")])
sys.modules["fabric_lint_rules"] = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sys.modules["fabric_lint_rules"])
sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import roots  # noqa: E402
# Every name the parts define, from here as before: tests and the memory-write
# hook reach them as lint.<name>.
from fabric_lint_rules.base import layout, workingcopy  # noqa: E402, F401
from fabric_lint_rules.base import FRONTMATTER_RE, PAYLOAD_DIRS, _git, _tracked  # noqa: E402, F401
from fabric_lint_rules.base import sibling_working_copies  # noqa: E402, F401
from fabric_lint_rules.docs import BANNED_PATTERNS, CLASS_DOCS, DOC_PATH_EXEMPT, DOC_PATH_RE  # noqa: E402, F401
from fabric_lint_rules.docs import FABRIC_ADR_RE, FABRIC_REF_NAME, FABRIC_REF_RE, FABRIC_SELF  # noqa: E402, F401
from fabric_lint_rules.docs import GENERIC_DIRS, GENERIC_FILES, GENERIC_SKIP, HARNESS_PLACEHOLDER  # noqa: E402, F401
from fabric_lint_rules.docs import HARNESS_SOURCE, ITALIAN_MARKERS, LENS_BODY_CAP  # noqa: E402, F401
from fabric_lint_rules.docs import LENS_DESCRIPTION_CAP, LENS_NAME_RE, PROJECT_PATTERNS  # noqa: E402, F401
from fabric_lint_rules.docs import SESSION_TEMP_REFERENCE, SKILL_CUE_RE, SKILL_DATE_RE  # noqa: E402, F401
from fabric_lint_rules.docs import SKILL_PR_RE, adr_findings, agent_source_findings  # noqa: E402, F401
from fabric_lint_rules.docs import check_durable_references, class_doc_findings, doc_path_findings  # noqa: E402, F401
from fabric_lint_rules.docs import fabric_ref_findings, harness_source_findings, hygiene_findings  # noqa: E402, F401
from fabric_lint_rules.docs import client_findings, key_lineage_findings, license_findings, parse_frontmatter, project_tools_findings  # noqa: E402, F401
from fabric_lint_rules.docs import payload_shape_findings, project_name_findings  # noqa: E402, F401
from fabric_lint_rules.docs import review_lens_findings, skill_findings  # noqa: E402, F401
from fabric_lint_rules.prompts import BUDGET_TOKENS, BUDGET_TOLERANCE, CHARS_PER_TOKEN  # noqa: E402, F401
from fabric_lint_rules.prompts import HARNESS_BUDGET_TOKENS, LOCALE_BUDGET_FACTOR, LOCALE_DIRNAME  # noqa: E402, F401
from fabric_lint_rules.prompts import LOCALE_TRANSLATIONS, NON_LATIN_CHARS_PER_TOKEN  # noqa: E402, F401
from fabric_lint_rules.prompts import PLACEHOLDER_RE, PROTECTED_PATTERNS, TIER1_BUDGET_TOKENS  # noqa: E402, F401
from fabric_lint_rules.prompts import WARNINGS, WORKER_TOOL, _is_mostly_non_latin, _locale_budget  # noqa: E402, F401
from fabric_lint_rules.prompts import _protected_tokens, _source_digest, prompt_template_findings  # noqa: E402, F401
from fabric_lint_rules.prompts import protected_token_findings  # noqa: E402, F401
from fabric_lint_rules.schema import SCHEMA_KEYWORDS, _SCHEMA_MAPS, _json_equal, _json_type  # noqa: E402, F401
from fabric_lint_rules.schema import _structural_check, fabric_settings_findings, load_json  # noqa: E402, F401
from fabric_lint_rules.schema import load_schema, model_profile_findings, python_pin_findings  # noqa: E402, F401
from fabric_lint_rules.schema import schema_keyword_findings, validate_json  # noqa: E402, F401
from fabric_lint_rules.regex import regex_dollar_findings  # noqa: E402, F401
from fabric_lint_rules.shape import BASH_LINE_LIMIT, BASH_SHEBANG, _is_bash, bash_size_findings  # noqa: E402, F401
from fabric_lint_rules.shape import candidate_role_findings, host_registry_findings  # noqa: E402, F401
from fabric_lint_rules.locales import AGENT_FRONTMATTER_RE, I18N_CONTROL_RE, I18N_DEFAULT_REL  # noqa: E402, F401
from fabric_lint_rules.locales import I18N_EXTRA_PATTERNS, I18N_SCHEMA_REL, LOCALE_ENGINES  # noqa: E402, F401
from fabric_lint_rules.locales import LOCALE_FILE_OPTIONAL, LOCALE_FILE_RE, _i18n_key_re  # noqa: E402, F401
from fabric_lint_rules.locales import i18n_default_dictionary_findings, i18n_dictionary_findings  # noqa: E402, F401
from fabric_lint_rules.locales import locale_file_findings, locale_translation_findings  # noqa: E402, F401
from fabric_lint_rules.locales import locale_alignment_findings  # noqa: E402, F401
from fabric_lint_rules.locales import locale_worker_findings  # noqa: E402, F401
from fabric_lint_rules.slices import CLASS_DIRS, flat_and_dir_findings, lint_slices  # noqa: E402, F401


# What a boundary record must cite so its approval can be checked: a GZCoord
# MESSAGE-ID (a UUID), a pull request (#N or owner/repo#N), or a relay seq.
# lint cannot authenticate an approval; it refuses one nobody could look up
# (#91's review: "removed" passed as a reason).
BOUNDARY_LOCATOR = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b"
                              r"|(?:^|[\s(])(?:[\w.-]+/[\w.-]+)?#\d+\b|\bseq \d+\b", re.I)


def _boundary_record_ok(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip()) and BOUNDARY_LOCATOR.search(value) is not None


def _catalog_roles(root: str) -> set[str] | None:
    """The catalogue's role ids; None when it cannot be read, so the
    finding names the catalogue, not the role (review of #92)."""
    try:
        with open(roots.role_catalog(engine=root), encoding="utf-8") as f:
            return {r["id"] for r in json.load(f).get("roles", [])}
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None


def arm_boundary_findings(root: str, base_ref: str = "origin/main") -> list[str]:
    """A project's arm.json (fabric-pr arm's rules) names, beside
    its boundary patterns, the cases that MUST stay boundary: each case is
    a path the patterns match and the exemptions do not, and a case the
    branch forked with leaves only into boundary.retired, with why and
    whose word. And the patterns themselves change only with a new
    boundary.changes entry: the cases are a floor, and a regex can lose an
    alternative no case depends on (review of #91). Narrowing or widening
    then needs a visible record, which the fold and the blind review see;
    before, a shrunk regex failed nothing (reviews of #89 and #90)."""
    findings = []
    for rel in sorted(r for r in _tracked(root)
                      if re.fullmatch(r"projects/[^/]+/integration/gh/arm\.json", r)):
        try:
            doc = json.load(open(os.path.join(root, rel), encoding="utf-8"))
            b = doc["boundary"]
            paths = re.compile(b["paths"], re.I)
            exempt = re.compile(b["exempt"]) if b.get("exempt") else None
        except (OSError, ValueError, KeyError, TypeError, re.error) as e:
            findings.append(f"{rel}: not a usable arm.json ({type(e).__name__}: {e})")
            continue
        role = doc.get("waiver_role")
        if role is not None:
            catalogued = _catalog_roles(root)
            if catalogued is None:
                findings.append(f"{rel}: waiver_role {role!r} cannot be checked: identities/roles/catalog.json "
                                "is missing or unreadable")
            elif role not in catalogued:
                findings.append(f"{rel}: waiver_role {role!r} is not a role in identities/roles/catalog.json")
        # Every record cites an approval anyone can look up, whether or not
        # the patterns moved and whether or not there is a base to compare:
        # a record lands uncited once, and the history rule then keeps it
        # so (review of #92). Retired entries are checked again below, per
        # dropped case.
        for key in ("changes", "retired"):
            rec = b.get(key)
            if rec is not None and not isinstance(rec, dict):
                findings.append(f"{rel}: boundary.{key} must map a name to its record")
                continue
            for k, v in sorted((rec or {}).items()):
                if not _boundary_record_ok(v):
                    findings.append(f"{rel}: boundary.{key} entry {k!r} cites no approval (why, and whose word, "
                                    "citing a message id, a PR #N or a relay seq)")
        cases = b.get("cases")
        if not isinstance(cases, list) or not cases or not all(isinstance(c, str) and c for c in cases):
            findings.append(f"{rel}: boundary.cases must list the paths that must stay boundary")
            continue
        for c in cases:
            if (exempt and exempt.search(c)) or not paths.search(c):
                findings.append(f"{rel}: boundary case {c!r} is not boundary under these patterns")
        mb = _git().run(root, "merge-base", "HEAD", base_ref, check=False, timeout=60)
        since = mb.stdout.strip() if mb.returncode == 0 and mb.stdout.strip() else base_ref
        base = _git().run(root, "show", f"{since}:{rel}", check=False, timeout=60)
        # No base, no comparison, and no finding: a managed project's CI runs
        # this lint on a depth-1 checkout of the fabric at its pinned ref,
        # with no origin/main, and a finding there would fail every project
        # PR. The fabric's own CI fetches full history, so a branch here is
        # always compared (#91's review asked; carried to the next PR).
        if base.returncode == 0:
            try:
                before = json.loads(base.stdout)["boundary"].get("cases") or []
            except (ValueError, KeyError, TypeError, AttributeError):
                before = []
            try:
                base_doc = json.loads(base.stdout)
                base_b = base_doc["boundary"]
                base_role = base_doc.get("waiver_role")
            except (ValueError, KeyError, TypeError, AttributeError):
                base_b, base_role = {}, None
            # The cases are a floor, not the boundary: a regex loses an
            # alternative no case depends on, or an exemption widens, and
            # every case still matches (review of #91). So any change to the
            # patterns themselves, widening included, is recorded as a new
            # boundary.changes entry: why, and whose word.
            # Who may waive the gate loosens it as much as an exemption does:
            # a waiver_role change is a boundary change too (review of #92).
            if isinstance(base_b, dict) and (base_b.get("paths") != b.get("paths")
                                             or base_b.get("exempt") != b.get("exempt")
                                             or base_role != doc.get("waiver_role")):
                now_changes = b.get("changes") if isinstance(b.get("changes"), dict) else {}
                old_changes = base_b.get("changes") if isinstance(base_b.get("changes"), dict) else {}
                added = {k: v for k, v in now_changes.items() if k not in old_changes}
                # Every entry cites its approval (the all-records loop at
                # the top of this file's checks); here, the change needs one
                # of its own.
                if not added:
                    findings.append(f"{rel}: boundary.paths, boundary.exempt or waiver_role changed with no new "
                                    "boundary.changes entry (why, and whose word, citing a message id, a PR #N "
                                    "or a relay seq)")
            # A record is history: the approval a reviewer checked stays as it
            # was. Rewriting one would carry a new change under an old
            # citation, which the all-new-entries rule above never sees.
            for key in ("changes", "retired"):
                old_rec = base_b.get(key) if isinstance(base_b, dict) else None
                new_rec = b.get(key)
                if isinstance(old_rec, dict):
                    new_rec = new_rec if isinstance(new_rec, dict) else {}
                    for k in sorted(old_rec):
                        if new_rec.get(k) != old_rec[k]:
                            findings.append(f"{rel}: boundary.{key} entry {k!r} is "
                                            f"{'removed' if k not in new_rec else 'rewritten'}; a record "
                                            "stays as it was, and a new decision is a new entry")
            retired = b.get("retired") or {}
            for c in sorted(set(before) - set(cases)):
                why = retired.get(c) if isinstance(retired, dict) else None
                if not _boundary_record_ok(why):
                    findings.append(f"{rel}: boundary case {c!r} is dropped; a narrowing moves it to "
                                    "boundary.retired with why and whose word (the project's architect-cto), "
                                    "citing the approval: a message id, a PR #N or a relay seq")
    # A project's arm.json deleted takes its boundary, its cases and its
    # records with it, and the per-file rules above never see a file that
    # is gone (review of #92). It leaves only with its project: a removal
    # while projects/registry.json still names the project is a finding.
    # No base (a project CI's depth-1 checkout): nothing to compare.
    mb = _git().run(root, "merge-base", "HEAD", base_ref, check=False, timeout=60)
    since = mb.stdout.strip() if mb.returncode == 0 and mb.stdout.strip() else ""
    if since:
        listed = _git().run(root, "ls-tree", "-r", "--name-only", since, "--", "projects/", check=False, timeout=60)
        before = {r for r in listed.stdout.splitlines()
                  if re.fullmatch(r"projects/[^/]+/integration/gh/arm\.json", r)} if listed.returncode == 0 else set()
        now = {r for r in _tracked(root) if re.fullmatch(r"projects/[^/]+/integration/gh/arm\.json", r)}
        removed = sorted(before - now)
        try:
            with open(roots.projects_registry(engine=root), encoding="utf-8") as fh:
                registered = set((json.load(fh).get("projects") or {}))
        except (OSError, ValueError, AttributeError) as e:
            # Unknown is not "no project": an unreadable registry would
            # let every deletion through (review of #96).
            if removed:
                findings.append(f"projects/registry.json: unreadable ({type(e).__name__}), so the deletion of "
                                f"{', '.join(removed)} cannot be judged")
            registered = set()
            removed = []
        for rel in removed:
            project = rel.split("/")[1]
            if project in registered:
                findings.append(f"{rel}: deleted while projects/registry.json still names {project!r}; a project's arm "
                                "rules leave only with the project (its boundary, cases and records go with the file)")
    return findings


def arm_declared_findings(root: str) -> list[str]:
    """Every project in projects/registry.json has an arm.json. Without one
    fabric-pr arm refuses to arm any PR of the project ("the security
    boundary cannot be judged"), which a project learns only when its first
    PR is ready; arm_boundary_findings above checks the files that exist and
    never sees the one that was not written."""
    try:
        with open(roots.projects_registry(engine=root), encoding="utf-8") as fh:
            registered = sorted((json.load(fh).get("projects") or {}))
    except (OSError, ValueError, AttributeError):
        # An unreadable registry is host_registry_findings' and the
        # registry's own checks' to report; naming every project missing
        # from a registry nobody could read would bury that.
        return []
    tracked = _tracked(root)
    if not tracked:
        return []   # not a git checkout: nothing is tracked, so absence proves nothing
    declared = {r.split("/")[1] for r in tracked
                if re.fullmatch(r"projects/[^/]+/integration/gh/arm\.json", r)}
    return [f"projects/registry.json: project {p!r} has no projects/{p}/integration/gh/arm.json; "
            "fabric-pr arm refuses to arm a PR of a project whose security boundary it cannot read"
            for p in registered if p not in declared]

# What a role IS, never a contributor's to commit (ADR-018 §5 rule 8): a rule
# ending in "/" is a directory, any other one file, as in an entry. The
# guards and what they import (git.py) or run in CI (the suite runners and
# the helper they source); the definitions; runtime/claude-code/ whole — the
# reviewer's agent file, the harness hooks and the settings that register
# them, the workspace prompt, and what installs them; the role, routing,
# prompt and review-brief code (review and re-review of #75).
CONTRIBUTOR_NEVER = (
    "identities/", "routing/", "policies/", "communication/gzcoord/protocol/", "docs/adr/", "memory/",
    ".agent-fabric/", ".github/", "CLAUDE.md",
    "tools/fabric/guards/", "tools/fabric/git.py", "tools/fabric/lint.py", "tools/fabric/lint_rules/",
    # Loaded by lint by path: a contributor who made one answer clean would
    # weaken lint without touching it (review of #106).
    "tools/fabric/layout.py", "tools/fabric/workingcopy.py", "tools/fabric/adr.py", "tests/run.sh", "tests/static.sh",
    "tools/fabric/secretstore/lineage.py", "tests/test_lineage_fence.py",
    "tests/test_contributors.py", "tests/test_agent_fabric_dir_authority.py", "tests/test_charter_authority.py",
    "tests/leak-check.sh", "runtime/identity.py", "runtime/claude-code/",
    "bin/fabric-role", "tools/fabric/role.py", "tools/fabric/routing.py", "tools/fabric/launch_prompt.py",
    "bin/fabric-review", "tools/fabric/review_brief.py",
    # Runs as root on every host and installs the interpreter every tool runs on.
    "tools/fabric/python_pin.py", "runtime/python.json",
    # Wires the fleet's hooks into a session started in this clone.
    ".claude/", "tools/fabric/fabric_settings.py",
    # Bootstrap runs it as every account, and it rewrites ~/.claude.json.
    "tools/fabric/workspace_trust.py",
    # Bootstrap and the agent files it installs, ported out of runtime/claude-code/ (ADR-040).
    "tools/fabric/bootstrap.py", "tools/fabric/fabric_writes.py", "tools/fabric/install_agent_files.py",
    # Writes and reads each agent's private conversational history (ADR-041).
    "tools/fabric/episodic.py", "tools/fabric/episodic_import.py", "tools/fabric/relay.py", "tools/fabric/history.py", "bin/fabric-history",
    # Reads the relay as the account, with its token, and prints what it finds.
    "tools/fabric/relay_catchup.py",
    # Derives a re-review's brief, as review_brief.py renders one.
    "tools/fabric/review_rounds.py",
)
# The one path under a never-prefix an entry may name: the list the port
# shrinks, which lint itself holds to shrinking (ADR-040 §5 rule 2).
CONTRIBUTOR_MAY = ("policies/bash-allowlist.json",)


def _rule_covers(rule: str, path: str) -> bool:
    return path.startswith(rule) if rule.endswith("/") else path == rule


def contributor_rule_findings(paths: list[str], excluding: list[str]) -> list[str]:
    """Each never-path a rule reaches, compared as prefixes rather than by
    sample files (review of #75): a rule inside a never-prefix is refused
    outright; a rule above one is refused unless an exclusion covers it."""
    out = []
    for r in paths:
        if r in CONTRIBUTOR_MAY:
            continue
        for n in CONTRIBUTOR_NEVER:
            inside = _rule_covers(n, r)
            above = r.endswith("/") and n.startswith(r) and not any(_rule_covers(e, n) for e in excluding)
            if inside or above:
                out.append(f"rule {r!r} reaches {n}")
    return out


def contributor_findings(root: str) -> list[str]:
    """policies/authority.json `contributors`: each entry is whole
    (contributors.py drops a half-written one, which then admits nothing —
    said here rather than found at a refused commit), names a catalogued role
    other than the owner, and reaches nothing in CONTRIBUTOR_NEVER."""
    path = roots.policy("authority.json", engine=root)
    try:
        text = open(path, encoding="utf-8").read()
        doc = json.loads(text)
    except FileNotFoundError:
        return []
    except ValueError as e:
        return [f"policies/authority.json: not JSON ({e})"]
    raw = doc.get("contributors", [])
    if not isinstance(raw, list):
        return ["policies/authority.json: `contributors` is not a list"]
    spec = importlib.util.spec_from_file_location(
        "fabric_contributors", os.path.join(os.path.dirname(os.path.abspath(__file__)), "guards", "contributors.py"))
    co = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(co)
    whole = co.contributors_of(text)
    findings = []
    catalogued: set[str] | None
    try:
        catalogued = {r["id"] for r in json.load(open(roots.role_catalog(engine=root),
                                                        encoding="utf-8"))["roles"]}
    except (OSError, ValueError, KeyError, TypeError) as e:
        catalogued = None
        if raw:
            findings.append(f"identities/roles/catalog.json: unreadable ({e}), so no contributor's role can be checked")
    owner = (doc.get("role_definitions") or {}).get("role")
    seen: set[str] = set()
    for i, e in enumerate(raw):
        role = e.get("role") if isinstance(e, dict) else None
        # Each entry judged on its own: a malformed one beside a whole entry
        # of the same role was dropped by contributors_of and passed unsaid.
        alone = co.contributors_of(json.dumps({"contributors": [e]}))
        if isinstance(role, str) and role in seen:
            findings.append(f"policies/authority.json: contributors[{i}] ({role}): a second entry for the role — "
                            "one entry per role")
            continue
        if isinstance(role, str):
            seen.add(role)
        if not isinstance(role, str) or role not in alone:
            findings.append(f"policies/authority.json: contributors[{i}]: not a whole entry (a role, a non-empty "
                            "list of paths, a list of exclusions, `merges` a boolean when present) — it admits nothing")
            continue
        where = f"policies/authority.json: contributors[{i}] ({role})"
        if role == owner:
            findings.append(f"{where}: the owner role needs no entry")
        if catalogued is not None and role not in catalogued:
            findings.append(f"{where}: not in identities/roles/catalog.json")
        for f in contributor_rule_findings(whole[role]["paths"], whole[role]["excluding"]):
            findings.append(f"{where}: {f}, which defines what a role is or enforces the fence (ADR-018 §5 rule 8)")
    return findings


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
    # A broken list withholds nothing: a finding, and nothing is judged
    # clean against it (layout.HygieneError names the file and the entry).
    hygiene_projects = sorted(set(layout.list_projects()) | set(layout.explicit_working_copies()))
    try:
        BANNED_PATTERNS[:] = layout.load_hygiene_patterns(hygiene_projects)
        # A project's own slices are held to its set: its "scope": "others"
        # names are its own to say there, and withheld everywhere else.
        PROJECT_PATTERNS.clear()
        PROJECT_PATTERNS.update({pid: layout.load_hygiene_patterns(hygiene_projects, for_project=pid)
                                 for pid in hygiene_projects})
    except layout.HygieneError as exc:
        findings.append(str(exc))

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
    projects_root = roots.projects_dir(engine=root)
    project_ids: list[str] = []
    taxonomy_roles: dict[str, set[str]] = {}   # project id -> the roles its taxonomy binds
    registry_ids: list[str] = []
    try:
        registry_ids = sorted((json.load(open(roots.projects_registry(engine=root), encoding="utf-8"))
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
            where = (f"projects/{pid}/taxonomy.json" if tax_path.startswith(roots.operator_root(engine=root))
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
    findings += client_findings(root)
    findings += project_tools_findings(root)

    # --- the class list a reader sees --------------------------------------
    findings += class_doc_findings(root)
    findings += agent_source_findings(root)
    findings += skill_findings(root)

    # --- the hosts and where each account lives -----------------------------
    findings += host_registry_findings(root)
    findings += key_lineage_findings(root)

    # --- no project's name in a generic file --------------------------------
    findings += project_name_findings(root)

    # --- bash over 150 lines only where the allowlist says (ADR-040) ---------
    findings += bash_size_findings(root)
    findings += regex_dollar_findings(root)
    findings += arm_boundary_findings(root)
    findings += arm_declared_findings(root)

    # --- a session started in this clone gets the workspace's hooks ---------
    findings += fabric_settings_findings(root)

    # --- the pinned Python: checkable, and what CI runs (ADR-040) ------------
    findings += python_pin_findings(root)

    # --- every schema checkable without jsonschema (the pinned Python) -------
    findings += schema_keyword_findings(root)

    # --- a contributor's entry never reaches a definition (ADR-018) ---------
    findings += contributor_findings(root)

    # --- the review lenses ---------------------------------------------------
    findings += review_lens_findings(root)

    findings += i18n_default_dictionary_findings()

    # --- routing profiles --------------------------------------------------
    profiles_schema = load_schema(root, os.path.join("routing", "schemas"), "model-profiles")
    profiles_path = roots.routing_profiles(engine=root)
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
        findings += locale_alignment_findings(role, role_path)
        for rel in identity_slices[role]:
            klass = (parse_frontmatter(open(layout.fabric_path(rel), encoding="utf-8").read()) or {}).get("class")
            if klass not in layout.IDENTITY_CLASSES:
                findings.append(f"{rel}: class {klass!r} is knowledge, not identity — it belongs under memory/")
    for role in known_roles - set(role_ids):
        findings.append(f"identities/roles/catalog.json: role {role!r} has no identities/roles/{role}/ directory")

    # --- domain memory -----------------------------------------------------
    domain_slices: dict[str, list[str]] = {}
    domains_root = roots.memory_dir("domains", engine=root)
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
            fabric_side = {layout.link_rel(layout.fabric_path(r), pid): r
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
                m = re.fullmatch(r"^- \[`([^`]+)`\]\(([^)]+)\) — (.*)$", line)
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
    findings += doc_path_findings()

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
