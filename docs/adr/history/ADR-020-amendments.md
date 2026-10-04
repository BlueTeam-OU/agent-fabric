# ADR-020 — amendments

The full notes; the ADR's body reads current and its Amendments table lists them.

### Amendment 2026-10-05 — The reviewer holds no secret

Rule 4 said the reviewer's Bash fence denies state-changing git and
package installs. On 2026-10-04 a review subagent printed its environment,
which every account's shell fills with its synced secrets, and the
operator's signing key was rotated (#95). #96 taught the fence to refuse
printing the environment and reading secret material by path, and ported
it to Python; its nine blind review rounds then each found a spelling the
patterns did not know, all of one class: bash expanding a path, or an
allowed tool running a program the guard never sees, which no string
match can follow. The environment half of that class now has a structural
answer. A live check showed that a `PreToolUse` hook in the code-review
agent's frontmatter can rewrite the command through `updatedInput` with no
permission decision, so the fence rewrites every command it lets through
to run under `env -i`, keeping only the variables a build or a test needs
(`CLEAN_ENV`); the names are fixed in the module and the values are
expanded by the reviewer's own shell, so none passes through the hook.
The patterns stay as the first line; secret material on disk still rests
on them, and on keeping secrets out of what a session can read.
