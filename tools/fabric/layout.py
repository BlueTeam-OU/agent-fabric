#!/usr/bin/env python3
"""tools/fabric/layout.py — where each kind of knowledge lives.

One module answers "where is it" so the activator, assembler, linter and
query tool agree by construction:

    identities/roles/<role>/            charter.md, recall.md, skills/, commands/
    memory/domains/<domain>/            domain slices (reusable field knowledge)
    memory/shared/                      multi-owner field slices
    memory/agents/<login>/              knowledge genuinely tied to one agent

    <working copy>/.agent-fabric/memory/<role>/
                                        PROJECT knowledge: solution, intersection,
                                        rationale, workflow, threads, crossref.json,
                                        INDEX.md — and shared/ for multi-owner
                                        project slices
    <working copy>/.agent-fabric/roles/<role>.md
                                        the role's REMIT in that project: which
                                        surfaces, stack and rules the function
                                        covers there. The charter here is the
                                        function; the remit is the project's,
                                        authored, and loads at activation with it.

Project knowledge lives IN THE PROJECT'S REPOSITORY, not here. A `solution`
slice describes the tree as of a date and loses to the tree; the only way it
stays honest is to be versioned with the tree, so a change that moves the
architecture can update the slice in the same commit series, and a checkout
at any commit carries the knowledge that was true then. It also keeps a
project's confidential knowledge under the project's own license and
access, and leaves this repository plainly Apache-2.0.

`.agent-fabric/` in a managed repository is fabric-coordinator's to write
(policies/AUTHORITY.md): the drain writes it, every other role reads it.

The working copy for a project comes from, in order: an explicit
`set_working_copy()` (a tool's --working-copy); for agent-fabric as a
managed project of its own, this checkout, whatever else names another; then
`$AGENT_FABRIC_WORKING_COPY`, and the agent's runtime binding (the
session-start hook records the working copy it started in). Links written
into a project's INDEX.md are relative to the working copy root; a
fabric-side slice (charter, domain, memory/shared) is linked as
`../agent-fabric/<path>`, the sibling-checkout layout every adapter already
assumes.

A project's memory is never under this repository: `memory/projects/`
was the pre-migration location, honoured by a runtime branch until
2026-09-16 (no project had used it for days; lint refuses the directory).

Domain ids currently equal role ids: the extracted corpus filed domain
knowledge per role, and renaming domains was not part of the extraction.
A domain may be split or renamed later without touching this contract.
"""
from __future__ import annotations

import json
import os
import sys

FABRIC_ROOT = os.environ.get("AGENT_FABRIC_ROOT") or os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import roots  # noqa: E402

# The project-side directory, and how a project's INDEX.md reaches back
# into this repository.
PROJECT_DIRNAME = ".agent-fabric"
# The literal rather than PROJECT_DIRNAME: the seam scan
# (tests/test_roots_seam.py) tells a project's own .agent-fabric/ tree
# from the operator's corpus by that literal in the join. Both name the
# same directory.
PROJECT_MEMORY_SUBDIR = os.path.join(".agent-fabric", "memory")
PROJECT_ROLES_SUBDIR = os.path.join(PROJECT_DIRNAME, "roles")
FABRIC_LINK_PREFIX = "../agent-fabric"
FABRIC_PROJECT_ID = "agent-fabric"

# charter: the function; brief: how the role works day to day, in any
# project (written by fabric-coordinator from the holders' own accounts,
# 2026-09-15, and read to every session in its launch prompt); recall:
# where its knowledge lives. All three are authored, never distilled.
IDENTITY_CLASSES = ("charter", "brief", "recall")
# The sections every launch prompt carries after the role's own files:
# identities/prompt/<name>.md, plain markdown with `{role}` substituted.
# Not slices — no frontmatter, no provenance, no index line — so lint
# checks them by name (`prompt_template_findings`).
PROMPT_DIR_NAME = os.path.join("identities", "prompt")
PROMPT_TEMPLATES = ("team.md", "memory.md")            # appended after the role's files, in this order
# Every template under identities/prompt/ and the placeholders each must
# carry: the header names the login; the shared sections the role; the
# missing-brief line none. launch_prompt.py renders them; lint budgets them
# together — every session pays for these bytes (the header and the
# missing-brief line were code until 2026-09-17, and always paid).
PROMPT_TEMPLATE_PLACEHOLDERS = {"header.md": ("{agent}", "{host}", "{role}"), "brief-missing.md": ("{role}",),
                                "team.md": ("{role}",), "memory.md": ("{role}",)}
# 1800 until 2026-09-18, when the owner's two rules on who owns a change
# and when a PR is armed joined team.md: ~200 tokens every session pays
# so that no holder has to learn them from a message.
PROMPT_TEMPLATE_BUDGET_TOKENS = 2500   # 2100 until 2026-09-19: one open PR per agent and its exceptions, and the clean-up-after-tests rule joined team.md (the owner); MAX_CHARS in launch_prompt.py moves with it
DOMAIN_CLASSES = ("domain",)
PROJECT_CLASSES = ("solution", "intersection", "rationale", "workflow", "threads")
# Tier-1 knowledge, in load order: the charter, the project index, the
# project workflow slices. Everything else waits for a cue from the index.
TIER1 = ("charter.md", "INDEX.md", "workflow")

_WORKING_COPIES: dict[str, str] = {}


def memory_slug(directory: str) -> str:
    """The name Claude Code gives a launch directory under
    ~/.claude/projects/: the absolute path with every character that is
    not a letter or a digit turned into `-` — `/` and `.` alike, read
    back on 2026-09-17 (`~/projects/foo.bar` is `-home-…-projects-foo-bar`).
    Two directories that differ only in such a character share a slug;
    the harness does not tell them apart either. One rule, used by the
    harvester, fabric-status, the control plane and the launch prompt."""
    import re
    return re.sub(r"[^A-Za-z0-9]", "-", os.path.abspath(directory))


def default_memory_dir(working_copy: str) -> str:
    """The memory directory Claude Code keeps for a launch directory. A
    location, not an identity — the same agent has one such directory per
    directory it has launched from."""
    return os.path.expanduser(f"~/.claude/projects/{memory_slug(working_copy)}/memory")


def project_ids() -> list[str]:
    """Every project the registry knows, sorted — the set whose hygiene
    lists a slice is held to, since a slice travels into every one."""
    try:
        with open(roots.projects_registry(engine=FABRIC_ROOT), encoding="utf-8") as fh:
            return sorted((json.load(fh).get("projects") or {}).keys())
    except (OSError, ValueError):
        return []


def roles_dir() -> str:
    return roots.roles_dir(engine=FABRIC_ROOT)


def prompt_dir() -> str:
    return os.path.join(FABRIC_ROOT, PROMPT_DIR_NAME)


def prompt_template_path(name: str) -> str:
    return os.path.join(prompt_dir(), name)


def role_dir(role: str) -> str:
    return os.path.join(roles_dir(), role)


def catalog_path() -> str:
    return roots.role_catalog(engine=FABRIC_ROOT)


def list_roles() -> list[str]:
    base = roles_dir()
    if not os.path.isdir(base):
        return []
    return sorted(d for d in os.listdir(base)
                  if os.path.isfile(os.path.join(base, d, "charter.md")))


def domain_dir(domain: str) -> str:
    return roots.memory_dir("domains", domain, engine=FABRIC_ROOT)


def shared_dir() -> str:
    return roots.memory_dir("shared", engine=FABRIC_ROOT)


def agent_memory_dir(agent: str) -> str:
    return roots.memory_dir("agents", agent, engine=FABRIC_ROOT)


# --- project homes ----------------------------------------------------------

def set_working_copy(project: str, path: str | None) -> None:
    """Tell the layout where a project's working copy is for this run."""
    if path:
        _WORKING_COPIES[project] = os.path.abspath(path)
    else:
        _WORKING_COPIES.pop(project, None)


def _binding_working_copy(project: str) -> str | None:
    """The working copy this agent's runtime binding names, if it is for
    `project` (runtime/identity.py owns where the binding lives)."""
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "fabric_identity", os.path.join(FABRIC_ROOT, "runtime", "identity.py"))
        identity = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(identity)  # type: ignore[union-attr]
        binding = identity.read_binding() or {}
    except Exception:  # noqa: BLE001
        return None
    if binding.get("project") == project and binding.get("working_copy"):
        return binding["working_copy"]
    return None


def explicit_working_copies() -> dict[str, str]:
    """The working copies this run was told about (set_working_copy)."""
    return dict(_WORKING_COPIES)


def working_copy_for(project: str) -> str | None:
    """The checkout holding `project`'s .agent-fabric/, if this run knows one."""
    if project in _WORKING_COPIES:
        return _WORKING_COPIES[project]
    # The fabric's own .agent-fabric/ is in the checkout that is running,
    # never the one a session is bound to: from a worktree of the fabric the
    # binding named the main clone, and lint read the worktree's index
    # against it as drift (python-dev-01, seq 10894).
    if project == FABRIC_PROJECT_ID:
        return FABRIC_ROOT
    env = os.environ.get("AGENT_FABRIC_WORKING_COPY")
    if env and _project_of_env_working_copy(env) == project:
        return os.path.abspath(env)
    bound = _binding_working_copy(project)
    if bound:
        return bound
    return None


def _project_of_env_working_copy(path: str) -> str | None:
    """$AGENT_FABRIC_WORKING_COPY names a directory, not a project; resolve
    it through the registry the same way the session-start hook does."""
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "fabric_workingcopy", os.path.join(FABRIC_ROOT, "tools", "fabric", "workingcopy.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        return mod.resolve(path).get("project")
    except Exception:  # noqa: BLE001
        return None


def project_memory_root(project: str) -> str:
    """The directory holding <role>/ subtrees for a project."""
    wc = working_copy_for(project)
    if not wc:
        raise LookupError(
            f"project {project!r}: no working copy known (its memory lives in the project's "
            f"repository under {PROJECT_MEMORY_SUBDIR}/); pass --working-copy, set "
            "AGENT_FABRIC_WORKING_COPY, or activate from inside the working copy")
    return os.path.join(wc, PROJECT_MEMORY_SUBDIR)


def project_remit_path(project: str, role: str) -> str | None:
    """The role's authored remit in the project's working copy, if the
    working copy is known (None otherwise; a project need not have one)."""
    wc = working_copy_for(project)
    return os.path.join(wc, PROJECT_ROLES_SUBDIR, f"{role}.md") if wc else None


def project_taxonomy_path(project: str) -> str | None:
    """A project's binding rules (which roles apply to which paths and
    keywords): <working copy>/.agent-fabric/taxonomy.json when the working
    copy is known, else projects/<id>/taxonomy.json here (the fabric's own,
    or a project not yet moved). None when neither exists."""
    wc = working_copy_for(project)
    if wc:
        candidate = os.path.join(wc, PROJECT_DIRNAME, "taxonomy.json")
        if os.path.isfile(candidate):
            return candidate
    here = os.path.join(roots.projects_dir(engine=FABRIC_ROOT), project, "taxonomy.json")
    return here if os.path.isfile(here) else None


def project_hygiene_path(project: str) -> str | None:
    """A project's own banned-pattern list, in its working copy: what must
    never appear in a slice because it names the deployment, a sibling
    project, or anything else that is that project's to keep. The fabric
    carries only the generic patterns (credentials, language)."""
    wc = working_copy_for(project)
    return os.path.join(wc, PROJECT_DIRNAME, "hygiene.json") if wc else None


class HygieneError(ValueError):
    """A hygiene list that cannot be read or is malformed. It withholds
    nothing, so nothing may proceed as if it did: skipped, it once let
    every name it lists into the corpus without a word."""


HYGIENE_ENTRY_KEYS = {"pattern", "label", "flags", "refer_as", "scope"}


def load_hygiene_patterns(projects: list[str] | None = None, for_project: str | None = None) -> list[tuple]:
    """Compiled (pattern, label, refer_as) triples: the generic ones, the
    fabric's own list (policies/hygiene.json), then every listed project's
    (from <working copy>/.agent-fabric/hygiene.json, when that working copy
    is known). Entries: {"pattern": <regex>, "label": <what it is>,
    "flags": "i"?, "refer_as": <what the corpus says instead>?,
    "scope": "others"?}. The assembler replaces a hit with refer_as, or
    "[redacted]" without one; lint refuses a committed hit either way.

    "scope": "others" marks a name that is the listing project's own: it
    is withheld from the fabric's slices and from every other project's,
    and allowed in that project's own. `for_project` names the project
    whose slices the patterns are for: its own "others" entries are left
    out. Without it every entry applies, everywhere (the strictest set).

    A list that exists but cannot be read, does not parse, or holds an
    entry that is not a pattern this reads raises HygieneError, naming the
    file and the entry: an absent list is no list, a broken one is an
    error."""
    import re
    # Secrets by shape: known token prefixes, key material, and any
    # password / api key / token ASSIGNED a value that looks like one (a
    # sentence about a token is fine; `token=abc123…` is not). A finding
    # here is a leak into every clone that installs the payload.
    out: list[tuple] = [
        (re.compile(r"\bghp_[A-Za-z0-9]{10,}"), "credential", None),
        (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"), "credential", None),
        (re.compile(r"\bsk-[A-Za-z0-9-]{20,}"), "credential", None),
        (re.compile(r"\bxox[bp]-[A-Za-z0-9-]{10,}"), "credential", None),
        (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "credential (AWS access key)", None),
        (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "credential (private key)", None),
        (re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"), "credential (JWT)", None),
        (re.compile(r"\bdp\.(?:st|pt|sa|ct|scim|audit)\.[A-Za-z0-9_.-]{10,}"), "credential (Doppler token)", None),
        (re.compile(r"\bBearer\s+[A-Za-z0-9_\-.=]{20,}"), "credential (bearer token)", None),
        (re.compile(r"(?i)\b(?:api[_-]?key|secret[_-]?key|client[_-]?secret|password|passwd|auth[_-]?token|access[_-]?token|api[_-]?token|token|secret)\s*[:=]\s*[\"']?(?![\"']?[<$%{]|[\"']?(?:redacted|none|null|\.\.\.|xxx+))[A-Za-z0-9_\-./+]{8,}"),
         "credential (a password, key or token assigned a value)", None),
    ]
    # The fabric's own list first (policies/hygiene.json: people by role,
    # never by name — a privacy rule, so it holds in every project), then
    # each project's.
    sources: list[tuple[str, str, str | None]] = [
        (roots.policy("hygiene.json", engine=FABRIC_ROOT), "fabric hygiene", None)]
    for pid in projects or []:
        path = project_hygiene_path(pid)
        if path:
            sources.append((path, f"{pid} hygiene", pid))
    for path, default_label, owner in sources:
        if not os.path.lexists(path):
            continue
        try:
            with open(path, encoding="utf-8") as fh:
                doc = json.load(fh)
        except OSError as exc:
            raise HygieneError(f"{path}: cannot be read ({exc.strerror or exc})") from None
        except ValueError as exc:
            raise HygieneError(f"{path}: does not parse ({exc})") from None
        if not isinstance(doc, dict) or not isinstance(doc.get("patterns"), list):
            raise HygieneError(f"{path}: not an object with a \"patterns\" list")
        for i, entry in enumerate(doc["patterns"]):
            where = f"{path}: patterns[{i}]"
            if not isinstance(entry, dict):
                raise HygieneError(f"{where} is not an object")
            unknown = sorted(set(entry) - HYGIENE_ENTRY_KEYS)
            if unknown:
                raise HygieneError(f"{where} has keys this does not read: {', '.join(unknown)}")
            pattern = entry.get("pattern")
            if not isinstance(pattern, str) or not pattern:
                raise HygieneError(f"{where} has no pattern")
            for key in ("label", "flags", "refer_as"):
                if entry.get(key) is not None and not isinstance(entry[key], str):
                    raise HygieneError(f"{where}: {key} is not a string")
            if entry.get("flags") not in (None, "", "i"):
                # "I" or "x" was read as no flag: a pattern meant to ignore
                # case let every other casing through.
                raise HygieneError(f"{where}: flags is {entry['flags']!r}; the one flag is \"i\"")
            scope = entry.get("scope")
            if scope is not None and scope != "others":
                raise HygieneError(f"{where}: scope is {scope!r}; the one scope is \"others\"")
            if scope == "others" and owner is None:
                raise HygieneError(f"{where}: scope \"others\" belongs in a project's list, not the fabric's")
            try:
                compiled = re.compile(pattern, re.I if "i" in (entry.get("flags") or "") else 0)
            except re.error as exc:
                raise HygieneError(f"{where}: the pattern does not compile ({exc})") from None
            if scope == "others" and owner == for_project:
                continue   # this project's own name, in this project's own slices
            out.append((compiled, entry.get("label") or default_label, entry.get("refer_as")))
    return out


def project_link_root(project: str) -> str:
    """The directory INDEX.md links for this project are relative to."""
    return working_copy_for(project) or FABRIC_ROOT


def project_dir(project: str, role: str) -> str:
    return os.path.join(project_memory_root(project), role)


def project_report_path(project: str) -> str:
    """Where a drain leaves its report for this project."""
    return os.path.join(project_memory_root(project), "last-drain-report.json")


def shared_home(klass: str, project: str | None = None) -> str:
    """Where a slice owned by several roles lives: field knowledge under
    memory/shared/, project knowledge under that project's shared/."""
    if klass in DOMAIN_CLASSES:
        return shared_dir()
    if not project:
        raise ValueError(f"shared {klass!r} is project-scoped; no project given")
    return os.path.join(project_memory_root(project), "shared")


def link_rel(path: str, project: str | None = None) -> str:
    """A path as an index writes it. Relative to the project's link root; a
    fabric-side path seen from a project's repository is linked through the
    sibling checkout (`../agent-fabric/...`)."""
    path = os.path.abspath(path)
    base = project_link_root(project) if project else FABRIC_ROOT
    fabric = os.path.abspath(FABRIC_ROOT)
    # The fabric first, when it is not the base itself: a checkout of the
    # fabric may sit INSIDE the working copy (CI checks it out under the
    # workspace), and a fabric slice is still reached through the sibling
    # prefix, never through wherever this run happened to put the checkout.
    if base != fabric and os.path.commonpath([path, fabric]) == fabric:
        return os.path.join(FABRIC_LINK_PREFIX, os.path.relpath(path, fabric))
    if os.path.commonpath([path, base]) == base:
        return os.path.relpath(path, base)
    return os.path.relpath(path, base)


def resolve_link(link: str, project: str | None = None) -> str:
    """The absolute path an index link denotes (the inverse of link_rel)."""
    if link.startswith(FABRIC_LINK_PREFIX + "/"):
        return os.path.join(FABRIC_ROOT, link[len(FABRIC_LINK_PREFIX) + 1:])
    base = project_link_root(project) if project else FABRIC_ROOT
    return os.path.join(base, link)


def root_rel(path: str) -> str:
    """A fabric-side path relative to this checkout (lint labels, provenance)."""
    return os.path.relpath(path, FABRIC_ROOT)


def list_projects() -> list[str]:
    """Projects whose memory this run can see: every project with a known
    working copy that has a .agent-fabric/memory/."""
    found: set[str] = set()
    candidates = set(_WORKING_COPIES) | {FABRIC_PROJECT_ID}
    env = os.environ.get("AGENT_FABRIC_WORKING_COPY")
    if env:
        pid = _project_of_env_working_copy(env)
        if pid:
            candidates.add(pid)
    for pid in candidates:
        if pid in found:
            continue
        wc = working_copy_for(pid)
        if wc and os.path.isdir(os.path.join(wc, PROJECT_MEMORY_SUBDIR)):
            found.add(pid)
    return sorted(found)


def class_home(klass: str, role: str, project: str | None = None) -> str:
    """The directory a slice of `klass` for `role` belongs in."""
    if klass in IDENTITY_CLASSES:
        return role_dir(role)
    if klass in DOMAIN_CLASSES:
        return domain_dir(role)
    if klass in PROJECT_CLASSES or klass == "index":
        if not project:
            raise ValueError(f"class {klass!r} is project-scoped; no project given")
        return project_dir(project, role)
    raise ValueError(f"unknown knowledge class {klass!r}")


def slices_of(base: str, name: str) -> list[str]:
    """Paths (relative to `base`) for one tier-1 entry.

    Two shapes are accepted: a file (`<name>` or `<name>.md`) or a directory
    of `.md` slices, sorted by name. Naming only `workflow.md` once meant the
    directory shape — the one every role actually uses — never matched, and
    28 tier-1 slices loaded nowhere while nothing said so.
    """
    as_dir = os.path.join(base, name)
    if os.path.isdir(as_dir):
        return [os.path.join(name, e) for e in sorted(os.listdir(as_dir)) if e.endswith(".md")]
    for candidate in (name, f"{name}.md"):
        if os.path.isfile(os.path.join(base, candidate)):
            return [candidate]
    return []


def tier1_paths(role: str, project: str | None) -> list[str]:
    """The absolute paths a role's tier-1 classes resolve to, in order.
    No hook loads them: loading workflow slices at session start was
    measured and rejected (ADR-013 §7), and a session is given the
    charter, brief, remit and the index pointer instead. Kept because
    its tests pin where a role's charter, remit and project memory live.
    A role with nothing of a class, or no project context, simply yields
    fewer paths."""
    found = [os.path.join(role_dir(role), p) for p in slices_of(role_dir(role), "charter.md")]
    if project:
        remit = project_remit_path(project, role)
        if remit and os.path.isfile(remit):
            found.append(remit)
        try:
            base = project_dir(project, role)
        except LookupError:
            return found  # no working copy known: the project's memory is out of reach
        for name in TIER1[1:]:
            found += [os.path.join(base, p) for p in slices_of(base, name)]
    return found
