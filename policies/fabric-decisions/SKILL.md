---
name: fabric-decisions
description: "How to find out why agent-fabric works the way it does, and how to ask for it to change: the decision records in agent-fabric's docs/adr/, read DIGEST first, a record's binding rules, citing \"agent-fabric ADR-NNN\" from another repository, and proposing a change to fabric-coordinator instead of editing. Load it when a rule of the fabric looks wrong or in your way, when a CLAUDE.md, remit, skill or message cites agent-fabric ADR-NNN, before you argue that the fabric should do something differently, or when two fabric texts disagree."
---

# The fabric's decisions

What agent-fabric has decided — how agents are identified, routed,
reviewed, how they talk and what they may change — is written as
numbered decision records in `docs/adr/` of the agent-fabric checkout
(`../agent-fabric/docs/adr/` from a project's working copy). The records
are the fabric's rules; `CLAUDE.md`, the prompts, skills and manuals say
how to act on them.

## Reading

1. **Start at `docs/adr/DIGEST.md`.** One entry per record: its status,
   the rules in a few lines, keywords. To find the entry for a subject:

   ```sh
   python3 ../agent-fabric/tools/fabric/adr.py lookup <word> [<word>…]
   ```

2. **Then the record.** §2 is the decision, §5 its binding rules —
   numbered, and numbers never change; §3 says what was rejected and
   why, §7 what would reopen it. The `Status` line matters: `Accepted`
   binds, `Proposed` is a direction nobody may act on as a rule yet,
   `Superseded` points at its successor.
3. **Amendments.** A record is edited in place and always reads current;
   its `## Amendments` table and `docs/adr/history/` say what changed
   when. A rule marked `(A YYYY-MM-DD)` changed on that date.

Where a record and another fabric text disagree, the record is the
decision and the other text is the defect. Where a record and the
code disagree, report it (below); do not decide it yourself.

## Citing

Inside agent-fabric a record is `ADR-NNN`. From any other repository
it is **"agent-fabric ADR-NNN"** — a project may number its own records,
and a bare number there means the project's.

## Asking for a change

The records, and everything under agent-fabric and every project's
`.agent-fabric/`, are fabric-coordinator's to write. You never edit
them. To change a decision:

- Send a GZCoord `REQUEST` to the login holding fabric-coordinator
  (`gzcoord-send`), or open a pull request on agent-fabric that you do
  not merge.
- Name the record and rule ("agent-fabric ADR-019 §5 rule 4"), what you
  observed — the incident, the command and its output, the cost — and
  what you ask for. A change earns adoption by what was observed, not
  by argument alone.
- Until the record changes, the rule stands. A conversation, a
  `DECISION` message or an agreement between agents is advisory until it
  reaches an artifact; only the owner ratifies a record.
