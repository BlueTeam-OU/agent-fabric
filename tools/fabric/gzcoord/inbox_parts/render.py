"""tools/fabric/gzcoord/inbox_parts/render.py — a message rendered for the session, cut to the notification's size.
A part of tools/fabric/gzcoord/inbox.py, whose docstring is the contract."""
from __future__ import annotations

import math
import re
from .. import gzmsg
from .. import i18n
from .. import jsvalues as js
from ..gzmsg import en
from .records import one_line, REPLAY_CMD


# ── one delivery, as the session reads it ────────────────────────────
# THE NOTIFICATION CAP. What a --follow watch prints reaches the session as a
# Monitor notification, and the harness shows about 3,000 characters of one
# event (--until-delivery prints the same text and keeps the same cap),
# then "...(truncated)"; the rest lives only in the task's output
# file, which the session does not know to open (architect-cto, 2026-09-16,
# four deliveries cut inside REQUEST or VERIFIED; measured at 3,017
# characters shown). So the watch renders under a cap of its own: a delivery
# that fits is printed whole; one that does not keeps every metadata line,
# cuts the body at a line boundary, and says where it cut and how to read
# the whole message. The drain is not a notification and is rendered whole.
# Lengths are JavaScript's (UTF-16 units), as the cap was measured.
NOTIFICATION_CAP = 2800


MAX_FLAG_LINES = 4


_SECTION = re.compile(r"[A-Z][A-Z0-9-]*:")


def cut_at_line(text: str, max_units: int) -> str:
    """Always at a line boundary: a body whose first line alone is longer
    than the budget keeps nothing of it (the notice says where to read)."""
    if js.length(text) <= max_units:
        return text
    nl = js.last_newline_at_or_before(text, max_units)
    return "" if nl < 0 else text[:nl]


def _drop_final_newline(s: str) -> str:
    return s[:-1] if s.endswith("\n") else s


def split_message(text: str) -> dict:
    """The metadata block ends at the first section marker (SPEC §6: the
    blank line before it MAY be absent), not at a blank line."""
    lines = _drop_final_newline(text.replace("\r\n", "\n")).split("\n")
    at = next((k for k, line in enumerate(lines) if k > 0 and _SECTION.fullmatch(line)), -1)
    if at < 0:
        return {"meta": re.sub(r"\n+$", "", "\n".join(lines)), "body": ""}
    meta_end = at
    while meta_end > 0 and lines[meta_end - 1] == "":
        meta_end -= 1
    return {"meta": "\n".join(lines[:meta_end]), "body": "\n".join(lines[at:])}


def render(res: dict, me: dict, channel: str, taxonomy: gzmsg.Taxonomy | None, cap: float = math.inf,
           t: i18n.Printer | None = None, reminder: str = "") -> str:
    t = t or en()
    mine, others = [], []
    for c in res["classified"]:
        rec, msg = c["rec"], c.get("msg")
        if not msg:
            others.append({"rec": rec, "line": t("inbox.not-a-message", {"id": js.get(rec, "id"),
                                                                       "sender": js.get(rec, "sender")})})
            continue
        (mine if c["isMine"] else others).append({"rec": rec, "msg": msg,
                                                   "retransmitOf": c.get("retransmitOf", js.UNDEFINED)})
    # The reminder rides the head line and nothing else: the one line read
    # on every drain and every delivery; the cap measures the head as it
    # prints.
    who = f"{me['address']}{' (' + me['slug'] + ')' if me.get('slug') else ''}"
    head = t("inbox.head", {"who": who, "mine": len(mine), "others": len(others), "channel": channel}) + reminder
    parts = []
    for p in mine:
        rec = p["rec"]
        # The message has arrived: the terminal-copy width warning does not apply.
        v = gzmsg.validate(rec["content"], taxonomy=taxonomy, max_columns=0, t=t)
        flags = [*(t("delivery.invalid", {"detail": e}) for e in v["errors"]),
                 *(t("delivery.warning", {"detail": w}) for w in v["warnings"])]
        # Only under a cap: the drain shows every validator line.
        if math.isfinite(cap) and len(flags) > MAX_FLAG_LINES:
            flags = [*flags[:MAX_FLAG_LINES], t("delivery.flags-more", {"n": len(flags) - MAX_FLAG_LINES})]
        if p["retransmitOf"] is not js.UNDEFINED:
            flags = [t("delivery.retransmission", {"seq": p["retransmitOf"]}), *flags]
        title = t("delivery.title", {"seq": js.get(rec, "seq"), "sender": js.get(rec, "sender"),
                                     "when": js.get(rec, "timestamp")})
        if flags:
            title += "\n    " + "\n    ".join(flags)
        text = _drop_final_newline(rec["content"])
        parts.append({"rec": rec, "title": title, "text": text, **split_message(text)})
    other_lines = [f"  {o['line'] if 'line' in o else one_line(o['msg'], t)}" for o in others]
    others_block = ["", t("inbox.others-header"), *other_lines] if others else []
    whole = "\n".join([head, *[x for p in parts for x in ("", p["title"], "```text", p["text"], "```")], *others_block])
    if js.length(whole) <= cap:
        return whole

    # Over the cap. Metadata whole and others listed if that fits; the
    # bodies share what is left, each cut at a line and ending with the
    # replay command for its seq. Nothing is claimed to be elsewhere.
    def seqs(lst: list) -> str:
        return t("cap.seq-range", {"first": js.get(lst[0]["rec"], "seq"), "last": js.get(lst[-1]["rec"], "seq")}) \
            if lst else ""

    def notice(p: dict) -> str:
        return t("cap.notice", {"replay_cmd": REPLAY_CMD, "seq": js.get(p["rec"], "seq")})

    others_count = ["", t("cap.others-count", {"count": len(others), "range": seqs(others)})] if others else []

    def layout(tail: list[str]) -> int:
        return js.length("\n".join([head, *[x for p in parts for x in ("", p["title"], "```text", p["meta"], "",
                                                                         notice(p), "```")], *tail]))

    others_tail = others_block
    if layout(others_tail) > cap:
        others_tail = others_count
    fixed = layout(others_tail)
    if fixed > cap:
        # Too many messages for one notification: one line each, read by
        # seq, and the tail says how many lines this listing dropped.
        lines = [head, t("cap.by-seq", {"replay_cmd": REPLAY_CMD})]
        rows = [t("cap.row", {"seq": js.get(p["rec"], "seq"), "line": one_line(gzmsg.parse(p["rec"]["content"]), t)})
                for p in parts]

        def tail_for(n: int) -> str:
            return t("cap.more-for-you", {"n": len(parts) - n, "range": seqs(parts[n:])}) if n < len(parts) else ""

        others_line = t("cap.and-others", {"count": len(others), "range": seqs(others)}) if others else ""
        n = 0
        while n < len(rows) and js.length("\n".join(x for x in [*lines, *rows[:n + 1], tail_for(n + 1), others_line]
                                                    if x)) <= cap:
            n += 1
        return "\n".join(x for x in [*lines, *rows[:n], tail_for(n), others_line] if x)
    budget = int(cap - fixed)
    shares = [0] * len(parts)
    # shortest bodies first: what they do not need goes to the longer ones
    order = sorted(range(len(parts)), key=lambda i: js.length(parts[i]["body"]))
    for k, i in enumerate(order):
        share = budget // (len(order) - k)
        take = min(share, js.length(parts[i]["body"]) + 2)
        shares[i] = take
        budget -= take
    out = [head]
    for i, p in enumerate(parts):
        cut = cut_at_line(p["body"], max(0, shares[i] - 2))
        fits = js.length(cut) >= js.length(p["body"])
        out.extend(["", p["title"], "```text", p["text"] if fits else p["meta"] + ("\n\n" + cut if cut else ""),
                    *([] if fits else ["", notice(p)]), "```"])
    return "\n".join([*out, *others_tail])
