"""tests/git_env.py — what git reads in a Python suite: the runner's git
environment never reaches the repositories a test makes or the tools it
runs.

    sys.path holds tests/ for a script run as `python3 tests/test_x.py`:
    from git_env import git_env, scrub_process_env
    scrub_process_env()                          # once, before anything runs
    subprocess.run(["git", "-C", repo, "init", "-q"], env=git_env(), check=True)

The runner's environment otherwise reaches every git call: an inherited
GIT_DIR (a suite run from a hook) aims it at another repository, the
machine's /etc/gitconfig applies, and the runner's global config — an
init.templateDir or core.hooksPath shaping a scratch repository, a
core.excludesFile changing what ls-files lists, a user.name a commit
quietly relies on — makes a result the runner's, not the test's.

Two layers, because a tool under test may need a global config of its own
(secrets_sync writes `git config --global` into the scratch HOME its test
gives it):
- scrub_process_env() drops every inherited GIT_* from this process's
  environment and turns the system config off, so every child inherits
  that, a call with no env= included. The global config stays whatever
  HOME a test hands a tool.
- git_env() is for the test's own git calls: no global config either, no
  global ignore or attributes file (XDG_CONFIG_HOME at nothing), and a
  fixed identity, so a commit never depends on the runner's user.name.
"""
from __future__ import annotations

import os
from collections.abc import Mapping


def scrub_process_env() -> None:
    for k in [k for k in os.environ if k.startswith("GIT_")]:
        del os.environ[k]
    os.environ["GIT_CONFIG_NOSYSTEM"] = "1"


def git_env(base: Mapping[str, str] | None = None) -> dict[str, str]:
    env = {k: v for k, v in (os.environ if base is None else base).items() if not k.startswith("GIT_")}
    env.update({
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "XDG_CONFIG_HOME": os.devnull,
        "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
    })
    return env
