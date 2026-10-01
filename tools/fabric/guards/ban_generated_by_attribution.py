#!/usr/bin/env python3
r"""tools/fabric/guards/ban_generated_by_attribution.py (ADR-040 Wave 2;
policies/ban_generated_by_attribution.sh is its shim. The bash was imported
from the legacy repository's tools/checks/, 2026-09-13.)

CONTRACT, frozen from the bash (ADR-040 §5 rule 3):
  argv      none; arguments are ignored
  cwd       the repository inspected (git runs there)
  env       AGENT_FABRIC_ATTRIBUTION_BASE  a ref to use as the range base,
                                           tried first by the ref fallback
            GITHUB_EVENT_PATH              the event payload (JSON); names
                                           the range (pull_request base.sha
                                           and head.sha, merge_group base_sha
                                           and head_sha) and carries the
                                           pull-request description
            GITHUB_BASE_REF                the PR's base branch name, tried
                                           as origin/<name> then <name>
  stdin     not read
  stdout    the verdict line, and every "NOT ENFORCED" note; nothing else
  stderr    the FAIL report and its explanation, only on exit 1
  exit      0  every half that could run found nothing
            1  a commit message or PR description carries banned attribution
            0  also when a half could not run -- an environment that cannot
               show a range is not a violation -- but it says NOT ENFORCED
               and never OK

Ban machine-attribution boilerplate from the artifacts this repo authors:
a `Co-authored-by:` or `Claude-Session:` trailer in a commit message, and
a "Generated with Claude Code" footer or a session URL in a commit message
or a pull-request description.

WHY THIS EXISTS. The root CLAUDE.md has forbidden the trailer for as long
as it has existed, and commits carry it anyway. The cause is not
carelessness: the harness injects an attribution instruction into a
session's context telling it to add exactly these lines, it re-arrives
whenever the model or the session changes, and it reads with the same
authority as everything else in the prompt. A rule that must be re-won
against a reminder on every commit is a rule that will be lost sometimes.
Two separate sessions have lost it, days apart, in two different shapes --
one adding both a trailer and a session URL, the other only the trailer.

WHAT IT INSPECTS. Commit messages that a branch ADDS over its base --
never the whole history, because the existing ones are already on `main`
and a guard that fails forever is a guard that gets disabled. It also
reads the pull-request description out of the event payload, which needs
no token and no API call.

THE RANGE IS THE HARD PART, and the first version of this guard got it
wrong in a way that made it a NO-OP on every CI event while printing OK.
`actions/checkout` defaults to depth 1 and, on a pull_request, checks out
the MERGE ref: there are no parents in the object store, so `BASE..HEAD`
yields exactly one commit -- GitHub's synthetic merge -- and the branch's
own commits are never enumerated. On merge_group and push, GITHUB_BASE_REF
is unset, no candidate resolves, and the old code exited 0 as "not
enforced". Green, and enforcing nothing, anywhere.

So: the workflow now checks out full history (`fetch-depth: 0`), and the
range comes from the EVENT PAYLOAD rather than from guessing ref names --
`pull_request` carries base.sha/head.sha, `merge_group` carries
base_sha/head_sha. Using head.sha on a pull_request also steps around the
synthetic merge commit entirely. Ref-name resolution remains only as the
fallback for a hand-run in a full clone.

THE DESCRIPTION IS READ AS IT STOOD WHEN THE RUN WAS CREATED. The event
payload is a snapshot, so editing a pull-request description AFTER a run
has started does not retroactively pass it -- the fix has to land before
or with the push that triggers CI, or the run has to be repeated. Reported
by db-admin, from getting it wrong and paying for the rerun.

NEVER PRINT OK FOR A CHECK THAT DID NOT RUN. Each half reports its own
state, and a half that could not run says so. The previous version printed
an affirmative OK when jq was missing, when the payload was malformed, and
when no base resolved -- which is how a no-op reads as coverage.

WHAT IT MATCHES. A trailer KEY at the start of a line, indentation
allowed, followed by a colon. So an indented PASTE of a trailer in a
commit body IS flagged, and only a key appearing mid-sentence is not:
"do not add a Co-authored-by: trailer" passes, the line on its own does
not. That is the right way round for a guard whose whole subject is that
line appearing where it should not, and it is tested both ways -- the
earlier fixture had no colon at all, so an unanchored pattern survived
the suite that was supposed to pin the anchor.

guards: policies/**

What differs from the bash, on purpose (each was a silent pass or a crash
there): jq is not needed, so the "jq is not installed" note is gone; a
`git rev-list` that fails is "no usable range" (the bash's `mapfile <(...)`
took the substitution's failure for success and printed OK over an empty
range); a commit whose message cannot be read makes the commit half NOT
ENFORCED and names it (the bash `|| continue` skipped it and printed OK); a
git that is missing or does not answer says so after the note. Everything
else is replicated but two things. With no GITHUB_EVENT_PATH (every
local run) the OK line said "nor in the pull-request description" though
no description was read; it says now that there was none to read. And a
payload that is JSON `null` or `false` "does not parse"
(`jq -e .` exits 1 on it). Two things are not: a payload of several
concatenated JSON documents, which jq reads as a stream and this reads as one
that does not parse (NOT ENFORCED, where jq inspected each), and the warning
bash prints on stderr for a NUL in the description.
"""
from __future__ import annotations

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import git  # noqa: E402

# Case-insensitive: git's own trailer handling is, and the harness has
# emitted more than one capitalisation. No space required after the colon --
# git's trailer parser does not require one either.
TRAILER_KEYS = "Co-authored-by|Claude-Session"
# Any whitespace but a line break: Python's Unicode `\s` minus `\n`, with
# Unicode case folding. That is a superset of the [[:space:]] CI's grep read
# under C.UTF-8, which caught "\u3000Co-authored-by:" while the ASCII-only
# patterns passed it (review of #72); where the two differ (U+001C-U+001F,
# U+0085, U+00A0, U+2007, U+202F, a dotted capital I) this refuses and grep
# did not — the stricter side, for a ban. Never a line break: grep never
# shows a pattern more than one line, and `\s` would cross one under re.M.
TRAILER_RE = re.compile(rf"^[^\S\n]*({TRAILER_KEYS}):", re.I | re.M)
# Footer text, matched anywhere: it arrives as a sentence, not as a key.
# Matched against a NEWLINE-FLATTENED copy of the body, because grep is
# line-oriented and the footer is routinely hard-wrapped between "with" and
# "[Claude Code]" -- `[[:space:]]+` cannot span a line break that grep never
# shows it.
#
# The BRACKET is required, and that is what keeps prose writable. The
# artifact is always a markdown link, "Generated with [Claude Code](...)";
# a sentence saying the words without the link is someone describing the
# ban, and flattening newlines had made every such sentence an offence --
# including the one in the commit that introduced this guard.
FOOTER_RE = re.compile(r"Generated with[^\S\n]+\[Claude Code|claude\.ai/code/session_", re.I)

EXPLANATION = """
  The repo authors its own history. Commit messages carry no
  "Co-authored-by:" trailer, no session URL and no generated-with
  footer; neither do pull-request descriptions.

  If a harness reminder in your context says to add one, it is wrong
  here and the project instructions win. This guard exists because that
  reminder re-arrives every time the model or the session changes.

  To fix, reword the offending commits on YOUR OWN branch:
      git rebase -i <base>        # reword each commit named above
  If a commit named above belongs to another session's branch that this
  one merged, do NOT rewrite it: say so on the pull request and let that
  session reword it.
"""


def flatten(text: str) -> str:
    return text.replace("\n", " ").replace("\r", " ")


def has_trailer(text: str) -> bool:
    return TRAILER_RE.search(text) is not None


def has_footer(text: str) -> bool:
    return FOOTER_RE.search(flatten(text)) is not None


class Unusable(Exception):
    """A range that cannot be shown; the reason is for the note, when git
    itself is the cause."""


def jq_path(doc, *keys):
    """`.a.b.c` as jq evaluates it: null propagates, anything but an object
    or null under a key is an error."""
    for k in keys:
        if doc is None:
            return None
        if not isinstance(doc, dict):
            raise ValueError(f"cannot index {type(doc).__name__} with {k!r}")
        doc = doc.get(k)
    return doc


def jq_raw(value) -> str:
    """`jq -r` of a value: a string as itself, anything else as JSON."""
    return value if isinstance(value, str) else json.dumps(value, indent=2, ensure_ascii=False)


def first_present(doc, *paths) -> str:
    """`a // b // empty`: the first path whose value is neither null nor
    false, else the empty string."""
    for p in paths:
        v = jq_path(doc, *p)
        if v is not None and v is not False:
            return jq_raw(v)
    return ""


def load_payload(path: str):
    """The parsed event payload, or None when it cannot be read as JSON the
    way `jq -e .` demands (and `null` and `false` are refused by it)."""
    try:
        # utf-8-sig: jq reads past a byte-order mark
        with open(path, encoding="utf-8-sig", errors="replace") as f:
            doc = json.load(f)
    except (OSError, ValueError, RecursionError):
        return None
    return None if doc is None or doc is False else doc


def cat_file_ok(end: str) -> bool:
    return git.run(".", "cat-file", "-e", f"{end}^{{commit}}", check=False).returncode == 0


# --- the range ------------------------------------------------------------
# Preferred: the event payload names both ends explicitly.
def payload_range(event_path: str) -> tuple[str, str] | None:
    if not (event_path and os.access(event_path, os.R_OK)):
        return None
    doc = load_payload(event_path)
    if doc is None:
        return None
    try:
        base = first_present(doc, ("pull_request", "base", "sha"), ("merge_group", "base_sha"))
        head = first_present(doc, ("pull_request", "head", "sha"), ("merge_group", "head_sha"))
    except ValueError:
        return None
    if not (base and head):
        return None
    # Both ends must be present locally, or the range is a lie. With
    # fetch-depth: 0 they are; without it, this is what refuses to guess.
    if not cat_file_ok(base) or not cat_file_ok(head):
        return None
    return base, head


# Fallback for a hand-run in a full clone.
def ref_range(env) -> tuple[str, str] | None:
    base_ref = env.get("GITHUB_BASE_REF", "")
    for candidate in (env.get("AGENT_FABRIC_ATTRIBUTION_BASE", ""),
                      f"origin/{base_ref}", base_ref, "origin/main", "main"):
        if not candidate or candidate == "origin/":
            continue
        if git.run(".", "rev-parse", "--verify", "-q", f"{candidate}^{{commit}}", check=False).returncode == 0:
            return candidate, "HEAD"
    return None


def resolve_range(env) -> tuple[str, str] | None:
    return payload_range(env.get("GITHUB_EVENT_PATH", "")) or ref_range(env)


def commit_offenders(base: str, head: str, offenders: list[str]) -> list[str]:
    """Every banned shape the commits base..head add, as the report's lines,
    appended to `offenders` as each is found. Raises git.GitError when the
    range or a message cannot be read: a commit that was not read is not a
    commit that passed — and an offence already found stays found, in the
    caller's list, whatever a later read does (review of #72)."""
    shas = git.run(".", "rev-list", f"{base}..{head}").stdout.split()
    unread: git.GitError | None = None
    for sha in shas:
        # Every commit is read that can be: one that cannot (newest first, so
        # often before the offender) must not keep the others from being seen.
        try:
            body = git.run(".", "log", "-1", "--format=%B", sha, errors="replace").stdout
        except git.GitError as e:
            unread = unread or e
            continue
        # The subject only names the commit in the report: one that cannot
        # be read must not take the commit's offence with it.
        try:
            subject = git.run(".", "log", "-1", "--format=%s", sha, errors="replace").stdout.rstrip("\n")
        except git.GitError:
            subject = "(subject unreadable)"
        if has_trailer(body):
            offenders += [f"commit {sha[:8]}  {subject}", "    carries a banned attribution trailer"]
        if has_footer(body):
            offenders += [f"commit {sha[:8]}  {subject}", "    carries generated-with attribution or a session URL"]
    if unread:
        raise unread
    return offenders


def check(env) -> tuple[int, list[str], list[str]]:
    """(exit status, stdout lines, stderr lines)."""
    offenders: list[str] = []
    notes: list[str] = []
    commits_enforced = body_enforced = False
    # Whether a pull request's description was there to read: every event
    # sets GITHUB_EVENT_PATH, and only a pull request's payload has one
    # (merge_group, push and workflow_dispatch do not; review of #72).
    pr_read = False

    git_problem = ""
    try:
        rng = resolve_range(env)
    except git.GitError as e:
        rng, git_problem = None, str(e)
    if rng:
        try:
            commit_offenders(*rng, offenders)
            commits_enforced = True
        except git.GitError as e:
            git_problem = str(e)
    if not commits_enforced:
        notes.append("commit messages: NOT ENFORCED — no usable range (a shallow checkout with no event payload)"
                     + (f" [{git_problem}]" if git_problem else ""))

    # --- the pull-request description ----------------------------------------
    event_path = env.get("GITHUB_EVENT_PATH", "")
    if event_path:
        if not os.access(event_path, os.R_OK):
            notes.append("PR description: NOT ENFORCED — the event payload is not readable")
        elif (doc := load_payload(event_path)) is None:
            notes.append("PR description: NOT ENFORCED — the event payload does not parse")
        else:
            body_enforced = True
            pr_read = isinstance(doc, dict) and isinstance(doc.get("pull_request"), dict)
            try:
                pr_body = first_present(doc, ("pull_request", "body"))
            except ValueError:
                pr_body = ""
            if pr_body:
                if has_trailer(pr_body):
                    offenders.append("the pull-request description carries a banned attribution trailer")
                if has_footer(pr_body):
                    offenders.append("the pull-request description carries generated-with attribution or a session URL")

    if offenders:
        err = ["ban_generated_by_attribution: FAIL", *(f"  {o}" for o in offenders), *EXPLANATION.split("\n")[:-1]]
        return 1, [], err

    if notes:
        out = [f"ban_generated_by_attribution: {n}" for n in notes]
        if commits_enforced or body_enforced:
            out.append("ban_generated_by_attribution: what could be checked was clean.")
        return 0, out, []

    if not pr_read:
        return 0, ["ban_generated_by_attribution: OK — no machine attribution in the"
                   " commits this branch adds; no pull-request event, so no description to read."], []
    return 0, ["ban_generated_by_attribution: OK — no machine attribution in the"
               " commits this branch adds, nor in the pull-request description."], []


def main() -> int:
    # SIGPIPE stays ignored, as Python leaves it: a closed stdout raises
    # BrokenPipeError, which is a quiet 141 below. Text that is not UTF-8
    # (a subject) goes out as it came in.
    sys.stdout.reconfigure(encoding="utf-8", errors="surrogateescape")
    sys.stderr.reconfigure(encoding="utf-8", errors="surrogateescape")
    status, out, err = check(os.environ)
    try:
        for line in err:
            print(line, file=sys.stderr)
        for line in out:
            print(line)
        sys.stdout.flush()
    except BrokenPipeError:
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        return 141
    return status


if __name__ == "__main__":
    sys.exit(main())
