#!/usr/bin/env python3
"""tools/fabric/github/arm.py — arm auto-merge on a pull request with the
gates the managed projects put before the arming applied by the tool, not
by memory (ADR-019's count rule; runtime/github/arm.sh is its shim, and
the managed projects' tools/gh/arm.sh forward to that path). Ported from
the first managed project's tools/gh/arm.sh, whose test is the oracle
(ADR-040 §5 rules 3–5); what was that project's own — the security-boundary paths and the classes that
arm under the floor without asking — is now the project's arm.json.

CONTRACT, frozen from the bash (ADR-040 §5 rule 3):
  argv      <pr-number> --basis "<one line>" [--boundary | --no-boundary "<why>"]
            [--any-owner] [--dry-run] [-h|--help]
  env       AGENT_FABRIC_PR_GATE (the count reader, run as a program),
            AGENT_FABRIC_PR_REVIEW_STATUS (the review reader, run as a
            program), AGENT_FABRIC_PR_SESSION (<host>/<login>),
            AGENT_FABRIC_ARM_CONFIG (an arm.json used instead of the
            project's), AGENT_FABRIC_ROOT
  stdout    `arm: ` lines — what each gate found, and the watcher line
  stderr    `arm: REFUSED #N — <why>` on a refusal; `arm: <why>` when a
            question could not be answered, or on a usage error
  exit      0 armed (or, with --dry-run, would arm); 1 refused — the
            reason is the last line; 2 gh / pr-gate / pr-review-status /
            the project's arm.json could not answer, or usage

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
from github import local, pr_gate  # noqa: E402

FABRIC = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
RUNTIME = os.path.join(FABRIC, "runtime", "github")

HELP = """Arm auto-merge on a PR — with the gates the project puts before the
arming applied by the tool, not by memory.

  tools/gh/arm.sh <pr-number> --basis "<one line>" [options]

What it refuses, in order, and why:
  1. a PR that is not OPEN, or is a draft;
  2. another session's PR — the head branch's <host>/<login> prefix
     is not this session's (the lane rule: never arm, retarget or
     merge a PR you did not open; --any-owner overrides, for the
     owner's own hand);
  3. a body that names an AWAITING-SUPPLY with no range line for that
     login — supply asked for and not folded (owed-supply.sh lists
     these; the caller arms never with its own REQUEST unanswered);
  4. a SECURITY-BOUNDARY change without the REVIEW CLASS'S review of
     the CURRENT head, or with an unresolved review thread, or without
     the owner's word. Read from pr-review-status.sh --json: a
     `blind.rows` entry whose commit_sha8 is the head, and
     `unresolved_threads` 0 ("no open P1 or P2"); a missing field or a
     null count is exit 2, never a pass. Its exit status is NOT the
     gate: exit 0 means ANY counted review, an empty thread-reply review
     included. The boundary is read from the changed files against the
     project's patterns (projects/<id>/integration/gh/arm.json in
     agent-fabric). --boundary forces the gate on, --no-boundary
     <reason> waives it and records the reason in the arming comment;
  5. the count rule (pr-gate.sh's classifier): 8–16 arms at the review
     gate; over 16 is ADVICE for the next batch, never a refusal; under
     8 is armed on the owner's word — the --basis must carry the phrase
     "owner's word" — EXCEPT a class the project's arm.json lets arm at
     the gate (none, in a project that declares none), STATED in the PR body
     ("Class: <class>") and confirmed by the changed files; a stated
     class the files contradict is refused, not trusted.

Then: posts the arming basis as a comment ("Arming basis: <text> —
<W> work commits, head <sha>"), runs `gh pr merge --merge --auto`,
and prints the watcher line to run — it is not started here, because
a watcher must be the SESSION's child for its exit to be the
session's callback.

Options:
  --basis "<text>"      required: the one-line arming basis
  --boundary            treat as a security-boundary change regardless of paths
  --no-boundary "<why>" waive the boundary gate; the reason goes in the comment
  --any-owner           arm a PR whose branch is not this session's
  --dry-run             evaluate every gate, arm nothing, post nothing

Exit codes:
  0  armed (or, with --dry-run, would arm)
  1  refused — the reason is the last line
  2  gh / pr-gate / pr-review-status / arm.json could not answer, or usage

Environment: AGENT_FABRIC_PR_GATE, AGENT_FABRIC_PR_REVIEW_STATUS,
AGENT_FABRIC_PR_SESSION, AGENT_FABRIC_ARM_CONFIG."""


class Refused(Exception):
    """Gate refusal: exit 1."""


class Unanswered(Exception):
    """A question nobody could answer, or usage: exit 2."""


def say(msg: str) -> None:
    print(f"arm: {msg}", flush=True)


def has_owner_word(basis: str) -> bool:
    # A fixed phrase, not any sentence with "owner" in it ("the owner has
    # not been asked yet" is not consent — a managed project's PR #894 review): straight
    # or curly apostrophe.
    return re.search(r"owner('|’)s word", basis, re.I) is not None


def head_lines(lines: list[str], n: int = 3) -> str:
    """The first n, as `head -3 | tr '\\n' ' '` wrote them."""
    return "".join(f"{l} " for l in lines[:n])


# ── the project's rules ──────────────────────────────────────────────

def config_path() -> str:
    explicit = os.environ.get("AGENT_FABRIC_ARM_CONFIG", "")
    if explicit:
        return explicit
    top = local.toplevel()
    if not top:
        return ""
    try:
        import workingcopy
        pid = workingcopy.resolve(top).get("project")
    except (Exception, SystemExit):   # a marker naming nothing the registry knows exits
        pid = None
    fabric = os.environ.get("AGENT_FABRIC_ROOT") or FABRIC
    return os.path.join(fabric, "projects", pid, "integration", "gh", "arm.json") if pid else ""


def load_config(path: str) -> tuple[re.Pattern, re.Pattern | None, dict[str, re.Pattern]]:
    if not path:
        raise Unanswered("no project found for this working copy, so no arm.json to read the security boundary from"
                         " (projects/<id>/integration/gh/arm.json in agent-fabric, or AGENT_FABRIC_ARM_CONFIG)")
    try:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
        b = doc["boundary"]
        paths = re.compile(b["paths"], re.I)
        exempt = re.compile(b["exempt"]) if b.get("exempt") else None
        classes = {str(k).lower(): re.compile(v) for k, v in (doc.get("classes") or {}).items()}
        # The project's own statement of what must stay boundary: a case the
        # patterns no longer match is a boundary narrowed by mistake, and
        # arming on it would judge with rules the project did not mean
        # (lint holds the same, and that no case is dropped unretired).
        missed = [c for c in (b.get("cases") or []) if (exempt and exempt.search(c)) or not paths.search(c)]
    except FileNotFoundError:
        raise Unanswered(f"this project declares no arm.json ({path}); the security boundary cannot be judged") from None
    except (OSError, ValueError, KeyError, TypeError, AttributeError, re.error) as e:
        raise Unanswered(f"{path} is not a usable arm.json ({type(e).__name__}: {e})") from None
    if missed:
        raise Unanswered(f"{path}: boundary case(s) not boundary under its own patterns — {', '.join(missed[:3])}"
                         " — the security boundary cannot be judged")
    return paths, exempt, classes


# ── readers run as programs: the seams the oracle mocks ──────────────

def program(env: str, default: str) -> str:
    return os.environ.get(env) or default


def run_reader(path: str, args: list[str]) -> tuple[int, str]:
    try:
        r = subprocess.run([path, *args], capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=600)
    except OSError:
        return 127, ""
    except subprocess.TimeoutExpired:
        return 124, ""
    return r.returncode, r.stdout


# ── the gates ────────────────────────────────────────────────────────

def unmet_supply(body: str) -> list[str]:
    """Each AWAITING-SUPPLY login with no `<sha>..<sha>: <login>` range
    line in the body — the reading owed-supply.sh makes."""
    out = []
    for line in body.split("\n"):
        m = re.match(r"^\s*-?\s*AWAITING-SUPPLY:\s*(\S+)", line)
        if not m:
            continue
        who = m.group(1).split("/")[-1]
        if not re.search(r"[0-9a-f]{7,40}\.\.[0-9a-f]{7,40}:\s*" + re.escape(who) + r"([^A-Za-z0-9_-]|$)", body):
            out.append(who)
    return out


def stated_class(body: str, classes: dict[str, re.Pattern]) -> str:
    if not classes:
        return ""
    names = "|".join(re.escape(c) for c in sorted(classes, key=len, reverse=True))
    for line in body.split("\n"):
        m = re.match(r"^[\s*_-]*Class:[\s*_]*(" + names + ")", line, re.I)
        if m:
            return m.group(1).lower()
    return ""


def arm(argv: list[str]) -> int:
    num = basis = no_boundary = ""
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
        repo = gh.run(["repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"], what="gh repo view").strip()
    except gh.GhError:
        repo = ""
    if not repo:
        raise Unanswered("cannot read the repository (gh repo view failed)")
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
    boundary_re, exempt_re, classes = load_config(config_path())

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
    if is_boundary:
        if no_boundary:
            say(f"boundary gate WAIVED: {no_boundary}")
        else:
            rc, out = run_reader(program("AGENT_FABRIC_PR_REVIEW_STATUS", os.path.join(RUNTIME, "pr-review-status.sh")),
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
                             f" review class on {head} and post with tools/gh/post-review.sh, then arm (an independent"
                             f" or automated review does not count here)")
            if not isinstance(unresolved, int) or isinstance(unresolved, bool):
                raise Unanswered(f"pr-review-status reported no unresolved_threads count for #{num} (null: the lookup"
                                 f" failed) — cannot judge the open findings")
            if unresolved != 0:
                raise refuse(f"a security-boundary change with {unresolved} unresolved review thread(s): answer and"
                             f" resolve them first (no open P1 or P2)")
            say(f"the current head {head} has the review class's review, and no unresolved thread")
            # …AND the owner's word, whatever the count.
            if not has_owner_word(basis):
                raise refuse("a security-boundary change arms only on the owner's word as well as the review"
                             " (CLAUDE.md §A security-boundary change), and the basis does not carry the phrase"
                             " \"owner's word\"")

    # 5. the count rule, from pr-gate's classifier
    rc, out = run_reader(program("AGENT_FABRIC_PR_GATE", os.path.join(RUNTIME, "pr-gate.sh")), ["--json", num])
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
    # Over 16 is advice for the NEXT batch, never a gate at arming time
    # nor a reorganisation of the open PR (the owner, 2026-09-19).
    if work > 16:
        say(f"{work} work commits — over 16: smaller batches next time; arming on the basis given")
    cls = stated_class(body, classes)
    if cls:
        offlist = [f for f in files if not classes[cls].search(f)]
        if offlist:
            raise refuse(f"the body states Class: {cls} but the changed files are not that class — {head_lines(offlist)}")
        say(f"class stated and confirmed by the files: {cls}")
    if work < 8 and not cls and not has_owner_word(basis):
        gate_classes = " / ".join(f"Class: {c}" for c in classes) or "none in this project"
        raise refuse(f"{work} work commits — under 8 arms only on the owner's word, unless the body states a class"
                     f" that arms at the gate ({gate_classes}) and the files agree; the basis does not carry the"
                     f" phrase \"owner's word\" and no class is stated")
    if work < 8:
        say(f"count rule: {work} work commits — under 8, arms at the gate as {cls}" if cls
            else f"count rule: {work} work commits — under 8, on the owner's word")
    elif work <= 16:
        say(f"count rule: {work} work commits — in the 8–16 band")

    comment = f"Arming basis: {basis} — {work} work commits{f', class: {cls}' if cls else ''}, head {head[:8]}."
    if no_boundary:
        comment += f" Boundary gate waived: {no_boundary}."
    if dry:
        say(f"DRY RUN — would post: {comment}")
        say(f"DRY RUN — would run: gh pr merge {num} --merge --auto")
        return 0
    # The body on stdin: a body is data (gh.py's invariant).
    try:
        gh.run(["pr", "comment", num, "--body-file", "-"], input=comment, what=f"gh pr comment {num}")
    except gh.GhError:
        raise Unanswered(f"could not post the basis comment on #{num}") from None
    try:
        gh.run(["pr", "merge", num, "--merge", "--auto"], what=f"gh pr merge {num}")
    except gh.GhError:
        raise Unanswered(f"gh pr merge --auto failed on #{num}") from None
    # A green PR goes STRAIGHT INTO THE QUEUE on arming, and a queued PR
    # reads autoMergeRequest null — exactly like an unarmed one (a managed project's PR
    # #881). So the read-back is the queue entry OR the arming.
    try:
        d = gh.graphql("query($o:String!,$n:String!,$num:Int!){repository(owner:$o,name:$n){pullRequest(number:$num)"
                       "{autoMergeRequest{enabledAt} mergeQueueEntry{position}}}}", o=owner, n=name, num=int(num))
        p = d["repository"]["pullRequest"]
        armed = (f"queued at {p['mergeQueueEntry']['position']}" if p.get("mergeQueueEntry")
                 else "armed" if p.get("autoMergeRequest") else "idle")
    except (gh.GhError, KeyError, TypeError):
        armed = "unknown"
    if armed not in ("armed",) and not armed.startswith("queued"):
        raise Unanswered(f"#{num} reads '{armed}' after gh pr merge --auto — check gh pr view {num}")
    say(f"ARMED #{num} ({title}) — {armed}; basis posted.")
    say(f"now, in the session: tools/gh/wait-merged.sh {num} &")
    return 0


def main(argv: list[str]) -> int:
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
