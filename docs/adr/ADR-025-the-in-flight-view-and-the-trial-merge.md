# ADR-025 — The in-flight view and the trial merge

**Date:** 2026-09-26
**Status:** Accepted
**Ratified:** owner, 2026-09-27, by arming agent-fabric #52 (ratification by merge, the owner's rule of 2026-09-27)
**Decision Makers:** the owner; drafted by fabric-coordinator
**Scope:** fabric-pr gate (`--in-flight`, `--overlap`, `--path`) and fabric-pr trial-merge, shims of tools/fabric/github/pr_gate.py and trial_merge.py (ADR-040); projects/gzapp/integration/gh/trial.json (a project's declared check); tests/test_pr_gate_cli.py, tests/test_trial_merge_cli.py
**Pillar:** P3
**Evidence:** docs/live-checks/2026-09-26-in-flight-and-trial-merge.md

## 1. Context and Problem

The fleet's most frequent rework was the same work started twice (the
survey of 2026-09-26, ADR-024). One cause was that a job waiting for a
merge sits on a pushed branch with no pull request, where no tool
looked: `pr-gate.sh` read open PRs only. On 2026-09-26 an assignment was
withdrawn three minutes after it was made, an hour lost, because the job
had sat on such a branch since 2026-09-21. `pr-gate.sh`'s own help
records 62 such branches against 3 open PRs in the first managed project
that day; the read-back, later the same day, counted 26 branches in
flight there.

The other cause was relying on another agent's branch without knowing
whether the two combine. CI and the merge queue test a PR against `main`
only, never with a sibling it depends on, and folding the sibling into
one's own clone froze that clone for twenty minutes, or left a hand-made
worktree behind.

## 2. Decision

Two read-only tools, built on the owner's acceptance, that
report and decide nothing:

- **The in-flight view** — `pr-gate.sh --in-flight` lists every branch
  on origin not merged into the base, PR or not, with its owner, its PR
  or "no PR", commits ahead, last commit time and the paths it changes;
  `--path <prefix>` keeps the rows touching a prefix, and `--overlap
  <PR|branch>` keeps the rows sharing a changed path with it and lists
  the shared paths.
- **The trial merge** — `trial-merge.sh <PR|branch>... [--check]` merges
  the named refs, in order, onto the base in a throwaway worktree, says
  whether they combine, optionally runs the project's own declared check
  on the result, and removes the worktree, leaving the caller's clone as
  it was.

Before assigning a job, starting one, or relying on another agent's
branch, the question "what already exists" is asked of the in-flight
view, and "do these combine" of the trial merge (ADR-024 §5 rule 4).

## 3. Alternatives Considered

- **Reservations or locks on paths.** Rejected: they would move the
  agenda into the control plane (ADR-024); a row says "this exists", and
  the agents decide.
- **Read "shares paths" as "conflicts".** Rejected: two branches can
  touch one file and merge cleanly; the trial merge answers that.
- **Fold the sibling into one's own clone.** Rejected by what it cost:
  a frozen clone, or a worktree left behind.
- **Read an unavailable check as a pass.** Rejected: a check that timed
  out, was not found, or printed no verdict says nothing; it is
  unavailable, and the exit code says so.

## 4. Rationale

Verification over assertion (ADR-000, P3): a job's existence is read from
git, not from what someone declared, and a combination is proved by
merging it, not by reading two diffs. Tools that reserve nothing keep the
decision with the agents while giving them the facts they lacked.

## 5. Binding Rules

1. `--in-flight` reads every branch on origin from git; GitHub supplies
   only which branches have a PR. A row's owner is the branch's
   `<host>/<login>` prefix, else "unattributed" — never the GitHub
   author. It changes paths against the branch's merge base with the
   base, not what anyone declared.
2. A failed fetch is said first, with the age of the last one, and the
   rows are what origin last showed; an unreadable PR list makes the PR
   column "unavailable", never "no PR".
3. `--overlap` lists shared paths and says that sharing a path is not a
   conflict; nothing in the in-flight view reserves anything.
4. `trial-merge.sh` merges in the order given onto the base in a
   throwaway worktree and reports `combines` (with the resulting tree
   hash), `conflicts` (the ref and the conflicted paths) or `could not
   merge` (git's own line: unrelated histories, a missing object — never
   read as a conflict). The shas tried are printed; the result holds for
   those shas only.
5. The caller's HEAD, index, working tree and branches are unchanged, no
   hook runs, nothing is committed or pushed, and the worktree is removed
   however the run ends, a TERM or INT during the check included.
6. `--check` runs the command the project declares in
   `projects/<id>/integration/gh/trial.json` (found from the clone's
   remote) as an argv in the worktree, within its `timeout_s`, under its
   `lease` when one is named. A declared `verdict` line wins over the exit
   code; a declared verdict that never appears, a timeout, a missing
   command or a held lease is `check unavailable` — never a pass. A
   project that declares none gets merge-only results, and `--check` says
   so; refs that do not combine are not checked.
7. Exit codes: 0 combines (and the check passed); 1 conflicts or the
   check failed; 2 could not try (a failed fetch, a ref not on origin, no
   room for the worktree, bad usage, a merge that failed without a
   conflict) or the check was unavailable.

## 6. Consequences

- On gzapp the first run found 26 branches in flight, most without a PR,
  and six sharing paths with the branch assigned that morning — the view
  would have shown the job before the assignment.
- A fresh worktree has no build cache: a compiled check starts cold, and
  two runs at once each get their own worktree and the same answer.
- `pr-gate.sh` and `trial-merge.sh` reach a project through its
  `tools/gh/` forwarder (`projects/<id>/integration/gh/`); neither is in
  `runtime/claude-code/commands.json`, so run by path they still ask for
  approval.

## 7. Future Evolution

The live check's positive control — a run with gzapp's check available,
expected FAIL on a known pair — was due after gzapp #943 merged;
no later read-back is recorded. A list of owed requests remains unbuilt;
the thread view is built over each agent's own journal (ADR-024 §6).

## 8. Decision Status

Accepted and in force: both tools (d1a136a, cd33e0c, d9eef83).

## References

- `fabric-pr gate` (help: IN FLIGHT) and `fabric-pr trial-merge`,
  shims of `tools/fabric/github/pr_gate.py` (`in_flight`) and `trial_merge.py`; `tests/test_pr_gate_cli.py`,
  `tests/test_trial_merge_cli.py`.
- `projects/gzapp/integration/gh/trial.json`.
- `communication/gzcoord/protocol/MESSAGE-FORMAT.md` §"Working on a
  request together".
- The live check in Evidence. ADR-024, ADR-019 (the gate), ADR-000 (P3).
