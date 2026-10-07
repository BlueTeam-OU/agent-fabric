#!/usr/bin/env python3
"""gh.this_repo and the GH_REPO every gh call carries: a working copy's pull
requests are in origin's repository (or GH_REPO's), never gh's default. In
a fork clone gh defaulted to upstream, and a review meant for the fork was
posted on the upstream project's public pull request of the same number
(herdr, 2026-10-07)."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools", "fabric"))
import gh  # noqa: E402

GIT_ENV = {k: v for k, v in os.environ.items() if not k.startswith(("GITHUB_", "GIT_", "GH_"))}
GIT_ENV.update(GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_NOSYSTEM="1")


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: str = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}" + ("" if good or not detail else f"\n        {detail}"))
        fails += not good

    saved = {k: os.environ.get(k) for k in ("GH_REPO", "PATH")}
    os.environ.pop("GH_REPO", None)
    with tempfile.TemporaryDirectory() as tmp:
        wc = os.path.join(tmp, "wc")
        subprocess.run(["git", "init", "-q", wc], check=True, env=GIT_ENV, timeout=30)

        def remote(name: str, url: str) -> None:
            subprocess.run(["git", "-C", wc, "remote", "remove", name], env=GIT_ENV, capture_output=True, timeout=30)
            subprocess.run(["git", "-C", wc, "remote", "add", name, url], check=True, env=GIT_ENV, timeout=30)

        def resolved() -> str:
            try:
                return gh.this_repo(cwd=wc)
            except gh.GhError as e:
                return "ERROR " + e.reason

        print("this_repo: origin's repository on github.com")
        remote("upstream", "https://github.com/upstream-org/project.git")
        check("no origin: refused, never gh's default", resolved().startswith("ERROR "), resolved())
        for url in ("git@github.com:gzapi-org/herdr.git", "https://github.com/gzapi-org/herdr",
                    "https://github.com/gzapi-org/herdr.git/", "ssh://git@github.com/gzapi-org/herdr.git"):
            remote("origin", url)
            check(f"origin {url}: the fork, beside an upstream remote", resolved() == "gzapi-org/herdr", resolved())
        remote("origin", "https://x-access-token:ghs_planted@github.com/gzapi-org/herdr.git")
        check("a credential in origin's URL still resolves", resolved() == "gzapi-org/herdr", resolved())
        remote("origin", "https://x-access-token:ghs_planted@example.com/gzapi-org/herdr.git")
        r = resolved()
        check("origin off github.com: refused, and the URL never echoed",
              r.startswith("ERROR ") and "ghs_planted" not in r and "example.com" not in r, r)

        print("this_repo: GH_REPO names it outright")
        remote("origin", "git@github.com:gzapi-org/herdr.git")
        os.environ["GH_REPO"] = "gzapi-org/other"
        check("GH_REPO wins over origin", resolved() == "gzapi-org/other", resolved())
        os.environ["GH_REPO"] = "noslash"
        check("a GH_REPO that is not <owner>/<repo>: refused", resolved().startswith("ERROR "), resolved())
        os.environ.pop("GH_REPO")

        print("every gh call carries GH_REPO=this_repo()")
        fake = os.path.join(tmp, "bin")
        os.makedirs(fake)
        with open(os.path.join(fake, "gh"), "w") as f:
            f.write("#!/bin/sh\nprintf '%s' \"${GH_REPO:-unset}\"\n")
        os.chmod(os.path.join(fake, "gh"), 0o755)
        os.environ["PATH"] = f"{fake}:{saved['PATH'] or ''}"
        cwd = os.getcwd()
        os.chdir(wc)
        try:
            check("gh.run in a fork clone pins the fork", gh.run(["pr", "view", "3"]) == "gzapi-org/herdr")
            remote("origin", "https://example.com/x/y.git")
            # An upstream github.com remote is still there: gh would guess it.
            try:
                gh.run(["pr", "view", "3"])
                check("no repository named: a scoped call is refused, never guessed", False)
            except gh.GhError as e:
                check("no repository named: a scoped call is refused, never guessed",
                      "never used" in e.reason and "example.com" not in e.reason, e.reason)
            try:
                gh.run(["api", "repos/{owner}/{repo}/pulls"])
                check("…an api path naming {owner}/{repo} too", False)
            except gh.GhError:
                check("…an api path naming {owner}/{repo} too", True)
            check("…a call naming its repository runs", gh.run(["pr", "view", "3", "--repo", "o/r"]) == "unset")
            check("…a call on no repository runs", gh.run(["api", "user"]) == "unset")
        finally:
            os.chdir(cwd)
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    print(f"\n{'all passed' if not fails else str(fails) + ' FAILED'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
