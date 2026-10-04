// runtime/control/presence.mjs — whether accounts have a session, asked of
// their control agents (ops.mjs `presence`), by any placed account. The
// sender's check before a message leaves (communication/gzcoord/scripts/
// send.mjs) is the caller: a message to a login with no session waits in
// the relay until one starts, and the sender is the one who can decide
// whether that is what it wants (the owner, 2026-09-25).
//
// The answer is the process table, not a claim a session made about
// itself: a crash, or a launch that never reached the harness, is never
// "present" — what the HELLO/GOODBYE pair, now retired, got wrong.
//
// THE CLI, for the sender in Python (agent-fabric ADR-040 §7, Wave 7; the
// coordinator's decision of 2026-10-04): the control channel's request
// and reply shapes stay here, in the control plane Node keeps, rather
// than copied into the sender — one implementation, changed once. It
// runs only for a TO or TO-ROLE send, beside a wait of up to
// GZCOORD_PRESENCE_WAIT_MS.
//
//   node runtime/control/presence.mjs check
//     stdin   one JSON object: {"metadata": {<the message's metadata>},
//             "from": "<host>/<login>", "token": "<relay token>"} — the
//             token on stdin, never in argv
//     env     GZCOORD_PRESENCE_WAIT_MS, AGENT_FABRIC_HOSTS_REGISTRY,
//             FABRIC_CONTROL_CHANNEL / CLAUDE_BRIDGE_URL (controlConfig)
//     stdout  one JSON object: checkAddressees' answer {checked,
//             problems, notes}; or, when the request could not be made,
//             {"error": "<one line>", "status": <HTTP status or null>}
//     exit    0 checked, no problem (or nothing to check); 4 a definite
//             problem only (offline, not-placed, no-holder with every
//             placement answering); 5 an addressee that did not answer
//             (silent, or a no-holder with silent placements); 6
//             unavailable — a presence that could not read its process
//             table, or the request that could not be made; 2 usage or
//             unreadable stdin. The JSON is the answer; the status sums it.

import fs from 'node:fs';
import { fileURLToPath } from 'node:url';
import { api } from './gzcoord.mjs';
import { controlConfig, newId, accountAddresses, operatorAddresses } from './agentd.mjs';

// How long a sender waits for an answer: a control agent answers within a
// second; the rest is the relay's poll. GZCOORD_PRESENCE_WAIT_MS shortens
// it for a suite's silent-agent case.
export const PRESENCE_WAIT_MS = Number(process.env.GZCOORD_PRESENCE_WAIT_MS) > 0 ? Number(process.env.GZCOORD_PRESENCE_WAIT_MS) : 6000;
const sleep = ms => new Promise(r => setTimeout(r, ms));

// { <address>: <presence> | null } for every address in `expect`; null is
// a control agent that did not answer within waitMs — unknown, never
// "offline". `to` is one address, a list, or '*' (a TO-ROLE is resolved
// by the caller from the roles in the answers).
export async function askPresence({ from, to, expect, token, waitMs = PRESENCE_WAIT_MS, cfg = controlConfig(), call = null }) {
  const c = call ?? ((p, init) => api(token, p, { relayUrl: cfg.relay_url, ...init }));
  const id = newId();
  const request = { v: 1, kind: 'request', id, from, to, op: 'presence', ts: new Date().toISOString(), ttl_s: Math.max(cfg.ttl_s, Math.ceil(waitMs / 1000)) };
  const sent = await c('/api/send', { method: 'POST', body: JSON.stringify({ channel: cfg.channel, sender: from, content: JSON.stringify(request) }) });
  const out = Object.fromEntries(expect.map(a => [a, null]));
  const want = new Set(expect);
  const deadline = Date.now() + waitMs;
  let since = sent.id;
  while (want.size && Date.now() < deadline) {
    const page = await c(`/api/messages?${new URLSearchParams({ channel: cfg.channel, since_id: since, limit: '500', full: '1' })}`);
    for (const rec of page.messages ?? []) {
      since = rec.id;
      let r; try { r = JSON.parse(rec.content); } catch { continue; }
      if (r?.kind === 'reply' && r.in_reply_to === id && want.has(r.from) && r.data?.presence) { out[r.from] = r.data.presence; want.delete(r.from); }
    }
    if (want.size) await sleep(400);
  }
  return out;
}

// Who a message is for, and which of them has no session now. TO: that
// one address. TO-ROLE: every placed account whose binding holds the role
// — reached if ANY of them is running, since the role is addressed, not
// an instance. BROADCAST, or no addressing field at all: no check;
// everyone is not a set that can be offline.
// `placed` is every <host>/<login> placement, the only accounts that hold
// roles; `operators` may be addressed by TO as well (a second host's
// operator need not be placed), and a TO-ROLE never waits on them.
export async function checkAddressees(metadata, { from, token, placed, operators = [], ask = askPresence, waitMs = PRESENCE_WAIT_MS }) {
  if (metadata.BROADCAST || (!metadata.TO && !metadata['TO-ROLE'])) return { checked: false };
  if (metadata.TO) {
    const a = metadata.TO.trim();
    if (!placed.includes(a) && !operators.includes(a)) return { checked: true, problems: [{ kind: 'not-placed', address: a }] };
    const p = (await ask({ from, to: [a], expect: [a], token, waitMs }))[a];
    // A reply that could not read the process table is unknown, never
    // "no session" (review of #38).
    if (p === null) return { checked: true, problems: [{ kind: 'silent', address: a }] };
    if (p.status !== 'ok') return { checked: true, problems: [{ kind: 'unavailable', detail: `${a}: ${p.error ?? p.status}` }] };
    // Planning is said, never a refusal: the message waits in the relay
    // for the approved plan, which is what it would do anyway.
    return { checked: true, problems: p.online ? [] : [{ kind: 'offline', address: a, presence: p }],
             notes: p.online && p.planning ? [{ kind: 'planning', address: a }] : [] };
  }
  const role = metadata['TO-ROLE'].trim();
  const all = await ask({ from, to: '*', expect: placed, token, waitMs });
  const holders = Object.entries(all).filter(([, p]) => p?.status === 'ok' && p.role === role);
  const online = holders.filter(([, p]) => p.online);
  // A role is planning only when every running holder is: one that is
  // not will read the message now — and an account that did not answer
  // may be such a holder, so any silence withholds the note.
  const unknown = Object.values(all).some(p => p === null || p?.status !== 'ok');
  if (online.length) return { checked: true, problems: [],
    notes: !unknown && online.every(([, p]) => p.planning) ? online.map(([a]) => ({ kind: 'planning', address: a })) : [] };
  // No answer, or an answer that could not read its process table: either
  // may hide a running holder, and both are said as such.
  const silent = Object.entries(all).filter(([, p]) => p === null || p.status !== 'ok').map(([a]) => a);
  return { checked: true, problems: [{ kind: 'no-holder', role, holders: holders.map(([a]) => a), silent }] };
}

// The summary status of an answer (the CLI's exit code, header above).
export function exitCodeOf(answer) {
  if (answer.error !== undefined) return 6;
  const kinds = (answer.problems ?? []).map(p => p.kind === 'no-holder' && p.silent?.length ? 'silent' : p.kind);
  if (kinds.includes('unavailable')) return 6;
  if (kinds.includes('silent')) return 5;
  return kinds.length ? 4 : 0;
}

export async function cli(argv = process.argv.slice(2), input = () => fs.readFileSync(0, 'utf8'), ask = checkAddressees) {
  if (argv.length !== 1 || argv[0] !== 'check') { console.error('usage: presence.mjs check   (the request as JSON on stdin)'); return 2; }
  let req;
  // Never the parser's message: it quotes the input, and the input carries the token.
  try { req = JSON.parse(input()); } catch { console.error('presence: stdin is not one JSON object'); return 2; }
  if (!req || typeof req !== 'object' || !req.metadata || typeof req.metadata !== 'object' || typeof req.from !== 'string' || typeof req.token !== 'string') {
    console.error('presence: stdin needs {"metadata": {...}, "from": "<host>/<login>", "token": "<relay token>"}'); return 2;
  }
  let answer;
  try { answer = await ask(req.metadata, { from: req.from, token: req.token, placed: [...accountAddresses()], operators: [...operatorAddresses()] }); }
  catch (e) { answer = { error: String(e?.message ?? e).split('\n')[0].slice(0, 160), status: Number.isInteger(e?.status) ? e.status : null }; }
  console.log(JSON.stringify(answer));
  return exitCodeOf(answer);
}

if (process.argv[1] && fs.realpathSync(process.argv[1]) === fileURLToPath(import.meta.url))
  cli().then(c => process.exit(c), e => { console.log(JSON.stringify({ error: `presence: ${e?.message ?? e}`, status: null })); process.exit(6); });
