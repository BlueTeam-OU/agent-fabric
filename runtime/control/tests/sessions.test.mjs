// What agentd says about its account's sessions (sessions.mjs): which
// entries of the hook's file are live, when a record is posted, and that a
// failed post is retried rather than lost.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { scratch } from '../../../tests/scratch.mjs';
import { alive, NO_PROCESS_FRESH_MS, readSessions, stateRecord, stateWatcher, transcriptExists, waitsOn } from '../sessions.mjs';

function fakeProc(dir, pid, start, comm = 'claude') {
  fs.mkdirSync(path.join(dir, String(pid)), { recursive: true });
  // Field 22 is the start time; a comm may hold spaces and parentheses.
  const fields = ['S', '1', ...Array(17).fill('0'), String(start), '0', '0'];
  fs.writeFileSync(path.join(dir, String(pid), 'stat'), `${pid} (${comm}) ${fields.join(' ')}\n`);
}

function setup() {
  const d = scratch('sessions-');
  const proc = path.join(d, 'proc');
  fakeProc(proc, 100, 5000);
  fakeProc(proc, 200, 6000, 'cla (u) de');
  const file = path.join(d, 'session-state.json');
  const write = sessions => fs.writeFileSync(file, JSON.stringify({ sessions }));
  return { d, proc, file, write };
}

test('a process is alive only while it is the one the hook recorded', () => {
  const { proc } = setup();
  assert.equal(alive(100, 5000, proc), true);
  assert.equal(alive(100, 5001, proc), false, 'a reused pid is not the session');
  assert.equal(alive(200, 6000, proc), true, 'a comm with a parenthesis');
  assert.equal(alive(300, 1, proc), false, 'a gone process');
  const now = Date.parse('2026-10-08T12:00:00Z');
  assert.equal(alive(null, null, proc, { since: '2026-10-08T11:45:00Z', now }), true, 'no process recorded, fresh: kept');
  assert.equal(alive(null, null, proc, { since: new Date(now - NO_PROCESS_FRESH_MS).toISOString(), now }), true,
    '…to the edge of two heartbeats');
  assert.equal(alive(null, null, proc, { since: new Date(now - NO_PROCESS_FRESH_MS - 1000).toISOString(), now }), false,
    'no process recorded, older than two heartbeats: not believed');
  assert.equal(alive(null, null, proc, { since: 'never', now }), false, 'a since that is not a time: not believed');
});

test('an entry with no process is left out once stale, and the watcher says so once, naming it', async () => {
  const { proc, file, write } = setup();
  const now = Date.parse('2026-10-08T12:00:00Z');
  write({
    probe: { state: 'idle', since: '2026-10-08T11:00:00Z', pid: null, start: null },
    young: { state: 'idle', since: '2026-10-08T11:59:00Z' },
  });
  const stale = [];
  assert.deepEqual(readSessions(file, { proc, now, onStale: id => stale.push(id) }),
    [{ session: 'young', state: 'idle', since: '2026-10-08T11:59:00Z' }]);
  assert.deepEqual(stale, ['probe']);
  const logs = [];
  let t = now;
  const w = stateWatcher({ address: 'h/x', post: async () => {}, file, proc, now: () => t, heartbeatMs: 1, log: m => logs.push(m) });
  await w.tick(); t += 5; await w.tick();
  assert.deepEqual(logs.filter(m => m.includes('probe')),
    ['agentd: session probe records no process and its state is older than 20 min; left out']);
});

test('readSessions keeps live sessions in a known state, sorted, without the process', () => {
  const { proc, file, write } = setup();
  assert.deepEqual(readSessions(file, { proc }), [], 'no file: none');
  fs.writeFileSync(file, '{broken'); assert.deepEqual(readSessions(file, { proc }), [], 'unreadable: none');
  write({
    b: { state: 'working', since: 't1', pid: 100, start: 5000 },
    a: { state: 'blocked', since: 't2', pid: 200, start: 6000 },
    dead: { state: 'idle', since: 't3', pid: 300, start: 1 },
    reused: { state: 'idle', since: 't4', pid: 100, start: 4999 },
    odd: { state: 'sleeping', since: 't5', pid: 100, start: 5000 },
  });
  assert.deepEqual(readSessions(file, { proc }), [
    { session: 'a', state: 'blocked', since: 't2' },
    { session: 'b', state: 'working', since: 't1' },
  ]);
});

test('the watcher posts at start, on a change, and on the heartbeat; nothing in between', async () => {
  const { d, proc, file, write } = setup();
  const binding = path.join(d, 'binding.json');
  // The binding's other fields (a path, the harness pid) never leave; its
  // session id does, as a key of the hook's file (ADR-029 rule 16 names it).
  fs.writeFileSync(binding, JSON.stringify({ role: 'backend-dev', project: 'gzapp', session: 's', working_copy: '/home/x/projects/private-wc', pid: 31337 }));
  const posts = [];
  let t = 1_000_000;
  const w = stateWatcher({ address: 'h/x', post: async r => { posts.push(r); }, file, binding, proc, now: () => t, heartbeatMs: 60_000, log: () => {} });
  assert.equal(await w.tick(), true, 'the first tick says what there is');
  assert.deepEqual(posts[0], { v: 1, kind: 'state', from: 'h/x', ts: new Date(t).toISOString(), sessions: [], role: 'backend-dev', project: 'gzapp' });
  t += 2000; assert.equal(await w.tick(), false, 'nothing changed: nothing posted');
  write({ s: { state: 'working', since: 'x', pid: 100, start: 5000 } });
  t += 2000; assert.equal(await w.tick(), true, 'a new session');
  assert.deepEqual(posts[1].sessions, [{ session: 's', state: 'working', since: 'x' }]);
  fs.rmSync(path.join(proc, '100'), { recursive: true });
  t += 2000; assert.equal(await w.tick(), true, 'its process died: said, with no SessionEnd');
  assert.deepEqual(posts[2].sessions, []);
  fs.writeFileSync(binding, JSON.stringify({ role: 'web-dev', project: 'gzapp' }));
  t += 2000; assert.equal(await w.tick(), true, 'a rebind is a change');
  t += 59_000; assert.equal(await w.tick(), false);
  t += 2000; assert.equal(await w.tick(), true, 'the heartbeat re-says it');
  assert.equal(posts.length, 5);
  const said = JSON.stringify(posts);
  assert.ok(!said.includes('private-wc') && !said.includes('31337') && !said.includes('"pid"') && !said.includes('"start"') && !said.includes('5000'),
    'no path, no binding field but role and project, no process id or start time');
});

test('a failed post is retried on the next tick and said once', async () => {
  const { file, proc } = setup();
  const logs = [], posts = [];
  let fail = 2;
  const w = stateWatcher({ address: 'h/x', post: async r => { if (fail-- > 0) throw new Error('relay down'); posts.push(r); }, file, proc, log: m => logs.push(m) });
  assert.equal(await w.tick(), false);
  assert.equal(await w.tick(), false);
  assert.equal(await w.tick(), true, 'posted once the relay is back');
  assert.equal(posts.length, 1);
  assert.equal(logs.length, 2, `one line down, one back: ${logs}`);
});

test('a tick while a post is in flight does nothing', async () => {
  const { file, proc } = setup();
  let release; const gate = new Promise(r => { release = r; });
  let calls = 0;
  const w = stateWatcher({ address: 'h/x', post: async () => { calls++; await gate; }, file, proc, log: () => {} });
  const first = w.tick();
  assert.equal(await w.tick(), false);
  release(); assert.equal(await first, true);
  assert.equal(calls, 1);
});

test('waits_on: the message ids of blocked jobs only, sorted, never a title', async () => {
  const { d, proc, file } = setup();
  const jobs = path.join(d, 'jobs.json');
  const A = '01a11a18-4728-7d8b-afd9-0edb2d30a59c', B = '01a11a19-0bea-70c7-b667-1e1e5a74dbe1';
  assert.deepEqual(waitsOn(jobs), [], 'no list: none');
  fs.writeFileSync(jobs, '{broken'); assert.equal(waitsOn(jobs), null, 'unreadable: unknown, never none');
  fs.writeFileSync(jobs, '{"jobs": 3}'); assert.equal(waitsOn(jobs), null, 'not a job list: unknown');
  fs.writeFileSync(jobs, JSON.stringify({ jobs: [
    { id: 'j1', state: 'blocked', title: 'secret title', waits_on: B },
    { id: 'j2', state: 'blocked', title: 'x', waits_on: A },
    { id: 'j3', state: 'queued', title: 'x', waits_on: '01a11a20-0000-7000-8000-000000000000' },
    { id: 'j4', state: 'blocked', title: 'x', waits_on: 'not an id; rm -rf' },
    { id: 'j5', state: 'blocked', title: 'x', blocked_on: 'a reply' },
    { id: 'j6', state: 'blocked', title: 'x', waits_on: A }] }));
  assert.deepEqual(waitsOn(jobs), [A, B], 'blocked, well-formed, de-duplicated, sorted');
  const posts = [];
  let t = 0;
  const w = stateWatcher({ address: 'h/x', post: async r => { posts.push(r); }, file, jobs, proc, now: () => t, heartbeatMs: 60_000, log: () => {} });
  await w.tick();
  assert.deepEqual(posts.at(-1).waits_on, [A, B]);
  assert.ok(!JSON.stringify(posts).includes('secret title') && !JSON.stringify(posts).includes('"j1"'), 'no title, no job id');
  fs.writeFileSync(jobs, JSON.stringify({ jobs: [{ id: 'j1', state: 'active', title: 'x', waits_on: B }] }));
  t = 1; assert.equal(await w.tick(), true, 'a job unblocked is a change');
  assert.ok(!('waits_on' in posts.at(-1)), 'waiting on nothing: the key is absent');
});

test('an unreadable job list keeps the waits_on last said, and is logged once', async () => {
  const { d, proc, file } = setup();
  const jobs = path.join(d, 'jobs.json');
  const A = '01a11a18-4728-7d8b-afd9-0edb2d30a59c';
  fs.writeFileSync(jobs, JSON.stringify({ jobs: [{ id: 'j1', state: 'blocked', title: 'x', waits_on: A }] }));
  const posts = [], logs = [];
  let t = 0;
  const w = stateWatcher({ address: 'h/x', post: async r => { posts.push(r); }, file, jobs, proc, now: () => t, heartbeatMs: 60_000, log: m => logs.push(m) });
  await w.tick();
  fs.writeFileSync(jobs, '{broken');
  t = 61_000; await w.tick(); t = 122_000; await w.tick();
  assert.deepEqual(posts.map(p => p.waits_on), [[A], [A], [A]], 'never said as waiting on nothing');
  assert.equal(logs.filter(m => m.includes('cannot be read')).length, 1);
  fs.rmSync(jobs);
  t = 123_000; assert.equal(await w.tick(), true);
  assert.ok(!('waits_on' in posts.at(-1)), 'no list at all waits on nothing');
});

test('stateRecord leaves out a role and project it does not have', () => {
  assert.deepEqual(stateRecord('h/x', { sessions: [], role: null, project: null }, 't'), { v: 1, kind: 'state', from: 'h/x', ts: 't', sessions: [] });
});

test('agentd posts state records on the state channel, never the control channel', async () => {
  const { statePoster, controlConfig } = await import('../agentd.mjs');
  const sent = [];
  const cfg = controlConfig({});
  await statePoster(async (p, init) => { sent.push({ p, body: JSON.parse(init.body) }); return {}; }, cfg, 'h/x')({ v: 1, kind: 'state' });
  assert.equal(sent[0].p, '/api/send');
  assert.equal(sent[0].body.channel, 'fabric:state:control');
  assert.notEqual(sent[0].body.channel, cfg.channel);
  assert.equal(controlConfig({ FABRIC_STATE_CHANNEL: 't:state:control' }).state_channel, 't:state:control');
});

test('the record carries the last session id and whether it can be resumed, never where (Fleet Deck)', async () => {
  const { d, proc, file, write } = setup();
  const cfg = path.join(d, 'claude');
  const id = '0f0e0d0c-1111-4222-8333-444455556666';
  const binding = path.join(d, 'binding.json');
  fs.writeFileSync(binding, JSON.stringify({ role: 'python-dev', project: 'agent-fabric', session: id,
    working_copy: '/home/x/projects/private-wc' }));
  write({});
  const posts = [];
  let t = 0;
  const w = stateWatcher({ address: 'h/x', post: async r => { posts.push(r); }, file, binding, proc,
    now: () => t, heartbeatMs: 60_000, log: () => {}, configDir: cfg });
  await w.tick();
  assert.equal(posts.at(-1).last_session, id);
  assert.equal(posts.at(-1).resumable, false, 'no transcript yet');
  fs.mkdirSync(path.join(cfg, 'projects', '-home-x-projects'), { recursive: true });
  fs.writeFileSync(path.join(cfg, 'projects', '-home-x-projects', `${id}.jsonl`), '{}\n');
  t = 1; await w.tick();
  assert.equal(posts.at(-1).resumable, true, 'the transcript appeared: posted as a change');
  assert.ok(!JSON.stringify(posts).includes('private-wc') && !JSON.stringify(posts).includes('-home-x-projects'),
    'no path leaves the account');
  // Planted where an unchecked id would reach it: projects/<dir>/../../etc/x.jsonl.
  fs.mkdirSync(path.join(cfg, 'etc'), { recursive: true });
  fs.writeFileSync(path.join(cfg, 'etc', 'x.jsonl'), '{}\n');
  assert.equal(transcriptExists('../../etc/x', cfg), false, 'an id that is not one is never looked up');
  for (const bad of ['../../etc/x', 'abc\u001b]0;t\u0007def', 42]) {
    fs.writeFileSync(binding, JSON.stringify({ role: 'python-dev', project: 'agent-fabric', session: bad }));
    t += 1; await w.tick();
    assert.ok(!('last_session' in posts.at(-1)) && !('resumable' in posts.at(-1)), `a binding session ${JSON.stringify(bad)} is no session`);
  }
  assert.deepEqual(stateRecord('h/x', { sessions: [], role: null, project: null, last_session: null }, 't'),
    { v: 1, kind: 'state', from: 'h/x', ts: 't', sessions: [] }, 'no last session: neither field');
});
