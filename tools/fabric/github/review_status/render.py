"""tools/fabric/github/review_status/render.py — the report, as JSON or as text.
A part of tools/fabric/github/pr_review_status.py, whose docstring is the contract."""
from __future__ import annotations

import json
from typing import TYPE_CHECKING
from github.review_status.base import out, jstr, sha8, jkey, login_of
from github.review_status.probe import Probe, Extras

if TYPE_CHECKING:
    from github.pr_review_status import Ctx


def render_json(ctx: "Ctx", p: Probe, x: Extras, cause: str, reason: str) -> str:
    """THE --json CONTRACT. Built from the same values the report prints, so
    the two cannot disagree; a caller reads fields, never the report's prose,
    whose wording is free to change."""
    b = p.buckets

    def rows(reviews, *keys):
        shape = {"login": lambda r: login_of(r), "state": lambda r: r.get("state"),
                 "association": lambda r: r.get("author_association"),
                 "commit_sha8": lambda r: sha8(r.get("commit_id")), "at": lambda r: r.get("submitted_at")}
        return [{k: shape[k](r) for k in keys} for r in reviews]

    try:
        pr_number = int(ctx.pr)
    except ValueError:
        pr_number = float(ctx.pr)
    doc = {
        "pr": pr_number, "state": p.state, "merge_state": p.mergest, "head": p.head,
        "head_reviewed": "yes" if p.head_reviewed else "no",
        "independent": {"count": len(b.independent), "rows": rows(b.independent, "login", "state", "commit_sha8", "at")},
        "blind": {"count": len(b.blind), "rows": rows(b.blind, "login", "commit_sha8", "at")},
        "not_trusted": {"count": len(b.outsiders), "rows": rows(b.outsiders, "login", "association", "commit_sha8", "at")},
        "no_review_coming": None if not cause else {"cause": cause, "reason": reason or None},
        "marked_by_others": {"count": len(b.marked_others), "rows": rows(b.marked_others, "login", "commit_sha8", "at")},
        "verdicts": {"count": len(p.verdicts),
                     "rows": [{"login": v["login"], "commit_sha8": sha8(v["sha"]), "at": v["at"]} for v in p.verdicts]},
        "self": {"count": len(b.self_)},
        "unresolved_threads": x.unresolved,
        "unresolved_paths": [t.get("path") for t in x.threads],
        "checks": {"pass": x.checks_pass, "other": x.checks_other},
    }
    return json.dumps(doc, indent=2, ensure_ascii=False)


def head_evidence(p: Probe) -> str:
    """" — <what covers the head>", or nothing when it is not reviewed. The
    blind review says that it is the review class under the shared account,
    so "independent reviews : 0" above it is not read as no review at all."""
    if not p.head_reviewed:
        return ""

    def at_head(rows):
        hit = sorted((r for r in rows if r.get("commit_id") == p.head), key=lambda r: jkey(r.get("submitted_at")))
        return hit[-1] if hit else None

    r = at_head(p.buckets.blind)
    if r:
        return (f" — the review class's blind review of {jstr(sha8(r.get('commit_id')))}, {jstr(r.get('submitted_at'))}"
                " (posted under the account every session pushes as)")
    r = at_head(p.buckets.independent)
    if r:
        return f" — an independent review ({jstr(login_of(r))}, {jstr(sha8(r.get('commit_id')))}, {jstr(r.get('submitted_at'))})"
    return " — a verdict comment on this head"


def render_text(ctx: "Ctx", p: Probe, x: Extras) -> None:
    b = p.buckets
    out(f"PR #{ctx.pr}  state={p.state}  mergeState={p.mergest}  head={p.head[:8]}")
    line = f"  independent reviews : {len(b.independent)}"
    if p.qual_count > 0:
        line += f"   (newest against {p.newest_ind_commit[:8]})"
    out(line)
    for r in b.independent:
        out(f"      - {jstr(login_of(r))}  {jstr(r.get('state'))}  commit={jstr(sha8(r.get('commit_id')))}  {jstr(r.get('submitted_at'))}")
    line = f"  verdict comments    : {len(p.verdicts)}"
    if p.verdicts:
        line += "   (a clean review leaves no review object)"
    out(line)
    for v in p.verdicts:
        out(f"      - {jstr(v['login'])}  commit={jstr(sha8(v['sha']))}  {jstr(v['at'])}")
    out(f"  blind reviews       : {len(b.blind)}" + ("   (the review class — coverage)" if b.blind else ""))
    for r in b.blind:
        out(f"      - {jstr(login_of(r))}  commit={jstr(sha8(r.get('commit_id')))}  {jstr(r.get('submitted_at'))}")
    if b.outsiders:
        out(f"  not trusted         : {len(b.outsiders)}   (NOT coverage — not the owner, a member, a collaborator or a configured reviewer)")
        for r in b.outsiders:
            out(f"      - {jstr(login_of(r))}  {jstr(r.get('author_association'))}  commit={jstr(sha8(r.get('commit_id')))}  {jstr(r.get('submitted_at'))}")
    if b.marked_others:
        out(f"  marked, other login : {len(b.marked_others)}   (NOT coverage — the marker is public; only the")
        out("                        account the sessions push as may post a blind review)")
        for r in b.marked_others:
            out(f"      - {jstr(login_of(r))}  commit={jstr(sha8(r.get('commit_id')))}  {jstr(r.get('submitted_at'))}")
    out(f"  self reviews        : {len(b.self_)}   (thread replies etc. — not coverage)")
    out(f"  review requested?   : {'yes' if p.requested > 0 else 'no'}")
    if p.request_at:
        out(f"  review asked        : {p.request_at}"
            + ("   (in flight — nothing has answered it yet)" if p.request_pending else "   (already answered)"))
    if p.refusal_at:
        out(f"  reviewer declined   : {p.refusal_at}"
            + ("   (nothing has superseded it)" if p.refusal_current else "   (superseded by later coverage)"))
        if p.refusal_reason:
            out(f"  decline reason      : {p.refusal_reason}")
    # The line names what covers the head, because it is the one a reader
    # keeps: agents trim this report with `tail`, and a verdict whose
    # evidence sits at the top reads, trimmed, as "NOT coverage" twice and a
    # bare yes. That is what a permission check saw before refusing an
    # owner-approved arm as a merge without review (a managed project's PR).
    # The parsers read only the first word after the colon.
    out(f"  head reviewed?      : {'yes' if p.head_reviewed else 'no'}{head_evidence(p)}")
    if not p.head_reviewed and p.qual_count > 0:
        out("                        ^ reviewed, but an EARLIER commit. Nothing reviews a")
        out("                          push by itself — dispatch a re-review of the new range.")
    out(f"  unresolved threads  : {'unknown' if x.unresolved is None else x.unresolved}")
    if x.unresolved:
        for t in x.threads:
            out(f"      - {jstr(t.get('path'))}  outdated={jstr(t.get('isOutdated'))}")
    if x.checks_pass is None:
        out("  checks              : unknown")
    else:
        out(f"  checks              : {x.checks_pass} pass, {x.checks_other} other")
