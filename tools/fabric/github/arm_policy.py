"""tools/fabric/github/arm_policy.py — a repository's arming policy: how a pull request reaches the default branch,
how many work commits arm it at the review gate, and the GitHub settings that enforce the rest, as one document
whose shape is identities/schemas/arming.schema.json (the coordinator's). Step A (#196) made arm.py and pr_gate.py
read the 8 and the 16 through it; step C (this) makes it the schema's document, reads it for the repository's client,
and maps it onto GitHub for tools/fabric/github/repo_policy.py (fabric-repo-policy plan|verify) and arm.py's drift
refusal.

WHERE A POLICY IS. Two layers, the second over the first:
  fleet     policies/arming.json in the fabric's tree (absent: DEFAULT below)
  repo      repos/<repo>.json in the settings repository of the repository's client, read from that repository's
            default branch through gh.py's contents API: never from a pull request's head or a working copy, so a PR
            cannot change the rules it is armed under. The client is projects/registry.json's `client` of the project
            whose remote is the repository (as workingcopy.canonical_remote compares them); the settings repository
            is projects/clients.json's `settings_repo` for it. A repository no registered project has, or no file
            for it (HTTP 404 with the settings repository itself answering): the fleet policy applies. A
            registered project whose client is missing, unknown or has no settings_repo is an error. Any other failure to
            read it — no answer, a refusal, a file that is not JSON, a settings repository that cannot be read —
            is PolicyUnavailable: an unreadable policy is never the default, because a default more permissive than
            the repository's own would arm what the repository meant to hold.
Objects merge recursively, scalars and lists replace. The fetched file is cached by the caller for one run
(`cache=`), never between runs. validate() holds the schema's shape and refuses what it does not allow: a typo must
not fall to the default.

commits.boundary_authority (a role slug; absent: none) names the role whose holder may authorize arming a
security-boundary change under boundary_min in the owner's place (arm.py --authorization); the review gate still applies.

commits.boundary_min. A security-boundary change not waived is judged against max(commits.min, commits.boundary_min):
the owner's word it needs under that many work commits is about the security boundary, not about the count of
commits (the owner, 2026-10-11, through fabric-coordinator's REPLY 01a12ab1). The fleet's value is the floor: a
repository's file may raise it and never lowers it below the fleet's, which load() enforces after the merge.

threshold() IS THE ORDER OF SPECIFICITY: a stated class whose regex every file matches (commits.classes), then the
author's role (commits.roles), then commits.min; a boundary change gets the floor above and nothing lowers it.
render() IS THE MAPPING to GitHub: the repository fields and the ruleset body.
"""
from __future__ import annotations

import base64
import binascii
import copy
import json
import os
import re
import sys
from typing import Any, Callable, Mapping

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import gh  # noqa: E402
import roots  # noqa: E402
import workingcopy  # noqa: E402

REPO_NAME = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
ROLE_SLUG = re.compile(r"[a-z][a-z0-9-]*")
MODES = ("queue", "auto", "direct", "owner-only")
METHODS = ("merge", "squash", "rebase")
BELOW_MIN = ("owner-word", "refuse")
GROUPING = ("allgreen", "headgreen")
UPDATE_TYPES = ("patch", "minor", "major")
# GitHub's repository fields for the merge methods: the merge commit's is the odd one out.
REPO_FIELD = {"merge": "allow_merge_commit", "squash": "allow_squash_merge", "rebase": "allow_rebase_merge"}
# The integration id of an App by its slug, for a ruleset's required check; one not here is asked of GitHub
# (apps/<slug>) by repo_policy.resolve_apps. github-actions is 15368 everywhere.
APP_IDS = {"github-actions": 15368}
# GitHub's own defaults for a merge queue, for what a policy leaves out.
QUEUE_DEFAULTS = {"grouping": "allgreen", "build": 5, "merge_max": 5, "merge_min": 1, "wait_minutes": 5, "check_timeout_minutes": 60}
RULESET_PARAMETERS = {"build": "max_entries_to_build", "merge_max": "max_entries_to_merge", "merge_min": "min_entries_to_merge",
                      "wait_minutes": "min_entries_to_merge_wait_minutes", "check_timeout_minutes": "check_response_timeout_minutes"}

# The fleet default, as policies/arming.json has it: what a tree without that file gets.
DEFAULT: dict[str, Any] = {
    "mode": "auto",
    "method": "merge",
    "required_checks": [],
    "signatures": True,
    "protect": {"deletion": True, "force_push": True},
    "delete_branch_on_merge": False,
    "queue": {},
    "commits": {"min": 8, "advice_over": 16, "boundary_min": 8, "below_min": "owner-word", "roles": {}, "classes": {}},
    "reviews": ["claude", "codex"],
    "boundary_reviews": ["claude", "codex"],
    "bots": {},
    "github": {"ruleset": "fabric arming policy"},
}
# The review engines (agent-fabric ADR-053 rule 6): "claude" is the review class's `fabric-pr post-review ... --model
# fable`; "codex" is one posted with `--model codex`.
ENGINES = ("claude", "codex")
# `description` is for the reader of the file (the schema allows it, a non-empty string, and nothing else beside the keys).
IGNORED_KEYS = ("description",)


class PolicyError(ValueError):
    """A policy document that is not one: the message names the file and the key."""


class PolicyUnavailable(Exception):
    """The repository's policy could not be read at all (not: it has none). Never answered with the default."""


def is_repo_name(v: Any) -> bool:
    """An <owner>/<name> as GitHub spells one; `.` and `..` are no owner or name, and they are what a path walks by."""
    return isinstance(v, str) and REPO_NAME.fullmatch(v) is not None and all(part not in (".", "..") for part in v.split("/"))


def _int(v: Any, low: int = 1) -> bool:
    """A whole number of at least `low`: JSON's `1.0` is the integer 1 to the schema, and is here."""
    return isinstance(v, (int, float)) and not isinstance(v, bool) and v == v and v not in (float("inf"), float("-inf")) \
        and int(v) == v and v >= low


def _whole(table: dict, key: str) -> None:
    if key in table:
        table[key] = int(table[key])


def merge(base: Any, over: Any) -> Any:
    """Objects merge recursively; anything else in `over` replaces `base`."""
    if isinstance(base, dict) and isinstance(over, dict):
        out = dict(base)
        for k, v in over.items():
            out[k] = merge(base[k], v) if k in base else copy.deepcopy(v)
        return out
    return copy.deepcopy(over)


def normalize_classes(raw: Any, where: str = "classes", legacy: bool = False) -> dict[str, dict]:
    """{name: {paths, min}} as the schema has it, names lower-cased as a PR body's `Class:` line is read. `legacy`
    is a project's arm.json (with_classes): there {name: regex} is also a class, = {paths, min: 1}, and `min` may
    be left out. A policy file is the schema's: both keys, an object."""
    if not isinstance(raw, dict):
        raise PolicyError(f"{where} is not an object of class names")
    out = {}
    for name, spec in raw.items():
        name = str(name).lower()
        if not name or "\n" in name:
            raise PolicyError(f"{where}: {name!r} is not a class name")
        if legacy and isinstance(spec, str):
            spec = {"paths": spec, "min": 1}
        required = {"paths"} if legacy else {"paths", "min"}
        if not isinstance(spec, dict) or set(spec) - {"paths", "min"} or required - set(spec) or not isinstance(spec.get("paths"), str) or not spec["paths"]:
            raise PolicyError(f"{where}.{name} is not an object with `paths` and `min`")
        floor = spec.get("min", 1)
        if not _int(floor):
            raise PolicyError(f"{where}.{name}.min is not a whole number of at least 1")
        try:
            re.compile(spec["paths"])
        except re.error as e:
            raise PolicyError(f"{where}.{name}.paths is not a regex ({e})") from None
        if name in out:
            raise PolicyError(f"{where}: class {name!r} is named twice")
        out[name] = {"paths": spec["paths"], "min": int(floor)}
    return out


def _only_keys(value: Any, allowed: tuple, where: str) -> dict:
    if not isinstance(value, dict) or set(value) - set(allowed):
        raise PolicyError(f"{where} is not an object of {', '.join(allowed)}")
    return value


def validate(doc: Any, where: str = "the policy") -> dict:
    """The document, completed from the default and checked against the schema's shape (a copy). Raises
    PolicyError naming `where` and the key."""
    if not isinstance(doc, dict):
        raise PolicyError(f"{where} is not an object")
    unknown = sorted(set(doc) - set(DEFAULT) - set(IGNORED_KEYS))
    if unknown:
        raise PolicyError(f"{where}: unknown key(s) {', '.join(unknown)}; the keys are {', '.join(DEFAULT)}")
    if "description" in doc and not (isinstance(doc["description"], str) and doc["description"]):
        raise PolicyError(f"{where}: description is not a non-empty string")
    p = merge(DEFAULT, {k: v for k, v in doc.items() if k not in IGNORED_KEYS})
    if p["mode"] not in MODES:
        raise PolicyError(f"{where}: mode is {p['mode']!r}, not one of {', '.join(MODES)}")
    if p["method"] not in METHODS:
        raise PolicyError(f"{where}: method is {p['method']!r}, not one of {', '.join(METHODS)}")
    checks = p["required_checks"]
    if not isinstance(checks, list):
        raise PolicyError(f"{where}: required_checks is not a list")
    seen = set()
    for c in checks:
        if not isinstance(c, dict) or set(c) - {"context", "app"} or not isinstance(c.get("context"), str) or not c["context"]:
            raise PolicyError(f"{where}: required_checks: {c!r} is not {{\"context\": a check name, \"app\": an App slug}}")
        if "app" in c and not (isinstance(c["app"], str) and c["app"]):
            raise PolicyError(f"{where}: required_checks: app {c['app']!r} is not an App's name")
        key = (c["context"], c.get("app"))
        if key in seen:
            raise PolicyError(f"{where}: required_checks names {c['context']!r} twice")
        seen.add(key)
    if not isinstance(p["signatures"], bool) or not isinstance(p["delete_branch_on_merge"], bool):
        raise PolicyError(f"{where}: signatures and delete_branch_on_merge are true or false")
    protect = _only_keys(p["protect"], ("deletion", "force_push"), f"{where}: protect")
    if not all(isinstance(v, bool) for v in protect.values()):
        raise PolicyError(f"{where}: protect.deletion and protect.force_push are true or false")
    q = _only_keys(p["queue"], tuple(QUEUE_DEFAULTS), f"{where}: queue")
    if q.get("grouping", "allgreen") not in GROUPING:
        raise PolicyError(f"{where}: queue.grouping is one of {', '.join(GROUPING)}")
    for k in QUEUE_DEFAULTS:
        if k != "grouping" and k in q:
            if not _int(q[k]):
                raise PolicyError(f"{where}: queue.{k} is not a whole number of at least 1")
            _whole(q, k)
    c = _only_keys(p["commits"], (*DEFAULT["commits"], "boundary_authority"), f"{where}: commits")
    if "boundary_authority" in c and not (isinstance(c["boundary_authority"], str) and ROLE_SLUG.fullmatch(c["boundary_authority"])):
        raise PolicyError(f"{where}: commits.boundary_authority is not a role slug")
    for k in ("min", "advice_over", "boundary_min"):
        if not _int(c[k]):
            raise PolicyError(f"{where}: commits.{k} is not a whole number of at least 1")
        _whole(c, k)
    if c["below_min"] not in BELOW_MIN:
        raise PolicyError(f"{where}: commits.below_min is {c['below_min']!r}, not one of {', '.join(BELOW_MIN)}")
    if not isinstance(c["roles"], dict):
        raise PolicyError(f"{where}: commits.roles is not an object of role slugs")
    for slug, spec in c["roles"].items():
        if not ROLE_SLUG.fullmatch(str(slug)):
            raise PolicyError(f"{where}: commits.roles: {slug!r} is not a role slug")
        if not isinstance(spec, dict) or set(spec) != {"min"} or not _int(spec["min"]):
            raise PolicyError(f"{where}: commits.roles.{slug} is not {{\"min\": a whole number of at least 1}}")
        _whole(spec, "min")
    c["classes"] = normalize_classes(c["classes"], f"{where}: commits.classes")
    for key in ("reviews", "boundary_reviews"):
        engines = p[key]
        if not isinstance(engines, list) or not engines or any(e not in ENGINES for e in engines) or len(set(engines)) != len(engines):
            raise PolicyError(f"{where}: {key} is a non-empty list of distinct engines drawn from {', '.join(ENGINES)}")
    bots = _only_keys(p["bots"], ("dependabot",), f"{where}: bots")
    if "dependabot" in bots:
        d = _only_keys(bots["dependabot"], ("arm", "ecosystems"), f"{where}: bots.dependabot")
        if "arm" not in d or not isinstance(d["arm"], list) or any(x not in UPDATE_TYPES for x in d["arm"]) or len(set(d["arm"])) != len(d["arm"]):
            raise PolicyError(f"{where}: bots.dependabot.arm is a list drawn from {', '.join(UPDATE_TYPES)}")
        eco = d.get("ecosystems", [])
        if not isinstance(eco, list) or not all(isinstance(x, str) and x for x in eco) or len(set(eco)) != len(eco):
            raise PolicyError(f"{where}: bots.dependabot.ecosystems is a list of distinct package ecosystems")
    g = _only_keys(p["github"], ("ruleset", "branch"), f"{where}: github")
    for k, v in g.items():
        if not isinstance(v, str) or not v:
            raise PolicyError(f"{where}: github.{k} is not a name")
    return p


def _read_json_file(path: str) -> Any:
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as e:
        raise PolicyError(f"{path} cannot be read ({type(e).__name__}: {e})") from None


def fleet_policy(root: str | None = None) -> dict:
    """DEFAULT, with policies/arming.json over it when the fabric has one."""
    path = roots.policy("arming.json", root=root)
    doc = _read_json_file(path)
    if doc is None:
        return validate({})
    return validate(doc, path)


def default() -> dict:
    """The built-in policy, for a caller with no repository to load for."""
    return validate({})


def project_of(registry: Any, repo: str) -> tuple[str, dict] | None:
    """The registry project whose remote is `repo` ("<owner>/<name>", compared without case), or None."""
    projects = registry.get("projects") if isinstance(registry, dict) else None
    if not isinstance(projects, dict):
        raise PolicyUnavailable("projects/registry.json has no projects map")
    # The registry's own comparison (workingcopy.canonical_remote): the scheme, the user, a trailing .git or space,
    # a host's case are not part of which repository a remote names. A second reading of remotes could miss a
    # registered project, and a registered project must never be given the fleet policy by a spelling.
    want = workingcopy.canonical_remote(f"https://github.com/{repo}")
    for pid, spec in projects.items():
        for remote in (spec.get("remotes") if isinstance(spec, dict) else None) or []:
            if want and workingcopy.canonical_remote(str(remote)) == want:
                return pid, spec
    return None


def settings_repo_of(registry: Any, clients: Any, repo: str) -> str | None:
    """The settings repository of `repo`'s client; None when the repository is not a registered project's (then the
    fleet policy applies). A registered project whose client is missing, unknown or names no settings repository
    is an error, said loudly: the policy of a repository the fabric knows is somewhere, and falling back to the
    fleet's would arm it by rules its owner did not write."""
    found = project_of(registry, repo)
    if found is None:
        return None
    pid, spec = found
    client = spec.get("client")
    if not isinstance(client, str) or not client:
        raise PolicyError(f"projects/registry.json: project {pid} (the remote of {repo}) names no client, so its settings repository is unknown")
    entry = clients.get("clients", {}).get(client) if isinstance(clients, dict) and isinstance(clients.get("clients"), dict) else None
    if not isinstance(entry, dict):
        raise PolicyError(f"projects/clients.json has no client {client!r}, which project {pid} ({repo}) names")
    value = entry.get("settings_repo")
    if value is None:
        raise PolicyError(f"projects/clients.json: client {client!r} (project {pid}, {repo}) has no settings_repo")
    if not is_repo_name(value):
        raise PolicyError(f"projects/clients.json: {client}'s settings_repo is not an <owner>/<name>")
    return value


def fetch_repo_policy(settings: str, repo: str, api: Callable[..., Any] = gh.api) -> dict | None:
    """repos/<repo name>.json from the settings repository's default branch, or None when it has none (404 while the
    settings repository itself answers). Every other failure raises PolicyUnavailable."""
    if not is_repo_name(repo):
        raise PolicyUnavailable(f"{repo!r} is not an <owner>/<name>")
    name = repo.split("/", 1)[1]
    where = f"{settings} repos/{name}.json"
    try:
        # No `ref`: the contents API reads the default branch, which is the point.
        answer = api(f"repos/{settings}/contents/repos/{name}.json")
    except gh.GhError as e:
        if e.status != 404:
            raise PolicyUnavailable(f"{where} could not be read ({e.reason})") from None
        # A 404 is also what a token that cannot see a private repository, or a repository that is not there,
        # gets: the file is absent only if the repository itself answers.
        try:
            api(f"repos/{settings}")
        except gh.GhError as e2:
            raise PolicyUnavailable(f"{settings} cannot be read ({e2.reason}); {where} is not known to be absent") from None
        return None
    try:
        if not isinstance(answer, dict) or answer.get("type") != "file" or answer.get("encoding") != "base64":
            raise ValueError("not a file")
        doc = json.loads(base64.b64decode(answer["content"], validate=False).decode("utf-8"))
    except (ValueError, KeyError, TypeError, binascii.Error, UnicodeDecodeError) as e:
        raise PolicyUnavailable(f"{where} is not a JSON file ({type(e).__name__})") from None
    if not isinstance(doc, dict):
        raise PolicyUnavailable(f"{where} is not an object")
    return doc


def load(repo: str | None, *, root: str | None = None, registry: Any = None, clients: Any = None,
         api: Callable[..., Any] = gh.api, cache: dict | None = None) -> dict:
    """The policy for `repo` ("<owner>/<name>"; None: the fleet's). `cache` is the caller's dict, for one run: a
    repository's file is fetched once. PolicyError for a document that is not valid, PolicyUnavailable when the
    repository's file could not be read."""
    fleet = fleet_policy(root)
    if not repo:
        return fleet
    if cache is not None and repo in cache:
        return copy.deepcopy(cache[repo])
    if registry is None:
        try:
            registry = workingcopy.load_registry()
        except (OSError, ValueError) as e:
            raise PolicyUnavailable(f"projects/registry.json cannot be read ({e})") from None
    if clients is None:
        clients = _read_json_file(os.path.join(roots.projects_dir(root=root), "clients.json")) or {}
    settings = settings_repo_of(registry, clients, repo)
    doc = fetch_repo_policy(settings, repo, api) if settings else None
    policy = fleet
    if doc is not None:
        policy = validate(merge(fleet, {k: v for k, v in doc.items() if k not in IGNORED_KEYS}), f"{settings} repos/{repo.split('/', 1)[1]}.json")
        # A repository may raise the boundary's minimum and never lower it below the fleet's.
        policy["commits"]["boundary_min"] = max(policy["commits"]["boundary_min"], fleet["commits"]["boundary_min"])
    if cache is not None:
        cache[repo] = copy.deepcopy(policy)
    return policy


def with_classes(policy: dict, classes: dict[str, str]) -> dict:
    """The policy with a project's older arm.json classes ({name: regex}) added under the policy's own: a class
    the policy states wins."""
    out = copy.deepcopy(policy)
    out["commits"]["classes"] = {**normalize_classes(classes, "arm.json classes", legacy=True), **policy["commits"]["classes"]}
    return out


def threshold(policy: dict, role: str | None, cls: str | None, boundary: bool) -> int:
    """The work commits at which this pull request arms at the review gate. `cls` is the stated class whose
    regex every changed file matches (the caller checked), or empty; `boundary` is a security-boundary change not
    waived. Most specific first: class, role, repository; a boundary change gets max(commits.min,
    commits.boundary_min) and nothing lowers it."""
    c = policy["commits"]
    if boundary:
        return max(c["min"], c["boundary_min"])
    if cls:
        if cls not in c["classes"]:
            raise PolicyError(f"the policy has no class {cls!r}")
        return c["classes"][cls]["min"]
    spec = c["roles"].get(role) if role else None
    return spec["min"] if spec else c["min"]


def required_engines(policy: dict, boundary: bool) -> list[str]:
    """The review engines this pull request needs, in ENGINES order: the policy's `reviews`, and for a security-boundary
    change not waived also its `boundary_reviews` (a waived boundary is judged as no boundary, as for the count)."""
    wanted = set(policy["reviews"]) | (set(policy["boundary_reviews"]) if boundary else set())
    return [e for e in ENGINES if e in wanted]


def engines_on_head(rows: Any, head: str) -> set[str]:
    """The engines with a review of `head` among pr-review-status --json's blind.rows: the reading fabric-pr arm gates
    on, and the gate and counts report. A row with no engine is the review class's: reviews posted before the field
    existed were all Claude's."""
    return {r.get("engine", "claude") for r in rows or [] if isinstance(r, dict) and r.get("commit_sha8") == head[:8]}


# What a summary opens with when every required engine has reviewed the head, and only then: three PRs were reported
# ready from a gate line that said it while one of the two engines the arm requires had not (REQUEST 01a13693).
HEAD_REVIEWED = "head reviewed"


def review_summary(have: set[str], required: list[str], head: str, boundary_only: list[str] = ()) -> str:
    """"claude ✓ codex ✗ (head 6bc0ad18)", one mark per required engine, opened by "head reviewed: " when all are
    there. `boundary_only` engines (a policy's boundary_reviews beyond its reviews, for a reader that does not judge
    the boundary) are marked and not required."""
    marks = [f"{e} {'✓' if e in have else '✗'}" for e in required]
    marks += [f"{e} {'✓' if e in have else '✗'} (boundary only)" for e in boundary_only if e not in required]
    line = f"{' '.join(marks)} (head {head[:8]})"
    return f"{HEAD_REVIEWED}: {line}" if all(e in have for e in required) else line


def is_head_reviewed(summary: str) -> bool:
    return summary.startswith(f"{HEAD_REVIEWED}:")


def ruleset_name(policy: dict) -> str:
    return policy["github"]["ruleset"]


def render(policy: dict, apps: Mapping[str, int] | None = None) -> dict:
    """What the policy asks of GitHub: {"repository": the repository fields, "ruleset": the ruleset body or None}.
    `apps` maps an App slug to its integration id (APP_IDS by default; repo_policy asks GitHub for the rest). The
    mode decides: auto and queue turn auto-merge on, owner-only and direct off; direct has no server-side rule, so
    no ruleset."""
    p = validate(policy)
    ids = {**APP_IDS, **(apps or {})}
    repository = {"allow_auto_merge": p["mode"] in ("auto", "queue"), "delete_branch_on_merge": p["delete_branch_on_merge"],
                  **{field: m == p["method"] for m, field in REPO_FIELD.items()}}
    if p["mode"] == "direct":
        return {"repository": repository, "ruleset": None}
    rules: list[dict] = []
    if p["protect"].get("deletion"):
        rules.append({"type": "deletion"})
    if p["protect"].get("force_push"):
        rules.append({"type": "non_fast_forward"})
    rules.append({"type": "pull_request", "parameters": {
        "allowed_merge_methods": [p["method"]], "dismiss_stale_reviews_on_push": False, "require_code_owner_review": False,
        "require_last_push_approval": False, "required_approving_review_count": 0, "required_review_thread_resolution": False}})
    if p["required_checks"]:
        entries = []
        for c in p["required_checks"]:
            entry: dict[str, Any] = {"context": c["context"]}
            if "app" in c:
                if c["app"] not in ids:
                    raise PolicyError(f"no integration id is known for the App {c['app']!r} (repo_policy asks GitHub for it)")
                entry["integration_id"] = ids[c["app"]]
            entries.append(entry)
        rules.append({"type": "required_status_checks", "parameters": {
            "strict_required_status_checks_policy": False, "do_not_enforce_on_create": False, "required_status_checks": entries}})
    if p["mode"] == "queue":
        q = {**QUEUE_DEFAULTS, **p["queue"]}
        rules.append({"type": "merge_queue", "parameters": {
            "merge_method": p["method"].upper(), "grouping_strategy": q["grouping"].upper(),
            **{RULESET_PARAMETERS[k]: q[k] for k in RULESET_PARAMETERS}}})
    if p["signatures"]:
        rules.append({"type": "required_signatures"})
    branch = p["github"].get("branch")
    return {"repository": repository,
            "ruleset": {"name": ruleset_name(p), "target": "branch", "enforcement": "active",
                        "conditions": {"ref_name": {"include": [f"refs/heads/{branch}" if branch else "~DEFAULT_BRANCH"], "exclude": []}},
                        "bypass_actors": [], "rules": rules}}
