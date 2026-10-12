# skill-creator — vendored, unchanged

Anthropic's `skill-creator` skill, the whole folder as upstream ships it.

- Upstream: https://github.com/anthropics/skills
- Path: `skills/skill-creator`
- Commit: `dbd4588f9e1033efb41dad4bef2f7947c8993d44`
- Licence: Apache-2.0 (`LICENSE.txt` in this folder is upstream's); the
  copyright is Anthropic's, recorded in `REUSE.toml`.

Nothing here but this README is the fabric's. Do not edit the upstream
files; a newer upstream is a new copy at a new commit, with this README and
`REUSE.toml` updated to name it.

Things to know before using it:

- **Its eval scripts start headless `claude -p` runs** (`scripts/run_eval.py`,
  `run_loop.py`, `improve_description.py`). Each run costs usage and loads the
  host. Run evals deliberately, a few at a time, never as a sweep.
- **`scripts/quick_validate.py` needs `pyyaml`**, which is not in the
  standard library. That is why this is vendored upstream code and not
  fabric code: ADR-040 (standard library only) governs the fabric's own
  Python, not a third party's.
- Bootstrap's `TREE_SKILLS` (`tools/fabric/bootstrap.py`) installs the whole
  tree into `~/.claude/skills/skill-creator/`, for the `fabric-coordinator`
  and `architect-cto` roles only; for any other role it is not installed and
  an earlier copy is removed (a file the fabric did not write keeps it).
