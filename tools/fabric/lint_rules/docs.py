"""tools/fabric/lint_rules/docs.py — the rules over the corpus's text: ADRs, doc paths, hygiene, licence, skills, project names, review lenses, key lineage, payload shape.
A part of tools/fabric/lint.py, the entry point."""
from __future__ import annotations

import glob
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from typing import Any

from .base import FRONTMATTER_RE, PAYLOAD_DIRS, layout


# The generic patterns plus every visible project's own list (its working
# copy's .agent-fabric/hygiene.json), loaded in main() once the working
# copies are known: layout.load_hygiene_patterns.
BANNED_PATTERNS: list = []


PROJECT_PATTERNS: dict[str, list] = {}   # project id -> the set its own slices are held to


ITALIAN_MARKERS = re.compile(
    r"(?<![a-z])(perch[eé]|per[oò]|quindi|anche|questo|questa|quello|quella|"
    r"dovrebbe|bisogna|abbiamo|siamo|essere|molto|senza|nella|nelle|negli|"
    r"dello|della|delle|degli)(?![a-z])",
    re.I,
)


# runtime/claude-code/harness/en.md: the harness's own system prompt,
# captured from a live build, kept as the English source a locale
# translates (runtime/claude-code/harness/README.md). Fabric-wide, not a
# role's; absent in a fixture fabric, present in this one.
HARNESS_SOURCE = os.path.join("runtime", "claude-code", "harness", "en.md")


HARNESS_PLACEHOLDER = "{memory_dir}"


def adr_findings(root: str | None = None) -> list[str]:
    """docs/adr/: tools/fabric/adr.py's check, as lint findings (agent-fabric
    ADR-001). Absent in a fixture fabric that has no records, which is fine."""
    root = root or layout.FABRIC_ROOT
    if not os.path.isdir(os.path.join(root, "docs", "adr")):
        return []
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    import adr  # noqa: E402 — a sibling module, loaded only when there are records
    return [f"adr: {f}" for f in adr.check(root)]


# A path to one of the fabric's own documents, cited from any tracked text
# file, must resolve — from the repository root or from the citing file's
# own directory: a moved relay-setup note left a dangling pointer in
# inbox.mjs for weeks, and nothing looked. A finding: the notes have moved
# into decision records and every citation in the tree resolves, so a new
# dangling one is a defect. The evidence (live checks), the amendment
# history, knowledge slices (they cite what was true when written) and test
# fixtures are exempt.
# Where the fabric keeps documents: a note at docs/<name>.md, the decision
# records and the live checks, the policies, the protocol and its transports.
# A deeper docs/ path (docs/scratchpad/…) is a project's, named in an example.
DOC_PATH_RE = re.compile(r"(?<![\w/.-])((?:docs/(?:adr/(?:history/|sources/)?|live-checks/)?|policies/(?:[\w-]+/)?|communication/gzcoord/(?:protocol|docs)/)[A-Za-z0-9_.-]+\.md)(?![\w/-])")


FABRIC_ADR_RE = re.compile(r"agent-fabric ADR-(\d{3})(?!\d)")


DOC_PATH_EXEMPT = ("docs/live-checks/", "docs/adr/history/", "docs/adr/ADR-TEMPLATE.md", "memory/", ".agent-fabric/memory/", "tests/", "communication/gzcoord/history/")


def doc_path_findings(root: str | None = None) -> list[str]:
    root = root or layout.FABRIC_ROOT
    try:
        files = subprocess.run(["git", "-C", root, "ls-files"], capture_output=True, text=True, check=True).stdout.split()
    except (OSError, subprocess.CalledProcessError):
        return []
    adr_dir = os.path.join(root, "docs", "adr")
    numbers = {f[4:7] for f in os.listdir(adr_dir) if f.startswith("ADR-") and f[4:7].isdigit()} if os.path.isdir(adr_dir) else set()
    out: list[str] = []
    for rel in files:
        if rel.startswith(DOC_PATH_EXEMPT) or "/test_" in f"/{rel}" or "/tests/" in f"/{rel}":
            continue
        if not rel.endswith((".md", ".py", ".sh", ".mjs", ".js", ".json", ".service")) and "/" in rel and not rel.startswith("bin/"):
            continue
        try:
            with open(os.path.join(root, rel), encoding="utf-8") as fh:
                text = fh.read()
        except (OSError, UnicodeDecodeError):
            continue
        here = os.path.dirname(os.path.join(root, rel))
        for m in DOC_PATH_RE.finditer(text):
            target = m.group(1)
            if not (os.path.exists(os.path.join(root, target)) or os.path.exists(os.path.join(here, target))):
                out.append(f"{rel}: cites {target}, which does not exist")
        for m in FABRIC_ADR_RE.finditer(text):
            if m.group(1) not in numbers:
                out.append(f"{rel}: cites agent-fabric ADR-{m.group(1)}, which does not exist")
    return sorted(set(out))


def harness_source_findings(root: str | None = None) -> list[str]:
    """The capture's shape: frontmatter with its class, the build it was
    captured from, the date, and the live check it came from (which must
    exist — the capture is a claim about a build, and the live check is
    its evidence); the memory-directory placeholder exactly once; hygiene."""
    root = root or layout.FABRIC_ROOT   # at call time: --fabric may have moved it
    path = os.path.join(root, HARNESS_SOURCE)
    if not os.path.isfile(path):
        return []
    out: list[str] = []
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    meta = parse_frontmatter(text)
    if meta is None:
        return [f"{HARNESS_SOURCE}: no frontmatter — class, build, captured_at, source"]
    if meta.get("class") != "harness-source":
        out.append(f"{HARNESS_SOURCE}: class {meta.get('class')!r}; the capture is class harness-source")
    for key in ("build", "captured_at", "source"):
        if not meta.get(key):
            out.append(f"{HARNESS_SOURCE}: no `{key}` — the build it was captured from, when, and the live check that shows it")
    source = str(meta.get("source") or "")
    if source and (not source.startswith("docs/live-checks/") or not os.path.isfile(os.path.join(root, source))):
        out.append(f"{HARNESS_SOURCE}: source {source!r} is not an existing docs/live-checks/ note")
    body = FRONTMATTER_RE.sub("", text)
    n = body.count(HARNESS_PLACEHOLDER)
    if n != 1:
        out.append(f"{HARNESS_SOURCE}: {HARNESS_PLACEHOLDER} appears {n} time(s); the memory directory is the one login-specific span and must be the placeholder exactly once")
    out += hygiene_findings(HARNESS_SOURCE, body)
    return out


def hygiene_findings(where: str, text: str, patterns: list | None = None) -> list[str]:
    """Banned patterns and the language check — for slices AND payload.

    Payload is exempt from the slice judgements; it is never exempt from
    this. lint.py is the only CI pass over the corpus, and role.py copies
    payload verbatim into `.claude/` in every workspace that adopts the role, so
    this is the only thing between a pasted credential and every one of them.
    """
    out: list[str] = []
    # The label and the place, never the hit: a finding lands in CI's log,
    # and a credential pattern's hit is the credential.
    for pattern, label, _refer_as in (BANNED_PATTERNS if patterns is None else patterns):
        if pattern.search(text):
            out.append(f"{where}: {label}")
    italian = {w.lower() for w in ITALIAN_MARKERS.findall(text)}
    if len(italian) >= 3:
        out.append(
            f"{where}: reads as non-English ({sorted(italian)[:5]}) — translate it"
        )
    return out


FABRIC_REF_NAME = "fabric-ref"


FABRIC_REF_RE = re.compile(r"^[0-9a-f]{40}$")


def fabric_ref_findings(pid: str, wc: str) -> list[str]:
    """<working copy>/.agent-fabric/fabric-ref names the agent-fabric commit
    the project's indexes were assembled against — the one its CI checks
    out, so the fabric moving cannot turn the project's check red
    (memory/README.md, "Landing a drain"; 2026-09-18, after three reds in
    a day). Optional; when present it is one line, one full commit id."""
    path = os.path.join(wc, layout.PROJECT_DIRNAME, FABRIC_REF_NAME)
    if not os.path.isfile(path):
        return []
    where = f"{pid}:{layout.PROJECT_DIRNAME}/{FABRIC_REF_NAME}"
    try:
        text = open(path, encoding="utf-8").read()
    except OSError as e:
        return [f"{where}: unreadable ({e})"]
    lines = text.split("\n")
    if len(lines) != 2 or lines[1] != "":
        return [f"{where}: must be exactly one line ending in a newline"]
    if not FABRIC_REF_RE.match(lines[0]):
        return [f"{where}: {lines[0]!r} is not a full lowercase commit id (40 hex)"]
    return []


def payload_shape_findings(role: str, role_path: str) -> list[str]:
    """Assert what role.py can actually install, where it is authored.

    role.py installs a DIRECTORY under skills/ and a .md FILE under
    commands/, and skips anything else without a word. Exempting payload
    from the slice checks would otherwise make misplaced payload invisible
    twice over: silent here, silently dropped at install time.
    """
    out: list[str] = []
    if role == "shared":
        for name in sorted(PAYLOAD_DIRS):
            if os.path.isdir(os.path.join(role_path, name)):
                out.append(
                    f"shared/{name}/: shared ships no payload — role.py "
                    "resolves it as no role and never installs from it"
                )
        return out
    skills_dir = os.path.join(role_path, "skills")
    if os.path.isdir(skills_dir):
        for name in sorted(os.listdir(skills_dir)):
            entry = os.path.join(skills_dir, name)
            if not os.path.isdir(entry):
                out.append(
                    f"{role}/skills/{name}: not a directory — role.py "
                    "installs only directories here, and skips the rest silently"
                )
            elif not os.path.isfile(os.path.join(entry, "SKILL.md")):
                out.append(f"{role}/skills/{name}/: no SKILL.md to be discovered by")
    commands_dir = os.path.join(role_path, "commands")
    if os.path.isdir(commands_dir):
        for name in sorted(os.listdir(commands_dir)):
            entry = os.path.join(commands_dir, name)
            if not (os.path.isfile(entry) and name.endswith(".md")):
                out.append(
                    f"{role}/commands/{name}: not a .md file — role.py "
                    "installs only .md files here, and skips the rest silently"
                )
    return out


def parse_frontmatter(text: str) -> dict[str, Any] | None:
    """Parse the small YAML subset the assembler emits (no external dep)."""
    match = FRONTMATTER_RE.match(text)
    if not match:
        return None
    meta: dict[str, Any] = {}
    key: str | None = None
    for raw in match.group(1).split("\n"):
        if not raw.strip():
            continue
        if raw.startswith("  - ") or raw.startswith("    "):
            if key is None:
                continue
            item = raw.strip().lstrip("- ").strip()
            if ":" in item and not item.startswith('"'):
                sub, _, value = item.partition(":")
                if isinstance(meta.get(key), list) and meta[key] and isinstance(meta[key][-1], dict):
                    meta[key][-1][sub.strip()] = value.strip()
                else:
                    meta.setdefault(key, []).append({sub.strip(): value.strip()})
            else:
                try:
                    item = json.loads(item)
                except json.JSONDecodeError:
                    pass
                meta.setdefault(key, []).append(item)
            continue
        if ":" in raw:
            key, _, value = raw.partition(":")
            key = key.strip()
            value = value.strip()
            if value == "":
                meta[key] = []
            else:
                try:
                    meta[key] = json.loads(value)
                except json.JSONDecodeError:
                    # MATCH assembler/slices.py decode_scalar's fallback, which strips the
                    # outer quotes when json.loads fails. Keeping them here made
                    # the two parsers disagree about the same file: a
                    # description written with unescaped inner quotes — which
                    # yaml_scalar would never emit, so it is hand-edited or
                    # pre-dates the current assembler — came back quoted to lint
                    # and unquoted to assemble. Every length, pattern and
                    # equality judgement lint makes on that field was therefore
                    # made on a different string than the index was generated
                    # from. Found because the INDEX description check below fired
                    # on three slices that were not actually drifted.
                    meta[key] = value.strip('"') if value.startswith('"') else value
    return meta


SESSION_TEMP_REFERENCE = re.compile(r"(^|/)(tmp/claude|scratchpad/)|^/tmp/")


def check_durable_references(role: str, crossref: dict[str, Any]) -> list[str]:
    """A crossref key must still resolve after its session is gone.

    The index's whole value is outliving the observation buffer: ADRs,
    PRs, commits and migrations resolve against git and GitHub. A path
    into a session scratchpad resolves against nothing — it names a
    directory belonging to one session on one machine, dead by the
    time anyone reads it, yet still shaped like a file to open. Three
    such keys reached the repo from other sessions before this check
    existed; `assembler/core.py normalize_artifact` now collapses them to a
    `scratch:` pseudo-path on the way in, and this catches any that
    arrive by another route (a hand edit, an older generator).

    Both `scratch:name` and `scratch:name#<digest>` are valid. The
    digest was added later, to keep two dead paths that share a basename
    from merging into one node; it hashes the ORIGINAL path, which no
    buffer still holds for the keys written before it, so those keep the
    bare form permanently. This check is about the session path being
    gone, which is true of both.
    """
    findings: list[str] = []
    for kind, values in (crossref.get("index") or {}).items():
        for value in values:
            if SESSION_TEMP_REFERENCE.search(value):
                findings.append(
                    f"{role}/crossref.json: index.{kind} key {value!r} is a "
                    "session-local temp path and will not resolve for anyone "
                    "else — use the 'scratch:' form"
                )
    return findings


def project_tools_findings(root: str) -> list[str]:
    """projects/registry.json `tools` (bin/fabric-tools): each a name, a
    proof that is a command line, a reason, where it lives (host or
    account), roles the catalogue knows, optional a boolean. And no
    fabric cleanup may remove a declared tool: runtime/claude-code/
    retire-*.py's RETIRED names none, so a fabric change cannot take a
    project's tool away again as it once took the Doppler CLI (the owner,
    2026-10-07)."""
    import ast
    import glob
    import shlex
    out: list[str] = []
    try:
        projects = (json.load(open(os.path.join(root, "projects", "registry.json"), encoding="utf-8"))
                    .get("projects") or {})
    except (OSError, ValueError):
        return out
    try:
        roles = {r["id"] for r in json.load(open(os.path.join(root, "identities", "roles", "catalog.json"),
                                                 encoding="utf-8"))["roles"]}
    except (OSError, ValueError, KeyError, TypeError):
        roles = None
    declared: set[str] = set()
    for pid, entry in sorted(projects.items()):
        tools = entry.get("tools")
        if tools is None:
            continue
        where = f"projects/registry.json: {pid}.tools"
        if not isinstance(tools, list):
            out.append(f"{where}: not a list")
            continue
        for i, tool in enumerate(tools):
            at = f"{where}[{i}]"
            if not isinstance(tool, dict):
                out.append(f"{at}: not an object")
                continue
            for key in ("name", "proof", "why"):
                if not isinstance(tool.get(key), str) or not tool[key].strip():
                    out.append(f"{at}: {key} missing")
            if tool.get("where") not in ("host", "account"):
                out.append(f"{at}: where is {tool.get('where')!r}; host or account")
            if "optional" in tool and not isinstance(tool["optional"], bool):
                out.append(f"{at}: optional is not a boolean")
            if "roles" in tool and (not isinstance(tool["roles"], list) or (roles is not None
                                    and any(r not in roles for r in tool["roles"]))):
                out.append(f"{at}: roles must be catalogued role ids")
            try:
                argv0 = shlex.split(tool.get("proof") or "")[:1]
            except ValueError:
                argv0 = []
                out.append(f"{at}: proof is not a command line")
            for n in (tool.get("name"), *(os.path.basename(a) for a in argv0)):
                if isinstance(n, str) and n:
                    declared.add(n)
    for script in sorted(glob.glob(os.path.join(root, "runtime", "claude-code", "retire-*.py"))):
        try:
            tree = ast.parse(open(script, encoding="utf-8").read())
        except (OSError, SyntaxError):
            continue
        for node in ast.walk(tree):
            targets = (node.targets if isinstance(node, ast.Assign)
                       else [node.target] if isinstance(node, (ast.AnnAssign, ast.AugAssign)) else [])
            if any(getattr(t, "id", "") == "RETIRED" for t in targets):
                try:
                    # An augmented RETIRED += (...) adds to what the lint
                    # cannot see whole: it is refused as computed.
                    if isinstance(node, ast.AugAssign):
                        raise ValueError("augmented")
                    paths = ast.literal_eval(node.value)
                except ValueError:
                    # A computed RETIRED cannot be checked, so it is refused,
                    # never skipped: the check is the reason it is a literal.
                    out.append(f"{os.path.relpath(script, root)}: RETIRED is not a literal; the lint cannot see what it removes")
                    continue
                for path in paths:
                    base = os.path.basename(str(path).rstrip("/")).lstrip(".")
                    if base in declared:
                        out.append(f"{os.path.relpath(script, root)}: RETIRED removes {path!r}, a tool a project "
                                   "declares (projects/registry.json tools) — a fabric cleanup never takes one away")
    return out


def license_findings(root: str) -> list[str]:
    """This repository is one license, Apache-2.0, throughout — REUSE.toml
    assigns nothing else, and every identifier it does use has its text
    under LICENSES/. projects/registry.json names each project's OWN
    license as information about that project's tree; it is required (a
    project with no stated license cannot be reasoned about) but binds
    nothing here. A project's knowledge never lives here at all."""
    findings: list[str] = []
    reg_path = os.path.join(root, "projects", "registry.json")
    reuse_path = os.path.join(root, "REUSE.toml")
    if not os.path.exists(reg_path):
        return findings
    try:
        registry = json.load(open(reg_path, encoding="utf-8"))
    except (OSError, ValueError):
        return findings  # the registry's own parse is reported elsewhere
    for pid, entry in sorted((registry.get("projects") or {}).items()):
        lic = entry.get("license")
        if not isinstance(lic, str) or not lic:
            findings.append(f"projects/registry.json: project {pid!r} names no license")
        if os.path.isdir(os.path.join(root, "memory", "projects", pid)):
            findings.append(f"memory/projects/{pid}/: a project's knowledge lives in the project's repository "
                            "(<working copy>/.agent-fabric/memory/), not here")
    if not os.path.exists(reuse_path):
        findings.append("REUSE.toml: missing; the repository states its license there")
        return findings
    try:
        import tomllib
        reuse = tomllib.load(open(reuse_path, "rb"))
    except Exception as exc:  # noqa: BLE001 - any parse failure is the finding
        return [f"REUSE.toml: does not parse ({exc})"]
    licenses_dir = os.path.join(root, "LICENSES")
    for ann in reuse.get("annotations") or []:
        lic = ann.get("SPDX-License-Identifier", "")
        if lic != "Apache-2.0":
            findings.append(f"REUSE.toml: assigns {lic!r} to {ann.get('path')}; this repository is Apache-2.0 throughout")
        if lic and not os.path.exists(os.path.join(licenses_dir, lic + ".txt")):
            findings.append(f"REUSE.toml: {lic!r} has no LICENSES/{lic}.txt")
    return findings


CLASS_DOCS = {
    # Where the class list is written out for a reader; each must name every
    # class in routing/capabilities.json and nothing that is not one — the
    # README said `review` for a class named code-review until 2026-09-16.
    "README.md": r"`routing/capabilities.json` classes:([^|\n]*)",
    "CLAUDE.md": r"name a capability class in `subagent_type`[^.]*?the five\s+are (.*?)— and",
}


def class_doc_findings(root: str) -> list[str]:
    """The capability class names a document lists must be exactly the
    classes routing/capabilities.json defines."""
    findings: list[str] = []
    cap_path = os.path.join(root, "routing", "capabilities.json")
    try:
        classes = set((json.load(open(cap_path, encoding="utf-8")).get("classes") or {}).keys())
    except (OSError, ValueError):
        return findings  # the file's own parse is reported by the routing check
    if not classes:
        return findings
    for rel, pattern in CLASS_DOCS.items():
        path = os.path.join(root, rel)
        try:
            text = open(path, encoding="utf-8").read()
        except OSError:
            continue
        m = re.search(pattern, text, flags=re.S)
        if not m:
            findings.append(f"{rel}: the capability class list was not found (lint looks for {pattern!r})")
            continue
        named = set(re.findall(r"`([a-z][a-z0-9-]*)`", m.group(1)))
        for extra in sorted(named - classes):
            findings.append(f"{rel}: names capability class {extra!r}, which routing/capabilities.json does not define "
                            f"(classes: {', '.join(sorted(classes))})")
        for missing in sorted(classes - named):
            findings.append(f"{rel}: does not name capability class {missing!r} (routing/capabilities.json defines it)")
    return findings


def agent_source_findings(root: str) -> list[str]:
    """A committed agent definition carries no routed value.

    `model:` and `effort:` are written into the installed copy by
    runtime/claude-code/install-agent-files.sh, from routing/. A value
    hand-written into the source here would be the second place a class's
    model or thinking is decided, and the one nobody updates — the source's
    `model:` is the tier alias the class rides, never a resolved id."""
    findings: list[str] = []
    # Every committed source of an INSTALLED agent file, not only the
    # class files: the locale worker is installed the same way and was
    # outside this scan, so a hand-written level there had no second
    # writer to refuse it (review of 2026-09-23).
    sources: list[tuple[str, str]] = []
    agents = os.path.join(root, "runtime", "claude-code", "agents")
    for name in sorted(os.listdir(agents)) if os.path.isdir(agents) else []:
        if name.endswith(".md"):
            sources.append((os.path.join("runtime", "claude-code", "agents", name),
                            os.path.join(agents, name)))
    locales = os.path.join(root, "identities", "roles", "language-culture", "locale")
    for suffix in sorted(os.listdir(locales)) if os.path.isdir(locales) else []:
        worker = os.path.join(locales, suffix, "worker.md")
        if os.path.isfile(worker):
            sources.append((os.path.join("identities", "roles", "language-culture",
                                         "locale", suffix, "worker.md"), worker))
    for rel, path in sources:
        try:
            text = open(path, encoding="utf-8").read()
        except OSError:
            continue
        head = text.split("---", 2)[1] if text.startswith("---") and "---" in text[3:] else text
        if re.search(r"^effort:", head, flags=re.M):
            findings.append(f"{rel}: carries a hand-written 'effort:'. The level is routing/effort.json's and is "
                            "written into the installed copy by install-agent-files.sh; a second source here is "
                            "the one that goes stale.")
    return findings


# Generic surfaces: what every managed project shares. A project's name
# there is project truth in the control plane — the review of 2026-09-16
# found one project's port variable in a role skill, its gpg wrapper in
# the provisioner, its channel as a GZCoord default.
GENERIC_DIRS = ("identities/roles", "runtime/provisioning", "runtime/claude-code", "runtime/hostexec",
                "runtime/openrouter", "runtime/github", "tools/fabric", "bin", "communication/gzcoord/scripts",
                "communication/gzcoord/skills")


GENERIC_SKIP = ("history/", "/test_", "/tests/", "README.md")


# The shared skills under policies/ are generic too (ADR-016 rule 1). The
# rest of policies/ is not walked: its authority texts and guards describe
# the fabric's own history with the projects it serves.
GENERIC_FILES = ("policies/*/SKILL.md",)


# The fabric's own remote is not a managed project's name.
FABRIC_SELF = ("gzapi-org/agent-fabric",)


# A skill carries rules, not the occasion that produced them (ADR-016 §5):
# no dates, no pull-request numbers, no one account's login — the reader
# cannot check them and they read as stale the week after. Its description
# is the only thing a session sees before loading it, so it must say WHEN
# to load it. Held by review until now (ADR-016 §6); these are the
# mechanical halves. A numbered login (backend-dev-01) names one account;
# a login that is also a role slug or a word ("user", "db-admin") cannot be
# told from the role or the word, and is left to review.
SKILL_DATE_RE = re.compile(r"\b20\d\d-\d\d-\d\d\b")


# "#57", "PR 57", "pull request 57", and a number glued to a word
# ("PR#57", "repo#12") — the last escaped the first pattern's lookbehind.
SKILL_PR_RE = re.compile(r"(?<![\w/&])#\d{2,}\b|\b[A-Za-z][\w.-]*#\d+\b|\bPR \d+\b|\bpull request #?\d+\b", re.I)


SKILL_CUE_RE = re.compile(r"\b(when|before|whenever)\b", re.I)


def skill_findings(root: str) -> list[str]:
    findings: list[str] = []
    try:
        placement = (json.load(open(os.path.join(root, "runtime", "hosts", "registry.json"),
                                    encoding="utf-8")).get("placement") or {})
    except (OSError, ValueError):
        placement = {}
    logins = sorted(lg for lg in placement if re.search(r"-\d+$", lg))
    for top in ("policies", "communication", "identities"):
        for dirpath, dirnames, filenames in os.walk(os.path.join(root, top)):
            dirnames[:] = [d for d in dirnames if d not in (".git", "node_modules", "locale")]
            if "SKILL.md" not in filenames:
                continue
            path = os.path.join(dirpath, "SKILL.md")
            rel = os.path.relpath(path, root)
            try:
                text = open(path, encoding="utf-8").read()
            except OSError:
                continue
            fm = parse_frontmatter(text) or {}
            desc = str(fm.get("description") or "")
            if not SKILL_CUE_RE.search(desc):
                findings.append(f"{rel}: the description names no occasion to load the skill "
                                "(\"when …\", \"before …\") — it is all a session sees before loading it")
            # The description is scanned too: it is the one part of a skill
            # every session sees, and an occasion there is the likeliest.
            body = desc + "\n" + re.sub(r"\A---\n.*?\n---\n", "", text, count=1, flags=re.DOTALL)
            for label, rx in (("a date", SKILL_DATE_RE), ("a pull-request number", SKILL_PR_RE)):
                m = rx.search(body)
                if m:
                    findings.append(f"{rel}: carries {label} ({m.group(0)!r}) — a skill carries the rule, "
                                    "the occasion goes in the commit or a record (ADR-016)")
            for lg in logins:
                if re.search(rf"(?<![\w/-]){re.escape(lg)}(?![\w-])", body):
                    findings.append(f"{rel}: names the account {lg!r} — a skill is for whoever holds the role (ADR-016)")
    return findings


def project_name_findings(root: str) -> list[str]:
    """A managed project's id (projects/registry.json) must not appear in
    a generic file: a role's skills, the provisioning, the harness
    adapters, the tools, the GZCoord runtime. What a project needs said
    goes in its own integration (projects/<id>/) or its working copy's
    .agent-fabric/ remit. The fabric's own id and remote are exempt; so
    are tests, READMEs and history."""
    findings: list[str] = []
    try:
        ids = sorted((json.load(open(os.path.join(root, "projects", "registry.json"), encoding="utf-8")).get("projects") or {}).keys())
    except (OSError, ValueError):
        return findings
    ids = [i for i in ids if i != layout.FABRIC_PROJECT_ID]
    if not ids:
        return findings
    pats = []
    for pid in ids:
        pats.append(re.compile(r"(?<![A-Za-z0-9])" + re.escape(pid) + r"(?![A-Za-z0-9.])", re.I))
        pats.append(re.compile(r"\b" + re.escape(re.sub(r"[^A-Za-z0-9]", "_", pid).upper()) + r"_"))
    def walked():
        for rel in GENERIC_DIRS:
            base = os.path.join(root, rel)
            if not os.path.isdir(base):
                continue
            for dirpath, dirnames, filenames in os.walk(base):
                dirnames[:] = sorted(d for d in dirnames if d not in ("node_modules", "__pycache__", ".git"))
                for name in sorted(filenames):
                    yield dirpath, name
        for pattern in GENERIC_FILES:
            for full in sorted(glob.glob(os.path.join(root, pattern))):
                yield os.path.dirname(full), os.path.basename(full)
    for dirpath, name in walked():
        full = os.path.join(dirpath, name)
        relpath = os.path.relpath(full, root)
        if any(x in relpath + ("/" if os.path.isdir(full) else "") for x in GENERIC_SKIP) or name.startswith("test_") or name.endswith((".png", ".jpg", ".txt", ".lock")):
            continue
        try:
            with open(full, encoding="utf-8") as fh:
                for n, line in enumerate(fh, 1):
                    probe = line
                    for exempt in FABRIC_SELF:
                        probe = probe.replace(exempt, "")
                    for pat in pats:
                        m = pat.search(probe)
                        if m:
                            findings.append(f"{relpath}:{n}: names a managed project ({m.group(0)!r}) in a generic file; "
                                            "project truth goes in projects/<id>/ or the project's .agent-fabric/ remit")
                            break
        except (OSError, UnicodeDecodeError):
            continue
    return findings


LENS_BODY_CAP = 1500


LENS_DESCRIPTION_CAP = 120


LENS_NAME_RE = re.compile(r"^[a-z][a-z0-9-]*$")


def review_lens_findings(root: str) -> list[str]:
    """runtime/claude-code/review/lenses/<name>.md: the review lens
    vocabulary IS this directory (bin/fabric-review lenses lists it, the
    brief renderer inlines a named one). Each file: `name:` equal to the
    filename, a one-line `description:`, a body under the cap — a lens
    biases a review and is paid on every dispatch that names it."""
    findings: list[str] = []
    base = os.path.join(root, "runtime", "claude-code", "review", "lenses")
    if not os.path.isdir(base):
        return findings
    names = sorted(os.listdir(base))
    if "general.md" not in names:
        findings.append("runtime/claude-code/review/lenses/: no general.md — the renderer adds `general` to every brief")
    for fn in names:
        rel = f"runtime/claude-code/review/lenses/{fn}"
        if not fn.endswith(".md"):
            findings.append(f"{rel}: not a lens (.md)")
            continue
        text = open(os.path.join(base, fn), encoding="utf-8").read()
        m = FRONTMATTER_RE.match(text)
        if not m:
            findings.append(f"{rel}: no frontmatter (name:, description:)")
            continue
        meta = dict(line.split(":", 1) for line in m.group(1).split("\n") if ":" in line)
        meta = {k.strip(): v.strip() for k, v in meta.items()}
        stem = fn[:-3]
        if meta.get("name") != stem or not LENS_NAME_RE.match(stem):
            findings.append(f"{rel}: name {meta.get('name')!r} must equal the filename and be a lowercase slug")
        desc = meta.get("description", "")
        if not desc or len(desc) > LENS_DESCRIPTION_CAP:
            findings.append(f"{rel}: description missing or over {LENS_DESCRIPTION_CAP} characters (one line, shown by fabric-review lenses)")
        body = text[m.end():]
        if len(body.encode()) > LENS_BODY_CAP:
            findings.append(f"{rel}: body is {len(body.encode())} bytes; the cap is {LENS_BODY_CAP} (a lens is paid on every dispatch that names it)")
        if not body.strip():
            findings.append(f"{rel}: empty body")
    return findings


def key_lineage_findings(root: str) -> list[str]:
    """ADR-038 §5 rule 2: every committed agent key is the one its
    lineage records and carries its parent's certification. Read by
    tools/fabric/secretstore/lineage.py in a throwaway keyring: a module of
    the standard library alone, fenced from contributors, so that no
    contributor change makes this answer clean (review of #106). No keys
    committed yet is clean; a host without gpg is said, not passed silently."""
    if not os.path.isdir(os.path.join(root, "identities", "keys")):
        return []
    if not shutil.which("gpg"):
        return ["identities/keys/: gpg is not installed here, so no key's lineage could be checked"]
    spec = importlib.util.spec_from_file_location(
        "fabric_secret_lineage",
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "secretstore", "lineage.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.verify(root)
