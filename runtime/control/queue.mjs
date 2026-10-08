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
//     stdout  {"waits": {"<message id>": ["<host>/<login>", …]}, "accounts": <n records read>}
//             — for every placed account's newest state record among the
//             last STATES_REPLAY on the state channel, the message ids its
//             blocked jobs wait on (sessions.mjs waits_on)
//     exit    0 read; 2 usage; 3 not readable — no token, the relay
//             unreachable or refusing — with {"error": "<one line>"} on stdout
//
//   node runtime/control/queue.mjs pool-list [<role>]     (default: this login's bound role)
//   node runtime/control/queue.mjs pool-claim <pool id>
//     stdout  {"holder": "<address>", "answer": {"status": "ok"|"claimed"|"refused", …}}
//             — the holder's answer as pool.mjs gives it; a refusal is an answer
//     exit    0 answered; 2 usage; 3 no token, the relay unreachable or
//             refusing, or no answer within FABRIC_QUEUE_WAIT_MS (10 s) —
//             "sent": true when the request was posted before that, since
//             a claim unanswered may still have landed at the holder, and a
//             second claim by the same account gets it again; 4 no account
//             holds the pool, or this login has no bound role to list
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
import { FABRIC_ROOT, whoami, api, syncedToken, integrationConfig, inboxRoot, token as gzToken, identity as gzIdentity } from './gzcoord.mjs';
import { controlConfig, newId } from './agentd.mjs';
import { poolHolder, POOL_ID, ROLE_SLUG } from './pool.mjs';
import { MESSAGE_ID } from './sessions.mjs';
import { STATES_REPLAY } from './ctl.mjs';

export class Unreadable extends Error {}

/** The message ids each placed account waits on: { id: [address, …] }. */
export function waitsFrom(rows, placed) {
  const newest = new Map();
  for (const rec of rows) {
    let r; try { r = JSON.parse(rec?.content); } catch { continue; }
    if (r?.kind !== 'state' || r.v !== 1 || typeof r.from !== 'string' || !placed.has(r.from) || typeof r.ts !== 'string') continue;
    if (r.waits_on !== undefined && !(Array.isArray(r.waits_on) && r.waits_on.every(m => typeof m === 'string' && MESSAGE_ID.test(m)))) continue;
    // The channel's order is the relay's; a record later on it is newer.
    newest.set(r.from, r);
  }
  const waits = {};
  for (const [from, r] of [...newest].sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0)))
    for (const m of r.waits_on ?? []) (waits[m] ??= []).push(from);
  return { waits, accounts: newest.size };
}

export async function readWaits({ call, cfg, placed }) {
  const page = await call(`/api/messages?${new URLSearchParams({ channel: cfg.state_channel, limit: String(STATES_REPLAY), full: '1' })}`);
  return waitsFrom(Array.isArray(page?.messages) ? page.messages : [], placed);
}

// The relay as this login reaches it, or Unreadable saying why not.
export function relay(who = whoami(), cfg = controlConfig()) {
  const gz = integrationConfig(who.project);
  const tok = gzToken(inboxRoot(who), gz.configured ? gz : undefined) ?? syncedToken();
  if (!tok) throw new Unreadable('no CLAUDE_BRIDGE_AUTH_TOKEN (fabric-secrets sync)');
  return { who, cfg, call: (p, init) => api(tok, p, { relayUrl: cfg.relay_url, ...init }) };
}

// Who is placed, read here rather than through agentd's accountAddresses,
// which takes an unreadable registry for nobody: here that would read as
// "nobody waits on anything" and say nothing.
export function placedAccounts(registry = process.env.AGENT_FABRIC_HOSTS_REGISTRY ?? path.join(FABRIC_ROOT, 'runtime', 'hosts', 'registry.json')) {
  let d;
  try { d = JSON.parse(fs.readFileSync(registry, 'utf8')); } catch (e) { throw new Unreadable(`the hosts registry cannot be read (${e.code ?? 'not JSON'})`); }
  if (!d || typeof d.placement !== 'object' || d.placement === null || Array.isArray(d.placement)) throw new Unreadable('the hosts registry has no placement');
  return new Set(Object.entries(d.placement).map(([login, host]) => `${host}/${login}`));
}

export function relayError(e, cfg) {
  if (e instanceof Unreadable) return e.message;
  return e?.status ? `the relay refused (HTTP ${e.status})` : `the relay is unreachable at ${cfg.relay_url}`;
}

export const QUEUE_WAIT_MS = Number(process.env.FABRIC_QUEUE_WAIT_MS) > 0 ? Number(process.env.FABRIC_QUEUE_WAIT_MS) : 10000;
const sleep = ms => new Promise(r => setTimeout(r, ms));

// One request to the holder, its one reply's data[op], or null when none
// came within waitMs. The request carries only what the op reads: a role
// for a list, an id for a claim — never the claimant's role.
export async function askHolder({ call, cfg, from, holder, op, args, waitMs = QUEUE_WAIT_MS }) {
  const id = newId();
  /** @type {import('./protocol.mjs').Request} */
  // The request lives as long as the asker waits, and no longer: a claim
  // the holder took after the asker gave up would be recorded for nobody.
  const request = { v: 1, kind: 'request', id, from, to: [holder], op, ts: new Date().toISOString(), ttl_s: Math.ceil(waitMs / 1000), args };
  const sent = await call('/api/send', { method: 'POST', body: JSON.stringify({ channel: cfg.channel, sender: from, content: JSON.stringify(request) }) });
  const deadline = Date.now() + waitMs;
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
  try { r = relay(undefined, cfg); } catch (e) { out(JSON.stringify({ error: relayError(e, cfg) })); return 3; }
  if (cmd === 'waits') {
    try { out(JSON.stringify(await readWaits({ call: r.call, cfg, placed: placedAccounts() }))); return 0; }
    catch (e) { out(JSON.stringify({ error: relayError(e, cfg) })); return 3; }
  }
  const holder = poolHolder(cfg);
  if (!holder) { out(JSON.stringify({ error: 'no account holds the pool: several hosts and no pool_holder in runtime/control/config.json' })); return 4; }
  const me = gzIdentity(r.who);
  const role = cmd === 'pool-list' ? (arg ?? r.who.role) : undefined;
  if (cmd === 'pool-list' && !(typeof role === 'string' && ROLE_SLUG.test(role))) { out(JSON.stringify({ error: 'this login has no bound role: name the role whose pool to list' })); return 4; }
  let answer;
  try { answer = await askHolder({ call: r.call, cfg, from: me.address, holder, op: cmd, args: cmd === 'pool-list' ? { role } : { id: arg } }); }
  catch (e) { out(JSON.stringify({ error: relayError(e, cfg), holder, ...(e?.sent ? { sent: true } : {}) })); return 3; }
  if (!answer) { out(JSON.stringify({ error: `${holder} did not answer within ${QUEUE_WAIT_MS / 1000} s`, holder, sent: true })); return 3; }
  out(JSON.stringify({ holder, answer }));
  return 0;
}

if (process.argv[1] && fs.realpathSync(process.argv[1]) === fileURLToPath(import.meta.url))
  cli().then(c => process.exit(c), e => { console.log(JSON.stringify({ error: `queue: ${String(e?.message ?? e).split('\n')[0]}` })); process.exit(3); });
