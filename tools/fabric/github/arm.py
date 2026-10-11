#!/usr/bin/env python3
"""tools/fabric/github/arm.py — arm auto-merge on a pull request with the
gates the managed projects put before the arming applied by the tool, not
by memory (ADR-019's count rule; `fabric-pr arm` runs it). Ported from
the first managed project's tools/gh/arm.sh, whose test is the oracle
(ADR-040 §5 rules 3–5); what was that project's own — the security-boundary paths and the classes that
arm under the floor without asking — is now the project's arm.json.

CONTRACT, frozen from the bash (ADR-040 §5 rule 3), its argv amended
since (agent-fabric #92): a boundary is waived only on the waiver role
holder's message, so --no-boundary alone — the bash's form — is now a
usage error, on a PR with no boundary file too, where a waiver of
nothing wrote a false record.
  argv      <pr-number> --basis "<one line>"
            [--boundary | --no-boundary "<why>" --waiver <message-id|seq>]
            [--authorization <message-id|seq>]
            [--any-owner] [--dry-run] [-h|--help]
            --no-boundary and --waiver come together; either alone is
            usage (exit 2)
  env       AGENT_FABRIC_PR_GATE (the count reader, run as a program),
            AGENT_FABRIC_PR_REVIEW_STATUS (the review reader, run as a
            program), AGENT_FABRIC_PR_SESSION (<host>/<login>),
            AGENT_FABRIC_ARM_CONFIG (an arm.json used instead of the
            project's), AGENT_FABRIC_GZCOORD_INBOX (the inbox, run as a
            program: <it> --replay <id> --json), AGENT_FABRIC_CTL
            (fabric-ctl, run as a program: <it> <login> presence
            --json), AGENT_FABRIC_ROOT
  stdout    `arm: ` lines — what each gate found, and the watcher line
            (none for a PR that merged on the arming)
  stderr    `arm: REFUSED #N — <why>` on a refusal; `arm: <why>` when a
            question could not be answered, or on a usage error
  exit      0 read back armed, queued or merged, each on the head the
            gates read (or, with --dry-run, would arm); 1 refused — the
            reason is the last line; 2 gh / pr-gate / pr-review-status /
            the project's arm.json / the relay / fabric-ctl could not
            answer, the read-back is idle, closed or on another head,
            or usage

THE WAIVER:
the security-boundary gate is waived only on a message from the holder
of the project's waiver role, read from the relay and checked here, never
on the caller's say-so. Read only when a boundary matched: on a PR that
matched none the waiver is said, not read, and not recorded. It is
refused (exit 1) unless ALL of —
  - the replay says it is addressed to this session, and its TO is this
    session's own <host>/<login>: a BROADCAST or a TO-ROLE is not a
    waiver given to this session;
  - its type is DECISION or REPLY;
  - the relay's sender is a <host>/<login>, its FROM says the same, and
    it is not this session's own login (no self-waiver);
  - it carries the metadata line the approver writes on purpose,
        WAIVES: <owner>/<repo>#<n>@<head sha, 8 or more hex>
    naming this repository (case-insensitive), this PR, and a prefix of
    its CURRENT head — a message that only mentions the PR, a decline
    included, waives nothing, and an approval of one head arms no other;
  - fabric-ctl's presence of that login, on that host, reports the
    role arm.json's `waiver_role` names — the fabric's record of the
    login's binding, never the message's ROLE line.
Unanswerable (exit 2, nothing posted): the replay not giving its JSON
(relay down, no such message, a refused token), a waiver with no
MESSAGE-ID, fabric-ctl not answering for the login, and an arm.json
whose waiver_role is missing while a waiver is asked, or is not a role
of identities/roles/catalog.json. The arming comment records "Boundary
gate waived by <login> (<message-id>): <why>". A boundary that is NOT
waived still needs the review of the head and no open thread, and,
under the policy's boundary minimum (commits.boundary_min, 8 by default) work commits, the owner's word.

THE ARMING POLICY (tools/fabric/github/arm_policy.py; the 8 and the 16 in the gates below are its defaults): the
fleet's policies/arming.json with the repository's file in its client's settings repository over it. Read before
the count rule, and a policy or a comparison with GitHub's settings that cannot be read is exit 2, never the
default. A repository in mode owner-only or direct is not armed here. A difference between the policy and GitHub
in how a merge is held (auto-merge off, a ruleset or required check missing or changed) is a refusal; in which
merge methods are allowed, advisory. The minimum is the stated class's, else the author's role's (the
Fabric-Role trailer every commit of the PR carries, when they agree), else commits.min; a boundary change gets
max(commits.min, commits.boundary_min) whatever role or class; commits.below_min "refuse" is a refusal the owner's
word does not lift; the merge method is the policy's; a repository with no required check is armed only with every
check on the head green.

AUTHORIZATION (commits.boundary_authority, a role slug the policy may name): a security-boundary change under its
minimum arms without the owner's word on `--authorization <MESSAGE-ID|seq>`: a DECISION or REPLY sent TO this session
(never a broadcast or a role address), from another login whose presence (fabric-ctl, never the ROLE line) reports
that role, carrying
        AUTHORIZES: <owner>/<repo>#<n>@<head sha, 8 or more hex>
for this repository, PR and current head. The same checks and exit codes as a waiver; unlike a waiver it drops no
gate: the head's review and the open threads are judged first, whatever it says, and a policy with no
boundary_authority refuses it. The comment records who authorized it and the message. arm.json's waiver_role
stays the waiver's.

WHAT THIS DOES NOT PROVE: the relay does not authenticate a sender
(BRIDGE-RELAY-SETUP.md) — FROM and the relay's sender are both the
poster's claim. The check stops a mistake (the wrong message, the wrong
PR, a decline, a stale head, a role not held), not a forger: a session
able to forge a waiver can run gh pr merge itself. A signed waiver is a
protocol question, not this tool's.

THE PROJECT'S RULES, projects/<id>/integration/gh/arm.json, found from
this clone's remote as trial.json is (or AGENT_FABRIC_ARM_CONFIG):
  boundary.paths    a regular expression, matched CASE-INSENSITIVELY
                    against each changed file: the project's
                    security-boundary list in path form. Over-matching
                    costs a review; under-matching costs a boundary.
  boundary.exempt   a regular expression for the files dropped BEFORE
                    the pattern is applied (documentation, tooling — a
                    wording PR on a privacy ADR says "regime" in its
                    filename: a managed project's PR #886, re-review
                    finding 1).
  boundary.cases    paths that must stay boundary: a case the patterns
                    miss is exit 2, never a judgement (lint also refuses
                    one dropped without boundary.retired's why and word).
  classes           {"<class>": "<regex every changed file must match>"}:
                    the classes the project lets arm under the floor
                    without the owner's word, stated in the PR body as
                    "Class: <class>". None is a project that has none.
  waiver_role       the catalogue slug whose holder may waive the
                    boundary gate: [a-z0-9][a-z0-9-]*, and a role of
                    identities/roles/catalog.json. Optional; a waiver
                    asked of a project without one, or with one that is
                    not a catalogue role, is exit 2.
  direct            optional: {"roles": [...], "pr_paths": "<regex>",
                    "cases": [...]}. A holder of one of `roles` pushes
                    straight to the project's default branch, unless a
                    file the pushed commits change matches `pr_paths`
                    (case-insensitive) or has the executable mode (100755),
                    and unless the push rewrites the branch (it must
                    fast-forward): those still come by pull request.
                    `cases` are paths that must need a PR; lint refuses
                    one pr_paths misses. Optional `not_cases` are the
                    opposite floor, paths that must go direct (a design
                    token, a key visual, a decision record); lint refuses
                    one pr_paths matches. fabric-pr arm IGNORES this key
                    (a direct push has no PR to arm); policies/githooks/
                    pre-push enforces it (agent-fabric ADR-019 §5 rule 1).
A project with no arm.json is exit 2: a boundary the tool cannot read is
never judged absent.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import gh  # noqa: E402
import roots  # noqa: E402
from github import arm_policy, common, pr_gate, repo_policy  # noqa: E402
# The rules' names stay importable from here, where the oracle and callers
# reach them as arm.<name>.
from github.arm_rules import (  # noqa: E402, F401
    Refused, Unanswered, config_path, has_owner_word, head_lines, load_config, stated_class, unmet_supply)

FABRIC = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))

HELP = """Arm auto-merge on a PR — with the gates the project puts before the
arming applied by the tool, not by memory.

  fabric-pr arm <pr-number> --basis "<one line>" [options]

What it refuses, in order, and why:
  1. a PR that is not OPEN, or is a draft;
  2. another session's PR — the head branch's <host>/<login> prefix
     is not this session's (the lane rule: never arm, retarget or
     merge a PR you did not open; --any-owner overrides, for the
     owner's own hand);
  3. a body that names an AWAITING-SUPPLY with no range line for that
     login — supply asked for and not folded (fabric-pr owed-supply lists
     these; the caller arms never with its own REQUEST unanswered);
  4. a SECURITY-BOUNDARY change without the REVIEW CLASS'S review of
     the CURRENT head, or with an unresolved review thread, at any
     count (its owner's word is the count rule's, gate 5). Read from fabric-pr review-status --json: a
     `blind.rows` entry whose commit_sha8 is the head, and
     `unresolved_threads` 0 ("no open P1 or P2"); a missing field or a
     null count is exit 2, never a pass. Its exit status is NOT the
     gate: exit 0 means ANY counted review, an empty thread-reply review
     included. The boundary is read from the changed files against the
     project's patterns (projects/<id>/integration/gh/arm.json in
     agent-fabric). --boundary forces the gate on. --no-boundary
     <reason> --waiver <message-id|seq> waives it, on a message from the
     holder of the project's waiver role (arm.json "waiver_role") that
     the relay holds: a DECISION or REPLY sent TO this login (not a
     broadcast, not a role), from another login, carrying the line
         WAIVES: <owner>/<repo>#<n>@<head sha, 8+ hex>
     for this repository, this PR and its CURRENT head, from a sender
     fabric-ctl presence reports holding the role — never the message's
     ROLE line. Any of those not so is refused; a relay or fabric-ctl
     that cannot answer, or a message with no MESSAGE-ID, is exit 2.
     The relay does not authenticate senders: this stops mistakes, not
     a forger. The comment records who waived it, the message
     and the reason. A PR that matches no boundary ignores a waiver;
  5. the count rule (fabric-pr gate's classifier; the 8 and the 16 here are
     the default numbers of the repository's arming policy, tools/fabric/
     github/arm_policy.py: the fleet's, with the settings repository's file for
     the repository over it; one that cannot be read is exit 2): 8 or more arms at the
     review gate; over 16 is ADVICE for the next batch, never a refusal; under
     8 is armed on the owner's word — the --basis must carry the phrase
     "owner's word" — EXCEPT a class the project's arm.json lets arm at
     the gate (none, in a project that declares none; a class arms at its own
     minimum, one for the older form, and under it only on the owner's word), STATED in the PR body
     ("Class: <class>") and confirmed by the changed files; a stated
     class the files contradict is refused, not trusted. A
     security-boundary change under 8 needs the owner's word whatever
     class it states; at 8 or more it needs none, boundary or not. A waived boundary is judged as no boundary.
     (8 and 16 are the default numbers; the policy's, read as THE ARMING POLICY above, are the ones applied.)

Then: posts the arming basis as a comment ("Arming basis: <text> —
<W> work commits, head <sha>"; a security boundary armed at 8 or more
without the owner's word adds a sentence saying so), runs `gh pr merge <n> --merge --auto
--match-head-commit <head>` (--squash or --rebase where the policy's method is that) — pinned to the head the gates read —
and prints the watcher line to run — it is not started here, because
a watcher must be the SESSION's child for its exit to be the
session's callback.

Options:
  --basis "<text>"      required: the one-line arming basis
  --boundary            treat as a security-boundary change regardless of paths
  --no-boundary "<why>" waive the boundary gate, with --waiver; the reason goes in the comment
  --waiver <id|seq>     the waiver role holder's message (MESSAGE-ID or relay seq)
  --authorization <id|seq>  the boundary authority's message (see THE ARMING POLICY), for a boundary change under its minimum
  --any-owner           arm a PR whose branch is not this session's
  --dry-run             evaluate every gate, arm nothing, post nothing

Exit codes:
  0  armed (or, with --dry-run, would arm)
  1  refused — the reason is the last line
  2  gh / pr-gate / pr-review-status / arm.json / the relay / fabric-ctl
     could not answer, or usage

Environment: AGENT_FABRIC_PR_GATE, AGENT_FABRIC_PR_REVIEW_STATUS,
AGENT_FABRIC_PR_SESSION, AGENT_FABRIC_ARM_CONFIG,
AGENT_FABRIC_GZCOORD_INBOX, AGENT_FABRIC_CTL."""


def say(msg: str) -> None:
    print(f"arm: {msg}", flush=True)


ROLE_TRAILER = re.compile(r"^Fabric-Role:[ \t]*([a-z][a-z0-9-]*)[ \t]*$", re.M)
# The merge method as the flag gh takes: a fixed table, not the policy's text put into an argument.
MERGE_FLAGS = {"merge": "--merge", "squash": "--squash", "rebase": "--rebase"}
# GitHub lists at most this many commits of a pull request; a role is not read from a part of them.
PR_COMMITS_CAP = 250


def author_role(repo: str, num: str) -> str | None:
    """The role the pull request's own commits are stamped with (the Fabric-Role trailer the commit-msg hook adds
    to every commit an account makes): the one role of its non-merge commits, or None when there are none, none
    carries a trailer, or they name several. A role is a minimum the repository may lower for it, so the answer is
    None unless it is certain. Raises Unanswered when GitHub cannot list the commits."""
    try:
        listed = gh.api(f"repos/{repo}/pulls/{num}/commits?per_page=100", paginate=True)
        if len(listed) >= PR_COMMITS_CAP:
            return None
        roles = set()
        for c in listed:
            if len(c.get("parents") or []) > 1:
                continue
            # The trailer block: the message's last paragraph, where the commit-msg hook writes it.
            found = ROLE_TRAILER.findall(str((c.get("commit") or {}).get("message") or "").rstrip().split("\n\n")[-1])
            if not found:
                return None
            roles.update(found)
    except (gh.GhError, AttributeError, TypeError):
        raise Unanswered(f"cannot list #{num}'s commits to read the author's role") from None
    return roles.pop() if len(roles) == 1 else None


# ── the project's rules ──────────────────────────────────────────────


# ── readers run as programs: the seams the oracle mocks ──────────────

def program(env: str, default: str) -> list[str]:
    """A reader that is a program of its own: the env override, else the default path."""
    return [os.environ.get(env) or default]


def fabric_pr(env: str, verb: str) -> list[str]:
    """A reader that is a `fabric-pr` verb of this checkout (ADR-040 §5
    rule 7), or the env override, which stays one program."""
    return [os.environ[env]] if os.environ.get(env) else [os.path.join(FABRIC, "bin", "fabric-pr"), verb]


def run_reader(head: list[str], args: list[str], timeout: int = 600) -> tuple[int, str]:
    try:
        r = subprocess.run([*head, *args], capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=timeout)
    except OSError:
        return 127, ""
    except subprocess.TimeoutExpired:
        return 124, ""
    return r.returncode, r.stdout


# ── the gates ────────────────────────────────────────────────────────


ADDRESS = re.compile(r"[a-z0-9._-]+/[a-z0-9._-]+")
# The line an approver writes on purpose: a message that only mentions the
# PR — "I do NOT waive #7" included — waives nothing (review of 0c2498a,
# F1), and the head it names ties the approval to the code it was given
# for (F2).
WAIVES = re.compile(r"([\w.-]+/[\w.-]+)#(\d+)@([0-9a-fA-F]{8,40})")
SLUG = re.compile(r"[a-z0-9][a-z0-9-]*")


def catalogue_roles(what: str) -> set:
    """The role slugs of identities/roles/catalog.json; Unanswered when it cannot be read (`what` is what asked)."""
    try:
        with open(roots.role_catalog(), encoding="utf-8") as fh:
            return {r.get("id") for r in json.load(fh).get("roles", []) if isinstance(r, dict)}
    except (OSError, ValueError, AttributeError) as e:
        raise Unanswered(f"the role catalogue could not be read to check {what} ({type(e).__name__}: {e})") from None


def waiver_role_checked(role: str | None) -> str:
    """arm.json's waiver_role, a slug the catalogue holds; anything else is
    unanswerable — a misspelt role would refuse every waiver as the
    approver's fault (review of 0c2498a, F5)."""
    if not role:
        raise Unanswered("a boundary waiver was asked, and this project's arm.json names no waiver_role — nobody"
                         " can be checked as holding it")
    roles = catalogue_roles("waiver_role")
    if not SLUG.fullmatch(role) or role not in roles:
        raise Unanswered(f"arm.json's waiver_role {role!r} is not a role of identities/roles/catalog.json")
    return role


def authority_role_checked(role: str | None, repo: str) -> str:
    """The policy's commits.boundary_authority, a slug the catalogue holds. None is a refusal's business (the
    caller says the policy names none); one the catalogue lacks is unanswerable, as a misspelt waiver_role is."""
    if not role:
        raise Unanswered(f"{repo}'s arming policy names no boundary_authority")
    roles = catalogue_roles("boundary_authority")
    if not SLUG.fullmatch(role) or role not in roles:
        raise Unanswered(f"{repo}'s arming policy names the boundary_authority {role!r}, which is not a role of identities/roles/catalog.json")
    return role


def verify_grant(ref: str, num: str, repo: str, head: str, session: str, role: str, refuse, *, word: str, field: str) -> tuple[str, str]:
    """(login, message-id) of a message that grants what `word` is (a "waiver" carrying WAIVES, an "authorization"
    carrying AUTHORIZES) for this repository, PR and head, from another login whose presence reports `role`, or
    Refused / Unanswered. Every refusal is a fact of the message or of the fabric's record; a question neither
    could answer is never read as a refusal or a pass. The relay does not authenticate a sender
    (BRIDGE-RELAY-SETUP.md): this stops a mistake, not a forger (review of 0c2498a, F4)."""
    rc, out = run_reader(program("AGENT_FABRIC_GZCOORD_INBOX",
                                 os.path.join(FABRIC, "bin", "gzcoord-inbox")),
                         ["--replay", ref, "--json"], timeout=120)
    try:
        msg = json.loads(out)
    except ValueError:
        msg = None
    # The replay exits 0 with {"addressed": true, ...} for a message
    # addressed to this session and 2 with {"addressed": false} for one
    # that is not; any other failure (no such message, a relay that did
    # not answer, a refused token) prints no JSON object. A status and an
    # object that disagree are an answer of a shape it never gave.
    if not isinstance(msg, dict) or (rc, msg.get("addressed")) not in ((0, True), (2, False)):
        raise Unanswered(f"the {word} {ref} could not be read from the relay (gzcoord-inbox --replay exit {rc})")
    if not msg["addressed"]:
        raise refuse(f"the {word} {ref} is not addressed to this session")
    meta = msg.get("metadata") if isinstance(msg.get("metadata"), dict) else {}
    mid = meta.get("MESSAGE-ID")
    if not isinstance(mid, str) or not mid:
        # The comment names the message by its id; a seq is the relay's
        # position, not the message (review of 0c2498a, F6).
        raise Unanswered(f"the {word} {ref} carries no MESSAGE-ID — the arming comment could not name it")
    # A broadcast or a role address is "addressed" to every holder; the message
    # is given to the session that arms (review of 0c2498a, F3).
    if meta.get("TO") != session:
        raise refuse(f"the {word} {ref} is not sent TO {session} "
                     f"({'TO ' + meta['TO'] if meta.get('TO') else 'a broadcast or a role address'})")
    if msg.get("type") not in ("DECISION", "REPLY"):
        raise refuse(f"the {word} {ref} is a {msg.get('type')}, not a DECISION or REPLY")
    sender = str(msg.get("sender") or "")
    if not ADDRESS.fullmatch(sender) or meta.get("FROM") != sender:
        raise refuse(f"the {word} {ref} was relayed from {sender or 'nobody'} but says FROM {meta.get('FROM')}")
    # The login, not the address: the same login on another host is the
    # same agent, and the message is another agent's (re-review of b1a8e41).
    if sender.split("/", 1)[1] == session.split("/", 1)[-1]:
        raise refuse(f"the {word} {ref} is from {sender}, the login arming: a {word} is another login's")
    m = WAIVES.fullmatch(str(meta.get(field) or "").strip())
    if not m:
        raise refuse(f"the {word} {ref} has no {field}: {repo}#{num}@<head sha> line — a message that mentions"
                     f" the PR {'waives' if field == 'WAIVES' else 'authorizes'} nothing")
    if m.group(1).lower() != repo.lower() or m.group(2) != num:
        raise refuse(f"the {word} {ref} {field} {m.group(1)}#{m.group(2)}, not {repo}#{num}")
    if not head.lower().startswith(m.group(3).lower()):
        raise refuse(f"the {word} {ref} {field} head {m.group(3)}, and #{num}'s head is now {head[:12]}"
                     f" — an approval of one head arms no other")
    host, login = sender.split("/", 1)
    rc, out = run_reader(program("AGENT_FABRIC_CTL", os.path.join(FABRIC, "bin", "fabric-ctl")),
                         [login, "presence", "--json"], timeout=120)
    try:
        row = json.loads(out.strip().splitlines()[0]) if rc == 0 and out.strip() else None
    except ValueError:
        row = None
    p = row.get("presence") if isinstance(row, dict) else None
    if (not isinstance(p, dict) or row.get("status") != "ok" or p.get("status") != "ok"
            or row.get("account") != login or row.get("host") != host):
        raise Unanswered(f"fabric-ctl could not say which role {login} holds (presence, exit {rc}) — the {word}"
                         f" cannot be checked")
    if p.get("role") != role:
        raise refuse(f"the {word} {ref} is from {login}, who holds {p.get('role') or 'no role'}, not {role}")
    return login, mid


def verify_waiver(waiver: str, num: str, repo: str, head: str, session: str, role: str | None,
                  refuse) -> tuple[str, str]:
    """(login, message-id) of a waiver that holds, or Refused / Unanswered (verify_grant, for WAIVES)."""
    return verify_grant(waiver, num, repo, head, session, waiver_role_checked(role), refuse, word="waiver", field="WAIVES")


def arm(argv: list[str]) -> int:
    num = basis = no_boundary = waiver = authorization = ""
    boundary = any_owner = dry = False
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--basis":
            basis = argv[i + 1] if i + 1 < len(argv) else ""
            i += 2
            continue
        if a == "--boundary":
            boundary = True
        elif a == "--no-boundary":
            no_boundary = argv[i + 1] if i + 1 < len(argv) else ""
            if not no_boundary:
                raise Unanswered("--no-boundary needs the reason")
            i += 2
            continue
        elif a == "--waiver":
            waiver = argv[i + 1] if i + 1 < len(argv) else ""
            if not waiver or waiver.startswith("-"):
                raise Unanswered("--waiver needs the waiver's MESSAGE-ID or relay seq")
            i += 2
            continue
        elif a == "--authorization":
            authorization = argv[i + 1] if i + 1 < len(argv) else ""
            if not authorization or authorization.startswith("-"):
                raise Unanswered("--authorization needs the authorization's MESSAGE-ID or relay seq")
            i += 2
            continue
        elif a == "--any-owner":
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
    if not basis:
        raise Unanswered('--basis "<one line>" is required — the arming comment is the record')
    if boundary and no_boundary:
        raise Unanswered("--boundary and --no-boundary contradict")
    if bool(no_boundary) != bool(waiver):
        raise Unanswered('--no-boundary "<why>" and --waiver <message-id|seq> come together: a boundary is waived'
                         " only on the waiver role holder's message (try --help)")
    if not shutil.which("gh"):
        raise Unanswered("gh is required")

    def refuse(why: str) -> Refused:
        return Refused(f"REFUSED #{num} — {why}")

    try:
        pr = json.loads(gh.run(["pr", "view", num, "--json", "number,state,isDraft,headRefName,headRefOid,body,title"],
                               what=f"gh pr view {num}"))
    except (gh.GhError, ValueError):
        raise Unanswered(f"cannot read #{num} (gh pr view failed)") from None
    try:
        repo = gh.this_repo()
    except gh.GhError as e:
        raise Unanswered(f"cannot read the repository: {e.reason}") from None
    owner, name = repo.split("/", 1)
    state, branch = str(pr.get("state")), str(pr.get("headRefName") or "")
    head, title, body = str(pr.get("headRefOid") or ""), str(pr.get("title") or ""), str(pr.get("body") or "")

    # 1. open, not a draft
    if state != "OPEN":
        raise refuse(f"it is {state}, not open")
    if pr.get("isDraft") is True:
        raise refuse("it is a draft")

    # 2. this session's PR
    session = pr_gate.session_prefix()
    if not branch.startswith(f"{session}/"):
        if not any_owner:
            raise refuse(f"its branch {branch} is not this session's ({session}/…): never arm another session's PR"
                         " (--any-owner for the owner's own hand)")
        say(f"arming another session's PR on --any-owner ({branch})")

    # 3. AWAITING-SUPPLY with no range line
    unmet = unmet_supply(body)
    if unmet:
        raise refuse(f"the body names AWAITING-SUPPLY {', '.join(unmet)} with no range line for it — supply asked for"
                     " and not folded; fold, add the range line, then arm")

    # The project's rules are read only now: gates 1–3 hold for any
    # project, and refuse without them.
    boundary_re, exempt_re, classes, waiver_role = load_config(config_path())
    # The count rule's numbers are the repository's arming policy (arm_policy.py): the fleet's, with the settings
    # repository's file for this repo over it. One that cannot be read is exit 2, never the default: a default more
    # permissive than the repository's own would arm what it meant to hold.
    try:
        policy = arm_policy.with_classes(arm_policy.load(repo), {c: r.pattern for c, r in classes.items()})
    except (arm_policy.PolicyError, arm_policy.PolicyUnavailable) as e:
        raise Unanswered(f"the arming policy for {repo} cannot be read ({e}); the count rule is not applied to a guess") from None
    # The mode first: some repositories are not armed at all.
    if policy["mode"] == "owner-only":
        raise refuse(f"{repo}'s arming policy is owner-only: fabric-pr arm does not arm it, only the owner merges")
    if policy["mode"] == "direct":
        raise refuse(f"{repo}'s arming policy is direct: it has no server-side rule to arm under, work reaches it by push")
    # GitHub's side must be what the policy says it is: arming on a repository whose ruleset lost its required
    # check, or whose auto-merge is off, would rely on rules that are not there. A difference in which merge
    # methods are allowed (the repository's allow_*_merge fields, or a ruleset that allows the policy's method and more) is
    # said and does not stop the arming; a ruleset without the policy's method does. One that cannot be
    # read is exit 2, never "no difference".
    try:
        found = repo_policy.check(repo, policy)
    except repo_policy.Unreadable as e:
        raise Unanswered(f"{repo}'s GitHub settings cannot be compared with its arming policy ({e})") from None
    for line in found:
        if line.endswith("(advisory)"):
            say(f"arming policy, advisory: {line[:-len(' (advisory)')]}")
    hard = repo_policy.blocking(found)
    if hard:
        raise refuse(f"{repo}'s GitHub settings differ from its arming policy — {'; '.join(hard[:3])}"
                     f"{f' (and {len(hard) - 3} more)' if len(hard) > 3 else ''} — fabric-repo-policy plan shows all of it")
    min_work = policy["commits"]["min"]
    # A policy that raises the minimum above the default advice size does not make every PR "too big".
    advice_over = max(policy["commits"]["advice_over"], min_work)
    # The classes are the policy's, whole: its regex and its minimum go together (the project's arm.json classes
    # ride under it as {paths, min: 1}, and one the policy states wins).
    classes = {name: re.compile(spec["paths"]) for name, spec in policy["commits"]["classes"].items()}

    # 4. the security boundary. The changed files come from the paginated
    # REST list, not `gh pr view --json files`, which stops at 100 — a
    # boundary path past the 100th file would otherwise hide (a managed project's PR #886
    # review, pre-existing in gh).
    # A rename is judged by both of its names: a file moved OUT of a
    # boundary directory and edited on the way is a boundary change, and
    # GitHub names it by where it ended up (previous_filename is the
    # other; review of this port, pre-existing in the bash it was ported from).
    try:
        listed = gh.api(f"repos/{repo}/pulls/{num}/files?per_page=100", paginate=True)
        files = [f.get("filename", "") for f in listed]
        files += [f["previous_filename"] for f in listed if f.get("previous_filename")]
    except (gh.GhError, AttributeError, TypeError):
        raise Unanswered(f"cannot list #{num}'s files") from None
    boundary_files = [f for f in files if not (exempt_re and exempt_re.search(f)) and boundary_re.search(f)]
    is_boundary = False
    if boundary:
        is_boundary = True
        say("security boundary: forced by --boundary")
    elif boundary_files:
        is_boundary = True
        say(f"security boundary: {len(boundary_files)} changed file(s) match — {head_lines(boundary_files)}")
    else:
        say("not a security-boundary change by its paths")
        if waiver:
            say(f"no boundary matched: the waiver {waiver} is not needed, not read, and not recorded")
    waived_by = ""
    boundary_unwaived = False
    if is_boundary:
        if waiver:
            login, mid = verify_waiver(waiver, num, repo, head, session, waiver_role, refuse)
            waived_by = f"Boundary gate waived by {login} ({mid}): {no_boundary}."
            say(f"boundary gate WAIVED by {login}, {waiver_role} ({mid}): {no_boundary}")
        else:
            rc, out = run_reader(fabric_pr("AGENT_FABRIC_PR_REVIEW_STATUS", "review-status"),
                                 [num, "-q", "--json"])
            if rc == 2:
                raise Unanswered(f"pr-review-status could not answer for #{num} (exit 2)")
            # The --json object is the reader's documented contract; the
            # report's layout is not. A missing field fails closed: never
            # read as "no blind review" nor as zero threads.
            try:
                rs = json.loads(out)
            except ValueError:
                rs = None
            rows = rs.get("blind", {}).get("rows") if isinstance(rs, dict) and isinstance(rs.get("blind"), dict) else None
            if not isinstance(rows, list):
                raise Unanswered(f"pr-review-status --json carried no blind.rows for #{num} — cannot judge the review-class review")
            unresolved = rs.get("unresolved_threads")
            if not any(isinstance(r, dict) and r.get("commit_sha8") == head[:8] for r in rows):
                # An independent or automated review is not the boundary's
                # review: the reader counts any non-author review object
                # (a managed project's PR #930 blind review, F1).
                raise refuse(f"a security-boundary change with no review-class review of the current head: dispatch the"
                             f" review class on {head} and post with fabric-pr post-review, then arm (an independent"
                             f" or automated review does not count here)")
            if not isinstance(unresolved, int) or isinstance(unresolved, bool):
                raise Unanswered(f"pr-review-status reported no unresolved_threads count for #{num} (null: the lookup"
                                 f" failed) — cannot judge the open findings")
            if unresolved != 0:
                raise refuse(f"a security-boundary change with {unresolved} unresolved review thread(s): answer and"
                             f" resolve them first (no open P1 or P2)")
            say(f"the current head {head} has the review class's review, and no unresolved thread")
            # Its owner's word follows the count (gate 5): only under the repository's minimum (8
            # by default), and there no class stands in for it.
            boundary_unwaived = True

    # 5. the count rule, from pr-gate's classifier
    rc, out = run_reader(fabric_pr("AGENT_FABRIC_PR_GATE", "gate"), ["--json", num])
    try:
        row = json.loads(out)[0] if rc == 0 else None
    except (ValueError, IndexError, KeyError, TypeError):
        row = None
    if not isinstance(row, dict):
        raise Unanswered(f"pr-gate could not answer for #{num}")
    # A count that was never measured is not zero: commits_known=false
    # when the head or the base is not in the local clone (a managed project's PR #886
    # review F2 — 0 read as "under 8" and armed).
    if row.get("commits_known") is not True:
        raise Unanswered(f"pr-gate could not count #{num}'s commits (head or base not in the clone — git fetch origin,"
                         f" then retry); the count rule is not applied to a guess")
    work = row.get("work_commits")
    if not isinstance(work, int) or isinstance(work, bool) or work < 0:
        raise Unanswered(f"pr-gate reported no commit count for #{num}")
    # Over the policy's advice_over (16) is advice for the NEXT batch, never a gate at arming time
    # nor a reorganisation of the open PR.
    if work > advice_over:
        say(f"{work} work commits — over {advice_over}: smaller batches next time; arming on the basis given")
    cls = stated_class(body, classes)
    if cls:
        offlist = [f for f in files if not classes[cls].search(f)]
        if offlist:
            raise refuse(f"the body states Class: {cls} but the changed files are not that class — {head_lines(offlist)}")
        say(f"class stated and confirmed by the files: {cls}")
    # The author's role is the one the PR's own commits are stamped with (the Fabric-Role trailer the commit-msg
    # hook adds); several roles, or none, is no role: the repository's minimum, never a lower one.
    role = author_role(repo, num)
    floor = arm_policy.threshold(policy, role, cls, boundary_unwaived)
    # A class whose minimum is one has no lower bound than a stated, confirmed class always had (a pull request of
    # only review fixes counts zero work commits and still arms under it); above one, the class's own minimum is
    # the floor. A boundary change not waived has no such exemption: no class stands in for the owner's word there.
    under = work < floor and not (cls and not boundary_unwaived and floor <= 1)
    if under and policy["commits"]["below_min"] == "refuse":
        raise refuse(f"{work} work commits — under {floor}; this repository's arming policy refuses below the minimum"
                     f" (commits.below_min: refuse), the owner's word does not change that")
    authorized_by = ""
    if under and boundary_unwaived and not has_owner_word(basis):
        if not authorization:
            raise refuse(f"{work} work commits — a security-boundary change under {floor} arms only on the owner's word as well"
                         f" as the review, whatever class is stated; the basis does not carry the phrase \"owner's word\"")
        # The owner's word, in the owner's place: the holder of the policy's boundary_authority role says so, for this
        # PR and this head, to this session. The review gate above still stood; it is not this message's to lift.
        authority = policy["commits"].get("boundary_authority")
        if not authority:
            raise refuse(f"{repo}'s arming policy names no boundary_authority: only the owner's word arms a security-boundary"
                         f" change under {floor}, and the authorization {authorization} is nobody's to give")
        login, mid = verify_grant(authorization, num, repo, head, session, authority_role_checked(authority, repo), refuse,
                                  word="authorization", field="AUTHORIZES")
        authorized_by = f"Boundary count gate authorized by {login}, {authority} ({mid})."
        say(f"count gate AUTHORIZED by {login}, {authority} ({mid}), in the owner's place")
    elif authorization:
        say(f"no authorization is needed: the authorization {authorization} is not read, and not recorded")
    word = has_owner_word(basis) or bool(authorized_by)
    if under and cls and not word:
        raise refuse(f"{work} work commits — the class {cls} arms at {floor} or more; under that only on the owner's word,"
                     f" and the basis does not carry the phrase \"owner's word\"")
    if under and not cls and not word:
        gate_classes = " / ".join(f"Class: {c}" for c in classes) or "none in this project"
        raise refuse(f"{work} work commits — under {floor} arms only on the owner's word, unless the body states a class"
                     f" that arms at the gate ({gate_classes}) and the files agree; the basis does not carry the"
                     f" phrase \"owner's word\" and no class is stated")
    # The role's minimum decided it only where it is below the repository's and nothing more specific stands.
    by_role = (bool(role) and not cls and not boundary_unwaived and role in policy["commits"]["roles"] and floor < min_work
               and work < min_work)
    if under and authorized_by:
        say(f"count rule: {work} work commits — under {floor}, authorized in the owner's place")
    elif under:
        say(f"count rule: {work} work commits — under {floor}, on the owner's word")
    elif by_role:
        say(f"count rule: {work} work commits — the role {role}'s minimum is {floor}, arms at the review gate")
    elif work < min_work:
        say(f"count rule: {work} work commits — under {min_work}, arms at the gate as {cls}" if cls and not boundary_unwaived
            else f"count rule: {work} work commits — under {min_work}, on the owner's word")
    elif work <= advice_over:
        say(f"count rule: {work} work commits — {min_work} or more, arms at the review gate")

    # A repository with no required check has nothing server-side that makes the merge wait for green: arm waits
    # for it here, on the head the gates read.
    if not policy["required_checks"]:
        checks = str(row.get("checks"))
        if checks != "green":
            raise refuse(f"{repo} has no required check, so nothing but this gate keeps a red or unfinished head from"
                         f" merging: every check on the head must be green first (pr-gate reads {checks})")
        say("no required check on this repository: every check on the head is green")

    comment = f"Arming basis: {basis} — {work} work commits{f', class: {cls}' if cls else ''}{f', role: {role}' if by_role else ''}, head {head[:8]}."
    if waived_by:
        comment += f" {waived_by}"
    if authorized_by:
        comment += f" {authorized_by}"
    # A boundary armed at the repository's minimum or more needs no owner's word (gate 5), so the
    # record says that is what happened: a reader of the PR would
    # otherwise take an unmarked boundary arming for an oversight. Gate 5
    # already refused an unwaived boundary under the minimum without the word, so
    # `work >= floor` restates it here rather than deciding anything.
    if boundary_unwaived and work >= floor and not has_owner_word(basis):
        comment += f" Security boundary, armed on the count rule ({floor} or more work commits) without the owner's word."
    if dry:
        say(f"DRY RUN — would post: {comment}")
        say(f"DRY RUN — would run: gh pr merge {num} {MERGE_FLAGS[policy['method']]} --auto --match-head-commit {head}")
        return 0
    # The body on stdin: a body is data (gh.py's invariant).
    try:
        gh.run(["pr", "comment", num, "--body-file", "-"], input=comment, what=f"gh pr comment {num}")
    except gh.GhError:
        raise Unanswered(f"could not post the basis comment on #{num}") from None
    try:
        # Pinned to the head the gates read: a push between the checks and
        # this call would otherwise arm a head nobody reviewed or waived
        # (re-review of b1a8e41, pre-existing).
        gh.run(["pr", "merge", num, MERGE_FLAGS[policy["method"]], "--auto", "--match-head-commit", head], what=f"gh pr merge {num}")
    except gh.GhError:
        raise Unanswered(f"gh pr merge --auto failed on #{num}") from None
    # A green PR goes STRAIGHT INTO THE QUEUE on arming, and a queued PR
    # reads autoMergeRequest null — exactly like an unarmed one (a managed project's PR
    # #881). So the read-back is the queue entry OR the arming. On a
    # repository with no queue, gh merges a PR whose checks are already
    # green at once, and a merged PR reads both null too (agent-fabric
    # #118 read 'idle', exit 2, already merged): MERGED on the head the
    # gates read is the arming done, not a question. Every exit 0 is on
    # that head: an armed or queued PR read on another one is not.
    # `merged` is its own flag, never a value of `armed`: a state read
    # back lowercased would otherwise stand for the merge it is not.
    merged, armed = False, "unknown"
    try:
        d = gh.graphql("query($o:String!,$n:String!,$num:Int!){repository(owner:$o,name:$n){pullRequest(number:$num)"
                       "{state headRefOid autoMergeRequest{enabledAt} mergeQueueEntry{position}}}}",
                       o=owner, n=name, num=int(num))
        p = d["repository"]["pullRequest"]
        state, read_head = p["state"], str(p["headRefOid"])
        if state == "MERGED" and read_head == head:
            merged = True
        elif state == "MERGED":
            armed = f"merged at {read_head[:8]}, not {head[:8]}"
        elif state != "OPEN":
            armed = f"state {state}"
        elif read_head != head:
            armed = f"open at {read_head[:8]}, not {head[:8]}"
        else:
            armed = (f"queued at {p['mergeQueueEntry']['position']}" if p.get("mergeQueueEntry")
                     else "armed" if p.get("autoMergeRequest") else "idle")
    except (gh.GhError, KeyError, TypeError):
        armed = "unknown"
    # The read-back follows the policy's mode: a queue repository queues a green PR, an auto-merge one arms it. A
    # queue where the policy says auto is said, not refused: the PR is in and the repository is what drifted.
    if policy["mode"] == "auto" and armed.startswith("queued"):
        say(f"note: the policy's mode is auto and GitHub put #{num} in a merge queue — fabric-repo-policy plan will show the drift")
    if merged:
        say(f"MERGED #{num} ({title}) — read back merged on head {head[:8]} after the arming; basis posted.")
        return 0
    if armed not in ("armed",) and not armed.startswith("queued"):
        raise Unanswered(f"#{num} reads '{armed}' after gh pr merge --auto — check gh pr view {num}")
    say(f"ARMED #{num} ({title}) — {armed}; basis posted.")
    say(f"now, in the session: fabric-pr wait-merged {num} &")
    return 0


def main(argv: list[str]) -> int:
    common.apply_project_env("arm")
    try:
        return arm(argv)
    except Refused as e:
        print(f"arm: {e}", file=sys.stderr)
        return 1
    except Unanswered as e:
        print(f"arm: {e}", file=sys.stderr)
        return 2
    except Exception as e:  # noqa: BLE001 — an answer of a shape gh never gave: unanswered, never "refused"
        print(f"arm: an unexpected answer stopped the gates ({type(e).__name__}: {e}); read gh pr view before retrying", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
