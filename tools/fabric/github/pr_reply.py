#!/usr/bin/env python3
"""tools/fabric/github/pr_reply.py — reply to ONE review thread and resolve
it, in a single call (ADR-040 Wave 1; `fabric-pr reply` runs it; the runtime/github
shim is deprecated, and the managed projects' tools/gh/pr-reply.sh forward to that path).

CONTRACT, frozen from the bash (ADR-040 §5 rule 3):
  argv      <thread-id> [--no-resolve | --resolve] [--dry-run] [-h|--help]
  stdin     the reply body, byte for byte (a heredoc's trailing blank
            line included); never an argument
  env       AGENT_FABRIC_ROOT, AGENT_FABRIC_LAUNCH_ROLE (the role the
            session was launched with)
  stdout    `replied: <url>`, then `resolved: #N path:line` or `left open:
            #N path:line`; with --dry-run the would-be reply and body
  stderr    every refusal and warning, prefixed `pr-reply: `
  exit      0 replied (and resolved unless --no-resolve); 2 any refusal —
            bad id, empty body, not your PR, gh failure

HELP is the bash's byte for byte but for the one sentence that named
the bash's own mechanism (`gh -f`), which now names gh.py's.

WHY (carried from the bash): replies quote code, and a body pasted into a
double-quoted `gh api -f body="..."` gets backticks command-substituted
and $vars expanded by the shell before gh sees it — a reply once posted
with the guard's name it described silently removed. Here the body goes
to GitHub as JSON on stdin (gh.py), never through a shell or argv.

ANOTHER SESSION'S PR IS REFUSED. Ownership is the branch prefix, not the
PR author (every session pushes as the same GitHub user). A reply cannot
be unsent, and that session is mid-flight on a fix you cannot see. A
BRANCH THAT NAMES NO SESSION is not "another session's": dependabot/…,
a pre-convention feat/x, add-claude-github-actions-178… each read as a
rival session under the old guard, and four such PRs held seven
unresolved P1/P2 findings for a month. An unowned PR is answered with a
warning, and its resolve is opt-in (--resolve): resolving is a claim, and
nothing downstream catches a false one since resolution stopped gating
merges on 2026-08-06.
"""
from __future__ import annotations

import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import gh  # noqa: E402
from github import local  # noqa: E402

HELP = """Reply to ONE review thread and resolve it, in a single call.

The body arrives on STDIN and is never interpolated into a command
line. That is the point of this script, not a detail: replies quote
code, and a body pasted into a double-quoted `gh api -f body="..."`
gets `backticks` command-substituted and `$vars` expanded by the shell
before gh ever sees it. That has already happened here — a reply
posted with the name of the guard it was describing silently removed,
because the shell ran it. Reading stdin and sending it to GitHub as
JSON on gh's own stdin closes the whole class.

It also enforces the two rules that are easy to break by hand:

  * ANOTHER SESSION'S PR IS REFUSED. Ownership is the branch prefix,
    not the PR author (every session pushes as the same GitHub user).
    The repo-root CLAUDE.md is explicit: never answer reviews on
    another session's branch. A wrong reply cannot be unsent, and that
    session is mid-flight on a fix you cannot see.

    A BRANCH THAT NAMES NO SESSION IS NOT "ANOTHER SESSION'S". The
    guard used to take the first two segments of anything and compare
    — so dependabot's `dependabot/pub`, a pre-convention `feat/x`, and
    `add-claude-github-actions-178…` each read as a rival session, and
    the refusal told you it was "mid-flight on a fix you cannot see"
    about a session that does not exist. Nobody could answer those
    threads through this script, and nobody owned them either: four
    such PRs held seven unresolved P1/P2 findings for a month. The
    shape is checked now, and an unowned PR is allowed with a warning
    — the reply still needs the owning SURFACE's role to have verified
    the claim, which is what the warning says.
  * RESOLVING IS A CLAIM. --no-resolve exists for the case where the
    reply is a question, or the finding is real and not yet fixed.
    Resolution stopped gating merges on 2026-08-06, so a resolve now
    signals only "handled" and nothing downstream catches a false one.

Usage:
  fabric-pr reply <thread-id> [options]   # body on stdin

  fabric-pr reply PRRT_xxx <<'EOF'
  Fixed in #123 — the guard now anchors the filter.
  EOF

  fabric-pr reply PRRT_xxx --no-resolve <<'EOF'
  Real, but the fix needs the contract change first — leaving open.
  EOF

Options:
  --no-resolve   post the reply, leave the thread open
  --resolve      resolve even on a branch that names no session, where
                 the default is to leave it open (see below)
  --dry-run      show what would be posted, touch nothing
  -h, --help     this text

Thread ids come from the queue: `/comments`, or the GraphQL in the
pr-review-backlog skill. They look like PRRT_kwDOS6OPLs6XAV3d.

A quoted heredoc (<<'EOF') is the recommended way to pass the body:
unquoted, the SHELL expands it before this script is reached, and no
amount of care in here can undo that.

Exit codes:
  0  replied (and resolved, unless --no-resolve)
  2  invocation problem — bad id, empty body, not your PR, gh failure"""

READ = """query($id: ID!) {
  node(id: $id) {
    ... on PullRequestReviewThread {
      isResolved path line
      pullRequest { number state headRefName repository { nameWithOwner } }
      comments(last: 1) { nodes { author { login } } }
    }
  }
}"""
REPLY = """mutation($id: ID!, $body: String!) {
  addPullRequestReviewThreadReply(input: {pullRequestReviewThreadId: $id, body: $body}) { comment { url } }
}"""
RESOLVE = """mutation($id: ID!) {
  resolveReviewThread(input: {threadId: $id}) { thread { isResolved } }
}"""
AUTOMATION = {"dependabot", "renovate", "github-actions", "weblate", "imgbot", "allcontributors", "pre-commit-ci",
              "snyk-bot"}
# BOT BRANCHES HAVE AN OWNER TOO — a ROLE (a Dependabot pull request is
# devex-tooling's: architect-cto decision, 2026-09-14). Same map as
# pr-sessions.
BOT_OWNER_ROLE = {"dependabot": "devex-tooling"}


class Refused(Exception):
    pass


def die(msg: str):
    raise Refused(msg)


def say(msg: str) -> None:
    print(msg, file=sys.stderr)


def branch_names_a_session(branch: str) -> bool:
    """<host>/<clone>/<type>/<desc>, and not an automation vendor's. NO TEST
    ON <type>: a wrong "not a session" here means POST AND RESOLVE on
    somebody else's PR, and `Fix/`, `chore(gh)/`, `WIP/` are all real
    session branches a shape test would call unowned. pr-sessions applies
    the same predicate; the two must agree about who owns what."""
    p = branch.split("/")
    return len(p) >= 4 and bool(p[0]) and bool(p[1]) and p[0] not in AUTOMATION


def run(argv: list[str], stdin) -> int:
    thread, resolve, resolve_explicit, dry = "", True, False, False
    for a in argv:
        if a == "--no-resolve":
            resolve, resolve_explicit = False, True
        elif a == "--resolve":
            resolve, resolve_explicit = True, True
        elif a == "--dry-run":
            dry = True
        elif a in ("-h", "--help"):
            print(HELP)
            return 0
        elif a.startswith("-"):
            die(f"unknown option '{a}' (try --help)")
        else:
            if thread:
                die(f"one thread id at a time (got '{thread}' and '{a}')")
            thread = a
    if not thread:
        die("a review-thread id is required (try --help)")
    # A review THREAD id starts PRRT_; a review COMMENT id (PRRC_) is the
    # other thing in the same output and cannot be replied to this way.
    if not re.fullmatch(r"PRRT_[A-Za-z0-9_-]+", thread):
        die(f"'{thread}' is not a review-thread id (expected PRRT_…; PRRC_ is a comment, not a thread)")
    # git and hostname are as required as gh: the ownership guard derives
    # this clone's identity from both, and a missing git would surface as
    # "not inside a git worktree" — sending the operator to look for a
    # clone they are already standing in.
    for binary in ("gh", "git", "hostname"):
        if not shutil.which(binary):
            die(f"{binary} is required but not installed.")
    if callable(stdin):
        stdin = stdin()
    if stdin is None:
        die("the reply body is read from stdin — pipe it, or use <<'EOF' … EOF")
    body = stdin
    if not body.strip(" \t\n"):
        die("the reply body is empty.")

    # ── who owns this thread's PR ────────────────────────────────────
    try:
        node = gh.graphql(READ, id=thread).get("node")
    except gh.GhError:
        die(f"could not read thread {thread} (gh not authenticated, or no access).")
    if not node:
        die(f"thread {thread} does not exist, or this token cannot see it.")
    # SCOPE THE THREAD TO THIS REPOSITORY, EXPLICITLY: node(id:) is a
    # GLOBAL lookup, and a thread in another repository resolved fine; the
    # branch-prefix check alone passes for any <host>/<clone>/… anywhere.
    pr = node.get("pullRequest") or {}
    thread_repo = (pr.get("repository") or {}).get("nameWithOwner") or ""
    try:
        here_repo = gh.this_repo()
    except gh.GhError as e:
        die(f"cannot determine the current repository: {e.reason}.")
    if thread_repo != here_repo:
        die(f"thread {thread} belongs to {thread_repo}, not {here_repo}.")
    number, branch, state = pr.get("number"), pr.get("headRefName") or "", pr.get("state")
    location = f"{node.get('path')}:{node.get('line') if node.get('line') is not None else '?'}"

    # FAILS CLOSED: not knowing whose PR this is has to mean stop.
    root = local.toplevel()
    if not root:
        die("not inside a git worktree, so the session's working-copy identity is unknown — refusing to reply "
            "(run it from the working copy that owns the PR).")
    fabric = os.environ.get("AGENT_FABRIC_ROOT") or os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
    ident = os.path.join(fabric, "runtime", "identity.py")
    host = local.probe(["hostname", "-s"])[1].strip()
    agent = local.probe([sys.executable, ident])[1].strip() if os.path.exists(ident) else ""
    agent = agent or local.probe(["id", "-un"])[1].strip()
    me = f"{host}/{agent}"
    # A working copy named after its repository is every login's default
    # clone, so its name is no session's; only a clone with a name of its
    # own carries a legacy prefix.
    remote = local.remote_url(root)
    repo_name = re.sub(r"\.git$", "", remote).rsplit("/", 1)[-1].rsplit(":", 1)[-1]
    wc_name = os.path.basename(root)
    me_legacy = "" if repo_name and wc_name.lower() == repo_name.lower() else f"{host}/{wc_name}"
    role = local.probe([sys.executable, ident, "--role"])[1].strip() if os.path.exists(ident) else ""
    # The role this session was LAUNCHED with is the one in its prompt; a
    # session the launcher did not start holds no role at all (reviews of
    # #68 and #70). No stamp, or one that disagrees, is no role.
    if os.environ.get("AGENT_FABRIC_LAUNCH_ROLE", "") != role:
        role = ""
    owner = "/".join(branch.split("/")[:2])

    bot_role = BOT_OWNER_ROLE.get(branch.split("/", 1)[0], "")
    if bot_role and role == bot_role:
        say(f"pr-reply: #{number} is on '{branch}' — a bot branch, owned by the {bot_role} role, which this session holds.")
    elif bot_role:
        say(f"pr-reply: #{number} is on '{branch}', which the {bot_role} role owns; this session holds '{role or 'no role'}'.")
        say("  Not replying. Hand the finding to that role (GZCoord), or raise it in the PR.")
        return 2
    elif not branch_names_a_session(branch):
        say(f"pr-reply: #{number} is on '{branch}', which names no session.")
        say("  No session owns it, so there is nobody to defer to — replying.")
        # THE ADVICE HAS TO BE ENFORCED, NOT PRINTED: the default inverts
        # here and --resolve is the opt-in.
        if resolve and not resolve_explicit:
            resolve = False
            say("  The finding may still be another SURFACE's (backend, flutter, web),")
            say("  so the thread is left OPEN. Pass --resolve once it is verified.")
    elif owner == me_legacy and owner != me:
        say(f"pr-reply: #{number} is on '{branch}', named for this working copy; this agent ({me}) owns it.")
    elif owner != me:
        say(f"pr-reply: #{number} belongs to '{owner}', and this session is '{me}'.")
        say("  Not replying. That session is mid-flight on a fix you cannot see,")
        say("  and a review reply cannot be unsent. Raise it in the PR instead.")
        return 2

    if node.get("isResolved"):
        say("pr-reply: thread is already resolved — replying anyway, leaving it resolved.")
        resolve = False
    if dry:
        print(f"would reply to #{number} ({state}) {location} — thread {thread}")
        print(f"would resolve: {'yes' if resolve else 'no'}")
        print("--- body ---")
        print(body)
        return 0

    # ── reply ────────────────────────────────────────────────────────
    try:
        url = (((gh.graphql(REPLY, id=thread, body=body).get("addPullRequestReviewThreadReply") or {})
                .get("comment") or {}).get("url") or "")
    except gh.GhError as e:
        # A reply cannot be unsent: a call that timed out or was throttled
        # may have landed, and a re-run then posts it twice. Only a refusal
        # GitHub gave is "rejected" (review of #71).
        if e.transient:
            die(f"no answer from GitHub for the reply (thread {thread} on #{number}: {e.reason}) — it may have "
                "posted. Look at the thread before re-running; a second run posts it twice.")
        die(f"the reply was rejected (thread {thread} on #{number}).")
    if not url:
        die("the reply returned no URL — assume it did not post.")
    print(f"replied: {url}")

    # ── resolve — only after the reply landed: a resolved thread with no
    # reply reads as answered and shows nothing ──────────────────────
    if resolve:
        try:
            done = ((gh.graphql(RESOLVE, id=thread).get("resolveReviewThread") or {}).get("thread") or {}).get("isResolved")
        except gh.GhError:
            die(f"replied, but the resolve failed — thread {thread} is still open.")
        if done is not True:
            die(f"replied, but the thread did not resolve (got '{str(done).lower() if isinstance(done, bool) else done}').")
        print(f"resolved: #{number} {location}")
    else:
        print(f"left open: #{number} {location}")
    return 0


def read_body() -> str | None:
    """The body, read only once the arguments are known to need it: read
    first, `--help` or a usage error with an open stdin waited on it (the
    bash read it after parsing). Bytes, decoded here: invalid UTF-8 becomes
    U+FFFD, never a lone surrogate that JSON cannot carry to GitHub."""
    return None if sys.stdin.isatty() else sys.stdin.buffer.read().decode("utf-8", "replace")


def main() -> int:
    try:
        return run(sys.argv[1:], read_body)
    except Refused as e:
        say(f"pr-reply: {e}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
