---
role: "python-dev"
class: workflow
topic: "off-shell-3-merged-151"
description: "#151 (merged 2026-10-09) ported hostexec/worker/fabric-host/enter/model-audit and split jobs.py; CI found what the first test run missed; repo moved to BlueTeam-OU"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 11d97914522c6140
---

## #151 (merged 2026-10-09) ported hostexec/worker/fabric-host/enter/model-audit and split jobs.py; CI found what the first test run missed; repo moved to BlueTeam-OU

PR #151 (4 work, 5 fix, 1 merge; 89bfb5b8), job j77, request 01a12117: hostexec/worker/fabric-host -> tools/fabric/{hostexec,hostworker,fabric_host}.py;
moveto `enter` -> `moveto.py --enter` (stub stays `#!/bin/bash -l`; rc stays shell); model-audit.sh -> tools/fabric/model_audit.py (golden files in
tests/fixtures/model-audit taken from the bash first); jobs.py -> facade over tools/fabric/jobsparts/ (loaded by path as fabric_jobs).

- **Run the whole suite before the first push, in CI's environment.** The ports' own tests passed; CI then found, one class at a time over six pushes: fixtures that
  copy files one by one (launch_cli: jobsparts/; new_agent_cli: hostexec.py, hostworker.py), readers of the moved file's TEXT (control_queue, and the Node
  queue.test.mjs reading QUEUE_TIMEOUT_S from jobs.py), tests/test_roots_seam.py (scans every Python module; exemptions with a reason), tests/test_own_instance_tree.py
  (a guard that arrived on main after my rebase: any suite naming AGENT_FABRIC_ROOT calls own_instance_tree() before its first def). Grep tests AND runtime/**/tests
  for the moved file's name and for per-file copies before pushing; merge main (not rebase) to pick up new guards.
- **A runner started in the background (nohup/&) has SIGINT/QUIT/HUP ignored and every child inherits it:** tests that send Ctrl-C start the child with
  preexec_fn=signal(SIGINT, SIG_DFL); test_fabric_lease_cli's "INT and QUIT are not ignored" fails for that reason alone. test_lease fails in a scratch copy
  without history (a shallow copy), not a defect.
- **Ctrl-C in a ported bash script:** bash carried on when a foreground child took the SIGINT. Port with a Python handler (not SIG_IGN, which children inherit):
  `signal.signal(SIGINT, lambda *_: None)` after the --wait read; KeyboardInterrupt at the prompt -> 130. A Python handler is reset by exec; SIG_IGN is not.
- **Mutation parity at scale:** 31 mutants x ~2.5 min on a loaded host (load 30+) is ~2 h per side even in 4 parallel copies; the harness timed out under load.
  Choose fewer mutants or the fastest test file; the five survivors on the base were gaps in test_jobs.py (claim title/project, drop reason, log note, queue timeout text).
- **The repo moved gzapi-org -> BlueTeam-OU:** a stale `origin` makes `fabric-pr post-review` fail with HTTP 307; repointing origin or GH_REPO was denied to me by the
  classifier; the owner fixed origin and a plain retry worked. Do not work around a denial; stop and say what is needed.
- Read the gate's counts ("#N (W work, F fix)") before saying anything about a PR; a merged PR has none (the gate skips it).
Related: [[stripped-fixes-merged-in-138]], [[splitting-a-closure-heavy-main]], [[facade-split-monkeypatch-trap]].

*References: facade-split-monkeypatch-trap, splitting-a-closure-heavy-main, stripped-fixes-merged-in-138*

*Observed 2026-10-09 (python-dev)*
