#!/usr/bin/env python3
"""runtime/claude-code/hooks/subagent-ledger.py — one ledger row per
subagent stop, appended on SubagentStop to
<state>/agents/<login>/ledger.jsonl.

Why a hook: a background Agent result carries no usage, so the subagent's
own transcript (agent_transcript_path, which SubagentStop receives) is the
only mechanical source of what a dispatch cost (review economics, P1;
REQUEST 01a1398e, row v1 REQUEST 01a139b5). The row is counts and
identifiers only — never message text, never a secret.

Row v1 (schema_version 1). Every row holds every key, null where unknown:

  schema_version, engine ("claude": this hook sees only Claude Code runs),
  attribution, purpose, description;
  the dispatch header's fields — dispatch_id, parent_session_id, job_id,
  project, repository, pr, review_id, review_round, evidence, base_sha,
  head_sha, started_at;
  session_id, agent_id, agent_type, tool_use_id;
  status, status_source, completed_at, wall_time, turns, input,
  cache_write, cache_read, output, reasoning, first_turn_context, model,
  provider, effort.

Attribution is structural. The brief's first fenced block is an
`agent-fabric-dispatch v1` JSON object, read from the subagent's first
user message. Its producer is to be fabric-review brief, in
fabric-coordinator's review-economics change (an amendment to ADR-020
proposed 2026-10-14, REQUEST 01a139bb); until it lands, only a brief
written by hand carries one. Its fields are copied, each
only when it has its shape (an identifier, an integer, a sha, owner/name,
an ISO time with its zone, evidence pinned | working-tree), and attribution is
"dispatch". A first block
that is not one: purpose "other-subagent", attribution "inferred", the
description (the dispatcher's label, from the sibling .meta.json) kept —
and never parsed: a PR or a round is never guessed from free text. A
header that does not parse as an object is "invalid-header", attributed
like "inferred", so its brief can be found and fixed. A dispatch row's
fields are the header's alone: one it lacks, or gives in the wrong
shape, is null — never filled from elsewhere, because a review row's
head_sha is what a later reproduction is checked against. A row without
a header reads repository and head_sha from the subagent's working
directory (the transcript's cwd — a worktree for an isolated dispatch)
while it still exists. parent_session_id falls back to the hook's
session_id, which is the dispatching session's, and started_at to the
transcript's first timestamp, on every row. The header's own engine is not copied:
engine is the engine that ran, and this hook sees only Claude.

status is completed | failed | cancelled, from the transcript's last
conversational record; status_source names the evidence:

  completed  transcript:end_turn   a final answer (end_turn/stop_sequence, no tool call)
             transcript:handback   a successful SubagentHandback result last
  failed     transcript:api-error:<kind>     the harness's API-error message last
             transcript:stop-reason:<reason> max_tokens, refusal and the like
             transcript:handback-error       the handback itself refused
  cancelled  transcript:interrupted          the user's interrupt marker last
             transcript:tool-use-unanswered  a tool call with no result
             transcript:after-tool-result    a tool result with no next turn
             transcript:message-incomplete   a message cut mid-stream, or none
             transcript:synthetic            a harness message that is not an API error

What cannot be told apart: the last five are every run stopped from
outside — killed by the dispatcher, a crash, the session ending, a limit
— and neither the transcript nor the hook input says which. timeout is
therefore never written by this hook (it is the codex row's, which sees
its own timeout). The rule that matters holds either way: a review that
did not finish is never "completed", so it never reads as a review with
zero findings.

Sums are over distinct API messages: the transcript writes one assistant
record per content block, each repeating its message's usage, and only
the last carries the final output count (read back 2026-10-14 on this
login's subagent transcripts). So a message counts once, at the maximum
of each field. reasoning is output_tokens_details.thinking_tokens, which
the API counts within output (never add the two); null when no message
reports it. A "<synthetic>" message is the harness's, not the API's, and
counts for nothing. first_turn_context is input + cache_write +
cache_read of the first counted message: what the brief and the
harness's preamble cost before any work. provider is "anthropic" for a
plain model id and "openrouter" for the broker's vendor/model ids
(routing/capabilities.json). effort is the hook input's effort.level,
else that of most of the transcript's turns.

A row is written per stop, so a subagent stopped twice (resumed, or held
by another SubagentStop hook) has two rows, the later one cumulative over
the whole transcript: a reader takes the last row per (session_id,
agent_id). A run that stopped before any API answer — its first call
refused, a limit hit — still writes its row, turns 0 and its status
(failed, api-error, when the harness recorded the error): the dispatches
that fail fastest are the ones a reader must see. A transcript with no
user or assistant record writes nothing.

Nothing reads the ledger for authorization; the gate never reads it.
Registered at user scope on SubagentStop (runtime/claude-code/
user-settings.py). Any error writes nothing and exits 0: a measurement
never stands in a session's way.
"""
from __future__ import annotations

import fcntl
import json
import os
import pwd
import re
import subprocess
import sys
from datetime import datetime, timezone

FILE = "ledger.jsonl"
SCHEMA_VERSION = 1
GIT_TIMEOUT_S = 3
HEADER_INFO = "agent-fabric-dispatch v1"
FENCE = re.compile(r"^(`{3,}|~{3,})[ \t]*([^\n`]*?)[ \t]*$", re.MULTILINE)
SHA = re.compile(r"^[0-9a-f]{7,64}$")
REPO = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
REMOTE = re.compile(r"[:/]([^/:@]+/[^/@]+?)(?:\.git)?/?$")
# A URL's userinfo (https://user:token@host/...) is a credential: dropped
# before matching, and a match holding an @ is never written either.
USERINFO = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://[^/]*@")
USAGE = (("input", "input_tokens"), ("cache_write", "cache_creation_input_tokens"),
         ("cache_read", "cache_read_input_tokens"), ("output", "output_tokens"))
HANDBACK = "SubagentHandback"
INTERRUPTED = "[Request interrupted"
DONE_REASONS = ("end_turn", "stop_sequence")
# A header string is an identifier, never prose. Matched with fullmatch:
# `$` also matches before a final newline.
IDENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$")
EVIDENCE = ("pinned", "working-tree")
OTHER = "other-subagent"

# The header's fields, by the type each must have to be copied.
HEADER_IDENT = ("dispatch_id", "parent_session_id", "job_id", "project", "review_id", "purpose")
HEADER_INT = ("pr", "review_round")
HEADER_SHA = ("base_sha", "head_sha")

KEYS = ("schema_version", "engine", "attribution", "purpose", "description",
        "dispatch_id", "parent_session_id", "job_id", "project", "repository", "pr",
        "review_id", "review_round", "evidence", "base_sha", "head_sha", "started_at",
        "session_id", "agent_id", "agent_type", "tool_use_id",
        "status", "status_source", "completed_at", "wall_time", "turns",
        "input", "cache_write", "cache_read", "output", "reasoning",
        "first_turn_context", "model", "provider", "effort")


def state_dir() -> str:
    # session-state.py's rule, so the ledger sits beside the state the
    # account's control agent already reads.
    login = pwd.getpwuid(os.getuid()).pw_name
    root = os.environ.get("AGENT_FABRIC_STATE_DIR")
    root = os.path.abspath(root) if root else os.path.join(
        os.environ.get("XDG_STATE_HOME") or os.path.join(os.path.expanduser("~"), ".local", "state"), "agent-fabric")
    return os.path.join(root, "agents", login)


def seconds(ts: str | None) -> float | None:
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp() if ts else None
    except (AttributeError, ValueError):
        return None


def zoned(ts: str) -> bool:
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).tzinfo is not None
    except ValueError:
        return False


def iso(t: float | None) -> str | None:
    return None if t is None else (
        datetime.fromtimestamp(t, timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"))


def text_of(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(b["text"] for b in content
                         if isinstance(b, dict) and b.get("type") == "text" and isinstance(b.get("text"), str))
    return ""


def most(values) -> str | None:
    count: dict[str, int] = {}
    for v in values:
        count[v] = count.get(v, 0) + 1
    return max(count, key=count.get) if count else None


def header(brief: str) -> tuple[str, dict]:
    """("dispatch", fields) when the brief's first fenced block is the
    dispatch header, ("invalid-header", {}) when it is one whose body is
    not a JSON object, ("inferred", {}) otherwise."""
    opening = FENCE.search(brief)
    if not opening or opening.group(2) != HEADER_INFO:
        return "inferred", {}
    fence = opening.group(1)
    close = re.compile(rf"^{re.escape(fence[0])}{{{len(fence)},}}[ \t]*$", re.MULTILINE)
    end = close.search(brief, opening.end())
    try:
        doc = json.loads(brief[opening.end():end.start()]) if end else None
    except ValueError:
        doc = None
    if not isinstance(doc, dict):
        return "invalid-header", {}
    out: dict = {}
    for k in HEADER_IDENT:
        v = doc.get(k)
        if isinstance(v, str) and IDENT.fullmatch(v):
            out[k] = v
    if doc.get("evidence") in EVIDENCE:
        out["evidence"] = doc["evidence"]
    v = doc.get("started_at")
    if isinstance(v, str) and len(v) <= 40 and zoned(v):
        out["started_at"] = v
    for k in HEADER_INT:
        v = doc.get(k)
        if isinstance(v, int) and not isinstance(v, bool) and v >= 0:
            out[k] = v
    for k in HEADER_SHA:
        v = doc.get(k)
        if isinstance(v, str) and SHA.fullmatch(v):
            out[k] = v
    v = doc.get("repository")
    if isinstance(v, str) and REPO.fullmatch(v):
        out["repository"] = v
    return "dispatch", out


def status(last: dict | None, handback_ids: set) -> tuple[str, str]:
    """(status, status_source) from the last user or assistant record."""
    msg = last.get("message") if last else None
    if not isinstance(msg, dict):
        return "cancelled", "transcript:message-incomplete"
    content = msg.get("content")
    blocks = [b for b in content if isinstance(b, dict)] if isinstance(content, list) else []
    if last.get("type") == "assistant":
        if last.get("isApiErrorMessage"):
            kind = last.get("error")
            return "failed", f"transcript:api-error:{kind if isinstance(kind, str) and kind.isidentifier() else 'unknown'}"
        if msg.get("model") == "<synthetic>":
            return "cancelled", "transcript:synthetic"
        if any(b.get("type") == "tool_use" for b in blocks):
            return "cancelled", "transcript:tool-use-unanswered"
        reason = msg.get("stop_reason")
        if reason in DONE_REASONS:
            return "completed", "transcript:end_turn"
        if isinstance(reason, str) and reason.isidentifier():
            return "failed", f"transcript:stop-reason:{reason}"
        return "cancelled", "transcript:message-incomplete"
    results = [b for b in blocks if b.get("type") == "tool_result"]
    if results:
        r = results[-1]
        if r.get("tool_use_id") in handback_ids:
            return ("failed", "transcript:handback-error") if r.get("is_error") else ("completed", "transcript:handback")
        return "cancelled", "transcript:after-tool-result"
    if text_of(content).lstrip().startswith(INTERRUPTED):
        return "cancelled", "transcript:interrupted"
    return "cancelled", "transcript:message-incomplete"


def read_transcript(path: str) -> dict:
    """Usage sums, turns, model, effort, the brief, the status and the
    working directory of one subagent transcript."""
    messages: dict[str, dict] = {}       # message id -> usage maxima; insertion order is turn order
    models: dict[str, str] = {}
    efforts: dict[str, str] = {}
    handback_ids: set = set()
    first_ts = last_ts = None
    cwd = brief = last = None
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                rec = json.loads(line)
            except ValueError:
                continue                 # a torn last line of a live file
            if not isinstance(rec, dict):
                continue
            t = seconds(rec.get("timestamp"))
            if t is not None:
                first_ts = t if first_ts is None else min(first_ts, t)
                last_ts = t if last_ts is None else max(last_ts, t)
            cwd = cwd or rec.get("cwd")
            msg = rec.get("message")
            if rec.get("type") not in ("user", "assistant") or not isinstance(msg, dict):
                continue
            last = rec
            if rec["type"] == "user":
                if brief is None:
                    brief = text_of(msg.get("content"))
                continue
            content = msg.get("content")
            for b in content if isinstance(content, list) else ():
                if isinstance(b, dict) and b.get("type") == "tool_use" and b.get("name") == HANDBACK:
                    handback_ids.add(b.get("id"))
            model, usage, mid = msg.get("model"), msg.get("usage"), msg.get("id")
            if model == "<synthetic>" or not isinstance(usage, dict) or not mid:
                continue
            seen = messages.setdefault(mid, {**{k: 0 for k, _ in USAGE}, "reasoning": None})
            for k, src in USAGE:
                v = usage.get(src)
                if isinstance(v, int) and v > seen[k]:
                    seen[k] = v
            details = usage.get("output_tokens_details")
            v = details.get("thinking_tokens") if isinstance(details, dict) else None
            if isinstance(v, int):
                seen["reasoning"] = max(v, seen["reasoning"] or 0)
            if mid not in models and isinstance(model, str):
                models[mid] = model
            if mid not in efforts and isinstance(rec.get("effort"), str):
                efforts[mid] = rec["effort"]
    first = next(iter(messages.values()), None)
    reasoning = [m["reasoning"] for m in messages.values() if m["reasoning"] is not None]
    st, source = status(last, handback_ids)
    return {
        # The model of most turns: a dispatch rides one class's model, and a
        # mid-run fallback is the exception the majority still names.
        "model": most(models.values()),
        "effort": most(efforts.values()),
        "turns": len(messages),
        **{k: sum(m[k] for m in messages.values()) for k, _ in USAGE},
        "reasoning": sum(reasoning) if reasoning else None,
        "first_turn_context": first["input"] + first["cache_write"] + first["cache_read"] if first else 0,
        "wall_time": round(last_ts - first_ts, 3) if first_ts is not None else None,
        "started_at": iso(first_ts),
        "status": st,
        "status_source": source,
        "conversation": last is not None,
        "brief": brief or "",
        "cwd": cwd,
    }


def provider(model: str | None) -> str | None:
    return None if not model else "openrouter" if "/" in model else "anthropic"


def hook_effort(payload: dict) -> str | None:
    # Documented as {"level": ...}; a bare string is taken too.
    e = payload.get("effort")
    level = e.get("level") if isinstance(e, dict) else e
    return level if isinstance(level, str) and level.isidentifier() else None


def read_meta(transcript: str) -> dict:
    meta = os.path.splitext(transcript)[0] + ".meta.json"
    try:
        with open(meta, encoding="utf-8") as fh:
            doc = json.load(fh)
    except (OSError, ValueError):
        return {}
    return doc if isinstance(doc, dict) else {}


def git(cwd: str, *args: str) -> str | None:
    try:
        r = subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True,
                           timeout=GIT_TIMEOUT_S, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout.strip() or None if r.returncode == 0 else None


def repository(cwd: str | None) -> tuple[str | None, str | None]:
    """(owner/name from origin, else the toplevel's basename; HEAD)."""
    if not cwd or not os.path.isdir(cwd):
        return None, None
    top = git(cwd, "rev-parse", "--show-toplevel")
    if not top:
        return None, None
    url = git(cwd, "remote", "get-url", "origin")
    m = REMOTE.search(USERINFO.sub("", url)) if url else None
    return (m.group(1) if m else os.path.basename(top)), git(cwd, "rev-parse", "HEAD")


def row(payload: dict) -> dict | None:
    transcript = payload.get("agent_transcript_path")
    if not isinstance(transcript, str) or not os.path.isfile(transcript):
        return None
    sums = read_transcript(transcript)
    if not sums.pop("conversation"):
        return None                      # nothing ran: no row
    attribution, fields = header(sums.pop("brief"))
    cwd = sums.pop("cwd") or payload.get("cwd")
    if attribution != "dispatch":
        fields["repository"], fields["head_sha"] = repository(cwd)
    meta = read_meta(transcript)
    session = payload.get("session_id") if isinstance(payload.get("session_id"), str) else None
    entry = {
        **sums,
        **fields,
        "schema_version": SCHEMA_VERSION,
        "engine": "claude",
        "attribution": attribution,
        "purpose": fields.get("purpose") or OTHER,
        "description": meta.get("description") if isinstance(meta.get("description"), str) else None,
        "parent_session_id": fields.get("parent_session_id") or session,
        "started_at": fields.get("started_at") or sums["started_at"],
        "session_id": session,
        "agent_id": payload.get("agent_id"),
        "agent_type": payload.get("agent_type") or meta.get("agentType"),
        "tool_use_id": meta.get("toolUseId"),
        "completed_at": iso(datetime.now(timezone.utc).timestamp()),
        "provider": provider(sums["model"]),
        "effort": hook_effort(payload) or sums["effort"],
    }
    return {k: entry.get(k) for k in KEYS}


def append(directory: str, entry: dict) -> None:
    os.makedirs(directory, mode=0o700, exist_ok=True)
    line = json.dumps(entry, separators=(",", ":")) + "\n"
    # One write under an exclusive lock: parallel subagents stopping at
    # once each append a whole line, never an interleaving.
    fd = os.open(os.path.join(directory, FILE), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        os.write(fd, line.encode("utf-8"))
    finally:
        os.close(fd)


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        entry = row(payload) if isinstance(payload, dict) else None
        if entry:
            append(state_dir(), entry)
    except Exception:  # noqa: BLE001 — a measurement never fails the session
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
