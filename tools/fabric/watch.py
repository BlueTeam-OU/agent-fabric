#!/usr/bin/env python3
"""tools/fabric/watch.py — this account at a glance, kept current, behind
bin/fabric-watch: the status pane of Fleet Deck's tab for the account
(`moveto <account> --watch`, the owner's three panes, 2026-10-08).

    fabric-watch [--every S] [--prs-every S] [--once]

What it shows, in this order, each block as its own command prints it:
  - fabric-status: who, the binding, the provider, every class's model
    and effort, routing health;
  - fabric-jobs list: the open jobs;
  - pr-gate in each working copy under ~/projects that has a GitHub
    remote: this account's open pull requests and what stands between
    each and main.
The first two are local and refresh every --every seconds (30); the pull
requests ask GitHub, so they refresh every --prs-every seconds (300) and
are shown from the last read in between, with its age.

It is read-only: it runs those three commands and nothing else, never
with an argument a person typed, so the pane can run no other command
as the account. q (or Ctrl-C) leaves it; --once prints one screen and
exits (what a test, or a person in a plain shell, uses).

Every line passes printable() before it reaches the terminal: a job
title or a PR title is someone's text, and an escape sequence in it
would otherwise retitle the window or write the clipboard.
"""
from __future__ import annotations

import os
import re
import select
import subprocess
import sys
import termios
import time
import tty

HERE = os.path.dirname(os.path.abspath(__file__))
FABRIC = os.path.dirname(os.path.dirname(HERE))
TIMEOUT_S = 60
CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")


def printable(s: str) -> str:
    return CONTROL.sub("?", s)


def run(argv: list[str], cwd: str | None = None) -> str:
    """The command's output, stdout then stderr, or why there is none."""
    try:
        r = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=TIMEOUT_S, stdin=subprocess.DEVNULL)
    except FileNotFoundError:
        return f"({os.path.basename(argv[0])} not found)"
    except subprocess.TimeoutExpired:
        return f"({os.path.basename(argv[0])}: no answer within {TIMEOUT_S} s)"
    out = (r.stdout + r.stderr).rstrip()
    return out or f"({os.path.basename(argv[0])}: nothing, exit {r.returncode})"


def working_copies(projects: str) -> list[str]:
    """Each directory under ~/projects whose origin is on GitHub."""
    found = []
    try:
        names = sorted(os.listdir(projects))
    except OSError:
        return found
    for name in names:
        path = os.path.join(projects, name)
        if not os.path.isdir(os.path.join(path, ".git")):
            continue
        url = run(["git", "-C", path, "remote", "get-url", "origin"])
        if "github.com" in url:
            found.append(path)
    return found


def prs(projects: str) -> str:
    gate = os.path.join(FABRIC, "runtime", "github", "pr-gate.sh")
    blocks = []
    for wc in working_copies(projects):
        out = run(["bash", gate], cwd=wc)
        if "no open pull request" in out.lower():
            continue
        blocks.append(f"[{os.path.basename(wc)}]\n{out}")
    return "\n".join(blocks) or "no open pull request"


def screen(status: str, jobs: str, pulls: str, pulls_age: float) -> str:
    stamp = time.strftime("%H:%M:%S")
    return "\n".join([
        f"── status ({stamp}; q leaves) ──", status, "",
        "── jobs ──", jobs, "",
        f"── pull requests (read {int(pulls_age)} s ago) ──", pulls,
    ])


def bin_cmd(name: str) -> list[str]:
    return [os.path.join(FABRIC, "bin", name)]


def draw(text: str, clear: bool) -> None:
    out = "\n".join(printable(line) for line in text.splitlines())
    sys.stdout.write(("\033[H\033[2J" if clear else "") + out + "\n")
    sys.stdout.flush()


def wait_for_q(seconds: float) -> bool:
    """True when q was typed (or input ended) within the wait."""
    if not sys.stdin.isatty():
        time.sleep(seconds)
        return False
    end = time.monotonic() + seconds
    while (left := end - time.monotonic()) > 0:
        ready, _, _ = select.select([sys.stdin], [], [], left)
        if ready:
            ch = sys.stdin.read(1)
            if ch in ("q", "Q", ""):
                return True
    return False


def main(argv: list[str]) -> int:
    every, prs_every, once = 30.0, 300.0, False
    args = list(argv)
    try:
        while args:
            a = args.pop(0)
            if a == "--every":
                every = max(5.0, float(args.pop(0)))
            elif a == "--prs-every":
                prs_every = max(60.0, float(args.pop(0)))
            elif a == "--once":
                once = True
            elif a in ("-h", "--help"):
                print(__doc__.strip())
                return 0
            else:
                raise ValueError(a)
    except (ValueError, IndexError):
        print("usage: fabric-watch [--every S] [--prs-every S] [--once]", file=sys.stderr)
        return 2
    projects = os.path.join(os.path.expanduser("~"), "projects")
    pulls, pulls_at = "", 0.0
    saved = termios.tcgetattr(sys.stdin) if sys.stdin.isatty() and not once else None
    try:
        if saved is not None:
            tty.setcbreak(sys.stdin)
        while True:
            now = time.monotonic()
            if not pulls_at or now - pulls_at >= prs_every:
                pulls, pulls_at = prs(projects), time.monotonic()
            draw(screen(run(bin_cmd("fabric-status")), run(bin_cmd("fabric-jobs") + ["list"]),
                        pulls, time.monotonic() - pulls_at), clear=not once)
            if once or wait_for_q(every):
                return 0
    except KeyboardInterrupt:
        return 0
    finally:
        if saved is not None:
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, saved)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
