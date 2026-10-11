"""tools/fabric/github/arm_policy.py — a repository's arming policy: how many work commits arm at the review gate,
who may arm under it, and the GitHub settings that enforce the rest, as one document (the owner, 2026-10-11).
Step A of the arming-policy work (fabric-coordinator REQUEST 01a12a13-cceb-755e-91b1-7f4e8236c1cf and its two
changes, INFO 01a12a14-985a-72e4-ba2f-f8a025a302c5 and 01a12a15-752f-7755-848a-1011e8949867): no behaviour
change. arm.py and pr_gate.py read the 8 and the 16 through here; until a policy file says otherwise the built-in
default is what they did.

WHERE A POLICY IS. Two layers, the second over the first:
  fleet     policies/arming.json in the fabric's tree (absent: DEFAULT below, today's behaviour)
  repo      repos/<owner>/<repo>.json in the settings repository that projects/registry.json names in
            `settings_repo` ("<owner>/<name>"), read from that repository's default branch through gh.py's
            contents API: never from a pull request's head or a working copy, so a PR cannot change the rules it is
            armed under. No `settings_repo` in the registry, or the repository has no file for this repo (HTTP 404):
            the fleet policy applies. Any other failure to read it — no answer, a refusal, a file that is not JSON —
            is PolicyUnavailable: an unreadable policy is never the default, because a default that is more
            permissive than the repository's own would arm what the repository meant to hold.
Objects merge recursively, scalars and lists replace. The fetched file is cached by the caller for one run
(`cache=`), never between runs. The schema of both files is identities/schemas/arming.schema.json (the
coordinator's); this module validates the same shape and refuses an unknown key, a typo must not fall to the default.

THE DOCUMENT (every key optional in a file; the merged policy has them all):
  mode           "auto" | "queue"      GitHub auto-merge, or the merge queue
  method         "merge" | "squash" | "rebase"
  commits        {min, advice_over, below_min}
                   min          work commits that arm at the review gate (8)
                   advice_over  over this many is advice for the next batch, never a refusal (16)
                   below_min    "owner-word": under min, arming needs the owner's word (the only value)
  roles          {<role slug>: {min}}  the minimum for a pull request whose author holds the role
  classes        {<name>: {paths, min}} | {<name>: "<regex>"} (the older arm.json form, = {paths, min: 1}):
                   a stated class whose regex every changed file matches arms at its own min
  required_checks  [<check context>, ...]      required_status_checks
  app            integration id of the App that reports them, or null
  signatures     bool                  required_signatures
  protect        ["deletion", "non_fast_forward", ...] subset
  delete_branch_on_merge  bool
  queue          the merge queue's parameters, read when mode is "queue"
  ruleset_name   the ruleset's name ("main protection")

threshold() IS THE ORDER OF SPECIFICITY: a stated class whose regex every file matches, then the author's role,
then the repository's minimum (the merged `commits.min`, which is the repository's own or else the fleet's). A
security-boundary change not waived is judged against the repository's minimum and never lowered by role or class.
render() IS THE MAPPING to GitHub: the repository fields and the ruleset body (docs/adr/ADR-019 §6).
"""
from __future__ import annotations

import base64
import binascii
import copy
import json
import os
import re
import sys
from typing import Any, Callable

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import gh  # noqa: E402
import roots  # noqa: E402

REPO_NAME = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
ROLE_SLUG = re.compile(r"[a-z0-9][a-z0-9-]*")
# A class is named in a PR body as `Class: <name>`: a project's existing names have spaces ("single-check tooling").
CLASS_NAME = re.compile(r"\S[^\n]*")
MODES = ("auto", "queue")
METHODS = ("merge", "squash", "rebase")
PROTECT = ("deletion", "non_fast_forward")
GROUPING = ("ALLGREEN", "HEADGREEN")
QUEUE_METHODS = ("MERGE", "SQUASH", "REBASE")
BELOW_MIN = ("owner-word",)
# GitHub's repository fields for the merge methods: the merge commit's is the odd one out.
REPO_FIELD = {"merge": "allow_merge_commit", "squash": "allow_squash_merge", "rebase": "allow_rebase_merge"}

# Today's behaviour: arm.py and pr_gate.py before this module. The queue block carries GitHub's own defaults.
DEFAULT: dict[str, Any] = {
    "mode": "auto",
    "method": "merge",
    "commits": {"min": 8, "advice_over": 16, "below_min": "owner-word"},
    "roles": {},
    "classes": {},
    "required_checks": [],
    "app": None,
    "signatures": False,
    "protect": ["deletion", "non_fast_forward"],
    "delete_branch_on_merge": False,
    "queue": {"merge_method": "MERGE", "grouping_strategy": "ALLGREEN", "max_entries_to_build": 5, "max_entries_to_merge": 5,
              "min_entries_to_merge": 1, "min_entries_to_merge_wait_minutes": 5, "check_response_timeout_minutes": 60},
    "ruleset_name": "main protection",
}
# `$schema` and `description` are for the reader of the file.
IGNORED_KEYS = ("$schema", "description")


class PolicyError(ValueError):
    """A policy document that is not one: the message names the file and the key."""


class PolicyUnavailable(Exception):
    """The repository's policy could not be read at all (not: it has none). Never answered with the default."""


def is_repo_name(v: Any) -> bool:
    """An <owner>/<name> as GitHub spells one; `.` and `..` are no owner or name, and they are what a path walks by."""
    return isinstance(v, str) and REPO_NAME.fullmatch(v) is not None and all(part not in (".", "..") for part in v.split("/"))


def _int(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def merge(base: Any, over: Any) -> Any:
    """Objects merge recursively; anything else in `over` replaces `base`."""
    if isinstance(base, dict) and isinstance(over, dict):
        out = dict(base)
        for k, v in over.items():
            out[k] = merge(base[k], v) if k in base else copy.deepcopy(v)
        return out
    return copy.deepcopy(over)


def normalize_classes(raw: Any, where: str = "classes") -> dict[str, dict]:
    """{name: regex} (the arm.json form) and {name: {paths, min}} as the second; the older form is {min: 1}."""
    if not isinstance(raw, dict):
        raise PolicyError(f"{where} is not an object of class names")
    out = {}
    for name, spec in raw.items():
        name = str(name).lower()
        if not CLASS_NAME.fullmatch(name) or name != name.strip():
            raise PolicyError(f"{where}: {name!r} is not a class name")
        if isinstance(spec, str):
            spec = {"paths": spec, "min": 1}
        if not isinstance(spec, dict) or set(spec) - {"paths", "min"} or not isinstance(spec.get("paths"), str):
            raise PolicyError(f"{where}.{name} is not a regex or an object with `paths` and `min`")
        floor = spec.get("min", 1)
        if not _int(floor) or floor < 1:
            raise PolicyError(f"{where}.{name}.min is not a whole number of at least 1")
        try:
            re.compile(spec["paths"])
        except re.error as e:
            raise PolicyError(f"{where}.{name}.paths is not a regex ({e})") from None
        if name in out:
            raise PolicyError(f"{where}: class {name!r} is named twice")
        out[name] = {"paths": spec["paths"], "min": floor}
    return out


def validate(doc: Any, where: str = "the policy") -> dict:
    """The document, checked and normalized (a copy). Raises PolicyError naming `where` and the key."""
    if not isinstance(doc, dict):
        raise PolicyError(f"{where} is not an object")
    unknown = sorted(set(doc) - set(DEFAULT) - set(IGNORED_KEYS))
    if unknown:
        raise PolicyError(f"{where}: unknown key(s) {', '.join(unknown)}; the keys are {', '.join(DEFAULT)}")
    p = merge(DEFAULT, {k: v for k, v in doc.items() if k not in IGNORED_KEYS})

    def one_of(key: str, allowed: tuple) -> None:
        if p[key] not in allowed:
            raise PolicyError(f"{where}: {key} is {p[key]!r}, not one of {', '.join(allowed)}")
    one_of("mode", MODES)
    one_of("method", METHODS)
    c = p["commits"]
    if not isinstance(c, dict) or set(c) - set(DEFAULT["commits"]):
        raise PolicyError(f"{where}: commits is not an object of {', '.join(DEFAULT['commits'])}")
    for k in ("min", "advice_over"):
        if not _int(c.get(k)) or c[k] < 1:
            raise PolicyError(f"{where}: commits.{k} is not a whole number of at least 1")
    if c["advice_over"] < c["min"]:
        raise PolicyError(f"{where}: commits.advice_over ({c['advice_over']}) is under commits.min ({c['min']})")
    if c.get("below_min") not in BELOW_MIN:
        raise PolicyError(f"{where}: commits.below_min is {c.get('below_min')!r}, not one of {', '.join(BELOW_MIN)}")
    roles = p["roles"]
    if not isinstance(roles, dict):
        raise PolicyError(f"{where}: roles is not an object of role slugs")
    for slug, spec in roles.items():
        if not ROLE_SLUG.fullmatch(str(slug)):
            raise PolicyError(f"{where}: roles: {slug!r} is not a role slug")
        if not isinstance(spec, dict) or set(spec) != {"min"} or not _int(spec["min"]) or spec["min"] < 1:
            raise PolicyError(f"{where}: roles.{slug} is not {{\"min\": a whole number of at least 1}}")
    p["classes"] = normalize_classes(p["classes"], f"{where}: classes")
    checks = p["required_checks"]
    if not isinstance(checks, list) or not all(isinstance(x, str) and x and x == x.strip() for x in checks) or len(set(checks)) != len(checks):
        raise PolicyError(f"{where}: required_checks is not a list of distinct check names")
    if p["app"] is not None and (not _int(p["app"]) or p["app"] < 1):
        raise PolicyError(f"{where}: app is not an App's integration id or null")
    if not isinstance(p["signatures"], bool) or not isinstance(p["delete_branch_on_merge"], bool):
        raise PolicyError(f"{where}: signatures and delete_branch_on_merge are true or false")
    if not isinstance(p["protect"], list) or any(x not in PROTECT for x in p["protect"]) or len(set(p["protect"])) != len(p["protect"]):
        raise PolicyError(f"{where}: protect is not a list drawn from {', '.join(PROTECT)}")
    q = p["queue"]
    if not isinstance(q, dict) or set(q) != set(DEFAULT["queue"]):
        raise PolicyError(f"{where}: queue is not an object of {', '.join(DEFAULT['queue'])}")
    if q["merge_method"] not in QUEUE_METHODS or q["grouping_strategy"] not in GROUPING:
        raise PolicyError(f"{where}: queue.merge_method is one of {', '.join(QUEUE_METHODS)}, queue.grouping_strategy one of {', '.join(GROUPING)}")
    for k in DEFAULT["queue"]:
        if k not in ("merge_method", "grouping_strategy") and (not _int(q[k]) or q[k] < 1):
            raise PolicyError(f"{where}: queue.{k} is not a whole number of at least 1")
    if q["min_entries_to_merge"] > q["max_entries_to_merge"]:
        raise PolicyError(f"{where}: queue.min_entries_to_merge is over queue.max_entries_to_merge")
    if not isinstance(p["ruleset_name"], str) or not p["ruleset_name"].strip():
        raise PolicyError(f"{where}: ruleset_name is not a name")
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
    """The built-in policy: today's behaviour, for a caller with no repository to load for."""
    return validate({})


def settings_repo(registry: Any) -> str | None:
    """The settings repository the registry names, or None when it names none (the feature is not set up)."""
    value = registry.get("settings_repo") if isinstance(registry, dict) else None
    if value is None:
        return None
    if not is_repo_name(value):
        raise PolicyError("projects/registry.json: settings_repo is not an <owner>/<name>")
    return value


def fetch_repo_policy(settings: str, repo: str, api: Callable[..., Any] = gh.api) -> dict | None:
    """repos/<repo>.json from the settings repository's default branch, or None when it has none (404). Every
    other failure raises PolicyUnavailable."""
    if not is_repo_name(repo):
        raise PolicyUnavailable(f"{repo!r} is not an <owner>/<name>")
    where = f"{settings} repos/{repo}.json"
    try:
        # No `ref`: the contents API reads the default branch, which is the point.
        answer = api(f"repos/{settings}/contents/repos/{repo}.json")
    except gh.GhError as e:
        if e.status == 404:
            return None
        raise PolicyUnavailable(f"{where} could not be read ({e.reason})") from None
    try:
        if not isinstance(answer, dict) or answer.get("type") != "file" or answer.get("encoding") != "base64":
            raise ValueError("not a file")
        doc = json.loads(base64.b64decode(answer["content"], validate=False).decode("utf-8"))
    except (ValueError, KeyError, TypeError, binascii.Error, UnicodeDecodeError) as e:
        raise PolicyUnavailable(f"{where} is not a JSON file ({type(e).__name__})") from None
    if not isinstance(doc, dict):
        raise PolicyUnavailable(f"{where} is not an object")
    return doc


def load(repo: str | None, *, root: str | None = None, registry: Any = None, api: Callable[..., Any] = gh.api,
         cache: dict | None = None) -> dict:
    """The policy for `repo` ("<owner>/<name>"; None: the fleet's). `cache` is the caller's dict, for one run: a
    repository's file is fetched once. PolicyError for a document that is not valid, PolicyUnavailable when the
    repository's file could not be read."""
    fleet = fleet_policy(root)
    if not repo:
        return fleet
    if cache is not None and repo in cache:
        return copy.deepcopy(cache[repo])
    if registry is None:
        import workingcopy
        try:
            registry = workingcopy.load_registry()
        except (OSError, ValueError) as e:
            raise PolicyUnavailable(f"projects/registry.json cannot be read ({e})") from None
    settings = settings_repo(registry)
    doc = fetch_repo_policy(settings, repo, api) if settings else None
    policy = fleet if doc is None else validate(merge(fleet, {k: v for k, v in doc.items() if k not in IGNORED_KEYS}),
                                                f"{settings} repos/{repo}.json")
    if cache is not None:
        cache[repo] = copy.deepcopy(policy)
    return policy


def with_classes(policy: dict, classes: dict[str, str]) -> dict:
    """The policy with a project's older arm.json classes ({name: regex}) added under the policy's own: a class
    the policy states wins. Step A leaves classes in arm.json."""
    out = copy.deepcopy(policy)
    out["classes"] = {**normalize_classes(classes, "arm.json classes"), **policy["classes"]}
    return out


def threshold(policy: dict, role: str | None, cls: str | None, boundary: bool) -> int:
    """The work commits at which this pull request arms at the review gate. `cls` is the stated class whose
    regex every changed file matches (the caller checked), or empty; `boundary` is a security-boundary change not
    waived. Most specific first: class, role, repository; a boundary change gets the repository's minimum and
    nothing lowers it."""
    base = policy["commits"]["min"]
    if boundary:
        return base
    if cls:
        if cls not in policy["classes"]:
            raise PolicyError(f"the policy has no class {cls!r}")
        return policy["classes"][cls]["min"]
    spec = policy["roles"].get(role) if role else None
    return spec["min"] if spec else base


def render(policy: dict) -> dict:
    """What the policy asks of GitHub: {"repository": the repository fields, "ruleset": the ruleset body}."""
    p = validate(policy)
    repository = {"allow_auto_merge": True, "delete_branch_on_merge": p["delete_branch_on_merge"],
                  **{field: m == p["method"] for m, field in REPO_FIELD.items()}}
    rules: list[dict] = [{"type": t} for t in p["protect"]]
    rules.append({"type": "pull_request", "parameters": {
        "allowed_merge_methods": [p["method"]], "dismiss_stale_reviews_on_push": False, "require_code_owner_review": False,
        "require_last_push_approval": False, "required_approving_review_count": 0, "required_review_thread_resolution": False}})
    if p["required_checks"]:
        rules.append({"type": "required_status_checks", "parameters": {
            "strict_required_status_checks_policy": False, "do_not_enforce_on_create": False,
            "required_status_checks": [{"context": c, **({"integration_id": p["app"]} if p["app"] is not None else {})}
                                       for c in p["required_checks"]]}})
    if p["mode"] == "queue":
        rules.append({"type": "merge_queue", "parameters": dict(p["queue"])})
    if p["signatures"]:
        rules.append({"type": "required_signatures"})
    return {"repository": repository,
            "ruleset": {"name": p["ruleset_name"], "target": "branch", "enforcement": "active",
                        "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}},
                        "bypass_actors": [], "rules": rules}}
