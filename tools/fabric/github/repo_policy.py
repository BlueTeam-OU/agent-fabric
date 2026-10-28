#!/usr/bin/env python3
"""tools/fabric/github/repo_policy.py — a repository's arming policy against what GitHub holds: `fabric-repo-policy
plan` says what GitHub would have to change to match the policy, `verify` fails when it differs, and arm.py refuses
to arm on a repository that has drifted (arming step C); `apply` writes the policy to GitHub (step E).

  fabric-repo-policy plan   [owner/repo] [--json]    exit 0; the differences, or "no change"
  fabric-repo-policy verify [owner/repo] [--json]    exit 0 when GitHub matches the policy, 1 when it differs
                                                     exit 2 for what could not be read or judged
  fabric-repo-policy apply  <owner/repo> [--yes] [--fleet-default] [--json]
                                                     the plan; with --yes, writes what differs and reads back
                                                     exit 0 when the read-back matches, re-read for up to 15 s (or with no --yes), 1 when a write
                                                     was refused or the read-back still differs, 2 as plan
A difference in which merge methods are allowed (a ruleset that allows the policy's method and more, or the
repository's allow_*_merge fields), in delete-branch-on-merge, or in bypass actors this token cannot see, is
`(advisory)`: verify fails on it, arm does not refuse on it.

The repository defaults to the current one (gh.py). The policy is arm_policy.load_with_source(repo): the
fleet's with the client's settings repository's file over it. What it asks of GitHub is arm_policy.render(): the repository's
merge fields and the one ruleset the policy names (every other ruleset is left alone). What GitHub holds is read
with GETs; apply alone writes: PATCH repos/<repo> with the differing REPOSITORY_FIELDS, then PUT the ruleset by
id when one of the policy's name exists, else POST it. Mode `direct` leaves an existing ruleset alone and says
so, so verify still differs after it. What is read is the repository, its rulesets (the repository's own, not the
organisation's) and, for an App named in a required check that arm_policy does not know, apps/<slug>.

Every verb says where the policy came from. A registered project whose own file (repos/<name>.json in its
client's settings repository) is not there yet gets the fleet's policy from arm_policy.load, which would drop its
queue and required checks if written: plan and verify report it and go on, apply refuses (exit 2, nothing
written). A repository that is no registered project's is applied only with --fleet-default.

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
import re
import sys
import time

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import gh  # noqa: E402
from github import arm_policy  # noqa: E402

REPOSITORY_FIELDS = arm_policy.REPOSITORY_FIELDS
# What differs without changing how a pull request is held to its checks and merged: reported by plan and verify,
# never a reason for arm to refuse (the repository's other merge methods being allowed does not let anything
# through that the ruleset's pull_request rule and required checks hold).
ADVISORY_FIELDS = ("allow_merge_commit", "allow_squash_merge", "allow_rebase_merge", "delete_branch_on_merge")


# GitHub's read right after a write can still answer the old settings (measured by devex-tooling: a PATCH that landed
# read back as differing, exit 1). The read-back is repeated after these waits, in seconds, until it matches; what
# still differs after the last is reported as it is. A module name so a test controls time instead of waiting.
READ_BACK_WAITS = (1, 2, 4, 8)
_sleep = time.sleep


# What an App's slug may be where it forms a request path: GitHub's own spelling.
APP_SLUG = re.compile(r"[a-z0-9][a-z0-9-]*")


class Unreadable(Exception):
    """GitHub's side could not be read, or the policy could not be rendered: nothing is known of the difference."""


def resolve_apps(policy: dict, api=gh.api) -> dict[str, int]:
    """The integration id of each App a required check names that arm_policy does not know, asked of GitHub."""
    ids: dict[str, int] = {}
    for c in policy["required_checks"]:
        slug = c.get("app")
        if slug and slug not in arm_policy.APP_IDS and slug not in ids:
            if not APP_SLUG.fullmatch(slug):
                raise Unreadable(f"the App {slug!r} named by a required check is not an App's slug")
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
        elif k == "allowed_merge_methods" and got != v:
            # More methods allowed than the policy's does not change how a merge is held; its method missing means
            # `gh pr merge --<method>` would fail.
            more = isinstance(got, list) and all(m in got for m in v)
            out.append(f"rule {t}: {k} is {got!r}, the policy wants {v!r}" + (" (advisory)" if more else ""))
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
        if "bypass_actors" not in have:
            out.append("ruleset bypass actors are not visible to this token, so none could be compared (advisory)")
        elif have["bypass_actors"] != want["bypass_actors"]:
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


def desired_state(policy: dict, api=gh.api) -> dict:
    """arm_policy.render of the policy with the Apps it names resolved; Unreadable when it cannot be mapped."""
    try:
        return arm_policy.render(policy, resolve_apps(policy, api))
    except arm_policy.PolicyError as e:
        raise Unreadable(f"the policy cannot be mapped onto GitHub ({e})") from None


def check(repo: str, policy: dict, api=gh.api) -> list[str]:
    """The differences between the policy and GitHub's side of `repo`; Unreadable when either cannot be had."""
    name = arm_policy.ruleset_name(policy)
    return differences(desired_state(policy, api), read_live(repo, name, api), name)


def write(repo: str, desired: dict, live: dict, found: list[str], written: list[str], notes: list[str], possible: list[str],
          api=gh.api) -> None:
    """Write exactly what differs (`found`), as render() says it, appending each call made to `written` as it lands
    (so a caller still has them when a later call is refused), what was left alone to `notes`, and a call whose
    outcome is unknown (gh.GhError transient: a timeout, an answer that is not JSON) to `possible` before it
    raises. The repository fields first, then the ruleset, so a refused PATCH leaves the ruleset untouched. A ruleset id is checked before
    the first write. gh.GhError propagates from a refused call; what was written before it stays."""
    changed = {f: desired["repository"][f] for f in REPOSITORY_FIELDS if live["repository"][f] != desired["repository"][f]}
    want, have = desired["ruleset"], live["ruleset"]
    rid = None
    if want is not None and have is not None and any(not line.startswith("repository ") for line in found):
        rid = have.get("id")
        if not isinstance(rid, int) or isinstance(rid, bool):
            raise Unreadable(f"GitHub's answer for the ruleset {want['name']!r} carries no id to update it by")
    def send(method: str, path: str, body: dict, label: str) -> None:
        try:
            api(path, method=method, body=body)
        except gh.GhError as e:
            if e.transient:
                possible.append(label)
            raise
        written.append(label)

    if changed:
        send("PATCH", f"repos/{repo}", changed, f"PATCH repos/{repo} ({', '.join(changed)})")
    if want is None:
        if have is not None:
            notes.append(f"the ruleset {have.get('name')!r} exists and the policy's mode has no server-side rule: left alone")
    elif have is None:
        send("POST", f"repos/{repo}/rulesets", want, f"POST repos/{repo}/rulesets")
    elif rid is not None:
        send("PUT", f"repos/{repo}/rulesets/{rid}", want, f"PUT repos/{repo}/rulesets/{rid}")


USAGE = "usage: fabric-repo-policy plan|verify [owner/repo] [--json] | apply <owner/repo> [--yes] [--fleet-default] [--json]"


def describe_source(repo: str, settings: str | None, has_file: bool) -> str:
    name = repo.split("/", 1)[1]
    if settings is None:
        return f"the fleet default ({repo} is no registered project's)"
    if has_file:
        return f"repos/{name}.json in {settings}"
    return f"the fleet default (repos/{name}.json is not in {settings}, which the project's client keeps its policy in)"


def _print_plan(repo: str, found: list[str], out) -> None:
    if found:
        print(f"{repo}: GitHub differs from the arming policy in {len(found)} place(s):", file=out)
        for line in found:
            print(f"  {line}", file=out)
    else:
        print(f"{repo}: GitHub matches the arming policy", file=out)


def run(argv: list[str], api=gh.api, out=sys.stdout, err=sys.stderr) -> int:
    as_json = "--json" in argv
    yes = "--yes" in argv
    fleet_default = "--fleet-default" in argv
    args = [a for a in argv if a not in ("--json", "--yes", "--fleet-default")]
    verb = args[0] if args else None
    if (verb not in ("plan", "verify", "apply") or len(args) > 2 or any(a.startswith("-") for a in args)
            or ((yes or fleet_default) and verb != "apply") or (verb == "apply" and len(args) != 2)):
        print(USAGE, file=err)
        return 2
    try:
        repo = args[1] if len(args) == 2 else gh.this_repo()
        if not arm_policy.is_repo_name(repo):
            print(f"fabric-repo-policy: {repo!r} is not an <owner>/<name>", file=err)
            return 2
        policy, settings, has_file = arm_policy.load_with_source(repo, api=api)
        source = describe_source(repo, settings, has_file)
        if verb == "apply" and settings is not None and not has_file:
            print(f"fabric-repo-policy: {source}; applying it would replace {repo}'s queue, required checks and rulesets "
                  f"with the default: nothing written (add the file first)", file=err)
            return 2
        if verb == "apply" and settings is None and not fleet_default:
            print(f"fabric-repo-policy: {source}; apply writes the default only with --fleet-default: nothing written", file=err)
            return 2
        name = arm_policy.ruleset_name(policy)
        desired = desired_state(policy, api)
        live = read_live(repo, name, api)
        found = differences(desired, live, name)
    except (arm_policy.PolicyError, arm_policy.PolicyUnavailable, Unreadable) as e:
        print(f"fabric-repo-policy: {e}", file=err)
        return 2
    except gh.GhError as e:
        print(f"fabric-repo-policy: cannot read the repository: {e.reason}", file=err)
        return 2
    if verb != "apply":
        if as_json:
            print(json.dumps({"repository": repo, "verb": verb, "drift": bool(found), "blocking": blocking(found), "differences": found,
                              "policy_source": source}, sort_keys=True), file=out)
        else:
            print(f"policy: {source}", file=out)
            _print_plan(repo, found, out)
        return 1 if (found and verb == "verify") else 0
    return _apply(repo, desired, live, found, name, yes, as_json, source, api, out, err)


def _apply(repo, desired, live, found, name, yes, as_json, source, api, out, err) -> int:
    written: list[str] = []
    notes: list[str] = []
    possible: list[str] = []
    after: list[str] = found
    rc = 0
    if found and yes:
        try:
            write(repo, desired, live, found, written, notes, possible, api)
        except Unreadable as e:
            print(f"fabric-repo-policy: {e}; nothing written", file=err)
            return 2
        except gh.GhError as e:
            if e.transient:
                print(f"fabric-repo-policy: the outcome of {e.what} is unknown ({e.reason}): it may have been written; "
                      f"run: fabric-repo-policy verify {repo}", file=err)
            else:
                print(f"fabric-repo-policy: GitHub refused {e.what}: {e.reason}", file=err)
            if written:
                print("fabric-repo-policy: what was written before it stays; a rerun is safe", file=err)
            if as_json:
                print(json.dumps({"repository": repo, "verb": "apply", "written": written, "possibly_written": possible,
                                  "error": f"{e.what}: {e.reason}", "policy_source": source}, sort_keys=True), file=out)
            elif possible:
                print(f"possibly written (outcome unknown): {', '.join(possible)}", file=out)
            return 1
        try:
            after = differences(desired, read_live(repo, name, api), name)
            for wait in READ_BACK_WAITS:
                if not after:
                    break
                _sleep(wait)
                after = differences(desired, read_live(repo, name, api), name)
        except Unreadable as e:
            print(f"fabric-repo-policy: written {written}, then the read-back failed: {e}", file=err)
            return 2
        rc = 1 if after else 0
    if as_json:
        print(json.dumps({"repository": repo, "verb": "apply", "written": written, "after": after, "drift": bool(found),
                          "blocking": blocking(found), "differences": found, "notes": notes, "possibly_written": possible,
                          "policy_source": source}, sort_keys=True), file=out)
    else:
        print(f"policy: {source}", file=out)
        _print_plan(repo, found, out)
        if found and not yes:
            print("re-run with --yes to write", file=out)
        for w in written:
            print(f"wrote {w}", file=out)
        for n in notes:
            print(n, file=out)
        if yes and found:
            if after:
                print(f"still differs after the write, in {len(after)} place(s):", file=out)
                for line in after:
                    print(f"  {line}", file=out)
            else:
                print("GitHub now matches the arming policy", file=out)
    return rc


def main() -> int:
    return run(sys.argv[1:])


if __name__ == "__main__":
    sys.exit(main())
