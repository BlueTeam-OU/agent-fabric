#!/usr/bin/env python3
"""Tests for tools/fabric/github/review_checkpoint.py: last_checkpoint, where the next review of a PR starts (agent-fabric
ADR-065 §5 rule 5). A real git repository in a scratch directory for the ancestry; gh scripted, no network. One case per
doubt that must read as "a full review" (None), with the positive control it departs from."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from unittest import mock

from git_env import git_env, scrub_process_env  # noqa: E402 — tests/, the script's own directory
from instance_fixtures import own_instance_tree  # noqa: E402 — tests/, the script's own directory
own_instance_tree()
scrub_process_env()

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
import gh  # noqa: E402
from github import review_checkpoint as cp  # noqa: E402
from github import review_coverage as rcov  # noqa: E402

CARD, CONFIG = "5" * 40, "6" * 64


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: object = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good else f": {str(detail)[:600]}"))
        fails += not good

    with tempfile.TemporaryDirectory() as tmp:
        env = git_env()

        def git(*args: str) -> str:
            r = subprocess.run(["git", "-C", tmp, "-c", "user.name=t", "-c", "user.email=t@t", *args],
                               capture_output=True, text=True, env=env, timeout=60)
            if r.returncode:
                raise RuntimeError(f"git {args}: {r.stderr}")
            return r.stdout.strip()

        def commit(name: str) -> str:
            with open(os.path.join(tmp, name), "w", encoding="utf-8") as f:
                f.write(name)
            git("add", "-A")
            git("commit", "-q", "-m", name)
            return git("rev-parse", "HEAD")

        git("init", "-q", "-b", "main")
        c0 = commit("c0")
        c1 = commit("c1")
        c2 = commit("c2")
        git("checkout", "-q", "-b", "forced", c0)
        forced = commit("forced")
        git("checkout", "-q", "main")
        elsewhere = tempfile.mkdtemp(dir=tmp)
        subprocess.run(["git", "-C", elsewhere, "init", "-q"], check=True, env=env, timeout=30)

        def body(base: str = c0, head: str = c1, statuses=("read",), marker: str | None = None, blocks: int = 1) -> str:
            m = marker or f"<!-- agent-fabric-review v2 base={base} head={head} card={CARD} config={CONFIG} -->"
            paths = {f"p{i}": ({"status": s} if s == "read" else {"status": s, "reason": "r"}) for i, s in enumerate(statuses)}
            block = f"```{rcov.BLOCK_INFO}\n{json.dumps({'paths': paths, 'lenses': {}})}\n```\n" * blocks
            return f"{m}\n**Blind review**\n\n{block}"

        def rv(text: str, *, login: str = "me", commit_id: str = c1, at: str | None = "2026-10-23T10:00:00Z") -> dict:
            return {"user": {"login": login}, "commit_id": commit_id, "submitted_at": at, "body": text}

        seen: list[str] = []

        def config_for(card: str) -> str:
            seen.append(card)
            return CONFIG

        def ask(reviews, *, current=c2, listed=None, cfg=config_for, author="me", cwd=tmp, environ=None, pr_error=None,
                list_error=None, commits_error=None):
            commits = [{"sha": c} for c in (listed if listed is not None else (c1, c2))]

            def api_list(path, **kw):
                if "/commits" in path:
                    if commits_error:
                        raise commits_error
                    return commits
                if list_error:
                    raise list_error
                return reviews

            def pr_view(number, fields, **kw):
                if pr_error:
                    raise pr_error
                return {"author": {"login": author}}

            with mock.patch.object(cp.gh, "api_list", api_list), mock.patch.object(cp.gh, "pr_view", pr_view):
                return cp.last_checkpoint(7, current, cfg, repo="o/r", cwd=cwd, environ={} if environ is None else environ)

        print("last_checkpoint: the newest complete v2 review of the author, whose head the PR still holds")
        check("the control: (base, head, card) of the review", ask([rv(body())]) == (c0, c1, CARD))
        check("config_for is asked with the marker's own card", seen[-1] == CARD, seen)
        check("a review of the current head is a checkpoint too", ask([rv(body())], current=c1) == (c0, c1, CARD))
        check("the newest of several decides", ask([rv(body(c0, c1), at="2026-10-23T09:00:00Z"),
                                                    rv(body(c1, c2), commit_id=c2, at="2026-10-23T11:00:00Z")], listed=(c1, c2)) == (c1, c2, CARD))
        check("a named poster counts", ask([rv(body(), login="ci")], environ={"AGENT_FABRIC_REVIEW_POSTERS": '["ci"]'}) == (c0, c1, CARD))

        print("last_checkpoint: any doubt is a full review")
        check("no review at all", ask([]) is None)
        check("a v1 review is never a checkpoint", ask([rv("<!-- agent-fabric-review v1 -->\nx")]) is None)
        check("a v2 marker from another account is not read", ask([rv(body(), login="rando")]) is None)
        check("…and does not hide the author's older one", ask([rv(body(), at="2026-10-23T09:00:00Z"),
                                                                rv(body(c1, c2), login="rando", commit_id=c2, at="2026-10-23T11:00:00Z")]) == (c0, c1, CARD))
        check("the marker is read only as the first line", ask([rv("findings\n" + body())]) is None)
        check("a partial review is no checkpoint", ask([rv(body(statuses=("read", "not read")))]) is None)
        check("…and the newest being partial does not fall back to an older complete one",
              ask([rv(body(c0, c1), at="2026-10-23T09:00:00Z"),
                   rv(body(c1, c2, ("not read",)), commit_id=c2, at="2026-10-23T11:00:00Z")], listed=(c1, c2)) is None)
        check("an unreadable marker", ask([rv(body(marker=f"<!-- agent-fabric-review v2 base={c0} head={c1} -->"))]) is None)
        check("two coverage blocks", ask([rv(body(blocks=2))]) is None)
        check("no coverage block", ask([rv(body().split("```")[0])]) is None)
        check("a marker naming another head than the review is on", ask([rv(body(), commit_id=c2)]) is None)
        check("a head that is not a commit of the PR", ask([rv(body())], listed=(c2,)) is None)
        check("a commit list GitHub may have cut", ask([rv(body())], listed=[c1] + [f"{i:040x}" for i in range(cp.COMMIT_LIST_CAP)]) is None)
        check("a force-push: the head is no ancestor of the PR's head now", ask([rv(body())], current=forced) is None)
        check("a base that is not an ancestor of the head", ask([rv(body(base=forced))]) is None)
        check("a config that changed since", ask([rv(body())], cfg=lambda card: "7" * 64) is None)
        check("a review without a submission time", ask([rv(body(), at=None)]) is None)
        check("two reviews at the same time: which is newest is unknown",
              ask([rv(body(c0, c1)), rv(body(c1, c2), commit_id=c2)], listed=(c1, c2)) is None)
        check("a clone that lacks the commits", ask([rv(body())], cwd=elsewhere) is None)
        check("a bad poster list in the environment", ask([rv(body())], environ={"AGENT_FABRIC_REVIEW_POSTERS": "nope"}) is None)
        err = gh.GhError("gh api", "HTTP 502", 502, True)
        check("an API error reading the PR", ask([rv(body())], pr_error=err) is None)
        check("an API error reading the reviews", ask([rv(body())], list_error=err) is None)
        check("an API error reading the commits", ask([rv(body())], commits_error=err) is None)
        check("a PR with no author login", ask([rv(body())], author="") is None)
        check("a review list that is not reviews", ask(["x", None, 3]) is None)

    print(f"\ntest_review_checkpoint: {'OK' if not fails else f'FAILED — {fails} check(s)'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
