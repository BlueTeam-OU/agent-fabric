"""tools/fabric/control/ops/activity.py — what the account did: the script and language it writes in, whether it read the corpus, and its locale workers.
A part of the ops package, whose __init__.py is the contract every
extractor here keeps."""
from __future__ import annotations

import json
import os
import pwd
import re
import subprocess
import time
import unicodedata
from typing import Any, Callable, Mapping

from . import util
from gzcoord import gzmsg, jsvalues as js  # noqa: E402 — util puts tools/fabric on sys.path
import roots  # noqa: E402

# Which SCRIPT the account writes in — the signature of the language it
# reasons in. A role that must think in the language it answers for
# (language-culture) leaves exactly one artifact that differs when it
# does not: the letters of its own session records. The harness keeps
# every assistant turn, thinking blocks included, under
# ~/.claude/projects/<launch dir>/<session>.jsonl; this counts the LETTERS
# of those blocks by script (Unicode block: Latin, Georgian, Cyrillic,
# Greek, Arabic, Hebrew, Armenian, CJK, other) and reports shares —
# thinking and visible text apart, since a session that reasons in one
# language and translates its answers shows a low share in thinking and
# a higher one in text. Nothing of the text itself leaves the account:
# counts and percentages only. Records touched in the last `hours`
# (default 24), newest `limit` files (default 5).
#
# Measured 2026-09-17: the reasoning itself is NOT on disk — the API
# returns most thinking blocks with a signature and no text, and the
# ones that carry text are 120–400-character summaries; one session
# with 117k thinking tokens had no stored thinking text at all. So the
# signature the charter names is the holder's NOTES: the directory
# `${XDG_STATE_HOME:-~/.local/state}/agent-fabric/agents/<login>/notes/`,
# where the role keeps the translated request, its working notes and
# the original answer in the locale's language, one file per day. The
# op counts those files (touched in the window) the same way, by
# script, and bins their paragraphs; that is the artifact the holder
# controls and the transcript's text share is the second number.
#
# The CEO's criterion (2026-09-17) is per BLOCK, not per total: most
# thinking blocks must be in the locale's script alone, some will be
# about half and half (a term quoted, a name), and a session that
# reasons in English shows the opposite — so each thinking block is
# also binned by the share of its dominant non-Latin script: `only`
# (≥ 90 %), `mixed` (30–90 %), `latin` (< 30 %), and the bins are
# reported as counts of blocks. `empty` is the block the API returned
# with a signature and no text: measured 2026-09-17 across the fleet,
# most thinking blocks are stored that way (one org: about a fifth
# carry text; the other: none on the same model), so the signature is
# read from the blocks that carry text, and `empty` says how many did
# not — a row of only empties is unmeasured, not clean.
SCRIPT_RANGES = [
    ("georgian", [(0x10A0, 0x10FF), (0x1C90, 0x1CBF), (0x2D00, 0x2D2F)]),
    ("cyrillic", [(0x0400, 0x052F), (0x2DE0, 0x2DFF), (0xA640, 0xA69F)]),
    ("greek", [(0x0370, 0x03FF), (0x1F00, 0x1FFF)]),
    ("armenian", [(0x0530, 0x058F)]),
    ("hebrew", [(0x0590, 0x05FF)]),
    ("arabic", [(0x0600, 0x06FF), (0x0750, 0x077F), (0x08A0, 0x08FF)]),
    ("cjk", [(0x3040, 0x30FF), (0x4E00, 0x9FFF), (0xAC00, 0xD7AF)]),
    ("latin", [(0x0041, 0x005A), (0x0061, 0x007A), (0x00C0, 0x024F), (0x1E00, 0x1EFF)]),
]

_JS_SPACE = f"[{js.JS_SPACE}]"
_PARAGRAPH_BREAK = re.compile(f"\n{_JS_SPACE}*\n")


def script_counts(text: str, counts: dict[str, int] | None = None) -> dict[str, int]:
    counts = {} if counts is None else counts
    for ch in text:
        cp = ord(ch)
        if cp < 0x41:
            continue   # digits, punctuation, space
        name = next((n for n, ranges in SCRIPT_RANGES if any(a <= cp <= b for a, b in ranges)), None)
        if name is None:
            if not unicodedata.category(ch).startswith("L"):
                continue
            name = "other"
        counts[name] = counts.get(name, 0) + 1
    return counts


def _shares(counts: Mapping[str, int]) -> dict[str, Any]:
    total = sum(counts.values())
    out: dict[str, Any] = {"letters": total}
    for k, v in sorted(counts.items(), key=lambda kv: -kv[1]):
        out[k] = util.whole(util.js_round(1000 * v / total) / 10)
    return out


def _blocks() -> dict[str, int]:
    return {"only": 0, "mixed": 0, "latin": 0, "empty": 0}


def _bin_into(blocks: dict[str, int], counts: Mapping[str, int]) -> None:
    """A block (a thinking block, a paragraph) binned by its non-Latin share:
    `only` at 90 %, `mixed` from 30 %, `latin` below, `empty` under 20 letters."""
    total = sum(counts.values())
    if total < 20:
        blocks["empty"] += 1
        return
    share = (total - counts.get("latin", 0) - counts.get("other", 0)) / total
    blocks["only" if share >= 0.9 else "mixed" if share >= 0.3 else "latin"] += 1


def _paragraphs(text: str, counts: dict[str, int], blocks: dict[str, int], sink: list[str] | None = None) -> None:
    for para in _PARAGRAPH_BREAK.split(text):
        c = script_counts(para)
        _bin_into(blocks, c)
        for k, v in c.items():
            counts[k] = counts.get(k, 0) + v
        if sink is not None:
            sink.append(para)


# THE LANGUAGE, not only the script (the CEO, 2026-09-17: CLD2). Script
# shares cannot tell English from Italian or Russian from Ukrainian, and
# a single-label classifier cannot see the English inside a Georgian
# paragraph (fastText named a half-and-half paragraph `ka 0.83`); CLD2
# names up to three languages per paragraph with the share of each, and
# says when it is unreliable. The detector runs in the account's own venv
# on the account's own text (runtime/langid/, installed by bootstrap.sh);
# only the verdicts come back. `shares` is the text by language, each
# paragraph's percentages weighted by its letters; `dominant` counts
# paragraphs by their first language; `unreliable` counts the paragraphs
# CLD2 would only guess at (a code line, a two-letter answer, Georgian in
# Latin letters — the script shares still see that one). A paragraph
# under 20 letters is not sent. Without the venv the section says
# `unavailable`, never a guess.
LANGID_TIMEOUT_S = 60
LANGID_MAX_BYTES = 16 * 1024 * 1024


def _letters_of(p: str) -> int:
    return sum(script_counts(p).values())


def _fabric_root(home: str, root: str | None) -> str:
    if root is not None:
        return root
    env = os.environ.get("AGENT_FABRIC_ROOT")
    return os.path.join(home, "projects", "agent-fabric") if env is None else env


def langid_cmd(home: str | None = None, root: str | None = None) -> list[str]:
    home = os.path.expanduser("~") if home is None else home
    return [os.path.join(home, ".cache", "agent-fabric", "langid", "venv", "bin", "python"),
            os.path.join(_fabric_root(home, root), "runtime", "langid", "langid.py")]


def languages(paragraphs: list[str], home: str | None = None, root: str | None = None,
              run: Callable[..., Any] = util.run_bounded) -> dict:
    judged = [p for p in paragraphs if _letters_of(p) >= 20]
    py, script = langid_cmd(home, root)
    if not os.path.exists(py):
        return {"status": "unavailable", "why": "no detector venv (runtime/langid/install.sh)"}
    if not judged:
        return {"status": "ok", "paragraphs": 0, "unreliable": 0, "shares": {}, "dominant": {}}
    try:
        out = util.decode(run([py, script], input=json.dumps(judged, ensure_ascii=False, separators=(",", ":")).encode("utf-8", "surrogatepass"),
                              timeout=LANGID_TIMEOUT_S, max_bytes=LANGID_MAX_BYTES).stdout)
    except (subprocess.SubprocessError, OSError) as e:
        said = gzmsg.js_trim(util.decode(getattr(e, "stderr", None)) or str(e))
        return {"status": "unavailable", "why": said.split("\n")[-1][:160]}
    try:
        verdicts = util.loads(out)
    except ValueError:
        return {"status": "unavailable", "why": "the detector answered something that is not JSON"}
    if not isinstance(verdicts, list) or len(verdicts) != len(judged):
        return {"status": "unavailable", "why": "the detector answered for a different number of paragraphs"}
    weight: dict[str, float] = {}
    dominant: dict[str, int] = {}
    total = unreliable = 0
    for i, v in enumerate(verdicts):
        reliable, details = (v[0] if v else None, v[2] if len(v) > 2 else None) if isinstance(v, list) else (False, [])
        if not util.truthy(reliable) or not isinstance(details, list) or not details:
            unreliable += 1
            continue
        n = _letters_of(judged[i])
        total += n
        # A detail is [code, percent]; one that is not a list is the
        # detector's fault, and raises as the Node's destructuring did.
        for d in details:
            if not isinstance(d, list):
                raise TypeError("the detector answered a detail that is not [code, percent]")
            key = js.string(d[0] if d else js.UNDEFINED)
            weight[key] = weight.get(key, 0) + n * js.number(d[1] if len(d) > 1 else js.UNDEFINED) / 100
        first = js.string(details[0][0] if details[0] else js.UNDEFINED)
        dominant[first] = dominant.get(first, 0) + 1

    def ordered(o: Mapping[str, float]) -> dict[str, Any]:
        return dict(sorted(o.items(), key=lambda kv: -kv[1]))
    shares = ordered({k: util.whole(util.js_round(1000 * v / total) / 10) for k, v in weight.items()}) if total else {}
    return {"status": "ok", "paragraphs": len(judged), "unreliable": unreliable, "shares": shares, "dominant": ordered(dominant)}


# RECALL — is the corpus read? A drain is instrumented end to end; the
# read-back never was: a slice read is a plain Read in the session's
# record and nothing counted them, so a slice with a poor cue could be
# written and never opened and nobody would know (the owner, 2026-09-20).
# This walks the account's session records in the window — every
# session and its subagents, not the newest five — and counts the tool
# calls that touch the corpus: an index (`INDEX.md` under a project's
# .agent-fabric/memory/<role>/ or the fabric's memory/domains/<x>/), a
# slice (any other .md there, or under memory/shared/), the authored
# identity (identities/roles/<role>/charter|brief|recall.md), and a
# search (Grep/Glob whose path is one of those directories, or a Bash
# command naming one). Counts and paths only — never a line of what was
# read. `sessions_without_recall` is the number that matters: a session
# that opened neither an index nor a slice worked without the corpus.
# Anchored at a path boundary, not at a slash: a session that reads
# `.agent-fabric/memory/<role>/INDEX.md` relative to its working copy —
# the shape every instruction file shows — is reading the corpus.
CORPUS_RE = re.compile(r"(?:^|/)(?:\.agent-fabric/memory/|memory/(?:domains|shared)/)")

IDENTITY_RE = re.compile(r"(?:^|/)identities/roles/[a-z0-9-]+/(?:charter|brief|recall)\.md\Z")

_BASH_CORPUS = re.compile(f"(?:^|[{js.JS_SPACE}'\"=])((?:[^{js.JS_SPACE}]*/)?(?:\\.agent-fabric/memory/|memory/(?:domains|shared)/)[^{js.JS_SPACE}]*)")


def recall_kind(tool: Any, inp: Any) -> dict | None:
    fp, pth = js.get(inp, "file_path"), js.get(inp, "path")
    p = fp if isinstance(fp, str) else pth if isinstance(pth, str) else ""
    if tool == "Read":
        if IDENTITY_RE.search(p):
            return {"kind": "identity", "path": p}
        if not CORPUS_RE.search(p) or not p.endswith(".md") or p.endswith("/README.md"):
            return None   # crossref.json, a drain report, a README: not a slice
        return {"kind": "index" if p.endswith("/INDEX.md") else "slice", "path": p}
    if tool in ("Grep", "Glob"):
        pattern = js.get(inp, "pattern")
        pattern = "" if js.nullish(pattern) else js.string(pattern)
        return {"kind": "search", "path": p or pattern} if CORPUS_RE.search(p) or CORPUS_RE.search(pattern) else None
    if tool == "Bash":
        command = js.get(inp, "command")
        m = _BASH_CORPUS.search("" if js.nullish(command) else js.string(command))
        return {"kind": "search", "path": re.sub(r"[\"'`;|)]+\Z", "", m.group(1))} if m else None
    return None


def _records(root: str) -> list[str] | None:
    """Every session record and the subagent records beside it; None when
    ~/.claude/projects cannot be listed."""
    try:
        dirs = sorted(os.listdir(root))
    except OSError:
        return None
    files: list[str] = []
    for d in dirs:
        directory = os.path.join(root, d)
        try:
            names = sorted(os.listdir(directory))
        except OSError:
            continue
        for n in names:
            if n.endswith(".jsonl"):
                files.append(os.path.join(directory, n))
            subs = os.path.join(directory, n, "subagents")
            try:
                inner = sorted(os.listdir(subs))
            except OSError:
                continue
            files.extend(os.path.join(subs, a) for a in inner if re.fullmatch(r"agent-.*\.jsonl", a))
    return files


def _mtime_ms(f: str) -> float | None:
    try:
        return os.stat(f).st_mtime * 1000
    except OSError:
        return None


def _read_text(f: str) -> str | None:
    try:
        with open(f, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return None


def _now(now: float | None) -> float:
    return time.time() * 1000 if now is None else now


def recall(home: str | None = None, hours: float = 24, now: float | None = None) -> dict:
    home = os.path.expanduser("~") if home is None else home
    now = _now(now)
    files = _records(os.path.join(home, ".claude", "projects"))
    if files is None:
        return {"status": "no-records", "hours": hours}
    recent = [f for f in files if (m := _mtime_ms(f)) is not None and now - m <= hours * 3600000]
    if not recent:
        return {"status": "no-records", "hours": hours}
    counts = {"index": 0, "slice": 0, "search": 0, "identity": 0}
    slices: dict[str, int] = {}
    sessions = turns = without = 0
    since = now - hours * 3600000
    for f in recent:
        body = _read_text(f)
        if body is None:
            continue
        mine = own = 0
        # The window applies to each RECORD: a long or resumed session's file
        # is touched today and holds weeks of turns; counting them all
        # inflated reads and turns and let an old index read stand for
        # recent work. A record without a parseable timestamp is inside the
        # window (the file is).
        for line in body.split("\n"):
            if '"assistant"' not in line:
                continue
            try:
                d = util.loads(line)
            except ValueError:
                continue
            if js.get(d, "type") != "assistant":
                continue
            ts = util.date_parse_ms(js.get(d, "timestamp"))
            if ts is not None and ts < since:
                continue
            own += 1
            content = js.get(js.get(d, "message"), "content")
            for b in content if isinstance(content, list) else []:
                if js.get(b, "type") != "tool_use":
                    continue
                r = recall_kind(js.get(b, "name"), js.get(b, "input"))
                if not r:
                    continue
                counts[r["kind"]] += 1
                if r["kind"] in ("index", "slice"):
                    mine += 1
                    slices[r["path"]] = slices.get(r["path"], 0) + 1
        if not own:
            continue   # a record with no assistant turn is not a session
        sessions += 1
        turns += own
        if not mine:
            without += 1
    top = [{"path": p.replace(home, "~", 1), "reads": n} for p, n in sorted(slices.items(), key=lambda kv: -kv[1])[:10]]
    return {"status": "ok", "hours": hours, "sessions": sessions, "turns": turns, **counts,
            "sessions_without_recall": without, "top": top}


def _login() -> str:
    try:
        return pwd.getpwuid(os.getuid()).pw_name
    except (KeyError, OSError):
        return "unknown"


def notes_dir(home: str | None = None, env: Mapping[str, str] | None = None, login: str | None = None) -> str:
    home = os.path.expanduser("~") if home is None else home
    env = os.environ if env is None else env
    state = env.get("XDG_STATE_HOME")
    return os.path.join(os.path.join(home, ".local", "state") if state is None else state,
                        "agent-fabric", "agents", _login() if login is None else login, "notes")


# THE SOURCE LOCALE. A holder of the fleet's own language translates
# nothing, and its notes are English by design: they are not measured by
# script (ADR-027 §2, A 2026-10-07), so the op says that instead of
# counts that would read as a measurement. The source is the locale whose
# locale.json carries lint's SOURCE_TAG (tools/fabric/lint_rules/locales.py);
# the holder's locale is the suffix after its login's last dash, as i18n
# reads it. A locale.json that cannot be read is not the source: measured,
# as before this rule.
SOURCE_TAG = "en-US"


def source_locale(who: Mapping[str, Any] | None = None, root: str | None = None) -> bool:
    who = gzmsg.whoami() if who is None else who   # unset: per request, so a rebind shows
    agent = who.get("agent") if isinstance(who, Mapping) else None
    if (who.get("role") if isinstance(who, Mapping) else None) != "language-culture" or not isinstance(agent, str):
        return False
    suffix = agent[agent.rfind("-") + 1:]
    loc = util.read_json(os.path.join(roots.locale_dir("language-culture", suffix, root=root), "locale.json"))
    return js.get(loc, "tag") == SOURCE_TAG


def script(home: str | None = None, hours: float = 24, limit: int = 5, now: float | None = None, notes: str | None = None,
           langid: Callable[..., dict] = languages, source: bool = False) -> dict:
    home = os.path.expanduser("~") if home is None else home
    now = _now(now)
    notes = notes_dir(home) if notes is None else notes
    root = os.path.join(home, ".claude", "projects")
    found: list[tuple[str, float]] = []
    try:
        dirs = sorted(os.listdir(root))
    except OSError:
        dirs = []   # no transcript directory: no files, and the notes are still said below
    for d in dirs:
        directory = os.path.join(root, d)
        try:
            names = sorted(os.listdir(directory))
        except OSError:
            continue
        for n in names:
            if not n.endswith(".jsonl"):
                continue
            f = os.path.join(directory, n)
            m = _mtime_ms(f)
            if m is not None and now - m <= hours * 3600000:
                found.append((f, m))
    found.sort(key=lambda x: -x[1])
    files = [f for f, _ in found[:limit]]
    # The notes: every file under the notes directory touched in the window,
    # its paragraphs binned like thinking blocks.
    note_counts: dict[str, int] = {}
    note_blocks = _blocks()
    note_files = 0
    note_paras: list[str] = []
    if not source:
        try:
            listed = sorted(os.listdir(notes))
        except OSError:
            listed = []   # no notes directory: reported as none
        for n in listed:
            f = os.path.join(notes, n)
            try:
                st = os.stat(f)
            except OSError:
                continue
            if not os.path.isfile(f) or now - st.st_mtime * 1000 > hours * 3600000:
                continue
            body = _read_text(f)
            if body is None:
                continue
            note_files += 1
            _paragraphs(body, note_counts, note_blocks, note_paras)
    if source:
        notes_out: dict[str, Any] = {"status": "not measured", "reason": "the source locale"}
    elif note_files:
        notes_out = {"status": "ok", "files": note_files, **_shares(note_counts), "blocks": note_blocks,
                     "language": langid(note_paras, home=home)}
    else:
        notes_out = {"status": "none", "dir": notes}
    if not files:
        return {"status": "no-records", "hours": hours, "notes": notes_out}
    thinking: dict[str, int] = {}
    text: dict[str, int] = {}
    turns = 0
    blocks = _blocks()
    for f in files:
        body = _read_text(f)
        if body is None:
            continue
        for line in body.split("\n"):
            if '"assistant"' not in line:
                continue
            try:
                d = util.loads(line)
            except ValueError:
                continue
            if js.get(d, "type") != "assistant":
                continue
            turns += 1
            content = js.get(js.get(d, "message"), "content")
            for b in content if isinstance(content, list) else []:
                kind = js.get(b, "type")
                if kind == "thinking" and isinstance(js.get(b, "thinking"), str):
                    c = script_counts(b["thinking"])
                    _bin_into(blocks, c)
                    for k, v in c.items():
                        thinking[k] = thinking.get(k, 0) + v
                elif kind == "text" and isinstance(js.get(b, "text"), str):
                    script_counts(b["text"], text)
    return {"status": "ok", "hours": hours, "files": len(files), "turns": turns, "thinking": _shares(thinking),
            "thinking_blocks": blocks, "text": _shares(text), "notes": notes_out,
            "workers": worker_transcripts(files, hours=hours, now=now, langid=lambda p: langid(p, home=home))}


# THE WORKERS. A subagent's transcript is stored beside its session's
# (<session>/subagents/agent-*.jsonl) with a sidecar the harness writes,
# agent-*.meta.json, whose agentType names the type dispatched: the
# locale worker of the language-culture bridge
# (identities/roles/language-culture/charter.md) is the one whose sidecar
# says locale-worker — read back 2026-09-17, when "no tool_use block"
# turned out to fit no transcript: the hand-back itself is a tool_use
# (SubagentHandback), and the harness refuses to spawn an agent with no
# tool at all, so the worker carries one inert tool. Its USER records are
# the worker's input, which the bridge composed, less the harness's own
# <system-reminder> spans (English, injected into every subagent, and not
# the bridge's doing): a Latin paragraph left is English reaching the
# worker, the leak the construction exists to prevent. Its assistant text
# is the answer. Any tool_use but the hand-back is counted as tool_uses —
# a worker that used a tool is a worker with one. Paragraphs binned like
# the notes; counts only.
WORKER_TYPE = "locale-worker"

REMINDER_RE = re.compile(r"<system-reminder>.*?(?:</system-reminder>|\Z)", re.S)


def worker_transcripts(files: list[str], hours: float = 24, now: float | None = None, type: str = WORKER_TYPE,  # noqa: A002
                       langid: Callable[[list[str]], dict] | None = None) -> dict:
    now = _now(now)
    inp: dict[str, int] = {}
    text: dict[str, int] = {}
    input_blocks, text_blocks = _blocks(), _blocks()
    input_paras: list[str] = []
    text_paras: list[str] = []
    n = turns = others = tool_uses = 0
    for f in files:
        directory = os.path.join(os.path.dirname(f), os.path.basename(f).removesuffix(".jsonl"), "subagents")
        try:
            names = sorted(os.listdir(directory))
        except OSError:
            continue
        for name in names:
            if not re.fullmatch(r"agent-.*\.jsonl", name):
                continue
            p = os.path.join(directory, name)
            m = _mtime_ms(p)
            if m is None or now - m > hours * 3600000:
                continue
            meta = util.read_json(p.removesuffix(".jsonl") + ".meta.json")   # no sidecar: not a worker
            if js.get(meta, "agentType") != type:
                others += 1
                continue
            body = _read_text(p)
            if body is None:
                continue
            n += 1
            for line in body.split("\n"):
                try:
                    d = util.loads(line)
                except ValueError:
                    continue
                c = js.get(js.get(d, "message"), "content")
                kind = js.get(d, "type")
                if kind == "user":
                    texts = [c] if isinstance(c, str) else [b["text"] for b in c if js.get(b, "type") == "text"
                                                             and isinstance(js.get(b, "text"), str)] if isinstance(c, list) else []
                    for t in texts:
                        own = REMINDER_RE.sub("", t)
                        if gzmsg.js_trim(own):
                            _paragraphs(own, inp, input_blocks, input_paras)
                elif kind == "assistant":
                    turns += 1
                    for b in c if isinstance(c, list) else []:
                        if js.get(b, "type") == "text" and isinstance(js.get(b, "text"), str):
                            _paragraphs(b["text"], text, text_blocks, text_paras)
                        elif js.get(b, "type") == "tool_use" and js.get(b, "name") != "SubagentHandback":
                            tool_uses += 1
    if not n:
        return {"status": "none", "other_subagents": others}
    return {"status": "ok", "files": n, "other_subagents": others, "turns": turns, "tool_uses": tool_uses,
            "input": {**_shares(inp), "blocks": input_blocks, **({"language": langid(input_paras)} if langid else {})},
            "text": {**_shares(text), "blocks": text_blocks, **({"language": langid(text_paras)} if langid else {})}}
