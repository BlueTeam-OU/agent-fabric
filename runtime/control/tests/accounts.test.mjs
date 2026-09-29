// bin/fabric-accounts: the setup and the local look at the observed Claude
// accounts. No token ever reaches the output; login needs a terminal and a
// valid account name, and runs the harness in that account's own config
// directory with no inherited token.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { scratch } from '../../../tests/scratch.mjs';
import { main, describe, listLines, templates, templateRef } from '../accounts.mjs';
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

test('templates: each Doppler template by fingerprint, read with the observer\'s token; the value goes into a hash and nowhere else', async () => {
  const TOK = { 'claude-accounts_claude-a': 'sk-ant-oat01-AAAA', 'claude-accounts_claude-b': '' };
  const calls = [];
  const exec = (bin, args) => {
    calls.push([bin, ...args]);
    if (args[0] === 'configs') return JSON.stringify([{ name: 'claude-accounts' }, { name: 'claude-accounts_claude-b' }, { name: 'claude-accounts_claude-a' }]);
    const cfg = args[args.indexOf('--config') + 1];
    if (!TOK[cfg]) throw new Error('Doppler Error: Could not find requested secret');
    return TOK[cfg] + '\n';   // doppler --plain ends with a newline; the fingerprint must not include it
  };
  const t = templates({ exec });
  const fp = crypto.createHash('sha256').update('sk-ant-oat01-AAAA').digest('hex').slice(0, 12);
  assert.deepEqual(t, [{ account: 'claude-a', config: 'claude-accounts_claude-a', token_sha256_12: fp }, { account: 'claude-b', config: 'claude-accounts_claude-b', token_sha256_12: null }]);
  assert.ok(calls.every(c => c.includes('--project') && c.includes('agent-fabric')), 'every doppler call names the project');
  const r = await capture(() => main(['templates'], { home: scratch('accounts-tpl-'), env: {}, exec }));
  assert.equal(r.code, 1, 'a template without a token is not a clean answer');
  assert.match(r.out, new RegExp(`claude-a\\s+setup-token ${fp}`));
  assert.match(r.out, /claude-b\s+no CLAUDE_CODE_OAUTH_TOKEN/);
  assert.ok(!r.out.includes('sk-ant-oat01-AAAA'));
});

// A Doppler with state: configs, secrets per config, the two templates.
function fakeDoppler(initial = {}) {
  const store = { 'agents_flutter-dev-01': {}, 'agents_db-admin': {}, 'agents2_web-dev-01': { CLAUDE_CODE_OAUTH_TOKEN: templateRef('claude-a') }, 'claude-accounts_claude-a': { CLAUDE_CODE_OAUTH_TOKEN: 'sk-ant-oat01-A' }, 'claude-accounts_claude-b': { CLAUDE_CODE_OAUTH_TOKEN: 'sk-ant-oat01-B' }, 'claude-accounts_claude-empty': {}, ...initial };
  const writes = [];
  const exec = (bin, args) => {
    const cfg = args[args.indexOf('--config') + 1];
    if (args[0] === 'configs') return JSON.stringify(['agents', 'agents2', 'claude-accounts', ...Object.keys(store)].map(name => ({ name })));
    if (args[0] === 'secrets' && args[1] === 'get') { const v = store[cfg]?.[args[2]]; if (v === undefined) throw new Error('Doppler Error: Could not find requested secret'); return v + '\n'; }
    if (args[0] === 'secrets' && args[1] === 'set') { writes.push(['set', cfg, args[2]]); const [k, ...v] = args[2].split('='); store[cfg][k] = v.join('='); return ''; }
    if (args[0] === 'secrets' && args[1] === 'delete') { writes.push(['delete', cfg, args[2]]); delete store[cfg][args[2]]; return ''; }
    throw new Error('unexpected doppler ' + args.join(' '));
  };
  return { store, writes, exec };
}
function placedRegistry() {
  const f = path.join(scratch('assign-reg-'), 'registry.json');
  fs.writeFileSync(f, JSON.stringify({ hosts: { h: { operator: 'user' } }, placement: { 'flutter-dev-01': 'h', 'db-admin': 'h', 'web-dev-01': 'h' } }));
  return f;
}

test('assign: the reference is written and read back, a login already there is left alone in Doppler, and every named login syncs, proves the template\'s fingerprint and restarts', async () => {
  const d = fakeDoppler(); const registry = placedRegistry();
  let synced;
  const r = await capture(() => main(['assign', 'flutter-dev-01', 'web-dev-01', 'claude-b'], { home: scratch('assign-home-'), env: {}, exec: d.exec, registry, spawn: (bin, args) => { synced = [path.basename(bin), ...args]; return { status: 0 }; } }));
  assert.equal(r.code, 0, r.err + r.out);
  assert.equal(d.store['agents_flutter-dev-01'].CLAUDE_CODE_OAUTH_TOKEN, templateRef('claude-b'));
  assert.equal(d.store['agents2_web-dev-01'].CLAUDE_CODE_OAUTH_TOKEN, templateRef('claude-b'));
  assert.match(r.out, /flutter-dev-01\s+none\s+→ claude-b\s+written/);
  assert.match(r.out, /web-dev-01\s+claude-a\s+→ claude-b\s+written/);
  const fpB = crypto.createHash('sha256').update('sk-ant-oat01-B').digest('hex').slice(0, 12);
  assert.deepEqual(synced, ['fabric-ctl', 'flutter-dev-01', 'web-dev-01', 'secrets-sync', '--expect', fpB, '--restart']);
  assert.ok(!r.out.includes('sk-ant-oat01'), 'no template token in the output');
  synced = null;
  const again = await capture(() => main(['assign', 'flutter-dev-01', 'claude-b', '--no-restart'], { home: scratch('assign-home-'), env: {}, exec: d.exec, registry, spawn: (bin, args) => { synced = args; return { status: 0 }; } }));
  assert.equal(again.code, 0); assert.match(again.out, /flutter-dev-01\s+claude-b\s+→ claude-b\s+unchanged/);
  assert.deepEqual(synced, ['flutter-dev-01', 'secrets-sync', '--expect', fpB], 'unchanged in Doppler, still proved on the account; --no-restart leaves its session alone');
  const failed = await capture(() => main(['assign', 'flutter-dev-01', 'claude-b'], { home: scratch('assign-home-'), env: {}, exec: d.exec, registry, spawn: () => ({ status: 1 }) }));
  assert.equal(failed.code, 1, 'an account that did not prove the move fails the command');
});

test('assign: no way back to a login\'s own /login; an unknown login, an unknown template and an empty template are refused before anything is written', async () => {
  const d = fakeDoppler(); const registry = placedRegistry();
  const n = d.writes.length;
  for (const [args, re] of [[['assign', 'web-dev-01', 'own'], /runs only on a template's token/], [['assign', 'nobody', 'claude-b'], /not a placed account/], [['assign', 'db-admin', 'claude-zzz'], /not a template/], [['assign', 'db-admin', 'claude-empty'], /holds no CLAUDE_CODE_OAUTH_TOKEN/]]) {
    const r = await capture(() => main(args, { home: scratch('assign-home-'), env: {}, exec: d.exec, registry, spawn: () => assert.fail('no sync') }));
    assert.equal(r.code, 2, args.join(' ')); assert.match(r.err, re);
  }
  assert.equal(d.writes.length, n, 'a refusal writes nothing');
});

// On the coordinator's store (ADR-038): the templates and an assignment
// go through fabric-secrets store, which keeps every value in its own
// process; a failed row still comes back as a row.
test('accounts on the store: onStore reads the source; templates and assign go through fabric-secrets store', async () => {
  const { onStore, storeTemplates, storeAssign } = await import('../accounts.mjs');
  const home = scratch('accounts-store-');
  assert.equal(onStore(home), false, 'no source file is doppler');
  fs.mkdirSync(path.join(home, '.config', 'agent-fabric'), { recursive: true });
  fs.writeFileSync(path.join(home, '.config', 'agent-fabric', 'secrets-source'), 'store\n');
  assert.equal(onStore(home), true);
  const calls = [];
  const exec = (bin, args) => {
    calls.push(args.join(' '));
    if (args[1] === 'templates') return JSON.stringify([{ account: 'work', token_sha256_12: 'abcdef012345' }]);
    const e = new Error('exit 1'); e.stdout = JSON.stringify([{ login: 'a', status: 'written' }, { login: 'b', status: 'failed', reason: 'no committed key for b' }]); throw e;
  };
  assert.deepEqual(storeTemplates({ exec }), [{ account: 'work', token_sha256_12: 'abcdef012345', config: 'store' }]);
  const rows = storeAssign(['a', 'b'], 'work', { exec });
  assert.deepEqual(rows.map(r => r.status), ['written', 'failed']);
  assert.deepEqual(calls, ['store templates --json', 'store assign work a b --json']);
});
