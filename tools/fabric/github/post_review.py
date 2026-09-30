#!/usr/bin/env python3
"""tools/fabric/github/post_review.py — post THE review of a PR, the review
class's blind review, as a marked review object (ADR-040 Wave 1;
runtime/github/post-review.sh is its shim, and the managed projects'
tools/gh/post-review.sh forward to that path).

CONTRACT, frozen from the bash (ADR-040 §5 rule 3):
  argv      <pr> [--model <name>] [--dry-run] [-h|--help]
  stdin     the review body, byte for byte; never an argument
  env       AGENT_FABRIC_ROOT, AGENT_FABRIC_LAUNCH_ROLE (the role the
            session was launched with)
  stdout    `posted review: <url>` and the line after it; with --dry-run
            the would-be review and its body
  stderr    every refusal and warning, prefixed `post-review: `
  exit      0 posted; 2 an invocation problem, a refusal, or a post
            GitHub rejected or did not confirm

REVIEW_MARKER is the contract with every reader (pr-review-status, the
gate, results.py): the first line of the body, versioned because a later
field must not silently reclassify older reviews. The shim repeats it on
a line of its own, which the bash oracle compares with the reader's;
tests/test_post_review.py holds the shim and this constant together.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import gh  # noqa: E402

REVIEW_MARKER = "<!-- agent-fabric-review v1 -->"

HELP = """Post THE review of a PR — the review class's blind review — as a
review object, marked so the tooling counts it as coverage of the head.

WHY THIS EXISTS. Every session pushes as the SAME GitHub account, so a
review the review class wrote is indistinguishable from the author's
own thread reply by account alone, and pr-review-status.sh used to
bucket both as "self reviews … not coverage". Prose attribution drifts
— three sessions wrote three different sentences — and a coverage
claim guessed from prose is worse than none. So every review this
script posts is a REVIEW OBJECT (never an issue comment, which is not
a review) and carries REVIEW_MARKER (below) as its first line, the
exact string pr-review-status.sh tests for.

The review class is the review. There is no automated reviewer it
stands in for: the fabric dispatches a blind reviewer for every PR
(runtime/claude-code/agents/code-review.md, briefed by bin/fabric-review),
and this is how that review reaches the PR and the gate.

Usage:
  post-review.sh <pr> [options]   # body on stdin

  post-review.sh 552 <<'EOF'
  Found a P1 in the ownership guard: a four-segment branch typed
  `Fix/` was classified unowned, so pr-reply.sh would post to it.
  EOF

Options:
  --model <name>   record which model produced the review (default: unset)
  --dry-run        show what would be posted, send nothing
  -h, --help

The body arrives on STDIN and is never interpolated into a command
line — the same rule, and the same reason, as pr-reply.sh: a body
quoting `backticks` or $vars passed through `-f body="…"` is expanded
by the shell before gh sees it, and that has already posted a mangled
comment in this repo.

Exit codes:
  0  posted
  2  invocation problem, or the PR belongs to another session"""

# Kept identical to pr_reply's: a wrong "names no session" means writing
# to somebody else's PR.
AUTOMATION = {"dependabot", "renovate", "github-actions", "weblate", "imgbot", "allcontributors", "pre-commit-ci",
              "snyk-bot"}
LOCALE_FILE = re.compile(r"identities/roles/[^/\n]+/locale/[^/\n]+/[^/\n]+")
# GitHub lists at most 3000 files of a pull request and stops there
# without an error: a list that long may be cut, so it is not read as
# whole (re-review of #70).
FILE_LIST_CAP = 3000


class Refused(Exception):
    pass


def die(msg: str):
    raise Refused(msg)


def say(msg: str) -> None:
    print(msg, file=sys.stderr)


def branch_names_a_session(branch: str) -> bool:
    """<host>/<agent>/<type>/<desc>, and not an automation vendor's. No
    test on <type>: a shape test there is a permission decision resting
    on an open-ended set (`Fix/`, `chore(gh)/`, `WIP/` are real session
    branches)."""
    p = branch.split("/")
    return len(p) >= 4 and bool(p[0]) and bool(p[1]) and p[0] not in AUTOMATION


def locale_only(repo: str, pr: str) -> bool:
    """Whether every path the PR touches, a rename's old path included, is
    a locale translation. FAILS CLOSED: anything unread is False.

    From REST, which gives a renamed file's old path too: gh's `files`
    lists only the new one, so a code file moved INTO locale/ read as a
    translation (review of #68). On an HTTP error gh prints the error body
    on STDOUT, and --slurp wraps it as [{"message": …}]: read without its
    exit status, that counted the error's keys as files and posted without
    having read the list (review of #70). The status decides first; then
    only an array of pages of file objects is a list."""
    try:
        out = gh.run(["api", "--paginate", "--slurp", f"repos/{repo}/pulls/{pr}/files?per_page=100"],
                     what=f"gh api GET repos/{repo}/pulls/{pr}/files")
        pages = json.loads(out)
    except (gh.GhError, ValueError):
        return False
    if not isinstance(pages, list) or not all(isinstance(p, list) for p in pages):
        return False
    files = [f for page in pages for f in page]
    if not 1 <= len(files) < FILE_LIST_CAP or not all(isinstance(f, dict) for f in files):
        return False
    paths = [f.get("filename") for f in files] + [f["previous_filename"] for f in files if f.get("previous_filename")]
    return all(isinstance(p, str) and LOCALE_FILE.fullmatch(p) for p in paths)


def identity(fabric: str, *args: str) -> str:
    ident = os.path.join(fabric, "runtime", "identity.py")
    if not os.path.exists(ident):
        return ""
    r = subprocess.run([sys.executable, ident, *args], capture_output=True, text=True, stdin=subprocess.DEVNULL)
    return r.stdout.strip() if r.returncode == 0 else ""


def run(argv: list[str], stdin: str | None) -> int:
    pr, model, dry = "", "", False
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--model":
            if i + 1 >= len(argv):
                die("--model needs a value")
            model = argv[i + 1]
            i += 2
            continue
        if a == "--dry-run":
            dry = True
        elif a in ("-h", "--help"):
            print(HELP)
            return 0
        elif a.startswith("-"):
            die(f"unknown option '{a}' (try --help)")
        else:
            if pr:
                die(f"only one PR number, got '{pr}' and '{a}'")
            pr = a
        i += 1
    if not pr:
        die("a PR number is required (try --help)")
    if not re.fullmatch(r"[1-9][0-9]*", pr):
        die(f"'{pr}' is not a PR number")
    for binary in ("gh", "git", "hostname"):
        if not shutil.which(binary):
            die(f"{binary} is required but not installed.")

    # STDIN, never an argument. See the help.
    if stdin is None:
        die("the review body is read from stdin — pipe it, or use <<'EOF' … EOF")
    body = stdin
    if not body.strip(" \t\n"):
        die("the review body is empty.")

    try:
        repo = gh.run(["repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"]).strip()
    except gh.GhError:
        repo = ""
    if not repo:
        die("could not resolve the repository (gh not authenticated?).")
    try:
        meta = gh.pr_view(int(pr), ["number", "state", "headRefName", "headRefOid"])
    except (gh.GhError, ValueError):
        die(f"could not read PR #{pr}.")
    # FAILS CLOSED, and this is what makes the lane guard true: a payload
    # missing the branch read as "names no session" in the bash, and the
    # guard took the POSTING path.
    meta = meta if isinstance(meta, dict) else {}
    branch, head, state = meta.get("headRefName"), meta.get("headRefOid"), meta.get("state")
    if not isinstance(branch, str) or not branch:
        die(f"could not read the head branch of PR #{pr} — refusing, because ownership is unknown.")
    if not isinstance(head, str) or not head:
        die(f"could not read the head commit of PR #{pr} — refusing.")

    # ── lane guard ──────────────────────────────────────────────────
    # Same rule as pr-reply, and the same reason: a review cannot be
    # unsent, and another session is mid-flight on work you cannot see.
    r = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True,
                       stdin=subprocess.DEVNULL)
    if r.returncode != 0:
        die("not inside a git worktree, so the session's working-copy identity is unknown — refusing.")
    root = r.stdout.strip()
    # The session is the AGENT — the Linux login — on this host. Older
    # branches carry the working-copy name in the second segment, so that
    # is accepted as this session too while they last.
    fabric = os.environ.get("AGENT_FABRIC_ROOT") or os.path.join(root, "..", "agent-fabric")
    host = subprocess.run(["hostname", "-s"], capture_output=True, text=True).stdout.strip()
    agent = identity(fabric) or subprocess.run(["id", "-un"], capture_output=True, text=True).stdout.strip()
    me, me_legacy = f"{host}/{agent}", f"{host}/{os.path.basename(root)}"
    owner = "/".join(branch.split("/")[:2])
    carve_out = False
    if not branch_names_a_session(branch):
        say(f"post-review: #{pr} is on '{branch}', which names no session.")
        say("  No session owns it, so there is nobody to defer to — posting.")
    elif owner not in (me, me_legacy):
        # The one exception: a locale's translations are committed by that
        # locale's holder and merged by fabric-coordinator (agent-fabric's
        # CLAUDE.md, the locale carve-out), so the merger must post the
        # review its gate counts. The role this session was LAUNCHED with
        # is the one in its prompt; a binding changed under it since does
        # not count (review of #68), and a session the launcher did not
        # start holds no role at all (review of #70).
        role = identity(fabric, "--role")
        if os.environ.get("AGENT_FABRIC_LAUNCH_ROLE", "") != role:
            role = ""
        if role == "fabric-coordinator" and locale_only(repo, pr):
            say(f"post-review: #{pr} belongs to '{owner}' and touches only locale translations;")
            say("  posting as the locale carve-out's merger (fabric-coordinator).")
            carve_out = True
        else:
            say(f"post-review: #{pr} belongs to '{owner}', and this session is '{me}'.")
            say("  Not posting. That session is mid-flight on work you cannot see,")
            say("  and a review cannot be unsent. Raise it in the PR instead.")
            return 2

    # ── assemble ────────────────────────────────────────────────────
    # The marker goes FIRST so it survives any truncation a reader
    # applies, and so the first line identifies the review.
    header = REVIEW_MARKER
    if model:
        header += f"\n<!-- model: {model} -->"
    if carve_out:
        header += "\n<!-- posted by the locale carve-out's merger -->"
    full_body = f"""{header}
**Blind review** — the review class, dispatched against this head with a
brief of facts and none of the author's session context. Its findings
are judged before they are answered; the judgement follows in the PR.

{body}"""

    if dry:
        print(f"would post a review to #{pr} ({state}) at {head}")
        print("--- body ---")
        print(full_body)
        return 0

    # The payload in a file, never -f body="…": a review body quotes code
    # by definition. gh's own --jq picks the URL out; the jq binary is not
    # involved.
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as f:
        json.dump({"body": full_body, "event": "COMMENT", "commit_id": head}, f, ensure_ascii=False)
        payload = f.name
    try:
        # GitHub's own reason, not a bare "rejected": the first transient
        # failure on #69 said nothing, and a hand-made retry to learn why
        # posted an unmarked review. No automatic retry: a timeout may have
        # posted it, and a second post is a duplicate review on the PR.
        url = gh.run(["api", f"repos/{repo}/pulls/{pr}/reviews", "--input", payload, "--jq", ".html_url"],
                     what=f"gh api POST repos/{repo}/pulls/{pr}/reviews").strip()
    except gh.GhError as e:
        die(f"the review was rejected by GitHub (PR #{pr}): {e.reason}. Look at the PR before re-running — "
            "a timeout may have posted it; never post it by hand, unmarked.")
    finally:
        os.unlink(payload)
    if not url:
        die("GitHub accepted the request but returned no review URL — treat as NOT posted.")
    print(f"posted review: {url}")
    print("  marked so pr-review-status.sh counts it as the review of this head.")
    return 0


def main() -> int:
    # Bytes, decoded here: text mode would turn a body's \r\n into \n.
    stdin = None if sys.stdin.isatty() else sys.stdin.buffer.read().decode("utf-8", "replace")
    try:
        return run(sys.argv[1:], stdin)
    except Refused as e:
        say(f"post-review: {e}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
