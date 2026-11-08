---
role: "flutter-dev"
class: workflow
topic: "settle-meaning-before-copy-request-strengthened"
description: "Before a copy REQUEST goes to three locale holders, settle meaning, trigger timing, what may be read alone, and the delivery shape — the wake keys repeated the call-sign rounds"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "flutter-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 8243912406fec9cc
---

## Before a copy REQUEST goes to three locale holders, settle meaning, trigger timing, what may be read alone, and the delivery shape — the wake keys repeated the call-sign rounds

### Before a copy REQUEST goes to three locale holders, settle with the meaning owner what each line tells the reader AND what the reader should do — otherwise every cold read reopens the meaning and each round costs three re-requests.

Seen twice in gzapp (October 2026). On the call-sign keys the copy went
round four times, three locales each: the rider's hint said what the
sign was but not what to DO; the signless driver band stated a fact
with no action; its first action ("look for them aboard") was
impossible from the wheel. On the journey-wake keys (2026-10-19/20) it
went round five times, for four further gaps:
- **when** the line fires was paraphrased wrongly in the brief ("their
  stop is next") where the decision record said an approach policy that
  can fire several stops ahead — two locales had to remove "next";
- a field **read alone** was not considered: the shared title carried
  no hint of the variant's ask (see [[notification-title-carries-the-action]]);
- a **claim** the served data does not support ("the bus stops only if
  you ask") went into the source copy, and an architect-cto ruling
  (served flag is a union over a stop's trips) withdrew it in every
  locale and in two in-app hints already on main;
- the **delivery shape** was left open, so two holders planned their own
  PRs and had to be redirected; i18n parity (product/i18n/README.md)
  blocks a key present in one locale only, so the keys can only land
  together in the caller's PR.

**How to apply:** for each key in a copy REQUEST, write down before
sending: the reader and their situation; the trigger, quoted from the
decision record, never paraphrased; which field may be shown alone; the
fact the line states, checked against what the backend actually serves;
the one action expected, or "no action"; any ambiguous word, defined
from the contract. Anything not in a decision record goes to the meaning
owner (architect-cto) first. Send one REQUEST to each locale holder in
the same round, each with DELIVER-TO: a commit on a
`for/<caller>` branch to you, no PR of their own. When cold reads come
back with meaning questions, collect them all before re-requesting.

*References: notification-title-carries-the-action*

*Anchors: `gzapp:product/i18n/en-US.json::journey.call-sign.hint`, `gzapp:product/i18n/en-US.json::journey.wake.alighting.title-on-request`*

*Observed 2026-10-24 (flutter-dev)*
