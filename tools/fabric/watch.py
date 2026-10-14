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
            While the pull requests are read it is looked at between
            working copies, so q waits for one pr-gate at most.
            On a terminal it is put in cbreak mode and restored on the way
            out. --once never reads it.
  env       AGENT_FABRIC_ROOT, the fabric whose commands it runs (the shim
            sets it to its own checkout); HOME, whose projects/ holds the
            working copies and .local/share/agent-fabric/secrets this
            login's store checkout (AGENT_FABRIC_SECRET_STORE names another;
            of it only settings/profile.json, settings/avatar.png and .agent-id);
            TERM_PROGRAM (a pane host listed in
            runtime/control/watch-graphics.json: the avatar goes by the kitty graphics
            protocol), COLUMNS; XDG_CACHE_HOME (the avatar's cache); the
            rest passes to the commands untouched.
  stdout    three blocks, in this order:
              identity       beside the avatar (20 x 10 cells, 12 x 6 on a pane
                             of fewer than 30 rows, where the text is 6
                             lines too: the blank ones, the second engine
                             and a line of the harness are left out; on a terminal
                             only, and not on one narrower than 52 columns):
                               "AI <first name> <surname>" from the persona
                               (watch_identity.persona; the login alone when
                               it has none: a name is never shown without
                               "AI"), then the login and the bound role;
                               the harness (claude or codex, the one this
                               account runs) and its version, read once;
                               the session's model and effort and the second
                               engine, from fabric-status --json; this
                               account's CPU% and memory (its processes, from
                               /proc), the host's load and free memory, and
                               the account's disk use (du of its home, read
                               in the background every 10 minutes, so never
                               in the way of a screen)
              jobs           bin/fabric-jobs list --json, by priority (high,
                             normal, low), within one active, blocked,
                             queued, delivered, then by id; each with its
                             id, state and title; a blocked one with what it
                             waits on
              pull requests  bin/fabric-pr gate, run in one
                             working copy per GitHub repository under
                             ~/projects (the first by name); one that has
                             none of this account's open is left out
            A command that failed is said in its place, with "(exit N)".
            The identity and the jobs are local and are read every --every
            seconds; the pull requests ask GitHub, so they are read every
            --prs-every seconds and shown from the last read in between,
            with its age. Each screen clears the last; --once prints one
            and no clear. On a terminal the screen is cut to the pane's
            height (one line less, so the last newline does not scroll the
            title off): the title and the identity stay, the jobs take what
            is left after a third for the pull requests, and a cut block
            ends with "… N more"; no line is longer than the pane is wide
            (wide characters count two cells). The pane's size is read from
            the kernel on every screen, so a resize is followed. --once is
            never cut.
  avatar    from settings/avatar.png of the store checkout, else the
            candidate the profile names, else none (avatar.py). On a pane of a
            host listed in runtime/control/watch-graphics.json (TERM_PROGRAM) the PNG file is transmitted as it is
            by the kitty graphics protocol, which the pane host re-draws on its
            terminal (that terminal must speak kitty graphics for it to
            show); anywhere else it is drawn with Unicode half blocks in
            24-bit colour from the stdlib PNG decoder (8-bit RGB or RGBA,
            not interlaced; any other file shows no avatar), decoded once
            and cached by the file's sha256 and the size as pixels, never as escapes.
  exit      0 when it leaves (q, end of input, Ctrl-C, or --once); 2 usage.

It is read-only: it runs bin/fabric-status --json, bin/fabric-jobs list --json
and bin/fabric-pr gate, `<harness> --version` once, and `du -sk -x <home>` in
the background, and nothing else, never with an argument a person typed, so
the pane can run no other command as the account. A command that is missing,
hangs past TIMEOUT_S or fails is said in its place; the screen goes on.

Every line of text passes printable() before it reaches the terminal: a job
title, a PR title, a persona name or a version line is someone's text, and an
escape sequence in it would otherwise retitle the window or write the
clipboard. The only escapes that reach the terminal are the avatar's own
(Row.prefix), generated by avatar.py from numbers and from the PNG's bytes,
never read from text or from a file.
"""
from __future__ import annotations

import json
import math
import os
import re
import select
import subprocess
import sys
import termios
import threading
import time
import tty
import unicodedata
from dataclasses import dataclass
from typing import Callable


HERE = os.path.dirname(os.path.abspath(__file__))
# The modules beside this file, however it is run: a script's own directory is on sys.path only by default (python -I
# and -P leave it out).
sys.path.insert(0, HERE)
import avatar  # noqa: E402
import watch_identity  # noqa: E402
import watch_resources  # noqa: E402

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


def run(argv: list[str], cwd: str | None = None, merge: bool = True) -> str:
    """The command's output, stdout then stderr, or why there is none. merge=False is for a command whose stdout is a
    document: an advisory line on its stderr must not make the document unparseable, so only stdout is returned (and
    stderr only when there is no stdout)."""
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
    out = ((r.stdout + r.stderr) if merge or r.returncode or not r.stdout.strip() else r.stdout).decode("utf-8", "replace").rstrip()
    if r.returncode:
        return f"{out}\n({name}: exit {r.returncode})" if out else f"({name}: exit {r.returncode})"
    return out or f"({name}: nothing)"


def repo_of(url: str) -> str:
    """owner/name of a GitHub origin, however it is spelt."""
    path = GITHUB.sub("", url.strip()).rstrip("/")
    return (path[:-4] if path.endswith(".git") else path).lower()


def working_copies(projects: str) -> list[str]:
    """One working copy per GitHub repository under projects/, the first
    by name: pr-gate lists the account's PRs of the repository, so a
    second clone of it would show the same block and ask GitHub again."""
    try:
        names = sorted(os.listdir(projects))
    except OSError:
        return []
    found, seen = [], set()
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
        if r.returncode == 0 and GITHUB.match(r.stdout.strip()) and repo_of(r.stdout) not in seen:
            seen.add(repo_of(r.stdout))
            found.append(path)
    return found


def pulls(root: str, projects: str, stop: Callable[[], bool] = lambda: False) -> str | None:
    """The pull-request block; None when stop() says to leave, which is
    asked between working copies, so q waits at most for one pr-gate."""
    gate = [os.path.join(root, "bin", "fabric-pr"), "gate"]
    blocks = []
    for wc in working_copies(projects):
        if stop():
            return None
        out = run(gate, cwd=wc)
        if out.startswith(NONE_OPEN):
            continue
        blocks.append(f"[{os.path.basename(wc)}]\n{out}")
    return "\n".join(blocks) or "no open pull request"


@dataclass
class Row:
    """A line of the screen with something drawn at its left: `prefix` is the avatar's own escape sequences, generated by
    avatar.py from numbers and from a PNG's bytes (never text, never read from a file), and `text` is someone's and goes
    through printable() like any other line. Nothing else may carry an escape."""
    prefix: str
    text: str


Line = str | Row
AVATAR_MIN_COLUMNS = 52
FULL_BOX = (avatar.COLS, avatar.ROWS)
SMALL_BOX = (12, 6)                            # same aspect: a cell is about twice as tall as wide
TALL_PANE_ROWS = 30                            # the full box only from here up; below, it is half a 20-row pane
JOB_PRIORITIES = ("blocking", "high", "normal", "low")      # fabric-jobs' own order (jobsparts/base.py)
JOB_STATES = ("active", "paused", "blocked", "queued", "delivered")
HEADER_ROWS = avatar.ROWS


def box_for(pane_rows: int) -> tuple[int, int]:
    """The avatar's (columns, rows) of cells: the full box on a tall pane or when the height is not known (0)."""
    return SMALL_BOX if 0 < pane_rows < TALL_PANE_ROWS else FULL_BOX


def text_column(box: tuple[int, int]) -> int:
    return box[0] + 2


def go_to_text(box: tuple[int, int]) -> str:
    return f"\033[{text_column(box)}G"          # kitty draws over the cells; the text is written beside them


def rank(value: object, order: tuple[str, ...]) -> int:
    return order.index(value) if value in order else len(order)


def jobs_block(jobs_text: str) -> list[str]:
    """fabric-jobs list --json as lines, by priority (high, normal, low) and within it by state (active, blocked,
    queued, delivered), then by id; a blocked job with what it waits on. Its failure message, when it did not answer."""
    try:
        doc = json.loads(jobs_text)
    except (ValueError, RecursionError):
        return jobs_text.split("\n")
    if not isinstance(doc, list):
        return ["(fabric-jobs: its answer is not a list of jobs)"]
    jobs = [j for j in doc if isinstance(j, dict)]
    if not jobs:
        return ["no open jobs"]

    def number(job: dict) -> tuple[int, str]:
        ident = str(job.get("id", ""))
        digits = re.sub(r"\D", "", ident)
        return (int(digits) if digits else 0, ident)
    lines = []
    for job in sorted(jobs, key=lambda j: (rank(j.get("effective_priority") or j.get("priority") or "normal", JOB_PRIORITIES), rank(j.get("state"), JOB_STATES), number(j))):
        ident, state = (str(job.get(k) or "?")[:12] for k in ("id", "state"))
        prio = str(job.get("effective_priority") or job.get("priority") or "normal")[:12]
        lines.append(f"{ident:<5} {state:<9} {prio:<7} {str(job.get('title') or '')[:300]}")
        if job.get("state") == "blocked":
            lines.append(f"      waits on: {str(job.get('blocked_on') or '(not said)')[:300]}")
    return lines


class AvatarSlot:
    """The avatar of the identity header: its left-hand prefixes (box rows of them), or None when there is nothing to
    draw. mode "kitty" transmits the PNG file as it is; "blocks" draws half blocks from the decoded, cached pixels,
    which a thread of its own decodes, so the first screens show the room it will take and never wait for it."""

    def __init__(self, mode: str | None, cache_dir: str):
        self.mode, self.cache_dir = mode, cache_dir
        self.box = FULL_BOX
        self.path: str | None = None
        self._prefixes: list[str] | None = None
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    def set_path(self, path: str | None, box: tuple[int, int] = FULL_BOX) -> None:
        with self._lock:
            if self.mode is None or (path, box) == (self.path, self.box):
                return
            self.path, self.box, self._prefixes = path, box, None
            if path is None:
                return
            self._thread = threading.Thread(target=self._load, args=(path, box), name="watch-avatar", daemon=True)
            self._thread.start()

    def _load(self, path: str, box: tuple[int, int]) -> None:
        try:
            data = avatar.read_file(path)
            if self.mode == "kitty":
                avatar.decode(data)                          # what is sent is a file this would draw: never bytes that only start like a PNG
                escape = avatar.kitty_escape(data, *box)
                prefixes = None if escape is None else [escape + go_to_text(box)] + [go_to_text(box)] * (box[1] - 1)
            else:
                grid = avatar.grid_of(data, self.cache_dir, cols=box[0], rows=box[1])
                prefixes = [row + "  " for row in avatar.half_blocks(grid)]
        except avatar.Refused:
            prefixes = None                                  # not an avatar this draws: none shown
        with self._lock:
            if (path, box) == (self.path, self.box):
                self._prefixes = prefixes if prefixes is not None else []

    def prefixes(self) -> list[str] | None:
        with self._lock:
            if self.mode is None or self.path is None:
                return None
            if self._prefixes is None:
                return [" " * text_column(self.box)] * self.box[1]     # loading: the room it will take
            return self._prefixes or None

    def wait(self, timeout: float = 30.0) -> None:
        thread = self._thread
        if thread is not None:
            thread.join(timeout)


def kitty_terminals(root: str) -> list[str]:
    """The TERM_PROGRAM values that take kitty graphics (runtime/control/watch-graphics.json); a file that is not there or
    not what it should be lists none, and the avatar is drawn with half blocks."""
    try:
        with open(os.path.join(root, "runtime", "control", "watch-graphics.json"), encoding="utf-8") as fh:
            names = json.load(fh).get("kitty_terminal_programs")
    except (OSError, ValueError, AttributeError, RecursionError):
        return []
    return [n for n in names if isinstance(n, str) and n] if isinstance(names, list) else []


def parse_object(text: str) -> tuple[dict | None, str | None]:
    """(the JSON object a command printed, None) or (None, why not: what it printed, its failure message included)."""
    try:
        doc = json.loads(text)
    except (ValueError, RecursionError):
        return None, text.strip()[:1000] or "(no answer)"
    return (doc, None) if isinstance(doc, dict) else (None, "(its answer is not an object)")


def clock_text(seconds: float | None) -> str:
    if seconds is None:
        return "-"
    return f"{int(seconds)} s" if seconds < 120 else f"{int(seconds // 60)} min"


class Deck:
    """What the identity header keeps between screens: the CPU sample, the disk reading, the avatar, the harness version."""

    def __init__(self, environ: dict[str, str], claims_path: str, avatar_mode: str | None = None, proc: str = "/proc",
                 uid: int | None = None, disk: watch_resources.DiskUse | None = None, version_of=watch_identity.version_line):
        self.environ, self.claims_path, self.proc = environ, claims_path, proc
        self.uid = os.geteuid() if uid is None else uid
        home = environ.get("HOME") or os.path.expanduser("~")
        self.sampler = watch_resources.ProcSampler(self.uid, proc)
        self.disk = disk or watch_resources.DiskUse(home)
        cache = environ.get("XDG_CACHE_HOME") or os.path.join(home, ".cache")
        self.slot = AvatarSlot(avatar_mode, os.path.join(cache, "agent-fabric"))
        self.versions: dict[str, str | None] = {}
        self.version_of = version_of

    def text_rows(self, status_text: str, box: tuple[int, int] = FULL_BOX) -> tuple[list[str], str]:
        """(as many lines of text as the box has rows, the name the title says). The small box is 6 rows: the blank
        lines go, the harness joins the login and the model its effort, and the second engine is left out."""
        status, problem = parse_object(status_text)
        persona = watch_identity.persona(self.environ, self.claims_path)
        login = str((status or {}).get("agent") or "(login unknown)")
        role = str((status or {}).get("role") or "-")
        harness = watch_identity.running_harness(self.uid, self.proc)
        if harness is not None and harness not in self.versions:
            self.versions[harness] = self.version_of(harness)          # once: a harness is not upgraded under a session
        models = watch_identity.model_lines(status)
        mine = self.sampler.sample()
        load, mem = watch_resources.host_load(self.proc), watch_resources.host_memory(self.proc)
        self.disk.poll()
        kb, age, why = self.disk.value()
        account = f"account  cpu {'-' if mine['cpu_pct'] is None else mine['cpu_pct']}%  mem {watch_resources.human_kb(mine['rss_kb'])}  ({mine['procs']} processes)"
        host = ("host     load " + (" ".join(f"{v:.2f}" for v in load) if load else "-")
                + "  free " + (f"{watch_resources.human_kb(mem[0])} of {watch_resources.human_kb(mem[1])}" if mem else "-"))
        disk = "disk     " + (f"{watch_resources.human_kb(kb)} (read {clock_text(age)} ago)" if kb is not None else (why or "reading…"))
        if box != FULL_BOX:
            rows = [
                persona.name or login,
                f"{login} · {role} · {harness or '-'} {self.versions.get(harness or '') or ''}".rstrip(),
                f"model {models['model'] or '-'} · effort {models['effort'] or '-'}",
                account, host, disk,
            ]
            if status is None:
                said = (problem or "(fabric-status: no answer)").split("\n")[:2]
                rows[1:3] = said + [""] * (2 - len(said))
            self.slot.set_path(persona.avatar_path, box)
            return rows, persona.name or login
        rows = [
            persona.name or login,
            f"{login} · {role}",
            f"harness {harness or '-'} {self.versions.get(harness or '') or ''}".rstrip(),
            f"model {models['model'] or '-'} · effort {models['effort'] or '-'}",
            models["engine"] or "",
            "",
            account, host, disk,
            "",
        ]
        if status is None:
            # fabric-status did not answer: what it said, in place of the login, harness and model lines
            said = (problem or "(fabric-status: no answer)").split("\n")[:5]
            rows[1:6] = said + [""] * (5 - len(said))
        self.slot.set_path(persona.avatar_path, box)
        return rows, persona.name or login

    def identity(self, status_text: str, once: bool = False, columns: int = 80, pane_rows: int = 0) -> tuple[list[Line], str]:
        box = box_for(pane_rows)
        rows, name = self.text_rows(status_text, box)
        if once:
            self.slot.wait()
            self.disk.wait(3.0)
            rows[8 if box == FULL_BOX else 5] = self.disk_row()           # the reading, if it finished
        prefixes = self.slot.prefixes() if columns >= AVATAR_MIN_COLUMNS else None
        cut = pane_rows > 0 and columns > 1            # on a pane: no line wraps into a second row
        if prefixes is None:
            return [fit(r, columns - 1) for r in rows] if cut else list(rows), name
        width = columns - text_column(box) - 1
        return [Row(prefix, fit(text, width) if cut else text) for prefix, text in zip(prefixes, rows)], name

    def disk_row(self) -> str:
        kb, age, why = self.disk.value()
        return "disk     " + (f"{watch_resources.human_kb(kb)} (read {clock_text(age)} ago)" if kb is not None else (why or "reading…"))


def cells(char: str) -> int:
    return 0 if unicodedata.combining(char) else 2 if unicodedata.east_asian_width(char) in "WF" else 1


def fit(text: str, width: int) -> str:
    """The line as printable() shows it, cut to `width` terminal cells (a wide character is two): a line that wraps takes
    two rows of the pane and pushes the title off it. Tabs are expanded first, as they are when drawn."""
    out, used = [], 0
    for char in printable(text):
        used += cells(char)
        if used > width:
            break
        out.append(char)
    return "".join(out)


def clip(lines: list[str], n: int) -> list[str]:
    """At most n lines (at least one when there are any); the last of a cut block says how many it hides, so a block is
    never dropped without a word."""
    n = max(1, n) if lines else 0
    if len(lines) <= n:
        return lines
    return lines[:n - 1] + [f"… {len(lines) - n + 1} more"]


def screen(identity: list[Line], name: str, jobs: list[str], prs: str, prs_age: float, stamp: str, rows: int = 0, columns: int = 0) -> list[Line]:
    """The three blocks. rows > 0 is the pane's height: the screen is cut to rows - 1 lines, because the newline that ends
    the last one would scroll a full pane and push the title off the top. The title and the identity stay; the jobs and
    the pull requests share what is left, the jobs first, the pull requests keeping a third of it at least one line;
    on a pane too short for both, the jobs alone (see the comment below). columns > 1 cuts a job or
    pull-request line, the block headers and the title to the width, since a wrapped line takes two rows of the pane (the identity's own
    lines are cut by Deck.identity, which knows where its text starts)."""
    pr_lines = prs.split("\n")
    title = f"── {name} ({stamp}; q leaves) ──"
    jobs_head, prs_head = "── jobs ──", f"── pull requests (read {int(prs_age)} s ago) ──"
    if rows > 0 and columns > 1:
        jobs = [fit(j, columns - 1) for j in jobs]
        pr_lines = [fit(l, columns - 1) for l in pr_lines]
        title = fit(title, columns - 1)
        jobs_head, prs_head = (fit(h, columns - 1) for h in (jobs_head, prs_head))
    show_jobs = show_prs = True
    if rows > 0:
        # A block costs its blank line and header and needs a line of its own (clip makes it the count of what it hides),
        # so both blocks need 6 spare rows. With fewer, the jobs are shown alone (the pull requests alone when there are
        # none) in what the title and identity leave, and with under 3 neither: a header with nothing under it reads as
        # an empty block.
        spare = rows - 1 - (len(identity) + 1)
        both = spare >= 6
        show_jobs = both or (spare >= 3 and bool(jobs))
        show_prs = both or (spare >= 3 and not jobs)
        if both:
            room = spare - 4
            pr_n = min(len(pr_lines), max(1, room // 3))
            job_n = min(len(jobs), max(1, room - pr_n))
            pr_n = min(len(pr_lines), max(1, room - job_n))
        else:
            job_n = pr_n = spare - 2
        jobs, pr_lines = clip(jobs, job_n), clip(pr_lines, pr_n)
    lines: list[Line] = [title, *identity]
    if show_jobs:
        lines += ["", jobs_head, *jobs]
    if show_prs:
        lines += ["", prs_head, *pr_lines]
    return lines[:rows - 1] if rows > 0 else lines


def draw(lines: list[Line] | str, clear: bool, out=None) -> None:
    out = out or sys.stdout
    if isinstance(lines, str):
        lines = lines.split("\n")
    body = "\n".join(line.prefix + printable(line.text) if isinstance(line, Row) else printable(line) for line in lines)
    out.write((CLEAR if clear else "") + body + "\n")
    out.flush()


def wait_for_q(seconds: float, fd: int = 0) -> bool:
    """True when q was typed, or input ended, within the wait. os.read, not
    sys.stdin: a buffered read after select may wait for more than a key."""
    end = time.monotonic() + seconds
    while True:
        # At least one look, so a wait of 0 still reads a key already typed.
        ready, _, _ = select.select([fd], [], [], max(0.0, end - time.monotonic()))
        if ready:
            ch = os.read(fd, 1)
            if ch in (b"q", b"Q", b""):
                return True
        elif time.monotonic() >= end:
            return False


def watch(root: str, projects: str, every: float, prs_every: float, once: bool,
          clock: Callable[[], float] = time.monotonic, wait: Callable[[float], bool] = wait_for_q,
          out=None, deck: Deck | None = None, columns: int = 80, rows: int = 0,
          pane: Callable[[], tuple[int, int]] | None = None) -> int:
    prs, prs_at = "", None
    deck = deck or Deck(dict(os.environ), os.path.join(root, "identities", "personas", "claims.json"))
    while True:
        if pane is not None:
            columns, rows = pane()                     # asked on every screen: a pane is resized under a running watch
        if prs_at is None or clock() - prs_at >= prs_every:
            read = pulls(root, projects, stop=(lambda: False) if once else (lambda: wait(0)))
            if read is None:
                return 0
            prs, prs_at = read, clock()
        status = run([os.path.join(root, "bin", "fabric-status"), "--json"], merge=False)
        jobs = run([os.path.join(root, "bin", "fabric-jobs"), "list", "--json"], merge=False)
        identity, name = deck.identity(status, once=once, columns=columns, pane_rows=rows)
        draw(screen(identity, name, jobs_block(jobs), prs, clock() - prs_at, time.strftime("%H:%M:%S"), rows, columns), clear=not once, out=out)
        if once or wait(every):
            return 0


def pane_size(fd: int = 1) -> tuple[int, int]:
    """(columns, rows) of the terminal on fd, from the kernel, not from LINES/COLUMNS (an exported stale value would size
    the box and the cut wrongly); 80 x 24 when it does not say."""
    try:
        size = os.get_terminal_size(fd)
    except OSError:
        return 80, 24
    return size.columns or 80, size.lines or 24


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
    on_terminal = sys.stdout.isatty()
    root = fabric_root()
    mode = ("kitty" if os.environ.get("TERM_PROGRAM") in kitty_terminals(root) else "blocks") if on_terminal else None
    deck = Deck(dict(os.environ), os.path.join(root, "identities", "personas", "claims.json"), mode)
    # --once is a document, not a pane: never cut, and its width is read once.
    columns = pane_size()[0] if on_terminal else 0
    pane = pane_size if on_terminal and not once else None
    try:
        return watch(root, projects, every, prs_every, once, deck=deck, columns=columns, pane=pane)
    except KeyboardInterrupt:
        return 0
    finally:
        if saved is not None:
            termios.tcsetattr(0, termios.TCSADRAIN, saved)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
