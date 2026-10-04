// What a GZCoord command shim runs: the tool in Python (agent-fabric
// ADR-040 §7, Wave 7; tools/fabric/gzcoord/, each tool's contract in its
// module's header), under the pinned interpreter, as this process.
//
// The shim stays alive while the tool runs, rather than handing over:
// node has no exec, and the session-start hook and the harness find the
// watch by `inbox.mjs --follow` in the process table. So it forwards the
// signals it can (TERM, INT, HUP), leaves stdin, stdout and stderr to the
// child, and ends as the child ends — with its status, or by its signal.
// What it cannot forward, a SIGKILL, the child answers itself: it asks the
// kernel to end it when this process ends (run.py, PR_SET_PDEATHSIG), so
// a killed watch never leaves a second one running unseen.
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

// The real path: the commands are links in ~/.local/bin, and the modules
// are found from where the shim really is, never from the link.
const HERE = path.dirname(fs.realpathSync(fileURLToPath(import.meta.url)));
const RUNNER = path.join(HERE, '..', '..', '..', 'tools', 'fabric', 'gzcoord', 'run.py');

// `lastResort` is the tool's own one line and status when the interpreter
// cannot be started at all — the inbox's contract is exit 0 at a session
// start, send's and gzmsg's exit 1 — never a stack trace.
export function runPython(tool, lastResort) {
  const py = process.env.AGENT_FABRIC_PYTHON || '/usr/local/bin/fabric-python';
  const child = spawn(py, ['-I', RUNNER, tool, ...process.argv.slice(2)],
                      { stdio: 'inherit', env: { ...process.env, GZCOORD_SHIM_PID: String(process.pid) } });
  for (const sig of ['SIGTERM', 'SIGINT', 'SIGHUP']) process.on(sig, () => { try { child.kill(sig); } catch { /* gone */ } });
  child.on('error', e => { const [line, code] = lastResort(e); console.error(line); process.exit(code); });
  child.on('exit', (code, signal) => {
    if (signal) { process.removeAllListeners(signal); process.kill(process.pid, signal); return; }
    process.exit(code ?? 1);
  });
}
