---
role: "fabric-coordinator"
class: workflow
topic: "review-dispatch-no-run-in-background"
description: "A code-review dispatch with run_in_background is refused \"model unset\" (claude 2.1.286): the harness re-runs the managed hook on its own updatedInput; FIXED #458, managed 1b90ade8 installed 2026-11-02"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-05"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - a89c1c44260b6918
---

## A code-review dispatch with run_in_background is refused "model unset" (claude 2.1.286): the harness re-runs the managed hook on its own updatedInput; FIXED #458, managed 1b90ade8 installed 2026-11-02

2026-11-01, #454 (j547): two code-review dispatches with `model: fable` and `run_in_background: true` were
denied by the dispatch guard as `model "unset"`, though the transcript shows `model: fable` in both calls. The
managed entry (`/usr/local/bin/fabric-python … hook_entry.py agent-dispatch-guard`), run by hand on the same
input, allows and strips `model` (updatedInput). The workspace entries in .claude/settings.json and
~/projects/.claude/settings.json stand down when the managed file names the guard. The same dispatch WITHOUT
`run_in_background` was allowed, and it still ran asynchronously. Writing-class dispatches with the flag
(no updatedInput) passed. Not yet explained. Likely hypothesis: with the flag, the harness runs the hook a
second time on the already-stripped input.

**Explained for project working copies (2026-11-01, blueteam.ee #16, j498):** two code-review dispatches with
`model: fable` and NO `run_in_background` were refused the same way. blueteam.ee's committed
`.claude/settings.json` (rendered 23c208a from the workspace template at dce67dba) registers the Agent guard
WITHOUT the "stand down when managed-settings names agent-dispatch-guard" clause the template has on
origin/main. So the managed guard allows and strips `model`, and the project's copy then sees it unset. The
same stale render is in InterWeave, agent-fabric-guards, gzapi.brand, gzapi.ge and gzapp: no review can be
dispatched from a session there until each is re-rendered. The `run_in_background` case in agent-fabric
(#454) is still unexplained, because both workspace entries there stand down.

**Owner's ruling, 2026-11-01 (j549):** the fix lands in its OWN agent-fabric PR, under the "CI-blocking fix
that must land now" exception, and the PR body says so. It does NOT go on #456, even though `fabric-jobs switch`
offers #456's branch: #456 stays as the owner left it. The fix: every runtime/claude-code/hooks/*.sh forwarder
that has a managed twin (runtime/claude-code/managed/hook_entry.py GUARDS, which runs the modules directly and
never the forwarders) stands down when /etc/claude-code/managed-settings.json names its guard, as the workspace
template does. Add a suite case that runs a stale-render forwarder with a managed file present. j498 and j499
are blocked on j549 (memory stale-project-settings-double-guard in the blueteam.ee j498 copy).

**Explained 2026-11-02 (j549):** with `run_in_background: true`, 2.1.286 runs the MANAGED Agent PreToolUse hook a
second time on the first run's updatedInput; the guard then denies its own answer (model removed). Measured with
logging hooks (no workspace hook ran; in the control they all saw model already stripped) and inotify on the snapshot's
dispatch_guard.py plus ~/.claude/agents/code-review.md (two guard runs, the first on the allow path). Record:
docs/live-checks/2026-11-02-dispatch-hook-reruns-on-updated-input.md. Fix on branch
develop-qzapp/user/fix/j549-dispatch-guard-accepts-its-own-output: under a fabric launch the guard allows an unset
model on code-review (the reviewer file pin is still checked against routing), and the six forwarders with a managed
twin stand down (owner's ruling). LANDED: #458 merged 1b90ade8, upgraded to 30 accounts, managed snapshot installed by the owner 2026-11-02; a code-review dispatch with run_in_background was allowed live right after (no relaunch: the managed hook reads `current`). The flag is fine now. strace on the harness
pid is refused by auto mode; inotify on the files a guard reads is the route.

**Why:** a refused review blocks every arm, and the refusal text points at the model, not the flag.
**How to apply:** on a host whose `fabric-managed check` is older than 1b90ade8, dispatch code-review with no `run_in_background`; elsewhere it is fine. The cause is a guard-or-harness finding in
my lane (dispatch_guard.py, the managed hooks). Reproduce it with a logging hook before changing the guard.
Related: [[review-dispatch-no-cd]].

*References: review-dispatch-no-cd*

*Anchors: `tools/fabric/guards/dispatch_guard.py::Review dispatch with model`*

*Observed 2026-11-01 (fabric-coordinator)*
