// What bin/fabric-jobs asks of the control plane to order a queue
// (queue.mjs): the waits read from the state stream.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { scratch } from '../../../tests/scratch.mjs';
import { waitsFrom, readWaits, askHolder, placedAccounts, Unreadable, unsent, relayError, QUEUE_CALL_TIMEOUT_MS, QUEUE_BUDGET_MS, boundCall, relay } from '../queue.mjs';

const A = '01a11a18-4728-7d8b-afd9-0edb2d30a59c', B = '01a11a19-0bea-70c7-b667-1e1e5a74dbe1';
const rec = (from, waits_on, extra = {}) => ({ content: JSON.stringify({ v: 1, kind: 'state', from, ts: '2026-10-08T12:00:00Z', sessions: [], ...(waits_on ? { waits_on } : {}), ...extra }) });
const NOW = Date.parse('2026-10-08T12:05:00Z');

test('waits: each placed account\'s newest record, its message ids, the waiters sorted', () => {
  const placed = new Set(['h/b', 'h/a', 'h/c']);
  const got = waitsFrom([
    rec('h/b', [A, B]),
    rec('h/a', [B]),
    rec('h/b', [A]),                       // newer than its first: B is no longer b's
    rec('h/c', ['not-an-id']),             // not agentd's shape: skipped whole
    rec('x/unplaced', [B]),                // not placed: skipped
    { content: '{broken' },
    rec('h/c', [B], { kind: 'reply' }),
  ], placed, NOW);
  assert.deepEqual(got, { waits: { [B]: ['h/a'], [A]: ['h/b'] }, accounts: 2, stale: {} });
});

test('a waiter whose record is older than the bound still waits, and is named stale with its age (ADR-037 rule 8)', () => {
  const placed = new Set(['h/a', 'h/b', 'h/c', 'h/d']);
  const got = waitsFrom([
    rec('h/a', [A], { ts: '2026-10-08T11:00:00Z' }),   // an hour old
    rec('h/b', [A]),                                  // five minutes: fresh
    rec('h/c', null, { ts: '2026-10-08T09:00:00Z' }),  // old, but waits on nothing
    rec('h/d', [B], { ts: 'yesterday' }),             // a ts that does not parse: age unknown
  ], placed, NOW);
  assert.deepEqual(got.waits, { [A]: ['h/a', 'h/b'], [B]: ['h/d'] }, 'counted all the same');
  assert.deepEqual(got.stale, { 'h/a': 3900, 'h/d': null });
  // The bound itself is fresh: exactly STATES_STALE_MS old is not stale.
  assert.deepEqual(waitsFrom([rec('h/a', [A], { ts: '2026-10-08T11:45:00Z' })], placed, NOW).stale, {});
});

test('a record without waits_on waits on nothing, and replaces an older one that did', () => {
  assert.deepEqual(waitsFrom([rec('h/a', [A]), rec('h/a', null)], new Set(['h/a']), NOW), { waits: {}, accounts: 1, stale: {} });
});

test('readWaits reads the state channel, never the control channel', async () => {
  const asked = [];
  const got = await readWaits({ call: async p => { asked.push(p); return { messages: [rec('h/a', [A])] }; },
    cfg: { channel: 'c:control', state_channel: 's:state:control' }, placed: new Set(['h/a']) });
  assert.match(asked[0], /channel=s%3Astate%3Acontrol/);
  assert.deepEqual(got.waits, { [A]: ['h/a'] });
});

// A relay with one channel: what is posted, and replies a test appends.
function channel(onRequest) {
  const rows = [];
  const call = async (p, init) => {
    if (init?.method === 'POST') {
      const body = JSON.parse(init.body);
      rows.push({ id: `m${rows.length + 1}`, content: body.content });
      const id = rows.at(-1).id;
      for (const reply of onRequest(JSON.parse(body.content))) rows.push({ id: `m${rows.length + 1}`, content: JSON.stringify(reply) });
      return { id };
    }
    const since = new URLSearchParams(p.split('?')[1]).get('since_id');
    return { messages: rows.slice(rows.findIndex(r => r.id === since) + 1) };
  };
  return { rows, call };
}
const cfg = { channel: 'c:control', state_channel: 's:state:control', ttl_s: 30 };
// The test process is no queue.mjs run: its budget is the test's to give.
const ALWAYS = () => 1e9;

test('askHolder: only the holder\'s reply to this request counts; a forged one is skipped', async () => {
  let sent;
  const { call } = channel(req => { sent = req; return [
    { v: 1, kind: 'reply', in_reply_to: req.id, from: 'h/forger', op: req.op, data: { 'pool-claim': { status: 'claimed', job: { id: 'p1' } } } },
    { v: 1, kind: 'reply', in_reply_to: 'other', from: 'h/user', op: req.op, data: { 'pool-claim': { status: 'claimed' } } },
    { v: 1, kind: 'reply', in_reply_to: req.id, from: 'h/user', op: req.op, data: { 'pool-claim': { status: 'refused', reason: 'no' } } }]; });
  const got = await askHolder({ call, cfg, from: 'h/py', holder: 'h/user', op: 'pool-claim', args: { id: 'p1' }, waitMs: 2000, left: ALWAYS });
  assert.deepEqual(got, { status: 'refused', reason: 'no' });
  assert.deepEqual([sent.to, sent.from, sent.args, sent.kind, sent.op], [['h/user'], 'h/py', { id: 'p1' }, 'request', 'pool-claim']);
  assert.equal(sent.ttl_s, 2, 'the request lives as long as the asker waits, not the channel\'s 30 s');
});

test('askHolder: a relay that fails after the request was posted says it was sent', async () => {
  let posted = false;
  const call = async (p, init) => { if (init?.method === 'POST') { posted = true; return { id: 'm1' }; } throw Object.assign(new Error('down'), { status: 502 }); };
  await assert.rejects(askHolder({ call, cfg, from: 'h/py', holder: 'h/user', op: 'pool-claim', args: { id: 'p1' }, waitMs: 500, left: ALWAYS }), e => e.sent === true && e.status === 502);
  assert.ok(posted);
  const refused = async () => { throw Object.assign(new Error('no'), { status: 403 }); };
  await assert.rejects(askHolder({ call: refused, cfg, from: 'h/py', holder: 'h/user', op: 'pool-claim', args: { id: 'p1' }, waitMs: 500, left: ALWAYS }), e => e.sent === undefined);
});

test('who is placed: an unreadable registry is an error, never nobody', () => {
  const d = scratch('queue-reg-');
  const reg = path.join(d, 'registry.json');
  assert.throws(() => placedAccounts(reg), Unreadable);
  fs.writeFileSync(reg, '{broken'); assert.throws(() => placedAccounts(reg), /cannot be read/);
  fs.writeFileSync(reg, '{}'); assert.throws(() => placedAccounts(reg), /no placement/);
  fs.writeFileSync(reg, JSON.stringify({ placement: { a: 'h', b: 'k' } }));
  assert.deepEqual([...placedAccounts(reg)], ['h/a', 'k/b']);
});

test('askHolder: a holder that does not answer is null, never an answer', async () => {
  const { call } = channel(() => []);
  assert.equal(await askHolder({ call, cfg, from: 'h/py', holder: 'h/user', op: 'pool-list', args: { role: 'python-dev' }, waitMs: 500, left: ALWAYS }), null);
});

test('unsent: only a refused or unconnected post certainly left nothing', () => {
  assert.equal(unsent({ status: 403 }), true);
  assert.equal(unsent({ cause: { code: 'ECONNREFUSED' } }), true);
  assert.equal(unsent({ status: 502 }), false, 'a 5xx may come after the write');
  assert.equal(unsent({ cause: { code: 'ECONNRESET' } }), false, 'a reset may come after the write');
  assert.equal(unsent(new Error('x')), false);
  assert.equal(unsent({ timedOut: true, message: '/api/send -> no answer within 30 s' }), false, 'a timed-out post may have been stored');
});

test('the run has one budget under jobs.py\'s kill, and every call takes at most what is left', async () => {
  const py = fs.readFileSync(new URL('../../../tools/fabric/jobs.py', import.meta.url), 'utf8');
  const outer = Number(py.match(/^QUEUE_TIMEOUT_S = (\d+)$/m)?.[1]);
  assert.ok(outer > 0 && QUEUE_BUDGET_MS <= outer * 1000 - 5000, `${QUEUE_BUDGET_MS} ms against ${outer} s, with room for node to start`);
  assert.ok(QUEUE_CALL_TIMEOUT_MS <= QUEUE_BUDGET_MS);
  const seen = [];
  const fake = (tok, p, opts) => seen.push(opts);
  boundCall('tok', { relay_url: 'http://r' }, fake, ALWAYS)('/api/send', { method: 'POST' });
  boundCall('tok', { relay_url: 'http://r' }, fake, () => 3000)('/x');
  assert.deepEqual(seen.map(o => o.timeoutMs), [QUEUE_CALL_TIMEOUT_MS, 3000]);
  assert.deepEqual(seen[0], { relayUrl: 'http://r', timeoutMs: QUEUE_CALL_TIMEOUT_MS, method: 'POST' });
  // A spent budget asks nothing, and says so: certainly unsent, never the relay's silence.
  await assert.rejects(boundCall('tok', { relay_url: 'http://r' }, fake, () => 0)('/api/send?x=1', { method: 'POST' }),
    e => e.budgetSpent === true && unsent(e) && relayError(e, { relay_url: 'http://r' }) === "/api/send: not asked, this run's 25 s budget is spent");
  assert.equal(seen.length, 2, 'no call made');
});

test('relay() itself: its calls go through the bound, with the token it resolved', () => {
  const env = { HOME: process.env.HOME, CLAUDE_BRIDGE_AUTH_TOKEN: process.env.CLAUDE_BRIDGE_AUTH_TOKEN };
  process.env.HOME = scratch('queue-home-'); process.env.CLAUDE_BRIDGE_AUTH_TOKEN = 'env-tok';
  try {
    const seen = [];
    const r = relay({ agent: 'x', project: undefined }, { relay_url: 'http://r' }, { call: (tok, p, opts) => seen.push([tok, p, opts]), left: () => 4000 });
    r.call('/api/messages?x=1');
    assert.deepEqual(seen, [['env-tok', '/api/messages?x=1', { relayUrl: 'http://r', timeoutMs: 4000 }]]);
  } finally { for (const [k, v] of Object.entries(env)) if (v === undefined) delete process.env[k]; else process.env[k] = v; }
});

test('askHolder: the wait is the run\'s budget when that is shorter, and the request lives no longer', async () => {
  const asked = [];
  const call = async (p, init) => { asked.push(init?.method ? JSON.parse(JSON.parse(init.body).content) : 'GET'); return init?.method === 'POST' ? { id: 'm1' } : { messages: [] }; };
  let left = 1200;
  assert.equal(await askHolder({ call, cfg, from: 'h/py', holder: 'h/user', op: 'pool-list', args: { role: 'python-dev' }, waitMs: 10000, left: () => left }), null);
  assert.equal(asked[0].ttl_s, 2, 'ttl from the shortened wait, not waitMs');
  // Spent before the post: nothing is posted, and it is said as the budget, unsent.
  asked.length = 0; left = 0;
  await assert.rejects(askHolder({ call, cfg, from: 'h/py', holder: 'h/user', op: 'pool-list', args: { role: 'python-dev' }, waitMs: 5000, left: () => left }),
    e => e.budgetSpent === true && unsent(e));
  assert.deepEqual(asked, [], 'nothing posted');
});

test('relayError: a relay that did not answer is said as that, not as unreachable', () => {
  const cfg = { relay_url: 'http://r' };
  assert.equal(relayError({ timedOut: true, message: '/api/send -> no answer within 30 s' }, cfg),
    'the relay at http://r did not answer (no answer within 30 s)');
  assert.equal(relayError({ status: 401 }, cfg), 'the relay refused (HTTP 401)');
  assert.equal(relayError(new Error('x'), cfg), 'the relay is unreachable at http://r');
});
