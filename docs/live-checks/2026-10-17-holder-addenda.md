# Holder addenda, the first live installs — 2026-10-17

ADR-060's mechanism (#290) was built and tested on throwaway stores and keys.
Whether a real parent-signed install, taken by a real `fabric-secrets sync`,
renders in a real launch, and renders only for its own holder, needs a live
read-back.

**Run.** 2026-10-17 between about 12:35Z and 12:40Z, on develop-qzapp, main at
58d4d33e (#290 and #291 merged and distributed). The owner approved three sets
of drafts in the coordinator's session; the coordinator copied each holder's
drafts aside, checked each file's sha256 against the holder's report, refreshed
its mirror of the holder's store (`fabric-secrets store refresh-mirror`; all
three were behind their remotes, and `roles-put` refused until they were not),
and installed with `fabric-secrets child roles-put --agent <login> --role
<role> --from <dir> --approval owner-2026-10-17-session-cae3ed99-stage4-approved
--authored-by <login>`. Each holder then ran `fabric-secrets sync`, relaunched
into a fresh session (`fabric-fresh`), and read back from that session.

## Result

| holder | role | install commit | `fabric-status` addenda line | where the addenda render in `launch-prompt.md` |
|---|---|---|---|---|
| legal-expert-ee-eu | legal-expert | a2734ff | `store a2734ffd4d06  addenda commit a2734ffd4d06` | charter line 15, its charter addendum 94, brief 141, its brief addendum 334 |
| legal-expert-ch | legal-expert | 960a3b7 | `store 960a3b7a9742  addenda commit 960a3b7a9742` | charter 15, charter addendum 94, brief 140, brief addendum 333 |
| language-culture-en | language-culture | 3b780f6 | `store 3b780f694ed9  addenda commit 3b780f694ed9` | header 1, charter 15, charter addendum 216, brief 257, brief addendum 364, team 393, memory 475 |

- No launch refused. Each prompt file's sha256 equals the digest `fabric-status`
  reports for the launch.
- The install commit on the coordinator's mirror (ee-eu, a2734ff) carries a good
  signature by the coordinator's key (`%G?` = G, D70E86CC226240EA), the trailers
  Addendum-Role, Authored-By, Owner-Approval and one Against-Digest per file,
  and exactly the two files under `settings/roles/legal-expert/`.
- Two holders of one role render different prompts: ee-eu's carries its
  Estonian and EU text ("Riigikohus judgments are cited by case number and
  date", line 349), ch's its Swiss text ("Three languages, one law", line 347),
  each only its own.
- legal-expert-ee-eu's prompt is 30 366 bytes with both addenda, within the
  ceiling the addenda widen (ADR-060 §5 rule 6).

## What it decides

The mechanism works end to end on real stores: stage 4 can go on (the Georgian
addenda after language-culture-ge's two passes), and stage 5 can remove the
jurisdiction and English-holder text from the shared charters and briefs once
every holder that needs it has its addenda installed.

**Georgian holder, read back 2026-10-19 ~04:40Z.** Measured by
legal-expert-ge in its own session and store, reported in its reply
01a15275-ec27-7f00-82f0-7d4532f95d61 to the coordinator's question
01a15275-4318. Its session (launched 2026-10-18 05:42Z) reports
`addenda  store f82a566fe919  addenda commit f82a566fe919; the store has
moved past the launch`, and no prompt-drift line. The newer commit, its
store's HEAD d7ae99c, is a working-state backup; `git diff f82a566 HEAD
-- settings/roles/legal-expert/`, run by legal-expert-ge in its own
store, is empty, so it renders the addenda the store holds. Its launch
prompt, as it read it, carries the charter addendum at line 90 and the
brief addendum at line 327, both Georgian headings. With it, every
holder the plan named has its addenda read back from a live session.
The "moved past the launch" note on a store change that leaves the
addenda alone reads like drift and is not; python-dev-01's request
01a15277-3a9a-7536-a880-b777aedfd325 asks to reword it (its j133).

Not shown here: a refusal on a real store (an agent-signed commit, a stale
mirror at launch). The suites cover those on throwaway stores; the first real
one, if it happens, is read back here.
