---
role: "python-dev"
class: workflow
topic: "shell-mirror-of-future-resolution-tests-the-file-not-the-dir"
description: "j115 #575 F1: a shell reader mirroring a Python resolution that does not exist yet must test the file it reads, not the directory that will hold it"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-04"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - e4fd7767c77f0291
---

## j115 #575 F1: a shell reader mirroring a Python resolution that does not exist yet must test the file it reads, not the directory that will hold it

The step-A shell readers of the hosts registry (both completions, `ssh-operator.sh`) took `<home>/projects/blueteam-fabric` on `-d`. Bootstrap clones that repository empty before step B, so every TAB said "no hosts registry" while `roots.hosts_registry()` (which has no clone step yet) answered the engine's. Fix acc8a4ee: `-f <clone>/runtime/hosts/registry.json`. The test needs a clone that exists without the file, with the same clone holding the file as positive control; it fails on all three readers before the fix.

**Why:** a directory test passes the moment an empty repository is cloned, which the plan itself schedules before the data moves. **How to apply:** when shell code mirrors a resolution the Python side does not have yet, key it on the file it will read; give the fixture the empty-directory state.

Also: `tests/run.sh` exits 75 after a 7200s wait for the full-suite lease (another login held it); that is not a suite verdict, rerun. Check `git merge-base --is-ancestor <head> origin/main` before `fabric-jobs deliver`: a pushed head may already have been folded and merged.

*Anchors: `tests/test_hosts_registry_shell.py::test_a_clone_without_the_file_is_skipped_for_the_engine_root`*

*Observed 2026-11-12 (python-dev)*
