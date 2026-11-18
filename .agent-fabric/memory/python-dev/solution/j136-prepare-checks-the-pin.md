---
role: "python-dev"
class: solution
topic: "j136-prepare-checks-the-pin"
description: "j136/j762 — #555 merged; worker.pin_problem, langid for/user branch, review traps (base ancestor, P3 defer, 127 from shim)"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 2c57549bdd48423e
---

## j136/j762 — #555 merged; worker.pin_problem, langid for/user branch, review traps (base ancestor, P3 defer, 127 from shim)

#555 merged (head 833de8dc): `worker.prepare` asks `python_pin.check` on `<root>/runtime/python.json`, no host python3 probe; Python `FABRIC_HOST_PYTHON_MIN`/`host_python_ok` removed, detect.sh keeps its own because ci.yml:199 sources it. Item 2 (langid venv made by `sys.executable`, seam `AGENT_FABRIC_LANGID_PYTHON`) is branch `develop-qzapp/python-dev-02/for/user/langid-venv-on-the-pin` 4c9cde1d, for the user session to fold.

**Why:** owner's ruling 2026-11-11, one Python on every host: the pin. The venv was really made in `tools/fabric/langid_install.py`, not bootstrap.py.

**How to apply:**
- A branch behind main makes `fabric-pr post-review` refuse ("base not an ancestor of head"): merge origin/main first (check conflict paths against my entry), re-run the suite, then brief on the new head.
- A commit in a second worktree is refused by the job guard; build a `for/` branch by `git switch -c` in the job worktree from a saved patch, then switch back.
- `$HOME` in a push/merge command makes the guard refuse; keep those commands free of it, run the suite separately.
- Boundary paths (runtime/provisioning/platform) arm below minimum only on the owner's word; open P3s need `--defer "<head8>:F<n>" "<why>"` each.
- Absent fabric-python exits 127 from new-agent-worker.sh:21 before prepare runs; the exit-1 pin message covers a wrong build or unreadable pin.
- Open P3s carried: KeyError on a malformed wheel entry in pin_problem, CONTRACT note for AGENT_FABRIC_PYTHON_LINK/PREFIX, ADR-040 amendment (070eb413 on user's branch) not yet on main.

*Anchors: `tools/fabric/provisioning/worker.py::pin_problem`, `tools/fabric/langid_install.py::AGENT_FABRIC_LANGID_PYTHON`*

*Observed 2026-11-11 (python-dev)*
