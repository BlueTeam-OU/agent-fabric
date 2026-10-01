# 2026-10-01 — a module beside the guards shadows the standard library

The re-review of #75 reasoned, without running it, that a contributor
could plant a Python module under `tools/fabric/` named after a
standard-library module the authority guard imports, and have it run
inside the guard in CI. This records the run, on develop-qzapp as user,
`/usr/bin/python3` 3.14.7, in a scratch clone of the branch.

## What was run

`tools/fabric/subprocess.py` was written into the clone, printing a
marker and exiting 0. Then the guard was run twice against the clone:

- the branch's own copy, as `tests/run.sh` and the shim run it:
  `/usr/bin/python3 tools/fabric/guards/agent_fabric_dir_authority.py`.
  It printed the marker and exited 0. The guard inserts `tools/fabric/`
  at the front of `sys.path` to import `git.py`, and `git.py` imports
  `subprocess`, which was not yet loaded, so the planted file won.
- main's copy, extracted with `git archive origin/main tools/fabric
  policies` and run with `-I`. It judged the clone and printed its usual
  verdict; the marker never appeared.

## What it decides

- CI's authority verdict comes from main's copy of the guards, run
  isolated, as a step before any suite runs the branch's code
  (`.github/workflows/ci.yml`, the bash legs).
- Excluding paths from a contributor's entry cannot close this class:
  Python resolves an import by name, not by path. The guards' own run
  inside `tests/run.sh` stays as the local check and the suite's case;
  it is not the verdict a contributor's branch is judged by.
