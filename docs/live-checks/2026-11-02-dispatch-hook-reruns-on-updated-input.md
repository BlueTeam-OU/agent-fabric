# 2026-11-02: why is a review dispatch with run_in_background denied "model unset"?

**Why.** On 2026-11-01 (#454, j547) two `code-review` dispatches with `model: fable` and `run_in_background: true` were denied by the dispatch guard as `Review dispatch with model "unset"`, though both calls carried `model: fable`. The same dispatch without the flag was allowed. Under a fabric launch the guard allows a review with an `updatedInput` that drops `model`, so the reviewer runs on the model its agent file pins (`tools/fabric/guards/dispatch_guard.py`, `launch_pins`). The question was whether a second guard saw that rewritten call, and which one. Job j549.

**How.** One session of user@develop-qzapp on Claude Code 2.1.286 (the pin), under a fabric launch (`AGENT_FABRIC_LAUNCH_PROVIDER=anthropic`), in the agent-fabric worktree. The managed file `/etc/claude-code/managed-settings.json` runs the guard as `hook_entry.py agent-dispatch-guard` from the snapshot `fabric-afd25d75`. The workspace entries for the Agent tool, in `.claude/settings.json`, stand down when that file names the guard. Two probes ran:
- **Logging hooks.** Agent `PreToolUse` hooks that append their stdin to a scratch file: one in `.claude/settings.local.json`, and two in `.claude/settings.json`, one before and one after the guard's entry. These were reverted afterwards.
- **A watch on file opens.** inotify on two files: the managed snapshot's `dispatch_guard.py`, which is opened once per guard run, and `~/.claude/agents/code-review.md`, which only this login reads and which the guard opens only on its allow path (`launch_pins`). Attaching strace to the harness was refused by auto mode and was not pursued.

Each probe dispatched `code-review`, `model: fable`, description "review probe …", with and without `run_in_background: true`.

**Measured on develop-qzapp, 2026-11-02, 2.1.286:**

| case | `run_in_background` | result |
|---|---|---|
| L1 control | absent | allowed, ran in the background anyway. All three logging hooks ran within 3 ms of each other. Each saw `tool_input` **without** `model`, so the managed tier's `updatedInput` reaches the workspace hooks. |
| L2 | `true` | denied, `model "unset"`. **No** logging hook ran, so the denial came from the managed tier. |
| W1 control | absent | one guard run (`dispatch_guard.py` opened at 01:20:33.038), allow path (`code-review.md` opened at .153 and .262), then the workspace hooks at .291. |
| W2 | `true` | guard run 1 at 01:20:44.060, allow path (`code-review.md` at .213 and .330). Guard run 2 at 01:20:44.401, with no `code-review.md` read: the deny path. No workspace hook ran. |
| W3 repeat of W2 | `true` | the same shape: run 1 at 01:21:23.047, allow path (.212 and .340). Run 2 at 01:21:23.417, deny path. |

Other accounts on the host share the snapshot, so `dispatch_guard.py` opens arrive at random as well. The pairs were attributed by `code-review.md`, which only this login reads, and by timing: run 2 starts right after run 1 ends, and in both W2 and W3 it is the first open after it.

**Finding.** With `run_in_background: true`, 2.1.286 runs the managed Agent `PreToolUse` hook a second time, on the `updatedInput` of the first run. The guard then judged its own answer, a review with `model` removed, as an unset model and denied it. This is the harness's behaviour, not the guard misreading its input.

**What it decides.** The guard must accept its own output. Under a fabric launch, a review call with no `model` key is now allowed: the reviewer runs on the agent file's pin, and the checks that follow still hold that pin to routing, which a test shows by denying a rewritten file on the second run. Outside a fabric launch, an unset model is still denied, because there it means the session model. A second cause, found alongside (blueteam.ee #16, j498), is that project settings rendered before the template's stand-down call the forwarders ungated. It is fixed in the forwarders themselves: each one that has a managed twin stands down when the managed file names its guard.

**Not measured here.**
- Whether a non-review guard that returns `updatedInput` is also run twice. `subagent-clone-guard` rewrites Bash commands, but the second run was seen only on the Agent tool with `run_in_background`.
- Builds after 2.1.286. Read this back when the pin moves (ADR-043).
- A `claude -p --debug hooks` child session. Its account had reached its weekly limit that day.
