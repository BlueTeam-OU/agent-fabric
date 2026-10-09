// `tools-install <tool>`: a signed action that makes an account install the
// tool its registry pin names. The control agent runs the account's own
// bin/fabric-tools --install and carries the verdict back; every rule about
// who gets what is tools/fabric/tools_install.py's (tests/test_tools_install.py).
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { scratch } from '../../../tests/scratch.mjs';
import { parseInstall, toolsInstall, TOOL_NAME, INSTALL_TIMEOUT_MS, TOOLS_INSTALL_BUDGET_S } from '../tools.mjs';
import { OPS, PUBLIC_OPS } from '../ops.mjs';
import { ACTION_OPS, ACTION_TTL_MAX_S } from '../sign.mjs';
import { answer } from '../agentd.mjs';
import { table, rows, parseArgs, buildRequest, ACTION_OK } from '../ctl.mjs';

// A root whose bin/fabric-tools prints `out` and exits `code`, and leaves
// what it was given (argv, HOME) beside it, so a test reads the call.
function fakeRoot(code, out) {
  const root = scratch('tools-install-root-');
  fs.mkdirSync(path.join(root, 'bin'));
  fs.writeFileSync(path.join(root, 'bin', 'fabric-tools'),
    `#!/usr/bin/env bash\nprintf '%s\\n' "$HOME $*" > "${root}/called"\ncat <<'EOF2'\n${out}\nEOF2\nexit ${code}\n`, { mode: 0o755 });
  return root;
}
const verdict = (status, extra = {}) => JSON.stringify({ status, tool: 'doppler', ...extra });
const REQ = { op: 'tools-install', args: { tool: 'doppler' } };

test('tools-install is an operator action: signed, not public, bounded by the action ttl', () => {
  assert.ok(OPS.includes('tools-install') && ACTION_OPS.includes('tools-install') && !PUBLIC_OPS.includes('tools-install'));
  assert.deepEqual(ACTION_OK['tools-install'], ['installed', 'current', 'skipped']);
  assert.ok(TOOLS_INSTALL_BUDGET_S > INSTALL_TIMEOUT_MS / 1000 && TOOLS_INSTALL_BUDGET_S <= ACTION_TTL_MAX_S);
});

test('fabric-ctl: the word after tools-install is the tool, and the request carries it as its only argument', () => {
  const a = parseArgs(['all', 'tools-install', 'doppler']);
  assert.deepEqual([a.op, a.tool, a.targets, a.timeout], ['tools-install', 'doppler', ['all'], TOOLS_INSTALL_BUDGET_S]);
  const b = parseArgs(['web-dev-01', 'tools-install', 'doppler']);
  assert.deepEqual([b.op, b.tool, b.targets], ['tools-install', 'doppler', ['web-dev-01']]);
  const req = buildRequest(a, { id: 'q', from: 'h/user', to: '*', cfg: { ttl_s: 30 } });
  assert.deepEqual(req.args, { tool: 'doppler' });
  assert.ok(req.ttl_s <= ACTION_TTL_MAX_S);
  for (const bad of [['all', 'tools-install'], ['all', 'tools-install', 'Doppler'], ['all', 'tools-install', '../x'], ['all', 'tools-install', '-x']]) {
    assert.throws(() => parseArgs(bad), /tools-install takes a tool name|unknown option/, bad.join(' '));
  }
  assert.ok(!('args' in buildRequest(parseArgs(['all', 'tools']), { id: 'q', from: 'h/user', to: '*', cfg: { ttl_s: 30 } })), 'no other op carries it');
});

test('toolsInstall: a request that is not one tool name never runs anything', async () => {
  let ran = false;
  const exec = async () => { ran = true; return '{}'; };
  for (const args of [undefined, null, [], {}, { tool: 5 }, { tool: '../x' }, { tool: 'Doppler' }, { tool: '' }, { tool: 'doppler', extra: 1 }, { other: 'doppler' }, 'doppler']) {
    const r = await toolsInstall({ args }, { exec });
    assert.equal(r.status, 'refused', JSON.stringify(args));
  }
  assert.equal(ran, false);
  assert.ok(TOOL_NAME.test('doppler') && TOOL_NAME.test('podman-compose') && !TOOL_NAME.test('a b'));
});

test('toolsInstall runs the account\'s own bin/fabric-tools by argv, as that account\'s HOME', async () => {
  const root = fakeRoot(0, verdict('installed', { version: '3.69.0', path: '/h/.local/bin/doppler' }));
  const home = scratch('tools-install-home-');
  const r = await toolsInstall(REQ, { root, home });
  assert.deepEqual(r, { status: 'installed', tool: 'doppler', version: '3.69.0', path: '/h/.local/bin/doppler', reason: undefined });
  assert.equal(fs.readFileSync(path.join(root, 'called'), 'utf8').trim(), `${home} --install doppler --json`);
});

test('every verdict maps to its exit status; the other statuses are an answer too', async () => {
  for (const [status, code] of [['current', 0], ['skipped', 0], ['failed', 1], ['refused', 2]]) {
    const r = await toolsInstall(REQ, { root: fakeRoot(code, verdict(status, { reason: `why ${status}` })), home: scratch('h-') });
    assert.equal(r.status, status);
    assert.equal(r.reason, `why ${status}`);
  }
});

test('a verdict that disagrees with the exit status, or is no verdict, is failed, never installed', async () => {
  const lie = await toolsInstall(REQ, { root: fakeRoot(1, verdict('installed')), home: scratch('h-') });
  assert.equal(lie.status, 'failed'); assert.match(lie.reason, /does not agree/);
  const unknown = await toolsInstall(REQ, { root: fakeRoot(0, verdict('rooted')), home: scratch('h-') });
  assert.equal(unknown.status, 'failed');
  const none = await toolsInstall(REQ, { root: fakeRoot(127, 'the pinned Python is not installed'), home: scratch('h-') });
  assert.equal(none.status, 'failed'); assert.match(none.reason, /exited 127 and printed no verdict/);
  const nothing = await toolsInstall(REQ, { root: scratch('no-bin-'), home: scratch('h-') });
  assert.equal(nothing.status, 'failed'); assert.match(nothing.reason, /could not run/);
  assert.equal(parseInstall(0, verdict('installed')).status, 'installed');   // the control for the three above
});

test('a run that outlives its bound is failed with the bound said', async () => {
  const root = scratch('tools-install-slow-');
  fs.mkdirSync(path.join(root, 'bin'));
  fs.writeFileSync(path.join(root, 'bin', 'fabric-tools'), '#!/usr/bin/env bash\nsleep 30\n', { mode: 0o755 });
  const r = await toolsInstall(REQ, { root, home: scratch('h-'), timeoutMs: 200 });
  assert.equal(r.status, 'failed'); assert.match(r.reason, /did not finish within 0\.2 s/);
});

test('what the account says is cut, and never reaches the operator\'s terminal as a control character', async () => {
  const long = 'x'.repeat(5000);
  const r = parseInstall(1, verdict('failed', { reason: long }));
  assert.equal(r.reason.length, 300);
  const text = table('tools-install', rows([{ login: 'a', host: 'h', address: 'h/a' }],
    [{ from: 'h/a', op: 'tools-install', data: { 'tools-install': { status: 'failed', tool: 'doppler', reason: 'bad \u001b[31mred' } } }]));
  assert.ok(!text.includes('\u001b'));
  assert.match(text, /failed +doppler.*\\x1b/);
});

test('the daemon answers the tools-install op from its own root and home', async () => {
  const root = fakeRoot(0, verdict('current', { version: '3.69.0' }));
  const home = scratch('tools-install-ctx-');
  const reply = await answer({ id: 'q1', op: 'tools-install', args: { tool: 'doppler' } },
    { me: { address: 'h/a' }, home, root, started: new Date().toISOString() });
  assert.equal(reply.data['tools-install'].status, 'current');
  assert.equal(fs.readFileSync(path.join(root, 'called'), 'utf8').trim(), `${home} --install doppler --json`);
});

test('fabric-ctl: the table is one row per account, and a refusing or silent account is its own row', () => {
  const expected = [{ login: 'gzapp-1', host: 'h', address: 'h/gzapp-1' }, { login: 'other-1', host: 'h', address: 'h/other-1' }, { login: 'dead-1', host: 'h', address: 'h/dead-1' }];
  const t = table('tools-install', rows(expected, [
    { from: 'h/gzapp-1', op: 'tools-install', data: { 'tools-install': { status: 'installed', tool: 'doppler', version: '3.69.0' } } },
    { from: 'h/other-1', op: 'tools-install', data: { 'tools-install': { status: 'skipped', tool: 'doppler', reason: 'no working copy of gzapp on this account' } } }])).split('\n');
  assert.match(t[0], /^gzapp-1\s+installed\s+doppler 3\.69\.0$/);
  assert.match(t[1], /^other-1\s+skipped\s+doppler\s+no working copy of gzapp on this account$/);
  assert.match(t[2], /^dead-1\s+no answer$/);
});
