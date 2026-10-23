#!/usr/bin/env python3
"""tools/fabric/review_rounds.py — the rounds of one PR's blind review, so a
re-review's brief comes from what was saved, never from editing the last
request by hand (bin/fabric-review save | next).

    review_rounds.py save PR ROUND [--repo NAME]  < report   (also removes the round's head worktree)
    review_rounds.py next REQUEST (--report FILE | --pr PR [--repo NAME])
                          [--head REV] [--keep-lenses] [--allow-rationale]

`save` keeps a round's report as <state>/agents/<login>/reviews/<repo>/
pr-<PR>/round-<ROUND>.md, written atomically, 0600 under directories
0700 at every level: a report quotes the change, and the account's state
is its own. <repo> is the working copy's directory name unless --repo
names it (for next --pr, the request's repository's), since PR numbers
repeat across repositories.

`next` reads the previous round's request and writes the re-review's
beside it, REQUEST-rr<N>.json (JSON, which the brief reader takes as it
is), then prints the rendered brief:
  mode               re-review
  range              the previous range's head, which must be a commit id,
                     .. HEAD of the request's repository (or --head)
  previous_findings  --report, or the newest round saved for --pr
  lenses             [general], unless --keep-lenses
  card_base          the first round's base, so the card stays the one the
                     first round read (review_brief.py); a symbolic first
                     base is refused unless the request pins card_base
  review_id          kept, else <repository>#<PR> when the PR is known
  review_round       the previous round's number plus one (the first is 1)
  pr                 --pr, where the request names none
Everything else is carried over unchanged. The brief it prints also embeds
the range's exact diff (up to 64 KB; over that, its --stat and a note) and
Locators: each previous finding's path:line at the old head and the same
region at the new (a line map read from the diff), and each hunk's
enclosing symbol where the hunk header names one. They are computed at
render time and are not in REQUEST-rr<N>.json. It refuses when the head has
not moved: there is nothing to re-review.

WHY. A round by hand was: copy the report to a file, edit mode, range,
lenses and previous_findings in the request, render. architect-cto-01
counted 13 such rounds in one session, two lost to a quoting slip in the
edit (request 01a10026, 2026-10-03), and this account did the same
three times that day. The fields a re-review must get right are the ones
a hand edit got wrong; here they are derived.

NOT HERE: composing the review that is posted. Its judgement is the
author's own words on each finding, which a tool assembling them from
reports would write in nobody's name.

exit 0 done; 1 a request, report or repository that cannot be read, or a
head that has not moved; 2 usage.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "runtime"))
import identity  # noqa: E402
import review_brief  # noqa: E402

ROUND_RE = re.compile(r"^round-(\d+)\.md$")
# The opening of a dispatch header block, as post-review reads it (tools/fabric/github/post_review.py).
DISPATCH_FENCE = re.compile(r"^[ \t]*(`{3,}|~{3,})[ \t]*" + re.escape(review_brief.DISPATCH_VERSION) + r"[ \t]*$")
# The embedded diff of a re-review: past this the brief carries the diffstat
# and a note instead, so the brief never costs more than the reviewer would
# pay reading the range (agent-fabric ADR-020).
DIFF_CAP = 64 * 1024
MAX_LOCATORS = 200
# A previous finding names its place as path:line or path:line-line.
FINDING_REF = re.compile(r"(?<![\w./+-])([\w./+-]*[\w+-]\.\w+):(\d+)(?:[-\u2013](\d+))?")
FINDING_NO = re.compile(r"^\s*(?:#+\s*)?\**(\d+)[.):]")
HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@ ?(.*)\Z")


class Refused(Exception):
    pass


def _repo_name(given: str | None) -> str:
    if given:
        name = given
    else:
        top = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, timeout=30)
        if top.returncode != 0:
            raise Refused("not in a working copy: name the repository with --repo")
        name = os.path.basename(top.stdout.strip())
    if not re.fullmatch(r"[A-Za-z0-9._-]+", name) or name in (".", ".."):
        raise Refused(f"--repo {name!r} is not a plain directory name")
    return name


def _pr(value: str) -> str:
    if not re.fullmatch(r"[1-9][0-9]*", value):
        raise Refused(f"PR {value!r} is not a pull request number")
    return value


def rounds_dir(repo: str, pr: str) -> str:
    return os.path.join(identity.agent_state_dir(), "reviews", repo, f"pr-{pr}")


def save(pr: str, rnd: str, report: str, repo: str) -> str:
    if not re.fullmatch(r"[1-9][0-9]*", rnd):
        raise Refused(f"ROUND {rnd!r} is not a round number")
    if not report.strip():
        raise Refused("no report on stdin")
    d = rounds_dir(repo, pr)
    # Every level 0700, not only the last: makedirs gives `mode` to the leaf
    # alone (review of #89). The write is atomic, as every file under the
    # agent's state is: a torn report would become a re-review's findings.
    base = identity.agent_state_dir()
    for level in ("reviews", os.path.join("reviews", repo), os.path.relpath(d, base)):
        os.makedirs(os.path.join(base, level), mode=0o700, exist_ok=True)
        os.chmod(os.path.join(base, level), 0o700)
    path = os.path.join(d, f"round-{rnd}.md")
    identity.atomic_write(path, report, 0o600)
    # The round records its evidence mode (agent-fabric ADR-020 rule 10) beside the report, read from the
    # report's first dispatch header: what a later reader of the round needs to know is whether it covered a
    # committed head. No header, or one that cannot be read, is recorded as such, never guessed.
    identity.atomic_write(os.path.join(d, f"round-{rnd}.json"),
                          json.dumps({"evidence_mode": report_evidence_mode(report)}) + "\n", 0o600)
    return path


def report_header(report: str) -> dict | str | None:
    """The report's first agent-fabric-dispatch header as a dict, "unreadable" when that header is not a JSON
    object, None when the report carries none."""
    lines = report.splitlines()
    for i, line in enumerate(lines):
        m = DISPATCH_FENCE.match(line)
        if not m:
            continue
        close = next((j for j in range(i + 1, len(lines)) if lines[j].strip() == m.group(1)), None)
        try:
            header = json.loads("\n".join(lines[i + 1:close])) if close is not None else None
        except ValueError:
            header = None
        return header if isinstance(header, dict) else "unreadable"
    return None


def report_evidence_mode(report: str) -> str | None:
    """The evidence_mode of the report's first dispatch header, "unreadable" when it cannot be read, None when
    the report carries none."""
    header = report_header(report)
    if not isinstance(header, dict):
        return header
    mode = header.get("evidence_mode")
    return mode if isinstance(mode, str) else "unreadable"


def remove_head_worktree(report: str, repo: str) -> str | None:
    """Remove the head worktree the brief made for this report's round; the path it removed, else None.
    The path is recomputed from repo and the header's head_sha by the function the brief used, never read
    from the report, and removed only when it is a worktree at exactly that head: a directory I did not
    make is not mine to delete. A failed removal warns; the report is already saved."""
    header = report_header(report)
    sha = header.get("head_sha") if isinstance(header, dict) else None
    if not (isinstance(header, dict) and header.get("evidence_mode") == "pinned"
            and isinstance(sha, str) and re.fullmatch(r"[0-9a-f]{40}", sha)):
        return None
    path = review_brief.evidence_path(repo, sha)
    try:
        at = review_brief.worktree_head(path) if os.path.dirname(path) == os.path.join(tempfile.gettempdir(), "fabric-review") else None
        if at != sha:
            # Said, not silent: --repo naming something other than the clone's directory looks here and finds nothing.
            print(f"fabric-review: left {path}: " + ("nothing there" if not os.path.lexists(path) else f"not a worktree at {sha[:12]}"),
                  file=sys.stderr)
            return None
        common = subprocess.run(["git", "-C", path, "rev-parse", "--path-format=absolute", "--git-common-dir"],
                                capture_output=True, text=True, timeout=30)
        gone = subprocess.run(["git", f"--git-dir={common.stdout.strip()}", "worktree", "remove", "--force", path],
                              capture_output=True, text=True, timeout=120) if common.returncode == 0 else common
    except subprocess.TimeoutExpired as exc:
        print(f"fabric-review: warning: could not remove the head worktree {path}: {exc}", file=sys.stderr)
        return None
    if gone.returncode != 0:
        print(f"fabric-review: warning: could not remove the head worktree {path}: {gone.stderr.strip()}", file=sys.stderr)
        return None
    return path


def newest_round(repo: str, pr: str) -> str:
    d = rounds_dir(repo, pr)
    try:
        found = [(int(m.group(1)), n) for n in os.listdir(d) if (m := ROUND_RE.fullmatch(n))]
    except FileNotFoundError:
        found = []
    if not found:
        raise Refused(f"no round saved for {repo} PR {pr} (fabric-review save {pr} 1 < report)")
    return os.path.join(d, max(found)[1])


def _commit(repo_dir: str, rev: str) -> str:
    r = subprocess.run(["git", "-C", repo_dir, "rev-parse", "--verify", "-q", f"{rev}^{{commit}}"],
                       capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        raise Refused(f"{rev!r} is not a commit in {repo_dir}")
    return r.stdout.strip()


def _git_out(repo_dir: str, *args: str) -> bytes:
    r = subprocess.run(["git", "-C", repo_dir, "-c", "core.quotepath=off", *args], capture_output=True, timeout=120)
    if r.returncode != 0:
        raise Refused(f"git {' '.join(args[:2])} failed in {repo_dir}: {r.stderr.decode(errors='replace').strip()}")
    return r.stdout


def _line_map(repo_dir: str, old: str, new: str) -> dict[str, dict]:
    """{old path: {"new": new path or None, "hunks": [(a, b, c, d, symbol)]}}
    from `git diff -U0 -M old new`: a hunk replaces old lines a..a+b-1 with
    new lines c..c+d-1 (b == 0: inserted after old line a). -U0 so that a
    hunk is exactly the changed lines, and its header names the symbol git's
    funcname rule finds above them."""
    out = _git_out(repo_dir, "diff", "-U0", "-M", "--no-color", "--no-ext-diff", "--src-prefix=a/", "--dst-prefix=b/", old, new).decode("utf-8", "replace")
    files: dict[str, dict] = {}
    cur: dict | None = None
    in_body = False
    old_path = new_path = None
    for line in out.split("\n"):
        if line.startswith("diff --git "):
            in_body, cur, old_path, new_path = False, None, None, None
        elif not in_body and line.startswith("rename from "):
            old_path = line[len("rename from "):]
        elif not in_body and line.startswith("rename to "):
            new_path = line[len("rename to "):]
            files[old_path] = cur = {"new": new_path, "hunks": []}
        elif not in_body and line.startswith("--- "):
            old_path = None if line == "--- /dev/null" else line[6:]
        elif not in_body and line.startswith("+++ "):
            new_path = None if line == "+++ /dev/null" else line[6:]
            if old_path is not None:
                cur = files.setdefault(old_path, {"new": new_path, "hunks": []})
                cur["new"] = new_path
        elif (m := HUNK_RE.match(line)) and cur is not None:
            in_body = True
            a, b, c, d = (int(m.group(i)) if m.group(i) is not None else 1 for i in (1, 2, 3, 4))
            cur["hunks"].append((a, b, c, d, m.group(5).strip()))
        elif line.startswith("Binary files "):
            in_body = True
    return files


def _locate(files: dict[str, dict], path: str, line: int) -> str:
    """Where old `path:line` is in the new tree, as words."""
    entry = files.get(path)
    if entry is None:
        return f"{path}:{line} (unchanged: the file is not in the range)"
    if entry["new"] is None:
        return "the file is deleted in the range"
    shift = 0
    for a, b, c, d, _ in entry["hunks"]:
        if b > 0 and a <= line < a + b:
            return (f"{entry['new']}:{c}-{c + d - 1} (rewritten in the range)" if d > 0
                    else f"(the line is deleted in the range, at {entry['new']}:{c})")
        if (b > 0 and a + b - 1 < line) or (b == 0 and a < line):
            shift += d - b
        else:
            break
    where = f"{entry['new']}:{line + shift}"
    note = "unchanged" if shift == 0 and entry["new"] == path else f"moved {shift:+d}"
    return f"{where} ({note})"


def _delta(repo_dir: str, old: str, new: str, report: str) -> dict:
    """What a re-review is briefed with besides the findings: the range's
    exact diff, and where each finding's line and each hunk is now, so the
    reviewer answers from the brief and opens a file only when it must."""
    raw = _git_out(repo_dir, "diff", "--no-color", "--no-ext-diff", old, new)
    delta: dict = {}
    if len(raw) <= DIFF_CAP:
        delta["diff"] = raw.decode("utf-8", "replace").rstrip("\n")
    else:
        delta["diff"] = None
        delta["note"] = f"The diff is {len(raw)} bytes, over the {DIFF_CAP}-byte cap, so only its diffstat is embedded."
        delta["stat"] = _git_out(repo_dir, "diff", "--stat", "--no-color", "--no-ext-diff", old, new).decode("utf-8", "replace").rstrip("\n")
    files = _line_map(repo_dir, old, new)
    locators: list[str] = []
    seen: set = set()
    number = None
    with open(report, encoding="utf-8", errors="replace") as f:
        text = f.read()
    for line in text.split("\n"):
        if (m := FINDING_NO.match(line)):
            number = m.group(1)
        for ref in FINDING_REF.finditer(line):
            path, first, last = ref.group(1), int(ref.group(2)), ref.group(3)
            key = (number, path, first, last)
            # A path the old head does not have is prose that looks like a
            # locator (localhost:8080), not a finding's place.
            if key in seen or subprocess.run(["git", "-C", repo_dir, "cat-file", "-e", f"{old}:{path}"],
                                             capture_output=True, timeout=30).returncode != 0:
                continue
            seen.add(key)
            end = f" to {_locate(files, path, int(last))}" if last else ""
            locators.append(f"- finding {number or '?'}: {path}:{first}{'-' + last if last else ''} at {old[:12]} is now "
                            f"{_locate(files, path, first)}{end}")
    symbols = [f"- {entry['new']}:{c}{'-' + str(c + d - 1) if d > 1 else ''}: {sym}"
               for entry in files.values() if entry["new"] for _, _, c, d, sym in entry["hunks"] if sym]
    for lines in (locators, symbols):
        if len(lines) > MAX_LOCATORS:
            lines[MAX_LOCATORS:] = [f"(and {len(lines) - MAX_LOCATORS} more, not listed)"]
    delta["locators"], delta["symbols"] = locators, symbols
    return delta


def _next_path(request_path: str) -> str:
    """REQUEST-rr<N>.json beside the first request, N one past the highest
    already there, whichever round's request this is."""
    d, name = os.path.split(os.path.abspath(request_path))
    stem = re.sub(r"-rr\d+$", "", os.path.splitext(name)[0])
    taken = [int(m.group(1)) for n in os.listdir(d) if (m := re.fullmatch(re.escape(stem) + r"-rr(\d+)\.json", n))]
    return os.path.join(d, f"{stem}-rr{max(taken, default=1) + 1}.json")


def next_request(request_path: str, report: str, head: str | None, keep_lenses: bool,
                 allow_rationale: bool = False, pr: str | None = None) -> tuple[str, dict, str]:
    with open(request_path, encoding="utf-8") as f:
        req = review_brief.parse_request(f.read())
    if not os.path.isfile(report):
        raise Refused(f"no report at {report}")
    # What is validated before the range is split is the request as it will
    # be derived — the new report, re-review, the lenses it will carry — not
    # the source as it stands: the derivation replaces previous_findings and
    # may narrow the lenses, so an earlier report deleted since, or a lens
    # no longer there, must not refuse a chain (review of #89). A range with
    # no `..` still refuses here, as one line (it raised IndexError once).
    # Without the PR: a PR's re-review must start at its last posted review
    # (ADR-065 §5 rule 5), which the SOURCE range no longer does once that
    # round is posted; the derived range is checked when it is rendered.
    shape = {**{k: v for k, v in req.items() if k != "pr"}, "mode": "re-review",
             "previous_findings": os.path.abspath(report)}
    if not keep_lenses:
        shape["lenses"] = ["general"]
    problems = review_brief.validate(shape)
    if problems or not req.get("range"):
        raise Refused(f"{request_path} is not a ranged request that validates: "
                      + ("; ".join(problems) if problems else "a re-review follows a ranged review"))
    repo_dir = req["repository"]
    prev = req["range"].split("..", 1)[1]
    # A symbolic head (HEAD, a remote-tracking ref) resolves to where it is
    # NOW, not to what was reviewed: refused, so a derived range never
    # starts past or at the commits it should cover (review of #89).
    if not re.fullmatch(r"[0-9a-f]{7,40}", prev):
        raise Refused(f"the previous range's head {prev!r} is not a commit id: name the reviewed head as one "
                      "(git rev-parse) in the request")
    old_head = _commit(repo_dir, prev)
    new_head = _commit(repo_dir, head or "HEAD")
    if new_head == old_head:
        raise Refused(f"the head has not moved since {old_head[:12]}: nothing to re-review")
    nxt = dict(req)
    nxt["mode"] = "re-review"
    nxt["range"] = f"{old_head[:12]}..{new_head[:12]}"
    nxt["previous_findings"] = os.path.abspath(report)
    if not keep_lenses:
        nxt["lenses"] = ["general"]
    # What every round of one review shares, and what this round is. The
    # card is the first round's: this range's base is the previous head,
    # which the default branch does not contain (agent-fabric ADR-020).
    if pr and "pr" not in nxt:
        nxt["pr"] = pr
    # A PR's previous report is its last posted review, which the brief reads
    # itself and refuses a typed copy of (ADR-065 §5 rule 5).
    if review_brief._count(nxt.get("pr")):
        nxt.pop("previous_findings", None)
    # A symbolic first base (main, origin/main) resolves to where it is when
    # `next` runs, not where round 1 rendered its card, so round 2 could read
    # another card than round 1: refused unless the request pins card_base.
    first_base = req["range"].split("..", 1)[0]
    if not req.get("card_base") and not re.fullmatch(r"[0-9a-f]{7,40}", first_base):
        raise Refused(f"the range's base {first_base!r} is not a commit id, so the first round's card cannot be "
                      "recovered: set card_base in the request to the commit round 1 used (the base_sha in round 1's dispatch header)")
    nxt["card_base"] = req.get("card_base") or _commit(repo_dir, first_base)
    if (rid := review_brief.default_review_id(nxt)):
        nxt["review_id"] = rid
    nxt["review_round"] = (review_brief._count(req.get("review_round")) or 1) + 1
    problems = review_brief.validate(nxt)
    if problems:
        raise Refused("the re-review request does not validate:\n  " + "\n  ".join(problems))
    # Rendered before it is written: a render that refuses leaves no orphan
    # request for the next attempt to number past (review of #89).
    if (problems := review_brief.refusals(nxt, allow_rationale)):
        raise review_brief.RequestError(problems)
    delta = _delta(repo_dir, old_head, new_head, report)  # before the worktree: it can fail too
    try:
        with review_brief.pinned_evidence(nxt, allow_rationale) as evidence:
            brief = review_brief.render(nxt, allow_rationale=allow_rationale, evidence_path=evidence, delta=delta)
    except review_brief.EvidenceRefused as e:
        raise Refused(str(e))
    path = _next_path(request_path)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(nxt, f, indent=2)
        f.write("\n")
    return path, nxt, brief


def _flag(args: list[str], name: str) -> str | None:
    if name in args:
        i = args.index(name)
        if i + 1 >= len(args):
            raise Refused(f"{name} needs a value")
        val = args[i + 1]
        del args[i:i + 2]
        return val
    return None


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in ("-h", "--help"):
        print(__doc__.split("\n\n")[1])
        return 0 if args else 2
    cmd = args.pop(0)
    try:
        if cmd == "save":
            repo = _flag(args, "--repo")
            if len(args) != 2:
                print("usage: fabric-review save PR ROUND [--repo NAME] < report", file=sys.stderr)
                return 2
            report = sys.stdin.read()
            name = _repo_name(repo)
            path = save(_pr(args[0]), args[1], report, name)
            print(path)
            if (gone := remove_head_worktree(report, name)):
                print(f"fabric-review: removed the head worktree {gone}", file=sys.stderr)
            return 0
        if cmd == "next":
            report, pr, repo, head = (_flag(args, f) for f in ("--report", "--pr", "--repo", "--head"))
            keep, allow = "--keep-lenses" in args, "--allow-rationale" in args
            args = [a for a in args if a not in ("--keep-lenses", "--allow-rationale")]
            if len(args) != 1 or bool(report) == bool(pr) or (repo and not pr):
                print("usage: fabric-review next REQUEST (--report FILE | --pr PR [--repo NAME]) [--head REV] "
                      "[--keep-lenses] [--allow-rationale]", file=sys.stderr)
                return 2
            if pr:
                # The request's own repository, not the cwd's: PR numbers
                # repeat across repositories (review of #89).
                if not repo:
                    with open(args[0], encoding="utf-8") as f:
                        named = review_brief.parse_request(f.read()).get("repository")
                    # A request with no repository, or not a path, is a
                    # refusal, not a KeyError (review of #89).
                    if not isinstance(named, str) or not named.strip():
                        raise Refused(f"{args[0]} names no repository: name the round's with --repo")
                    repo = os.path.basename(os.path.normpath(named))
                report = newest_round(_repo_name(repo), _pr(pr))
            path, _, brief = next_request(args[0], report, head, keep, allow, pr)
            print(f"fabric-review: wrote {path}", file=sys.stderr)
            sys.stdout.write(brief)
            return 0
    except Refused as e:
        print(f"fabric-review: {e}", file=sys.stderr)
        return 1
    except review_brief.RequestError as e:
        print("fabric-review: the request does not render:\n  " + "\n  ".join(e.problems), file=sys.stderr)
        return 1
    except (OSError, ValueError) as e:
        print(f"fabric-review: {e}", file=sys.stderr)
        return 1
    print(f"fabric-review: unknown command {cmd} (save | next)", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
