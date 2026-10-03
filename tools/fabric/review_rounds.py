#!/usr/bin/env python3
"""tools/fabric/review_rounds.py — the rounds of one PR's blind review, so a
re-review's brief comes from what was saved, never from editing the last
request by hand (bin/fabric-review save | next).

    review_rounds.py save PR ROUND [--repo NAME]  < report
    review_rounds.py next REQUEST (--report FILE | --pr PR [--repo NAME])
                          [--head REV] [--keep-lenses]

`save` keeps a round's report as <state>/agents/<login>/reviews/<repo>/
pr-<PR>/round-<ROUND>.md, 0600 in a 0700 directory: a report quotes the
change, and the account's state is its own. <repo> is the working copy's
directory name unless --repo names it, since PR numbers repeat across
repositories.

`next` reads the previous round's request and writes the re-review's
beside it, REQUEST-rr<N>.json (JSON, which the brief reader takes as it
is), then prints the rendered brief:
  mode               re-review
  range              the previous range's head .. HEAD of the request's
                     repository (or --head), both resolved to commits
  previous_findings  --report, or the newest round saved for --pr
  lenses             [general], unless --keep-lenses
Everything else is carried over unchanged. It refuses when the head has
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

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "runtime"))
import identity  # noqa: E402
import review_brief  # noqa: E402

ROUND_RE = re.compile(r"^round-(\d+)\.md$")


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
    os.makedirs(d, mode=0o700, exist_ok=True)
    path = os.path.join(d, f"round-{rnd}.md")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(report)
    return path


def newest_round(repo: str, pr: str) -> str:
    d = rounds_dir(repo, pr)
    try:
        found = [(int(m.group(1)), n) for n in os.listdir(d) if (m := ROUND_RE.match(n))]
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


def _next_path(request_path: str) -> str:
    """REQUEST-rr<N>.json beside the first request, N one past the highest
    already there, whichever round's request this is."""
    d, name = os.path.split(os.path.abspath(request_path))
    stem = re.sub(r"-rr\d+$", "", os.path.splitext(name)[0])
    taken = [int(m.group(1)) for n in os.listdir(d) if (m := re.fullmatch(re.escape(stem) + r"-rr(\d+)\.json", n))]
    return os.path.join(d, f"{stem}-rr{max(taken, default=1) + 1}.json")


def next_request(request_path: str, report: str, head: str | None, keep_lenses: bool) -> tuple[str, dict]:
    with open(request_path, encoding="utf-8") as f:
        req = review_brief.parse_request(f.read())
    if not req.get("range"):
        raise Refused(f"{request_path} has no range: a re-review follows a ranged review")
    repo_dir = req["repository"]
    old_head = _commit(repo_dir, req["range"].split("..", 1)[1])
    new_head = _commit(repo_dir, head or "HEAD")
    if new_head == old_head:
        raise Refused(f"the head has not moved since {old_head[:12]}: nothing to re-review")
    if not os.path.isfile(report):
        raise Refused(f"no report at {report}")
    nxt = dict(req)
    nxt["mode"] = "re-review"
    nxt["range"] = f"{old_head[:12]}..{new_head[:12]}"
    nxt["previous_findings"] = os.path.abspath(report)
    if not keep_lenses:
        nxt["lenses"] = ["general"]
    problems = review_brief.validate(nxt)
    if problems:
        raise Refused("the re-review request does not validate:\n  " + "\n  ".join(problems))
    path = _next_path(request_path)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(nxt, f, indent=2)
        f.write("\n")
    return path, nxt


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
            path = save(_pr(args[0]), args[1], sys.stdin.read(), _repo_name(repo))
            print(path)
            return 0
        if cmd == "next":
            report, pr, repo, head = (_flag(args, f) for f in ("--report", "--pr", "--repo", "--head"))
            keep = "--keep-lenses" in args
            args = [a for a in args if a != "--keep-lenses"]
            if len(args) != 1 or bool(report) == bool(pr) or (repo and not pr):
                print("usage: fabric-review next REQUEST (--report FILE | --pr PR [--repo NAME]) [--head REV] "
                      "[--keep-lenses]", file=sys.stderr)
                return 2
            if pr:
                report = newest_round(_repo_name(repo), _pr(pr))
            path, nxt = next_request(args[0], report, head, keep)
            print(f"fabric-review: wrote {path}", file=sys.stderr)
            sys.stdout.write(review_brief.render(nxt))
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
