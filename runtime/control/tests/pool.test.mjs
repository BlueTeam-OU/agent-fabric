// A role's open pool (pool.mjs, ADR-037 rule 9): held by one control
// agent, added to by a signed action, listed and claimed by placed agents,
// a claim checked against the role the claimant's own control agent
// reports, one claimant per job.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { scratch } from '../../../tests/scratch.mjs';
import { poolHolder, poolAdd, poolList, poolClaim, readPool, roleFromStream, checkPoolArgs } from '../pool.mjs';
import { OPS, PUBLIC_OPS } from '../ops.mjs';
import { ACTION_OPS, generateOperatorKey, signRequest, publicKeyFrom } from '../sign.mjs';
import { accept, answer } from '../agentd.mjs';
import { parseArgs, buildRequest, table, ACTION_OK, STATES_REPLAY } from '../ctl.mjs';

const HOLDER = 'h/user';
const KNOWN = new Set(['python-dev', 'web-dev']);

function pool() {
  const d = scratch('pool-');
  const file = path.join(d, 'pool.json');
  let n = 0;
  const add = (args, from = HOLDER) => poolAdd({ from, to: [HOLDER], args }, { me: HOLDER, holder: HOLDER, file, known: KNOWN, now: () => `2026-10-08T00:00:0${n++}Z` });
  return { d, file, add };
}
const roles = map => async address => (address in map ? { role: map[address] } : { error: `no state record from ${address}` });

test('the pool ops: pool-add a signed action, pool-list and pool-claim public', () => {
  for (const op of ['pool-add', 'pool-list', 'pool-claim']) assert.ok(OPS.includes(op), op);
  assert.ok(ACTION_OPS.includes('pool-add') && !ACTION_OPS.includes('pool-list') && !ACTION_OPS.includes('pool-claim'));
  assert.ok(PUBLIC_OPS.includes('pool-list') && PUBLIC_OPS.includes('pool-claim') && !PUBLIC_OPS.includes('pool-add'));
  assert.deepEqual(ACTION_OK['pool-add'], ['added']);
});

test('the holder: configured, else the operator of the one host, else nobody', () => {
  const d = scratch('pool-reg-');
  const reg = path.join(d, 'registry.json');
  fs.writeFileSync(reg, JSON.stringify({ hosts: { h: { operator: 'user' } } }));
  assert.equal(poolHolder({}, reg), 'h/user');
  assert.equal(poolHolder({ pool_holder: 'k/coord' }, reg), 'k/coord');
  fs.writeFileSync(reg, JSON.stringify({ hosts: { h: { operator: 'user' }, k: { operator: 'op' } } }));
  assert.equal(poolHolder({}, reg), null, 'two hosts, none configured: never guessed');
  assert.equal(poolHolder({}, path.join(d, 'missing.json')), null);
});

test('pool-add: a closed argument set, a catalogue role, ids in order', () => {
  const { file, add } = pool();
  assert.match(add({ role: 'python-dev', title: 'x', extra: 1 }).reason, /only role, title, topic, project and priority/);
  assert.match(add({ role: 'nobody', title: 'x' }).reason, /no role nobody in the catalogue/);
  assert.match(add({ role: 'python-dev', title: 'x', priority: 'urgent' }).reason, /priority is one of/);
  assert.match(add({ title: 'x' }).reason, /role is a catalogue id/);
  assert.match(checkPoolArgs({ role: 'python-dev', title: 'x' }, null), /catalogue cannot be read/);
  assert.equal(readPool(file).jobs.length, 0, 'a refused add writes nothing');
  const r = add({ role: 'python-dev', title: '  port   the thing ', priority: 'high', topic: 'port' });
  assert.equal(r.status, 'added', JSON.stringify(r));
  assert.deepEqual([r.job.id, r.job.role, r.job.title, r.job.priority, r.job.topic], ['p1', 'python-dev', 'port the thing', 'high', 'port']);
  assert.equal(add({ role: 'web-dev', title: 'y' }).job.id, 'p2');
  assert.equal(readPool(file).jobs[1].priority, 'normal');
  assert.equal(fs.statSync(file).mode & 0o777, 0o600);
});

test('pool-add only on the holder, addressed to it alone', () => {
  const { file } = pool();
  const req = { from: HOLDER, to: ['h/other'], args: { role: 'python-dev', title: 'x' } };
  assert.match(poolAdd(req, { me: 'h/other', holder: HOLDER, file, known: KNOWN }).reason, /h\/user does/);
  assert.match(poolAdd({ ...req, to: '*' }, { me: HOLDER, holder: HOLDER, file, known: KNOWN }).reason, /only it/);
  assert.match(poolAdd({ ...req, to: [HOLDER] }, { me: HOLDER, holder: null, file, known: KNOWN }).reason, /no account holds the pool/);
});

test('pool-list: the role\'s open jobs, highest priority then oldest; claimed ones gone', async () => {
  const { file, add } = pool();
  add({ role: 'python-dev', title: 'old normal' });
  add({ role: 'web-dev', title: 'not mine' });
  add({ role: 'python-dev', title: 'low', priority: 'low' });
  add({ role: 'python-dev', title: 'high', priority: 'high' });
  add({ role: 'python-dev', title: 'newer high', priority: 'high' });
  const list = () => poolList({ from: 'h/a', args: { role: 'python-dev' } }, { me: HOLDER, holder: HOLDER, file });
  assert.deepEqual(list().jobs.map(j => j.id), ['p4', 'p5', 'p1', 'p3']);
  await poolClaim({ from: 'h/a', args: { id: 'p4' } }, { me: HOLDER, holder: HOLDER, file, roleOf: roles({ 'h/a': 'python-dev' }) });
  assert.deepEqual(list().jobs.map(j => j.id), ['p5', 'p1', 'p3']);
  assert.deepEqual(poolList({ from: 'h/a', args: { role: 'db-admin' } }, { me: HOLDER, holder: HOLDER, file }), { status: 'ok', role: 'db-admin', jobs: [] }, 'an empty pool is said as one');
  assert.match(poolList({ from: 'h/a', args: {} }, { me: HOLDER, holder: HOLDER, file }).reason, /takes \{ role \}/);
});

test('pool-claim: the claimant\'s reported role decides, never one the request names', async () => {
  const { file, add } = pool();
  add({ role: 'python-dev', title: 'x' });
  const claim = (from, args, map) => poolClaim({ from, args }, { me: HOLDER, holder: HOLDER, file, roleOf: roles(map) });
  const r = await claim('h/web', { id: 'p1', role: 'python-dev' }, { 'h/web': 'web-dev' });
  assert.equal(r.status, 'refused');
  assert.match(r.reason, /h\/web holds web-dev, as its control agent reports it; p1 is for python-dev/);
  assert.equal(readPool(file).jobs[0].claimed, null);
  assert.match((await claim('h/gone', { id: 'p1' }, {})).reason, /no state record from h\/gone/);
  assert.match((await claim('h/py', { id: 'p9' }, { 'h/py': 'python-dev' })).reason, /no pool job p9/);
  assert.match((await claim('h/py', { id: '../p1' }, { 'h/py': 'python-dev' })).reason, /a pool job id/);
  const won = await claim('h/py', { id: 'p1' }, { 'h/py': 'python-dev' });
  assert.equal(won.status, 'claimed');
  assert.equal(readPool(file).jobs[0].claimed.by, 'h/py');
  const other = await claim('h/py2', { id: 'p1' }, { 'h/py2': 'python-dev' });
  assert.match(other.reason, /p1 is claimed by h\/py/);
  const again = await claim('h/py', { id: 'p1' }, { 'h/py': 'python-dev' });
  assert.deepEqual([again.status, again.again], ['claimed', true], 'the claimant again gets it again');
  assert.match((await poolClaim({ from: 'h/py', args: { id: 'p1' } }, { me: HOLDER, holder: HOLDER, file })).reason, /reads no state stream/);
});

test('two concurrent claims of one job: one wins, one is refused', async () => {
  const { file, add } = pool();
  add({ role: 'python-dev', title: 'x' });
  // Each role read takes a turn of the event loop, so both claims are
  // inside poolClaim at once before either writes.
  const slow = map => async a => { await new Promise(r => setTimeout(r, 5)); return { role: map[a] }; };
  const map = { 'h/a': 'python-dev', 'h/b': 'python-dev' };
  const [a, b] = await Promise.all(['h/a', 'h/b'].map(from => poolClaim({ from, args: { id: 'p1' } }, { me: HOLDER, holder: HOLDER, file, roleOf: slow(map) })));
  assert.deepEqual([a.status, b.status].sort(), ['claimed', 'refused']);
  const loser = a.status === 'refused' ? a : b;
  assert.match(loser.reason, /is claimed by/);
  assert.equal(readPool(file).jobs[0].claimed.by, (a.status === 'claimed' ? 'h/a' : 'h/b'));
});

test('an unreadable pool is refused, never read as empty', async () => {
  const { file, add } = pool();
  add({ role: 'python-dev', title: 'x' });
  fs.writeFileSync(file, '{broken');
  assert.match(add({ role: 'python-dev', title: 'y' }).reason, /not JSON/);
  assert.equal(fs.readFileSync(file, 'utf8'), '{broken', 'nothing written over it');
  assert.match((await poolClaim({ from: 'h/a', args: { id: 'p1' } }, { me: HOLDER, holder: HOLDER, file, roleOf: roles({ 'h/a': 'python-dev' }) })).reason, /not JSON/);
  assert.match(poolList({ from: 'h/a', args: { role: 'python-dev' } }, { me: HOLDER, holder: HOLDER, file }).reason, /not JSON/);
});

test('the claimant\'s role: its newest state record, fresh, with a role', async () => {
  const now = Date.parse('2026-10-08T12:00:00Z');
  const rec = (from, role, ts = '2026-10-08T11:59:00Z') => ({ content: JSON.stringify({ v: 1, kind: 'state', from, ts, sessions: [], ...(role ? { role } : {}) }) });
  const asked = [];
  const of = rows => roleFromStream({ call: async p => { asked.push(p); return { messages: rows }; }, cfg: { state_channel: 's:state:control' }, now: () => now });
  assert.deepEqual(await of([rec('h/a', 'web-dev'), rec('h/a', 'python-dev'), rec('h/b', 'db-admin')])('h/a'), { role: 'python-dev' });
  assert.match(asked[0], /channel=s%3Astate%3Acontrol/);
  assert.match((await of([rec('h/a', 'python-dev', '2026-10-08T11:00:00Z')])('h/a')).error, /binding is unknown/, 'stale');
  assert.match((await of([rec('h/a', null)])('h/a')).error, /no bound role/);
  assert.match((await of([])('h/a')).error, /no state record from h\/a/);
  // A full page whose oldest record is newer than the bound has not seen the whole of it.
  const busy = Array.from({ length: STATES_REPLAY }, () => rec('h/b', 'db-admin', '2026-10-08T11:55:00Z'));
  assert.match((await of(busy)('h/a')).error, /last 500 records reach back only 5 min and none is from h\/a/);
  // Mid-page: the oldest by its own ts, not by the relay's order (clocks skew).
  const covered = [...busy.slice(1, 250), rec('h/b', 'db-admin', '2026-10-08T11:30:00Z'), ...busy.slice(250)];
  assert.match((await of(covered)('h/a')).error, /no state record from h\/a in the last 20 min/, 'a page that covers the bound');
  assert.match((await of(busy.slice(1))('h/a')).error, /no state record from h\/a in the last 20 min/, 'a page short of full is the whole stream');
  const down = roleFromStream({ call: async () => { throw Object.assign(new Error('x'), { status: 503 }); }, cfg: { state_channel: 's' } });
  assert.match((await down('h/a')).error, /could not be read \(HTTP 503\)/);
});

test('agentd: a placed account may ask pool-list and pool-claim unsigned; pool-add needs the operator\'s signature', () => {
  const k = generateOperatorKey();
  const me = { address: HOLDER };
  const base = { v: 1, kind: 'request', from: 'h/py', to: [HOLDER], ts: new Date().toISOString() };
  const ctx = { me, operators: new Set([HOLDER]), accounts: new Set(['h/py', HOLDER]), keys: new Map([[HOLDER, publicKeyFrom(k.publicKeySpec)]]), ttl_s: 30, seen: new Set() };
  const rec = r => ({ content: JSON.stringify(r) });
  assert.equal(accept(rec({ ...base, id: '1', op: 'pool-claim', args: { id: 'p1' } }), ctx).ok, true);
  assert.equal(accept(rec({ ...base, id: '2', op: 'pool-list', args: { role: 'python-dev' } }), ctx).ok, true);
  assert.equal(accept(rec({ ...base, id: '3', op: 'pool-add', args: { role: 'python-dev', title: 'x' } }), ctx).ok, false, 'a placed account cannot add');
  assert.equal(accept(rec({ ...base, id: '4', from: HOLDER, op: 'pool-add', args: { role: 'python-dev', title: 'x' } }), ctx).ok, false, 'unsigned: refused');
  const signed = signRequest({ ...base, id: '5', from: HOLDER, op: 'pool-add', args: { role: 'python-dev', title: 'x' } }, k.privateKeySpec);
  assert.equal(accept(rec(signed), ctx).ok, true);
});

test('agentd answers the pool ops from its own pool file', async () => {
  const { file } = pool();
  const prev = process.env.AGENT_FABRIC_HOSTS_REGISTRY;
  const d = scratch('pool-agentd-');
  process.env.AGENT_FABRIC_HOSTS_REGISTRY = path.join(d, 'registry.json');
  fs.writeFileSync(process.env.AGENT_FABRIC_HOSTS_REGISTRY, JSON.stringify({ hosts: { h: { operator: 'user' } } }));
  try {
    const ctx = { me: { address: HOLDER }, started: new Date().toISOString(), poolOpts: { file, known: KNOWN, roleOf: roles({ 'h/py': 'python-dev' }) } };
    const added = await answer({ id: 'a', op: 'pool-add', from: HOLDER, to: [HOLDER], args: { role: 'python-dev', title: 'x' } }, ctx);
    assert.equal(added.data['pool-add'].status, 'added', JSON.stringify(added.data));
    const listed = await answer({ id: 'b', op: 'pool-list', from: 'h/py', args: { role: 'python-dev' } }, ctx);
    assert.deepEqual(listed.data['pool-list'].jobs.map(j => j.id), ['p1']);
    const claimed = await answer({ id: 'c', op: 'pool-claim', from: 'h/py', args: { id: 'p1' } }, ctx);
    assert.equal(claimed.data['pool-claim'].status, 'claimed');
  } finally { if (prev === undefined) delete process.env.AGENT_FABRIC_HOSTS_REGISTRY; else process.env.AGENT_FABRIC_HOSTS_REGISTRY = prev; }
});

test('fabric-ctl: pool-add takes --role and a title, names one login; pool-list and pool-claim are fabric-jobs\'s', () => {
  const a = parseArgs(['user', 'pool-add', '--role', 'python-dev', '--priority', 'high', '--', '-dash title']);
  assert.deepEqual([a.op, a.role, a.priority, a.title, a.targets], ['pool-add', 'python-dev', 'high', '-dash title', ['user']]);
  const req = buildRequest(a, { id: 'i', from: HOLDER, to: [HOLDER], cfg: { ttl_s: 30 } });
  assert.deepEqual(req.args, { role: 'python-dev', title: '-dash title', priority: 'high' });
  assert.throws(() => parseArgs(['all', 'pool-add', '--role', 'python-dev', 'x']), /one login that holds the pool/);
  assert.throws(() => parseArgs(['user', 'pool-add', 'x']), /role is a catalogue id/);
  assert.throws(() => parseArgs(['user', 'pool-add', '--role', 'nobody', 'x']), /no role nobody/);
  assert.throws(() => parseArgs(['user', 'status', '--role', 'python-dev']), /--role goes with pool-add only/);
  assert.throws(() => parseArgs(['user', 'pool-claim']), /fabric-jobs's/);
  assert.throws(() => parseArgs(['user', 'pool-list']), /fabric-jobs's/);
  const out = table('pool-add', [{ account: 'user', status: 'ok', poolAdd: { status: 'added', job: { id: 'p1', role: 'python-dev', priority: 'high', title: 'x\u001b[31m' } } },
    { account: 'user2', status: 'ok', poolAdd: { status: 'refused', reason: 'no' } }]);
  assert.match(out, /^user +added  p1 python-dev high: x\\x1b\[31m$/m);
  assert.match(out, /^user2 +refused  no$/m);
});
