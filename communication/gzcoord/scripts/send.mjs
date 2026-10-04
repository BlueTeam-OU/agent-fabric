#!/usr/bin/env node
// gzcoord-send — send ONE message over the relay. The tool is
// tools/fabric/gzcoord/send.py (agent-fabric ADR-040 §7), its contract in
// that module's header; this path is the shim the commands, the docs and
// the sessions name.
import { runPython } from './python.mjs';
runPython('send', e => [`send: ${e?.message ?? e}`, 1]);
