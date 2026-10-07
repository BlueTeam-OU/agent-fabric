// The control plane's envelopes, as the code builds them, against the keys
// protocol.mjs declares: every required key present, nothing undeclared. No
// checker reads the JSDoc typedefs (option (B), j28), so this is what keeps
// them true.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { scratch } from '../../../tests/scratch.mjs';
import { memorySlug } from '../ops.mjs';
import { ENVELOPE_KEYS } from '../protocol.mjs';
import { answer, upRecord } from '../agentd.mjs';
import { askPresence } from '../presence.mjs';
import { stateRecord } from '../sessions.mjs';
import { signRequest, generateOperatorKey } from '../sign.mjs';
import { buildRequest, parseArgs } from '../ctl.mjs';

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
  const ping = { v: 1, kind: 'request', id: 'q1', from: 'h/user', to: '*', op: 'ping', ts: new Date().toISOString() };
  const ctx = { me: { address: 'h/db-admin' }, started: new Date().toISOString(), home: scratch('protocol-home-') };
  const { _followups: none, ...reply } = await answer(ping, ctx);
  holds(reply, 'reply', 'ping reply');
  assert.equal(none, undefined, 'a ping has no parts');
  // A memory reply big enough to need parts: the harvester stubbed, as in agentd.test.mjs.
  const h = scratch('protocol-mem-');
  const wc = path.join(h, 'projects', 'gzapp'); fs.mkdirSync(wc, { recursive: true });
  const mem = path.join(h, '.claude', 'projects', memorySlug(wc), 'memory'); fs.mkdirSync(mem, { recursive: true });
  fs.writeFileSync(path.join(mem, 'a.md'), 'x');
  const tar = crypto.randomBytes(200000);
  const exec = async () => ({ stdout: tar, stderr: JSON.stringify({ claims: 1, counts: { in_scope: 1, total: 1 }, needs_rendering: [], skipped_no_roles_class: [] }) });
  const { _followups, ...first } = await answer({ ...ping, id: 'q2', op: 'memory' }, { ...ctx, home: h, exec });
  holds(first, 'reply', 'memory reply');
  assert.ok(_followups && _followups.length > 1, `a memory reply this size comes in parts: ${_followups?.length}`);
  for (const part of _followups) holds(part, 'reply', 'a part');
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

test('what agentd posts about its sessions is a State, with and without a binding', () => {
  holds(stateRecord('h/db-admin', { sessions: [{ session: 's', state: 'idle', since: 't' }], role: 'db-admin', project: 'gzapp' }), 'state', 'state');
  holds(stateRecord('h/db-admin', { sessions: [], role: null, project: null }), 'state', 'unbound state');
});

test('the request fabric-ctl sends is a Request, for every op shape it builds', () => {
  const cfg = { ttl_s: 30 };
  const build = argv => buildRequest(parseArgs(argv), {
    id: 'q', from: 'h/user', to: '*', cfg, commit: () => 'c'.repeat(40), version: () => '9.9.9' });
  const shapes = [
    ['all', 'status'],
    ['all', 'tokens', '--days', '7'],
    ['all', 'upgrade', 'fabric'],
    ['all', 'upgrade', 'claude'],
    ['h-dev', 'jobs-add', 'a title', '--topic', 't'],
    ['all', 'secrets-sync', '--restart'],
    ['all', 'secrets-sync', '--expect', 'abcdef012345'],
  ];
  for (const argv of shapes) {
    const r = build(argv);
    holds(r, 'request', `fabric-ctl ${argv.join(' ')}`);
  }
  assert.ok('days' in build(['all', 'tokens', '--days', '7']), 'the days a usage request carries');
  assert.ok('args' in build(['all', 'upgrade', 'fabric']), 'the args an action carries');
});
