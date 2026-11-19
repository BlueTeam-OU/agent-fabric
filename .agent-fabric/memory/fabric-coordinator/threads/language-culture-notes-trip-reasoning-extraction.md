---
role: "fabric-coordinator"
class: threads
topic: "language-culture-notes-trip-reasoning-extraction"
description: "language-culture-ge's safeguard stops ([reasoning_extraction]) came right after shell appends of Georgian reasoning notes, which its charter asks for as proof of thinking in the locale"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 0aca733551a52573
---

## language-culture-ge's safeguard stops ([reasoning_extraction]) came right after shell appends of Georgian reasoning notes, which its charter asks for as proof of thinking in the locale

2026-11-10, language-culture-ge, job j146 (ka-GE glossary). The model's safeguards stopped the session three times, each with
`Details: [reasoning_extraction]`. The first stop came right after a `cat >> ~/.local/state/agent-fabric/agents/<login>/notes/2026-11-10.md <<'EOF'`
of Georgian first-pass/second-pass working notes; the heredoc was cut off. The second came while re-appending the missing
part, and the third right after a validator grep in the same j146 flow. The agent then held 9 queued jobs, waiting for
"the operator's word". Three gzapp PRs (#1235, #1236, #1237) waited on its Georgian.

The charter (identities/roles/language-culture/charter.md, "You think in the language…" and "The signature is measured…
it is your notes") asks the holder to put its reasoning and inner dialogue into the daily notes file, as proof of
thinking in the locale. A model writing out its own reasoning is what `reasoning_extraction` reads as. This is a
hypothesis from 3 stops out of 3 in this session, with no control run. It also fits the 2026-10-18 stop
([[safeguard-refusal-stalls-agent]]).

Unstick that worked: `/clear` in its pane, then a relayed owner's word with an interim rule: the notes hold only the
translated request, renderings and findings as short lines, with no account of reasoning; the file is written with
Write/Edit, never a heredoc; on another stop, REPLY to me and take the next job. Charter fix queued (j732).

Recurrence 2026-11-10 ~07Z: language-culture-en stopped the same way (heredoc append of reasoning notes, j262); /clear + relayed interim rule restarted it. language-culture-ge, after the interim rule, still appended notes by heredoc and was stopped again on j146 (WIP ff4ddc698 local, unpushed); it moved to j150. The interim rule does not hold across a /clear: j732 (charter fix) is the only durable fix.

**Owner 2026-11-10 ~20Z decided the fix's scope:** drop the reasoning notes only (rule 3). "You think in the language", translate-the-request-in and the locale-worker stay. Commit b1b8ce3d (charter "Your notes are a record of the work, never of your reasoning" + four brief lines) on the j706 branch; the ge/ru/en renderings still carry the old text until their holders render it, so the fix reaches a holder only after its translation lands.

*References: safeguard-refusal-stalls-agent*

*Observed 2026-11-10 (fabric-coordinator)*
