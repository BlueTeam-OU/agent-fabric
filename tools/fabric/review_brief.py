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

import json
import os
import re
import sys

FABRIC_ROOT = os.environ.get("AGENT_FABRIC_ROOT") or os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
LENSES_DIR = os.path.join(FABRIC_ROOT, "runtime", "claude-code", "review", "lenses")
BRIEF_VERSION = "agent-fabric review brief v1"

MODES = ("review", "re-review")
SCALAR_KEYS = ("mode", "repository", "range", "diff", "objective", "previous_findings")
LIST_KEYS = ("requirements", "invariants", "compatibility", "threat_model", "scope", "out_of_scope", "lenses")
KNOWN_KEYS = SCALAR_KEYS + LIST_KEYS
# The free text the rationale lint reads: everything a dispatcher writes in words.
FREE_TEXT_KEYS = ("objective", "requirements", "invariants", "compatibility", "threat_model", "scope", "out_of_scope")
RANGE_RE = re.compile(r"^[A-Za-z0-9_./~^-]+\.\.[A-Za-z0-9_./~^-]+$")
LENS_NAME_RE = re.compile(r"^[a-z][a-z0-9-]*$")
MANY_LENSES = 3

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
    for key in LIST_KEYS:
        if key in req and not isinstance(req[key], list):
            problems.append(f"{key}: must be a list (- item lines, or [a, b])")
        elif key in req and any(not isinstance(x, str) or not x.strip() for x in req[key]):
            problems.append(f"{key}: every item must be a non-empty string")
    mode = req.get("mode")
    if mode not in MODES:
        problems.append(f"mode: {mode!r}; must be one of {', '.join(MODES)}")
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
    if mode == "re-review":
        pf = req.get("previous_findings")
        if not isinstance(pf, str) or not pf:
            problems.append("previous_findings: required on a re-review (the previous report, a file)")
        elif not os.path.isfile(pf):
            problems.append(f"previous_findings: {pf} does not exist")
    elif "previous_findings" in req:
        problems.append("previous_findings: only on a re-review (mode: re-review)")
    if mode == "review" and not (req.get("objective") if isinstance(req.get("objective"), str) else "").strip():
        problems.append("objective: required on a review — one line, what must be true of the system")
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


def render(req: dict, lenses_dir: str | None = None, allow_rationale: bool = False) -> str:
    """The brief, or a RequestError naming every problem. Byte-stable for
    the same request and lens files."""
    problems = validate(req, lenses_dir)
    rationale = rationale_findings(req)
    if rationale and not allow_rationale:
        for field, sentence, why in rationale:
            problems.append(f"{field}: {sentence!r} — {why}; state what must be true instead (or --allow-rationale to render it flagged)")
    if problems:
        raise RequestError(problems)
    known = lenses(lenses_dir)
    mode = req["mode"]
    # A review always carries general; a re-review verifies the new hunks
    # against the previous findings and carries only a lens it names.
    names = list(dict.fromkeys(([] if mode == "re-review" else ["general"]) + list(req.get("lenses") or [])))
    out = [f"# Review brief ({BRIEF_VERSION})", "## Mode", mode,
           "## Repository", f"{req['repository']} (the live clone; read-only for you)",
           "## Range", req["range"] if req.get("range") else f"diff file: {req['diff']} (the range is not yet pushed; the tree is the same clone)"]
    out += ["## Objective", (req.get("objective") or "").strip() or "(none stated)"]
    for key, heading in (("requirements", "Requirements"), ("invariants", "Invariants"), ("compatibility", "Compatibility"),
                         ("threat_model", "Threat model"), ("scope", "Scope"), ("out_of_scope", "Out of scope")):
        out += [f"## {heading}", _items(req.get(key))]
    if mode == "re-review":
        # Fenced: the previous report carries headings at the brief's own
        # level, and verbatim inside a fence is still verbatim. The fence
        # is longer than any backtick run in the report (every conforming
        # report quotes hunks in ``` blocks), so it closes where we close it.
        report = open(req["previous_findings"], encoding="utf-8").read().rstrip()
        fence = "`" * max(3, max((len(m) for m in re.findall(r"`+", report)), default=0) + 1)
        out += ["## Previous findings", "Verify only the hunks of the range above against these, answering each by number.",
                fence + "markdown", report, fence]
    out.append("## Lenses")
    if not names:
        out.append("(none named; the constitution's method applies)")
    for name in names:
        out += [f"### {name}", known[name]["body"]]
    if rationale:
        out.append("## Brief notes (dispatcher-asserted, not facts)")
        out.append("The dispatcher rendered these with --allow-rationale; they are the author's conclusions, not evidence — set them aside and say so:")
        out += [f"- {field}: {sentence}" for field, sentence, _ in rationale]
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
            sys.stdout.write(render(req, allow_rationale=allow))
            names = list(dict.fromkeys(([] if req["mode"] == "re-review" else ["general"]) + list(req.get("lenses") or [])))
            if len(names) > MANY_LENSES:
                print(f"review_brief: {len(names)} lenses — more than {MANY_LENSES} dilutes the bias", file=sys.stderr)
            return 0
        except RequestError as exc:
            print("review_brief: the request does not render:", file=sys.stderr)
            for p in exc.problems:
                print(f"  {p}", file=sys.stderr)
            return 2
        except (OSError, ValueError) as exc:
            print(f"review_brief: {exc}", file=sys.stderr); return 2
    print(f"review_brief: unknown command {cmd} (render | check | lenses)", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
