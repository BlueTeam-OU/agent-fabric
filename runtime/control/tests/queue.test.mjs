// What bin/fabric-jobs asks of the control plane to order a queue
// (queue.mjs): the waits read from the state stream.
import test from 'node:test';
import assert from 'node:assert/strict';
import { waitsFrom, readWaits } from '../queue.mjs';

const A = '01a11a18-4728-7d8b-afd9-0edb2d30a59c', B = '01a11a19-0bea-70c7-b667-1e1e5a74dbe1';
const rec = (from, waits_on, extra = {}) => ({ content: JSON.stringify({ v: 1, kind: 'state', from, ts: 't', sessions: [], ...(waits_on ? { waits_on } : {}), ...extra }) });

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
  ], placed);
  assert.deepEqual(got, { waits: { [B]: ['h/a'], [A]: ['h/b'] }, accounts: 2 });
});

test('a record without waits_on waits on nothing, and replaces an older one that did', () => {
  assert.deepEqual(waitsFrom([rec('h/a', [A]), rec('h/a', null)], new Set(['h/a'])), { waits: {}, accounts: 1 });
});

test('readWaits reads the state channel, never the control channel', async () => {
  const asked = [];
  const got = await readWaits({ call: async p => { asked.push(p); return { messages: [rec('h/a', [A])] }; },
    cfg: { channel: 'c:control', state_channel: 's:state:control' }, placed: new Set(['h/a']) });
  assert.match(asked[0], /channel=s%3Astate%3Acontrol/);
  assert.deepEqual(got.waits, { [A]: ['h/a'] });
});
