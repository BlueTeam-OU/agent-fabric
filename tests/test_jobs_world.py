#!/usr/bin/env python3
"""tests/jobs_world.py `seeded`: every world is its own checkout of its own bare origin, though all copy one template built once per
process. The jobs suites lean on that (a push in one world, a branch swept in another); a copy that kept the template's remote or shared
its origin would let one case write into the next without any of them failing on its own."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import jobs_world  # noqa: E402 — tests/, the script's own directory
from git_env import git_env, scrub_process_env  # noqa: E402 — tests/, the script's own directory
scrub_process_env()


def git(path: str, *args: str) -> str:
    return subprocess.run(["git", "-C", path, *args], check=True, capture_output=True, text=True, env=git_env()).stdout.strip()


def main() -> int:
    fails = 0

    def check(label: str, good: bool, detail: str = "") -> None:
        nonlocal fails
        print(f"  {'ok  ' if good else 'FAIL'} {label}")
        if not good and detail:
            print("      " + detail.replace("\n", "\n      "))
        fails += not good

    with tempfile.TemporaryDirectory() as tmp:
        origins = os.path.join(tmp, "origins")
        a = jobs_world.seeded(os.path.join(tmp, "a"), origins)
        b = jobs_world.seeded(os.path.join(tmp, "b"), origins)
        check("a world's origin is the bare repository beside its own name, not the template's",
              git(a, "remote", "get-url", "origin") == os.path.join(origins, "a.git")
              and git(b, "remote", "get-url", "origin") == os.path.join(origins, "b.git"),
              f"{git(a, 'remote', 'get-url', 'origin')}\n{git(b, 'remote', 'get-url', 'origin')}")
        check("main is pushed and origin/HEAD points at it", git(a, "rev-parse", "origin/main") == git(a, "rev-parse", "main")
              and git(a, "symbolic-ref", "refs/remotes/origin/HEAD") == "refs/remotes/origin/main")
        git(a, "commit", "-q", "--allow-empty", "-m", "only in a")
        git(a, "push", "-q", "origin", "main")
        check("a push in one world reaches that world's origin and no other",
              git(os.path.join(origins, "a.git"), "rev-parse", "main") == git(a, "rev-parse", "main")
              and git(os.path.join(origins, "b.git"), "rev-parse", "main") == git(b, "rev-parse", "main")
              and git(a, "rev-parse", "main") != git(b, "rev-parse", "main"))
        c = jobs_world.seeded(os.path.join(tmp, "c"), origins)
        check("a world made after another has pushed starts from the seed, not from that push",
              git(os.path.join(origins, "c.git"), "rev-list", "--count", "main") == "1" and git(c, "rev-list", "--count", "main") == "1")
    print("test_jobs_world: " + ("OK" if not fails else f"{fails} FAIL"))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
