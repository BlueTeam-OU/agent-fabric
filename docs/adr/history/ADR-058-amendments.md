# ADR-058 — amendments

The full notes; the ADR's body reads current and its Amendments table lists them.

### Amendment 2026-10-15 — A pass is closed by its cursor

Rule 4 moved the cursor when a pass finished, but `fabric-jobs` settles
`done` only on a merged PR, a commit or branch on the default branch, or
a reply, and a pass lands none of them. The first week's jobs (2026-W42)
showed it: an agent that finished its pass could neither settle the job
`done` nor `drop` it once marked done, so `fabric-jobs next` would not
leave it. The cursor rule 4 already records is the pass's artifact; rule
4 now names it as the job's evidence. Keyed on the job's topic, which the
weekly job carries, never on a title a person can reword; a cursor that
cannot be read, or one closed before the job started, is no evidence.
Built in `tools/fabric/jobsparts/settle.py` by python-dev.
