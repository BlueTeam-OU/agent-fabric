# GZCoord in the gzapp repository

The protocol and its runtime live in agent-fabric
(`communication/gzcoord/`); nothing is copied into gzapp. What gzapp
carries is its own integration: the snippet its root `CLAUDE.md`
includes, the hook that drains the inbox at session start, the relay one
of its agents hosts, and this directory's `config.json`, which tells the
inbox which relay, channel and token location apply to a gzapp working
copy.

Do not create a nested Git repository, and do not vendor the subsystem.

1. Add the contents of [`CLAUDE.snippet.md`](CLAUDE.snippet.md) to gzapp's
   root `CLAUDE.md` (or reference it from the project rules if that
   repository already has a modular rules structure).
2. Wire the `SessionStart` hook in gzapp's `.claude/settings.json` at
   `f="$CLAUDE_PROJECT_DIR/../agent-fabric/bin/gzcoord-inbox"; [ -x "$f" ] && "$f"; true`
   — the inbox drain, as the workspace copy runs it
   (`agent-fabric/runtime/claude-code/bootstrap.sh` writes that one with
   the path substituted). A project keeps its own for sessions launched
   inside the working copy, resolved from `$CLAUDE_PROJECT_DIR`: hook
   commands run before the fabric hook has exported `AGENT_FABRIC_ROOT`
   into the session shell, so a hook line never relies on the variable.
   In a session's own shell the same drain is `gzcoord-inbox`.
   The same file wires the **inbox hold** (2026-09-16,
   `agent-fabric/docs/adr/ADR-022-the-session-lifecycle.md`): three hook groups
   running `agent-fabric/runtime/claude-code/hooks/plan-hold.sh` — on
   `PreToolUse` with no matcher, on `UserPromptSubmit` and on
   `SessionEnd` — so a session that plans inside the working copy holds
   its account's inbox until the plan is approved. The shape is the
   workspace template's (`runtime/claude-code/workspace/settings.json`)
   with the `$CLAUDE_PROJECT_DIR/../agent-fabric` prefix:

   ```json
   {"hooks": [{"type": "command", "timeout": 5,
     "command": "f=\"$CLAUDE_PROJECT_DIR/../agent-fabric/runtime/claude-code/hooks/plan-hold.sh\"; [ -f \"$f\" ] && bash \"$f\"; true"}]}
   ```

   A session launched inside a clone takes its hooks from the clone's
   own settings, never from the workspace's, so until this is wired
   the hold reaches only sessions started from `~/projects`. The same
   holds for the **fallback note** (agent-fabric ADR-007):
   one group on `PostModelSwitch` running
   `agent-fabric/runtime/claude-code/hooks/model-fallback-note.sh`, same
   shape, so a session whose model fell back after a safeguard flag is
   told at once that the flagged text travels nowhere.
3. Nothing to configure by hand: the session's identity is its OS login
   and runtime binding (the role `bin/fabric-role` bound from a login
   shell; slugs from agent-fabric's `identities/roles/catalog.json`), the
   relay and channel are this file's neighbour `config.json`, read by
   `gzcoord-inbox` when the working copy
   resolves to gzapp, and the token arrives with `fabric-secrets sync`.
4. Relay hosting: [`BRIDGE-RELAY-SETUP.md`](BRIDGE-RELAY-SETUP.md). The
   relay's runtime — venv, token, database, log — lives in the hosting
   workspace's `projects/.gzcoord/`, outside every repository. Every
   account gets the token as `CLAUDE_BRIDGE_AUTH_TOKEN` in
   `~/.config/agent-fabric/secrets.env`, which gzcoord-inbox and
   gzcoord-send read and no shell sources (agent-fabric ADR-038 rule 9);
   the launcher hands it to the harness alone, for the `claude-bridge`
   entry of `.mcp.json`, and a session's Bash never holds it; from its own store (`fabric-secrets sync`,
   `runtime/provisioning/README.md` "Secrets"); the gitignored
   `.claude/settings.local.json` `env` entry and `infra/local/.env.local`
   remain accepted for a clone provisioned by hand.

The agent's address is `<host>/<login>` (SPEC §3.1): the account the
session runs under, not the working-copy directory. `gzapp-claude2` and
`gzapp-claude3` under the shared account are therefore one
agent to their peers (`user`); the provisioned accounts
(`architect-cto-01`, `backend-dev-02`, …) keep the addresses they already
had.
