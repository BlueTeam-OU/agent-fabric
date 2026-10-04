#!/usr/bin/env node
// gzmsg — the GZCOORD/1 validator's command: validate, normalize, new-id.
// The tool is tools/fabric/gzcoord/gzmsg.py (agent-fabric ADR-040 §7), its
// contract in that module's header; this path is the shim the commands,
// the docs and the sessions name.
import { runPython } from './python.mjs';
runPython('gzmsg', e => [`gzmsg: ${e?.message ?? e}`, 1]);
