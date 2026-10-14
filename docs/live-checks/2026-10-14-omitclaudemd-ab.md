# omitClaudeMd, measured on a subagent — 2026-10-14

The review-economics work (ADR-020 rule 9) rests on one harness switch:
a subagent defined with `omitClaudeMd: true` does not load the
project's instruction files. The documentation does not say which files
that covers, in particular whether the `@`-imported `AGENTS.md` and the
auto-memory index go too, and a design decided from documentation is a
guess until a live read-back confirms it. An A/B run measured it.

**Run.** 2026-10-14 at about 09:45Z, on develop-qzapp, as the
coordinator's login (`fabric-coordinator`), Claude Code 2.1.286.
`claude -p` in `~/projects/gzapp`, one custom subagent defined through
`--agents`, model `sonnet`, hooks off through
`--settings '{"disableAllHooks":true}'`, the subagent reading
`README.md`. Run once without `omitClaudeMd` and once with
`omitClaudeMd: true`. Both read from the subagent transcripts.

## Result

| run | first-turn context | turns | instruction files loaded |
|---|---|---|---|
| without | 36,172 tokens | 2 | `projects/CLAUDE.md` 320 B, `agent-fabric/CLAUDE.md` 1,350 B, `agent-fabric/AGENTS.md` 13,060 B, `gzapp/CLAUDE.md` 70,438 B, the auto-memory `MEMORY.md` 5,357 B |
| with `omitClaudeMd: true` | 2,031 tokens | 2 | none |

- The switch removes all of it: the project's `CLAUDE.md` chain, the
  `@`-imported `AGENTS.md` (13,060 B, reached only through
  `agent-fabric/CLAUDE.md`), and the auto-memory index. Neither the
  import nor the memory index is documented as covered; this run
  measured it.
- What is left is the harness's own prompt and the subagent's
  definition: 2,031 tokens, against 36,172.

## A void first attempt

A first attempt used `--setting-sources local` to keep the project's
settings out. It also stopped the project instruction files from
loading in the run that should have had them, so it measured only
`MEMORY.md` (4,291 against 2,030 tokens). It is void: it does not
compare the two cases, and no number above comes from it.

## Decision

P2 stands as specified. `omitClaudeMd` is the mechanism for a reviewer
that reads a review card in place of the instruction files, because it
drops the `@`-imported `AGENTS.md` and the auto-memory index along with
the `CLAUDE.md` chain; nothing else has to be done to keep them out.

## Not measured

One model (`sonnet`), one repository (gzapp), one two-turn task. The
ratio on a longer review grows with the turns, since the files are
re-sent on every turn; the first-turn figure is the floor of the saving,
not the total.
