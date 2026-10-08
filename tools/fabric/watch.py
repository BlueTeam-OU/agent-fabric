#!/usr/bin/env python3
"""tools/fabric/watch.py — this account at a glance, kept current, behind
bin/fabric-watch: the status pane of Fleet Deck's tab for the account
(`moveto <account> --watch`, the owner's three panes, 2026-10-08). From the
coordinator's draft (d241b4bf), finished.

    fabric-watch [--every S] [--prs-every S] [--once]

CONTRACT:
  argv      --every S (default 30, at least 5), --prs-every S (default
            300, at least 60), --once, -h/--help; anything else, or a
            value that is not a finite number: usage on stderr, exit 2.
  stdin     a key at a time: q (or Q) leaves; input that ends leaves too.
            On a terminal it is put in cbreak mode and restored on the way
            out. --once never reads it.
  env       AGENT_FABRIC_ROOT, the fabric whose commands it runs (the shim
            sets it to its own checkout); HOME, whose projects/ holds the
            working copies; the rest passes to the commands untouched.
  stdout    three blocks, in this order, each as its own command prints
            it, stdout then stderr, with "(exit N)" after a command that
            failed:
              status         bin/fabric-status
              jobs           bin/fabric-jobs list
              pull requests  runtime/github/pr-gate.sh, run in each
                             working copy under ~/projects whose origin is
                             on GitHub; one that has none of this
                             account's open is left out
            The first two are local and are read every --every seconds; the
            pull requests ask GitHub, so they are read every --prs-every
            seconds and shown from the last read in between, with its age.
            Each screen clears the last; --once prints one and no clear.
  exit      0 when it leaves (q, end of input, Ctrl-C, or --once); 2 usage.

It is read-only: it runs those three commands and nothing else, never
with an argument a person typed, so the pane can run no other command as
the account. A command that is missing, hangs past TIMEOUT_S or fails is
said in its block; the screen goes on.

Every line passes printable() before it reaches the terminal: a job title
or a PR title is someone's text, and an escape sequence in it would
otherwise retitle the window or write the clipboard.
"""
from __future__ import annotations

import math
import os
import re
import select
import subprocess
import sys
import termios
import time
import tty
import unicodedata
from typing import Callable

HERE = os.path.dirname(os.path.abspath(__file__))
TIMEOUT_S = 60
EVERY_S, PRS_EVERY_S = 30.0, 300.0
MIN_EVERY_S, MIN_PRS_EVERY_S = 5.0, 60.0
CLEAR = "\033[H\033[2J"
USAGE = "usage: fabric-watch [--every S] [--prs-every S] [--once]"
# origin on GitHub: scp-like git@github.com:o/r, ssh://…github.com/…, https://github.com/…
GITHUB = re.compile(r"^(?:[\w.+-]+@github\.com:|(?:ssh|https?|git)://(?:[^/@]+@)?github\.com(?::\d+)?/)")
NONE_OPEN = "pr-gate: no open pull request"


def fabric_root() -> str:
    return os.environ.get("AGENT_FABRIC_ROOT") or os.path.dirname(os.path.dirname(HERE))


def printable(line: str) -> str:
    """The line with every control character a terminal could act on shown
    as `?`: C0 (ESC, BEL), DEL, C1 (CSI is one byte there) and the Unicode
    line separators, as moveto's display_safe strips them. Tabs are spaces."""
    return "".join("?" if unicodedata.category(c) == "Cc" or c in "\u2028\u2029" else c for c in line.expandtabs())


def run(argv: list[str], cwd: str | None = None) -> str:
    """The command's output, stdout then stderr, or why there is none."""
    name = os.path.basename(argv[0])
    try:
        r = subprocess.run(argv, cwd=cwd, stdin=subprocess.DEVNULL, capture_output=True, timeout=TIMEOUT_S)
    except FileNotFoundError:
        return f"({name}: not found)"
    except PermissionError:
        return f"({name}: not executable)"
    except subprocess.TimeoutExpired:
        return f"({name}: no answer within {TIMEOUT_S} s)"
    except OSError as exc:
        return f"({name}: {exc.strerror or exc})"
    out = (r.stdout + r.stderr).decode("utf-8", "replace").rstrip()
    if r.returncode:
        return f"{out}\n({name}: exit {r.returncode})" if out else f"({name}: exit {r.returncode})"
    return out or f"({name}: nothing)"


def working_copies(projects: str) -> list[str]:
    """Each working copy under projects/ whose origin is on GitHub, by name."""
    try:
        names = sorted(os.listdir(projects))
    except OSError:
        return []
    found = []
    for name in names:
        path = os.path.join(projects, name)
        # .git is a file in a linked worktree.
        if not os.path.exists(os.path.join(path, ".git")):
            continue
        try:
            r = subprocess.run(["git", "-C", path, "remote", "get-url", "origin"], stdin=subprocess.DEVNULL,
                               capture_output=True, text=True, timeout=TIMEOUT_S)
        except (OSError, subprocess.TimeoutExpired):
            continue
        if r.returncode == 0 and GITHUB.match(r.stdout.strip()):
            found.append(path)
    return found


def pulls(root: str, projects: str) -> str:
    gate = os.path.join(root, "runtime", "github", "pr-gate.sh")
    blocks = []
    for wc in working_copies(projects):
        out = run([gate], cwd=wc)
        if out.startswith(NONE_OPEN):
            continue
        blocks.append(f"[{os.path.basename(wc)}]\n{out}")
    return "\n".join(blocks) or "no open pull request"


def screen(status: str, jobs: str, prs: str, prs_age: float, stamp: str) -> str:
    return "\n".join([
        f"── status ({stamp}; q leaves) ──", status, "",
        "── jobs ──", jobs, "",
        f"── pull requests (read {int(prs_age)} s ago) ──", prs,
    ])


def draw(text: str, clear: bool, out=None) -> None:
    out = out or sys.stdout
    out.write((CLEAR if clear else "") + "\n".join(printable(line) for line in text.split("\n")) + "\n")
    out.flush()


def wait_for_q(seconds: float, fd: int = 0) -> bool:
    """True when q was typed, or input ended, within the wait. os.read, not
    sys.stdin: a buffered read after select may wait for more than a key."""
    end = time.monotonic() + seconds
    while (left := end - time.monotonic()) > 0:
        ready, _, _ = select.select([fd], [], [], left)
        if ready:
            ch = os.read(fd, 1)
            if ch in (b"q", b"Q", b""):
                return True
    return False


def watch(root: str, projects: str, every: float, prs_every: float, once: bool,
          clock: Callable[[], float] = time.monotonic, wait: Callable[[float], bool] = wait_for_q,
          out=None) -> int:
    prs, prs_at = "", None
    while True:
        if prs_at is None or clock() - prs_at >= prs_every:
            prs, prs_at = pulls(root, projects), clock()
        status = run([os.path.join(root, "bin", "fabric-status")])
        jobs = run([os.path.join(root, "bin", "fabric-jobs"), "list"])
        draw(screen(status, jobs, prs, clock() - prs_at, time.strftime("%H:%M:%S")), clear=not once, out=out)
        if once or wait(every):
            return 0


def parse(argv: list[str]) -> tuple[float, float, bool] | None:
    every, prs_every, once = EVERY_S, PRS_EVERY_S, False
    args = list(argv)
    try:
        while args:
            a = args.pop(0)
            if a == "--every":
                every = float(args.pop(0))
            elif a == "--prs-every":
                prs_every = float(args.pop(0))
            elif a == "--once":
                once = True
            else:
                return None
    except (ValueError, IndexError):
        return None
    # NaN and infinity are numbers to float() and no interval to select().
    if not (math.isfinite(every) and math.isfinite(prs_every)):
        return None
    return max(MIN_EVERY_S, every), max(MIN_PRS_EVERY_S, prs_every), once


def main(argv: list[str]) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    if any(a in ("-h", "--help") for a in argv):
        print(__doc__.strip())
        return 0
    parsed = parse(argv)
    if parsed is None:
        print(USAGE, file=sys.stderr)
        return 2
    every, prs_every, once = parsed
    projects = os.path.join(os.path.expanduser("~"), "projects")
    saved = None
    if not once and os.isatty(0):
        saved = termios.tcgetattr(0)
        tty.setcbreak(0)
    try:
        return watch(fabric_root(), projects, every, prs_every, once)
    except KeyboardInterrupt:
        return 0
    finally:
        if saved is not None:
            termios.tcsetattr(0, termios.TCSADRAIN, saved)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
