"""tools/fabric/github/review_coverage.py — the v2 review marker and the coverage block, read and written in ONE place
(agent-fabric ADR-065 §2 C, §5 rules 4-5). post_review.py writes them; pr_review_status's classify, results.py and
last_checkpoint (below) read them. No reader has a second parser: two readings of the same line are how a review
counts for one tool and not for the next.

THE MARKER, the first line of a posted review:
    <!-- agent-fabric-review v2 base=<sha40> head=<sha40> card=<sha40> config=<sha256hex> -->
`base` and `head` are the range the review read, `card` the commit its project card was read at (a re-review reads
the card at card_base, not at the range's base) and `config` the hash of what produced it (agent file, the card at
`card`, brief renderer). It is read as the WHOLE first line and nothing else: a marker-like line further down is the report's
text, never the review's.

THE BLOCK, one fenced block whose info string is `agent-fabric-coverage v1`, JSON:
    {"paths": {"<path>": {"status": "read"|"not read", "reason": str}}, "lenses": {"<lens>": "applied"|"not applied"},
     "default": {"status": "read"|"not read", "reason": str}}
`reason` is required when a path is "not read". `default` is optional: the entry of every path of the range the block
does not name, so a block's size does not grow with the paths a reviewer treated alike (a memory drain's thousand).
It is a key of its own, not a path called "*", because a file may be called that. A path named in "paths" is read by
its own entry whatever the default says; a default that is "not read" makes the review partial (Coverage.complete),
since the block alone cannot say that no path falls under it. Exactly one block per review: the report is model output, and a second
block (in a longer fence, a blockquote or a list item included) leaves which one the reader means a guess, so any
line that opens a second one makes the whole block unreadable.

WHAT A READER MAY COUNT. A v2 review is coverage of its head only when marker and block both read and every path is
"read" (Review.counts). A review that does not read is not counted and is not an error: unknown stays unknown, and
the caller shows it (classify's `partial`). v1 is not handled here; it counts as before and is never a checkpoint.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass

V2_PREFIX = "<!-- agent-fabric-review v2"
MARKER_V2 = re.compile(r"<!-- agent-fabric-review v2 base=(?P<base>[0-9a-f]{40}) head=(?P<head>[0-9a-f]{40}) "
                       r"card=(?P<card>[0-9a-f]{40}) config=(?P<config>[0-9a-f]{64}) -->")
BLOCK_INFO = "agent-fabric-coverage v1"
READ, NOT_READ = "read", "not read"
APPLIED, NOT_APPLIED = "applied", "not applied"

# The block is what grows with the PR's paths, so it is bounded inside the review's limit, with room left for the
# marker and the pointer to a report moved to a comment, and a larger one is refused at post time instead of
# rejected by GitHub after the fact. It is posted compact (render_block): a few hundred paths with long names are
# tens of thousands of characters, and the limit must not be what a review of a memory drain meets.
MAX_BLOCK_CHARS = 60_000
# GitHub takes at most 65536 characters in a review's body; a margin is left for what a review adds around the block.
MAX_REVIEW_CHARS = 65_000
MAX_NAME_CHARS = 1_000
MAX_REASON_CHARS = 1_000
MAX_LENSES = 100
GIT_TIMEOUT_S = 60

# CommonMark: up to three spaces, a run of three or more backticks or tildes, then the info string.
_FENCE = re.compile(r" {0,3}(?P<run>`{3,}|~{3,})[ \t]*(?P<info>[^\n]*?)[ \t]*")
# Any line that names the block behind quote and list markers, as post_review's STRAY_FENCE does for the dispatch
# header: whatever a markdown renderer might take for a block of ours.
_LOOKALIKE = re.compile(r"^[ \t]*(?:>[ \t]*|(?:[*+-]|\d{1,9}[.)])[ \t]+)*(?:`{3,}|~{3,})[ \t]*" + re.escape(BLOCK_INFO.split()[0]))


class CoverageError(ValueError):
    """A block that cannot be read as the contract says; the message names why."""


@dataclass(frozen=True)
class Marker:
    base: str
    head: str
    card: str
    config: str

    def line(self) -> str:
        return format_marker(self.base, self.head, self.card, self.config)


def format_marker(base: str, head: str, card: str, config: str) -> str:
    marker = f"{V2_PREFIX} base={base} head={head} card={card} config={config} -->"
    if not MARKER_V2.fullmatch(marker):
        raise CoverageError("base, head and card must be full 40-hex commit shas and config a 64-hex sha256")
    return marker


def parse_marker(body: str) -> Marker | None:
    """The marker when the whole first line is one, else None."""
    m = MARKER_V2.fullmatch((body or "").split("\n", 1)[0].rstrip("\r"))
    return Marker(m["base"], m["head"], m["card"], m["config"]) if m else None


@dataclass(frozen=True)
class Coverage:
    paths: dict[str, tuple[str, str]]   # path -> (status, reason)
    lenses: dict[str, str]
    default: tuple[str, str] | None = None   # (status, reason) of every range path not named in `paths`

    @property
    def not_read(self) -> list[str]:
        """The named paths that are not read; a default that is not read is `default_not_read`, not a path."""
        return [p for p, (status, _) in self.paths.items() if status != READ]

    @property
    def default_not_read(self) -> bool:
        return self.default is not None and self.default[0] != READ

    @property
    def complete(self) -> bool:
        return not self.not_read and not self.default_not_read

    def as_json(self) -> dict:
        doc: dict = {"paths": {p: _entry_json(s, r) for p, (s, r) in sorted(self.paths.items())}, "lenses": dict(self.lenses)}
        if self.default is not None:
            doc["default"] = _entry_json(*self.default)
        return doc


def _entry_json(status: str, reason: str) -> dict:
    return {"status": status, "reason": reason} if reason else {"status": status}


def _unique_keys(pairs: list) -> dict:
    keys = [k for k, _ in pairs]
    if len(set(keys)) != len(keys):
        raise ValueError("a key given twice")
    return dict(pairs)


def _no_constant(name: str):
    raise ValueError(f"{name} is not JSON")


def _plain(name: object, what: str) -> str:
    """A path or lens name that is one printable line: a control character (a newline above all) in a name is how a
    value leaves the line it was written on."""
    if not isinstance(name, str) or not name.strip():
        raise CoverageError(f"{what} is not a non-empty string")
    if len(name) > MAX_NAME_CHARS:
        raise CoverageError(f"{what} {name[:40]!r}… is longer than {MAX_NAME_CHARS} characters")
    if any(ord(c) < 0x20 or ord(c) == 0x7F for c in name):
        raise CoverageError(f"{what} {name!r} holds a control character")
    return name


def _parse_entry(entry: object, what: str) -> tuple[str, str]:
    if not isinstance(entry, dict) or not set(entry) <= {"status", "reason"} or "status" not in entry:
        raise CoverageError(f'{what}: the entry is not an object of "status" and "reason"')
    status, reason = entry["status"], entry.get("reason", "")
    if status not in (READ, NOT_READ):
        raise CoverageError(f'{what}: status {status!r} is neither "read" nor "not read"')
    if not isinstance(reason, str) or len(reason) > MAX_REASON_CHARS:
        raise CoverageError(f"{what}: the reason is not a string of at most {MAX_REASON_CHARS} characters")
    if status == NOT_READ and not reason.strip():
        raise CoverageError(f'{what}: "not read" needs a reason')
    return status, reason


def parse_block(text: str) -> Coverage:
    if len(text) > MAX_BLOCK_CHARS:
        raise CoverageError(f"the coverage block is {len(text)} characters, over the {MAX_BLOCK_CHARS} it may hold")
    try:
        doc = json.loads(text, object_pairs_hook=_unique_keys, parse_constant=_no_constant)
    except (ValueError, RecursionError) as e:
        raise CoverageError(f"the coverage block is not JSON with each key once ({e})") from None
    if not isinstance(doc, dict) or not {"paths", "lenses"} <= set(doc) <= {"paths", "lenses", "default"}:
        raise CoverageError('the coverage block is not an object of "paths" and "lenses" and, optionally, "default"')
    if not isinstance(doc["paths"], dict) or not isinstance(doc["lenses"], dict):
        raise CoverageError('"paths" and "lenses" must each be an object')
    paths: dict[str, tuple[str, str]] = {}
    for path, entry in doc["paths"].items():
        _plain(path, "a path")
        paths[path] = _parse_entry(entry, f"path {path!r}")
    if len(doc["lenses"]) > MAX_LENSES:
        raise CoverageError(f"more than {MAX_LENSES} lenses")
    lenses: dict[str, str] = {}
    for lens, state in doc["lenses"].items():
        _plain(lens, "a lens")
        if state not in (APPLIED, NOT_APPLIED):
            raise CoverageError(f'lens {lens!r}: {state!r} is neither "applied" nor "not applied"')
        lenses[lens] = state
    default = _parse_entry(doc["default"], "the default") if "default" in doc else None
    return Coverage(paths, lenses, default)


def find_blocks(lines: list[str]) -> list[tuple[int, int]]:
    """(opening line, closing line) of each fenced block whose info string is BLOCK_INFO, in CommonMark's terms: a
    block opened inside another fence is that fence's text, not ours. A block never closed runs to the end of the
    document, as markdown renders it, and is returned with its end as len(lines)."""
    found, i = [], 0
    while i < len(lines):
        m = _FENCE.fullmatch(lines[i])
        if not m or (m["run"][0] == "`" and "`" in m["info"]):
            i += 1
            continue
        run = m["run"]
        close = next((j for j in range(i + 1, len(lines))
                      if re.fullmatch(rf" {{0,3}}{re.escape(run[0])}{{{len(run)},}}[ \t]*", lines[j])), len(lines))
        if m["info"] == BLOCK_INFO:
            found.append((i, close))
        i = close + 1
    return found


def split_lines(body: str) -> list[str]:
    """Lines as GitHub's markdown counts them: "\\n" only (str.splitlines also breaks at U+2028 and the like)."""
    return [l.rstrip("\r") for l in body.split("\n")]


def read_block(body: str) -> tuple[Coverage, tuple[int, int]]:
    """The one coverage block of a body and its line span, or CoverageError. Exactly one: a second block, one inside
    another fence or behind a quote marker, and one never closed are all refused."""
    lines = split_lines(body)
    blocks = find_blocks(lines)
    named = sum(1 for l in lines if _LOOKALIKE.match(l))
    if not blocks:
        raise CoverageError("the report carries no coverage block (a fenced block whose info string is "
                            f"`{BLOCK_INFO}`)")
    if len(blocks) > 1:
        raise CoverageError(f"the report carries more than one coverage block ({len(blocks)} lines open one)")
    start, close = blocks[0]
    if close >= len(lines):
        raise CoverageError("the coverage block is never closed")
    if named != 1:
        # A second opener the structural scan did not take for a block (quoted, listed, inside another fence).
        raise CoverageError(f"{named} lines open a coverage block, and only one is a block of its own")
    return parse_block("\n".join(lines[start + 1:close])), (start, close)


def render_block(coverage: Coverage) -> str:
    """The block as posted: the parsed data re-written, never the model's text, with ASCII escapes (a path's bidi
    or line-separator characters stay visible as what they are) and a fence longer than any run of backticks in it.
    Compact on one line, as the reviews write it: indentation re-expanded a block that fitted into one that did not."""
    text = json.dumps(coverage.as_json(), separators=(",", ":"), ensure_ascii=True)
    runs = [len(r) for r in re.findall(r"`+", text)]
    fence = "`" * max(3, max(runs, default=0) + 1)
    return f"{fence}{BLOCK_INFO}\n{text}\n{fence}"


def without_block(body: str, span: tuple[int, int]) -> str:
    lines = split_lines(body)
    return "\n".join(lines[:span[0]] + lines[span[1] + 1:]).strip("\n")


def partial_line(coverage: Coverage) -> str:
    n = len(coverage.not_read)
    if coverage.default_not_read:
        return f"partial coverage: {n} named path(s) and every path not named not read"
    return f"partial coverage: {n} path(s) not read" if n else ""


def marker_like_lines(body: str) -> list[int]:
    """1-based lines of a body that look like a review marker of any version: the posted body's first line is the
    marker post_review writes, and a report's own is a line a reader might take for it."""
    return [n for n, l in enumerate(split_lines(body), 1) if l.strip().startswith("<!-- agent-fabric-review")]


@dataclass(frozen=True)
class Review:
    """What a v2-looking review body reads as. `problem` is "" when marker and block both read."""
    marker: Marker | None
    coverage: Coverage | None
    problem: str

    @property
    def counts(self) -> bool:
        return bool(self.marker and self.coverage and self.coverage.complete)

    @property
    def why_not(self) -> str:
        """Why it is not coverage, for the line that shows it; "" when it is."""
        if self.problem:
            return self.problem
        if self.coverage and not self.coverage.complete:
            return partial_line(self.coverage)
        return ""


def read_review(body: str) -> Review | None:
    """None for a body that does not claim to be v2 (v1, unmarked, another marker): its first line does not open with
    the v2 prefix. Otherwise the reading, which is never an exception."""
    first = (body or "").split("\n", 1)[0].rstrip("\r")
    if not first.startswith(V2_PREFIX):
        return None
    marker = parse_marker(body)
    if marker is None:
        return Review(None, None, "the v2 marker on the first line cannot be read")
    try:
        coverage, _ = read_block(body)
    except CoverageError as e:
        return Review(marker, None, str(e))
    return Review(marker, coverage, "")


def _git(repo: str, *args: str) -> subprocess.CompletedProcess:
    """git in `repo` that never fetches. In a promisor clone a missing object otherwise starts a `git fetch` child, from
    post-review and the checkpoint reader alike, and that child writes (FETCH_HEAD, packs, config); the object is
    reported missing instead, which both callers already read as a refusal. Said twice, by the flag and by the
    environment, so a git that reads only one of them still refuses (review_mcp does the same)."""
    return subprocess.run(["git", "--no-lazy-fetch", "-C", repo, *args], capture_output=True, stdin=subprocess.DEVNULL,
                          timeout=GIT_TIMEOUT_S, env={**os.environ, "GIT_NO_LAZY_FETCH": "1"})


def diff_changes(repo: str, base: str, head: str) -> tuple[list[str], list[str]]:
    """(the paths `git diff --name-only <base>..<head>` prints, the source paths of its renames and copies) in `repo`,
    read from one `--name-status -z` so the two cannot disagree. NUL-separated so a path with a newline or a quote is
    one entry. Renames are detected, as git does by default and as the reviewer's own `git diff` shows them: pinned
    here so a user's diff.renames cannot change which paths a review owes. A source is a path the reviewer sees in
    `--name-status` and `review_diff` and a review may name; `--name-only`, the brief's own instruction, does not
    print it, so a review is never required to. Raises CoverageError when git cannot say."""
    try:
        r = _git(repo, "-c", "diff.renames=true", "diff", "--name-status", "-z", "--no-ext-diff", f"{base}..{head}")
    except (OSError, subprocess.TimeoutExpired) as e:
        raise CoverageError(f"git diff --name-status {base[:12]}..{head[:12]} could not run ({type(e).__name__})") from None
    if r.returncode != 0:
        raise CoverageError(f"git diff --name-status {base[:12]}..{head[:12]} failed: "
                            f"{r.stderr.decode(errors='replace').strip()[:200] or r.returncode}")
    fields = [f.decode("utf-8", errors="surrogateescape") for f in r.stdout.split(b"\0")]
    if fields and fields[-1] == "":
        fields.pop()   # the terminator of the last record, not an empty path
    paths: list[str] = []
    sources: list[str] = []
    i = 0
    while i < len(fields):
        status = fields[i]
        # R<score> and C<score> carry two paths (source, destination), every other status one.
        width = 2 if status[:1] in ("R", "C") else 1
        names = fields[i + 1:i + 1 + width]
        if not status or len(names) != width or not all(names):
            raise CoverageError(f"git diff --name-status {base[:12]}..{head[:12]} printed a record that cannot be read")
        paths.append(names[-1])
        sources += names[:-1]
        i += 1 + width
    return paths, sources


def diff_paths(repo: str, base: str, head: str) -> list[str]:
    """The paths of `git diff --name-only <base>..<head>`; diff_changes has the rest."""
    return diff_changes(repo, base, head)[0]


def is_ancestor(repo: str, ancestor: str, descendant: str) -> bool:
    """git merge-base --is-ancestor, exit 0 yes, 1 no; anything else (an object the clone lacks, no git) is an error."""
    try:
        r = _git(repo, "merge-base", "--is-ancestor", ancestor, descendant)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise CoverageError(f"git merge-base --is-ancestor could not run ({type(e).__name__})") from None
    if r.returncode not in (0, 1):
        raise CoverageError(f"git merge-base --is-ancestor {ancestor[:12]} {descendant[:12]} failed: "
                            f"{r.stderr.decode(errors='replace').strip()[:200] or r.returncode}")
    return r.returncode == 0


def check_paths(coverage: Coverage, expected: list[str], sources: list[str] | tuple[str, ...] = ()) -> str:
    """Why the block does not name exactly the range's paths, or "". Both directions: a path left out is a path
    unaccounted for, one named that the range does not change is a claim about nothing. `sources` (the source side of
    a rename) may be named and need not be: the range does change them, only `--name-only` does not say so."""
    for p in expected:
        _plain(p, "a changed path")
    want, have = set(expected), set(coverage.paths)
    # Without a default, a path left out is unaccounted for; with one, it is accounted for by the default.
    missing, extra = sorted(want - have) if coverage.default is None else [], sorted(have - want - set(sources))
    if missing:
        return f"the coverage block omits {len(missing)} path(s) of the range, first {missing[0]!r}"
    if extra:
        return f"the coverage block names {len(extra)} path(s) outside the range, first {extra[0]!r}"
    return ""
