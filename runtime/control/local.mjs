// runtime/control/local.mjs — each account's per-clone harness settings,
// <working copy>/.claude/settings.local.json, on the control plane
// (ADR-029; ADR-038 rule 9). The work is tools/fabric/local_settings.py,
// run as this login by argv — no field of a request reaches it; this is
// the daemon's door to it, as jobs.mjs is to jobs.py.
//
//   `local`        a read op: per working copy, the env key NAMES, which of
//                  them are synced secrets, permission rules by count,
//                  other top-level keys. Never a value.
//   `local-prune`  an ACTION (sign.mjs ACTION_OPS): removes the env entries
//                  that duplicate a synced secret, nothing else. It takes
//                  no arguments.

import os from 'node:os';
import path from 'node:path';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';

const execFileP = promisify(execFile);
const LOCAL_TIMEOUT_MS = 15000;
const tool = root => path.join(root, 'tools', 'fabric', 'local_settings.py');
const defaultRoot = home => process.env.AGENT_FABRIC_ROOT ?? path.join(home, 'projects', 'agent-fabric');

async function run(sub, { home = os.homedir(), root = defaultRoot(home), exec = execFileP } = {}) {
  const r = await exec('python3', [tool(root), sub, '--home', home], { encoding: 'utf8', timeout: LOCAL_TIMEOUT_MS });
  return JSON.parse(typeof r === 'string' ? r : r.stdout);
}

export function local(opts = {}) { return run('report', opts); }

export async function localPrune(request, opts = {}) {
  const a = request?.args;
  if (a !== undefined && !(a && typeof a === 'object' && !Array.isArray(a) && !Object.keys(a).length)) {
    return { status: 'refused', reason: 'local-prune takes no arguments' };
  }
  try { return await run('prune', opts); }
  catch (e) { return { status: 'failed', reason: String(e?.stderr || e?.message || e).trim().split('\n').pop().slice(0, 200) }; }
}
