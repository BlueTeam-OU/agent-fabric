// bin/fabric-accounts: the setup and the local look at the observed Claude
// accounts. No token ever reaches the output; login needs a terminal and a
// valid account name, and runs the harness in that account's own config
// directory with no inherited token.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { scratch } from '../../../tests/scratch.mjs';
import { main, describe, listLines, storeTemplates, storeAssign } from '../accounts.mjs';
import crypto from 'node:crypto';
import { accountsDir } from '../ops.mjs';

const ACCESS = 'sk-ant-oat01-ACCESS-VALUE', REFRESH = 'sk-ant-ort01-REFRESH-VALUE';
function capture(fn) {
  const out = [], err = [];
  const [log, error] = [console.log, console.error];
  console.log = (...a) => out.push(a.join(' ')); console.error = (...a) => err.push(a.join(' '));
  return Promise.resolve(fn()).then(code => ({ code, out: out.join('\n'), err: err.join('\n') })).finally(() => { console.log = log; console.error = error; });
}
function signIn(dir, { expiresAt, refresh = true, email = 'a@example.org' } = {}) {
  fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(path.join(dir, '.credentials.json'), JSON.stringify({ claudeAiOauth: { accessToken: ACCESS, ...(refresh && { refreshToken: REFRESH }), expiresAt } }));
  fs.writeFileSync(path.join(dir, '.claude.json'), JSON.stringify({ oauthAccount: { emailAddress: email } }));
}

test('list: each account in words — signed in until, lapsed, no refresh token, not signed in — and never a token', async () => {
  const h = scratch('accounts-home-'); const env = {};
  const dir = accountsDir(h, env);
  const now = Date.parse('2026-09-24T20:00:00Z');
  signIn(path.join(dir, 'claude-live'), { expiresAt: now + 3600e3 });
  signIn(path.join(dir, 'claude-lapsed'), { expiresAt: now - 60e3, email: 'b@example.org' });
  signIn(path.join(dir, 'claude-norefresh'), { expiresAt: now + 3600e3, refresh: false, email: 'c@example.org' });
  fs.mkdirSync(path.join(dir, 'claude-new'));
  const lines = listLines(dir, now).join('\n');
  assert.match(lines, /claude-lapsed\s+b@example\.org\s+sign-in lapsed at 2026-09-24T19:59:00\.000Z \(the next read renews it\)/);
  assert.match(lines, /claude-live\s+a@example\.org\s+signed in until 2026-09-24T21:00:00\.000Z/);
  assert.match(lines, /claude-new\s+-\s+not signed in/);
  assert.match(lines, /claude-norefresh\s+c@example\.org\s+signed in, NO refresh token/);
  assert.ok(!lines.includes(ACCESS) && !lines.includes(REFRESH), 'a token reached the output');
  assert.deepEqual(Object.keys(describe(path.join(dir, 'claude-live'), now)).sort(), ['email', 'expired', 'expires_at', 'refresh_token', 'signed_in', 'slug']);
  const { code, out } = await capture(() => main(['list'], { home: h, env }));
  assert.equal(code, 0); assert.match(out, /claude-live/);
  assert.match(listLines(accountsDir(scratch('accounts-empty-'), {})).join('\n'), /no Claude account observed .* fabric-accounts login <account>/);
});

test('login: refuses a bad name and a missing terminal; otherwise runs the harness in the account\'s own 0700 directory, no inherited token', async () => {
  const h = scratch('accounts-login-');
  const env = { PATH: '/usr/bin', CLAUDE_CODE_OAUTH_TOKEN: 'sk-ant-oat01-inherited', ANTHROPIC_API_KEY: 'sk-ant-api-x', KEEP: 'yes' };
  let r = await capture(() => main(['login', 'Not/A Name'], { home: h, env, stdinTTY: true, spawn: () => assert.fail('no harness for a bad name') }));
  assert.equal(r.code, 2);
  r = await capture(() => main(['login', 'claude-a'], { home: h, env, stdinTTY: false, spawn: () => assert.fail('no harness without a terminal') }));
  assert.equal(r.code, 2); assert.match(r.err, /real terminal/);
  const target = path.join(accountsDir(h, env), 'claude-a');
  let seen;
  r = await capture(() => main(['login', 'claude-a'], { home: h, env, stdinTTY: true, spawn: (bin, args, opts) => { seen = opts; signIn(target, { expiresAt: Date.now() + 8 * 3600e3 }); return { status: 0 }; } }));
  assert.equal(r.code, 0, r.err);
  assert.equal(seen.env.CLAUDE_CONFIG_DIR, target);
  assert.equal(seen.cwd, target);
  assert.ok(!('CLAUDE_CODE_OAUTH_TOKEN' in seen.env) && !('ANTHROPIC_API_KEY' in seen.env), 'an inherited token reached the login harness');
  assert.equal(seen.env.KEEP, 'yes', 'the rest of the environment is kept (a terminal needs it)');
  assert.equal(fs.statSync(target).mode & 0o777, 0o700);
  assert.match(r.err, /claude-a signed in as a@example\.org/);
  fs.mkdirSync(path.join(accountsDir(h, env), 'claude-held'), { recursive: true });
  fs.writeFileSync(path.join(accountsDir(h, env), 'claude-held', '.fabric-read.lock'), `${process.ppid}\n`);
  r = await capture(() => main(['login', 'claude-held'], { home: h, env, stdinTTY: true, spawn: () => assert.fail('a /login over a running read') }));
  assert.equal(r.code, 1); assert.match(r.err, /being read right now/);
  assert.doesNotMatch(r.err, /opens now/, 'a refused login never tells the operator to go to the browser');
  assert.ok(!fs.existsSync(path.join(target, '.fabric-read.lock')), 'login released its lock');
  r = await capture(() => main(['login', 'claude-b'], { home: h, env, stdinTTY: true, spawn: () => ({ status: 0 }) }));
  assert.equal(r.code, 1, 'a harness closed without /login is not a success'); assert.match(r.err, /not signed in/);
});

test('read: one line per account from the op; any account not ok is exit 1; none observed is said', async () => {
  const h = scratch('accounts-read-');
  const read = async () => ({ status: 'ok', accounts: [
    { slug: 'claude-a', email: 'a@example.org', status: 'ok', limits: [{ kind: 'session', percent: 11, resets_at: '2026-09-24T18:49:59Z' }, { kind: 'weekly_scoped', percent: 86, resets_at: '2026-09-28T15:59:59Z', model: 'Opus' }] },
    { slug: 'claude-b', email: null, status: 'failed', error: 'Failed to refresh OAuth token' }] });
  const r = await capture(() => main(['read'], { home: h, env: {}, read }));
  assert.equal(r.code, 1);
  assert.match(r.out, /a@example\.org\s+ok\s+session 11% resets 2026-09-24T18:49; weekly_scoped 86% \(Opus\) resets 2026-09-28T15:59/);
  assert.match(r.out, /claude-b\s+failed\s+Failed to refresh OAuth token/);
  const none = await capture(() => main(['read'], { home: h, env: {}, read: async () => ({ status: 'none' }) }));
  assert.equal(none.code, 1); assert.match(none.out, /no Claude account observed/);
  assert.equal((await capture(() => main(['bogus'], { home: h, env: {} }))).code, 2);
});

// The coordinator's store, faked at the command fabric-accounts runs:
// `fabric-secrets store templates|assign … --json`. It keeps the value in
// its own process, so only fingerprints and rows come back.
const fp = v => crypto.createHash('sha256').update(v).digest('hex').slice(0, 12);
function fakeStore() {
  const tpl = { 'claude-a': 'sk-ant-oat01-A', 'claude-b': 'sk-ant-oat01-B', 'claude-empty': '' };
  const on = { 'flutter-dev-01': 'none', 'db-admin': 'none', 'web-dev-01': 'claude-a' };
  const calls = [];
  const exec = (bin, args) => {
    assert.equal(path.basename(bin), 'fabric-secrets', 'nothing but the store is asked');
    calls.push(args.join(' '));
    if (args[1] === 'templates') return JSON.stringify(Object.entries(tpl).map(([account, v]) => ({ account, token_sha256_12: v ? fp(v) : null })));
    const [, , account, ...rest] = args;
    const logins = rest.filter(a => a !== '--json' && a !== '--force');
    return JSON.stringify(logins.map(login => {
      const from = on[login];
      if (from === account) return { login, from, to: account, status: 'unchanged' };
      on[login] = account;
      return { login, from, to: account, status: 'written' };
    }));
  };
  return { on, calls, exec };
}
function placedRegistry() {
  const f = path.join(scratch('assign-reg-'), 'registry.json');
  fs.writeFileSync(f, JSON.stringify({ hosts: { h: { operator: 'user' } }, placement: { 'flutter-dev-01': 'h', 'db-admin': 'h', 'web-dev-01': 'h' } }));
  return f;
}

test('templates: each template in the store by fingerprint; one without a token is not a clean answer; no value is printed', async () => {
  const d = fakeStore();
  const r = await capture(() => main(['templates'], { home: scratch('accounts-tpl-'), env: {}, exec: d.exec }));
  assert.equal(r.code, 1, 'a template without a token is not a clean answer');
  assert.match(r.out, new RegExp(`claude-a\\s+setup-token ${fp('sk-ant-oat01-A')}`));
  assert.match(r.out, /claude-empty\s+no CLAUDE_CODE_OAUTH_TOKEN/);
  assert.ok(!r.out.includes('sk-ant-oat01'));
  assert.deepEqual(d.calls, ['store templates --json']);
});

test('assign: the token is written into each login\'s store, a login already there is left alone, and every named login syncs, proves the template\'s fingerprint and restarts', async () => {
  const d = fakeStore(); const registry = placedRegistry();
  let synced;
  const r = await capture(() => main(['assign', 'flutter-dev-01', 'web-dev-01', 'claude-b'], { home: scratch('assign-home-'), env: {}, exec: d.exec, registry, spawn: (bin, args) => { synced = [path.basename(bin), ...args]; return { status: 0 }; } }));
  assert.equal(r.code, 0, r.err + r.out);
  assert.deepEqual([d.on['flutter-dev-01'], d.on['web-dev-01']], ['claude-b', 'claude-b']);
  assert.match(r.out, /flutter-dev-01\s+none\s+→ claude-b\s+written/);
  assert.match(r.out, /web-dev-01\s+claude-a\s+→ claude-b\s+written/);
  assert.deepEqual(synced, ['fabric-ctl', 'flutter-dev-01', 'web-dev-01', 'secrets-sync', '--expect', fp('sk-ant-oat01-B'), '--restart']);
  assert.ok(!r.out.includes('sk-ant-oat01'), 'no template token in the output');
  synced = null;
  const again = await capture(() => main(['assign', 'flutter-dev-01', 'claude-b', '--no-restart'], { home: scratch('assign-home-'), env: {}, exec: d.exec, registry, spawn: (bin, args) => { synced = args; return { status: 0 }; } }));
  assert.equal(again.code, 0); assert.match(again.out, /flutter-dev-01\s+claude-b\s+→ claude-b\s+unchanged/);
  assert.deepEqual(synced, ['flutter-dev-01', 'secrets-sync', '--expect', fp('sk-ant-oat01-B')], 'unchanged in the store, still proved on the account; --no-restart leaves its session alone');
  const failed = await capture(() => main(['assign', 'flutter-dev-01', 'claude-b'], { home: scratch('assign-home-'), env: {}, exec: d.exec, registry, spawn: () => ({ status: 1 }) }));
  assert.equal(failed.code, 1, 'an account that did not prove the move fails the command');
});

test('assign: no way back to a login\'s own /login; an unknown login, an unknown template and an empty template are refused before anything is written', async () => {
  const d = fakeStore(); const registry = placedRegistry();
  for (const [args, re] of [[['assign', 'web-dev-01', 'own'], /runs only on a template's token/], [['assign', 'nobody', 'claude-b'], /not a placed account/], [['assign', 'db-admin', 'claude-zzz'], /not a template/], [['assign', 'db-admin', 'claude-empty'], /holds no CLAUDE_CODE_OAUTH_TOKEN/]]) {
    const r = await capture(() => main(args, { home: scratch('assign-home-'), env: {}, exec: d.exec, registry, spawn: () => assert.fail('no sync') }));
    assert.equal(r.code, 2, args.join(' ')); assert.match(r.err, re);
  }
  assert.ok(!d.calls.some(c => c.startsWith('store assign')), 'a refusal writes nothing');
});

test('assign: a failed row still comes back as a row and fails the run; --no-sync proves nothing and syncs nothing', async () => {
  const calls = [];
  const exec = (bin, args) => {
    calls.push(args.join(' '));
    if (args[1] === 'templates') return JSON.stringify([{ account: 'work', token_sha256_12: 'abcdef012345' }]);
    const e = new Error('exit 1'); e.stdout = JSON.stringify([{ login: 'a', status: 'written' }, { login: 'b', status: 'failed', reason: 'no committed key for b' }]); throw e;
  };
  assert.deepEqual(storeTemplates({ exec }), [{ account: 'work', token_sha256_12: 'abcdef012345' }]);
  assert.deepEqual(storeAssign(['a', 'b'], 'work', { exec, force: true }).map(r => r.status), ['written', 'failed']);
  assert.deepEqual(calls, ['store templates --json', 'store assign work a b --force --json']);
  const reg = path.join(scratch('accounts-nosync-'), 'hosts.json');
  fs.writeFileSync(reg, JSON.stringify({ hosts: { h: {} }, placement: { a: 'h', b: 'h' } }));
  const r = await capture(() => main(['assign', 'a', 'b', 'work', '--no-sync'], { home: scratch('assign-home-'), env: {}, exec, registry: reg, spawn: () => assert.fail('no sync') }));
  assert.equal(r.code, 1, r.out + r.err);
  assert.match(r.out, /b .* failed  no committed key for b/);
  assert.match(r.err, /--no-sync — each changed login applies it at its next fabric-secrets sync/);
});
