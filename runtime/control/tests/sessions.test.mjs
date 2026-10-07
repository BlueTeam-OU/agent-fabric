// What agentd says about its account's sessions (sessions.mjs): which
// entries of the hook's file are live, when a record is posted, and that a
// failed post is retried rather than lost.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { scratch } from '../../../tests/scratch.mjs';
import { alive, readSessions, stateRecord, stateWatcher } from '../sessions.mjs';

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
  assert.equal(alive(null, null, proc), true, 'no process recorded: kept');
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
