"""tools/fabric/memory_flags.py — from what memory_check.py sorted and what readers marked, to one REQUEST per
agent that owns the sections (agent-fabric ADR-050 rules 3 and 5). The drain calls this; it reads no relay, no
jobs list and no other account's state, so everything it needs is passed in (rule 14: nothing crosses hosts by
a local read) and nothing is sent: it returns the REQUESTs and the ledger entries that say they were.

THE FLAG   one per SECTION, however many of its anchors failed or readers marked it: key
           `<corpus>:<slice>#<heading>` (the corpus a label the caller gives: the project the
           corpus belongs to), with its reasons, each one of
             stale-hard   an anchor's path or string is gone, or a path the section cites
             maybe-stale  an anchor's file has a commit after the section's Observed day
             mark-stale / mark-wrong   a reader's memory_mark (ADR-049 rule 3), a note carried as
                          the reader's words, clipped, never as an instruction
           `helpful` marks are not flags. A model's hint (rule 6) may be attached to a flag by the
           caller; it is rendered, marked as a guess, and changes nothing else.

THE OWNER  rule 3, per section: the agent that last wrote it (`writers[key]["agent"]`, the drain's
           state, the assembler's per-section record) if it still holds the section's role; else the
           role's running holder; else its lowest-numbered holder. The section's role is the one in
           its Observed tail, else the first directory of a project corpus's slice. A section no
           role names, or whose role has no holder, is `unrouted` with the reason: reported, never
           dropped and never sent to a guess.

THE REQUEST  one per agent, addressed TO that agent's own address (an assignment names one login, SPEC
           §13), listing its flags with slice, heading, anchor and reason; intake (ADR-037 rule 11)
           makes it one job titled `<SUBJECT> (REQUEST <MESSAGE-ID>)`. At most MAX_FLAGS flags go in
           one REQUEST; the rest are `deferred`, unsent and unrecorded, so the next drain sends them.
           The text passes gzmsg.validate.

DEDUP      `sent` is the drain's ledger, flag key -> {to, message_id, at}; a flag whose last REQUEST is
           still an open job of that agent (`is_open(address, message_id)`) is not sent again and is
           listed `open`. `open_message_ids` reads that from a jobs list. A flag whose job is done or
           dropped and which is still flagged is sent again: the tree still disagrees.

WHAT IT DOES NOT DO  send, read the corpus's git history (memory_check did), decide whether a section is
           true (the owning agent does), or edit a slice.
"""
from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)
from assembler import slices  # noqa: E402
from gzcoord import gzmsg  # noqa: E402
from jobsparts.base import OPEN as OPEN_STATES  # noqa: E402 — the one list of the states in which a job is still open

MAX_FLAGS = 20
NOTE_CLIP = 200
# Where a section's last writer is recorded in the drain report (assembler `section_writers`): the report names a
# slice by its path from the fabric root or the working copy, which the id letter of a mark (f: / p:) also says.
REPORT_PREFIX = {"f": "memory/", "p": ".agent-fabric/memory/"}
MARK_VERDICTS = {"stale": "mark-stale", "wrong": "mark-wrong"}
KIND_ORDER = ("stale-hard", "maybe-stale", "mark-wrong", "mark-stale")


@dataclass
class Flag:
    corpus: str
    slice: str
    heading: str
    role: str | None
    reasons: list[dict] = field(default_factory=list)   # {"kind", "what", "detail"?}
    hint: str | None = None
    report_prefix: str = ""     # what the drain report puts before the slice's path: "memory/" or ".agent-fabric/memory/"

    @property
    def key(self) -> str:
        """The flag's identity in the ledger: the corpus label, the slice from its corpus, the heading."""
        return f"{self.corpus}:{self.slice}#{self.heading}"

    @property
    def report_key(self) -> str:
        """The section as the drain report's `section_writers` names it."""
        return f"{self.report_prefix}{self.slice}#{self.heading}"


@dataclass
class Plan:
    requests: dict[str, list[Flag]] = field(default_factory=dict)       # address -> flags to send
    open: list[tuple[Flag, str, str]] = field(default_factory=list)     # (flag, address, message id) still an open job
    unrouted: list[tuple[Flag, str]] = field(default_factory=list)      # (flag, why)
    deferred: list[Flag] = field(default_factory=list)                  # past MAX_FLAGS for its agent
    how: dict[str, str] = field(default_factory=dict)                   # flag key -> how its owner was chosen


def section_role(slice_rel: str, observed_role: str | None) -> str | None:
    """The role a section belongs to: its Observed tail names it; else a project corpus's first directory. A
    fabric domain slice (domains/<domain>/…) names a field, not a role, and without a tail names none."""
    if observed_role:
        return observed_role
    first = slice_rel.split("/", 1)[0]
    return None if first in ("domains", "shared", "") or "/" not in slice_rel else first


def flags_from_rows(corpus: str, rows: Iterable[dict], report_prefix: str) -> list[Flag]:
    """The flags of memory_check's rows: one per section whose verdict is stale-hard or maybe-stale, with a
    reason for each failing path and anchor. `report_prefix` is what the drain report puts before this corpus's
    slices ("memory/" for the fabric's, ".agent-fabric/memory/" for a project's): the key of its last writer."""
    out: list[Flag] = []
    for r in rows:
        if r.get("verdict") not in ("stale-hard", "maybe-stale"):
            continue
        flag = Flag(corpus, r["slice"], r["heading"], section_role(r["slice"], r.get("role")), report_prefix=report_prefix)
        for p in r.get("paths", []):
            if p["status"] == "stale-hard":
                flag.reasons.append({"kind": "stale-hard", "what": p["path"], "detail": "a path the section cites is gone"})
        for a in r.get("anchors", []):
            if a["status"] == "stale-hard":
                flag.reasons.append({"kind": "stale-hard", "what": a["anchor"], "detail": a.get("why") or "the path is gone"})
            elif a["status"] == "maybe-stale":
                flag.reasons.append({"kind": "maybe-stale", "what": a["anchor"],
                                     "detail": f"changed after {r.get('observed', '?')}: {a['commit']} {a['date']} {a['subject']}"})
        out.append(flag)
    return out


def clip_note(note: Any) -> str:
    """A reader's words as one line of at most NOTE_CLIP characters, no control characters."""
    text = " ".join(re.sub(r"[\x00-\x1f\x7f]", " ", str(note or "")).split())
    return text[:NOTE_CLIP] + ("…" if len(text) > NOTE_CLIP else "")


def one_line(text: Any, limit: int) -> str:
    """Text from a slice, a commit or a reader as one line of at most `limit` characters, no control or line-break
    characters: it reaches a REQUEST as data to read, never as lines of the request itself."""
    flat = " ".join(re.sub(r"[\x00-\x1f\x7f]", " ", str(text if text is not None else "")).split())
    return flat[:limit] + ("…" if len(flat) > limit else "")


def resolve_mark(ident: str, corpora: dict[str, str]) -> tuple[str, str, str] | None:
    """(corpus label, slice relative to its corpus, heading) of a mark's section id `f:<path>#<n>` or
    `p:<path>#<n>`, n counted from 1 in the slice's file order (memory_index.section_id), or None when the id
    names no section of a corpus given. `corpora` maps `f` and `p` to the corpus root's directory."""
    m = re.fullmatch(r"([fp]):([A-Za-z0-9._/-]+)#([0-9]+)", ident)
    if not m or m.group(1) not in corpora or m.group(2).startswith("/") or ".." in m.group(2).split("/"):
        return None
    rel = m.group(2) + ".md"
    path = os.path.join(corpora[m.group(1)], rel)
    top = os.path.realpath(corpora[m.group(1)])
    if not os.path.realpath(path).startswith(top + os.sep):
        return None           # an id is text a reader wrote: it names a slice of the corpus or nothing
    try:
        _meta, sections = slices.read_existing_slice(path)
    except (OSError, UnicodeDecodeError):
        return None
    headings = list(sections)
    n = int(m.group(3))
    if not 1 <= n <= len(headings):
        return None
    return m.group(1), rel, headings[n - 1]


def flags_from_marks(marks: "Iterable[dict] | dict[str, list[dict]]", corpora: dict[str, str], labels: dict[str, str],
                     into: list[Flag] | None = None) -> list[Flag]:
    """A reader's `stale` or `wrong` mark joins the flag of the section it names (a new flag when there is none);
    `helpful` marks and marks naming no section of the corpora given are left to the caller's report. `marks` is
    the rows of a harvest's marks.jsonl, or the drain report's `memory_marks`: {section id: [{t, verdict, note}]}."""
    if isinstance(marks, dict):
        marks = [{**row, "id": ident} for ident, rows in marks.items() for row in rows if isinstance(row, dict)]
    flags = into if into is not None else []
    by_key = {f.key: f for f in flags}
    for mk in marks:
        kind = MARK_VERDICTS.get(mk.get("verdict"))
        target = resolve_mark(str(mk.get("id", "")), corpora) if kind else None
        if not target:
            continue
        prefix, rel, heading = target
        corpus = labels.get(prefix, prefix)
        key = f"{corpus}:{rel}#{heading}"
        flag = by_key.get(key)
        if flag is None:
            _meta, sections = slices.read_existing_slice(os.path.join(corpora[prefix], rel))
            _date, role = _observed(sections.get(heading, ""))
            flag = by_key[key] = Flag(corpus, rel, heading, section_role(rel, role), report_prefix=REPORT_PREFIX[prefix])
            flags.append(flag)
        note = clip_note(mk.get("note"))
        flag.reasons.append({"kind": kind, "what": "a reader's mark" + (f" of {mk['t']}" if mk.get("t") else ""),
                             "detail": f"the reader's words, not ours: {note!r}" if note else "no note"})
    return flags


def _observed(text: str) -> tuple[str | None, str | None]:
    m = slices.OBSERVED_RE.search(text)
    return (m.group(1), m.group(2)) if m else (None, None)


def number_of(login: str) -> tuple[int, str]:
    """python-dev-02 sorts before python-dev-10; a login with no number sorts as 0."""
    m = re.search(r"-([0-9]+)$", login)
    return (int(m.group(1)) if m else 0, login)


def login_of(address: str) -> str:
    return address.rsplit("/", 1)[-1]


def route(flag: Flag, writers: dict[str, dict], holders: dict[str, list[str]], running: set[str]) -> tuple[str | None, str]:
    """(address, how) of the agent a flag goes to, or (None, why not). `holders` maps a role to the addresses
    that hold it, `running` is the set of addresses with a session now."""
    if not flag.role:
        return None, "no role: its Observed tail names none and its slice is not a role's"
    held = sorted(holders.get(flag.role, []), key=lambda a: number_of(login_of(a)))
    if not held:
        return None, f"role {flag.role!r} has no holder"
    writer = (writers.get(flag.report_key) or {}).get("agent")
    if writer:
        for a in held:
            if login_of(a) == writer:
                return a, "last-writer"
    for a in held:
        if a in running:
            return a, "running-holder"
    return held[0], "lowest-numbered-holder"


def open_message_ids(jobs_doc: dict) -> set[str]:
    """The MESSAGE-IDs of the REQUESTs that are still open jobs in a jobs.json document (queued, active or
    blocked), from each job's source or the `(REQUEST <id>)` of its title."""
    ids: set[str] = set()
    for j in (jobs_doc or {}).get("jobs", []):
        if j.get("state") not in OPEN_STATES:
            continue
        sid = (j.get("source") or {}).get("message_id")
        if sid:
            ids.add(sid)
        ids.update(re.findall(r"\(REQUEST ([0-9a-f-]{36})\)", str(j.get("title", ""))))
    return ids


def plan(flags: list[Flag], writers: dict[str, dict], holders: dict[str, list[str]], running: set[str],
         sent: dict[str, dict], is_open: Callable[[str, str], bool]) -> Plan:
    out = Plan()
    for flag in sorted(flags, key=lambda f: f.key):
        address, how = route(flag, writers, holders, running)
        if address is None:
            out.unrouted.append((flag, how))
            continue
        out.how[flag.key] = how
        prior = sent.get(flag.key)
        if prior and prior.get("to") == address and is_open(address, prior.get("message_id", "")):
            out.open.append((flag, address, prior["message_id"]))
            continue
        bucket = out.requests.setdefault(address, [])
        if len(bucket) >= MAX_FLAGS:
            out.deferred.append(flag)
        else:
            bucket.append(flag)
    return out


def render_request(address: str, flags: list[Flag], sender: str, sender_role: str, project: str,
                   message_id: str | None = None, taxonomy: "gzmsg.Taxonomy | None" = None) -> tuple[str, str]:
    """(the REQUEST's text, its MESSAGE-ID). The text passes gzmsg.validate (against `taxonomy`, the operator's
    role catalogue, when the caller has it); a hint is rendered as a guess."""
    mid = message_id or gzmsg.mint_id()
    roles = sorted({f.role for f in flags if f.role})
    subject = f"memory: {len(flags)} section(s) to check against the tree (ADR-050)"
    lines = [
        "[GZCOORD/1] REQUEST", f"FROM: {sender}", f"ROLE: {sender_role}", f"PROJECT: {project}", f"TO: {address}",
        "REPLY-EXPECTED: no", f"MESSAGE-ID: {mid}", f"SUBJECT: {subject}", "",
        "REQUEST:",
        f"The curated memory of {', '.join(one_line(r, 40) for r in roles) or 'your role'} holds {len(flags)} section(s) a mechanical check or a reader",
        "marked. You hold the code they describe: check each against the tree, as it is now.", "",
    ]
    for i, f in enumerate(flags, 1):
        lines.append(f"{i}. {one_line(f.slice, 200)} — {one_line(f.heading, 120)!r}" + (f" ({one_line(f.role, 40)})" if f.role else "")
                     + f"  [{one_line(f.corpus, 60)}]")
        for r in sorted(f.reasons, key=lambda r: KIND_ORDER.index(r["kind"])):
            lines.append(f"   - {r['kind']}: {one_line(r['what'], 200)} — {one_line(r['detail'], 240)}")
        if f.hint:
            lines.append(f"   - a model's guess, advisory, not a finding: {clip_note(f.hint)}")
        lines.append("")
    lines += [
        "ACCEPTANCE:",
        "Each section is settled by one memory of yours with `merge_target: \"<the section's heading>\"`: the",
        "corrected claim, or the same claim unchanged (its Observed date then re-dates the section), or no body",
        "at all to retire it (ADR-050 rules 4 and 7). Nothing here edits a slice; the next drain applies yours.", "",
        "DELIVER-TO:", "The memory itself, in your own memory directory.", "",
        "REFERENCES:", "- path: docs/adr/ADR-050-keeping-wisdom-true.md", "",
    ]
    text = "\n".join(lines)
    check = gzmsg.validate(text, taxonomy=taxonomy)
    if check["errors"]:
        raise ValueError("the flag REQUEST does not validate: " + "; ".join(check["errors"][:3]))
    return text, mid


def record(sent: dict[str, dict], address: str, flags: list[Flag], message_id: str, at: str) -> dict[str, dict]:
    """The ledger after `flags` were sent to `address` as `message_id`."""
    out = dict(sent)
    for f in flags:
        out[f.key] = {"to": address, "message_id": message_id, "at": at}
    return out


def load_ledger(path: str) -> dict[str, dict]:
    try:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
    except FileNotFoundError:
        return {}
    if not isinstance(doc, dict):
        raise ValueError(f"{path} is not a ledger: a JSON object of flag key to {{to, message_id, at}}")
    return doc


def save_ledger(path: str, doc: dict[str, dict]) -> None:
    """Whole, by rename, mode 0600: a ledger half-written would send every flag twice."""
    tmp = f"{path}.{os.getpid()}.tmp"
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, indent=1, sort_keys=True, ensure_ascii=False)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
