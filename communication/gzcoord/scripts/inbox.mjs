#!/usr/bin/env node
// gzcoord-inbox — what the relay holds for this session: the drain, the
// watch (--follow), --wait, --replay, --history, --held. The tool is
// tools/fabric/gzcoord/inbox.py (agent-fabric ADR-040 §7), its contract in
// that module's header; this path is the shim the hooks, the commands, the
// docs and the sessions name. Never blocks a session start: exit 0.
import { runPython } from './python.mjs';
runPython('inbox', e => [`gzcoord inbox: ${e?.message ?? e}`, 0]);
