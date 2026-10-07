// runtime/control/selftest.mjs — the `secrets-selftest` ACTION (sign.mjs
// ACTION_OPS): proves, on each account, that an agent can add, use and
// delete a secret of its own. The work is tools/fabric/secret_selftest.py,
// run as this login through `fabric-secrets selftest --json` — no field of
// a request reaches it; this is the daemon's door to it, as local.mjs is
// to local_settings.py.
//
// An action, signed, because it writes: two signed commits to the login's
// store (set, then rm, of AF_SELFTEST_CANARY), pushed to its remote. It
// takes no arguments. The reply is the tool's verdict and its steps —
// {status: pass|fail, name, steps: [{step, ok, reason}]} — never the
// canary or its digest, which never leave the tool. `failed` is a test
// that could not be run or answered no report; `busy`, one already
// running on this account.

import os from 'node:os';
import path from 'node:path';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';

const execFileP = promisify(execFile);
// Above the tool's own worst case (seven commands, each bounded at 60 s):
// a test killed half-way may leave its canary, which the next one then
// refuses to overwrite and names.
export const SELFTEST_TIMEOUT_MS = 450000;
// How long fabric-ctl waits for the replies: the run, and the relay's way back.
export const SELFTEST_BUDGET_S = SELFTEST_TIMEOUT_MS / 1000 + 30;
const defaultRoot = home => process.env.AGENT_FABRIC_ROOT ?? path.join(home, 'projects', 'agent-fabric');
const lastLine = s => String(s ?? '').trim().split('\n').pop().slice(0, 200);
// What the tool reports is relayed only as strings and booleans of bounded
// size: a field of another type is no field, so no report can make the
// reply fail to build (and agentd post nothing) or grow without bound.
const str = (v, max) => typeof v === 'string' ? v.slice(0, max) : '';
const MAX_STEPS = 16;

let running = null;   // one self-test at a time per daemon: both would write the same name
export function secretsSelftest(request, opts = {}) {
  if (running) return Promise.resolve({ status: 'busy', note: 'a secrets-selftest is already running on this account' });
  running = secretsSelftestOnce(request, opts).finally(() => { running = null; });
  return running;
}

export async function secretsSelftestOnce(request, { home = os.homedir(), root = defaultRoot(home), exec = execFileP } = {}) {
  const a = request?.args;
  if (a !== undefined && !(a && typeof a === 'object' && !Array.isArray(a) && !Object.keys(a).length)) {
    return { status: 'refused', reason: 'secrets-selftest takes no arguments' };
  }
  let code = 0, out = '', err = '';
  try {
    const r = await exec(path.join(root, 'bin', 'fabric-secrets'), ['selftest', '--json'], { encoding: 'utf8', timeout: SELFTEST_TIMEOUT_MS });
    out = typeof r === 'string' ? r : r.stdout;
  } catch (e) {
    if (typeof e?.code !== 'number') {
      return { status: 'failed', reason: e?.killed ? `fabric-secrets selftest: timed out after ${SELFTEST_TIMEOUT_MS / 1000} s` : `fabric-secrets selftest: ${lastLine(e?.message ?? e)}` };
    }
    code = e.code; out = e.stdout ?? ''; err = e.stderr ?? '';
  }
  let report = null;
  try { report = JSON.parse(out); } catch { /* said below */ }
  // 0 is pass, 1 fail; anything else, or no report, is a test not run.
  if (![0, 1].includes(code) || !report || !Array.isArray(report.steps)) {
    return { status: 'failed', reason: lastLine(err) || `fabric-secrets selftest exited ${code} with no report` };
  }
  if (report.steps.length > MAX_STEPS) return { status: 'failed', reason: `fabric-secrets selftest reported ${report.steps.length} steps, more than ${MAX_STEPS}` };
  const steps = report.steps.map(s => ({ step: str(s?.step, 40) || '?', ok: s?.ok === true, reason: str(s?.reason, 200) }));
  const pass = code === 0 && report.status === 'pass' && steps.length > 0 && steps.every(s => s.ok);
  return { status: pass ? 'pass' : 'fail', name: str(report.name, 64), steps };
}
