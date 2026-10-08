// runtime/control/queue.mjs — what bin/fabric-jobs asks of the control
// plane to order a queue (agent-fabric ADR-037 rules 8 and 9): which
// requests some account waits on, read from the state stream.
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
//   env       CLAUDE_BRIDGE_URL, FABRIC_STATE_CHANNEL (controlConfig),
//             AGENT_FABRIC_HOSTS_REGISTRY (who is placed)
//
// A state record is any relay-token holder's post: one that does not have
// the shape agentd writes, or comes from no placed address, is skipped. A
// forged one can make a job look waited on — an ordering, never a
// permission — and the waiter it names is shown.

import { fileURLToPath } from 'node:url';
import fs from 'node:fs';
import { whoami, api, syncedToken, integrationConfig, inboxRoot, token as gzToken } from './gzcoord.mjs';
import { controlConfig, accountAddresses } from './agentd.mjs';
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

export function relayError(e, cfg) {
  if (e instanceof Unreadable) return e.message;
  return e?.status ? `the relay refused (HTTP ${e.status})` : `the relay is unreachable at ${cfg.relay_url}`;
}

export async function cli(argv = process.argv.slice(2), out = s => console.log(s)) {
  if (argv.length !== 1 || argv[0] !== 'waits') { console.error('usage: queue.mjs waits'); return 2; }
  const cfg = controlConfig();
  try {
    const { call } = relay(undefined, cfg);
    out(JSON.stringify(await readWaits({ call, cfg, placed: accountAddresses() })));
    return 0;
  } catch (e) {
    out(JSON.stringify({ error: relayError(e, cfg) }));
    return 3;
  }
}

if (process.argv[1] && fs.realpathSync(process.argv[1]) === fileURLToPath(import.meta.url))
  cli().then(c => process.exit(c), e => { console.log(JSON.stringify({ error: `queue: ${String(e?.message ?? e).split('\n')[0]}` })); process.exit(3); });
