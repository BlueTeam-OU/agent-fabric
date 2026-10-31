"""tools/fabric/github/arm_findings.py — gate 4c of fabric-pr arm: a finding left open in ANY review chain of a pull
request, not only in the latest one (REQUEST 01a18fe0). #425 merged with F5 open: an earlier chain raised it, nothing
judged it, and a fresh full review of the head started a new chain the review gate alone read as "head reviewed".

The rule, as the request states it:
  - the reviews read are the review objects whose first line is the v2 marker (review_coverage.MARKER_V2), from an
    account the blind review counts from (the PR's author, or a login in AGENT_FABRIC_REVIEW_POSTERS), oldest first;
  - a review whose base= is the head= of an earlier review continues that review's chain; any other starts one;
  - each body is read by errors.parse_machine_lines, the one reader of the Finding:/Judgement: lines;
  - a Finding is open until a LATER review judges its label fixed or not-real; the latest judgement of it wins, so a
    real, partly or not-fixed after a fixed opens it again. A judgement goes to its own chain whenever that chain
    ever raised the label, open or closed (a repeated fixed re-closes its own, #437 F1); only a label its chain
    never raised goes to the chains begun before its own, less every Finding raised on the judging review's own
    head (another engine's review of that head numbers from F1 too, and its findings are not what this one judged:
    #437 round 3 F5); among those, the newest earlier Finding of the label, a fixed or not-real taking an open one
    first. Two findings that share a label are told apart by nothing but that
    order: a judgement may close the wrong one and leave the right one open, which over-blocks —
    the accepted cost; under-blocking is the defect this gate exists for;
  - a review read as nothing — no body from the API, a body with no machine lines, a malformed line — is unknown,
    never "no findings": the gate refuses naming it.
Pure: the caller (arm.py) reads the reviews and decides what to do with the answer.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import errors  # noqa: E402 — python-dev's file: imported, never copied (a change to it is a supply request)
from github import review_coverage  # noqa: E402

CLEARS = ("fixed", "not-real")


@dataclass
class Finding:
    review_id: str
    head: str            # the head of the review that raised it: what --defer names, as <head8>:F<n>
    chain: int
    order: int           # the raising review's place, oldest first
    label: str
    level: str
    path: str
    summary: str
    open: bool = True


@dataclass
class Reading:
    reviews: int = 0
    chains: list[str] = field(default_factory=list)       # each chain's latest head, by chain number
    findings: list[Finding] = field(default_factory=list)
    unknown: list[str] = field(default_factory=list)      # "review <id> (<why>)"

    @property
    def open(self) -> list[Finding]:
        return [f for f in self.findings if f.open]


def _where(body: str, label: str) -> tuple[str, str]:
    """(path, summary) of the Finding line of `label`: errors.Review keeps (label, level) only. Read with errors'
    own line pattern and field reader, so the line chosen is the one parse_machine_lines counted."""
    for rest in errors.FINDING_LINE.findall(body):
        got = errors.parse_finding_line(rest)
        if got and got[0] == label:
            fields = [f.strip() for f in rest.split("|", 4)]
            return fields[3], fields[4]
    return "-", ""


def read(reviews: list, trusted: set[str]) -> Reading:
    """The open findings of every chain, from the REST review objects of one PR (any order)."""
    out = Reading()
    rows = []
    for r in reviews if isinstance(reviews, list) else []:
        if not isinstance(r, dict):
            continue
        login = str((r.get("user") or {}).get("login") or "")
        if login not in trusted:
            continue
        rid = str(r.get("id") or "?")
        body = r.get("body")
        if not isinstance(body, str):
            # Its first line is unread too, so whether it is a v2 review at all is unknown: refused, never skipped.
            out.unknown.append(f"review {rid} (the API returned no body)")
            continue
        marker = review_coverage.parse_marker(body)
        if marker is None:
            continue
        rows.append((str(r.get("submitted_at") or ""), int(r["id"]) if isinstance(r.get("id"), int) else 0, rid, marker, body))
    # Oldest first: GitHub's submitted_at, the id breaking a tie (ids grow with time).
    rows.sort(key=lambda x: (x[0], x[1]))
    chain_of_head: dict[str, int] = {}
    chain_first: list[int] = []
    for order, (_, _, rid, marker, body) in enumerate(rows):
        out.reviews += 1
        chain = chain_of_head.get(marker.base)
        if chain is None:
            chain = len(out.chains)
            out.chains.append(marker.head)
            chain_first.append(order)
        else:
            out.chains[chain] = marker.head
        chain_of_head[marker.head] = chain
        parsed = errors.parse_machine_lines(body)
        if parsed is None:
            out.unknown.append(f"review {rid} (no Finding:/Judgement: lines: an older report is unread, not clean)")
            continue
        if parsed.unparsed:
            out.unknown.append(f"review {rid} (machine lines do not parse: {'; '.join(parsed.malformed) or 'malformed'})")
            continue
        # Judged before this review's own findings are added: a review never judges what it raises itself.
        for label, verdict, _ in parsed.judgements:
            same = [f for f in out.findings if f.label == label]
            # Its own chain whenever that chain ever raised the label, open or closed: a repeated `F1 | fixed` (a
            # second engine on the range, the next round restating it) re-closes its own F1 and never spills onto
            # an earlier chain's open F1 (#437 F1). Only a label its chain never raised goes to the chains begun
            # before, never one raised on this review's own head: a second engine's review of the same head (Codex
            # and Claude both at H1 on base B, two chains) raises its own F1, which this judgement never saw; closing
            # it would arm with that F1 unjudged (#437 round 3 F5). Within the chosen chains, newest first, a
            # clearing verdict preferring one still open.
            mine = [f for f in same if f.chain == chain]
            pool = mine or [f for f in same if chain_first[f.chain] < chain_first[chain] and f.head != marker.head]
            pool.sort(key=lambda f: -f.order)
            if verdict in CLEARS:
                pool = [f for f in pool if f.open] + [f for f in pool if not f.open]
            if pool:
                pool[0].open = verdict not in CLEARS
        for label, level in parsed.findings:
            path, summary = _where(body, label)
            out.findings.append(Finding(rid, marker.head, chain, order, label, level, path, summary))
    return out


def defer_key(text: str) -> tuple[str, str] | None:
    """(head prefix, label) of a --defer "<review-head8>:F<n>", None when it is not that shape."""
    head, sep, label = text.partition(":")
    head = head.lower()
    if not sep or len(head) < 8 or any(c not in "0123456789abcdef" for c in head) or not errors.FINDING_LABEL.fullmatch(label):
        return None
    return head, label


def matches(f: Finding, key: tuple[str, str]) -> bool:
    return f.head.startswith(key[0]) and f.label == key[1]
