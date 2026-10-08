// runtime/control/pool.mjs — a role's open pool of jobs (agent-fabric
// ADR-037 rule 9), held by one control agent so that one process orders
// every claim.
//
// THE HOLDER is config.json's `pool_holder` when set; otherwise, with one
// host in runtime/hosts/registry.json, that host's operator — the
// coordinator's account. With several hosts and none configured no account
// holds it, and every pool op says so: which agentd orders the claims is
// never guessed.
//
// THE FILE is <state>/agents/<holder login>/pool.json, {seq, jobs: [...]},
// written whole through a temporary file and a rename. A file that cannot
// be read is an error, never an empty pool: claims recorded in it would be
// handed out again.
//
// THE OPS. `pool-add` is an ACTION (sign.mjs ACTION_OPS): the owner's job
// for a role, a closed argument set — role, title, topic, project,
// priority — as jobs-add checks it. `pool-list` and `pool-claim` are
// PUBLIC (ops.mjs PUBLIC_OPS): any placed account asks, for itself.
//
// A CLAIM is checked against the claimant's binding as ITS control agent
// reports it — the role in its newest state record on the state channel
// (sessions.mjs), never a role the request names (the owner, 2026-10-08).
// No record from it within STATES_STALE_MS is a binding unknown, and the
// claim is refused. A job has one claimant: a claim of a job another
// account holds is refused; the same account claiming again gets it again,
// so a claimant whose own list could not take it can try once more.
//
// SERIALIZED, by construction: every change to the file is one synchronous
// read-modify-write, which no other request of this process can interleave,
// and agentd answers pool-claim in its loop, one request at a time. One
// agentd runs per account (its systemd unit); nothing else writes the file.
//
// What the relay verifies about a sender is nothing, here as for every
// public op: an unsigned `from` is a claim, and so is the role a state
// record carries. The fence is that a claim lands only on the claimant's
// own list, written by its own fabric-jobs (rule 1).

import fs from 'node:fs';
import path from 'node:path';
import { FABRIC_ROOT, loadTaxonomy } from './gzcoord.mjs';
import { checkJobArgs, PRIORITIES } from './jobs.mjs';
import { stateDir } from './upgrade.mjs';
import { STATES_REPLAY, STATES_STALE_MS } from './ctl.mjs';

export const POOL_FILE = 'pool.json';
export const POOL_ID = /^p[1-9][0-9]{0,8}$/;
export const ROLE_SLUG = /^[a-z][a-z0-9-]{0,62}$/;
const defaultRegistry = () => process.env.AGENT_FABRIC_HOSTS_REGISTRY ?? path.join(FABRIC_ROOT, 'runtime', 'hosts', 'registry.json');

/** The address that holds the pool, or null when none can be named. */
export function poolHolder(cfg = {}, registry = defaultRegistry()) {
  if (typeof cfg.pool_holder === 'string' && cfg.pool_holder) return cfg.pool_holder;
  try {
    const hosts = Object.entries(JSON.parse(fs.readFileSync(registry, 'utf8')).hosts ?? {});
    return hosts.length === 1 ? `${hosts[0][0]}/${hosts[0][1].operator ?? 'user'}` : null;
  } catch { return null; }
}

export const poolFile = () => path.join(stateDir(), POOL_FILE);

export function readPool(file) {
  let raw;
  try { raw = fs.readFileSync(file, 'utf8'); } catch (e) { if (e.code === 'ENOENT') return { seq: 0, jobs: [] }; throw new Error(`the pool cannot be read (${e.code ?? e.message})`); }
  let doc;
  try { doc = JSON.parse(raw); } catch { throw new Error('the pool file is not JSON'); }
  if (!doc || !Array.isArray(doc.jobs) || !Number.isInteger(doc.seq)) throw new Error('the pool file is not a pool');
  return doc;
}

function writePool(file, doc) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  const tmp = `${file}.${process.pid}.tmp`;
  fs.writeFileSync(tmp, JSON.stringify(doc, null, 2) + '\n', { mode: 0o600 });
  fs.renameSync(tmp, file);
}

// The pool's order is the queue's (tools/fabric/jobs.py queue_order):
// highest priority, then the oldest.
export const byPriority = (a, b) => (PRIORITIES.indexOf(a.priority) - PRIORITIES.indexOf(b.priority)) || (a.seq - b.seq);
const shown = j => ({ id: j.id, role: j.role, title: j.title, topic: j.topic, project: j.project, priority: j.priority, created: j.created });

export function roles(catalog = path.join(FABRIC_ROOT, 'identities', 'roles', 'catalog.json')) {
  try { return new Set(loadTaxonomy(catalog).roles.keys()); } catch { return null; }
}

export function checkPoolArgs(args, known = roles()) {
  if (!args || typeof args !== 'object' || Array.isArray(args)) return 'pool-add takes { role, title, topic, project, priority }';
  const extra = Object.keys(args).filter(k => !['role', 'title', 'topic', 'project', 'priority'].includes(k));
  if (extra.length) return `pool-add takes only role, title, topic, project and priority, not ${extra.join(', ')}`;
  if (typeof args.role !== 'string' || !ROLE_SLUG.test(args.role)) return 'role is a catalogue id (lowercase, digits, dashes)';
  if (!known) return 'the role catalogue cannot be read';
  if (!known.has(args.role)) return `no role ${args.role} in the catalogue`;
  const { role, ...job } = args;
  return checkJobArgs(job);
}

// Every op answers {status, ...}: 'refused' with a reason the asker reads.
const refused = reason => ({ status: 'refused', reason });
function notHolder(me, holder) {
  if (!holder) return refused('no account holds the pool: several hosts and no pool_holder in runtime/control/config.json');
  return me === holder ? null : refused(`this account does not hold the pool; ${holder} does`);
}

export function poolAdd(request, { me, holder, file = poolFile(), known = roles(), now = () => new Date().toISOString() }) {
  const to = Array.isArray(request.to) ? request.to : [request.to];
  if (to.length !== 1 || to[0] !== me) return refused('pool-add names the account that holds the pool, and only it');
  const no = notHolder(me, holder); if (no) return no;
  const bad = checkPoolArgs(request.args, known);
  if (bad) return refused(bad);
  const { role, title, topic, project, priority } = request.args;
  try {
    const doc = readPool(file);
    doc.seq += 1;
    const job = { id: `p${doc.seq}`, seq: doc.seq, role, title: title.trim().replace(/\s+/g, ' '), topic: topic?.trim().replace(/\s+/g, ' ') ?? null,
      project: project ?? null, priority: priority ?? 'normal', created: now(), from: String(request.from), claimed: null };
    doc.jobs.push(job);
    writePool(file, doc);
    return { status: 'added', job: shown(job) };
  } catch (e) { return refused(e.message); }
}

export function poolList(request, { me, holder, file = poolFile() }) {
  const no = notHolder(me, holder); if (no) return no;
  const role = request.args?.role;
  if (typeof role !== 'string' || !ROLE_SLUG.test(role)) return refused('pool-list takes { role }');
  try {
    const open = readPool(file).jobs.filter(j => j.role === role && !j.claimed).sort(byPriority);
    return { status: 'ok', role, jobs: open.map(shown) };
  } catch (e) { return refused(e.message); }
}

// The claimant's role as its control agent last reported it, read from the
// state channel: {role} or {error}.
export function roleFromStream({ call, cfg, now = Date.now }) {
  return async address => {
    let page;
    try { page = await call(`/api/messages?${new URLSearchParams({ channel: cfg.state_channel, limit: String(STATES_REPLAY), full: '1' })}`); }
    catch (e) { return { error: `the state stream could not be read (${e.status ? `HTTP ${e.status}` : 'relay unreachable'})` }; }
    let newest = null;
    for (const rec of Array.isArray(page?.messages) ? page.messages : []) {
      let r; try { r = JSON.parse(rec?.content); } catch { continue; }
      if (r?.kind === 'state' && r.v === 1 && r.from === address && typeof r.ts === 'string') newest = r;
    }
    if (!newest || !(now() - Date.parse(newest.ts) <= STATES_STALE_MS)) return { error: `no state record from ${address} in the last ${STATES_STALE_MS / 60000} min: its binding is unknown` };
    return typeof newest.role === 'string' && newest.role ? { role: newest.role } : { error: `${address} reports no bound role` };
  };
}

export async function poolClaim(request, { me, holder, file = poolFile(), roleOf, now = () => new Date().toISOString() }) {
  const no = notHolder(me, holder); if (no) return no;
  const id = request.args?.id;
  if (typeof id !== 'string' || !POOL_ID.test(id)) return refused('pool-claim takes { id }, a pool job id (p<n>)');
  const from = String(request.from);
  if (typeof roleOf !== 'function') return refused('this control agent reads no state stream: the claimant\'s role is unknown');
  const bound = await roleOf(from);
  // Everything below is synchronous: no other claim runs between the read
  // and the write.
  try {
    const doc = readPool(file);
    const job = doc.jobs.find(j => j.id === id);
    if (!job) return refused(`no pool job ${id}`);
    if (bound.error) return refused(bound.error);
    if (bound.role !== job.role) return refused(`${from} holds ${bound.role}, as its control agent reports it; ${id} is for ${job.role}`);
    if (job.claimed && job.claimed.by !== from) return refused(`${id} is claimed by ${job.claimed.by} (${job.claimed.at})`);
    const again = Boolean(job.claimed);
    if (!again) { job.claimed = { by: from, at: now() }; writePool(file, doc); }
    return { status: 'claimed', job: shown(job), ...(again ? { again: true } : {}) };
  } catch (e) { return refused(e.message); }
}
