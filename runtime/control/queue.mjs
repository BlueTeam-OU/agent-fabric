// runtime/control/queue.mjs — what bin/fabric-jobs asks of the control
// plane to order a queue (agent-fabric ADR-037 rules 8 and 9): which
// requests some account waits on, read from the state stream; and the
// role's pool, asked of the control agent that holds it (pool.mjs).
//
// THE CLI, for tools/fabric/jobs.py: the control plane's channels, record
// shapes and relay client stay in Node, one implementation, as for
// presence.mjs (the coordinator's decision of 2026-10-04, ADR-040 §7).
// This login's identity and relay token are resolved here, as agentd
// resolves its own: the token never crosses a pipe or an argv.
//
//   node runtime/control/queue.mjs waits
//     stdout  {"waits": {"<message id>": ["<host>/<login>", …]}, "accounts": <n records read>,
//              "stale": {"<host>/<login>": <age in s, or null when its ts does not parse>, …}}
//             — for every placed account's newest state record among the
//             last STATES_REPLAY on the state channel, the message ids its
//             blocked jobs wait on (sessions.mjs waits_on); `stale` names
//             each waiting account whose record is older than
//             STATES_STALE_MS. Its waits still count (ADR-037 rule 8: the
//             block is real in its jobs.json whether or not its agentd
//             runs); the age is for the reader to see the doubt.
//     exit    0 read; 2 usage; 3 not readable — no token, the relay
//             unreachable, refusing or not answering — with {"error": "<one line>"} on stdout
//
//   node runtime/control/queue.mjs pool-list [<role>]     (default: this login's bound role)
//   node runtime/control/queue.mjs pool-claim <pool id>
//     stdout  {"holder": "<address>", "answer": {"status": "ok"|"claimed"|"refused", …}}
//             — the holder's answer as pool.mjs gives it; a refusal is an answer
//     exit    0 answered; 2 usage; 3 no token, the relay unreachable,
//             refusing or not answering a call within QUEUE_CALL_TIMEOUT_MS,
//             or no answer from the holder within FABRIC_QUEUE_WAIT_MS (10 s),
//             all of it within QUEUE_BUDGET_MS of the run's start —
//             "sent": true when the request was posted before that, false
//             only where nothing left for certain (no token, a refused or
//             unconnected post), absent when it is unknown — a claim
//             unanswered may still have landed at the holder, and a second
//             claim by the same account gets it again; 4 no account holds
//             the pool, or this login has no bound role to list (sent: false)
//
//   env       CLAUDE_BRIDGE_URL, FABRIC_CONTROL_CHANNEL, FABRIC_STATE_CHANNEL
//             (controlConfig), AGENT_FABRIC_HOSTS_REGISTRY (who is placed,
//             who holds the pool), FABRIC_QUEUE_WAIT_MS
//
// A state record is any relay-token holder's post: one that does not have
// the shape agentd writes, or comes from no placed address, is skipped. A
// forged one can make a job look waited on — an ordering, never a
// permission — and the waiter it names is shown.

import { fileURLToPath } from 'node:url';
import fs from 'node:fs';
import path from 'node:path';
import { FABRIC_ROOT, whoami, api, syncedToken, integrationConfig, inboxRoot, token as gzToken, identity as gzIdentity, relayFailure } from './gzcoord.mjs';
import { hostsRegistry } from './roots.mjs';
import { controlConfig, newId } from './agentd.mjs';
import { poolHolder, POOL_ID, ROLE_SLUG } from './pool.mjs';
import { MESSAGE_ID } from './sessions.mjs';
import { STATES_REPLAY, STATES_STALE_MS } from './ctl.mjs';

export class Unreadable extends Error {}

/** The message ids each placed account waits on: { id: [address, …] }. */
export function waitsFrom(rows, placed, now = Date.now()) {
  const newest = new Map();
  for (const rec of rows) {
    let r; try { r = JSON.parse(rec?.content); } catch { continue; }
    if (r?.kind !== 'state' || r.v !== 1 || typeof r.from !== 'string' || !placed.has(r.from) || typeof r.ts !== 'string') continue;
    if (r.waits_on !== undefined && !(Array.isArray(r.waits_on) && r.waits_on.every(m => typeof m === 'string' && MESSAGE_ID.test(m)))) continue;
    // The channel's order is the relay's; a record later on it is newer.
    newest.set(r.from, r);
  }
  const waits = {}, stale = {};
  for (const [from, r] of [...newest].sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0))) {
    for (const m of r.waits_on ?? []) (waits[m] ??= []).push(from);
    const age = now - Date.parse(r.ts);
    if (r.waits_on?.length && !(age <= STATES_STALE_MS)) stale[from] = Number.isFinite(age) ? Math.floor(age / 1000) : null;
  }
  return { waits, accounts: newest.size, stale };
}

export async function readWaits({ call, cfg, placed }) {
  const page = await call(`/api/messages?${new URLSearchParams({ channel: cfg.state_channel, limit: String(STATES_REPLAY), full: '1' })}`);
  return waitsFrom(Array.isArray(page?.messages) ? page.messages : [], placed);
}

// THE BUDGET. tools/fabric/jobs.py kills this run QUEUE_TIMEOUT_S (30 s)
// after it starts node, whatever the run is doing. So the run has one
// budget, counted from the process's own start and under that kill, and
// every relay call — and the wait for the holder — takes at most what is
// left of it, and no call more than QUEUE_CALL_TIMEOUT_MS: a relay that
// does not answer is said by this side, never cut off by that one. A
// per-call bound alone was not enough: a post, the holder's wait and a
// hung poll added up past the kill (review of #124). No call here is a
// long poll.
export const QUEUE_CALL_TIMEOUT_MS = 15000;
export const QUEUE_BUDGET_MS = 25000;
const budgetEnd = performance.timeOrigin + QUEUE_BUDGET_MS;
// Whole milliseconds: performance.timeOrigin carries a fraction.
export const budgetLeft = (now = Date.now()) => Math.floor(budgetEnd - now);

// The relay as this login reaches it, or Unreadable saying why not.
// `api` is a parameter so a test can see what each call is given.
export function relay(who = whoami(), cfg = controlConfig(), { call = api, left = budgetLeft } = {}) {
  const gz = integrationConfig(who.project);
  const tok = gzToken(inboxRoot(who), gz.configured ? gz : undefined) ?? syncedToken();
  if (!tok) throw new Unreadable('no CLAUDE_BRIDGE_AUTH_TOKEN (fabric-secrets sync)');
  return { who, cfg, call: boundCall(tok, cfg, call, left) };
}

// A spent budget asks nothing: the call is not made, so nothing left this
// account, and the run's budget is named, never the relay (review of #128).
export const budgetSpent = p => Object.assign(
  new Error(`${String(p).split('?')[0]}: not asked, this run's ${QUEUE_BUDGET_MS / 1000} s budget is spent`), { budgetSpent: true });
export const boundCall = (tok, cfg, call = api, left = budgetLeft) => async (p, init) => {
  const ms = Math.min(QUEUE_CALL_TIMEOUT_MS, left());
  if (!(ms > 0)) throw budgetSpent(p);
  return call(tok, p, { relayUrl: cfg.relay_url, timeoutMs: ms, ...init });
};

// Who is placed, read here rather than through agentd's accountAddresses,
// which takes an unreadable registry for nobody: here that would read as
// "nobody waits on anything" and say nothing.
export function placedAccounts(registry = hostsRegistry({ engine: FABRIC_ROOT, emptyIsSet: true })) {
  let d;
  try { d = JSON.parse(fs.readFileSync(registry, 'utf8')); } catch (e) { throw new Unreadable(`the hosts registry cannot be read (${e.code ?? 'not JSON'})`); }
  if (!d || typeof d.placement !== 'object' || d.placement === null || Array.isArray(d.placement)) throw new Unreadable('the hosts registry has no placement');
  return new Set(Object.entries(d.placement).map(([login, host]) => `${host}/${login}`));
}

export function relayError(e, cfg) {
  if (e instanceof Unreadable) return e.message;
  if (e?.budgetSpent) return e.message;
  return relayFailure(e, cfg.relay_url);
}

export const QUEUE_WAIT_MS = Number(process.env.FABRIC_QUEUE_WAIT_MS) > 0 ? Number(process.env.FABRIC_QUEUE_WAIT_MS) : 10000;
const sleep = ms => new Promise(r => setTimeout(r, ms));

// One request to the holder, its one reply's data[op], or null when none
// came within waitMs. The request carries only what the op reads: a role
// for a list, an id for a claim — never the claimant's role.
// Whether a failed post certainly left nothing at the relay: refused with
// a 4xx, or never connected. Anything else (a reset, a 5xx after the write)
// is unknown, and said as such by leaving `sent` out.
export const unsent = e => e?.budgetSpent === true || (Number.isInteger(e?.status) && e.status >= 400 && e.status < 500) || e?.cause?.code === 'ECONNREFUSED';

export async function askHolder({ call, cfg, from, holder, op, args, waitMs = QUEUE_WAIT_MS, left = budgetLeft }) {
  const id = newId();
  // The wait, fixed once before anything is posted: waitMs, or what the run's
  // budget has left when that is less.
  const wait = Math.min(waitMs, left());
  if (!(wait > 0)) throw budgetSpent('/api/send');
  /** @type {import('./protocol.mjs').Request} */
  // The request lives as long as the asker waits, and no longer: a claim
  // the holder took after the asker gave up would be recorded for nobody.
  const request = { v: 1, kind: 'request', id, from, to: [holder], op, ts: new Date().toISOString(), ttl_s: Math.ceil(wait / 1000), args };
  const sent = await call('/api/send', { method: 'POST', body: JSON.stringify({ channel: cfg.channel, sender: from, content: JSON.stringify(request) }) });
  const deadline = Date.now() + Math.min(wait, left());
  let since = sent.id;
  while (Date.now() < deadline) {
    let page;
    try { page = await call(`/api/messages?${new URLSearchParams({ channel: cfg.channel, since_id: since, limit: '500', full: '1' })}`); }
    catch (e) { e.sent = true; throw e; }
    for (const rec of page?.messages ?? []) {
      since = rec.id;
      let r; try { r = JSON.parse(rec.content); } catch { continue; }
      // Only the holder's reply to this request: anyone may post on the channel.
      if (r?.kind === 'reply' && r.in_reply_to === id && r.from === holder && r.data?.[op] && typeof r.data[op].status === 'string') return r.data[op];
    }
    await sleep(400);
  }
  return null;
}

export async function cli(argv = process.argv.slice(2), out = s => console.log(s)) {
  const [cmd, arg, ...rest] = argv;
  const usage = 'usage: queue.mjs waits | pool-list [<role>] | pool-claim <pool id>';
  if (rest.length || !['waits', 'pool-list', 'pool-claim'].includes(cmd) || (cmd === 'waits' && arg !== undefined)
      || (cmd === 'pool-claim' && !POOL_ID.test(arg ?? '')) || (cmd === 'pool-list' && arg !== undefined && !ROLE_SLUG.test(arg))) { console.error(usage); return 2; }
  const cfg = controlConfig();
  let r;
  try { r = relay(undefined, cfg); } catch (e) { out(JSON.stringify({ error: relayError(e, cfg), sent: false })); return 3; }
  if (cmd === 'waits') {
    try { out(JSON.stringify(await readWaits({ call: r.call, cfg, placed: placedAccounts() }))); return 0; }
    catch (e) { out(JSON.stringify({ error: relayError(e, cfg) })); return 3; }
  }
  const holder = poolHolder(cfg);
  if (!holder) { out(JSON.stringify({ error: 'no account holds the pool: several hosts and no pool_holder in runtime/control/config.json', sent: false })); return 4; }
  const me = gzIdentity(r.who);
  const role = cmd === 'pool-list' ? (arg ?? r.who.role) : undefined;
  if (cmd === 'pool-list' && !(typeof role === 'string' && ROLE_SLUG.test(role))) { out(JSON.stringify({ error: 'this login has no bound role: name the role whose pool to list', sent: false })); return 4; }
  let answer; const asked = Date.now();
  try { answer = await askHolder({ call: r.call, cfg, from: me.address, holder, op: cmd, args: cmd === 'pool-list' ? { role } : { id: arg } }); }
  catch (e) { out(JSON.stringify({ error: relayError(e, cfg), holder, ...(e?.sent ? { sent: true } : unsent(e) ? { sent: false } : {}) })); return 3; }
  if (!answer) { out(JSON.stringify({ error: `${holder} did not answer within ${Math.round((Date.now() - asked) / 1000)} s`, holder, sent: true })); return 3; }
  out(JSON.stringify({ holder, answer }));
  return 0;
}

if (process.argv[1] && fs.realpathSync(process.argv[1]) === fileURLToPath(import.meta.url))
  cli().then(c => process.exit(c), e => { console.log(JSON.stringify({ error: `queue: ${String(e?.message ?? e).split('\n')[0]}` })); process.exit(3); });
