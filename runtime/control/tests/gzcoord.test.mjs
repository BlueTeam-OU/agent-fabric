// The control plane's own copy of GZCoord's identity, integration, token,
// relay API and hold (runtime/control/gzcoord.mjs). The cases on identity,
// the catalogue, inboxRoot, integrationConfig and holdStatus are
// communication/gzcoord/tests/protocol.test.mjs's, case for case, run here
// against this copy (agent-fabric ADR-040 §7); the token, syncedVar and
// api cases are this module's own, since the protocol suite reaches those
// only through the commands.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { scratch } from '../../../tests/scratch.mjs';
import { whoami, FABRIC_ROOT, findTaxonomy, loadTaxonomy, identity, integrationConfig, inboxRoot, token, syncedToken, syncedVar, api, holdStatus } from '../gzcoord.mjs';

const CATALOG = fileURLToPath(new URL('../../../identities/roles/catalog.json', import.meta.url));
const taxonomy = loadTaxonomy(CATALOG);
const login = os.userInfo().username;

test('FABRIC_ROOT is the checkout this module sits in, and the catalogue is found under it', () => {
  assert.equal(FABRIC_ROOT, process.env.AGENT_FABRIC_ROOT ?? path.resolve(import.meta.dirname, '..', '..', '..'));
  assert.ok(findTaxonomy().endsWith('/identities/roles/catalog.json'));
  assert.equal(taxonomy.path, CATALOG);
  assert.ok(taxonomy.roles.has('python-dev'));
  const empty = path.join(scratch('catalog-'), 'catalog.json');
  fs.writeFileSync(empty, JSON.stringify({ roles: [{ id: 'x' }] }));
  assert.throws(() => loadTaxonomy(empty), /holds no roles with id and title/);
});

// A throwaway agent-fabric STATE directory holding this agent's binding
// (or none, or a broken one), with AGENT_FABRIC_STATE_DIR pointing at it
// for the duration so whoami() is kept off the developer's real binding.
function fixtureRoot(state) {
  const root = scratch('gzcoord-fixture-');
  fs.mkdirSync(`${root}/state/agents/${login}`, { recursive: true });
  fs.copyFileSync(CATALOG, `${root}/catalog.json`);
  if (state !== undefined) fs.writeFileSync(`${root}/state/agents/${login}/binding.json`, state);
  return root;
}
// Synchronous callbacks only: the finally fires when fn RETURNS, so an
// async fn would have its fixture removed while still running.
const withFixture = (state, fn) => {
  const root = fixtureRoot(state);
  const saved = process.env.AGENT_FABRIC_STATE_DIR;
  process.env.AGENT_FABRIC_STATE_DIR = `${root}/state`;
  try {
    const r = fn(root, `${root}/catalog.json`);
    if (r instanceof Promise) throw new TypeError('withFixture takes a synchronous callback');
    return r;
  } finally {
    if (saved === undefined) delete process.env.AGENT_FABRIC_STATE_DIR; else process.env.AGENT_FABRIC_STATE_DIR = saved;
    fs.rmSync(root, { recursive: true, force: true });
  }
};
const bound = (role) => JSON.stringify({ agent: login, host: 'h', role, updated_at: 'x' });

test('whoami: the agent is the effective login, never the directory', () => {
  const me = whoami();
  assert.equal(me.agent, login);
  assert.notEqual(me.agent, path.basename(process.cwd()) === login ? 'x' : path.basename(process.cwd()));
});

// The login is overridden AFTER the binding is read, so a slug-carrying
// account name can be exercised from whatever login runs the suite.
const asLogin = (agent, me = whoami()) => ({ ...me, agent });
test('identity derives the slug from the login when no role is recorded', () => withFixture(undefined, (root, tax) => {
  const me = identity(asLogin('architect-cto-01'), loadTaxonomy(tax));
  assert.equal(me.slug, 'architect-cto');
  assert.equal(me.address, `${whoami().host}/architect-cto-01`);
  assert.equal(identity(asLogin('gzapp-claude2'), loadTaxonomy(tax)).slug, undefined, 'a login naming no role derives none');
}));

test('the recorded role wins over the login, and a recorded role outside the catalogue is an error', () => {
  withFixture(bound('backend-dev'), (root, tax) => {
    assert.equal(identity(asLogin('architect-cto-01'), loadTaxonomy(tax)).slug, 'backend-dev');
    assert.equal(identity(asLogin('architect-cto-01'), loadTaxonomy(tax)).roleError, undefined);
  });
  withFixture(bound('security-engineer'), (root, tax) => {
    // The fallback is said: the error travels with the identity every caller prints.
    const me = identity(asLogin('architect-cto-01'), loadTaxonomy(tax));
    assert.match(me.roleError, /binding\.json records role "security-engineer", which is not in .*catalog\.json; the login's role is used instead/);
    assert.equal(me.slug, 'architect-cto');
  });
  for (const state of ['not json', JSON.stringify({ agent: login, host: 'h', updated_at: 'x' })]) {
    withFixture(state, (root, tax) => {
      assert.equal(identity(asLogin('architect-cto-01'), loadTaxonomy(tax)).slug, 'architect-cto');
      assert.equal(identity(asLogin('architect-cto-01'), loadTaxonomy(tax)).roleError, undefined);
      assert.equal(identity(asLogin('gzapp-claude2'), loadTaxonomy(tax)).slug, undefined);
    });
  }
  assert.throws(() => withFixture(undefined, async () => {}), /synchronous callback/);
  withFixture(JSON.stringify({ agent: login, host: 'h', role: 'web-dev', project: 'gzapp', updated_at: 'x' }), (root, tax) => {
    const me = identity(whoami(), loadTaxonomy(tax));
    assert.equal(me.address, `${os.hostname().split('.')[0]}/${login}`);
    assert.equal(me.slug, 'web-dev');
    // The project is the WORKING COPY's when the suite runs inside a
    // registered one; the binding's project applies only outside any.
    assert.equal(me.project, whoami().project ?? 'gzapp');
  });
});

test('identity: address is <host>/<login>; the slug comes from the binding, then from the login', () => {
  const host = 'box';
  const noRole = { agent: 'architect-cto-01', host, role: undefined, binding: '/nonexistent/binding.json' };
  assert.deepEqual(identity(noRole, taxonomy), { address: 'box/architect-cto-01', instance: 'architect-cto-01', slug: 'architect-cto', project: undefined });
  assert.equal(identity({ ...noRole, role: 'backend-dev', project: 'gzapp' }, taxonomy).slug, 'backend-dev');
  assert.equal(identity({ ...noRole, role: 'backend-dev', project: 'gzapp' }, taxonomy).project, 'gzapp');
  assert.deepEqual(identity({ agent: 'user', host, binding: '/nonexistent' }, taxonomy), { address: 'box/user', instance: 'user', slug: undefined, project: undefined });
  assert.deepEqual(identity(noRole, undefined), { address: 'box/architect-cto-01', instance: 'architect-cto-01', slug: undefined, project: undefined });
  assert.equal(identity(whoami(), undefined).instance, login);
  // The longest whole-token slug wins, wherever the catalogue lists it.
  const nested = path.join(scratch('catalog-'), 'catalog.json');
  fs.writeFileSync(nested, JSON.stringify({ roles: [{ id: 'dev', title: 'Dev' }, { id: 'backend-dev', title: 'Backend' }] }));
  assert.equal(identity({ agent: 'backend-dev-01', host, binding: '/nonexistent' }, loadTaxonomy(nested)).slug, 'backend-dev');
  assert.equal(identity({ agent: 'web-developer', host, binding: '/nonexistent' }, loadTaxonomy(nested)).slug, undefined, 'a token match, not a substring');
});

test('inboxRoot uses the binding working copy outside a checkout', () => {
  const tmp = scratch('inbox-root-');
  const wc = path.join(tmp, 'clone'); fs.mkdirSync(wc);
  const binding = path.join(tmp, 'binding.json');
  fs.writeFileSync(binding, JSON.stringify({ working_copy: wc }));
  const cwd = process.cwd();
  try {
    process.chdir(tmp);                       // tmp is outside any repository
    assert.equal(inboxRoot({ working_copy: null, binding }), wc);
    assert.equal(inboxRoot({ working_copy: wc, binding: '/nonexistent' }), wc);
    fs.rmSync(wc, { recursive: true });
    assert.equal(inboxRoot({ working_copy: null, binding }), tmp, 'a vanished working copy falls back to the cwd');
  } finally { process.chdir(cwd); }
});

test('integrationConfig comes from the project or the environment, never a default of another project', () => {
  const none = integrationConfig('no-such-project', {});
  assert.equal(none.configured, false);
  assert.match(none.reason, /projects\/no-such-project\/integration\/gzcoord\/config.json/);
  assert.match(none.reason, /CLAUDE_BRIDGE_URL and GZCOORD_CHANNEL/);
  assert.equal(none.channel, undefined, 'no channel is ever guessed');
  assert.equal(integrationConfig(undefined, {}).configured, false, 'no project: not configured either');
  const fromEnv = integrationConfig('no-such-project', { CLAUDE_BRIDGE_URL: 'http://127.0.0.1:1', GZCOORD_CHANNEL: 'x:y' });
  assert.deepEqual([fromEnv.configured, fromEnv.source, fromEnv.relay_url, fromEnv.channel, fromEnv.token_env_file], [true, 'environment', 'http://127.0.0.1:1', 'x:y', undefined]);
  assert.equal(integrationConfig('no-such-project', { CLAUDE_BRIDGE_URL: 'http://127.0.0.1:1' }).configured, false, 'half an environment override configures nothing');
  const gz = integrationConfig('gzapp', {});
  assert.equal(gz.configured, true);
  assert.match(gz.source, /projects\/gzapp\/integration\/gzcoord\/config.json$/);
  assert.equal(gz.channel, 'gzapp:gzcoord');
  assert.equal(integrationConfig('gzapp', { GZCOORD_CHANNEL: 'over:ride' }).channel, 'over:ride', 'the environment overrides a project file');
});

// The start time /proc gives the pid, read here rather than through the
// module so the default startOf is what the "same start time" case meets.
const startOf = pid => fs.readFileSync(`/proc/${pid}/stat`, 'utf8').replace(/.*\) /s, '').split(' ')[19];
test('holdStatus: held iff some marker names a live harness of this login', () => {
  const dir = scratch('hold-');
  const f = pid => path.join(dir, `${pid}.json`);
  const uid = process.getuid();
  assert.equal(holdStatus(path.join(dir, 'none')).held, false, 'no directory');
  assert.equal(holdStatus(dir).held, false, 'empty directory');
  fs.writeFileSync(f(11), 'not json');
  assert.match(holdStatus(dir).reason, /11\.json: unreadable/);
  fs.writeFileSync(f(12), JSON.stringify({ session_id: 's' }));
  assert.match(holdStatus(dir).reason, /12\.json: names no pid/);
  fs.writeFileSync(f(process.pid), JSON.stringify({ session_id: 'me', pid: process.pid, start: startOf(process.pid), since: 't' }));
  const h = holdStatus(dir);
  assert.equal(h.held, true, 'our own pid, alive, same start time');
  assert.deepEqual(h.sessions.map(x => x.pid), [process.pid]);
  assert.equal(holdStatus(dir, { isAlive: () => false }).held, false, 'a dead pid is not a hold');
  assert.match(holdStatus(dir, { isAlive: () => false }).reason, /is gone/);
  // the production liveness: pid 1 answers EPERM to an unprivileged login and is nobody's harness
  if (process.getuid() !== 0) {
    fs.writeFileSync(f(1), JSON.stringify({ session_id: 'forged', pid: 1, start: '' }));
    assert.deepEqual(holdStatus(dir).sessions.map(x => x.pid), [process.pid], 'a forged marker naming pid 1 does not hold, with the default isAlive');
    fs.unlinkSync(f(1));
  }
  fs.writeFileSync(f(process.pid), JSON.stringify({ session_id: 'me', pid: process.pid, start: 'other', since: 't' }));
  assert.equal(holdStatus(dir).held, false, 'a pid with another start time is not the harness, with the default startOf');
  assert.match(holdStatus(dir).reason, /reused/);
  fs.writeFileSync(f(process.pid), JSON.stringify({ session_id: 'me', pid: process.pid, start: startOf(process.pid), since: 't' }));
  assert.equal(holdStatus(dir, { startOf: () => 'other' }).held, false, 'a pid with another start time is not the harness');
  assert.equal(holdStatus(dir, { startOf: () => '' }).held, true, 'an unknown start time (off Linux) falls back to the pid');
  fs.writeFileSync(f(4194304000), JSON.stringify({ session_id: 'gone', pid: 4194304000 }));
  assert.equal(holdStatus(dir).held, true, 'one live marker among dead ones holds');
  assert.equal(holdStatus(dir, { uid: uid + 1 }).held, false);
  assert.equal(holdStatus(dir, { uid: uid + 1 }).reason, "hold directory is not this login's", 'the directory itself, not only its files');
  const link = path.join(scratch('hold-link-'), 'link');
  fs.symlinkSync(dir, link);
  assert.match(holdStatus(link).reason, /not a directory/, 'a symlinked directory is refused');
  // the default directory is under the login's home, overridable for tests
  const saved = process.env.AGENT_FABRIC_HOLD_DIR;
  process.env.AGENT_FABRIC_HOLD_DIR = dir;
  try { assert.equal(holdStatus().held, true, 'AGENT_FABRIC_HOLD_DIR names the directory'); }
  finally { if (saved === undefined) delete process.env.AGENT_FABRIC_HOLD_DIR; else process.env.AGENT_FABRIC_HOLD_DIR = saved; }
  const home = scratch('hold-home-');
  fs.mkdirSync(path.join(home, '.cache', 'agent-fabric'), { recursive: true });
  fs.symlinkSync(dir, path.join(home, '.cache', 'agent-fabric', 'hold'));
  const savedHome = process.env.HOME;
  delete process.env.AGENT_FABRIC_HOLD_DIR;
  process.env.HOME = home;
  try { assert.match(holdStatus().reason, /not a directory/, 'without the override, ~/.cache/agent-fabric/hold is the directory read'); }
  finally { process.env.HOME = savedHome; if (saved !== undefined) process.env.AGENT_FABRIC_HOLD_DIR = saved; }
});

const secretsHome = text => {
  const home = scratch('home-');
  fs.mkdirSync(path.join(home, '.config', 'agent-fabric'), { recursive: true });
  if (text !== undefined) fs.writeFileSync(path.join(home, '.config', 'agent-fabric', 'secrets.env'), text);
  return home;
};
test('syncedVar reads one export line of the synced secrets file, unquoted', () => {
  const home = secretsHome("# x\nexport A='single'\nexport B=\"double\"\nexport C=bare  \nexport D=''\nexport AXB=not-a-dot\nexport A.B=dot\n");
  assert.equal(syncedVar('A', home), 'single');
  assert.equal(syncedVar('B', home), 'double');
  assert.equal(syncedVar('C', home), 'bare');
  assert.equal(syncedVar('D', home), undefined, 'an empty value is no value');
  assert.equal(syncedVar('MISSING', home), undefined);
  assert.equal(syncedVar('A.B', home), 'dot', 'the name is matched literally');
  assert.equal(syncedVar('A', secretsHome(undefined)), undefined, 'no file: not enrolled');
  assert.equal(syncedToken(secretsHome("export CLAUDE_BRIDGE_AUTH_TOKEN='t1'\n")), 't1');
});

// The synced file first, then the environment snapshot, then the working
// copy's token file, its settings.local.json, the relay's own token.
test('token: the synced file, then the environment, then the working copy, then the hosting workspace', () => {
  const savedHome = process.env.HOME, savedTok = process.env.CLAUDE_BRIDGE_AUTH_TOKEN;
  const root = scratch('wc-');
  const ws = scratch('ws-');
  const cfg = { token_env_file: '.gzcoord.env', relay_runtime_dir: ws };
  try {
    process.env.HOME = secretsHome("export CLAUDE_BRIDGE_AUTH_TOKEN='synced'\n");
    process.env.CLAUDE_BRIDGE_AUTH_TOKEN = 'environment';
    assert.equal(token(root, cfg), 'synced', 'the synced file wins over the environment snapshot');
    process.env.HOME = secretsHome(undefined);
    assert.equal(token(root, cfg), 'environment');
    delete process.env.CLAUDE_BRIDGE_AUTH_TOKEN;
    assert.equal(token(root, cfg), undefined, 'nothing anywhere: no token, never a guess');
    fs.writeFileSync(path.join(ws, 'bridge-token'), 'hosted\n');
    assert.equal(token(root, cfg), 'hosted');
    fs.mkdirSync(path.join(root, '.claude'));
    fs.writeFileSync(path.join(root, '.claude', 'settings.local.json'), JSON.stringify({ env: { CLAUDE_BRIDGE_AUTH_TOKEN: 'local' } }));
    assert.equal(token(root, cfg), 'local');
    fs.writeFileSync(path.join(root, '.gzcoord.env'), 'OTHER=x\nCLAUDE_BRIDGE_AUTH_TOKEN= file \n');
    assert.equal(token(root, cfg), 'file');
  } finally {
    process.env.HOME = savedHome;
    if (savedTok === undefined) delete process.env.CLAUDE_BRIDGE_AUTH_TOKEN; else process.env.CLAUDE_BRIDGE_AUTH_TOKEN = savedTok;
  }
});

test('api sends the bearer token and JSON, and a refusal throws with its status', async () => {
  const seen = [];
  const server = http.createServer((req, res) => {
    let body = ''; req.on('data', c => body += c); req.on('end', () => {
      seen.push({ url: req.url, method: req.method, auth: req.headers.authorization, type: req.headers['content-type'], body });
      res.setHeader('connection', 'close'); res.setHeader('content-type', 'application/json');
      if (req.url === '/refused') { res.statusCode = 401; res.end('{}'); return; }
      res.end(JSON.stringify({ ok: true }));
    });
  });
  await new Promise(r => server.listen(0, '127.0.0.1', r));
  const relayUrl = `http://127.0.0.1:${server.address().port}`;
  try {
    assert.deepEqual(await api('tok', '/api/x?a=1', { relayUrl, method: 'POST', body: '{"k":1}' }), { ok: true });
    assert.deepEqual(seen[0], { url: '/api/x?a=1', method: 'POST', auth: 'Bearer tok', type: 'application/json', body: '{"k":1}' });
    await assert.rejects(api('tok', '/refused', { relayUrl }), e => e.status === 401 && e.message === '/refused -> HTTP 401');
  } finally { server.closeAllConnections(); server.close(); }
});

// The point of this module: the daemon never depends on a script that
// becomes a shim when GZCoord's tools move to Python (ADR-040 §7).
test('no control-plane module imports from communication/gzcoord/scripts/', () => {
  const dir = fileURLToPath(new URL('..', import.meta.url));
  const offenders = [];
  for (const name of fs.readdirSync(dir, { recursive: true })) {
    if (!name.endsWith('.mjs')) continue;
    const src = fs.readFileSync(path.join(dir, name), 'utf8');
    for (const m of src.matchAll(/(?:\bfrom\s*|\bimport\s*\(\s*)['"]([^'"]+)['"]/g))
      if (m[1].includes('communication/gzcoord/scripts/')) offenders.push(`${name}: ${m[1]}`);
  }
  assert.deepEqual(offenders, []);
});
