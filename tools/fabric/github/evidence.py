"""tools/fabric/github/evidence.py — the one reader of a pull request's file and commit lists (owner's rule of
2026-11-08: one owner per cross-cutting mechanism).

    ev = PrEvidence(repo, number)
    ev.files()     -> list of GitHub's file objects, or Incomplete
    ev.commits()   -> list of GitHub's commit objects, or Incomplete
    ev.has_commit(sha) -> True, False, or Incomplete

GitHub lists at most common.PR_FILE_LIST_CAP files and common.PR_COMMIT_LIST_CAP commits of a pull request, paginated
or not, and stops there WITHOUT an error. A list of exactly the cap length may therefore be the first part of a longer
one, and a gate judged on it judges a part of the change (external review F08: arm read 3000 docs paths as a
docs-only change). So a list is returned only when it is shorter than its cap; at the cap the answer is Incomplete,
which no caller can iterate, index or take the length of by mistake, and which says how it came about.

A list that cannot be read is gh.GhError, as for any gh call (including an answer that is not a list of objects):
unreadable and incomplete are kept apart, and neither becomes an empty list. The result is memoised per instance,
which is one pull request read at one moment; a caller that needs a later moment makes a new PrEvidence.

`polled=True` reads the commits through gh.api_list, whose conditional request is free of the rate limit while the list
has not changed (review_checkpoint polls it); the answer is the same list."""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
import gh  # noqa: E402
from github import common  # noqa: E402


@dataclass(frozen=True)
class Incomplete:
    """A list GitHub may have cut: it came back as long as GitHub's cap for it, `cap`."""
    what: str      # "files" or "commits"
    count: int
    cap: int

    @property
    def reason(self) -> str:
        return f"{self.count} {self.what}, GitHub's cap: the list may be cut"


class PrEvidence:
    def __init__(self, repo: str, number: int | str):
        self.repo, self.number = repo, number
        self._read: dict[str, list[dict] | Incomplete] = {}
        self._items: dict[str, list[dict]] = {}

    def files(self, *, timeout: float | None = None) -> list[dict] | Incomplete:
        return self._list("files", common.PR_FILE_LIST_CAP, False, timeout)

    def commits(self, *, timeout: float | None = None, polled: bool = False) -> list[dict] | Incomplete:
        return self._list("commits", common.PR_COMMIT_LIST_CAP, polled, timeout)

    def has_commit(self, sha: str) -> bool | Incomplete:
        """Whether sha is a commit of the pull request. A sha found is found even in a list GitHub cut (what is listed is
        listed); one not found is False only from a whole list, else Incomplete: it may be in the part not shown."""
        listed = self.commits()
        if any(c.get("sha") == sha for c in self._items["commits"]):
            return True
        return listed if isinstance(listed, Incomplete) else False

    def _list(self, what: str, cap: int, polled: bool, timeout: float | None) -> list[dict] | Incomplete:
        if what in self._read:
            return self._read[what]
        path = f"repos/{self.repo}/pulls/{self.number}/{what}"
        kw = {} if timeout is None else {"timeout": timeout}
        listed = gh.api_list(path, **kw) if polled else gh.api(f"{path}?per_page=100", paginate=True, **kw)
        if not isinstance(listed, list) or not all(isinstance(x, dict) for x in listed):
            raise gh.GhError(f"gh api GET {path}", "the answer is not a list of objects")
        self._items[what] = listed
        self._read[what] = Incomplete(what, len(listed), cap) if len(listed) >= cap else listed
        return self._read[what]
