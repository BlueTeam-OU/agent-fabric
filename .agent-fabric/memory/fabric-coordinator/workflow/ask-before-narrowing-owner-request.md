---
role: "fabric-coordinator"
class: workflow
topic: "ask-before-narrowing-owner-request"
description: "Before a contract narrows or reshapes what the owner asked for (an out-of-scope line, a cheaper shape), ask the owner; never decide it in the REQUEST"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 4960289bd542312f
---

## Before a contract narrows or reshapes what the owner asked for (an out-of-scope line, a cheaper shape), ask the owner; never decide it in the REQUEST

2026-10-15: the owner asked for per-agent sub-tabs in FleetDeck. My REQUEST
01a13fb9 to rust-ui-dev-02 wrote "a first-class tab mode in Rust is out of
scope" and proposed a fourth pane toggled by zoom; FleetDeck #33 built that,
I deployed it, and the owner saw four panes at once — not the second row of
yellow sub-tabs, one view at a time, that was meant. The owner: "why this —
ask next time."

**Why:** the scope cut was my cost judgement, not the owner's; a contract
carries it as if it were the requirement, and the builder cannot see the gap.

**How to apply:** when a contract for an owner's request would exclude
something, pick a cheaper shape, or read an ambiguous word ("sub tabs") one
way, ask the owner first (AskUserQuestion, with a sketch), and quote the
owner's words in the REQUEST beside my reading. Related:
[[owner-commands-one-line]].

**Again 2026-10-16:** "a second row of tab (... in yellow background ...)" — I passed it on as the
row's colour; the owner meant the selected sub-tab ("yellow background was for selected tab").
An ambiguous attachment (which noun does a colour, a key, a scope belong to?) is a question to ask
with a sketch before the contract goes out, not a reading to pick.

*References: owner-commands-one-line*

*Observed 2026-10-15 (fabric-coordinator)*
