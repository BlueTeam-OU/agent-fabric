#!/usr/bin/env python3
"""tools/fabric/github/disarm.py — take an arming off a pull request and leave
the reason on it, as fabric-pr arm leaves its basis (`fabric-pr disarm` runs
it; REQUEST 01a1c27c: an authority that withdrew an arming on a managed
project's PR #600 had no verb, and left no trace).

CONTRACT
  argv      <pr-number> --basis "<one line>" [--any-owner] [--dry-run] [-h|--help]
  env       AGENT_FABRIC_PR_SESSION (<host>/<login>), AGENT_FABRIC_WHOAMI
            (fabric-whoami, run as a program: <it> --json; the role of this
            session by its binding, which the comment names), and the
            arming policy's settings, read as fabric-pr arm reads them
  stdout    `disarm: ` lines — what was found and what was done
  stderr    `disarm: REFUSED #N — <why>` on a refusal; `disarm: <why>` when a
            question could not be answered, or on a usage error
  exit      0 disarmed (read back with no auto-merge and no merge-queue
            entry), or not armed — said, nothing changed and nothing posted
            (or, with --dry-run, would disarm); 1 refused; 2 gh / the arming
            policy / fabric-whoami / the role catalogue could not answer, the
            read-back still armed, queued or merged, or usage

WHO MAY DISARM is who may arm (THE WORD OF A ROLE UNDER THE MINIMUM in
arm.py), never more: the session whose branch the PR is; on another
session's PR, --any-owner with a basis giving the owner's word (the owner's
claim, as arm takes it) or "<role>'s word" for a role the repository's arming
policy names as commits.below_min_authority or commits.boundary_authority,
checked against this session's binding (fabric-whoami, never a message's ROLE
line). A repository whose policy is owner-only is not disarmed here, as it is
not armed here. The other gates of arm (review, count, checks) judge whether a
head may merge; none of them stands between a merge and its withdrawal.

ARMED is any of: auto-merge enabled, a merge-queue entry, or the policy's
armed_status (fabric/armed) at success on the PR's head. Each one found is
taken off: the status first — set to pending, since GitHub deletes no status,
and in an auto repository the ruleset then holds the head until an arming of
its own — then the queue entry and auto-merge. The comment follows, "Disarming
basis: <text> — <role>, head <sha8>.", and the PR is read back.
"""
from __future__ import annotations

import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import gh  # noqa: E402
from github import arm, arm_policy, common, pr_gate  # noqa: E402
from github.arm_rules import Refused, Unanswered, has_owner_word  # noqa: E402

HELP = """Take an arming off a PR, and post why — as arm posts its basis.

  fabric-pr disarm <pr-number> --basis "<one line>" [--any-owner] [--dry-run]

Who may: whoever may arm it. This session's own PR; another session's only
with --any-owner and a basis that gives "the owner's word", or "<role>'s word"
for the role the arming policy names as commits.below_min_authority or
commits.boundary_authority, held by this session's binding. A repository whose
policy is owner-only is refused.

What it takes off: the head's fabric/armed status (set to pending: the ruleset
then holds the head until it is armed again), a merge-queue entry, auto-merge.
Then it posts "Disarming basis: <text> — <role>, head <sha8>." and reads the PR
back. A PR armed by none of the three is said so: nothing changed, nothing
posted, exit 0.

Options:
  --basis "<text>"  required: the one-line disarming basis
  --any-owner       disarm a PR whose branch is not this session's
  --dry-run         say what would be taken off, change nothing, post nothing
  --repo <owner/name|project>  the PR's repository, not the cwd checkout's

Exit codes:
  0  disarmed, or not armed (or, with --dry-run, would disarm)
  1  refused — the reason is the last line
  2  gh / the arming policy / fabric-whoami / the role catalogue could not
     answer, the read-back is still armed, or usage"""

# GitHub cuts a status description at 140 characters.
DISARMED_DESCRIPTION = "Disarmed through fabric-pr disarm: this head waits for an arming of its own"
PR_QUERY = ("query($o:String!,$n:String!,$num:Int!){repository(owner:$o,name:$n){pullRequest(number:$num)"
            "{id state headRefName headRefOid title autoMergeRequest{enabledAt} mergeQueueEntry{position}}}}")


def say(msg: str) -> None:
    print(f"disarm: {msg}", flush=True)


def read_pr(owner: str, name: str, num: str) -> dict:
    try:
        p = gh.graphql(PR_QUERY, o=owner, n=name, num=int(num))["repository"]["pullRequest"]
        if not isinstance(p, dict) or not isinstance(p.get("headRefOid"), str) or not isinstance(p.get("state"), str):
            raise TypeError("no pull request")
    except (gh.GhError, KeyError, TypeError):
        raise Unanswered(f"cannot read #{num}") from None
    return p


def head_status(repo: str, head: str, context: str) -> str:
    """The state of `context` on `head` as GitHub's combined status has it (the latest per context), "" for none."""
    try:
        doc = gh.api(f"repos/{repo}/commits/{head}/status?per_page=100")
        for s in doc["statuses"]:
            if s.get("context") == context:
                return str(s.get("state") or "")
    except (gh.GhError, KeyError, TypeError, AttributeError):
        raise Unanswered(f"cannot read {context} on {head[:8]}: whether the head is armed is unknown") from None
    return ""


def disarm(argv: list[str]) -> int:
    num = basis = ""
    any_owner = dry = False
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--basis":
            basis = argv[i + 1] if i + 1 < len(argv) else ""
            i += 2
            continue
        if a == "--any-owner":
            any_owner = True
        elif a == "--dry-run":
            dry = True
        elif a in ("-h", "--help"):
            print(HELP)
            return 0
        elif a.startswith("-"):
            raise Unanswered(f"unknown option '{a}' (try --help)")
        else:
            if num or not re.fullmatch(r"[0-9]+", a):
                raise Unanswered("one PR number, then options (try --help)")
            num = a
        i += 1
    if not num:
        raise Unanswered("the PR number is required")
    if not basis.strip():
        raise Unanswered('--basis "<one line>" is required — the disarming comment is the record')
    if not shutil.which("gh"):
        raise Unanswered("gh is required")

    def refuse(why: str) -> Refused:
        return Refused(f"REFUSED #{num} — {why}")

    try:
        repo = gh.this_repo()
    except gh.GhError as e:
        raise Unanswered(f"cannot read the repository: {e.reason}") from None
    owner, name = repo.split("/", 1)
    pr = read_pr(owner, name, num)
    branch, head, title = str(pr.get("headRefName") or ""), pr["headRefOid"], str(pr.get("title") or "")
    if pr["state"] != "OPEN":
        raise refuse(f"it is {pr['state']}, not open: there is no arming to take off")

    try:
        policy = arm_policy.load(repo)
    except (arm_policy.PolicyError, arm_policy.PolicyUnavailable) as e:
        raise Unanswered(f"the arming policy for {repo} cannot be read ({e}); who may disarm is not read from a guess") from None
    if policy["mode"] == "owner-only":
        raise refuse(f"{repo}'s arming policy is owner-only: fabric-pr never arms it, and so never disarms it (the owner"
                     " takes auto-merge off by hand)")

    session = pr_gate.session_prefix()
    # Read for every disarming, not only an authority's: the comment names the role that withdrew the arming.
    held = arm.session_role(session)
    if branch.startswith(f"{session}/"):
        say("this session's own PR")
    elif not any_owner:
        raise refuse(f"its branch {branch} is not this session's ({session}/…): never disarm another session's PR"
                     " (--any-owner, on the owner's word or on the word of the arming policy's authority role)")
    elif has_owner_word(basis):
        say(f"another session's PR ({branch}), on the owner's word")
    else:
        named = [(k, policy["commits"][k]) for k in arm_policy.AUTHORITY_KEYS if policy["commits"].get(k)]
        claimed = [(k, r) for k, r in named if re.search(rf"(?<![\w-]){re.escape(r)}(?:'|’)s word", basis, re.I)]
        roles = " or ".join(sorted({r for _, r in named})) or "none"
        if not claimed:
            raise refuse(f"another session's PR is disarmed on the owner's word or on the word of a role {repo}'s arming"
                         f" policy names to arm in the owner's place ({roles}), and the basis gives neither")
        key, role = claimed[0]
        arm.authority_role_checked(role, repo, key)
        if held != role:
            raise refuse(f"the basis gives {role}'s word, and this session holds {held or 'no role'} by its binding, not"
                         f" {role}: an authority that may not arm may not disarm")
        say(f"another session's PR ({branch}), on the word of {role}, which this session holds by its binding")

    context = arm_policy.armed_status(policy)
    tied = bool(context) and head_status(repo, head, context) == "success"
    auto, queued = pr.get("autoMergeRequest") is not None, pr.get("mergeQueueEntry") is not None
    found = [what for what, on in ((f"{context} on {head[:8]}", tied), ("the merge-queue entry", queued),
                                   ("auto-merge", auto)) if on]
    if not found:
        say(f"#{num} is not armed: no auto-merge, no merge-queue entry"
            f"{f', and {head[:8]} carries no {context} success' if context else ''} — nothing changed, nothing posted")
        return 0
    comment = f"{common.DISARMING_BASIS} {basis.strip()} — {held or 'no role'}, head {head[:8]}."
    if dry:
        say(f"DRY RUN — would take off: {', '.join(found)}")
        say(f"DRY RUN — would post: {comment}")
        return 0
    taken: list[str] = []
    if tied:
        try:
            gh.api(f"repos/{repo}/statuses/{head}", method="POST",
                   body={"state": "pending", "context": context, "description": DISARMED_DESCRIPTION})
        except gh.GhError as e:
            raise Unanswered(f"could not set {context} on {head[:8]} to pending ({e.reason}): nothing taken off") from None
        say(f"{context} on {head[:8]} set to pending: the head waits for an arming of its own")
        taken.append(f"{context} on {head[:8]}")
    try:
        if queued:
            gh.graphql("mutation($id:ID!){dequeuePullRequest(input:{id:$id}){clientMutationId}}", id=pr["id"])
            say(f"#{num} taken out of the merge queue")
            taken.append("the merge-queue entry")
        if auto:
            gh.graphql("mutation($id:ID!){disablePullRequestAutoMerge(input:{pullRequestId:$id}){clientMutationId}}",
                       id=pr["id"])
            say(f"auto-merge taken off #{num}")
    except (gh.GhError, KeyError) as e:
        # stderr may be all a caller keeps: it names what is already off, as the stdout lines did.
        raise Unanswered(f"could not take #{num}'s arming off ({getattr(e, 'reason', e)}); already taken off:"
                         f" {', '.join(taken) or 'nothing'}; read gh pr view {num}") from None
    # The body on stdin: a body is data (gh.py's invariant).
    try:
        gh.run(["pr", "comment", num, "--body-file", "-"], input=comment, what=f"gh pr comment {num}")
    except gh.GhError:
        raise Unanswered(f"#{num} is disarmed, and the basis comment could not be posted: post it by hand — {comment}") from None
    back = read_pr(owner, name, num)
    if back["state"] != "OPEN":
        raise Unanswered(f"#{num} reads {back['state']} after the disarming: it may have merged before it took")
    if back.get("autoMergeRequest") is not None or back.get("mergeQueueEntry") is not None:
        raise Unanswered(f"#{num} still reads armed or queued after the disarming — check gh pr view {num}")
    say(f"DISARMED #{num} ({title}) — took off {', '.join(found)}; basis posted.")
    return 0


def main(argv: list[str]) -> int:
    common.apply_project_env("disarm")
    try:
        return disarm(argv)
    except Refused as e:
        print(f"disarm: {e}", file=sys.stderr)
        return 1
    except Unanswered as e:
        print(f"disarm: {e}", file=sys.stderr)
        return 2
    except Exception as e:  # noqa: BLE001 — an answer of a shape gh never gave: unanswered, never "refused"
        print(f"disarm: an unexpected answer stopped it ({type(e).__name__}: {e}); read gh pr view before retrying",
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
