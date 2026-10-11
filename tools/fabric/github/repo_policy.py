#!/usr/bin/env python3
"""tools/fabric/github/repo_policy.py — a repository's arming policy against what GitHub holds: `fabric-repo-policy
plan` says what GitHub would have to change to match the policy, `verify` fails when it differs, and arm.py refuses
to arm on a repository that has drifted (arming step C; apply is step E's).

  fabric-repo-policy plan   [owner/repo] [--json]    exit 0; the differences, or "no change"
  fabric-repo-policy verify [owner/repo] [--json]    exit 0 when GitHub matches the policy, 1 when it differs
                                                     exit 2 for what could not be read or judged
A difference in which merge methods are allowed or in delete-branch-on-merge is `(advisory)`: verify fails on it,
arm does not refuse on it.

The repository defaults to the current one (gh.py). The policy is arm_policy.load(repo): the fleet's with the
client's settings repository's file over it. What it asks of GitHub is arm_policy.render(): the repository's
merge fields and the one ruleset the policy names (every other ruleset is left alone). What GitHub holds is read
with GETs only: the repository, its rulesets (the repository's own, not the organisation's) and, for an App named
in a required check that arm_policy does not know, apps/<slug>.

What is compared, and what is not: the repository fields allow_auto_merge, allow_merge_commit, allow_squash_merge,
allow_rebase_merge, delete_branch_on_merge; the ruleset's presence, target, enforcement, conditions and bypass
actors; its rules by type — a rule GitHub has that the policy does not want, and one the policy wants that GitHub
lacks — and for each rule the parameters the policy states (GitHub adds fields of its own, which are not
differences). Rule order is not. A read that fails is an error, never "no difference": an unreadable repository is
not a matching one.
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import gh  # noqa: E402
from github import arm_policy  # noqa: E402

REPOSITORY_FIELDS = ("allow_auto_merge", "allow_merge_commit", "allow_squash_merge", "allow_rebase_merge", "delete_branch_on_merge")
# What differs without changing how a pull request is held to its checks and merged: reported by plan and verify,
# never a reason for arm to refuse (the repository's other merge methods being allowed does not let anything
# through that the ruleset's pull_request rule and required checks hold).
ADVISORY_FIELDS = ("allow_merge_commit", "allow_squash_merge", "allow_rebase_merge", "delete_branch_on_merge")


class Unreadable(Exception):
    """GitHub's side could not be read, or the policy could not be rendered: nothing is known of the difference."""


def resolve_apps(policy: dict, api=gh.api) -> dict[str, int]:
    """The integration id of each App a required check names that arm_policy does not know, asked of GitHub."""
    ids: dict[str, int] = {}
    for c in policy["required_checks"]:
        slug = c.get("app")
        if slug and slug not in arm_policy.APP_IDS and slug not in ids:
            try:
                got = api(f"apps/{slug}")
            except gh.GhError as e:
                raise Unreadable(f"the App {slug!r} named by a required check cannot be looked up ({e.reason})") from None
            if not isinstance(got, dict) or not isinstance(got.get("id"), int) or isinstance(got.get("id"), bool):
                raise Unreadable(f"GitHub's answer for the App {slug!r} carries no id")
            ids[slug] = got["id"]
    return ids


def read_live(repo: str, name: str, api=gh.api) -> dict:
    """{"repository": the compared fields, "ruleset": the named ruleset's body or None}."""
    try:
        r = api(f"repos/{repo}")
        listed = api(f"repos/{repo}/rulesets?includes_parents=false", paginate=True)
        if not isinstance(r, dict) or not isinstance(listed, list):
            raise ValueError("an answer of another shape")
        missing = [f for f in REPOSITORY_FIELDS if not isinstance(r.get(f), bool)]
        if missing:
            raise ValueError(f"the repository carries no {', '.join(missing)} (the token may lack the right to see them)")
        ids = [x.get("id") for x in listed if isinstance(x, dict) and x.get("name") == name]
        ruleset = api(f"repos/{repo}/rulesets/{ids[0]}") if ids else None
        if ruleset is not None and not isinstance(ruleset, dict):
            raise ValueError("a ruleset of another shape")
    except gh.GhError as e:
        raise Unreadable(f"{repo}'s settings cannot be read ({e.reason})") from None
    except ValueError as e:
        raise Unreadable(f"{repo}'s settings cannot be read ({e})") from None
    return {"repository": {f: r[f] for f in REPOSITORY_FIELDS}, "ruleset": ruleset}


def _checks(params: dict) -> list:
    return sorted((c.get("context"), c.get("integration_id")) for c in params.get("required_status_checks") or [] if isinstance(c, dict))


def _rule_differences(want: dict, have: dict) -> list[str]:
    t = want["type"]
    out = []
    for k, v in (want.get("parameters") or {}).items():
        got = (have.get("parameters") or {}).get(k)
        if k == "required_status_checks":
            if _checks(want["parameters"]) != _checks(have.get("parameters") or {}):
                out.append(f"rule {t}: required checks are {_checks(have.get('parameters') or {})}, the policy wants {_checks(want['parameters'])}")
        elif got != v:
            out.append(f"rule {t}: {k} is {got!r}, the policy wants {v!r}")
    return out


def differences(desired: dict, live: dict, name: str) -> list[str]:
    """What GitHub holds that the policy does not ask for, and what the policy asks that GitHub does not hold, one
    line each, in a stable order; a line about an ADVISORY_FIELDS field ends `(advisory)`."""
    out = []
    for f in REPOSITORY_FIELDS:
        if live["repository"][f] != desired["repository"][f]:
            out.append(f"repository {f} is {live['repository'][f]}, the policy wants {desired['repository'][f]}"
                       + (" (advisory)" if f in ADVISORY_FIELDS else ""))
    want, have = desired["ruleset"], live["ruleset"]
    if want is None and have is not None:
        out.append(f"ruleset {name!r} exists, and the policy's mode has no server-side rule")
    if want is not None and have is None:
        out.append(f"ruleset {name!r} is missing")
    if want is not None and have is not None:
        for k in ("target", "enforcement"):
            if have.get(k) != want[k]:
                out.append(f"ruleset {k} is {have.get(k)!r}, the policy wants {want[k]!r}")
        if (have.get("conditions") or {}).get("ref_name") != want["conditions"]["ref_name"]:
            out.append(f"ruleset conditions are {(have.get('conditions') or {}).get('ref_name')!r}, the policy wants {want['conditions']['ref_name']!r}")
        if have.get("bypass_actors") != want["bypass_actors"]:
            out.append(f"ruleset bypass actors are {have.get('bypass_actors')!r}, the policy wants none")
        by_want = {r["type"]: r for r in want["rules"]}
        by_have = {r.get("type"): r for r in have.get("rules") or [] if isinstance(r, dict)}
        for t in sorted(by_want):
            if t not in by_have:
                out.append(f"rule {t} is missing")
            else:
                out += _rule_differences(by_want[t], by_have[t])
        for t in sorted(set(by_have) - set(by_want)):
            out.append(f"rule {t} is on the ruleset, and the policy does not want it")
    return out


def blocking(found: list[str]) -> list[str]:
    """The differences that bear on how a pull request is held and merged: all but the advisory ones."""
    return [line for line in found if not line.endswith("(advisory)")]


def check(repo: str, policy: dict, api=gh.api) -> list[str]:
    """The differences between the policy and GitHub's side of `repo`; Unreadable when either cannot be had."""
    try:
        desired = arm_policy.render(policy, resolve_apps(policy, api))
    except arm_policy.PolicyError as e:
        raise Unreadable(f"the policy cannot be mapped onto GitHub ({e})") from None
    return differences(desired, read_live(repo, arm_policy.ruleset_name(policy), api), arm_policy.ruleset_name(policy))


USAGE = "usage: fabric-repo-policy plan|verify [owner/repo] [--json]"


def run(argv: list[str], api=gh.api, out=sys.stdout, err=sys.stderr) -> int:
    args = [a for a in argv if a != "--json"]
    as_json = "--json" in argv
    if not args or args[0] not in ("plan", "verify") or len(args) > 2 or any(a.startswith("-") for a in args):
        print(USAGE, file=err)
        return 2
    verb = args[0]
    try:
        repo = args[1] if len(args) == 2 else gh.this_repo()
        if not arm_policy.is_repo_name(repo):
            print(f"fabric-repo-policy: {repo!r} is not an <owner>/<name>", file=err)
            return 2
        policy = arm_policy.load(repo, api=api)
        found = check(repo, policy, api)
    except (arm_policy.PolicyError, arm_policy.PolicyUnavailable, Unreadable) as e:
        print(f"fabric-repo-policy: {e}", file=err)
        return 2
    except gh.GhError as e:
        print(f"fabric-repo-policy: cannot read the repository: {e.reason}", file=err)
        return 2
    if as_json:
        print(json.dumps({"repository": repo, "verb": verb, "drift": bool(found), "blocking": blocking(found), "differences": found},
                         sort_keys=True), file=out)
    elif found:
        print(f"{repo}: GitHub differs from the arming policy in {len(found)} place(s):", file=out)
        for line in found:
            print(f"  {line}", file=out)
    else:
        print(f"{repo}: GitHub matches the arming policy", file=out)
    return 1 if (found and verb == "verify") else 0


def main() -> int:
    return run(sys.argv[1:])


if __name__ == "__main__":
    sys.exit(main())
