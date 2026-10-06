// The control plane's envelopes, as the code builds them, against the keys
// protocol.mjs declares: every required key present, nothing undeclared. No
// checker reads the JSDoc typedefs (option (B), j28), so this is what keeps
// them true.
import test from 'node:test';
import assert from 'node:assert/strict';
import { scratch } from '../../../tests/scratch.mjs';
import { ENVELOPE_KEYS } from '../protocol.mjs';
import { answer, upRecord } from '../agentd.mjs';
import { askPresence } from '../presence.mjs';
import { signRequest, generateOperatorKey } from '../sign.mjs';

function holds(value, kind, what) {
  const { required, optional } = ENVELOPE_KEYS[kind];
  const keys = Object.keys(value);
  const missing = required.filter(k => !keys.includes(k));
  const extra = keys.filter(k => !required.includes(k) && !optional.includes(k));
  assert.deepEqual({ missing, extra }, { missing: [], extra: [] }, `${what} is no ${kind}`);
  assert.equal(value.kind, kind, `${what}: kind`);
  assert.equal(value.v, 1, `${what}: v`);
}

test('a reply agentd answers with is a Reply, and so is each part of a memory reply', async () => {
  const ctx = { me: { address: 'h/db-admin' }, started: new Date().toISOString(), home: scratch('protocol-home-') };
  const { _followups, ...reply } = await answer({ v: 1, kind: 'request', id: 'q1', from: 'h/user', to: '*', op: 'ping', ts: new Date().toISOString() }, ctx);
  holds(reply, 'reply', 'ping reply');
  for (const part of _followups ?? []) holds(part, 'reply', 'a part');
});

test('the request presence sends is a Request; a signed one too', async () => {
  const posts = [];
  const call = async (p, init) => { if (p === '/api/send') posts.push(JSON.parse(init.body)); return { messages: [] }; };
  await askPresence({ from: 'h/user', to: ['h/a'], expect: ['h/a'], token: 't', waitMs: 50, cfg: { relay_url: 'x', channel: 'fabric:control', ttl_s: 30 }, call });
  const request = JSON.parse(posts[0].content);
  holds(request, 'request', 'presence request');
  holds(signRequest(request, generateOperatorKey().privateKeySpec), 'request', 'a signed request');
});

test('what agentd posts when it comes up is an Up', () => {
  holds(upRecord('h/db-admin'), 'up', 'up');
});
