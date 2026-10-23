#!/usr/bin/env python3
"""tools/fabric/review_brief.py — render a review request into the brief a
code-review dispatch carries (bin/fabric-review is the front door).

    review_brief.py render REQUEST[.yaml|.json|-]   [--allow-rationale]   the brief, to stdout
    review_brief.py check  REQUEST                                          validate only
    review_brief.py lenses                                                  the vocabulary

THE THREE PARTS OF A REVIEW. The reviewer's CONSTITUTION is its agent
file (runtime/claude-code/agents/code-review.md — its whole system
prompt). The CHARTER is what this renders: the facts of one change —
mode, repository, range, what must be true, what is out of scope — under
fixed headings the constitution names. A LENS is a file under
runtime/claude-code/review/lenses/ whose body is inlined under the
brief's Lenses heading; `general` is always on for a review (a re-review
carries only the lenses it names: it verifies, it does not explore).

WHAT A BRIEF CARRIES AND WHAT IT MUST NOT. Facts: a requirement, an
invariant, a compatibility target, a threat model, a boundary — WHAT must
be true. Never the author's conclusions: that the change is correct, how
it achieves something, what was fixed, where the dispatcher suspects the
defect is. A reviewer told why the code is right agrees with it; the
value of the review is that it does not know. So the free-text fields
are linted for verdict-shaped sentences and a hit refuses the render
(--allow-rationale renders it anyway, flagged under Brief notes so the
reviewer sets it aside — the constitution's verdict rule).

THIS IS ERGONOMICS AND A LINT, NOT AUTHORISATION. The dispatch guard
(runtime/claude-code/hooks/agent-dispatch-guard.sh) decides what may be
dispatched from four fields of the tool call and never reads the prompt;
a hook that granted or refused on prompt text would be a hole any
phrasing could walk through (policies/subagent-dispatch/SKILL.md). This
tool makes the right brief easy and the wrong one visible, before the
dispatch. A hand-written prose brief remains valid: the constitution
says so.

The request is a flat document — scalars and lists of strings — so a
small YAML subset (top-level `key: value`, `key:` followed by `- item`
lines, `[a, b]` inline lists, quoted strings, `>-` folded scalars) is
read here without a dependency; JSON is accepted as is. Unknown keys are
refused: a misspelt `invariant:` must not vanish into a brief that then
claims nothing was required.
"""
from __future__ import annotations

import contextlib
import datetime
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "runtime"))

import review_lines  # noqa: E402

FABRIC_ROOT = os.environ.get("AGENT_FABRIC_ROOT") or os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
LENSES_DIR = os.path.join(FABRIC_ROOT, "runtime", "claude-code", "review", "lenses")
BRIEF_VERSION = "agent-fabric review brief v1"

MODES = ("review", "re-review", "finding-adjudication")
# What the dispatch header calls each mode; second-engine-review is written
# by review_codex.py itself, which passes it to render().
PURPOSES = {"review": "primary-review", "re-review": "re-review", "finding-adjudication": "finding-adjudication"}
EVIDENCE_MODES = ("pinned", "working-tree")
SCALAR_KEYS = ("mode", "repository", "range", "diff", "objective", "previous_findings",
               "job_id", "review_id", "evidence", "card_base")
# A PR number and a review round: a request in YAML gives a string, in JSON a number.
COUNT_KEYS = ("pr", "review_round")
DISPATCH_VERSION = "agent-fabric-dispatch v1"
LIST_KEYS = ("requirements", "invariants", "compatibility", "threat_model", "scope", "out_of_scope", "lenses")
KNOWN_KEYS = SCALAR_KEYS + COUNT_KEYS + LIST_KEYS
# The free text the rationale lint reads: everything a dispatcher writes in words.
FREE_TEXT_KEYS = ("objective", "requirements", "invariants", "compatibility", "threat_model", "scope", "out_of_scope")
RANGE_RE = re.compile(r"^[A-Za-z0-9_./~^-]+\.\.[A-Za-z0-9_./~^-]+$")
LENS_NAME_RE = re.compile(r"^[a-z][a-z0-9-]*$")
JOB_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
COUNT_RE = re.compile(r"^[1-9][0-9]*$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
MANY_LENSES = 3
# The project's own text a reviewer gets (agent-fabric ADR-020): the reviewer
# runs without the project's instruction files (omitClaudeMd), so this card
# is all of it, and it is re-sent every turn: a cap, refused over, not truncated.
# It is read from the request's BASE commit, never the working tree or the
# head: a change under review must not write its own rules of review. The
# head's copy is evidence, and the card's own diff is in the reviewed range.
CARD_PATH = ".agent-fabric/review-card.md"
CARD_CAP = 2048

# Verdict-shaped phrasing: the author's conclusion about the change, not
# a fact about what must be true. Kept short and each one actionable —
# the refusal says "state what must be true instead". Case-insensitive.
RATIONALE_PATTERNS = [
    (r"\bcorrectly\b", "asserts correctness"),
    (r"\bfix(?:es|ed)\b", "names what was fixed"),
    (r"\bensures?\b", "asserts what the change guarantees"),
    (r"\bis (?:now )?(?:safe|correct|right|sound)\b", "asserts correctness"),
    (r"\bthe (?:bug|defect|issue|problem) (?:was|is)\b", "explains the defect for the reviewer"),
    (r"\bI (?:think|believe|suspect)\b", "the dispatcher's opinion"),
    (r"\bsuspect(?:ed)?\b", "points the reviewer at a suspected place"),
    (r"\bthe (?:change|implementation|patch|PR) (?:adds|introduces|makes|removes|replaces|refactors|correctly)\b", "describes what the change does — the reviewer reconstructs that"),
    (r"(?:^|[.;:]\s*)because\b", "explains the author's reasoning"),
    (r"\bshould (?:be|now be) (?:fine|ok|okay|correct|safe)\b", "asserts correctness"),
]
_RATIONALE = [(re.compile(p, re.I | re.M), why) for p, why in RATIONALE_PATTERNS]


class RequestError(Exception):
    """One or more refusals, each naming the field."""

    def __init__(self, problems: list[str]):
        super().__init__("\n".join(problems))
        self.problems = problems


# --- reading the request -----------------------------------------------------

def _unquote(v: str) -> str:
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        return v[1:-1]
    return v


def _inline_list(v: str) -> list[str]:
    """`[a, "b, c", 'd']`. A quote opens an item only at the item's start
    (an apostrophe inside a plain item is text); an unterminated quote is
    refused rather than absorbing the rest of the list."""
    inner = v.strip()[1:-1].strip()
    if not inner:
        return []
    items, cur, quote = [], "", None
    for ch in inner:
        if quote:
            if ch == quote:
                quote = None
            else:
                cur += ch
        elif ch in "\"'" and cur.strip() == "":
            quote = ch; cur = ""
        elif ch == ",":
            items.append(cur.strip()); cur = ""
        else:
            cur += ch
    if quote:
        raise RequestError([f"request: unterminated {quote} quote in {v.strip()!r}"])
    items.append(cur.strip())
    return [i for i in items if i != ""]


def _strip_comment(line: str, value_at: int = 0) -> str:
    """A `#` outside quotes that stands alone — at the start or after
    whitespace, and followed by whitespace or the end — begins a comment;
    a `#` inside a quoted string is text. So is a `#` glued to what
    follows it, quoted or not: `PR #934`, `#pragma`, `#12`. YAML would
    cut those lines there, and the brief silently rendered "No #pragma …
    is introduced" as "No" and lost the rest of a folded objective at
    "PR #934" (backend-dev-01, 2026-09-25); the subset keeps them as text.
    A quote opens a string only where a value starts (`value_at`, or after
    a `- `): an apostrophe inside a plain value is text."""
    quote = None
    since = value_at                      # where the current value or item began
    inline_list = line[value_at:].lstrip().startswith("[")
    for i, ch in enumerate(line):
        if quote:
            if ch == quote:
                quote = None
        elif ch in "\"'" and line[since:i].strip() in ("", "["):
            quote = ch
        elif inline_list and ch in "[,":
            since = i + 1                 # an item of an inline list starts after `[` or `,`
        elif ch == "#" and (i == 0 or line[i - 1] in " \t") and (i + 1 == len(line) or line[i + 1] in " \t\r"):
            return line[:i].rstrip()
    return line.rstrip()


def _value_start(line: str) -> int:
    """Where the value begins on a `key: value` or `- item` line."""
    st = line.lstrip()
    if st.startswith("- "):
        return len(line) - len(st) + 2
    if ":" in line:
        return line.index(":") + 1
    return 0


def parse_request(text: str) -> dict:
    """A flat YAML subset, or JSON. Returns {key: str | list[str]}; every
    key seen, so validate() can refuse the unknown ones."""
    stripped = text.lstrip()
    if stripped.startswith("{"):
        def no_duplicates(pairs):
            out: dict = {}
            for k, v in pairs:
                if k in out:
                    raise RequestError([f"request: {k}: given twice; the earlier value would be lost"])
                out[k] = v
            return out
        doc = json.loads(text, object_pairs_hook=no_duplicates)
        if not isinstance(doc, dict):
            raise RequestError(["request: the JSON document is not an object"])
        return doc
    doc: dict = {}
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        raw = lines[i]
        line = _strip_comment(raw, _value_start(raw))
        i += 1
        if not line.strip():
            continue
        if line.startswith((" ", "\t")):
            raise RequestError([f"request line {i}: unexpected indentation ({raw.strip()!r}); the request is flat (key: value, or key: then - items)"])
        if ":" not in line:
            raise RequestError([f"request line {i}: not `key: value` ({raw.strip()!r})"])
        key, _, value = line.partition(":")
        key = key.strip(); value = value.strip()
        if key in doc:
            raise RequestError([f"request line {i}: {key}: given twice; the earlier value would be lost"])
        if value in ("", "|", "|-", ">", ">-"):
            # a block: `- item` lines, or a folded/literal scalar. Each
            # block line is comment-stripped like a top-level one.
            block: list[str] = []
            while i < len(lines) and (lines[i].startswith((" ", "\t")) or lines[i].strip() == ""):
                stripped = _strip_comment(lines[i], _value_start(lines[i]) if lines[i].strip().startswith("- ") else len(lines[i]) - len(lines[i].lstrip()))
                if stripped.strip() != "":
                    block.append(stripped)
                i += 1
            if not block:
                doc[key] = [] if key in LIST_KEYS else ""
            elif value in ("|", "|-", ">", ">-"):
                joiner = " " if value.startswith(">") else "\n"
                doc[key] = joiner.join(b.strip() for b in block)
            elif all(b.strip().startswith("- ") or b.strip() == "-" for b in block):
                doc[key] = [_unquote(b.strip()[2:]) for b in block if b.strip() != "-"]
            else:
                raise RequestError([f"request: {key}: a block must be `- item` lines or a folded scalar (>-)"])
        elif value.startswith(("|", ">")):
            raise RequestError([f"request line {i}: {key}: a block indicator ({value.split()[0]}) takes no text on its line; put the text on the indented lines below"])
        elif value.startswith("[") and value.endswith("]"):
            doc[key] = [_unquote(x) for x in _inline_list(value)]
        else:
            doc[key] = _unquote(value)
    return doc


# --- the vocabulary ----------------------------------------------------------

def lenses(lenses_dir: str | None = None) -> dict[str, dict]:
    """{name: {description, body}} from the lens directory — the vocabulary."""
    base = lenses_dir or LENSES_DIR
    out: dict[str, dict] = {}
    if not os.path.isdir(base):
        return out
    for fn in sorted(os.listdir(base)):
        if not fn.endswith(".md"):
            continue
        text = open(os.path.join(base, fn), encoding="utf-8").read()
        m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
        if not m:
            continue
        meta = {k.strip(): v.strip() for k, v in (l.split(":", 1) for l in m.group(1).split("\n") if ":" in l)}
        out[fn[:-3]] = {"description": meta.get("description", ""), "body": text[m.end():].strip()}
    return out


def _git(repo: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, timeout=60)


def _commit_of(repo: str, rev: str) -> str | None:
    """The commit `rev` names now, as review_rounds.py resolves a head."""
    r = _git(repo, "rev-parse", "--verify", "-q", f"{rev}^{{commit}}")
    return r.stdout.decode().strip() if r.returncode == 0 else None


def default_ref(repo: str) -> str | None:
    """The ref the default branch is read from: the registry's default_branch
    for the repository's project, else origin's HEAD, else main; the
    remote-tracking ref where there is one (a local copy of it may be stale)."""
    names: list[str] = []
    try:
        import workingcopy
        entry = (workingcopy.load_registry().get("projects") or {}).get(workingcopy.resolve(repo).get("project") or "")
        if isinstance(entry, dict) and isinstance(entry.get("default_branch"), str):
            names.append(entry["default_branch"])
    except Exception:  # an unreadable registry falls through to what git says
        pass
    head = _git(repo, "symbolic-ref", "-q", "--short", "refs/remotes/origin/HEAD")
    if head.returncode == 0 and head.stdout.decode().strip().startswith("origin/"):
        names.append(head.stdout.decode().strip()[len("origin/"):])
    names.append("main")
    for name in names:
        for ref in (f"origin/{name}", name):
            if _commit_of(repo, ref):
                return ref
    return None


def _default_tip(repo: object) -> str | None:
    """The default branch's tip, where a diff file (a working tree with no
    base commit) reads the card: the same governed source as a ranged review's."""
    ref = default_ref(repo) if isinstance(repo, str) and repo else None
    return _commit_of(repo, ref) if ref else None


def checkpoint(pr: int, head_sha: str, repo: str) -> tuple[str, str, str] | None:
    """(base, head, card) of the PR's last review a re-review may start from,
    or None. A seam: tests replace it, since the real one asks GitHub."""
    from github.review_checkpoint import last_checkpoint
    return last_checkpoint(pr, head_sha, lambda card: config_fingerprint(repo, card), cwd=repo)


def resolve_range(req: dict) -> tuple[dict | None, list[str]]:
    """({base_sha, head_sha, card_base}, refusals) for a ranged request: both
    ends resolved now, and the card's base (the request's `card_base`, which
    review_rounds carries across a re-review, else the range's base) refused
    unless it is an ancestor of the default branch. None for a diff file."""
    rng, repo = req.get("range"), req.get("repository")
    if not (isinstance(rng, str) and RANGE_RE.fullmatch(rng) and isinstance(repo, str)):
        return None, []
    base, head = rng.split("..", 1)
    base_sha, head_sha = _commit_of(repo, base), _commit_of(repo, head)
    problems = [f"range: {end!r} is not a commit in {repo}" for end, sha in ((base, base_sha), (head, head_sha)) if not sha]
    if problems:
        return None, problems
    wanted = req.get("card_base")
    card_base = _commit_of(repo, wanted) if isinstance(wanted, str) and wanted else base_sha
    if not card_base:
        return None, [f"card_base: {wanted!r} is not a commit in {repo}"]
    pr = _count(req.get("pr"))
    if req.get("mode") == "re-review" and pr:
        # A PR's re-review starts where its last posted review stopped, read
        # from that review's v2 marker, never from what the dispatcher typed
        # (agent-fabric ADR-065 §5 rule 5). Without a PR there is no posted
        # review to read, and the typed range stands.
        cp = checkpoint(pr, head_sha, repo)
        if cp is None:
            return None, [f"re-review: #{pr} has no review a re-review can start from (a v2 review, every path read, of an "
                          f"ancestor of {head_sha[:12]}, under today's config); render a full review (mode: review)"]
        _, cp_head, cp_card = cp
        if base_sha != cp_head:
            return None, [f"range: a re-review of #{pr} starts at its last review's head {cp_head[:12]}, not {base!r} "
                          f"({base_sha[:12]}); the range is {cp_head}..{head}"]
        if wanted and card_base != cp_card:
            return None, [f"card_base: #{pr}'s last review read the card at {cp_card[:12]}, not {wanted!r}; leave card_base "
                          f"out and it is taken from that review"]
        card_base = cp_card
    ref = default_ref(repo)
    if ref is None:
        return None, [f"range: the default branch of {repo} cannot be found, so base {base!r} cannot be checked against it"]
    if _git(repo, "merge-base", "--is-ancestor", card_base, ref).returncode != 0:
        return None, [f"range: base {base!r} ({card_base[:12]}) is not an ancestor of {ref}; the project review card is read from "
                      f"the base, and only a commit the default branch contains may govern a review"
                      + ("" if wanted else "; name card_base (a full commit id the default branch contains, the first round's base) in the request")]
    return {"base_sha": base_sha, "head_sha": head_sha, "card_base": card_base}, []


def card(repo: object, base_sha: str | None) -> tuple[str | None, str | None]:
    """(card text, refusal) for .agent-fabric/review-card.md as it is at
    `base_sha`. No base (a diff file) or no card there: (None, None). Over
    CARD_CAP bytes: a refusal naming the file and its size, never a cut
    card: a truncated rule would read as a whole one."""
    if not isinstance(repo, str) or not repo or not base_sha:
        return None, None
    spec = f"{base_sha}:{CARD_PATH}"
    if _git(repo, "cat-file", "-e", spec).returncode != 0:
        return None, None
    r = _git(repo, "show", spec)
    if r.returncode != 0:
        return None, f"{spec}: the project review card cannot be read ({r.stderr.decode(errors='replace').strip()})"
    if len(r.stdout) > CARD_CAP:
        return None, f"{spec}: the project review card is {len(r.stdout)} bytes, over the {CARD_CAP}-byte cap; shorten it"
    return r.stdout.decode("utf-8", errors="replace").strip(), None


def evidence_mode(req: dict) -> str:
    """pinned: the reviewer reads the range's commits through git. working-tree:
    it reads the files on disk. A range review defaults to pinned; a diff file
    names no commits, so it is working-tree."""
    return req.get("evidence") or ("pinned" if req.get("range") else "working-tree")


def _count(v: object) -> int | None:
    return int(v) if isinstance(v, (int, str)) and not isinstance(v, bool) and COUNT_RE.fullmatch(str(v)) else None


# --- validation --------------------------------------------------------------

def validate(req: dict, lenses_dir: str | None = None) -> list[str]:
    """Every refusal, by field. Empty means the request renders."""
    problems: list[str] = []
    for key in req:
        if key not in KNOWN_KEYS:
            close = [k for k in KNOWN_KEYS if k.startswith(key[:4])]
            problems.append(f"{key}: not a request field" + (f" (did you mean {close[0]}?)" if close else "") + f"; the fields are {', '.join(KNOWN_KEYS)}")
    for key in SCALAR_KEYS:
        if key in req and not isinstance(req[key], str):
            problems.append(f"{key}: must be one value, not a list")
    for key in COUNT_KEYS:
        if key in req and _count(req[key]) is None:
            problems.append(f"{key}: {req[key]!r} is not a positive number")
    if isinstance(req.get("job_id"), str) and not JOB_ID_RE.fullmatch(req["job_id"]):
        problems.append(f"job_id: {req['job_id']!r} is not a job id")
    if isinstance(req.get("review_id"), str) and (not req["review_id"].strip() or "\n" in req["review_id"]):
        problems.append("review_id: must be one non-empty line")
    if isinstance(req.get("card_base"), str) and not SHA_RE.fullmatch(req["card_base"]):
        problems.append(f"card_base: {req['card_base']!r} is not a full commit id")
    for key in LIST_KEYS:
        if key in req and not isinstance(req[key], list):
            problems.append(f"{key}: must be a list (- item lines, or [a, b])")
        elif key in req and any(not isinstance(x, str) or not x.strip() for x in req[key]):
            problems.append(f"{key}: every item must be a non-empty string")
    mode = req.get("mode")
    if mode not in MODES:
        problems.append(f"mode: {mode!r}; must be one of {', '.join(MODES)}")
    if "evidence" in req and req["evidence"] not in EVIDENCE_MODES:
        problems.append(f"evidence: {req['evidence']!r}; must be one of {', '.join(EVIDENCE_MODES)}")
    repo = req.get("repository")
    if not isinstance(repo, str) or not repo:
        problems.append("repository: required (the live clone's path)")
    elif not os.path.isdir(os.path.join(repo, ".git")) and not os.path.isfile(os.path.join(repo, ".git")):
        problems.append(f"repository: {repo} is not a git working copy")
    rng, diff = req.get("range"), req.get("diff")
    if bool(rng) == bool(diff):
        problems.append("range / diff: exactly one — a base..head range, or a diff file in the scratchpad")
    if isinstance(rng, str) and rng and not RANGE_RE.fullmatch(rng):
        problems.append(f"range: {rng!r} is not base..head")
    if isinstance(diff, str) and diff and not os.path.isfile(diff):
        problems.append(f"diff: {diff} does not exist")
    if diff and req.get("evidence") == "pinned":
        problems.append("evidence: pinned needs a range; a diff file names no commits to read")
    if isinstance(rng, str) and RANGE_RE.fullmatch(rng) and isinstance(repo, str) and repo \
            and (os.path.isdir(os.path.join(repo, ".git")) or os.path.isfile(os.path.join(repo, ".git"))):
        info, refused = resolve_range(req)
        problems += refused
        if info and (refusal := card(repo, info["card_base"])[1]):
            problems.append(refusal)
    elif isinstance(diff, str) and diff and not rng and isinstance(repo, str) and repo \
            and (refusal := card(repo, _default_tip(repo))[1]):
        # render reads a diff file's card at the default tip and drops the
        # refusal, so an over-cap card would silently render as none.
        problems.append(refusal)
    if mode == "re-review" or "previous_findings" in req:
        pf = req.get("previous_findings")
        if mode not in ("re-review", "finding-adjudication"):
            problems.append("previous_findings: only on a re-review (mode: re-review) or a finding-adjudication")
        elif not isinstance(pf, str) or not pf:
            problems.append("previous_findings: required on a re-review (the previous report, a file)" if mode == "re-review"
                            else "previous_findings: names the findings to judge, a file")
        elif not os.path.isfile(pf):
            problems.append(f"previous_findings: {pf} does not exist")
    if mode != "re-review" and not (req.get("objective") if isinstance(req.get("objective"), str) else "").strip():
        problems.append("objective: required on a review (not a re-review) — one line, what must be true of the system")
    known = lenses(lenses_dir)
    for name in req.get("lenses") or []:
        if not isinstance(name, str) or not LENS_NAME_RE.fullmatch(name or ""):
            problems.append(f"lenses: {name!r} is not a lens name")
        elif name not in known:
            problems.append(f"lenses: {name!r} is not a lens (fabric-review lenses: {', '.join(sorted(known)) or 'none'})")
    return problems


def rationale_findings(req: dict) -> list[tuple[str, str, str]]:
    """(field, sentence, why) for every verdict-shaped sentence in the free text."""
    hits: list[tuple[str, str, str]] = []
    for key in FREE_TEXT_KEYS:
        value = req.get(key)
        texts = [t for t in value if isinstance(t, str)] if isinstance(value, list) else ([value] if isinstance(value, str) else [])
        for text in texts:
            for pat, why in _RATIONALE:
                m = pat.search(text)
                if m:
                    hits.append((key, text.strip(), why))
                    break
    return hits


# --- rendering ---------------------------------------------------------------

def _items(values: list[str] | None) -> str:
    return "\n".join(f"- {v}" for v in values) if values else "(none stated)"


def _fence(text: str, info: str = "") -> list[str]:
    """`text` verbatim inside a fence longer than any backtick run in it."""
    fence = "`" * max(3, max((len(m) for m in re.findall(r"`+", text)), default=0) + 1)
    return [fence + info, text, fence]


def _active_job() -> str | None:
    """fabric-jobs' active job id for this login, if there is one."""
    try:
        import identity
        job = next((j for j in identity.read_jobs()["jobs"] if j.get("state") == "active"), None)
        return job["id"] if job else None
    except (Exception, SystemExit):  # no list, or not this host's: no job to name
        return None


def default_review_id(req: dict) -> str | None:
    """A review's id, shared by its rounds: the request's own, else the
    repository's name and the PR, which every round of one PR has."""
    if req.get("review_id"):
        return req["review_id"]
    pr = _count(req.get("pr"))
    repo = req.get("repository")
    return f"{os.path.basename(os.path.normpath(repo))}#{pr}" if pr and isinstance(repo, str) and repo else None


def dispatch_header(req: dict, info: dict | None, engine: str, purpose: str | None,
                    dispatch_id: str | None, started_at: str | None) -> list[str]:
    """The brief's first block: who this dispatch is, for whatever attributes
    its cost (devex-tooling's hook reads it from the transcript's first user
    message). Machine facts only; no field is the dispatcher's opinion."""
    repo = req["repository"]
    remote = None
    try:
        import workingcopy
        r = workingcopy.resolve(repo)
        project, remote = r.get("project"), r.get("remote")
        remote = workingcopy.canonical_remote(remote) if remote else None
    except Exception:  # an unregistered clone has no project; the header says null
        project = None
    mode = req["mode"]
    rnd = _count(req.get("review_round"))
    header = {
        "dispatch_id": dispatch_id or str(uuid.uuid4()),
        "parent_session_id": os.environ.get("CLAUDE_CODE_SESSION_ID") or None,
        "job_id": req.get("job_id") or _active_job(),
        "project": project,
        "repository": remote or repo,
        "pr": _count(req.get("pr")),
        "review_id": default_review_id(req),
        "review_round": rnd if rnd else (1 if mode != "re-review" else None),
        "purpose": purpose or PURPOSES[mode],
        "engine": engine,
        "evidence_mode": evidence_mode(req),
        "base_sha": info["base_sha"] if info else None,
        "head_sha": info["head_sha"] if info else None,
        "card_base": info["card_base"] if info else None,
        "config": config_fingerprint(repo, info["card_base"]) if info else None,
        "started_at": started_at or datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    return _fence(json.dumps(header, indent=2), DISPATCH_VERSION)


AGENT_FILE = os.path.join(FABRIC_ROOT, "runtime", "claude-code", "agents", "code-review.md")


def config_fingerprint(repo: str, card_base: str | None) -> str:
    """sha256 of what a review's verdict depends on besides the range: the
    review class's agent file as committed here, the project card at
    card_base, and this renderer's versions (agent-fabric ADR-065 §2 C). A
    re-review may start from an earlier review's head only while this is
    unchanged; any part missing or unreadable is hashed as its absence, so
    it differs from a present one rather than matching an empty one."""
    h = hashlib.sha256()
    try:
        agent = open(AGENT_FILE, "rb").read()
    except OSError:
        agent = None
    text, refusal = card(repo, card_base)
    for label, part in (("agent", agent), ("card", None if refusal else (text.encode() if text is not None else None)),
                        ("brief", BRIEF_VERSION.encode()), ("dispatch", DISPATCH_VERSION.encode())):
        # Length-prefixed, so no two different tuples of parts hash alike.
        h.update(label.encode() + b"\0" + (b"-" if part is None else str(len(part)).encode() + b"\0" + part))
    return h.hexdigest()


class EvidenceRefused(Exception):
    """The head worktree cannot be made or reused; the message names why."""


def evidence_path(repo_name: str, head_sha: str) -> str:
    """Where a pinned review's head is checked out. ONE function for the brief
    that makes it and `save` that removes it: save never takes a path from a
    report's text. tempfile.gettempdir() is the launcher's per-login TMPDIR,
    not a home's hidden dir, which the review Bash guard refuses as a search path."""
    return os.path.join(tempfile.gettempdir(), "fabric-review", f"{repo_name}-{head_sha[:12]}")


def repo_name_of(repo: str) -> str:
    return os.path.basename(os.path.normpath(os.path.abspath(repo)))


def worktree_head(path: str) -> str | None:
    """HEAD of the git worktree AT path (not of a repository merely above it), else None."""
    if not os.path.isdir(path) or os.path.islink(path):
        return None
    top = subprocess.run(["git", "-C", path, "rev-parse", "--show-toplevel"], capture_output=True, text=True, timeout=30)
    if top.returncode != 0 or os.path.realpath(top.stdout.strip()) != os.path.realpath(path):
        return None
    head = subprocess.run(["git", "-C", path, "rev-parse", "HEAD"], capture_output=True, text=True, timeout=30)
    return head.stdout.strip() if head.returncode == 0 else None


def dispatching_session_pid(proc: str = "/proc", start: int | None = None) -> int | None:
    """Pid of the nearest ancestor of `start` (default: this process) whose comm is
    `claude`, or None. `proc` is injectable so a test can lay out a fake process tree."""
    pid = os.getpid() if start is None else start
    seen: set[int] = set()
    while pid > 1 and pid not in seen:
        seen.add(pid)
        try:
            with open(os.path.join(proc, str(pid), "comm"), encoding="utf-8", errors="replace") as f:
                comm = f.read().strip()
            if comm == "claude":
                return pid
            with open(os.path.join(proc, str(pid), "stat"), encoding="utf-8", errors="replace") as f:
                # comm may hold spaces and parens: the fields after the LAST ')' are state, ppid, ...
                pid = int(f.read().rsplit(")", 1)[1].split()[1])
        except (OSError, ValueError, IndexError):
            return None
    return None


def mark_in_use(path: str, proc: str = "/proc") -> None:
    """Write `fabric-in-use` (pid line, UTC timestamp line) into the worktree's own git
    directory. `fabric-branches --sweep` once removed a pinned evidence worktree while
    a review still read it; it keeps one whose git dir names a live pid. The git dir,
    never the tree: the reviewer reads the tree as the head, and ensure_head_worktree
    refuses a tree that differs from it. No claude ancestor (a shell, a test) writes
    nothing, so the sweep behaves as before. A failure never fails the brief."""
    pid = dispatching_session_pid(proc)
    if pid is None:
        return
    tmp = None
    try:
        r = subprocess.run(["git", "-C", path, "rev-parse", "--absolute-git-dir"], capture_output=True, text=True, timeout=30)
        if r.returncode != 0:
            raise OSError(r.stderr.strip() or "git rev-parse --absolute-git-dir failed")
        gitdir = r.stdout.strip()
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        fd, tmp = tempfile.mkstemp(prefix=".fabric-in-use.", dir=gitdir)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(f"{pid}\n{stamp}\n")
        os.chmod(tmp, 0o600)
        os.replace(tmp, os.path.join(gitdir, "fabric-in-use"))
        tmp = None
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"fabric-review: could not mark {path} in use ({exc}); the branch sweep may take the worktree", file=sys.stderr)
    finally:
        if tmp:
            with contextlib.suppress(OSError):
                os.unlink(tmp)


def ensure_head_worktree(repo: str, head_sha: str) -> tuple[str, bool]:
    """(path, made_by_this_call): a detached worktree of head_sha, made or
    reused. --detach so no branch and no branch.* config lands in the clone
    (tests/test_session_start.py snapshots it). Anything else at the path is
    refused, never deleted."""
    path = evidence_path(repo_name_of(repo), head_sha)
    root = os.path.dirname(path)
    os.makedirs(root, mode=0o700, exist_ok=True)
    os.chmod(root, 0o700)
    try:
        if os.path.lexists(path):
            if worktree_head(path) != head_sha:
                raise EvidenceRefused(f"{path} exists and is not a worktree at {head_sha[:12]}; "
                                      "it is not mine to delete: move it away or remove it, then render again")
            # A reviewer reads this tree as the head: a tracked edit would be evidence that is not the head.
            st = _git(path, "status", "--porcelain", "--untracked-files=no")
            changed = st.stdout.decode(errors="replace").splitlines()
            if st.returncode != 0 or changed:
                raise EvidenceRefused(f"{path} is not clean ({changed[0][3:] if changed else st.stderr.decode(errors='replace').strip()}); "
                                      "it is not mine to delete: restore or remove it, then render again")
            mark_in_use(path)
            return path, False
        r = _git(repo, "worktree", "add", "--detach", path, head_sha)
        # A cleaned temp dir leaves the clone's registration behind; prune drops only registrations whose path is gone.
        if r.returncode != 0 and b"missing but already registered" in r.stderr:
            _git(repo, "worktree", "prune")
            r = _git(repo, "worktree", "add", "--detach", path, head_sha)
        if r.returncode != 0:
            raise EvidenceRefused(f"git worktree add --detach {path} {head_sha[:12]} failed: {r.stderr.decode(errors='replace').strip()}")
    except subprocess.TimeoutExpired as exc:
        raise EvidenceRefused(f"{' '.join(map(str, exc.cmd))} timed out after {exc.timeout:g}s; {path} may be half made: check it, then render again")
    mark_in_use(path)
    return path, True


def prepare_evidence(req: dict) -> tuple[str | None, bool]:
    """(head worktree, made_by_this_call) for a pinned request with a range;
    (None, False) for a working-tree or diff-file request, which read what is on disk."""
    if evidence_mode(req) != "pinned" or not req.get("range"):
        return None, False
    info, _ = resolve_range(req)  # an unresolvable range is validate()'s refusal, raised by render
    return ensure_head_worktree(req["repository"], info["head_sha"]) if info else (None, False)


def refusals(req: dict, allow_rationale: bool = False, lenses_dir: str | None = None) -> list[str]:
    """Every refusal render() raises that needs no evidence: what a caller
    runs before it makes a worktree, so a request that will not render creates nothing."""
    problems = validate(req, lenses_dir)
    if not allow_rationale:
        problems += [f"{field}: {sentence!r} — {why}; state what must be true instead (or --allow-rationale to render it flagged)"
                     for field, sentence, why in rationale_findings(req)]
    return problems


@contextlib.contextmanager
def pinned_evidence(req: dict, allow_rationale: bool = False):
    """Yields the pinned head's worktree path (None when the request pins none),
    after `refusals` pass. A failure inside the block removes the worktree this
    call made, never a reused one: a render that refuses leaves nothing behind."""
    if (problems := refusals(req, allow_rationale)):
        raise RequestError(problems)
    path, made = prepare_evidence(req)
    try:
        yield path
    except BaseException:
        if made and path:
            with contextlib.suppress(subprocess.TimeoutExpired):
                _git(req["repository"], "worktree", "remove", "--force", path)
        raise


def _evidence_line(req: dict, info: dict | None, path: str | None) -> str | None:
    if not (path and info and evidence_mode(req) == "pinned"):
        return None
    return (f"Evidence: pinned. The range's head {info['head_sha'][:12]} is checked out, detached, at {path}: read and run the "
            "head's files there, naming that path in each command (no cd; git -C <path> for git); it is read-only for you, and you "
            "make no extract or copy of your own. The clone at the path above may be a different state; git show <sha>:path stays valid.")


EVIDENCE_LINE = {
    "pinned": "Evidence: pinned. Read the range's commits through git (git show <sha>:path, git diff, git log); the files on disk may be a different state.",
    "working-tree": "Evidence: working-tree. Read the files on disk; they are the state under review.",
}


def render(req: dict, lenses_dir: str | None = None, allow_rationale: bool = False,
           delta: dict | None = None, engine: str = "claude", purpose: str | None = None,
           dispatch_id: str | None = None, started_at: str | None = None,
           evidence_path: str | None = None) -> str:
    """The brief, or a RequestError naming every problem. Byte-stable for
    the same request and lens files. `delta` is what review_rounds derives
    for a re-review and keeps out of the saved request: {"diff": the range's
    diff text, or None with "note" and "stat" when it was too large,
    "locators": lines, "symbols": lines}; the brief's format lives here and
    nowhere else. The first block is the dispatch header; its dispatch_id and
    started_at are minted here, so two renders differ in exactly those (and
    tests pass them in). `evidence_path` is the pinned head's worktree, made by
    the caller (prepare_evidence), so that rendering has no side effect."""
    rationale = rationale_findings(req)
    if (problems := refusals(req, allow_rationale, lenses_dir)):
        raise RequestError(problems)
    known = lenses(lenses_dir)
    mode = req["mode"]
    # A review always carries general; a re-review verifies the new hunks
    # against the previous findings and carries only a lens it names.
    names = list(dict.fromkeys(([] if mode == "re-review" else ["general"]) + list(req.get("lenses") or [])))
    info, _ = resolve_range(req)
    out = dispatch_header(req, info, engine, purpose, dispatch_id, started_at)
    out += [f"# Review brief ({BRIEF_VERSION})", "## Mode", mode,
            "## Repository", f"{req['repository']} (the live clone; read-only for you)", _evidence_line(req, info, evidence_path) or EVIDENCE_LINE[evidence_mode(req)],
           "## Range", req["range"] if req.get("range") else f"diff file: {req['diff']} (the range is not yet pushed; the tree is the same clone)"]
    out += ["## Objective", (req.get("objective") or "").strip() or "(none stated)"]
    for key, heading in (("requirements", "Requirements"), ("invariants", "Invariants"), ("compatibility", "Compatibility"),
                         ("threat_model", "Threat model"), ("scope", "Scope"), ("out_of_scope", "Out of scope")):
        out += [f"## {heading}", _items(req.get(key))]
    text, _ = card(req["repository"], info["card_base"] if info else _default_tip(req["repository"]))
    out += ["## Project review card", text if text else "(none)"]
    if mode == "re-review" or (mode == "finding-adjudication" and req.get("previous_findings")):
        # Fenced: the previous report carries headings at the brief's own
        # level, and verbatim inside a fence is still verbatim. The fence
        # is longer than any backtick run in the report (every conforming
        # report quotes hunks in ``` blocks), so it closes where we close it.
        report = open(req["previous_findings"], encoding="utf-8").read().rstrip()
        fence = "`" * max(3, max((len(m) for m in re.findall(r"`+", report)), default=0) + 1)
        if mode == "re-review":
            out += ["## Previous findings", "Start from the range above and these findings, answering each by number."]
        else:
            out += ["## Findings to judge", "These are the findings to judge, from the range above: answer each by number."]
        out += [fence + "markdown", report, fence]
        if delta and mode == "re-review":
            if delta.get("diff") is not None:
                out += ["## Re-review diff", "The exact diff of the range above."] + _fence(delta["diff"], "diff")
            else:
                out += ["## Re-review diff", delta.get("note", "The diff was too large to embed."),
                        "The diffstat of the range above:"] + _fence(delta.get("stat", ""))
            out += ["## Locators",
                    "Answer each previous finding from these and the diff above; widen only to establish the fix's semantics or to detect a regression, and say what you widened to and why.",
                    "Each previous finding's file:line at the old head, and the same region at the new head:"]
            out += list(delta.get("locators") or []) or ["(no previous finding names a file:line)"]
            out += ["Each changed hunk's enclosing symbol, where the diff names one:"]
            out += list(delta.get("symbols") or []) or ["(none)"]
    out.append("## Lenses")
    if not names:
        out.append("(none named; the constitution's method applies)")
    for name in names:
        out += [f"### {name}", known[name]["body"]]
    if rationale:
        out.append("## Brief notes (dispatcher-asserted, not facts)")
        out.append("The dispatcher rendered these with --allow-rationale; they are the author's conclusions, not evidence — set them aside and say so:")
        out += [f"- {field}: {sentence}" for field, sentence, _ in rationale]
    if engine == "claude":
        # Codex's body is rendered by our code from its structured answer (review_codex.render_review), and the
        # brief it gets adds only its answer shape (ADR-053 rule 1).
        out += ["## Report lines"] + review_lines.report_rules(mode)
    return "\n".join(out) + "\n"


# --- CLI ---------------------------------------------------------------------

def _load(path: str) -> dict:
    text = sys.stdin.read() if path == "-" else open(path, encoding="utf-8").read()
    return parse_request(text)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__.split("\n\n")[1])
        return 0
    cmd, rest = argv[0], argv[1:]
    if cmd == "lenses":
        known = lenses()
        if not known:
            print(f"no lenses under {LENSES_DIR}", file=sys.stderr); return 1
        width = max(len(n) for n in known)
        for name, entry in known.items():
            print(f"{name:{width}}  {entry['description']}")
        return 0
    if cmd in ("render", "check"):
        allow = "--allow-rationale" in rest
        paths = [a for a in rest if not a.startswith("--")]
        if len(paths) != 1:
            print(f"usage: review_brief.py {cmd} REQUEST[.yaml|.json|-] [--allow-rationale]", file=sys.stderr); return 2
        try:
            req = _load(paths[0])
            if cmd == "check":
                problems = validate(req)
                problems += [f"{f}: {s!r} — {w}" for f, s, w in rationale_findings(req)] if not allow else []
                if problems:
                    raise RequestError(problems)
                names = list(dict.fromkeys(([] if req["mode"] == "re-review" else ["general"]) + list(req.get("lenses") or [])))
                print(f"ok: {req['mode']} of {req.get('range') or req.get('diff')} in {req['repository']}; lenses {', '.join(names) or 'none'}"
                      + (f"; {len(names)} lenses — more than {MANY_LENSES} dilutes the bias" if len(names) > MANY_LENSES else ""))
                return 0
            # Made here, not in render(): the brief stays a pure function of the request.
            with pinned_evidence(req, allow) as evidence:
                brief = render(req, allow_rationale=allow, evidence_path=evidence)
            sys.stdout.write(brief)
            names = list(dict.fromkeys(([] if req["mode"] == "re-review" else ["general"]) + list(req.get("lenses") or [])))
            if len(names) > MANY_LENSES:
                print(f"review_brief: {len(names)} lenses — more than {MANY_LENSES} dilutes the bias", file=sys.stderr)
            return 0
        except RequestError as exc:
            print("review_brief: the request does not render:", file=sys.stderr)
            for p in exc.problems:
                print(f"  {p}", file=sys.stderr)
            return 2
        except (OSError, ValueError, EvidenceRefused) as exc:
            print(f"review_brief: {exc}", file=sys.stderr); return 2
    print(f"review_brief: unknown command {cmd} (render | check | lenses)", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
