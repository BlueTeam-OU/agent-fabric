#!/usr/bin/env python3
"""tools/fabric/github/post_review.py — post THE review of a PR, the review
class's blind review, as a marked review object (ADR-040 Wave 1;
`fabric-pr post-review` runs it).

CONTRACT, frozen from the bash (ADR-040 §5 rule 3):
  argv      <pr> [--model <name>] [--head <sha>] [--dry-run] [-h|--help]
  stdin     the review body, byte for byte; never an argument
  env       AGENT_FABRIC_ROOT, AGENT_FABRIC_LAUNCH_ROLE (the role the
            session was launched with)
  stdout    `posted review: <url>` and the line after it, naming the
            commit the review is recorded on; with --dry-run the would-be
            review and its body
  stderr    every refusal and warning, prefixed `post-review: `
  exit      0 posted; 2 an invocation problem, a refusal, or a post
            GitHub rejected or did not confirm

A REVIEW COVERS THE HEAD IT READ, never the PR's head at posting time
(agent-fabric ADR-020 §5 rule 6; "only a pinned review covers a head" is
rule 10). A report with dispatch headers is posted
with commit_id = their head_sha: every header names the same one, or the
report is refused; a sha that is not a commit of the PR is refused; one that
is no longer the head is posted against it all the same, saying so on
stdout with the URL, so the gate counts it for that commit and never for the head pushed
after it. A report with no header names its head with --head, or is refused
(ADR-020 §5 rule 6): posted against the PR's head, a summary written for an
older range read as the review of the head pushed after it.

A REPORT WHOSE DISPATCH HEADERS NAME A RANGE IS POSTED AS v2 (agent-fabric ADR-065 §2 C, §5 rule 4): every header
names the same base_sha, head_sha, card_base and config, or the report is refused, and the first line is
<!-- agent-fabric-review v2 base=… head=… card=… config=… -->. The report then carries exactly one coverage block
(review_coverage.py has its grammar), which is checked against `git diff --name-only base..head` run here, in the
working copy: a path omitted, a path outside the range, a base that is not an ancestor of the head, a marker-like
line in the body, a second block, or a block that is not that JSON refuses the report. A block with a path "not read"
posts, and the line after the marker says so; no reader counts it as coverage of its head. The posted block is the
parsed data re-written, not the model's text. A header with none of those fields (a report from before the change)
and a report with no header are REFUSED, naming what is missing: v1 stays readable for the reviews already posted
(agent-fabric ADR-065 §5 rule 4), never writable, because a v1 review counts and names no range. The base of a v2
review is tied to the PR on this side too: it is the PR's merge-base with its base branch or the head of the PR's last
checkpoint review (review_checkpoint), so a narrow range posted as a full review does not count and chain. The
assembled body is read back with the readers' own parser before it is sent, and must give the coverage just validated.

REVIEW_MARKER is the contract with every reader (pr-review-status, the
gate, results.py): the first line of the body, versioned because a later
field must not silently reclassify older reviews. test_post_review_cli.py
compares this module's line with the reader's (pr_review_status's, defined
in github/review_status/config.py), and tests/test_post_review.py the two
constants and results.py's import. This tool no longer WRITES it (a new review is v2); the readers keep counting
the v1 reviews already posted.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
import tempfile
from urllib.parse import quote

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import gh  # noqa: E402
import review_brief  # noqa: E402
from github import common, local, review_coverage  # noqa: E402
from github.review_checkpoint import last_checkpoint_review  # noqa: E402

REVIEW_MARKER = "<!-- agent-fabric-review v1 -->"

HELP = """Post THE review of a PR — the review class's blind review — as a
review object, marked so the tooling counts it as coverage of the head.

WHY THIS EXISTS. Every session pushes as the SAME GitHub account, so a
review the review class wrote is indistinguishable from the author's
own thread reply by account alone, and pr_review_status used to
bucket both as "self reviews … not coverage". Prose attribution drifts
— three sessions wrote three different sentences — and a coverage
claim guessed from prose is worse than none. So every review this
script posts is a REVIEW OBJECT (never an issue comment, which is not
a review) and carries REVIEW_MARKER (below) as its first line, the
exact string fabric-pr review-status tests for.

The review class is the review. There is no automated reviewer it
stands in for: the fabric dispatches a blind reviewer for every PR
(runtime/claude-code/agents/code-review.md, briefed by bin/fabric-review),
and this is how that review reaches the PR and the gate.

Usage:
  fabric-pr post-review <pr> [options]   # body on stdin
  fabric-pr post-review --repo <owner/name|project> <pr> …   # another repository's PR

  # The review class's report, as it arrives: it opens with the brief's
  # agent-fabric-dispatch v1 block, which names the head it read.
  fabric-pr post-review 552 <<'EOF'
  ```agent-fabric-dispatch v1
  { …, "evidence_mode": "pinned", "head_sha": "<full sha>", … }
  ```
  Found a P1 in the ownership guard: a four-segment branch typed
  `Fix/` was classified unowned, so fabric-pr reply would post to it.
  EOF

Options:
  --model <name>   record which model produced the review (default: unset);
                   `codex` is the second engine's (agent-fabric ADR-053)
  --head <sha>     the commit the review read (the full sha); it must be the
                   head_sha the report's dispatch header names
  --dry-run        show what would be posted, send nothing
  -h, --help

The body arrives on STDIN and is never interpolated into a command
line — the same rule, and the same reason, as fabric-pr reply: a body
quoting `backticks` or $vars passed through `-f body="…"` is expanded
by the shell before gh sees it, and that has already posted a mangled
comment in this repo.

Only a pinned review covers a head (agent-fabric ADR-020 §5 rule 10).
A report that carries the brief's agent-fabric-dispatch v1 header is
posted only when every such header says "evidence_mode": "pinned"; a
working-tree one, or a header it cannot read, is refused before the PR
is read. A header is read only as a fenced block of its own; any other
line naming agent-fabric-dispatch (in a blockquote, a list item, prose,
or another version) is refused, naming the line. A report with no
header is refused (a new review is v2, which needs the header's range);
a pinned one posts with every header taken out, since a
header names the dispatching session.

A pinned review is posted against the head it read, the headers'
head_sha, never the PR's head at posting time: headers naming no
head_sha or different ones refuse, and so does a sha that is not a
commit of the PR, and so does a --head that names another. A review of
an older head, posted after a push, is posted against that older commit,
and says so on stdout: the gate counts it for that commit, not for the
new head.

A report whose headers name the range (base_sha, head_sha, card_base and config) is posted as a v2 review
(agent-fabric ADR-065): the first line is <!-- agent-fabric-review v2 base=… head=… card=… config=… -->, and the report
carries exactly one fenced block whose info string is `agent-fabric-coverage v1`:

  ```agent-fabric-coverage v1
  {"paths": {"<path>": {"status": "read"}, "<path>": {"status": "not read", "reason": "…"}},
   "lenses": {"<lens>": "applied" | "not applied"}}
  ```

Its paths are exactly those of `git diff --name-only <base>..<head>`, which this tool computes in the working copy:
a path omitted, a path outside the range, a base that is not an ancestor of the head, a second block, a marker-like
line in the body, or a block that is not that JSON refuses the report. A path "not read" posts, and the line after the
marker says "partial coverage: N path(s) not read"; the gate does not count a partial review as coverage of its head.
A report with no header, or a header from before those fields, is refused: a new review is posted as v2 only.
The range's base must be the PR's merge-base with its base branch or the head of its last checkpoint review (an
earlier v2 review the next one may start from, review_checkpoint.py); otherwise the report is refused, as it is
when GitHub cannot say.

Exit codes:
  0  posted
  2  invocation problem, a working-tree report, a report whose head is
     unnamed or not one commit of the PR, or the PR belongs to another
     session"""

# Kept identical to pr_reply's: a wrong "names no session" means writing
# to somebody else's PR.
AUTOMATION = {"dependabot", "renovate", "github-actions", "weblate", "imgbot", "allcontributors", "pre-commit-ci",
              "snyk-bot"}
LOCALE_FILE = re.compile(r"identities/roles/[^/\n]+/locale/[^/\n]+/[^/\n]+")
# GitHub lists at most 3000 files of a pull request and stops there
# without an error: a list that long may be cut, so it is not read as
# whole (re-review of #70).
FILE_LIST_CAP = 3000
# The same for a pull request's commits, which GitHub lists up to 250 of.
COMMIT_LIST_CAP = 250
SHA = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")
SHA40 = re.compile(r"[0-9a-f]{40}")
SHA256 = re.compile(r"[0-9a-f]{64}")
# The dispatch header a brief opens with (review_brief.dispatch_header), when a report carries it: a fence of three
# or more backticks or tildes whose info string is the header's version, closed by the same fence. CommonMark lets
# spaces stand between a fence and its info string, and a model reformatting the header may write them: a spaced
# header unmatched would post a working-tree report as one with no header (review of #259, F5; ledger.FENCE agrees).
DISPATCH_FENCE = re.compile(r"^[ \t]*(`{3,}|~{3,})[ \t]*" + re.escape(review_brief.DISPATCH_VERSION) + r"[ \t]*$")
# A fence whose info string starts with the header's name, behind any blockquote or list markers: one DISPATCH_FENCE
# does not recognise (quoted in a blockquote or a list item, or another version) is a header this tool cannot read,
# so it refuses rather than post it unchecked (review of #259, risk 1). Not every line naming it: prose and a quoted
# hunk carry no header, and a Codex review naming it in a finding would be refused and lost (supplier review, F1).
DISPATCH_NAME = review_brief.DISPATCH_VERSION.split()[0]
# A list marker needs whitespace after it, as in CommonMark: a quoted diff's "+```" or "-```" opens no list item
# (re-review, finding 1).
STRAY_FENCE = re.compile(r"^[ \t]*(?:>[ \t]*|(?:[*+-]|\d{1,9}[.)])[ \t]+)*(`{3,}|~{3,})[ \t]*" + re.escape(DISPATCH_NAME))


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


def _unique_keys(pairs: list) -> dict:
    """A JSON object whose keys are each given once: with two evidence_mode keys, which one counts is the parser's
    choice, and the header has not said which evidence it is."""
    keys = [k for k, _ in pairs]
    if len(set(keys)) != len(keys):
        raise ValueError("a key given twice")
    return dict(pairs)


def evidence_refusal(body: str) -> str:
    """Why a report may not be posted as the review of a head, or "" when it may. agent-fabric ADR-020 §5 rule 10:
    only a pinned review covers a head, so every dispatch header in the report must say evidence_mode "pinned" —
    every one, a header the report quotes included, because nothing tells the report's own header from a quote,
    and a report wrongly refused is posted again without the quote while one wrongly posted claims coverage it does
    not give. A report with none posts as before (its cost is attributed inferred). A header that cannot be read
    refuses: it claims a dispatch whose evidence it then does not show, and so does a fence opening one that is not
    read as a header at all (in a blockquote or a list item, or another version). A line is named as an editor
    counts it, by "\n"."""
    # splitlines, not split("\n"): a report with CRLF line ends keeps its \r on every line otherwise, and the
    # opening fence would not match where the closing one does.
    lines = body.splitlines()
    line_no = _newline_numbers(body)
    read: set[int] = set()
    for i, close in _dispatch_headers(lines):
        where = f"the {review_brief.DISPATCH_VERSION} header at line {line_no[i]}"
        if close is None:
            return f"{where} is never closed"
        try:
            header = json.loads("\n".join(lines[i + 1:close]), object_pairs_hook=_unique_keys)
        except ValueError:
            header = None
        if not isinstance(header, dict):
            return f"{where} is not a JSON object with each key once"
        mode = header.get("evidence_mode")
        if mode != "pinned":
            said = f"says evidence_mode {mode!r}" if mode is not None else "names no evidence_mode"
            return (f"{where} {said}, and only a pinned review covers a head (agent-fabric ADR-020 §5 rule 10). "
                    "Every header in a report counts, one it quotes too: a working-tree review stays out of the PR "
                    "(review the pushed range pinned and post that); a quoted header is taken out of the report")
        read.update(range(i, close + 1))
    stray = next((n for n, line in enumerate(lines) if n not in read and STRAY_FENCE.match(line)), None)
    if stray is not None:
        return (f"line {line_no[stray]} opens an {DISPATCH_NAME} fence that is not an {review_brief.DISPATCH_VERSION} "
                "header this tool reads, a fenced block of its own: a header in a blockquote or a list item, or of "
                "another version, may say working-tree unchecked. Take the block out of the report")
    return ""


def report_head(body: str) -> tuple[str | None, str]:
    """(the head every dispatch header names, why the report may not be posted or ""); the head is None for a report
    with no header. Only after evidence_refusal passed, which has read every header as a JSON object. A pinned
    review covers the commit it read, so the report says which one; two different ones, or none, leave the commit
    the review is pinned to a guess."""
    lines = body.splitlines()
    line_no = _newline_numbers(body)
    heads: dict[str, int] = {}
    for i, close in _dispatch_headers(lines):
        sha = json.loads("\n".join(lines[i + 1:close])).get("head_sha")
        if not isinstance(sha, str) or not SHA.fullmatch(sha):
            return None, (f"the {review_brief.DISPATCH_VERSION} header at line {line_no[i]} names no head_sha, so the "
                          "commit it reviewed is unknown (brief the review on a range)")
        heads.setdefault(sha, line_no[i])
    if len(heads) > 1:
        named = ", ".join(f"{sha[:12]} at line {n}" for sha, n in heads.items())
        return None, f"its {review_brief.DISPATCH_VERSION} headers name different heads ({named})"
    return next(iter(heads), None), ""


def report_range(body: str) -> tuple[review_coverage.Marker | None, str]:
    """(the v2 marker the dispatch headers name, why the report may not be posted or ""); the marker is None for a
    report whose headers name none of card_base and config (v1). Only after report_head, which has read every header
    as a JSON object with a head_sha. Every header names the same four values or none: the first line of the posted
    review is one range, and a report with two leaves which one the review read to a pick."""
    lines = body.splitlines()
    line_no = _newline_numbers(body)
    seen: dict[tuple, int] = {}
    plain = 0
    for i, close in _dispatch_headers(lines):
        header = json.loads("\n".join(lines[i + 1:close]))
        where = f"the {review_brief.DISPATCH_VERSION} header at line {line_no[i]}"
        if header.get("config") is None and header.get("card_base") is None:
            plain += 1
            continue
        got = (header.get("base_sha"), header.get("head_sha"), header.get("card_base"), header.get("config"))
        for name, value, pattern in zip(("base_sha", "head_sha", "card_base", "config"), got,
                                        (SHA40, SHA40, SHA40, SHA256)):
            if not isinstance(value, str) or not pattern.fullmatch(value):
                return None, f"{where} names no usable {name}, which the v2 marker records"
        seen.setdefault(got, line_no[i])
    if not seen:
        return None, ""
    if plain:
        return None, "some of its dispatch headers name the range's card_base and config and some do not"
    if len(seen) > 1:
        return None, f"its {review_brief.DISPATCH_VERSION} headers name different ranges (lines {', '.join(map(str, seen.values()))})"
    base, head, card, config = next(iter(seen))
    return review_coverage.Marker(base, head, card, config), ""


def v2_report(body: str) -> tuple[str, review_coverage.Coverage]:
    """(the report without its coverage block, the block read), or Refused. The report is model output: a line a
    reader could take for a review marker is refused rather than left in the posted body to be argued about."""
    stray = review_coverage.marker_like_lines(body)
    if stray:
        die(f"not posting this report: line {stray[0]} looks like a review marker, and a report posted as v2 holds "
            "none: the marker is the posted review's first line, written by this tool. Take the line out of the report.")
    try:
        coverage, span = review_coverage.read_block(body)
    except review_coverage.CoverageError as e:
        die(f"not posting this report: {e}.")
    rest = review_coverage.without_block(body, span)
    if not rest.strip(" \t\n"):
        die("the review body is empty once its coverage block is taken out.")
    return rest, coverage


def range_refusal(root: str, marker: review_coverage.Marker, coverage: review_coverage.Coverage) -> str:
    """Why the coverage block does not account for the range the marker names, or "". The paths are this tool's own
    `git diff --name-only`, never the report's claim of them."""
    try:
        if not review_coverage.is_ancestor(root, marker.base, marker.head):
            return f"base {marker.base[:12]} is not an ancestor of head {marker.head[:12]}"
        return review_coverage.check_paths(coverage, review_coverage.diff_paths(root, marker.base, marker.head))
    except review_coverage.CoverageError as e:
        return str(e)


def readback_refusal(full_body: str, marker: review_coverage.Marker, coverage: review_coverage.Coverage) -> str:
    """Why the readers would not read the assembled body as the marker and coverage validated, or "". Compares what
    the shared parser finds, not what this tool meant to write."""
    read = review_coverage.read_review(full_body)
    if read is None or read.problem:
        return ("the assembled review does not read back as a v2 review"
                + (f" ({read.problem})" if read else "") + "; an unclosed code fence in the report is the usual cause")
    if read.marker != marker or read.coverage != coverage:
        return ("the assembled review reads back as another range or another coverage than the one validated; "
                "an unclosed code fence in the report is the usual cause")
    return ""


def base_refusal(root: str, repo: str, pr: str, base_branch: str, marker: review_coverage.Marker) -> str:
    """Why the marker's base is not one a v2 review of this PR may start from, or "": the PR's merge-base with its base
    branch (a full review) or the head of the PR's last checkpoint review (a re-review). Anything else, a narrow range
    posted as a full review, would count and chain. FAILS CLOSED: a lookup that fails refuses, and a checkpoint in
    doubt (review_checkpoint) is none, so the merge-base is the only start left."""
    try:
        out = gh.run(["api", f"repos/{repo}/compare/{quote(base_branch, safe='/')}...{marker.head}",
                      "--jq", ".merge_base_commit.sha"], what=f"gh api GET repos/{repo}/compare")
    except gh.GhError as e:
        return f"the merge-base of PR #{pr} with {base_branch} could not be read ({e.reason}), so the range's base is unchecked"
    merge_base = out.strip()
    if not SHA40.fullmatch(merge_base):
        return f"the merge-base of PR #{pr} with {base_branch} could not be read, so the range's base is unchecked"
    if marker.base == merge_base:
        return ""
    found = last_checkpoint_review(pr, marker.head, lambda card: review_brief.config_fingerprint(root, card),
                                   repo=repo, cwd=root)
    if found and found[1] == marker.base:
        return ""
    return (f"base {marker.base[:12]} is neither the merge-base {merge_base[:12]} of PR #{pr} with {base_branch} (a full "
            "review) nor the head of the PR's last checkpoint review "
            + (f"({found[1][:12]})" if found else "(the PR has none a re-review may start from)")
            + ": a narrower range is not the review of the PR, and would count as one")


def pr_commit_refusal(repo: str, pr: str, sha: str) -> str:
    """Why sha is not known to be a commit of the PR, or "" when it is. FAILS CLOSED, as locale_only: a list not
    read, or one GitHub may have cut, does not say the sha is in it."""
    try:
        out = gh.run(["api", "--paginate", "--slurp", f"repos/{repo}/pulls/{pr}/commits?per_page=100"],
                     what=f"gh api GET repos/{repo}/pulls/{pr}/commits")
        pages = json.loads(out)
    except (gh.GhError, ValueError):
        return f"the commits of PR #{pr} could not be read"
    if not isinstance(pages, list) or not all(isinstance(p, list) for p in pages):
        return f"the commits of PR #{pr} could not be read"
    commits = [c for page in pages for c in page]
    if any(isinstance(c, dict) and c.get("sha") == sha for c in commits):
        return ""
    if len(commits) >= COMMIT_LIST_CAP:
        return f"{sha[:12]} is not among the {len(commits)} commits GitHub lists for PR #{pr}, a list it cuts there"
    return f"{sha[:12]} is not a commit of PR #{pr} (a force-push may have dropped it)"


def _newline_numbers(body: str) -> list[int]:
    """The 1-based "\n" line each of body.splitlines() starts on: splitlines also breaks at U+2028, \x0c and the
    like, which an editor, sed -n or nl do not count (supplier review, F2)."""
    numbers, n = [], 1
    for line in body.splitlines(keepends=True):
        numbers.append(n)
        n += line.count("\n")
    return numbers


def _dispatch_headers(lines: list[str]):
    """(opening line, closing line) of each dispatch header in order; the closing line is None for one never
    closed, and then the scan stops there."""
    i = 0
    while i < len(lines):
        m = DISPATCH_FENCE.match(lines[i])
        if not m:
            i += 1
            continue
        close = next((j for j in range(i + 1, len(lines)) if lines[j].strip() == m.group(1)), None)
        yield i, close
        if close is None:
            return
        i = close + 1


def _dispatch_headers_present(body: str) -> bool:
    return any(True for _ in _dispatch_headers(body.splitlines()))


def first_dispatch_header(text: str) -> str:
    """The first dispatch header of a brief or report, fences included, as written; "" when it has none or never
    closes it. review_codex puts the brief's own in front of the report it posts."""
    lines = text.splitlines()
    for i, close in _dispatch_headers(lines):
        return "\n".join(lines[i:close + 1]) if close is not None else ""
    return ""


def without_dispatch_headers(body: str) -> str:
    """The report as it is posted: every dispatch header taken out. A header names the dispatching session
    (parent_session_id), its job and maybe a local clone path, which the repo keeps out of what it publishes; the
    ledger reads the header from the transcript, and evidence_refusal has read the mode already, so the PR loses
    nothing. Only after evidence_refusal passed: it is what makes every header closed. A report with none is
    posted byte for byte."""
    spans = list(_dispatch_headers(body.splitlines()))
    if not spans:
        return body
    drop = {j for i, close in spans for j in range(i, close + 1)}
    # Kept with their own line ends, and the same split as the scan's: splitlines breaks at U+2028, \x0c and the
    # like too, and a rejoin with "\n" would rewrite those in the findings that stay.
    kept = body.splitlines(keepends=True)
    return "".join(line for n, line in enumerate(kept) if n not in drop).strip("\r\n")


def identity(fabric: str, *args: str) -> str:
    ident = os.path.join(fabric, "runtime", "identity.py")
    if not os.path.exists(ident):
        return ""
    rc, out = local.probe([sys.executable, ident, *args])
    return out.strip() if rc == 0 else ""


def run(argv: list[str], stdin) -> int:
    pr, model, given_head, dry = "", "", "", False
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("--model", "--head"):
            if i + 1 >= len(argv):
                die(f"{a} needs a value")
            if a == "--model":
                model = argv[i + 1]
            else:
                given_head = argv[i + 1]
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
    # The full sha, as GitHub's commit_id takes it: an abbreviation would be a second resolution, against a clone
    # that may not hold the commit.
    if given_head and not SHA.fullmatch(given_head):
        die(f"--head '{given_head}' is not a full commit sha")
    for binary in ("gh", "git", "hostname"):
        if not shutil.which(binary):
            die(f"{binary} is required but not installed.")

    # STDIN, never an argument. See the help.
    if callable(stdin):
        stdin = stdin()
    if stdin is None:
        die("the review body is read from stdin — pipe it, or use <<'EOF' … EOF")
    body = stdin
    if not body.strip(" \t\n"):
        die("the review body is empty.")
    # Before anything is read of the PR: what the report is decides it, whichever PR it names, --dry-run too.
    refusal = evidence_refusal(body)
    if refusal:
        die(f"not posting this report as the review of a head: {refusal}.")
    reviewed, refusal = report_head(body)
    if refusal:
        die(f"not posting this report: {refusal}.")
    if reviewed is None and not given_head:
        die("not posting this report: it has no dispatch header and no --head, so the commit it reviewed is "
            "unknown, and posted on the PR's head it would read as the review of whatever was pushed last. "
            "Post the review class's report whole, its agent-fabric-dispatch v1 block first as the brief gave it, "
            "or name the commit it read with --head.")
    if reviewed and given_head and given_head != reviewed:
        die(f"not posting this report: --head {given_head[:12]} is not the head_sha {reviewed[:12]} its dispatch "
            "header names.")
    reviewed = reviewed or given_head
    marker, refusal = report_range(body)
    if refusal:
        die(f"not posting this report: {refusal}.")
    if marker is None:
        # ADR-065 §5 rule 4: v1 is read, never written. A v1 review counts as coverage of its head and names no range,
        # so a new one would be the review the v2 checks were made to stop.
        die("not posting this report: " + (
            "it has no dispatch header, and a review is posted as v2, which takes its range (base_sha, head_sha, "
            "card_base, config) from the header" if not _dispatch_headers_present(body) else
            "its dispatch header names none of card_base and config, and a review is posted as v2, which records them")
            + ". Brief the review on a range (fabric-review brief) and post the report whole, header first.")
    body = without_dispatch_headers(body)
    if not body.strip(" \t\n"):
        die("the review body is empty once its dispatch header is taken out.")
    body, coverage = v2_report(body)

    try:
        repo = gh.this_repo()
    except gh.GhError as e:
        die(f"could not resolve the repository: {e.reason}.")
    try:
        meta = gh.pr_view(int(pr), ["number", "state", "headRefName", "headRefOid", "baseRefName"])
    except (gh.GhError, ValueError):
        die(f"could not read PR #{pr} in {repo} (--repo names another repository).")
    # FAILS CLOSED, and this is what makes the lane guard true: a payload
    # missing the branch read as "names no session" in the bash, and the
    # guard took the POSTING path.
    meta = meta if isinstance(meta, dict) else {}
    branch, head, state = meta.get("headRefName"), meta.get("headRefOid"), meta.get("state")
    if not isinstance(branch, str) or not branch:
        die(f"could not read the head branch of PR #{pr} — refusing, because ownership is unknown.")
    if not isinstance(head, str) or not head:
        die(f"could not read the head commit of PR #{pr} — refusing.")
    base_branch = meta.get("baseRefName")
    if not isinstance(base_branch, str) or not base_branch:
        die(f"could not read the base branch of PR #{pr}, so the review's base cannot be tied to it — refusing.")

    # ── lane guard ──────────────────────────────────────────────────
    # Same rule as pr-reply, and the same reason: a review cannot be
    # unsent, and another session is mid-flight on work you cannot see.
    root = local.toplevel()
    if not root:
        die("not inside a git worktree, so the session's working-copy identity is unknown — refusing.")
    # The session is the AGENT — the Linux login — on this host. Older
    # branches carry the working-copy name in the second segment, so that
    # is accepted as this session too while they last.
    fabric = os.environ.get("AGENT_FABRIC_ROOT") or os.path.join(root, "..", "agent-fabric")
    host = local.probe(["hostname", "-s"])[1].strip()
    agent = identity(fabric) or local.probe(["id", "-un"])[1].strip()
    me, me_legacy = f"{host}/{agent}", f"{host}/{os.path.basename(root)}"
    owner = "/".join(branch.split("/")[:2])
    carve_out = False
    if not branch_names_a_session(branch):
        say(f"post-review: #{pr} is on '{branch}', which names no session.")
        say("  No session owns it, so there is nobody to defer to — posting.")
    elif owner not in (me, me_legacy):
        # The one exception: a locale's translations are committed by that
        # locale's holder and merged by fabric-coordinator (agent-fabric's
        # AGENTS.md, the locale carve-out), so the merger must post the
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

    # The head the review read, never the head now: a review of an older head posted as the new one's reads in the
    # gate as coverage of commits nobody reviewed (the module docstring).
    commit = reviewed
    if commit != head:
        refusal = pr_commit_refusal(repo, pr, commit)
        if refusal:
            die(f"not posting this report: {refusal}.")
    refusal = range_refusal(root, marker, coverage)
    if refusal:
        die(f"not posting this report: {refusal}.")
    refusal = base_refusal(root, repo, pr, base_branch, marker)
    if refusal:
        die(f"not posting this report: {refusal}.")
    # Said on stdout with the URL, not as a warning: which commit the review is recorded on is the result.
    recorded = (f"recorded on {commit}, the head of PR #{pr}." if commit == head else
                f"recorded on {commit}; the head {head} of PR #{pr} is not covered by it.")

    # ── assemble ────────────────────────────────────────────────────
    # The marker goes FIRST so it survives any truncation a reader
    # applies, and so the first line identifies the review.
    header = marker.line()
    if coverage.not_read:
        header += "\n" + review_coverage.partial_line(coverage)
    if model:
        header += f"\n<!-- model: {model} -->"
    if carve_out:
        header += "\n<!-- posted by the locale carve-out's merger -->"
    # The second engine (agent-fabric ADR-053) is not the review class, and
    # its review must not say it is; the marker and its reading are the same.
    who = ("Codex, the second review engine, run once against the commit this review is on" if (model or "").strip().lower() == "codex"
           else "the review class, dispatched against the commit this review is on")
    full_body = f"""{header}
**Blind review** — {who} with a
brief of facts and none of the author's session context. Its findings
are judged before they are answered; the judgement follows in the PR.

{body}"""
    full_body += "\n\n" + review_coverage.render_block(coverage) + "\n"
    if len(full_body) > review_coverage.MAX_REVIEW_CHARS:
        die(f"not posting this report: the review is {len(full_body)} characters, over the "
            f"{review_coverage.MAX_REVIEW_CHARS} GitHub takes in one review.")
    # The body the readers will be given, read with their parser: the report around the block is model text, and an
    # unclosed fence in it swallows the block written after it (the block validated above is then not the one a
    # reader finds).
    refusal = readback_refusal(full_body, marker, coverage)
    if refusal:
        die(f"not posting this report: {refusal}.")

    if dry:
        print(f"would post a review to #{pr} ({state}), {recorded}")
        print("--- body ---")
        print(full_body)
        return 0

    # The payload in a file, never -f body="…": a review body quotes code
    # by definition. gh's own --jq picks the URL out; the jq binary is not
    # involved.
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as f:
        json.dump({"body": full_body, "event": "COMMENT", "commit_id": commit}, f, ensure_ascii=False)
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
    print(f"  {recorded}")
    return 0


def main() -> int:
    common.apply_project_env("post-review")
    try:
        return run(sys.argv[1:], common.read_body)
    except Refused as e:
        say(f"post-review: {e}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
