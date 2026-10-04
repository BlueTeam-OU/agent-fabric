// The control agent against a fake relay: what it answers, what it
// ignores, what it never does (ack, replay history, execute anything).
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import http from 'node:http';
import { spawn } from 'node:child_process';
import crypto from 'node:crypto';
import zlib from 'node:zlib';
import { scratch } from '../../../tests/scratch.mjs';
import { accept, remember, SEEN_MAX, newId, operatorAddresses, controlConfig, watchSource, answer, accountsKeeper, ACCOUNTS_KEEPALIVE_MS, leaver } from '../agentd.mjs';
import { memorySlug, SIGNING_ROW } from '../ops.mjs';
import { generateOperatorKey, signRequest } from '../sign.mjs';
import { whoami } from '../gzcoord.mjs';
import { fileURLToPath } from 'node:url';

const AGENTD = fileURLToPath(new URL('../agentd.mjs', import.meta.url));
const ROOT = fileURLToPath(new URL('../../../', import.meta.url)).replace(/\/$/, '');
const me = { address: 'develop-qzapp/db-admin' };
const operators = new Set(['develop-qzapp/user']);
const req = (over = {}) => ({ content: JSON.stringify({ v: 1, kind: 'request', id: newId(), from: 'develop-qzapp/user', to: '*', op: 'ping', ts: new Date().toISOString(), ttl_s: 30, ...over }) });

test('accept: the fence, case by case', () => {
  const seen = new Set();
  const ok = accept(req(), { me, operators, ttl_s: 30, seen });
  assert.equal(ok.ok, true, JSON.stringify(ok));
  assert.equal(accept(req({ to: 'develop-qzapp/db-admin' }), { me, operators, ttl_s: 30, seen }).ok, true, 'addressed to me');
  assert.equal(accept(req({ to: ['develop-qzapp/x', 'develop-qzapp/db-admin'] }), { me, operators, ttl_s: 30, seen }).ok, true, 'in a list');
  assert.equal(accept(req({ to: 'develop-qzapp/other' }), { me, operators, ttl_s: 30, seen }).why, 'not for me');
  assert.match(accept(req({ op: 'shutdown' }), { me, operators, ttl_s: 30, seen }).why, /^op shutdown/);
  assert.match(accept(req({ from: 'develop-qzapp/backend-dev-01' }), { me, operators, ttl_s: 30, seen }).why, /not an operator/);
  // presence is answered for any placed account; every other op still only for an operator
  const accounts = new Set(['develop-qzapp/backend-dev-01', 'develop-qzapp/db-admin']);
  assert.equal(accept(req({ from: 'develop-qzapp/backend-dev-01', op: 'presence' }), { me, operators, accounts, ttl_s: 30, seen }).ok, true, 'a placed account may ask presence');
  assert.match(accept(req({ from: 'develop-qzapp/backend-dev-01', op: 'session' }), { me, operators, accounts, ttl_s: 30, seen }).why, /not an operator$/, 'but nothing else');
  assert.match(accept(req({ from: 'elsewhere/stranger', op: 'presence' }), { me, operators, accounts, ttl_s: 30, seen }).why, /not an operator or a placed account/, 'an address no host places is refused');
  assert.equal(accept(req({ ts: new Date(Date.now() - 60000).toISOString(), ttl_s: 30 }), { me, operators, ttl_s: 30, seen }).why, 'expired');
  assert.equal(accept(req({ ts: 'garbage' }), { me, operators, ttl_s: 30, seen }).why, 'expired');
  assert.equal(accept({ content: 'not json' }, { me, operators, ttl_s: 30, seen }).why, 'not json');
  assert.equal(accept({ content: JSON.stringify({ v: 1, kind: 'reply', id: 'x' }) }, { me, operators, ttl_s: 30, seen }).why, 'not a request');
  assert.equal(accept(req({ v: 2 }), { me, operators, ttl_s: 30, seen }).why, 'v 2');
  const dup = req(); const id = JSON.parse(dup.content).id;
  assert.equal(accept(dup, { me, operators, ttl_s: 30, seen }).ok, true); remember(seen, id);
  assert.equal(accept(dup, { me, operators, ttl_s: 30, seen }).why, 'seen');
  for (let i = 0; i < SEEN_MAX + 5; i++) remember(seen, `x${i}`);
  assert.ok(seen.size <= SEEN_MAX + 1, 'the LRU is bounded');
  assert.ok(!seen.has(id), 'the oldest ids fall out');
});

test('operatorAddresses and controlConfig read the fabric\'s own files', () => {
  const ops = operatorAddresses(path.join(ROOT, 'runtime', 'hosts', 'registry.json'));
  assert.ok(ops.has('develop-qzapp/user'), [...ops]);
  assert.deepEqual(operatorAddresses('/nonexistent'), new Set());
  const c = controlConfig({});
  assert.equal(c.channel, 'fabric:control'); assert.equal(c.ttl_s, 30);
  assert.equal(controlConfig({ FABRIC_CONTROL_CHANNEL: 'x:control', CLAUDE_BRIDGE_URL: 'http://h:1' }).relay_url, 'http://h:1');
});

test('watchSource: a changed .mjs in a watched directory fires once, after the quiet period; a .txt does not', async () => {
  const dir = scratch('agentd-src-');
  let fired = 0;
  const ws = watchSource(() => { fired += 1; }, [dir]);
  try {
    fs.writeFileSync(path.join(dir, 'notes.txt'), 'x');
    await new Promise(r => setTimeout(r, 2500));
    assert.equal(fired, 0, 'a non-source file is not a change');
    fs.writeFileSync(path.join(dir, 'a.mjs'), '1'); fs.writeFileSync(path.join(dir, 'b.mjs'), '2');   // a pull: several files
    await new Promise(r => setTimeout(r, 2800));
    assert.equal(fired, 1, 'one restart for one pull');
  } finally { for (const w of ws) w?.close(); fs.rmSync(dir, { recursive: true, force: true }); }
});

// A fake relay that keeps a channel in memory: /api/messages (newest N, or
// after since_id), /api/wait (after since_id; 1 s), /api/send. Records
// every request path so the test can assert what was never called.
function relay(initial = []) {
  const rows = []; let seq = 0;
  const add = (sender, content) => { seq += 1; const r = { seq, id: `id-${seq}`, sender, content, timestamp: new Date().toISOString() }; rows.push(r); return r; };
  for (const [s, c] of initial) add(s, c);
  const hits = [];
  const server = http.createServer((req, res) => {
    const u = new URL(req.url, 'http://x'); hits.push(u.pathname + u.search);
    res.setHeader('content-type', 'application/json');
    const after = id => { const i = rows.findIndex(r => r.id === id); return i < 0 ? null : rows.slice(i + 1); };
    if (u.pathname === '/api/messages') {
      const since = u.searchParams.get('since_id'); const limit = Number(u.searchParams.get('limit') || 50);
      if (since) { const a = after(since); res.end(JSON.stringify(a === null ? { messages: [], warning: 'since_id_not_found' } : { messages: a.slice(0, limit) })); }
      else res.end(JSON.stringify({ messages: rows.slice(-limit) }));
      return;
    }
    if (u.pathname === '/api/wait') {
      // a long poll, like the relay: answer when something follows since_id, or at the timeout
      const since = u.searchParams.get('since_id'); const deadline = Date.now() + Number(u.searchParams.get('timeout_seconds') || 1) * 1000;
      const tick = () => {
        const a = since ? after(since) : rows;
        if (a === null) { res.end(JSON.stringify({ messages: [], warning: 'since_id_not_found' })); return; }
        if (a.length || Date.now() >= deadline) { res.end(JSON.stringify({ messages: a.slice(0, 50) })); return; }
        setTimeout(tick, 50);
      };
      tick(); return;
    }
    if (u.pathname === '/api/send') {
      let body = ''; req.on('data', c => body += c); req.on('end', () => { const b = JSON.parse(body); const r = add(b.sender, b.content); res.end(JSON.stringify({ seq: r.seq, id: r.id, deduplicated: false })); }); return;
    }
    res.statusCode = 404; res.end('{}');
  });
  const waiting = () => new Promise(res => { const t = () => hits.some(h => h.startsWith('/api/wait?')) ? res() : setTimeout(t, 20); t(); });
  return { server, rows, hits, add, waiting, listen: () => new Promise(r => server.listen(0, '127.0.0.1', r)), url: () => `http://127.0.0.1:${server.address().port}`, close: () => { server.closeAllConnections(); server.close(); } };
}
function scratchHome() {
  const h = scratch('agentd-home-');
  fs.mkdirSync(path.join(h, '.config', 'agent-fabric'), { recursive: true });
  fs.writeFileSync(path.join(h, '.config', 'agent-fabric', 'secrets.env'), "export CLAUDE_BRIDGE_AUTH_TOKEN='tok-fixture'\nexport OPENROUTER_API_KEY='sk-or-secret-value-0123456789'\n");
  return h;
}

test('answer: a memory reply is the report first, then one record per part in order; the parts never ride in the first record', async () => {
  const tar = crypto.randomBytes(2500);
  const exec = async () => ({ stdout: tar, stderr: JSON.stringify({ claims: 1, counts: { in_scope: 1, total: 1 }, needs_rendering: [], skipped_no_roles_class: [] }) });
  const h = scratch('agentd-mem-');
  const wc = path.join(h, 'projects', 'gzapp'); fs.mkdirSync(wc, { recursive: true });
  // The slug is the op's own rule (every non-alphanumeric to '-'), not a
  // '/'-only substitution: the run's TMPDIR carries a '.', and the two
  // rules differed exactly there.
  const mem = path.join(h, '.claude', 'projects', memorySlug(wc), 'memory'); fs.mkdirSync(mem, { recursive: true }); fs.writeFileSync(path.join(mem, 'a.md'), 'x');
  const ctx = { me: { address: 'h/db-admin' }, started: new Date().toISOString(), home: h, exec };
  const r = await answer({ id: 'q1', op: 'memory' }, ctx);
  assert.equal(r.op, 'memory'); assert.equal(r.in_reply_to, 'q1'); assert.equal(r.data.parts, 1);
  const b = r.data.memory.bundles[0];
  assert.equal(b.status, 'ok'); assert.equal(b.parts, 1); assert.equal(b.working_copy, wc); assert.equal(b.report.claims, 1);
  assert.ok(!('_parts' in b) && !JSON.stringify(r.data).includes('chunk'), 'the first record carries the report and sizes, not the bundle');
  assert.equal(r._followups.length, 1);
  const f = r._followups[0];
  assert.equal(f.kind, 'reply'); assert.equal(f.in_reply_to, 'q1'); assert.equal(f.from, 'h/db-admin'); assert.notEqual(f.id, r.id);
  assert.deepEqual(Object.keys(f.data), ['part']);
  assert.deepEqual({ slug: f.data.part.slug, part: f.data.part.part, parts: f.data.part.parts }, { slug: b.slug, part: 1, parts: 1 });
  assert.deepEqual(zlib.gunzipSync(Buffer.from(f.data.part.chunk, 'base64')), tar);
  assert.equal(crypto.createHash('sha256').update(tar).digest('hex'), b.sha256);
  const ping = await answer({ id: 'q2', op: 'ping' }, ctx);
  assert.ok(!('_followups' in ping), 'only a memory reply has follow-ups');
  const empty = await answer({ id: 'q3', op: 'memory' }, { ...ctx, home: scratch('agentd-nomem-') });
  assert.deepEqual(empty.data.memory, { status: 'ok', bundles: [] }); assert.equal(empty.data.parts, 0); assert.deepEqual(empty._followups, []);
  // A tokens request names its window; unset, absurd or huge, the op's default or the 90-day cap decides.
  const tk = await answer({ id: 'q4', op: 'tokens', days: 3 }, ctx);
  assert.equal(tk.data.tokens.days, 3); assert.ok('identity' in tk.data, 'tokens rides with identity');
  assert.equal((await answer({ id: 'q5', op: 'tokens' }, ctx)).data.tokens.days, 7);
  assert.equal((await answer({ id: 'q6', op: 'tokens', days: -2 }, ctx)).data.tokens.days, 7);
  assert.equal((await answer({ id: 'q7', op: 'tokens', days: 9999 }, ctx)).data.tokens.days, 90);
});

// A python3 on the daemon's PATH that answers for the harvester alone — a
// fixed payload on stdout, the report on stderr — and hands everything
// else to the real interpreter (whoami needs it). The payload is bigger
// than one relay message, so the parts are real at the real size.
function fakeHarvester(payload) {
  const bin = scratch('fake-py-');
  fs.writeFileSync(path.join(bin, 'payload.tar'), payload);
  const real = process.env.PATH.split(':').map(d => path.join(d, 'python3')).find(f => fs.existsSync(f));
  fs.writeFileSync(path.join(bin, 'python3'), `#!/bin/sh\ncase "$1" in *harvest_memory.py) cat "${bin}/payload.tar"; printf '%s' '{"claims": 4, "counts": {"in_scope": 5, "total": 5}, "needs_rendering": ["ka-1"], "skipped_no_roles_class": []}' >&2; exit 0;; esac\nexec "${real}" "$@"\n`, { mode: 0o755 });
  return bin;
}
const request = over => JSON.stringify({ v: 1, kind: 'request', id: newId(), from: 'develop-qzapp/user', to: '*', op: 'ping', ts: new Date().toISOString(), ttl_s: 30, ...over });
// What points git or gpg somewhere other than HOME. The daemon's keys
// probe runs the real git and gpg; under the runner's environment a
// GIT_CONFIG_GLOBAL, an XDG_CONFIG_HOME or a GNUPGHOME reaches past the
// scratch HOME into whoever runs the suite's own config and keyring
// (review of #89). Stripped as a class: GIT_CONFIG_COUNT/KEY/VALUE and
// GIT_CONFIG_PARAMETERS inject config the same way, and /etc/gitconfig
// is kept out with GIT_CONFIG_NOSYSTEM.
const POINTS_ELSEWHERE = /^(GIT_CONFIG.*|GIT_DIR|GIT_WORK_TREE|XDG_CONFIG_HOME|GNUPGHOME)$/;
const ownEnv = () => ({ ...Object.fromEntries(Object.entries(process.env).filter(([k]) => !POINTS_ELSEWHERE.test(k))), GIT_CONFIG_NOSYSTEM: '1' });
// Asynchronous: the fake relay lives in this process, and a synchronous
// spawn would block the event loop it answers from.
function runOnce(url, env = {}) {
  return new Promise(resolve => {
    const child = spawn('node', [AGENTD, '--once'], { env: { ...ownEnv(), HOME: scratchHome(), CLAUDE_BRIDGE_URL: url, FABRIC_CONTROL_CHANNEL: 'test:control', ...env } });
    let stderr = '', stdout = '';
    child.stderr.on('data', d => { stderr += d; }); child.stdout.on('data', d => { stdout += d; });
    const t = setTimeout(() => child.kill('SIGKILL'), 20000);
    child.on('close', (status, signal) => { clearTimeout(t); resolve({ status, signal, stderr, stdout }); });
  });
}
const replies = r => r.rows.filter(x => { try { return JSON.parse(x.content).kind === 'reply'; } catch { return false; } }).map(x => JSON.parse(x.content));

test('agentd --once: primes from the newest record, answers a live request, never acks, never answers history', async () => {
  const r = relay([['develop-qzapp/user', request({ op: 'status' })]]);   // history: must not be answered
  await r.listen();
  try {
    // prime happens at start; the request must land after it, so post it once the agent is up:
    // --once primes then waits 1 s, so a record added right after launch is what it sees.
    r.waiting().then(() => r.add('develop-qzapp/user', request({ op: 'ping' })));
    const out = await runOnce(r.url());
    assert.equal(out.status, 0, out.stderr);
    const rs = replies(r);
    assert.equal(rs.length, 1, `replies: ${JSON.stringify(rs)}\n${out.stderr}`);
    assert.equal(rs[0].op, 'ping'); assert.equal(rs[0].ok, true); assert.ok(rs[0].data.agentd.pid > 0);
    assert.ok(rs[0].in_reply_to !== JSON.parse(r.rows[0].content).id, 'the historical status request was not answered');
    assert.ok(!r.hits.some(h => h.startsWith('/api/ack')), 'no ack ever');
    assert.ok(r.hits.some(h => h.startsWith('/api/messages?') && h.includes('limit=1')), 'primed from the newest record');
    assert.ok(r.hits.some(h => h.startsWith('/api/wait?') && h.includes('since_id=id-1')), 'waited after it');
  } finally { r.close(); }
});

test('agentd --once: a request from a non-operator, an unknown op and an expired one get no reply; keys carry no value', async () => {
  const r = relay([['develop-qzapp/user', request({ op: 'ping', id: 'primer' })]]);
  await r.listen();
  try {
    r.waiting().then(() => {
      r.add('develop-qzapp/backend-dev-01', request({ op: 'ping', from: 'develop-qzapp/backend-dev-01' }));
      r.add('develop-qzapp/user', request({ op: 'rm -rf' }));
      r.add('develop-qzapp/user', request({ op: 'ping', ts: new Date(Date.now() - 3600000).toISOString() }));
      r.add('develop-qzapp/user', request({ op: 'keys', to: 'develop-qzapp/nobody' }));
      r.add('develop-qzapp/user', request({ op: 'keys' }));
    });
    const out = await runOnce(r.url());
    assert.equal(out.status, 0, out.stderr);
    const rs = replies(r);
    assert.equal(rs.length, 1, JSON.stringify(rs));
    assert.equal(rs[0].op, 'keys');
    assert.match(out.stderr, /ignored a record "from develop-qzapp\/backend-dev-01 is not an operator"/, out.stderr);
    assert.match(out.stderr, /ignored a record "op rm -rf"/); assert.match(out.stderr, /ignored a record "expired"/);
    assert.ok(!/not for me|not a request/.test(out.stderr), `the quiet refusals stay quiet:\n${out.stderr}`);
    const k = rs[0].data.keys.find(x => x.name === 'OPENROUTER_API_KEY');
    assert.equal(k.present, true); assert.equal(k.sha256_12.length, 12);
    assert.ok(!JSON.stringify(rs).includes('sk-or-secret-value'), 'no key value in a reply');
  } finally { r.close(); }
});

// The keys probe asks git for the signing key and gpg for its secret.
// The runner's GIT_CONFIG_GLOBAL, XDG_CONFIG_HOME and GNUPGHOME are set
// hostile here; a gpg that records how it was asked sits first on PATH.
// The positive control: the scratch HOME's own ~/.gitconfig naming a key
// does reach that gpg, with no GNUPGHOME, so silence in the first run is
// the environment kept out, not a recorder never reached.
test('agentd --once: the keys probe reads the scratch HOME, never the runner\'s git config or keyring', async () => {
  const hostile = scratch('agentd-hostile-');
  fs.writeFileSync(path.join(hostile, 'gitconfig'), '[user]\n\tsigningkey = HOSTILEKEY\n');
  fs.mkdirSync(path.join(hostile, 'xdg', 'git'), { recursive: true });
  fs.writeFileSync(path.join(hostile, 'xdg', 'git', 'config'), '[user]\n\tsigningkey = HOSTILEKEY\n');
  const bin = scratch('agentd-gpg-');
  const asked = path.join(bin, 'asked');
  fs.writeFileSync(path.join(bin, 'gpg'), `#!/bin/sh\necho "GNUPGHOME=\${GNUPGHOME-unset} $*" >> "${asked}"\nexit 2\n`, { mode: 0o755 });
  const saved = Object.fromEntries(['GIT_CONFIG_GLOBAL', 'XDG_CONFIG_HOME', 'GNUPGHOME'].map(k => [k, process.env[k]]));
  Object.assign(process.env, { GIT_CONFIG_GLOBAL: path.join(hostile, 'gitconfig'), XDG_CONFIG_HOME: path.join(hostile, 'xdg'), GNUPGHOME: hostile });
  const keysOnce = async home => {
    const r = relay([['develop-qzapp/user', request({ op: 'ping', id: 'primer' })]]);
    await r.listen();
    try {
      r.waiting().then(() => r.add('develop-qzapp/user', request({ op: 'keys' })));
      const out = await runOnce(r.url(), { PATH: `${bin}:${process.env.PATH}`, ...(home ? { HOME: home } : {}) });
      assert.equal(out.status, 0, out.stderr);
      assert.equal(replies(r).length, 1, out.stderr);
      return replies(r)[0];
    } finally { r.close(); }
  };
  try {
    const reply = await keysOnce();
    assert.deepEqual(reply.data.keys.at(-1), { name: SIGNING_ROW, present: false });
    assert.ok(!fs.existsSync(asked), `gpg was asked under the runner's config: ${fs.existsSync(asked) && fs.readFileSync(asked, 'utf8')}`);
    const home = scratchHome();
    fs.writeFileSync(path.join(home, '.gitconfig'), '[user]\n\tsigningkey = SCRATCHKEY\n');
    await keysOnce(home);
    assert.equal(fs.readFileSync(asked, 'utf8'), 'GNUPGHOME=unset --list-secret-keys --with-colons -- SCRATCHKEY\n');
  } finally {
    for (const [k, v] of Object.entries(saved)) if (v === undefined) delete process.env[k]; else process.env[k] = v;
  }
});

// disk walks a whole home: it answers beside the read loop, so a request
// behind it — a sender's presence question waits seconds — is not held.
test('agentd --once: a slow disk answers beside the loop; a ping sent after it is answered first', async () => {
  const bin = scratch('agentd-du-');
  fs.writeFileSync(path.join(bin, 'du'), '#!/bin/sh\nsleep 3\nfor a in "$@"; do case "$a" in -*) ;; *) printf "7\\t%s\\0" "$a";; esac; done\n', { mode: 0o755 });
  const r = relay([['develop-qzapp/user', request({ op: 'ping', id: 'primer' })]]);
  await r.listen();
  try {
    r.waiting().then(() => { r.add('develop-qzapp/user', request({ op: 'disk' })); r.add('develop-qzapp/user', request({ op: 'ping' })); });
    const out = await runOnce(r.url(), { PATH: `${bin}:${process.env.PATH}` });
    assert.equal(out.status, 0, out.stderr);
    const rs = replies(r);
    assert.deepEqual(rs.map(x => x.op), ['ping', 'disk'], `the ping was not held behind the disk:\n${out.stderr}`);
    assert.equal(rs[1].ok, true);
    assert.ok(rs[1].data.disk.total_kb > 0 && Array.isArray(rs[1].data.disk.largest), JSON.stringify(rs[1].data.disk));
  } finally { r.close(); }
});

// Review of #92, round 4: one scan per daemon, shared by every request that
// arrives while it runs — any placed account may post the read unsigned.
test('agentd --once: three disk requests share one scan, and each is answered', async () => {
  const bin = scratch('agentd-du-');
  const count = path.join(bin, 'calls');
  fs.writeFileSync(path.join(bin, 'du'), `#!/bin/sh\necho x >> ${JSON.stringify(count)}\nsleep 2\nfor a in "$@"; do case "$a" in -*) ;; *) printf "7\\t%s\\0" "$a";; esac; done\n`, { mode: 0o755 });
  const r = relay([['develop-qzapp/user', request({ op: 'ping', id: 'primer' })]]);
  await r.listen();
  try {
    r.waiting().then(() => { for (let i = 0; i < 3; i++) r.add('develop-qzapp/user', request({ op: 'disk' })); });
    const out = await runOnce(r.url(), { PATH: `${bin}:${process.env.PATH}` });
    assert.equal(out.status, 0, out.stderr);
    const rs = replies(r).filter(x => x.op === 'disk');
    assert.equal(rs.length, 3, `every request answered:\n${out.stderr}`);
    assert.ok(rs.every(x => x.ok && x.data.disk.total_kb > 0), JSON.stringify(rs.map(x => x.data)));
    const calls = fs.readFileSync(count, 'utf8').trim().split('\n').length;
    assert.ok(calls <= 2, `one scan (at most two du: the entries and projects/), not one per request: ${calls}`);
  } finally { r.close(); }
});

test('agentd --once: an empty channel is primed with an up record; a cleared history (since_id_not_found) re-primes instead of spinning', async () => {
  const r = relay();
  await r.listen();
  try {
    // The relay's history is cleared while the daemon waits: the wait comes
    // back with the warning, the daemon primes again (a second limit=1
    // read, a second up record) and waits after the new id.
    r.waiting().then(() => { r.rows.length = 0; });
    const out = await runOnce(r.url());
    assert.equal(out.status, 0, out.stderr);
    assert.equal(r.rows.length, 1, JSON.stringify(r.rows)); assert.equal(JSON.parse(r.rows[0].content).kind, 'up');
    const primes = r.hits.filter(h => h.startsWith('/api/messages?') && h.includes('limit=1'));
    assert.equal(primes.length, 2, `primed once at start and once after the warning: ${r.hits.join(' ')}`);
    const waits = r.hits.filter(h => h.startsWith('/api/wait?'));
    assert.ok(waits.length >= 2 && waits.length <= 3, `one wait per prime, no spin: ${waits.join(' ')}`);
    assert.ok(waits[waits.length - 1].includes(`since_id=${r.rows[0].id}`), 'the last wait follows the new up record');
  } finally { r.close(); }
});

test('agentd --once: a memory request is answered with the report and then the bundle in parts under the relay\'s limit, reassembling to the harvester\'s bytes', async () => {
  const payload = crypto.randomBytes(200 * 1024);   // ~267 KB of base64: three parts at 90 KiB
  const bin = fakeHarvester(payload);
  const home = scratchHome();
  const wc = path.join(home, 'projects', 'gzapp'); fs.mkdirSync(wc, { recursive: true });
  const mem = path.join(home, '.claude', 'projects', memorySlug(wc), 'memory'); fs.mkdirSync(mem, { recursive: true }); fs.writeFileSync(path.join(mem, 'a.md'), 'x');
  const r = relay([['develop-qzapp/user', request({ op: 'ping', id: 'primer' })]]);
  await r.listen();
  try {
    r.waiting().then(() => r.add('develop-qzapp/user', request({ op: 'memory' })));
    const out = await new Promise(resolve => {
      const child = spawn('node', [AGENTD, '--once'], { env: { ...process.env, HOME: home, PATH: `${bin}:${process.env.PATH}`, CLAUDE_BRIDGE_URL: r.url(), FABRIC_CONTROL_CHANNEL: 'test:control' } });
      let stderr = ''; child.stderr.on('data', d => { stderr += d; });
      const t = setTimeout(() => child.kill('SIGKILL'), 30000);
      child.on('close', status => { clearTimeout(t); resolve({ status, stderr }); });
    });
    assert.equal(out.status, 0, out.stderr);
    const rs = replies(r);
    assert.equal(rs.length, 4, `one report record and three parts: ${rs.map(x => Object.keys(x.data)).join(' | ')}\n${out.stderr}`);
    const [first, ...parts] = rs;
    assert.equal(first.data.parts, 3); assert.equal(first.data.memory.bundles.length, 1);
    const b = first.data.memory.bundles[0];
    assert.equal(b.status, 'ok'); assert.equal(b.parts, 3); assert.equal(b.bytes, payload.length); assert.equal(b.working_copy, wc);
    assert.deepEqual(b.report, { claims: 4, counts: { in_scope: 5, total: 5 }, needs_rendering: ['ka-1'], skipped_no_roles_class: [] });
    assert.deepEqual(parts.map(p => p.data.part.part), [1, 2, 3], 'in order');
    assert.ok(parts.every(p => p.data.part.parts === 3 && p.data.part.slug === b.slug && p.in_reply_to === first.in_reply_to));
    for (const row of r.rows) assert.ok(row.content.length < 128 * 1024, `every record under the relay's limit: ${row.content.length}`);
    const tar = zlib.gunzipSync(Buffer.from(parts.map(p => p.data.part.chunk).join(''), 'base64'));
    assert.deepEqual(tar, payload); assert.equal(crypto.createHash('sha256').update(tar).digest('hex'), b.sha256);
  } finally { r.close(); }
});

test('agentd: a registry with no operator is a refusal to start, not a silent daemon', async () => {
  const r = relay();
  await r.listen();
  try {
    const out = await runOnce(r.url(), { AGENT_FABRIC_HOSTS_REGISTRY: '/nonexistent/registry.json' });
    assert.equal(out.status, 3, out.stderr);
    assert.match(out.stderr, /no host operator/);
    assert.equal(r.hits.length, 0, 'the relay was never contacted');
  } finally { r.close(); }
});

test('agentd --once: a refused token is re-read from the synced file once, then reported', async () => {
  const hits = [];
  const server = http.createServer((req, res) => { hits.push(req.headers.authorization); res.statusCode = 401; res.setHeader('content-type', 'application/json'); res.end('{}'); });
  await new Promise(r => server.listen(0, '127.0.0.1', r));
  try {
    const out = await runOnce(`http://127.0.0.1:${server.address().port}`, { CLAUDE_BRIDGE_AUTH_TOKEN: 'tok-stale' });
    assert.equal(out.status, 4, out.stderr);
    assert.match(out.stderr, /refused this token/);
    assert.ok(hits.includes('Bearer tok-fixture'), `the synced value was tried: ${hits}`);
  } finally { server.closeAllConnections(); server.close(); }
});

test('accountsKeeper: the timer and a request share one reading; the cache answers inside its window; a failed read does not jam the next', async () => {
  let clock = 0, reads = 0, release;
  const gate = () => new Promise(r => { release = r; });
  let fail = false;
  const k = accountsKeeper(async () => { reads++; if (fail) throw new Error('harness gone'); await gate(); return { status: 'ok', n: reads }; }, { now: () => clock, cacheMs: 1000 });
  const a = k.refresh(), b = k.cached();
  await new Promise(r => setImmediate(r));
  release();
  const [ra, rb] = await Promise.all([a, b]);
  assert.equal(reads, 1, 'a timer tick and a request arriving together start one harness run');
  assert.equal(ra, rb);
  clock = 500;
  assert.equal((await k.cached()).n, 1, 'inside the window: the last reading, no new run');
  assert.equal(reads, 1);
  clock = 1500;
  const c = k.cached(); await new Promise(r => setImmediate(r)); release();
  assert.equal((await c).n, 2, 'past the window: a new reading');
  fail = true;
  await assert.rejects(k.refresh(), /harness gone/);
  fail = false;
  const d = k.refresh(); await new Promise(r => setImmediate(r)); release();
  assert.equal((await d).n, 4, 'the failed run released the slot');
  assert.ok(ACCOUNTS_KEEPALIVE_MS < 8 * 3600 * 1000 / 1.5, 'the keeper reads well inside the 8-hour sign-in');
});

test('agentd --once: a signed upgrade already started is waited for — its reply is posted before the process exits', async () => {
  const me = whoami();
  const k = generateOperatorKey();
  const reg = path.join(scratch('agentd-reg-'), 'registry.json');
  fs.writeFileSync(reg, JSON.stringify({ hosts: { [me.host]: { operator: me.agent, operator_key: k.publicKeySpec } }, placement: {} }));
  const home = scratchHome();
  fs.mkdirSync(path.join(home, '.local', 'bin'), { recursive: true });
  // A slow harness already at the target: the action takes seconds and installs nothing.
  fs.writeFileSync(path.join(home, '.local', 'bin', 'claude'), '#!/bin/sh\nsleep 2\necho "9.9.9 (Claude Code)"\n', { mode: 0o755 });
  const r = relay([]);
  await r.listen();
  try {
    r.waiting().then(() => r.add(`${me.host}/${me.agent}`, JSON.stringify(signRequest({ v: 1, kind: 'request', id: newId(), from: `${me.host}/${me.agent}`, to: '*', op: 'upgrade', args: { piece: 'claude', version: '9.9.9' }, ts: new Date().toISOString(), ttl_s: 60 }, k.privateKeySpec))));
    const out = await new Promise(resolve => {
      const child = spawn('node', [AGENTD, '--once'], { env: { ...process.env, HOME: home, CLAUDE_BRIDGE_URL: r.url(), FABRIC_CONTROL_CHANNEL: 'test:control', AGENT_FABRIC_HOSTS_REGISTRY: reg, AGENT_FABRIC_STATE_DIR: path.join(home, 'state') } });
      let stderr = ''; child.stderr.on('data', d => { stderr += d; });
      const t = setTimeout(() => child.kill('SIGKILL'), 20000);
      child.on('close', status => { clearTimeout(t); resolve({ status, stderr }); });
    });
    assert.equal(out.status, 0, out.stderr);
    const rs = replies(r).filter(x => x.op === 'upgrade');
    assert.equal(rs.length, 1, `the action's reply was posted before exit\n${out.stderr}`);
    assert.deepEqual([rs[0].data.upgrade.status, rs[0].data.upgrade.version], ['current', '9.9.9']);
    // The ledger the daemon wrote, read back: the action's own timestamp.
    const ledgerFile = path.join(home, 'state', 'agents', me.agent, 'actions-seen.json');
    const signedRec = r.rows.find(x => { try { return JSON.parse(x.content).op === 'upgrade' && JSON.parse(x.content).kind === 'request'; } catch { return false; } });
    const sent = JSON.parse(signedRec.content);
    assert.equal(JSON.parse(fs.readFileSync(ledgerFile, 'utf8'))[sent.from], Date.parse(sent.ts), 'the daemon recorded the action in its ledger');
    // A new daemon (a restart: its in-memory LRU is empty) is shown the same signed record again: refused, no second reply.
    // After the NEW daemon's first wait (r.waiting() already resolved on the first run's).
    const waitsBefore = r.hits.filter(h => h.startsWith('/api/wait?')).length;
    const newWait = () => new Promise(res => { const t = () => r.hits.filter(h => h.startsWith('/api/wait?')).length > waitsBefore ? res() : setTimeout(t, 20); t(); });
    newWait().then(() => r.add(sent.from, signedRec.content));
    const again = await new Promise(resolve => {
      const child = spawn('node', [AGENTD, '--once'], { env: { ...process.env, HOME: home, CLAUDE_BRIDGE_URL: r.url(), FABRIC_CONTROL_CHANNEL: 'test:control', AGENT_FABRIC_HOSTS_REGISTRY: reg, AGENT_FABRIC_STATE_DIR: path.join(home, 'state') } });
      let stderr = ''; child.stderr.on('data', d => { stderr += d; });
      const t = setTimeout(() => child.kill('SIGKILL'), 20000);
      child.on('close', status => { clearTimeout(t); resolve({ status, stderr }); });
    });
    assert.equal(replies(r).filter(x => x.op === 'upgrade').length, 1, `a replay after a restart got a reply\n${again.stderr}`);
    assert.match(again.stderr, /not newer than the last action accepted .* \(a replay\)/);
  } finally { r.close(); }
});

test('agentd --once: an action whose ledger cannot be written is refused by name, not blamed on the relay', async () => {
  const me = whoami();
  const k = generateOperatorKey();
  const reg = path.join(scratch('agentd-reg-'), 'registry.json');
  fs.writeFileSync(reg, JSON.stringify({ hosts: { [me.host]: { operator: me.agent, operator_key: k.publicKeySpec } }, placement: {} }));
  const home = scratchHome();
  const state = path.join(home, 'state');
  fs.mkdirSync(state, { recursive: true });
  fs.writeFileSync(path.join(state, 'agents'), 'not a directory');   // the ledger's directory cannot be made
  const r = relay([]);
  await r.listen();
  try {
    r.waiting().then(() => r.add(`${me.host}/${me.agent}`, JSON.stringify(signRequest({ v: 1, kind: 'request', id: newId(), from: `${me.host}/${me.agent}`, to: '*', op: 'upgrade', args: { piece: 'claude', version: '9.9.9' }, ts: new Date().toISOString(), ttl_s: 60 }, k.privateKeySpec))));
    const out = await new Promise(resolve => {
      const child = spawn('node', [AGENTD, '--once'], { env: { ...process.env, HOME: home, CLAUDE_BRIDGE_URL: r.url(), FABRIC_CONTROL_CHANNEL: 'test:control', AGENT_FABRIC_HOSTS_REGISTRY: reg, AGENT_FABRIC_STATE_DIR: state } });
      let stderr = ''; child.stderr.on('data', d => { stderr += d; });
      const t = setTimeout(() => child.kill('SIGKILL'), 20000);
      child.on('close', status => { clearTimeout(t); resolve({ status, stderr }); });
    });
    assert.match(out.stderr, /upgrade for .* refused: the action ledger could not be written \(ENOTDIR\)/);
    assert.doesNotMatch(out.stderr, /relay unreachable/);
    assert.equal(replies(r).filter(x => x.op === 'upgrade').length, 0, 'nothing ran');
  } finally { r.close(); }
});

test('leaving for new code waits for every running action to reply, then exits once', () => {
  const inflight = new Set(['a', 'b']);
  const exits = [], logs = [];
  const l = leaver({ inflight, exit: c => exits.push(c), log: m => logs.push(m) });
  assert.equal(l.settle(), false, 'nothing asked to leave: an action finishing never exits');
  assert.equal(l.request('source changed'), false); assert.deepEqual(exits, [], 'two actions still running: not yet');
  inflight.delete('a'); assert.equal(l.settle(), false); assert.deepEqual(exits, []);
  assert.equal(l.request('the fabric moved (upgrade fabric)'), false);
  inflight.delete('b'); assert.equal(l.settle(), true);
  assert.deepEqual(exits, [0]);
  assert.match(logs[0], /agentd: source changed; exiting/, 'the first reason is the one said');
  const idle = leaver({ inflight: new Set(), exit: c => exits.push(c), log: () => {} });
  assert.equal(idle.request('source changed'), true, 'nothing running: leaves at once, as at the base');
});
