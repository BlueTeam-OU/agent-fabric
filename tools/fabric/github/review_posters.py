"""tools/fabric/github/review_posters.py — whose marked review counts as the PR's blind review: the PR's author,
the logins AGENT_FABRIC_REVIEW_POSTERS names, and, on a PR an app opened (Dependabot), the account this session
pushes and posts as.

Every session pushes and posts as one account, the author of every PR a session opens, so on those the author is
the poster and the configured list stays empty. A bot's PR has no session for an author: the blind review is posted
by the push account, and with the author rule alone it read "marked, other login", not coverage (agent-fabric #408
and #409 armed on 2026-11-01 only with the list set by hand). The push account is whom `gh` acts as here, read from
GitHub, never typed: an account other than the fleet's that runs these tools trusts only its own posts, which is
what it already does on the PRs it authors. One reader for every gate (pr-review-status, the review checkpoint,
arm's gate 4c, pr-counts), so a review that counts in one is not unread in another."""
from __future__ import annotations

import os
import sys
from typing import Callable

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
import gh  # noqa: E402


def is_bot(author: object) -> bool:
    """Whether a PR's author, as any of the three reads spells it, is an app: `gh pr view` gives
    {"login": "app/dependabot", "is_bot": true}, REST {"login": "dependabot[bot]", "type": "Bot"}, GraphQL
    {"__typename": "Bot", "login": "dependabot"} (that last login alone is a user's shape, so the query asks the
    type). A shape not recognised is a person's PR: the rule that held before."""
    if not isinstance(author, dict):
        return False
    login = author.get("login")
    login = login if isinstance(login, str) else ""
    return (author.get("is_bot") is True or author.get("type") == "Bot" or author.get("__typename") == "Bot"
            or login.startswith("app/") or login.endswith("[bot]"))


_login: list[str] = []


def push_account(timeout: float | Callable[[], float] = gh.TIMEOUT_S) -> str:
    """The login `gh` acts as, asked of GitHub within `timeout` (a caller's budget, pr-counts' `--timeout`; a callable is
    read only when GitHub is asked, so a budget spent by a later call does not stop one that asks nothing). gh.GhError
    when GitHub cannot say: never "" taken as nobody, which would read the bot PR's blind review as another login's
    and say so as a fact. Read once per process: the login is kept apart from the timeout, which a cache keyed on the
    arguments would ask again under every budget left; a failure is not kept, so the next call asks again."""
    if not _login:
        who = gh.api("user", timeout=timeout() if callable(timeout) else timeout)
        login = who.get("login") if isinstance(who, dict) else None
        if not isinstance(login, str) or not login:
            raise gh.GhError("gh api GET user", "the answer names no login")
        _login.append(login)
    return _login[0]


# The suites script several accounts in one process, and forget the login between them by this name.
push_account.cache_clear = _login.clear  # type: ignore[attr-defined]


def for_pr(author: object, configured, timeout: float | Callable[[], float] = gh.TIMEOUT_S) -> list[str]:
    """The posters besides the author for a PR whose author is `author` (its author object, as read): the
    configured logins, and the push account when an app opened the PR, asked within `timeout`."""
    posters = list(configured)
    if is_bot(author):
        me = push_account(timeout)
        if me not in posters:
            posters.append(me)
    return posters
