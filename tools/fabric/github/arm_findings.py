"""tools/fabric/github/arm_findings.py — gate 4c of fabric-pr arm: a finding left open in ANY review chain of a pull
request, not only in the latest one (REQUEST 01a18fe0). #425 merged with F5 open: an earlier chain raised it, nothing
judged it, and a fresh full review of the head started a new chain the review gate alone read as "head reviewed".

The rule, as the request states it:
  - the reviews read are the review objects whose first line is the v2 marker (review_coverage.MARKER_V2), from an
    account the blind review counts from (the PR's author, a login in AGENT_FABRIC_REVIEW_POSTERS, or on an app's
    PR the account gh acts as: review_posters), oldest first by GitHub's review id, never by submitted_at
    (review_status.base.review_order);
  - a review whose base= is the head= of an earlier review continues that review's chain; any other starts one;
  - each body is read by errors.parse_machine_lines, the one reader of the Finding:/Judgement: lines;
  - a Finding is open until a LATER review judges its label fixed or not-real; the latest judgement of it wins, so a
    real, partly or not-fixed after a fixed opens it again. A judgement goes to its own chain whenever that chain
    ever raised the label, open or closed (a repeated fixed re-closes its own, #437 F1); only a label its chain
    never raised goes to the chains begun before its own; among those, the newest earlier Finding of the label, a
    fixed or not-real taking an open one first. In both, a judgement never applies to a Finding raised on its own
    head unless its own base is that head: another engine's review of the same range numbers from F1 too, in
    another chain (#437 round 3 F5) or in the same one (both bases one chain's head, #437 round 4 F8), and its
    findings are not what this one judged; a review whose base is that head (H..H, the next round) has read them.
    Two findings that share a label are told apart by nothing but that order: a judgement may close the wrong one and leave the right one open, which over-blocks —
    the accepted cost; under-blocking is the defect this gate exists for;
  - an ADJUDICATION (review_coverage.is_adjudication: a review post_review accepted on the head of any earlier review
    that raised findings, judgements only, REQUEST 01a1cf77) judges only the findings raised on its base head, by any
    review of that head, whichever chain raised them: so a finding from round 1 of 3 is closed by a review based on
    round 1's head, and two rounds that both number an F1 are told apart by the head. It is no link of any chain: it
    neither continues nor starts one, so a later review based on its head continues the chain that head was in. One
    that raises a Finding is unknown, never read: post_review posts none, and its findings would be judged by nothing
    that reads its head as a chain's;
  - a review read as nothing — no body or no id from the API, a body with no machine lines, a malformed line — is unknown,
    never "no findings": the gate refuses naming it. One way out for the last two: a LATER review from a trusted
    account whose body has a line `Supersedes: <review-id>` naming that review (an id on this PR) is skipped as
    unknown — an unparsed report cannot be edited or re-posted in place, and post-review only creates. It lifts
    nothing else: a review that parses keeps its findings, and a body the API did not return stays unknown.
Pure: the caller (arm.py) reads the reviews and decides what to do with the answer.
"""
from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass, field

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import errors  # noqa: E402 — python-dev's file: imported, never copied (a change to it is a supply request)
from github import review_coverage  # noqa: E402
from github.review_status.base import review_id, review_order  # noqa: E402

CLEARS = ("fixed", "not-real")
SUPERSEDES = re.compile(r"^Supersedes: ([0-9]+)[ \t]*$", re.M)


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
    supersedable: list[str] = field(default_factory=list)  # ids of the unknown reviews a `Supersedes:` line can lift
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


def _superseded(reviews: list, trusted: set[str]) -> set[int]:
    """Ids named by a `Supersedes:` line of a LATER review (GitHub's id order) from a trusted account whose body is a
    v2 review: one without the marker is no review gate 4c reads, so it must not lift one that is. An id no review on
    the PR carries is never looked up, so a typo skips nothing."""
    out: set[int] = set()
    for r in reviews:
        if not isinstance(r, dict) or review_id(r) is None or not isinstance(r.get("body"), str):
            continue
        if str((r.get("user") or {}).get("login") or "") not in trusted or review_coverage.parse_marker(r["body"]) is None:
            continue
        out.update(t for t in map(int, SUPERSEDES.findall(r["body"])) if review_id(r) > t)
    return out


def read(reviews: list, trusted: set[str]) -> Reading:
    """The open findings of every chain, from the REST review objects of one PR (any order)."""
    out = Reading()
    rows = []
    superseded = _superseded(reviews, trusted) if isinstance(reviews, list) else {}
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
            # Without an id it is named by the commit GitHub says it reviewed, the one thing left to find it by.
            name = f"review {rid}" if r.get("id") else f"review of commit {str(r.get('commit_id') or '?')[:8]}"
            out.unknown.append(f"{name} (the API returned no body)")
            continue
        marker = review_coverage.parse_marker(body)
        if marker is None:
            continue
        if review_id(r) is None:
            # Its place in the order is unknown, and with it which judgement comes after which Finding.
            # Named by its marker's head, which a person finds it by: "review ?" named none (#465 round 3 risk).
            out.unknown.append(f"review marked for head {marker.head[:8]} (the API returned no id: its place among the"
                               " reviews is unknown)")
            continue
        rows.append((review_order(r), rid, marker, body))
    # Oldest first, by GitHub's review id: never its submitted_at, which it has served in the future (review_order).
    rows.sort(key=lambda x: x[0])
    chain_of_head: dict[str, int] = {}
    chain_first: list[int] = []
    for order, (_, rid, marker, body) in enumerate(rows):
        out.reviews += 1
        if review_coverage.is_adjudication(body):
            _adjudicate(out, rid, marker, body, int(rid) in superseded)
            continue
        chain = chain_of_head.get(marker.base)
        if chain is None:
            chain = len(out.chains)
            out.chains.append(marker.head)
            chain_first.append(order)
        else:
            out.chains[chain] = marker.head
        chain_of_head[marker.head] = chain
        parsed = errors.parse_machine_lines(body)
        # Only a report read as nothing can be superseded: its chain position above still counts (its head is a head).
        if (parsed is None or parsed.unparsed) and int(rid) in superseded:
            continue
        if parsed is None:
            out.supersedable.append(rid)
            out.unknown.append(f"review {rid} (no Finding:/Judgement: lines: an older report is unread, not clean)")
            continue
        if parsed.unparsed:
            out.supersedable.append(rid)
            out.unknown.append(f"review {rid} (machine lines do not parse: {'; '.join(parsed.malformed) or 'malformed'})")
            continue
        # Judged before this review's own findings are added: a review never judges what it raises itself.
        for label, verdict, _ in parsed.judgements:
            # Never a Finding raised on this review's own head, unless its base is that head: a second engine's
            # review of the same range raises its own F1, which this judgement never saw, whether the two bases start
            # two chains (#437 round 3 F5) or continue one (both on a chain's head h0, #437 round 4 F8); closing it
            # would arm with that F1 unjudged. A review of H..H (an adjudication, the next round) read the findings
            # raised on H, and judges them. The filter is on both pools, so a chain that raised the label only on
            # this head counts as never having raised it.
            same = [f for f in out.findings if f.label == label and (f.head != marker.head or marker.base == marker.head)]
            # Its own chain whenever that chain ever raised the label, open or closed: a repeated `F1 | fixed` (a
            # second engine on the range, the next round restating it) re-closes its own F1 and never spills onto
            # an earlier chain's open F1 (#437 F1). Only a label its chain never raised goes to the chains begun
            # before. Within the chosen chains, newest first, a clearing verdict preferring one still open.
            mine = [f for f in same if f.chain == chain]
            pool = mine or [f for f in same if chain_first[f.chain] < chain_first[chain]]
            pool.sort(key=lambda f: -f.order)
            if verdict in CLEARS:
                pool = [f for f in pool if f.open] + [f for f in pool if not f.open]
            if pool:
                pool[0].open = verdict not in CLEARS
        for label, level in parsed.findings:
            path, summary = _where(body, label)
            out.findings.append(Finding(rid, marker.head, chain, order, label, level, path, summary))
    return out


def _adjudicate(out: Reading, rid: str, marker, body: str, superseded: bool) -> None:
    """One adjudication's judgements, applied to the findings raised on its base head and to no other: the newest
    first, a clearing verdict preferring one still open (as in a chain). Its own head is never its base (post_review
    refuses an empty range), so no finding raised on the commit it read is reachable from it."""
    parsed = errors.parse_machine_lines(body)
    if parsed is None or parsed.unparsed or parsed.findings:
        if not superseded:
            out.supersedable.append(rid)
            if parsed is None:
                why = "no Finding:/Judgement: lines"
            elif parsed.unparsed:
                why = f"machine lines do not parse: {'; '.join(parsed.malformed) or 'malformed'}"
            else:
                why = "it raises findings, which no later review would judge: an adjudication judges only"
            out.unknown.append(f"review {rid} (an adjudication: {why})")
        return
    for label, verdict, _ in parsed.judgements:
        pool = sorted((f for f in out.findings if f.label == label and f.head == marker.base and f.head != marker.head),
                      key=lambda f: -f.order)
        if verdict in CLEARS:
            pool = [f for f in pool if f.open] + [f for f in pool if not f.open]
        if pool:
            pool[0].open = verdict not in CLEARS


def raised_on(reviews: list, trusted: set[str], head: str) -> set[str]:
    """The labels `read` counts as raised on `head`: what an adjudication based on it can judge (post_review asks it
    before posting one). From `read` itself, so the two never disagree on which review is read."""
    return {f.label for f in read(reviews, trusted).findings if f.head == head}


def defer_key(text: str) -> tuple[str, str] | None:
    """(head prefix, label) of a --defer "<review-head8>:F<n>", None when it is not that shape."""
    head, sep, label = text.partition(":")
    head = head.lower()
    if not sep or len(head) < 8 or any(c not in "0123456789abcdef" for c in head) or not errors.FINDING_LABEL.fullmatch(label):
        return None
    return head, label


def matches(f: Finding, key: tuple[str, str]) -> bool:
    return f.head.startswith(key[0]) and f.label == key[1]
