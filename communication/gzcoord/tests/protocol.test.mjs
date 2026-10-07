import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { spawnSync } from 'node:child_process';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const gzmsg = (...args) =>
  spawnSync(fileURLToPath(new URL('../../../bin/gzmsg', import.meta.url)), args,
            { encoding: 'utf8' });

test('validate CLI reports a bad first line on one line and exits 1', () => {
  const file = new URL('./bad-first-line.tmp.txt', import.meta.url);
  fs.writeFileSync(file, 'GZCOORD/1 INFO\nFROM: develop-gzapp/gzapp\nROLE: Tester\nPROJECT: gzapp\nMESSAGE-ID: test-0001\nBROADCAST: true\n');
  try {
    const bad = gzmsg('validate', fileURLToPath(file));
    assert.equal(bad.status, 1);
    // The LAST line: a tool may say something else first — a login whose
    // locale is pinned away is told so — and an assertion that forbids any
    // other line is testing the absence of diagnostics, not this behaviour.
    assert.equal(bad.stderr.trim().split('\n').pop(), 'invalid GZCOORD/1 first line');
    assert.equal(bad.stdout, '');
  } finally { fs.unlinkSync(file); }
});

test('validate prints the line-length warning on stderr and still passes the message', () => {
  const file = new URL('./long-line.tmp.txt', import.meta.url);
  fs.writeFileSync(file, `[GZCOORD/1] INFO\nFROM: develop-gzapp/gzapp\nROLE: Tester\nPROJECT: gzapp\nMESSAGE-ID: test-0001\nBROADCAST: true\nSPECIALTIES: ${'z'.repeat(80)}\n`);
  try {
    const ok = gzmsg('validate', '--no-taxonomy', fileURLToPath(file));
    assert.equal(ok.status, 0, ok.stderr);
    assert.match(ok.stderr, /^warning: line 7 is 93 columns wide/m);
    assert.equal(ok.stdout, 'valid GZCOORD/1 message\n');
  } finally { fs.unlinkSync(file); }
});

test('new-id CLI mints; next-id is gone; --seed is refused', () => {
  const a = gzmsg('new-id');
  assert.equal(a.status, 0, a.stderr);
  assert.match(a.stdout.trim(), /^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
  const b = gzmsg('next-id');
  assert.equal(b.status, 2, 'the counter-era name is an unknown command, not an alias');
  assert.match(b.stderr, /usage:/);
  // new-id declares no flags at all, so the generic unknown-flag refusal
  // fires before the retired-flag message is reachable.
  {
    const r = gzmsg('new-id', '--seed', '9');
    assert.equal(r.status, 2);
    assert.match(r.stderr, /unknown flag --seed/);
  }
});

test('CLI: an unknown flag is refused before any side effect', () => {
  const dir = scratch('gzcoord-flags-');
  try {
    const typo = gzmsg('new-id', '--seeed', '9');
    assert.equal(typo.status, 2);
    assert.match(typo.stderr, /unknown flag --seeed/);
    assert.equal(typo.stdout, '');
    const peek = gzmsg('new-id', '--peek');
    assert.equal(peek.status, 2, 'the counter-era flag is unknown on new-id');
    assert.match(peek.stderr, /unknown flag --peek/);
    assert.equal(peek.stdout, '');
    const retired = gzmsg('hello', '--no-taxonomy', '--from', 'develop-gzapp/web', '--role', 'R', '--project', 'p');
    assert.equal(retired.status, 2, 'hello is no longer a command');
    assert.match(retired.stderr, /^usage: gzmsg validate/);
    assert.equal(retired.stdout, '');
    const file = path.join(dir, 'm.txt'); fs.writeFileSync(file, '[GZCOORD/1] INFO\nFROM: a/b\nROLE: R\nPROJECT: p\nMESSAGE-ID: b-0001\nBROADCAST: true\n');
    const v = gzmsg('validate', file, '--nope');
    assert.equal(v.status, 2);
    assert.match(v.stderr, /unknown flag --nope/);
    // and the declared paths are untouched
    assert.equal(gzmsg('validate', file, '--no-taxonomy').status, 0);
    assert.match(gzmsg('new-id').stdout.trim(), /^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab]/, 'the declared path mints');
  } finally { fs.rmSync(dir, { recursive: true, force: true }); }
});

// gzcoord-send is the other half of the inbox: same identity, same relay,
// same token resolution. It validates last, refuses a FROM that is not
// this login's address, and posts exactly {channel, sender, content}.
import http from 'node:http';
import { execFile, spawn } from 'node:child_process';
import { scratch } from '../../../tests/scratch.mjs';
const SEND = fileURLToPath(new URL('../../../bin/gzcoord-send', import.meta.url));
function withRelay(fn) {
  const posts = [];
  const server = http.createServer((req, res) => {
    let body = ''; req.on('data', c => body += c); req.on('end', () => {
      posts.push({ url: req.url, auth: req.headers.authorization, body: JSON.parse(body || '{}') });
      res.setHeader('content-type', 'application/json'); res.end(JSON.stringify({ seq: 42, id: 'relay-id', deduplicated: false }));
    });
  });
  return new Promise((resolve, reject) => server.listen(0, '127.0.0.1', async () => {
    try { resolve(await fn(`http://127.0.0.1:${server.address().port}`, posts)); } catch (e) { reject(e); } finally { server.close(); }
  }));
}
// A scratch secrets store holding an agent id: send keeps every message in
// the sender's episodic journal (ADR-041), and a journal has an owner. Its
// own directory, never HOME — one test makes the message's directory
// read-only.
const AGENT_ID = '01a0f782-7e06-7dee-811f-0a860ed93bf3';
function idStore() {
  const d = scratch('send-store-'); fs.writeFileSync(path.join(d, '.agent-id'), `${AGENT_ID}\n`); return d;
}
// Asynchronous on purpose: the stub relay lives in this process, and a
// synchronous exec would block the event loop the server answers on.
function sendWith(relay, text, extra = [], moreEnv = {}) {
  const f = path.join(scratch('send-'), 'm.txt'); fs.writeFileSync(f, text);
  // HOME is a scratch dir: the runner's own synced secrets.env must not be the token here.
  // The state dir too: send records every id it sends, and a test must never write that record into the runner's own.
  const env = { ...process.env, HOME: path.dirname(f), AGENT_FABRIC_STATE_DIR: path.join(path.dirname(f), 'state'), AGENT_FABRIC_SECRET_STORE: idStore(), CLAUDE_BRIDGE_URL: relay, CLAUDE_BRIDGE_AUTH_TOKEN: 'tok-fixture', GZCOORD_CHANNEL: 'fixture:chan', ...moreEnv };
  return new Promise(resolve => execFile(SEND, [f, ...extra], { env, encoding: 'utf8' },
    (e, out, err) => resolve({ code: e ? e.code : 0, out: String(out), err: String(err) })));
}
// The login's address, from the one place that derives it — what
// gzmsg's whoami() asked, asked by the fixture now that the tools
// are Python behind these command paths (ADR-040 §7).
function whoami() {
  const r = spawnSync('python3', [fileURLToPath(new URL('../../../runtime/identity.py', import.meta.url)), '--json'], { encoding: 'utf8' });
  if (r.status !== 0) throw new Error(`runtime/identity.py --json failed: ${r.stderr}`);
  return JSON.parse(r.stdout);
}
const ME = whoami();
const MY_ADDRESS = `${ME.host}/${ME.agent}`;
const valid = `[GZCOORD/1] INFO\nFROM: ${MY_ADDRESS}\nROLE: backend-dev\nPROJECT: fixture\nBROADCAST: true\nMESSAGE-ID: 01a09fc1-0000-7000-8000-000000000001\nSUBJECT: fixture\n\nNOTES:\nhello\n`;

test('send posts a valid message as this login, to the configured channel', async () => {
  await withRelay(async (relay, posts) => {
    const r = await sendWith(relay, valid);
    assert.equal(r.code, 0, r.err);
    assert.match(r.out, /^sent seq 42 INFO 01a09fc1-0000-7000-8000-000000000001/);
    assert.equal(posts.length, 1);
    assert.equal(posts[0].url, '/api/send');
    assert.equal(posts[0].auth, 'Bearer tok-fixture');
    assert.deepEqual(Object.keys(posts[0].body).sort(), ['channel', 'content', 'sender']);
    assert.equal(posts[0].body.sender, MY_ADDRESS);
    assert.equal(posts[0].body.channel, 'fixture:chan');
    assert.equal(posts[0].body.content, valid);
  });
});

// The episodic journal (ADR-041): the message is kept before the post and
// marked with its outcome after; a journal that cannot take it stops the send.
function journalRows(state, store) {
  const py = process.env.AGENT_FABRIC_PYTHON || '/usr/local/bin/fabric-python';
  const r = spawnSync(py, ['-c', `import sqlite3,json,sys
sys.path.insert(0, sys.argv[1]); import episodic
c = sqlite3.connect(episodic.db_path())
print(json.dumps(c.execute("SELECT direction, state, message_id, carrier_seq, content FROM episodes ORDER BY recorded_at").fetchall()))`,
    fileURLToPath(new URL('../../../tools/fabric', import.meta.url))],
    { encoding: 'utf8', env: { ...process.env, AGENT_FABRIC_STATE_DIR: state, AGENT_FABRIC_SECRET_STORE: store } });
  assert.equal(r.status, 0, r.stderr);
  return JSON.parse(r.stdout);
}
test('send keeps the message in its journal before posting, and marks it accepted with the relay seq', async () => {
  await withRelay(async (relay, posts) => {
    const state = path.join(scratch('send-journal-'), 'state'); const store = idStore();
    const r = await sendWith(relay, valid, [], { AGENT_FABRIC_STATE_DIR: state, AGENT_FABRIC_SECRET_STORE: store });
    assert.equal(r.code, 0, r.err);
    assert.deepEqual(journalRows(state, store), [['outbound', 'accepted', '01a09fc1-0000-7000-8000-000000000001', 42, valid]]);
    assert.equal(posts.length, 1);
  });
});
test('a journal that cannot take the message stops the send: nothing posted, exit 2, said', async () => {
  await withRelay(async (relay, posts) => {
    const r = await sendWith(relay, valid, [], { AGENT_FABRIC_SECRET_STORE: scratch('send-no-id-') });
    assert.equal(r.code, 2, r.err);
    assert.match(r.err, /no agent id/);
    assert.match(r.err, /not sent: a message is kept before it leaves/);
    assert.equal(posts.length, 0, 'the carrier never saw it');
    const off = await sendWith(relay, valid, [], { AGENT_FABRIC_SECRET_STORE: scratch('send-no-id-'), GZCOORD_JOURNAL: 'off' });
    assert.equal(off.code, 0, off.err);
    assert.match(off.err, /GZCOORD_JOURNAL=off — this message is sent without being kept/);
    assert.equal(posts.length, 1, 'the explicit bypass sends, and says so');
  });
});
test('a post the relay refuses leaves the journal row failed, not accepted, and says it was refused, not unreachable', async () => {
  const server = http.createServer((req, res) => { res.statusCode = 409; res.end('{}'); });
  await new Promise(r => server.listen(0, '127.0.0.1', r));
  try {
    const state = path.join(scratch('send-journal-fail-'), 'state'); const store = idStore();
    const r = await sendWith(`http://127.0.0.1:${server.address().port}`, valid, [], { AGENT_FABRIC_STATE_DIR: state, AGENT_FABRIC_SECRET_STORE: store });
    assert.equal(r.code, 3, r.err);
    assert.match(r.err, /answered and refused it .* not sent/); assert.doesNotMatch(r.err, /unreachable/);
    assert.deepEqual(journalRows(state, store).map(x => x.slice(0, 3)), [['outbound', 'failed', '01a09fc1-0000-7000-8000-000000000001']]);
  } finally { server.closeAllConnections(); server.close(); }
});

test('a post whose answer cannot be read (a 5xx) leaves the row pending and says it may have been delivered; a refused connection is not sent', async () => {
  const server = http.createServer((req, res) => { res.statusCode = 503; res.end('{}'); });
  await new Promise(r => server.listen(0, '127.0.0.1', r));
  try {
    const state = path.join(scratch('send-journal-5xx-'), 'state'); const store = idStore();
    const r = await sendWith(`http://127.0.0.1:${server.address().port}`, valid, [], { AGENT_FABRIC_STATE_DIR: state, AGENT_FABRIC_SECRET_STORE: store });
    assert.equal(r.code, 3, r.err);
    assert.match(r.err, /may have been delivered/); assert.doesNotMatch(r.err, /not sent/);
    assert.deepEqual(journalRows(state, store).map(x => x.slice(0, 3)), [['outbound', 'pending', '01a09fc1-0000-7000-8000-000000000001']]);
  } finally { server.closeAllConnections(); server.close(); }
  // A port nothing listens on: the connection is refused, the relay never saw it.
  const closed = http.createServer(); await new Promise(r => closed.listen(0, '127.0.0.1', r));
  const port = closed.address().port; await new Promise(r => closed.close(r));
  const state = path.join(scratch('send-journal-refused-'), 'state'); const store = idStore();
  const r = await sendWith(`http://127.0.0.1:${port}`, valid, [], { AGENT_FABRIC_STATE_DIR: state, AGENT_FABRIC_SECRET_STORE: store });
  assert.equal(r.code, 3, r.err); assert.match(r.err, /relay unreachable .* not sent/);
  assert.deepEqual(journalRows(state, store).map(x => x.slice(0, 3)), [['outbound', 'failed', '01a09fc1-0000-7000-8000-000000000001']]);
});

test('a failed retransmission leaves a row pending whose earlier outcome was never written (review of #78)', async () => {
  const server = http.createServer((req, res) => { res.statusCode = 500; res.end('{}'); });
  await new Promise(r => server.listen(0, '127.0.0.1', r));
  try {
    const state = path.join(scratch('send-journal-unknown-'), 'state'); const store = idStore();
    const env = { ...process.env, AGENT_FABRIC_STATE_DIR: state, AGENT_FABRIC_SECRET_STORE: store };
    // An earlier send that died after its post: a pending row and no outcome.
    const py = process.env.AGENT_FABRIC_PYTHON || '/usr/local/bin/fabric-python';
    const first = spawnSync(py, [fileURLToPath(new URL('../../../tools/fabric/episodic.py', import.meta.url)), 'gzcoord-out-pending'],
      { encoding: 'utf8', env, input: valid });
    assert.deepEqual([first.status, first.stdout.trim()], [0, 'pending'], first.stderr);
    const r = await sendWith(`http://127.0.0.1:${server.address().port}`, valid, [], { AGENT_FABRIC_STATE_DIR: state, AGENT_FABRIC_SECRET_STORE: store });
    assert.equal(r.code, 3, r.err);
    assert.match(r.err, /may have reached the relay; its row stays pending/);
    assert.deepEqual(journalRows(state, store).map(x => x.slice(0, 3)), [['outbound', 'pending', '01a09fc1-0000-7000-8000-000000000001']]);
  } finally { server.closeAllConnections(); server.close(); }
});

// A message with no MESSAGE-ID gets one from the sender, written into the
// file before it posts, so a retry of the same file carries the same id
// (SPEC §7.2) — and the command on screen is the message that goes out.
function sendFile(relay, f, extra = [], state = path.join(path.dirname(f), 'state')) {
  const env = { ...process.env, HOME: path.dirname(f), AGENT_FABRIC_STATE_DIR: state, AGENT_FABRIC_SECRET_STORE: idStore(), CLAUDE_BRIDGE_URL: relay, CLAUDE_BRIDGE_AUTH_TOKEN: 'tok-fixture', GZCOORD_CHANNEL: 'fixture:chan' };
  return new Promise(resolve => execFile(SEND, [f, ...extra], { env, encoding: 'utf8' },
    (e, out, err) => resolve({ code: e ? e.code : 0, out: String(out), err: String(err) })));
}
const noId = valid.replace(/^MESSAGE-ID: .*\n/m, '');
const idOf = text => /^MESSAGE-ID: (.+)$/m.exec(text)?.[1];

test('send mints a missing MESSAGE-ID, writes it into the file, and a retry of the file sends the same id', async () => {
  await withRelay(async (relay, posts) => {
    const f = path.join(scratch('send-mint-'), 'm.txt'); fs.writeFileSync(f, noId);
    const r = await sendFile(relay, f);
    assert.equal(r.code, 0, r.err);
    const id = idOf(fs.readFileSync(f, 'utf8'));
    assert.match(id, /^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/, 'a UUIDv7, the deployment\'s own shape');
    assert.match(r.out, new RegExp(`^sent seq 42 INFO ${id}`));
    assert.match(r.err, /minted .* and wrote it into/);
    assert.equal(idOf(posts[0].body.content), id, 'the posted message carries the id the file now holds');
    assert.ok(/^SUBJECT: fixture$/m.test(posts[0].body.content) && posts[0].body.content.indexOf('MESSAGE-ID:') < posts[0].body.content.indexOf('\n\n'), 'the id sits in the metadata block');
    const again = await sendFile(relay, f);
    assert.equal(again.code, 0, again.err);
    assert.equal(idOf(posts[1].body.content), id, 'the retry sends the same id');
    assert.doesNotMatch(again.err, /minted/, 'nothing is minted the second time');
  });
});

test('a dry run mints in memory only; stdin is said to keep nothing; a present id is kept; a placeholder is still refused', async () => {
  await withRelay(async (relay, posts) => {
    const f = path.join(scratch('send-mint-dry-'), 'm.txt'); fs.writeFileSync(f, noId);
    const dry = await sendFile(relay, f, ['--dry-run']);
    assert.equal(dry.code, 0, dry.err);
    assert.equal(fs.readFileSync(f, 'utf8'), noId, 'the dry run changed nothing');
    assert.match(dry.err, /would mint one \(dry run/);
    const env = { ...process.env, HOME: path.dirname(f), AGENT_FABRIC_STATE_DIR: path.join(path.dirname(f), 'state'), AGENT_FABRIC_SECRET_STORE: idStore(), CLAUDE_BRIDGE_URL: relay, CLAUDE_BRIDGE_AUTH_TOKEN: 'tok-fixture', GZCOORD_CHANNEL: 'fixture:chan' };
    const piped = await new Promise(resolve => { const c = execFile(SEND, ['-'], { env, encoding: 'utf8' }, (e, out, err) => resolve({ code: e ? e.code : 0, out, err })); c.stdin.end(noId); });
    assert.equal(piped.code, 0, piped.err);
    assert.match(piped.err, /from stdin it is kept nowhere/);
    const kept = await sendWith(relay, valid);
    assert.match(kept.out, /01a09fc1-0000-7000-8000-000000000001/);
    assert.doesNotMatch(kept.err, /minted/);
    const placeholder = await sendWith(relay, valid.replace(/^MESSAGE-ID: .*$/m, 'MESSAGE-ID: MSGID'));
    assert.equal(placeholder.code, 2);
    assert.match(placeholder.err, /MSGID.*not sent/);
  });
});

test('an id that already went out with another message is refused — a reused file does not send its new message under the old id', async () => {
  await withRelay(async (relay, posts) => {
    const dir = scratch('send-reuse-'); const f = path.join(dir, 'm.txt'); const state = path.join(dir, 'state');
    fs.writeFileSync(f, noId);
    const first = await sendFile(relay, f, [], state);
    assert.equal(first.code, 0, first.err);
    const again = await sendFile(relay, f, [], state);
    assert.equal(again.code, 0, 'the same message again is a retry, and passes');
    fs.writeFileSync(f, fs.readFileSync(f, 'utf8').replace('hello', 'a different message'));
    const reused = await sendFile(relay, f, [], state);
    assert.equal(reused.code, 2);
    assert.match(reused.err, /already went out with a different message \(seq 42\).*delete the MESSAGE-ID line/);
    assert.equal(posts.length, 2, 'the reused-id message was not posted');
    fs.writeFileSync(f, fs.readFileSync(f, 'utf8').replace(/^MESSAGE-ID: .*\n/m, ''));
    const fresh = await sendFile(relay, f, [], state);
    assert.equal(fresh.code, 0, fresh.err);
    assert.notEqual(idOf(fs.readFileSync(f, 'utf8')), idOf(posts[0].body.content), 'deleting the line mints a new id');
  });
});

test('a header send cannot parse is refused by the validator (exit 2), never a crash; a file that cannot be rewritten is refused unchanged and not posted', async () => {
  await withRelay(async (relay, posts) => {
    const bad = await sendWith(relay, 'GZCOORD INFO\nFROM: a/b\n\nNOTES:\nx\n');
    assert.equal(bad.code, 2, bad.err); assert.match(bad.err, /does not validate/);
    const dir = scratch('send-ro-'); const f = path.join(dir, 'm.txt'); fs.writeFileSync(f, noId);
    fs.chmodSync(dir, 0o555);
    try {
      if (process.getuid && process.getuid() === 0) return;   // root writes anywhere: nothing to show
      const r = await sendFile(relay, f, [], path.join(scratch('send-ro-state-'), 'state'));
      assert.equal(r.code, 1); assert.match(r.err, /could not write the minted MESSAGE-ID/);
      assert.equal(fs.readFileSync(f, 'utf8'), noId, 'the file is unchanged');
      assert.deepEqual(fs.readdirSync(dir), ['m.txt'], 'no temporary left');
      assert.equal(posts.length, 0);
    } finally { fs.chmodSync(dir, 0o755); }
  });
});

// Presence before sending (runtime/control/presence.mjs): a relay stub that
// answers `presence` requests on the control channel from a fixture table,
// and a registry that places the addressees.
function withPresenceRelay(answers, fn) {
  const posts = []; const asked = [];
  const server = http.createServer((req, res) => {
    res.setHeader('content-type', 'application/json');
    if (req.method === 'GET') {
      const u = new URL(req.url, 'http://x');
      const messages = u.searchParams.get('channel') === 'fabric:control' ? asked.flatMap(r => (r.to === '*' ? Object.keys(answers) : r.to).filter(a => answers[a]).map((a, i) =>
        ({ id: `${r.id}-${i}`, content: JSON.stringify({ kind: 'reply', in_reply_to: r.id, from: a, data: { presence: answers[a] } }) }))) : [];
      return res.end(JSON.stringify({ messages }));
    }
    let body = ''; req.on('data', c => body += c); req.on('end', () => {
      const b = JSON.parse(body || '{}');
      if (b.channel === 'fabric:control') { asked.push(JSON.parse(b.content)); return res.end(JSON.stringify({ id: 'ctl', seq: 1 })); }
      posts.push({ url: req.url, body: b }); res.end(JSON.stringify({ seq: 42, id: 'relay-id', deduplicated: false }));
    });
  });
  const reg = path.join(scratch('presence-reg-'), 'hosts.json');
  fs.writeFileSync(reg, JSON.stringify({ version: 1, hosts: { h: { operator: 'user' } }, placement: { alpha: 'h', beta: 'h', gamma: 'h' } }));
  return new Promise((resolve, reject) => server.listen(0, '127.0.0.1', async () => {
    try { resolve(await fn(`http://127.0.0.1:${server.address().port}`, posts, asked, { AGENT_FABRIC_HOSTS_REGISTRY: reg, GZCOORD_PRESENCE_WAIT_MS: '1200' })); }
    catch (e) { reject(e); } finally { server.closeAllConnections(); server.close(); }
  }));
}
const addressed = field => valid.replace('BROADCAST: true', field).replace('[GZCOORD/1] INFO', '[GZCOORD/1] OBSERVATION');
const failedRead = { status: 'failed', error: 'pgrep: spawn pgrep ENOENT' };
const up = role => ({ status: 'ok', online: true, sessions: 1, since: '2026-09-25T09:00:00.000Z', role, project: 'gzapp' });
const down = role => ({ status: 'ok', online: false, sessions: 0, since: null, role, project: 'gzapp' });

test('an addressee that is planning: sent, and the sender told its inbox is held until the plan is approved', async () => {
  await withPresenceRelay({ 'h/alpha': { ...up('web-dev'), planning: true } }, async (relay, posts, asked, env) => {
    const r = await sendWith(relay, addressed('TO: h/alpha'), [], env);
    assert.equal(r.code, 0, r.err);
    assert.match(r.err, /h\/alpha is planning — its inbox is held until the plan is approved; the message waits in the relay, and no answer comes before then/);
    assert.equal(posts.length, 1, 'planning never blocks the send');
  });
});

test('send checks presence first: a running addressee is sent to; one with no session, a silent agent or an unplaced address is refused, named, unless --force', async () => {
  await withPresenceRelay({ 'h/alpha': up('web-dev'), 'h/beta': down('web-dev') }, async (relay, posts, asked, env) => {
    const ok = await sendWith(relay, addressed('TO: h/alpha'), [], env);
    assert.equal(ok.code, 0, ok.err); assert.equal(posts.length, 1, 'sent');
    assert.deepEqual([asked[0].op, asked[0].to, asked[0].from], ['presence', ['h/alpha'], MY_ADDRESS]);
    const offline = await sendWith(relay, addressed('TO: h/beta'), [], env);
    assert.equal(offline.code, 4, offline.err);
    assert.match(offline.err, /h\/beta has no session running[\s\S]*not sent — --force sends it anyway/);
    assert.equal(posts.length, 1, 'nothing posted for an addressee with no session');
    const silent = await sendWith(relay, addressed('TO: h/gamma'), [], env);
    assert.equal(silent.code, 4); assert.match(silent.err, /h\/gamma's control agent did not answer within 1\.2 s/);
    const stranger = await sendWith(relay, addressed('TO: other/nobody'), [], env);
    assert.equal(stranger.code, 4); assert.match(stranger.err, /other\/nobody is not an account any host places/);
    const forced = await sendWith(relay, addressed('TO: h/beta'), ['--force'], env);
    assert.equal(forced.code, 0, forced.err); assert.match(forced.err, /sending anyway \(--force\)/);
    assert.equal(posts.length, 2, '--force sends it');
  });
});

test('a dry run posts nothing, not even a presence request; a refused token is the post\'s to report', async () => {
  await withPresenceRelay({ 'h/beta': down('web-dev') }, async (relay, posts, asked, env) => {
    const dry = await sendWith(relay, addressed('TO: h/beta'), ['--dry-run'], env);
    assert.equal(dry.code, 0, dry.err); assert.match(dry.err, /would post/);
    assert.deepEqual([posts.length, asked.length], [0, 0], 'no record of any kind (review of #38)');
  });
  const hits = [];
  const server = http.createServer((req, res) => { hits.push(`${req.method} ${req.url.split('?')[0]}`); res.statusCode = 401; res.end('{}'); });
  await new Promise(r => server.listen(0, '127.0.0.1', r));
  try {
    const reg = path.join(scratch('presence-reg-'), 'hosts.json');
    fs.writeFileSync(reg, JSON.stringify({ version: 1, hosts: { h: { operator: 'user' } }, placement: { alpha: 'h' } }));
    const r = await sendWith(`http://127.0.0.1:${server.address().port}`, addressed('TO: h/alpha'), [], { AGENT_FABRIC_HOSTS_REGISTRY: reg, GZCOORD_PRESENCE_WAIT_MS: '800' });
    assert.equal(r.code, 3, r.err); assert.match(r.err, /refused/); assert.doesNotMatch(r.err, /presence is unknown/);
    assert.match(r.err, /presence not asked — the relay refused the token in hand/, 'the skipped check is said, never silent');
    assert.equal(hits.filter(h => h === 'POST /api/send').length, 2, 'the presence request, then the post itself — which owns the token refusal');
  } finally { server.closeAllConnections(); server.close(); }
});

test('an addressee whose control agent could not tell is named as unknown, never as having no session', async () => {
  await withPresenceRelay({ 'h/alpha': failedRead }, async (relay, posts, asked, env) => {
    const r = await sendWith(relay, addressed('TO: h/alpha'), [], env);
    assert.equal(r.code, 4, r.err); assert.match(r.err, /presence is unknown \(h\/alpha: pgrep: spawn pgrep ENOENT\)/);
    assert.doesNotMatch(r.err, /has no session running/); assert.equal(posts.length, 0);
  });
});

test('send to a role: reached when any holder runs; a broadcast asks nothing', async () => {
  await withPresenceRelay({ 'h/alpha': down('web-dev'), 'h/beta': up('web-dev'), 'h/gamma': up('db-admin') }, async (relay, posts, asked, env) => {
    const r = await sendWith(relay, addressed('TO-ROLE: web-dev'), [], env);
    assert.equal(r.code, 0, r.err); assert.equal(asked[0].to, '*');
    const none = await sendWith(relay, addressed('TO-ROLE: flutter-dev'), [], env);
    assert.equal(none.code, 4); assert.match(none.err, /no account holds flutter-dev/);
    const n = asked.length;
    const b = await sendWith(relay, valid, [], env);
    assert.equal(b.code, 0, b.err); assert.equal(asked.length, n, 'a broadcast is not checked');
  });
});

test('send stops, named, when no integration is configured — nothing is posted anywhere', async () => {
  await withRelay(async (relay, posts) => {
    const f = path.join(scratch('send-'), 'm.txt'); fs.writeFileSync(f, valid);
    // Outside any working copy, with no channel in the environment: whoami()
    // reports whatever project the runner's binding names; the fixture
    // strips the environment and points the fabric at an empty root so no
    // project file can be found.
    const emptyFabric = scratch('fabric-');
    const env = { ...process.env, HOME: path.dirname(f), CLAUDE_BRIDGE_URL: relay, CLAUDE_BRIDGE_AUTH_TOKEN: 'tok', AGENT_FABRIC_ROOT: emptyFabric };
    delete env.GZCOORD_CHANNEL;
    const r = await new Promise(resolve => execFile(SEND, [f], { env, encoding: 'utf8', cwd: emptyFabric },
      (e, out, err) => resolve({ code: e ? e.code : 0, out: String(out), err: String(err) })));
    assert.equal(r.code, 3, r.err);
    assert.match(r.err, /no GZCoord integration configured/);
    assert.match(r.err, /not sent/);
    assert.equal(posts.length, 0);
  });
});

test('send refuses a message that does not validate, and posts nothing', async () => {
  await withRelay(async (relay, posts) => {
    // Two addresses at once (SPEC §7.1). A missing MESSAGE-ID was the
    // example here until the sender began minting one.
    const r = await sendWith(relay, valid.replace('BROADCAST: true', 'BROADCAST: true\nTO-ROLE: backend-dev'));
    assert.equal(r.code, 2); assert.match(r.err, /not sent/); assert.equal(posts.length, 0);
  });
});

test('send refuses an id the deployment did not mint — the literal $ID reached the channel once', async () => {
  await withRelay(async (relay, posts) => {
    const r = await sendWith(relay, valid.replace('MESSAGE-ID: 01a09fc1-0000-7000-8000-000000000001', 'MESSAGE-ID: $ID'));
    assert.equal(r.code, 2); assert.match(r.err, /MESSAGE-ID is the literal \$ID — the shell variable was not expanded/); assert.match(r.err, /not sent/); assert.equal(posts.length, 0);
    // ONCE: the complaint is also the refusal, and send suppresses the
    // duplicate warning. That suppression matched its own English until a
    // translated warning silently stopped matching, and nothing counted —
    // so this counts (blind review, PR #28).
    assert.equal(r.err.match(/is the literal \$ID/g).length, 1, r.err);
    const reply = await sendWith(relay, valid.replace('SUBJECT: fixture', 'IN-REPLY-TO: ${PREV}\nSUBJECT: fixture'));
    assert.equal(reply.code, 2); assert.match(reply.err, /IN-REPLY-TO is the literal \$\{PREV\}/); assert.equal(posts.length, 0);
    // The retired counter shape is still an id: older traffic is answered by it.
    const old = await sendWith(relay, valid.replace('SUBJECT: fixture', 'IN-REPLY-TO: db-admin-0007\nSUBJECT: fixture'));
    assert.equal(old.code, 0, old.err); assert.equal(posts.length, 1);
  });
});

test('send refuses a FROM that is not this session', async () => {
  await withRelay(async (relay, posts) => {
    const r = await sendWith(relay, valid.replace(`FROM: ${MY_ADDRESS}`, 'FROM: other-host/someone'));
    assert.equal(r.code, 2); assert.match(r.err, /FROM is other-host\/someone but this session is/); assert.equal(posts.length, 0);
  });
});

test('send --dry-run validates and resolves but posts nothing', async () => {
  await withRelay(async (relay, posts) => {
    const r = await sendWith(relay, valid, ['--dry-run']);
    assert.equal(r.code, 0); assert.equal(posts.length, 0);
  });
});

test('send carries a long line as written, with no width warning (the bridge does not re-break)', async () => {
  await withRelay(async (relay, posts) => {
    const wide = valid.replace(/\n$/, '') + '\n' + 'a path or an id that is longer than seventy-two columns: /home/x/projects/agent-fabric/runtime/claude-code/hooks/plan-hold.sh\n';
    const r = await sendWith(relay, wide);
    assert.equal(r.code, 0, r.err);
    assert.ok(!/columns wide/.test(r.err), `no width warning on the send path: ${r.err}`);
    assert.equal(posts[0].body.content, wide, 'the line is posted as written');
  });
});

test('send reminds a session that fell back that the flagged text must not travel', async () => {
  await withRelay(async (relay, posts) => {
    const dir = scratch('fallback-');
    fs.writeFileSync(path.join(dir, `${process.pid}.json`), JSON.stringify({ session_id: 's', pid: process.pid, from_model: 'claude-opus-5[1m]', to_model: 'claude-opus-4-8', at: '2026-09-16T11:46:21Z', category: 'cyber', topic: 'a cybersecurity issue' }));
    const r = await sendWith(relay, valid, [], { AGENT_FABRIC_FALLBACK_DIR: dir, CLAUDE_PID: String(process.pid) });
    assert.equal(r.code, 0, r.err);
    assert.match(r.err, /send: reminder — this session fell back from claude-opus-5\[1m\] to claude-opus-4-8 at 2026-09-16T11:46:21Z/, 'the reminder names the switch');
    assert.match(r.err, /flagged a request as a cybersecurity issue; filter anything that could be read as a cybersecurity issue out of this message/);
    assert.equal(posts.length, 1, 'a reminder, not a refusal: the message is posted');
    // a marker whose session is gone is not a fallback
    fs.writeFileSync(path.join(dir, `${process.pid}.json`), JSON.stringify({ session_id: 's', pid: 4194304000, from_model: 'a', to_model: 'b' }));
    const r2 = await sendWith(relay, valid, [], { AGENT_FABRIC_FALLBACK_DIR: dir, CLAUDE_PID: String(process.pid) });
    assert.equal(r2.code, 0); assert.ok(!/reminder/.test(r2.err), r2.err);
  });
});

test('send normalizes a pasted, indented message before validating', async () => {
  await withRelay(async (relay, posts) => {
    const r = await sendWith(relay, valid.split('\n').map(l => l ? '    ' + l : l).join('\n'));
    assert.equal(r.code, 0, r.err); assert.equal(posts[0].body.content, valid);
  });
});

// A refused token is not "unreachable": the relay answered. The inbox
// says the token was rotated and exits 4, so a watch loop can stop.
test('inbox reports a refused token as a rotation, exit 4', async () => {
  const server = http.createServer((req, res) => { res.statusCode = 401; res.setHeader('connection', 'close'); res.end('{}'); });
  await new Promise(r => server.listen(0, '127.0.0.1', r));
  const INBOX = fileURLToPath(new URL('../../../bin/gzcoord-inbox', import.meta.url));
  const env = { ...process.env, HOME: scratch('home-'), AGENT_FABRIC_SECRET_STORE: idStore(), CLAUDE_BRIDGE_URL: `http://127.0.0.1:${server.address().port}`, CLAUDE_BRIDGE_AUTH_TOKEN: 'dead', GZCOORD_CHANNEL: 'fixture:chan' };
  const r = await new Promise(resolve => execFile(INBOX, ['--wait', '1'], { env, encoding: 'utf8' }, (e, out, err) => resolve({ code: e ? e.code : 0, err: String(err) })));
  server.closeAllConnections(); server.close();
  assert.equal(r.code, 4, r.err);
  assert.match(r.err, /refused this token \(HTTP 401\) — it was rotated; run bin\/fabric-secrets sync/);
});

// --replay re-reads one message without a consumer id (the cursor does
// not move) and shows a body only when the message is addressed to me.
test('inbox --replay shows a broadcast, withholds a body not for me, moves no cursor, and says so in --json', async () => {
  const mine = `[GZCOORD/1] INFO\nFROM: x/y\nROLE: backend-dev\nPROJECT: fixture\nBROADCAST: true\nMESSAGE-ID: 01a09fc1-0000-7000-8000-00000000000a\nSUBJECT: for all\n\nNOTES:\nBODY-FOR-ALL\n`;
  const theirs = `[GZCOORD/1] REPLY\nFROM: x/y\nROLE: backend-dev\nPROJECT: fixture\nTO: other-host/someone\nMESSAGE-ID: 01a09fc1-0000-7000-8000-00000000000b\nSUBJECT: private\n\nNOTES:\nBODY-PRIVATE\n`;
  const hits = [];
  const server = http.createServer((req, res) => {
    hits.push(req.url); res.setHeader('content-type', 'application/json'); res.setHeader('connection', 'close');
    res.end(JSON.stringify({ channel: 'fixture:chan', messages: [
      { seq: 7, id: 'r7', ts: 'T7', sender: 'x/y', content: mine }, { seq: 8, id: 'r8', ts: 'T8', sender: 'x/y', content: theirs }] }));
  });
  await new Promise(r => server.listen(0, '127.0.0.1', r));
  const INBOX = fileURLToPath(new URL('../../../bin/gzcoord-inbox', import.meta.url));
  const env = { ...process.env, HOME: scratch('home-'), AGENT_FABRIC_SECRET_STORE: idStore(), CLAUDE_BRIDGE_URL: `http://127.0.0.1:${server.address().port}`, CLAUDE_BRIDGE_AUTH_TOKEN: 'tok', GZCOORD_CHANNEL: 'fixture:chan' };
  const run = args => new Promise(resolve => execFile(INBOX, [...args], { env, encoding: 'utf8' }, (e, out, err) => resolve({ code: e ? e.code : 0, out: String(out), err: String(err) })));
  const a = await run(['--replay', '7']);
  const b = await run(['--replay', '01a09fc1-0000-7000-8000-00000000000b']);
  const c = await run(['--replay', '99']);
  const aj = await run(['--replay', '7', '--json']);
  const bj = await run(['--replay', '8', '--json']);
  server.closeAllConnections(); server.close();
  // --json, for fabric-jobs add --request: the same read, the same withholding.
  assert.equal(aj.code, 0, aj.err);
  const aDoc = JSON.parse(aj.out);
  assert.deepEqual([aDoc.addressed, aDoc.seq, aDoc.type, aDoc.metadata.SUBJECT], [true, 7, 'INFO', 'for all']);
  assert.match(aDoc.text, /BODY-FOR-ALL/);
  assert.equal(bj.code, 2); assert.deepEqual(JSON.parse(bj.out), { addressed: false, seq: 8 });
  assert.equal(a.code, 0, a.err); assert.match(a.out, /BODY-FOR-ALL/); assert.match(a.out, /cursor unchanged/);
  assert.equal(b.code, 2); assert.doesNotMatch(b.out, /BODY-PRIVATE/); assert.match(b.out, /not addressed to/);
  assert.equal(c.code, 1); assert.match(c.err, /no message 99/);
  // /status is ensureRelay's liveness probe; nothing names a consumer and nothing acks.
  assert.ok(hits.every(u => u === '/status' || (u.startsWith('/api/messages?') && !u.includes('consumer_id'))), hits);
  assert.ok(!hits.some(u => u.includes('/api/ack') || u.includes('/api/wait')), hits);
});

// --history lists what is addressed to me in one call, from a seq on,
// withholding what is not, reading no body into the listing and moving no cursor.
test('inbox --history lists the messages addressed to me, from a seq, and moves no cursor', async () => {
  const msg = (n, to, subject) => `[GZCOORD/1] INFO\nFROM: x/y\nROLE: backend-dev\nPROJECT: fixture\n${to}\nMESSAGE-ID: 01a09fc1-0000-7000-8000-00000000000${n}\nSUBJECT: ${subject}\n\nNOTES:\nBODY-${n}\n`;
  const hits = [];
  const server = http.createServer((req, res) => {
    hits.push(req.url); res.setHeader('content-type', 'application/json'); res.setHeader('connection', 'close');
    res.end(JSON.stringify({ channel: 'fixture:chan', messages: [
      { seq: 5, id: 'r5', ts: 'T5', sender: 'x/y', content: msg(5, 'BROADCAST: true', 'early') },
      { seq: 7, id: 'r7', ts: 'T7', sender: 'x/y', content: msg(7, 'BROADCAST: true', 'for all') },
      { seq: 8, id: 'r8', ts: 'T8', sender: 'x/y', content: msg(8, 'TO: other-host/someone', 'private') }] }));
  });
  await new Promise(r => server.listen(0, '127.0.0.1', r));
  const INBOX = fileURLToPath(new URL('../../../bin/gzcoord-inbox', import.meta.url));
  const env = { ...process.env, HOME: scratch('home-'), AGENT_FABRIC_SECRET_STORE: idStore(), CLAUDE_BRIDGE_URL: `http://127.0.0.1:${server.address().port}`, CLAUDE_BRIDGE_AUTH_TOKEN: 'tok', GZCOORD_CHANNEL: 'fixture:chan' };
  const run = args => new Promise(resolve => execFile(INBOX, [...args], { env, encoding: 'utf8' }, (e, out, err) => resolve({ code: e ? e.code : 0, out: String(out), err: String(err) })));
  const all = await run(['--history']);
  const from = await run(['--history', '6']);
  const bad = await run(['--history', 'x']);
  server.closeAllConnections(); server.close();
  assert.equal(all.code, 0, all.err);
  assert.match(all.out, /2 addressed to you in the relay's last 3/); assert.match(all.out, / 5 .*early/); assert.match(all.out, / 7 .*for all/);
  assert.doesNotMatch(all.out, /private|BODY-/); assert.match(all.out, /gzcoord-inbox --replay <seq>/);
  assert.equal(from.code, 0, from.err); assert.match(from.out, /1 addressed to you/); assert.doesNotMatch(from.out, /early/);
  assert.equal(bad.code, 1); assert.match(bad.err, /usage: inbox\.mjs --history/);
  assert.ok(hits.every(u => u === '/status' || (u.startsWith('/api/messages?') && !u.includes('consumer_id'))), hits);
  assert.ok(!hits.some(u => u.includes('/api/ack') || u.includes('/api/wait')), hits);
});

// The environment is a snapshot; the synced file is current. A refused
// token is retried once with the file's value, and that is what recovers
// a watch re-armed from a pre-rotation shell.
test('the synced file is the token; the environment snapshot is not consulted while it exists', async () => {
  const home = scratch('home-');
  fs.mkdirSync(path.join(home, '.config', 'agent-fabric'), { recursive: true });
  fs.writeFileSync(path.join(home, '.config', 'agent-fabric', 'secrets.env'), "# x\nexport CLAUDE_BRIDGE_AUTH_TOKEN='fresh-token'\n");
  const seen = [];
  const server = http.createServer((req, res) => {
    seen.push(req.headers.authorization); res.setHeader('connection', 'close'); res.setHeader('content-type', 'application/json');
    if (req.url === '/status') { res.end('{}'); return; }
    if (req.headers.authorization !== 'Bearer fresh-token') { res.statusCode = 401; res.end('{}'); return; }
    res.end(JSON.stringify({ messages: [], next_cursor: null }));
  });
  await new Promise(r => server.listen(0, '127.0.0.1', r));
  const INBOX = fileURLToPath(new URL('../../../bin/gzcoord-inbox', import.meta.url));
  const env = { ...process.env, HOME: home, AGENT_FABRIC_SECRET_STORE: idStore(), CLAUDE_BRIDGE_URL: `http://127.0.0.1:${server.address().port}`, CLAUDE_BRIDGE_AUTH_TOKEN: 'dead', GZCOORD_CHANNEL: 'fixture:chan' };
  const r = await new Promise(resolve => execFile(INBOX, ['--wait', '1'], { env, encoding: 'utf8' }, (e, out, err) => resolve({ code: e ? e.code : 0, out: String(out), err: String(err) })));
  server.closeAllConnections(); server.close();
  assert.equal(r.code, 0, r.err);
  assert.ok(seen.includes('Bearer fresh-token') && !seen.includes('Bearer dead'), seen);
  assert.doesNotMatch(r.err, /retrying/);
  assert.match(r.out + r.err, /nothing for you/);
});

// --follow is the watch: it blocks, prints a delivery as it lands, and
// does not return on a quiet spell. We cannot let it run forever in a
// test, so a stub relay returns one message then stalls; the child is
// killed after the message is observed.
test('inbox --follow prints a delivery and keeps running', async () => {
  const mine = `[GZCOORD/1] INFO\nFROM: x/y\nROLE: backend-dev\nPROJECT: fixture\nBROADCAST: true\nMESSAGE-ID: 01a09fc1-0000-7000-8000-00000000000f\nSUBJECT: live\n\nNOTES:\nFOLLOW-BODY\n`;
  let served = false;
  const server = http.createServer((req, res) => {
    res.setHeader('content-type', 'application/json'); res.setHeader('connection', 'close');
    if (req.url === '/status') { res.end('{}'); return; }
    if (req.url.startsWith('/api/wait')) {
      if (!served) { served = true; res.end(JSON.stringify({ messages: [{ seq: 5, id: 'r5', ts: 'T', sender: 'x/y', content: mine }], next_cursor: 'c' })); }
      else { /* stall: never respond, --follow keeps waiting */ }
      return;
    }
    res.end('{}');   // ack
  });
  await new Promise(r => server.listen(0, '127.0.0.1', r));
  const INBOX = fileURLToPath(new URL('../../../bin/gzcoord-inbox', import.meta.url));
  const env = { ...process.env, HOME: scratch('home-'), AGENT_FABRIC_SECRET_STORE: idStore(), CLAUDE_BRIDGE_URL: `http://127.0.0.1:${server.address().port}`, CLAUDE_BRIDGE_AUTH_TOKEN: 'tok', GZCOORD_CHANNEL: 'fixture:chan' };
  const child = spawn(INBOX, ['--follow'], { env });
  let out = '';
  const done = new Promise(resolve => {
    child.stdout.on('data', d => { out += d; if (out.includes('FOLLOW-BODY')) resolve(); });
    setTimeout(resolve, 8000);
  });
  await done;
  const stillRunning = child.exitCode === null;
  child.kill('SIGKILL'); server.closeAllConnections(); server.close();
  assert.match(out, /FOLLOW-BODY/, 'the delivery was printed');
  assert.ok(stillRunning, '--follow did not exit after the delivery');
});
