// The `secrets-sync` action against a fake fabric-secrets: it applies what
// the login's own store says, reports the sign-in by fingerprint,
// proves it against the fingerprint it was sent, and — asked to — resumes
// a running session on it through the launcher's restart marker.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { scratch } from '../../../tests/scratch.mjs';
import { secretsSync, sessionEnv } from '../secrets.mjs';
import { markerPath, upgrade } from '../upgrade.mjs';
import { table, rows, ACTION_OK } from '../ctl.mjs';

const TPL = 'sk-ant-oat01-TEMPLATE-FIXTURE';
const envWith = (tok, provider = 'anthropic') => () => `PATH=/usr/bin\0${provider ? `AGENT_FABRIC_LAUNCH_PROVIDER=${provider}\0` : ''}${tok ? `CLAUDE_CODE_OAUTH_TOKEN=${tok}\0` : ''}HOME=/x\0`;
const fp = v => crypto.createHash('sha256').update(v).digest('hex').slice(0, 12);
function fixture({ writes = TPL, code = 0, report = {}, before = null } = {}) {
  const home = scratch('secrets-home-'); const root = scratch('secrets-root-');
  fs.mkdirSync(path.join(home, '.config', 'agent-fabric'), { recursive: true });
  if (before) fs.writeFileSync(path.join(home, '.config', 'agent-fabric', 'secrets.env'), `export CLAUDE_CODE_OAUTH_TOKEN='${before}'\n`);
  const calls = [];
  const exec = async (bin, args) => {
    calls.push([path.relative(root, bin), ...args]);
    fs.writeFileSync(path.join(home, '.config', 'agent-fabric', 'secrets.env'), writes ? `export CLAUDE_CODE_OAUTH_TOKEN='${writes}'\n` : 'export GH_TOKEN=x\n');
    if (code) { const e = new Error(`Command failed: fabric-secrets sync --json`); e.code = code; e.stdout = JSON.stringify(report); throw e; }
    return { stdout: JSON.stringify(report) };
  };
  return { home, root, calls, exec, dir: path.join(home, 'state') };
}

test('a template in the login\'s config: synced, named by fingerprint, the value nowhere', async () => {
  const f = fixture();
  const r = await secretsSync({ id: 'x' }, { home: f.home, root: f.root, exec: f.exec, sessions: [] });
  assert.deepEqual(f.calls, [['bin/fabric-secrets', 'sync', '--json']], 'the login\'s own fabric-secrets, nothing else');
  assert.deepEqual(r, { status: 'synced', claude_sign_in: { via: 'setup-token', token_sha256_12: crypto.createHash('sha256').update(TPL).digest('hex').slice(0, 12) }, session: 'none' });
  assert.ok(!JSON.stringify(r).includes(TPL));
});

test('no template: its own sign-in; names missing in the store are applied around and said; a running session is told to relaunch', async () => {
  const f = fixture({ writes: null, code: 2, report: { missing: ['SSH_PRIVATE_KEY'] } });
  const r = await secretsSync({ id: 'x' }, { home: f.home, root: f.root, exec: f.exec, sessions: [4242], envOf: envWith(null) });
  assert.deepEqual(r, { status: 'synced', claude_sign_in: { via: 'none: its next session is refused' }, missing: ['SSH_PRIVATE_KEY'], session: 'running: relaunch to use it' });
});

test('a sync that applied nothing is a failure with its reason; arguments are refused before anything runs', async () => {
  const f = fixture({ code: 3, report: { error: 'config agents_x names AGENT_LOGIN=y, this login is x; nothing applied' } });
  const r = await secretsSync({ id: 'x' }, { home: f.home, root: f.root, exec: f.exec, sessions: [] });
  assert.deepEqual([r.status, r.reason], ['failed', 'config agents_x names AGENT_LOGIN=y, this login is x; nothing applied']);
  const g = fixture();
  const refused = await secretsSync({ id: 'x', args: { config: 'agents_other' } }, { home: g.home, root: g.root, exec: g.exec, sessions: [] });
  assert.equal(refused.status, 'refused'); assert.equal(g.calls.length, 0, 'nothing ran');
});

test('fabric-ctl secrets-sync: one row per account with the sign-in and the session; only synced is success', () => {
  const expected = [{ login: 'flutter-dev-01', host: 'h', address: 'h/flutter-dev-01' }, { login: 'web-dev-01', host: 'h', address: 'h/web-dev-01' }];
  const t = table('secrets-sync', rows(expected, [{ kind: 'reply', from: 'h/flutter-dev-01', op: 'secrets-sync', data: { 'secrets-sync': { status: 'synced', claude_sign_in: { via: 'setup-token', token_sha256_12: '183a68e97389' }, session: 'running: relaunch to use it' } } }])).split('\n');
  assert.match(t[1], /^flutter-dev-01\s+synced\s+setup-token 183a68e97389\s+running: relaunch to use it$/);
  assert.match(t[2], /^web-dev-01\s+no answer$/);
  assert.deepEqual(ACTION_OK['secrets-sync'], ['synced']);
  const bare = table('secrets-sync', rows([expected[0]], [{ kind: 'reply', from: 'h/flutter-dev-01', op: 'secrets-sync', data: { 'secrets-sync': { claude_sign_in: { via: 'setup-token', token_sha256_12: '183a68e97389' } } } }])).split('\n');
  assert.match(bare[1], /^flutter-dev-01\s+no status\s+setup-token 183a68e97389/, 'never "undefined"');
  const busy = table('secrets-sync', rows([expected[0]], [{ kind: 'reply', from: 'h/flutter-dev-01', op: 'secrets-sync', data: { 'secrets-sync': { status: 'busy', note: 'a secrets-sync is already running on this account' } } }])).split('\n');
  assert.match(busy[1], /^flutter-dev-01\s+busy\s.*a secrets-sync is already running on this account$/, 'a busy row shows its note');
});

test('expect: the synced token must be the template\'s; another one is a failure, and nothing is stopped', async () => {
  const f = fixture();
  assert.equal((await secretsSync({ id: 'x', args: { expect: fp(TPL) } }, { home: f.home, root: f.root, exec: f.exec, sessions: [] })).status, 'synced');
  const g = fixture({ writes: 'sk-ant-oat01-SOMEONE-ELSE' });
  const r = await secretsSync({ id: 'x', args: { expect: fp(TPL), restart: true } }, { home: g.home, root: g.root, exec: g.exec, dir: g.dir, sessions: [7], kill: () => assert.fail('nothing stopped on a mismatch') });
  assert.equal(r.status, 'failed'); assert.match(r.reason, new RegExp(`holds setup-token ${fp('sk-ant-oat01-SOMEONE-ELSE')}, not the expected ${fp(TPL)}; nothing restarted`));
  assert.ok(!fs.existsSync(markerPath(g.dir)));
  for (const args of [{ expect: 'XYZ' }, { restart: 'yes' }, { config: 'agents_other' }, []]) {
    const h = fixture();
    const x = await secretsSync({ id: 'x', args }, { home: h.home, root: h.root, exec: h.exec, sessions: [] });
    assert.equal(x.status, 'refused', JSON.stringify(args)); assert.equal(h.calls.length, 0);
  }
});

test('restart: the marker first, already done, then SIGTERM; the launcher resumes the session on the new sign-in', async () => {
  const OLD = 'sk-ant-oat01-OLD-ACCOUNT';
  const f = fixture({ before: OLD });
  let up = true; const order = [];
  const kill = (pid, sig) => { const m = JSON.parse(fs.readFileSync(markerPath(f.dir))); order.push(`${sig} ${pid} marker=${m.status}`); up = false; };
  const r = await secretsSync({ id: 'req-9', from: 'h/user', args: { expect: fp(TPL), restart: true } }, { home: f.home, root: f.root, exec: f.exec, dir: f.dir, sessions: [55], me: 'h/web-dev-01', envOf: envWith(OLD), kill, alive: () => up, sleep: async () => {}, now: () => new Date('2026-09-25T12:00:00Z') });
  assert.deepEqual([r.status, r.session], ['synced', 'restarting']);
  assert.deepEqual(order, ['SIGTERM 55 marker=done'], 'the marker is written, done, before the session is signalled');
  const m = JSON.parse(fs.readFileSync(markerPath(f.dir)));
  assert.deepEqual([m.piece, m.from, m.installed, m.request_id], ['the Claude account', `setup-token ${fp(OLD)}`, `setup-token ${fp(TPL)}`, 'req-9']);
  assert.ok(!JSON.stringify(m).includes('sk-ant-oat01'), 'fingerprints only, in the marker too');
});

test('restart spares the requester\'s own session, a session already on the token, and forces none that will not stop', async () => {
  const own = fixture({ before: 'sk-ant-oat01-OLD-ACCOUNT' });
  const r1 = await secretsSync({ id: 'x', from: 'h/user', args: { restart: true } }, { home: own.home, root: own.root, exec: own.exec, dir: own.dir, sessions: [1], me: 'h/user', envOf: envWith('sk-ant-oat01-OLD-ACCOUNT'), kill: () => assert.fail('own session stopped') });
  assert.equal(r1.session, 'yours: relaunch to use it');
  const same = fixture({ before: TPL });
  const r2 = await secretsSync({ id: 'x', from: 'h/user', args: { restart: true } }, { home: same.home, root: same.root, exec: same.exec, dir: same.dir, sessions: [2], me: 'h/db-admin', envOf: envWith(TPL), kill: () => assert.fail('a session already on it was stopped') });
  assert.equal(r2.session, 'running, already on it');
  const stuck = fixture({ before: 'sk-ant-oat01-OLD-ACCOUNT' });
  const sigs = [];
  const r3 = await secretsSync({ id: 'x', from: 'h/user', args: { restart: true } }, { home: stuck.home, root: stuck.root, exec: stuck.exec, dir: stuck.dir, sessions: [3], me: 'h/db-admin', envOf: envWith('sk-ant-oat01-OLD-ACCOUNT'), kill: (p, s) => sigs.push(s), alive: () => true, sleep: async () => {}, stopWaitMs: 0 });
  assert.equal(r3.status, 'failed', 'a restart asked for and not done is not a success'); assert.match(r3.reason, /synced, but the session .*did not stop .*nothing forced — run it again/);
  assert.deepEqual(sigs, ['SIGTERM']);
  assert.ok(!fs.existsSync(markerPath(stuck.dir)), 'no marker left to resume the session whenever it is ended later');
});

test('the session, not the record, says whether it is on the token: a record synced earlier under an unrestarted session still restarts it', async () => {
  const f = fixture({ before: TPL });   // the record already moved (a --no-restart run, or a session that did not stop)
  let up = true; const sigs = [];
  const r = await secretsSync({ id: 'r2', from: 'h/user', args: { expect: fp(TPL), restart: true } }, { home: f.home, root: f.root, exec: f.exec, dir: f.dir, sessions: [66], me: 'h/db-admin',
    envOf: envWith('sk-ant-oat01-OLD-ACCOUNT'), kill: (p, sg) => { sigs.push(sg); up = false; }, alive: () => up, sleep: async () => {} });
  assert.deepEqual([r.status, r.session, sigs], ['synced', 'restarting', ['SIGTERM']]);
  const g = fixture();
  const r2 = await secretsSync({ id: 'r3', from: 'h/user', args: { restart: true } }, { home: g.home, root: g.root, exec: g.exec, dir: g.dir, sessions: [67], me: 'h/db-admin',
    envOf: () => { throw Object.assign(new Error('EACCES'), { code: 'EACCES' }); }, kill: () => { up = false; }, alive: () => false, sleep: async () => {} });
  assert.equal(r2.session, 'restarting', 'an environment that cannot be read is not "already on it"');
  assert.deepEqual(sessionEnv(1, { envOf: envWith(TPL) }), { token: TPL, provider: 'anthropic' });
  assert.deepEqual(sessionEnv(1, { envOf: envWith(null, 'openrouter') }), { token: null, provider: 'openrouter' });
});

test('restart refuses: no token to move to, a pgrep that failed, an upgrade in flight; a marker another action wrote is never removed', async () => {
  const none = fixture({ writes: null });
  const r1 = await secretsSync({ id: 'x', from: 'h/user', args: { restart: true } }, { home: none.home, root: none.root, exec: none.exec, dir: none.dir, sessions: [5], me: 'h/db-admin', envOf: envWith('sk-ant-oat01-OLD-ACCOUNT'), kill: () => assert.fail('stopped a session that could not come back') });
  assert.deepEqual([r1.status, r1.reason], ['failed', 'the synced record holds no token; nothing stopped']);
  assert.ok(!fs.existsSync(markerPath(none.dir)));
  const pg = fixture();
  const eacces = () => { const e = new Error('spawn pgrep EACCES'); e.code = 'EACCES'; throw e; };
  const r2 = await secretsSync({ id: 'x', from: 'h/user', args: { restart: true } }, { home: pg.home, root: pg.root, exec: pg.exec, dir: pg.dir, me: 'h/db-admin', pgrep: eacces, kill: () => assert.fail('no signal') });
  assert.equal(r2.status, 'failed'); assert.match(r2.reason, /could not tell whether a session is running \(pgrep: spawn pgrep EACCES\); nothing restarted/);
  const quiet = fixture();
  const r2b = await secretsSync({ id: 'x', from: 'h/user' }, { home: quiet.home, root: quiet.root, exec: quiet.exec, dir: quiet.dir, me: 'h/db-admin', pgrep: eacces });
  assert.deepEqual([r2b.status, r2b.session], ['synced', 'unknown'], 'without a restart asked, the sync stands and the unknown is said'); assert.match(r2b.reason, /EACCES/);
  const up = fixture();
  const r3 = await secretsSync({ id: 'x', from: 'h/user', args: { restart: true } }, { home: up.home, root: up.root, exec: up.exec, dir: up.dir, sessions: [8], me: 'h/db-admin', envOf: envWith('sk-ant-oat01-OLD-ACCOUNT'), upgrading: () => true, kill: () => assert.fail('stopped under an upgrade') });
  assert.equal(r3.status, 'failed'); assert.match(r3.reason, /an upgrade is running/);
  const other = fixture();
  fs.mkdirSync(other.dir, { recursive: true });
  const sigs = [];
  const r4 = await secretsSync({ id: 'mine', from: 'h/user', args: { restart: true } }, { home: other.home, root: other.root, exec: other.exec, dir: other.dir, sessions: [9], me: 'h/db-admin', envOf: envWith('sk-ant-oat01-OLD-ACCOUNT'),
    kill: () => { sigs.push(1); fs.writeFileSync(markerPath(other.dir), JSON.stringify({ request_id: 'an-upgrade', status: 'pending' })); }, alive: () => true, sleep: async () => {}, stopWaitMs: 0 });
  assert.equal(r4.status, 'failed');
  assert.equal(JSON.parse(fs.readFileSync(markerPath(other.dir))).request_id, 'an-upgrade', 'the upgrade\'s marker survives');
});

test('a broker session has no Claude account to move: never restarted, however often the sync is asked', async () => {
  const f = fixture();
  for (let run = 0; run < 2; run++) {
    const r = await secretsSync({ id: `b${run}`, from: 'h/user', args: { expect: fp(TPL), restart: true } }, { home: f.home, root: f.root, exec: f.exec, dir: f.dir, sessions: [70], me: 'h/db-admin',
      envOf: envWith(null, 'openrouter'), kill: () => assert.fail('a broker session was stopped') });
    assert.deepEqual([r.status, r.session], ['synced', 'running (broker): no Claude account to move']);
  }
  assert.ok(!fs.existsSync(markerPath(f.dir)));
  const g = fixture();
  let up = true; const sigs = [];
  const r = await secretsSync({ id: 'mix', from: 'h/user', args: { restart: true } }, { home: g.home, root: g.root, exec: g.exec, dir: g.dir, sessions: [71, 72], me: 'h/db-admin',
    envOf: pid => (pid === 71 ? envWith(null, 'openrouter') : envWith('sk-ant-oat01-OLD-ACCOUNT'))(), kill: (pid) => { sigs.push(pid); up = false; }, alive: () => up, sleep: async () => {} });
  assert.deepEqual([r.session, sigs], ['restarting', [72]], 'only the plain-claude session on another account is stopped');
  assert.deepEqual(JSON.parse(fs.readFileSync(markerPath(g.dir))).pids, [72]);
});

test('an upgrade asked for while a secrets-sync restarts the session is busy, and says why', async () => {
  const f = fixture();
  let release, up = true; const gate = new Promise(r => { release = () => { up = false; r(); }; });
  const sync = secretsSync({ id: 's', from: 'h/user', args: { restart: true } }, { home: f.home, root: f.root, exec: f.exec, dir: f.dir, sessions: [80], me: 'h/db-admin',
    envOf: envWith('sk-ant-oat01-OLD-ACCOUNT'), kill: () => {}, alive: () => up, sleep: () => gate, stopWaitMs: 60000 });
  await new Promise(r => setImmediate(r));
  const u = await upgrade({ id: 'u', from: 'h/user', op: 'upgrade', args: { piece: 'claude' } }, {});
  assert.deepEqual([u.status, u.note], ['busy', 'a secrets-sync is restarting the session on this account']);
  release(); assert.equal((await sync).session, 'restarting');
  assert.equal((await upgrade({ id: 'u2', from: 'h/user', op: 'upgrade', args: { piece: 'claude', version: 'x' } }, {})).status, 'refused', 'the interlock is released afterwards');
});
