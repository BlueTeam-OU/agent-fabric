# The job list against real working copies, before merge (2026-09-28)

What was measured, on develop-qzapp as user, before the job-list branch
(ADR-037) opened its pull request. The branch's `fabric-jobs`, its
session-start hook and its `fabric-status` ran against this host's real
checkouts (`agent-fabric`, `agent-fabric-gateway`, `InterWeave`), with a
scratch state directory so neither this login's list nor its binding was
touched.

## The probe

From the agent-fabric checkout: four jobs added, two of them for other
projects by `--project` (`agent-fabric-gateway`, `interweave`) and one
more in agent-fabric with the same topic as the first. The first was
started and delivered, then `fabric-jobs next` named the same-topic job,
which was finished, then `next` took the oldest queued job. Last, the
session-start hook ran with its `cwd` in agent-fabric and in the
gateway, and `fabric-status` ran.

## What came back

- **The first run found a defect.** The gateway job took the agent-fabric
  checkout as its working copy. The sibling search looked beside the
  fabric in use, which was the branch's worktree outside the workspace,
  and the fallback was the current directory's checkout. After the fix
  (the search starts beside the current working copy, and another
  project's job never takes it), the gateway job's working copy was
  `/home/user/projects/agent-fabric-gateway` and InterWeave's was its
  own. Both cases are now in `tests/test_jobs.py`, and both fail on the
  code before the fix.
- **The same project and topic continued here.** `next j4` after j1
  printed `continue here: the same repository and topic as j1.`
- **Another project was a fresh session.** `next` then took j2 and
  printed `fresh session: against j4, working copy
  /home/user/projects/agent-fabric-gateway, not
  /home/user/projects/agent-fabric; topic 'gateway docs', not 'job
  list'.` followed by `run: fabric-fresh --job j2`.
- **The hook saw the mismatch.** In agent-fabric, the jobs line named the
  active job and warned that it is in the gateway, naming
  `fabric-fresh --job j2`. In the gateway, the same line had no warning.
- **`fabric-status` printed** `jobs  active j2 (gateway CLAUDE.md bullet
  sync); 1 queued, 0 blocked, 1 delivered`.

## Not read back here

- **The relaunch itself.** `fabric-fresh --job` stopping a real session,
  and the launcher starting the next one in the job's working copy, is
  covered by `runtime/openrouter/test_launch.sh` with a fake session:
  the relaunch's directory, the opening prompt, a dirty copy, a missing
  copy. The opening prompt reaches the harness the way the `--note`
  already did in ADR-022 rule 10. A real session ended this way is read
  back once the branch is merged and distributed.
- **`fabric-ctl <login> jobs` and `jobs-add` over the relay.** Each account's
  control agent must run the merged code first. Read back at
  distribution: `jobs-add` on one login, then `jobs` on `all`.

## What it decides

The working-copy lookup is fixed in this pull request, and the rules of
ADR-037 stand as written. The two read-backs above are due when the
branch is distributed, before the job list is relied on across the
fleet.
