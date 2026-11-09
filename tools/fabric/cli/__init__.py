"""tools/fabric/cli/ — the `fabric <noun> <verb>` command (agent-fabric ADR-068).

table.py     the `fabric` section of runtime/claude-code/commands.json and how a word line resolves through it
canonical.py a Bash segment's words to (command, args), the one reading every hook and guard shares (rule 7)
checks.py    lint's two checks: the table against `commands`, and the mechanism's checker
fabric.py    the command bin/fabric forwards to

Standard library only, and no import outside this package: a hook loads the package by path (as job-copy-guard.py loads
jobsparts), so nothing on sys.path answers for its imports."""
