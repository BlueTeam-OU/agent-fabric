// The `secrets-selftest` action: a signed action, never public; agentd runs
// `bin/fabric-secrets selftest --json` as the account and relays its verdict
// and steps, nothing else; one at a time; fabric-ctl waits long enough and
// prints steps, never a value. Against a fake fabric-secrets in a scratch
// root, through agentd's own answer(); tests/test_secret_selftest.py holds
// the tool's behaviour against a real store.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { scratch } from '../../../tests/scratch.mjs';
import { secretsSelftest, secretsSelftestOnce, SELFTEST_BUDGET_S, SELFTEST_TIMEOUT_MS } from '../selftest.mjs';
import { answer } from '../agentd.mjs';
import { OPS, PUBLIC_OPS } from '../ops.mjs';
import { ACTION_OPS, ACTION_TTL_MAX_S } from '../sign.mjs';
import { table, rows, ACTION_OK, parseArgs, buildRequest } from '../ctl.mjs';

const STEPS = ['precondition', 'set', 'run', 'rm', 'absent'];

// A root whose bin/fabric-secrets prints REPORT and exits CODE, recording
// its argv: the daemon's whole contact with the tool.
function fakeRoot(report, code = 0, stderr = '') {
  const root = scratch('selftest-root-');
  fs.mkdirSync(path.join(root, 'bin'));
  const bin = path.join(root, 'bin', 'fabric-secrets');
  fs.writeFileSync(bin, `#!/bin/sh\nprintf '%s\\n' "$*" > "${root}/argv"\ncat <<'EOF'\n${typeof report === 'string' ? report : JSON.stringify(report)}\nEOF\n${stderr ? `echo '${stderr}' >&2\n` : ''}exit ${code}\n`);
  fs.chmodSync(bin, 0o755);
  return root;
}
const passing = { status: 'pass', name: 'AF_SELFTEST_CANARY', steps: STEPS.map(step => ({ step, ok: true, reason: '' })) };

test('secrets-selftest is a signed action, never public, and pass is its one success', () => {
  assert.ok(OPS.includes('secrets-selftest') && ACTION_OPS.includes('secrets-selftest'));
  assert.ok(!PUBLIC_OPS.includes('secrets-selftest'));
  assert.deepEqual(ACTION_OK['secrets-selftest'], ['pass']);
});

test('agentd runs fabric-secrets selftest --json and relays the verdict and the steps', async () => {
  const root = fakeRoot(passing);
  const r = await answer({ id: 'q1', op: 'secrets-selftest', from: 'h/user' }, { me: { address: 'h/a' }, started: new Date().toISOString(), home: root, root });
  assert.deepEqual(r.data['secrets-selftest'], { status: 'pass', name: 'AF_SELFTEST_CANARY', steps: passing.steps });
  assert.equal(fs.readFileSync(path.join(root, 'argv'), 'utf8').trim(), 'selftest --json');
});

test('a failing step is fail; a report that says pass with a failed step is not a pass', async () => {
  const failing = { ...passing, status: 'fail', steps: passing.steps.map(s => s.step === 'run' ? { ...s, ok: false, reason: 'the command\'s environment held another value' } : s) };
  assert.equal((await secretsSelftestOnce({}, { root: fakeRoot(failing, 1) })).status, 'fail');
  assert.equal((await secretsSelftestOnce({}, { root: fakeRoot({ ...failing, status: 'pass' }, 0) })).status, 'fail');
  assert.equal((await secretsSelftestOnce({}, { root: fakeRoot({ ...passing, steps: [] }, 0) })).status, 'fail', 'no steps is no pass');
});

test('no report, or an exit that is neither pass nor fail, is failed with the reason; nothing invented', async () => {
  const r = await secretsSelftestOnce({}, { root: fakeRoot('not json', 1, 'fabric-secrets: the store could not be read') });
  assert.deepEqual(r, { status: 'failed', reason: 'fabric-secrets: the store could not be read' });
  const r2 = await secretsSelftestOnce({}, { root: fakeRoot(passing, 127) });
  assert.equal(r2.status, 'failed');
  const r3 = await secretsSelftestOnce({}, { root: scratch('selftest-empty-') });
  assert.equal(r3.status, 'failed', 'no fabric-secrets at all');
});

test('only step, ok and reason are relayed, each bounded: a field the tool added never reaches the reply', async () => {
  const noisy = { ...passing, extra: 'x', steps: passing.steps.map(s => ({ ...s, value: 'should-not-pass', reason: 'r'.repeat(500) })) };
  const r = await secretsSelftestOnce({}, { root: fakeRoot(noisy) });
  assert.ok(!JSON.stringify(r).includes('should-not-pass') && !('extra' in r));
  assert.ok(r.steps.every(s => Object.keys(s).join() === 'step,ok,reason' && s.reason.length === 200));
});

test('it takes no arguments, and runs nothing when given some', async () => {
  const root = fakeRoot(passing);
  assert.deepEqual(await secretsSelftestOnce({ args: { name: 'X' } }, { root }), { status: 'refused', reason: 'secrets-selftest takes no arguments' });
  assert.ok(!fs.existsSync(path.join(root, 'argv')));
  assert.equal((await secretsSelftestOnce({ args: {} }, { root })).status, 'pass');
});

test('one at a time per daemon: a second while one runs is busy', async () => {
  let release;
  const exec = () => new Promise(r => { release = () => r({ stdout: JSON.stringify(passing) }); });
  const first = secretsSelftest({}, { exec, root: '/nowhere' });
  let ranAgain = false;
  const exec2 = async () => { ranAgain = true; return { stdout: JSON.stringify(passing) }; };
  assert.deepEqual(await secretsSelftest({}, { exec: exec2, root: '/nowhere' }), { status: 'busy', note: 'a secrets-selftest is already running on this account' });
  assert.equal(ranAgain, false, 'the second ran nothing');
  release();
  assert.equal((await first).status, 'pass');
  assert.equal((await secretsSelftest({}, { exec: exec2, root: '/nowhere' })).status, 'pass', 'free again once it ended');
});

test('fabric-ctl waits past the daemon\'s own bound, inside the action ttl cap, and prints steps', () => {
  const a = parseArgs(['all', 'secrets-selftest']);
  assert.equal(a.timeout, SELFTEST_BUDGET_S);
  assert.ok(SELFTEST_BUDGET_S > SELFTEST_TIMEOUT_MS / 1000 && SELFTEST_BUDGET_S <= ACTION_TTL_MAX_S);
  const req = buildRequest(a, { id: 'q', from: 'h/user', to: '*', cfg: { ttl_s: 30 } });
  assert.equal(req.op, 'secrets-selftest'); assert.ok(!('args' in req));
  const expected = [{ login: 'web-dev-01', host: 'h', address: 'h/web-dev-01' }, { login: 'db-admin', host: 'h', address: 'h/db-admin' }];
  const failing = { status: 'fail', name: 'AF_SELFTEST_CANARY', steps: [{ step: 'precondition', ok: false, reason: 'AF_SELFTEST_CANARY is in the store already' }] };
  const t = table('secrets-selftest', rows(expected, [{ from: 'h/web-dev-01', op: 'secrets-selftest', data: { 'secrets-selftest': { ...passing } } },
                                                       { from: 'h/db-admin', op: 'secrets-selftest', data: { 'secrets-selftest': failing } }])).split('\n');
  assert.match(t[1], /^web-dev-01\s+pass\s+precondition ok, set ok, run ok, rm ok, absent ok$/);
  assert.match(t[2], /^db-admin\s+fail\s+precondition FAIL {2}\(AF_SELFTEST_CANARY is in the store already\)$/);
  const none = table('secrets-selftest', rows([expected[0]], [])).split('\n');
  assert.match(none[1], /^web-dev-01\s+no answer$/);
});
