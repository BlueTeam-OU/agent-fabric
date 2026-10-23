"""tools/fabric/github/review_checkpoint.py — where the next review of a PR starts (agent-fabric ADR-065 §2 C, §5 rule 5).

    last_checkpoint(pr, current_head, config_for) -> (base, head, card) | None

for review_brief, which derives `card_base` and the re-review's base from it. The answer is the range of the newest v2
review on the PR when EVERY check holds, and None, a full review, on any doubt: the review is not by an account
pr_review_status trusts (the PR's author or AGENT_FABRIC_REVIEW_POSTERS), its marker or block does not read, a path
is "not read" (a partial review is no checkpoint: the paths it skipped would never be read), its marker names another
commit than it is on, its head is not a commit of the PR or not an ancestor of `current_head` (a force-push), its
base is not an ancestor of its head, its config differs from `config_for(its card)`, or any lookup failed. Never a
default: an API error is not "no review yet", it is "not known", which the caller reads as a full review.

NEWEST means newest by submission time among the trusted v2 reviews, and the newest one decides: when it fails a
check there is no fallback to an older one (two reviews with the same time are a doubt too). v1 reviews are never a
checkpoint, and a v2 marker from any other account is not read at all.

`config_for` is the caller's: an exception it raises is not caught here (it is a bug of the caller's, not a doubt about the PR).
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import gh  # noqa: E402
from github import review_coverage  # noqa: E402
from github.review_status.base import Die, jkey, login_of  # noqa: E402
from github.review_status.config import read_config  # noqa: E402

# GitHub lists at most 250 commits of a pull request: a list that long may be cut, and a head not found in a cut
# list proves nothing (post_review.COMMIT_LIST_CAP).
COMMIT_LIST_CAP = 250


def last_checkpoint(pr: int | str, current_head: str, config_for, *, repo: str | None = None, cwd: str | None = None,
                    environ=None) -> tuple[str, str, str] | None:
    """`config_for(card)` is the config fingerprint today for a project card read at `card`; `cwd` is a clone that
    holds the PR's commits (the ancestry questions are asked there); `repo` is owner/name, the working copy's when
    omitted."""
    try:
        return _checkpoint(int(pr), current_head, config_for, repo, cwd or os.getcwd(),
                           os.environ if environ is None else environ)
    except (gh.GhError, Die, review_coverage.CoverageError, ValueError, TypeError, AttributeError, KeyError, OSError):
        return None


def _checkpoint(pr: int, current_head: str, config_for, repo: str | None, cwd: str, environ):
    repo = repo or gh.this_repo(cwd)
    cfg = read_config(environ)
    meta = gh.pr_view(pr, ["author"], repo=repo)
    author = (meta.get("author") or {}).get("login")
    if not isinstance(author, str) or not author:
        return None
    reviews = gh.api_list(f"repos/{repo}/pulls/{pr}/reviews")
    posted = [r for r in reviews if isinstance(r, dict) and (r.get("body") or "").startswith(review_coverage.V2_PREFIX)
              and (login_of(r) == author or login_of(r) in cfg.review_posters)]
    if not posted:
        return None
    ordered = sorted(posted, key=lambda r: jkey(r.get("submitted_at")))
    newest = ordered[-1]
    if newest.get("submitted_at") is None or (len(ordered) > 1 and ordered[-2].get("submitted_at") == newest["submitted_at"]):
        return None
    v2 = review_coverage.read_review(newest.get("body") or "")
    if v2 is None or not v2.counts:
        return None
    marker = v2.marker
    if newest.get("commit_id") != marker.head:
        return None
    commits = gh.api_list(f"repos/{repo}/pulls/{pr}/commits")
    if len(commits) >= COMMIT_LIST_CAP or not any(isinstance(c, dict) and c.get("sha") == marker.head for c in commits):
        return None
    if not review_coverage.is_ancestor(cwd, marker.head, current_head):
        return None
    if not review_coverage.is_ancestor(cwd, marker.base, marker.head):
        return None
    if config_for(marker.card) != marker.config:
        return None
    return marker.base, marker.head, marker.card
