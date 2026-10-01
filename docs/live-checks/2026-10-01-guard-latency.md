# 2026-10-01 — the guards' latency, bash and Python

ADR-040 §6 says the hooks would pay Python's start-up where they were
bash, and that the guards' wave would measure it before and after. This
is that measurement, for the four guards Wave 2 ports:
- the dispatch guard (`runtime/claude-code/hooks/agent-dispatch-guard.sh`),
  which runs before every Agent call a session makes;
- the three policy scripts (`policies/ban_generated_by_attribution.sh`,
  `check_charter_authority.sh`, `check_agent_fabric_dir_authority.sh`),
  which run in CI and in the suites, not at the keyboard.

## How it was measured

On develop-qzapp as user, each case ran 40 times through the same path
its caller uses: `bash` on the script, with stdin as the hook or CI
gives it. The policy scripts ran on the agent-fabric checkout itself.
The wall time of each run was taken in-process. The before column is
agent-fabric at 49d61f2 (bash); the after column is the Wave 2 branch at
270c9ef (Python behind the same paths). Each row also records the answer
each run gave, so a changed answer would show beside a changed time.

| case | before median / p90 (ms) | after median / p90 (ms) | answer before | answer after |
|---|---|---|---|---|
| dispatch: review, allowed | 19.9 / 29.8 | 45.5 / 109.8 | rc=0 | rc=0 |
| dispatch: writer without worktree, denied | 15.9 / 22.5 | 43.2 / 53.8 | rc=0 deny | rc=0 deny |
| dispatch: code-high, asked | 17.9 / 29.3 | 38.7 / 51.5 | rc=0 ask | rc=0 ask |
| policy: ban_generated_by_attribution | 11.8 / 16.7 | 69.7 / 144.2 | rc=0 | rc=0 |
| policy: check_charter_authority | 12.5 / 22.8 | 46.3 / 55.1 | rc=0 | rc=0 |
| policy: check_agent_fabric_dir_authority | 43.5 / 81.4 | 72.7 / 142.4 | rc=0 | rc=0 |

The p90 column is noisy on this host: one run of the same Python case
gave 115 ms and the next 54 ms. Read the medians.

## What it decides

- Every answer is unchanged.
- The dispatch guard costs about 25 ms more per Agent call at the median,
  on a call that then runs for seconds to minutes. It stays in Python.
- The bare interpreter is about 41 ms of that, measured alone with the
  module on a deny. `-I -S` saved about 5 ms of it; the shim keeps them
  for the other reason they exist: no `PYTHONPATH` or user site can put
  a module of its own under a permission gate.
- The policy scripts run once per CI job and suite; 30 to 60 ms there is
  nothing.
- No guard needs to stay in bash for speed.
