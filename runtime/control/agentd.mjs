// runtime/control/agentd.mjs — the control agent: one process per account,
// run as the login under its systemd user unit, answering the
// coordinator's requests on the control channel with what the account can
// say about itself (ops.mjs). The real-time control plane the CEO asked
// for on 2026-09-17: no sudo, no session, no model in the loop.
//
//   node runtime/control/agentd.mjs           the daemon: block, answer, repeat
//   node runtime/control/agentd.mjs --once    answer what is pending, then exit (tests)
//   node runtime/control/agentd.mjs --self    print this account's status locally, no relay
//
// THE CHANNEL. runtime/control/config.json names it (fabric:control) and
// the relay — the same one the fleet's GZCoord traffic rides. A control
// channel carries JSON records, not GZCOORD/1 messages, and no session
// ever drains it (inbox.mjs refuses a channel ending in :control). There
// is no point-to-point delivery: every agent reads every record and
// answers the ones addressed to it (`to` its address, a list holding it,
// or "*"); the coordinator reads the replies by `in_reply_to`.
//
// THE READ. No consumer cursor and no ack: the relay's `since_id` is an
// explicit cursor, so a restart never replays history — the agent primes
// from the newest record on the channel and waits after it, 55 s a poll.
// A `since_id_not_found` (the relay's history was cleared) re-primes.
//
// THE FENCE, v1. A request is answered only when its `from` is a host
// operator's address as runtime/hosts/registry.json places it — except a
// PUBLIC op (ops.mjs PUBLIC_OPS: `presence`), answered for any placed
// <host>/<login>, since every sender needs it and a relay-token holder
// could already get it by forging an operator's `from` on an unsigned
// read op — read
// again for every record, so a pull that changes the registry counts at
// once, and the identity section asks whoami() per request, so a rebind
// shows without a restart (review, 2026-09-17) — (a claim,
// not a proof — the relay verifies no sender; it stops any other session
// from asking), its op is one of the closed set, its `ts` plus `ttl_s` is
// not in the past, and its id was not seen before (an LRU of 256). An
// ACTION op (sign.mjs ACTION_OPS) additionally needs `sig`, an Ed25519
// signature by the operator's committed key, lives at most 10 minutes,
// and must be newer than the last action accepted from that operator (a
// ledger in the account's fabric state), and no more than a minute in
// its future. A read op takes no argument but `tokens`'s `days` (a number
// capped at 90); an action takes only its closed set (upgrade.mjs,
// secrets.mjs and jobs.mjs checkArgs). No field of a
// request ever reaches a shell; the answer carries no secret (ops.mjs).
//
// Every reply arrives: a section that cannot be read says so inline.
// Relay down: one line on stderr, retry every 30 s; a refused token is
// re-read once from the synced file (a rotation), then reported.

import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { whoami, FABRIC_ROOT, api, syncedToken, identity as gzIdentity, integrationConfig, inboxRoot, token as gzToken } from './gzcoord.mjs';
import { hostsRegistry } from './roots.mjs';
import { OPS, PUBLIC_OPS, collect, usage, accounts, accountSlugs, accountsDir, disk } from './ops.mjs';
import { jobsAdd } from './jobs.mjs';
import { poolAdd, poolList, poolClaim, poolHolder, roleFromStream } from './pool.mjs';
import { localPrune } from './local.mjs';
import { ACTION_OPS, ACTION_TTL_MAX_S, publicKeyFrom, verifyRequest } from './sign.mjs';
import { upgrade, stateDir } from './upgrade.mjs';
import { stateWatcher, STATE_POLL_MS } from './sessions.mjs';
import { secretsSync } from './secrets.mjs';
import { secretsSelftest } from './selftest.mjs';
import { sampler, SAMPLE_INTERVAL_MS } from './pressure.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
export const SEEN_MAX = 256;
export const USAGE_CACHE_MS = 10000;
// An observed account's sign-in lives 8 hours and only a read renews it,
// so the keeper reads every 4 h — twice inside the lifetime, so one failed
// read (the relay down, a harness update mid-run) is not a lapse. A
// request inside ACCOUNTS_CACHE_MS gets the last reading, not a new harness run.
export const ACCOUNTS_KEEPALIVE_MS = 4 * 3600 * 1000;
export const ACTION_CLOCK_SKEW_MS = 60 * 1000;
export const ACCOUNTS_CACHE_MS = 5 * 60 * 1000;

// One reading at a time, shared: the keeper's timer and a request that
// arrive together wait on the same run, because two harness runs on one
// config directory race for its refresh lock.
export function accountsKeeper(read = () => accounts(), { now = Date.now, cacheMs = ACCOUNTS_CACHE_MS } = {}) {
  let at = 0, last = null, running = null;
  const refresh = () => (running ??= Promise.resolve().then(read).then(r => { last = r; at = now(); return r; }).finally(() => { running = null; }));
  const cached = () => (last && now() - at < cacheMs) ? Promise.resolve(last) : refresh();
  return { refresh, cached };
}

// Reads that run beside the read loop, like the actions: each can take
// minutes, and the loop must keep answering behind it.
export const BESIDE_LOOP_OPS = ['disk'];
// One disk scan per daemon, shared by every request that arrives while it
// runs, and its answer kept a minute: any placed account may post the read
// unsigned, and fifty requests started a hundred du (review of #92,
// round 4). The keeper is accountsKeeper's: one read in flight at a time.
export const DISK_CACHE_MS = 60000;

export function controlConfig(env = process.env, file = path.join(HERE, 'config.json')) {
  let own = {};
  try { own = JSON.parse(fs.readFileSync(file, 'utf8')); } catch { /* defaults below */ }
  return {
    relay_url: env.CLAUDE_BRIDGE_URL ?? own.relay_url ?? 'http://127.0.0.1:8765',
    channel: env.FABRIC_CONTROL_CHANNEL ?? own.channel ?? 'fabric:control',
    // Session state rides its own channel (ADR-029 rule 16), named to end
    // in :control like the control channel, so no inbox ever drains it.
    state_channel: env.FABRIC_STATE_CHANNEL ?? own.state_channel ?? 'fabric:state:control',
    ttl_s: Number(own.ttl_s) > 0 ? Number(own.ttl_s) : 30,
  };
}

// Each operator's public key (`operator_key`), read like the addresses:
// again for every record, so a rotation committed to the registry counts
// at the next pull. A host with no key, or a malformed one, has none — its
// operator can still ask what an account reports, and can order nothing.
export function operatorKeys(registry = hostsRegistry({ engine: FABRIC_ROOT, emptyIsSet: true })) {
  const out = new Map();
  try {
    const d = JSON.parse(fs.readFileSync(registry, 'utf8'));
    for (const [h, v] of Object.entries(d.hosts ?? {})) { const k = publicKeyFrom(v.operator_key); if (k) out.set(`${h}/${v.operator ?? 'user'}`, k); }
  } catch { /* no registry: no keys */ }
  return out;
}

// The operators: <host>/<operator> for every host in the registry.
export function operatorAddresses(registry = hostsRegistry({ engine: FABRIC_ROOT, emptyIsSet: true })) {
  try {
    const d = JSON.parse(fs.readFileSync(registry, 'utf8'));
    return new Set(Object.entries(d.hosts ?? {}).map(([h, v]) => `${h}/${v.operator ?? 'user'}`));
  } catch { return new Set(); }
}

// Every placed account: <host>/<login> for each placement — who may ask a
// public op (ops.mjs PUBLIC_OPS).
export function accountAddresses(registry = hostsRegistry({ engine: FABRIC_ROOT, emptyIsSet: true })) {
  try {
    const d = JSON.parse(fs.readFileSync(registry, 'utf8'));
    return new Set(Object.entries(d.placement ?? {}).map(([login, host]) => `${host}/${login}`));
  } catch { return new Set(); }
}

export function newId() {
  // UUIDv7: time-ordered, unique by construction; the same shape gzmsg new-id mints.
  const t = BigInt(Date.now());
  const b = crypto.randomBytes(16);
  b[0] = Number((t >> 40n) & 0xffn); b[1] = Number((t >> 32n) & 0xffn); b[2] = Number((t >> 24n) & 0xffn);
  b[3] = Number((t >> 16n) & 0xffn); b[4] = Number((t >> 8n) & 0xffn); b[5] = Number(t & 0xffn);
  b[6] = (b[6] & 0x0f) | 0x70; b[8] = (b[8] & 0x3f) | 0x80;
  const h = b.toString('hex');
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
}

// The replay defence for ACTIONS, persisted: the newest accepted action's
// timestamp per operator, in the account's fabric state. The seen-id LRU is
// in memory — a restart empties it, and 256 unsigned read requests evict
// it — so a signed action copied off the channel could be posted again
// inside its lifetime and stop a session again (review of #34). An action
// is accepted only when strictly newer than the last one from its sender.
export function actionLedger(file = path.join(stateDir(), 'actions-seen.json')) {
  const read = () => { try { const d = JSON.parse(fs.readFileSync(file, 'utf8')); return d && typeof d === 'object' ? d : {}; } catch { return {}; } };
  return {
    floor: from => Number(read()[from]) || 0,
    record(from, ts) {
      const d = read(); if ((Number(d[from]) || 0) >= ts) return;
      d[from] = ts;
      fs.mkdirSync(path.dirname(file), { recursive: true });
      const tmp = `${file}.${process.pid}.tmp`;
      fs.writeFileSync(tmp, JSON.stringify(d) + '\n', { mode: 0o600 });
      fs.renameSync(tmp, file);
    },
  };
}

// Is this record a request this agent answers? The reason when not, for
// the log; never an error, never a reply.
export function accept(rec, { me, operators, accounts = new Set(), keys = new Map(), ttl_s, seen, now = Date.now(), actionFloor = () => 0 }) {
  let r;
  try { r = JSON.parse(rec.content); } catch { return { ok: false, why: 'not json' }; }
  if (!r || r.kind !== 'request') return { ok: false, why: 'not a request' };
  if (r.v !== 1) return { ok: false, why: `v ${r.v}` };
  if (typeof r.id !== 'string' || !r.id) return { ok: false, why: 'no id' };
  if (seen.has(r.id)) return { ok: false, why: 'seen' };
  const to = Array.isArray(r.to) ? r.to : [r.to];
  if (!to.includes('*') && !to.includes(me.address)) return { ok: false, why: 'not for me' };
  if (!OPS.includes(r.op)) return { ok: false, why: `op ${String(r.op).slice(0, 20)}` };
  const asker = typeof r.from === 'string' && (operators.has(r.from) || (PUBLIC_OPS.includes(r.op) && accounts.has(r.from)));
  if (!asker) return { ok: false, why: `from ${String(r.from).slice(0, 40)} is not an operator${PUBLIC_OPS.includes(r.op) ? ' or a placed account' : ''}` };
  const action = ACTION_OPS.includes(r.op);
  // An action is ordered, not asked: only a signature by the operator's
  // own key (runtime/control/sign.mjs) proves the operator sent it.
  if (action && !verifyRequest(r, keys.get(r.from))) return { ok: false, why: `${r.op}: not signed by ${String(r.from).slice(0, 40)}'s key` };
  const ts = Date.parse(r.ts);
  const ttl = Number(r.ttl_s) > 0 ? Math.min(Number(r.ttl_s), action ? ACTION_TTL_MAX_S : 3600) : ttl_s;
  if (!Number.isFinite(ts) || ts + ttl * 1000 < now) return { ok: false, why: 'expired' };
  // An action dated in the future would raise the ledger's floor past
  // every honest action that follows until the clock caught up — one
  // request signed on a fast clock locks the operator out (review of #34).
  if (action && ts - now > ACTION_CLOCK_SKEW_MS) return { ok: false, why: `${r.op}: dated ${Math.round((ts - now) / 1000)} s in the future (the operator's clock?)` };
  if (action && !(ts > actionFloor(r.from))) return { ok: false, why: `${r.op}: not newer than the last action accepted from ${String(r.from).slice(0, 40)} (a replay)` };
  return { ok: true, request: r, ts };
}

// A pull that changes the daemon's own code must reach the daemon: a
// loaded module never reloads, so the process ends itself (after a 2 s
// quiet period, a pull writes several files) and the unit's Restart=
// starts the next one on the new tree. What is watched is the directory
// the daemon imports from, never a file's content: since GZCoord's
// functions moved into runtime/control/gzcoord.mjs (ADR-040 §7) that is
// this one alone, and a change to the scripts it no longer loads, the
// Python port above all, must not restart it (review of #91).
export function watchSource(onChange, dirs = [HERE]) {
  let timer = null;
  const arm = (ev, name) => { if (!name || !/\.(mjs|json)$/.test(String(name))) return; clearTimeout(timer); timer = setTimeout(onChange, 2000); };
  return dirs.map(d => { try { const w = fs.watch(d, arm); w.unref(); return w; } catch { return null; } });
}

// Leaving for new code waits for every running action: the source watch
// fired the moment an `upgrade fabric` pulled this daemon's own code, and
// exiting then killed the process before it posted the reply the operator
// was waiting for. request() asks to leave; settle() is called as each
// action finishes, and leaves once none is left. A disk read runs there
// too (BESIDE_LOOP_OPS), so a restart also waits for a scan in flight.
export function leaver({ inflight, exit = code => process.exit(code), log = m => console.error(m) }) {
  let why = null;
  const settle = () => {
    if (why === null || inflight.size) return false;
    log(`agentd: ${why}; exiting for systemd to restart on the new code`);
    exit(0);
    return true;
  };
  return { request: reason => { why = why ?? reason; return settle(); }, settle, get pending() { return why; } };
}

export function remember(seen, id) {
  seen.add(id);
  if (seen.size > SEEN_MAX) seen.delete(seen.values().next().value);
}

/**
 * How a state record leaves: on the state channel, never the control
 * channel, whose replies would push it out of a reader's window (ADR-029
 * rule 16).
 */
export function statePoster(call, cfg, address) {
  return content => call('/api/send', { method: 'POST', body: JSON.stringify({ channel: cfg.state_channel, sender: address, content: JSON.stringify(content) }) });
}

/**
 * The record agentd posts once when it comes up (protocol.mjs).
 * @param {string} address
 * @returns {import('./protocol.mjs').Up}
 */
export function upRecord(address) { return { v: 1, kind: 'up', from: address, ts: new Date().toISOString() }; }

// A reply is one record; a `memory` reply is several: the first carries
// the bundles' reports and sizes, then one record per part
// ({part, parts, slug, chunk}) — the relay's message limit is 128 KiB and
// a drain is bigger. The coordinator reassembles by slug and part and
// verifies the sha256 the first record names.
/**
 * @param {import('./protocol.mjs').Request} request
 * @returns {Promise<import('./protocol.mjs').Reply & { _followups?: import('./protocol.mjs').Reply[] }>}
 */
export async function answer(request, ctx) {
  const days = Number(request.days);
  const data = request.op === 'ping' ? {} : request.op === 'upgrade' ? { upgrade: await upgrade(request, { me: ctx.me.address, ...ctx.upgradeOpts }) }
    : request.op === 'secrets-sync' ? { 'secrets-sync': await secretsSync(request, { me: ctx.me.address, ...ctx.secretsOpts }) }
    : request.op === 'jobs-add' ? { 'jobs-add': await jobsAdd(request, { home: ctx.home, root: ctx.root, ...(ctx.jobsOpts ?? {}) }) }
    : request.op === 'pool-add' ? { 'pool-add': poolAdd(request, { me: ctx.me.address, holder: poolHolder(controlConfig()), ...(ctx.poolOpts ?? {}) }) }
    : request.op === 'pool-list' ? { 'pool-list': poolList(request, { me: ctx.me.address, holder: poolHolder(controlConfig()), ...(ctx.poolOpts ?? {}) }) }
    : request.op === 'pool-claim' ? { 'pool-claim': await poolClaim(request, { me: ctx.me.address, holder: poolHolder(controlConfig()), ...(ctx.poolOpts ?? {}) }) }
    : request.op === 'local-prune' ? { 'local-prune': await localPrune(request, { home: ctx.home, root: ctx.root }) }
    : request.op === 'secrets-selftest' ? { 'secrets-selftest': await secretsSelftest(request, { home: ctx.home, root: ctx.root, ...(ctx.selftestOpts ?? {}) }) }
    : await collect(request.op, Number.isFinite(days) && days > 0 ? { ...ctx, days: Math.min(days, 90) } : ctx);
  const head = () => ({ v: 1, kind: 'reply', id: newId(), in_reply_to: request.id, from: ctx.me.address, op: request.op, ts: new Date().toISOString(), ok: true });
  const meta = { agentd: { pid: process.pid, started: ctx.started, uptime_s: Math.round((Date.now() - Date.parse(ctx.started)) / 1000) } };
  if (request.op !== 'memory' || !data.memory?.bundles) return { ...head(), data: { ...data, ...meta } };
  const parts = [];
  const bundles = data.memory.bundles.map(b => { const { _parts, ...rest } = b; for (let i = 0; i < (_parts ?? []).length; i++) parts.push({ slug: b.slug, part: i + 1, parts: _parts.length, chunk: _parts[i] }); return rest; });
  const first = { ...head(), data: { memory: { ...data.memory, bundles }, ...meta, parts: parts.length } };
  return { ...first, _followups: parts.map(p => ({ ...head(), data: { part: p } })) };
}

export async function main(argv = process.argv.slice(2)) {
  const once = argv.includes('--once');
  const self = argv.includes('--self');
  const who = whoami();
  const me = gzIdentity(who);
  const cfg = controlConfig();
  const started = new Date().toISOString();
  let usageAt = 0, usageLast = null;
  const usageCached = async () => { if (Date.now() - usageAt > USAGE_CACHE_MS) { usageLast = await usage(); usageAt = Date.now(); } return usageLast; };
  const keeper = accountsKeeper();
  const diskKeeper = accountsKeeper(() => disk(), { cacheMs: DISK_CACHE_MS });
  const ctx = { me, started, usageCached, accountsCached: keeper.cached, diskCached: diskKeeper.cached };   // no `who`: identity() resolves it per request
  if (self) { const { _followups, ...r } = await answer({ id: 'self', op: 'status' }, ctx); console.log(JSON.stringify(r, null, 2)); return 0; }

  const root = inboxRoot(who);
  const gz = integrationConfig(who.project);
  let tok = gzToken(root, gz.configured ? gz : undefined) ?? syncedToken();
  if (!tok) { console.error('agentd: no CLAUDE_BRIDGE_AUTH_TOKEN (fabric-secrets sync) — nothing to read with'); return 3; }
  if (operatorAddresses().size === 0) { console.error('agentd: no host operator in runtime/hosts/registry.json — nothing could ever be answered; not starting'); return 3; }
  const seen = new Set();
  const ledger = actionLedger();
  const inflight = new Set();   // actions and disk reads running beside the loop; --once and a restart wait for them
  // What is not logged: every reply on the channel (not a request), a
  // request for another account (not for me) and a duplicate (seen) —
  // fifteen daemons times fifteen replies per fabric-ctl would be noise.
  // Every other refusal is one line, so a refused operator can be found.
  const QUIET = new Set(['not a request', 'not for me', 'seen']);
  const q = o => new URLSearchParams(o).toString();
  const call = async (p, init) => {
    try { return await api(tok, p, { relayUrl: cfg.relay_url, ...init }); }
    catch (e) {
      const fresh = (e.status === 401 || e.status === 403) ? syncedToken() : undefined;
      if (fresh && fresh !== tok) { tok = fresh; console.error('agentd: token refused; retrying with the synced value'); return api(tok, p, { relayUrl: cfg.relay_url, ...init }); }
      throw e;
    }
  };
  const post = content => call('/api/send', { method: 'POST', body: JSON.stringify({ channel: cfg.channel, sender: me.address, content: JSON.stringify(content) }) });
  // A claimant's role is what its own control agent last said on the state channel.
  ctx.poolOpts = { roleOf: roleFromStream({ call, cfg }) };

  let last = null, down = false;
  const prime = async () => {
    const page = await call(`/api/messages?${q({ channel: cfg.channel, limit: '1' })}`);
    const rows = page.messages ?? page;
    if (rows.length) { last = rows[rows.length - 1].id; return; }
    const up = await post(upRecord(me.address));
    last = up.id;
  };
  console.error(`agentd: ${me.address} on ${cfg.channel} at ${cfg.relay_url}; operators: ${[...operatorAddresses()].join(' ')}`);
  const leave = leaver({ inflight });
  if (!once) watchSource(() => leave.request('source changed'));
  if (!once) {
    // At start too: after a reboot every observed sign-in may have lapsed.
    const keep = () => { if (!accountSlugs(accountsDir()).length) return; keeper.refresh().then(r => { for (const a of r.accounts ?? []) if (a.status !== 'ok') console.error(`agentd: account ${a.slug}: ${a.status}${a.error ? ` (${a.error})` : ''}`); }).catch(e => console.error(`agentd: accounts: ${e.message}`)); };
    setTimeout(keep, 30000).unref();
    setInterval(keep, ACCOUNTS_KEEPALIVE_MS).unref();
    // Only the resident daemon samples: a --once run would add a lone
    // sample with no minute behind it.
    const pressure = sampler();
    pressure.tick();
    setInterval(pressure.tick, SAMPLE_INTERVAL_MS).unref();
    // What the account's sessions are doing, posted when it changes
    // (sessions.mjs); first at start, so a restart re-says it.
    const states = stateWatcher({ address: me.address, post: statePoster(call, cfg, me.address), binding: who.binding,
      jobs: path.join(stateDir(), 'jobs.json') });
    states.tick();
    setInterval(states.tick, STATE_POLL_MS).unref();
  }
  for (;;) {
    try {
      if (!last) await prime();
      const page = await call(`/api/wait?${q({ channel: cfg.channel, since_id: last, timeout_seconds: once ? '3' : '55', limit: '50' })}`);
      if (down) { console.error('agentd: relay is back'); down = false; }
      if (page.warning === 'since_id_not_found') { last = null; continue; }
      const rows = page.messages ?? [];
      for (const rec of rows) {
        last = rec.id;
        const a = accept(rec, { me, operators: operatorAddresses(), accounts: accountAddresses(), keys: operatorKeys(), ttl_s: cfg.ttl_s, seen, actionFloor: ledger.floor });
        if (!a.ok) { if (!QUIET.has(a.why)) console.error(`agentd: ignored a record ${JSON.stringify(a.why)}`); continue; }
        remember(seen, a.request.id);
        // An action can take minutes (a session to stop, an install): run
        // it beside the loop, so the daemon keeps answering — a request that
        // waited behind it would expire unanswered. Its reply is posted when
        // it is done; one action at a time is the action's own rule.
        if (ACTION_OPS.includes(a.request.op)) {
          const { op, from, id } = a.request;
          // Recorded before it runs, so a replay posted while it runs is refused
          // too; a ledger that cannot be written refuses the action BY NAME —
          // thrown here it read as "relay unreachable" and the action vanished.
          try { ledger.record(from, a.ts); }
          catch (e) { console.error(`agentd: ${op} for ${from} refused: the action ledger could not be written (${e.code ?? e.message})`); continue; }
          console.error(`agentd: started ${op} for ${from} (${id.slice(0, 8)})`);
          let moved = false;
          const p = answer(a.request, ctx).then(async reply => { const { _followups, ...first } = reply; moved = first.data?.upgrade?.restart_daemon === true; await post(first); console.error(`agentd: answered ${op} for ${from} (${id.slice(0, 8)}): ${first.data?.[op]?.status ?? '?'}`); })
            .catch(e => console.error(`agentd: ${op} for ${from} failed to answer: ${e.message}`))
            .finally(() => { inflight.delete(p); if (!once) { if (moved) leave.request('the fabric moved (upgrade fabric)'); else leave.settle(); } });
          inflight.add(p);
          continue;
        }
        // A read that walks a whole home (disk) can take minutes on a large
        // one: it answers beside the loop too, or every request behind it —
        // a sender's presence question, which waits seconds — would go
        // unanswered and read as silent. No ledger: it is a read.
        if (BESIDE_LOOP_OPS.includes(a.request.op)) {
          const { op, from, id } = a.request;
          const p = answer(a.request, ctx).then(async reply => { const { _followups, ...first } = reply; await post(first); console.error(`agentd: answered ${op} for ${from} (${id.slice(0, 8)})`); })
            .catch(e => console.error(`agentd: ${op} for ${from} failed to answer: ${e.message}`))
            .finally(() => { inflight.delete(p); if (!once) leave.settle(); });
          inflight.add(p);
          continue;
        }
        const reply = await answer(a.request, ctx);
        const { _followups, ...firstReply } = reply;
        await post(firstReply);
        for (const f of _followups ?? []) await post(f);
        console.error(`agentd: answered ${a.request.op} for ${a.request.from} (${a.request.id.slice(0, 8)})`);
      }
      // An action already started has stopped a session and written a
      // marker: exiting under it would leave the launcher waiting on a
      // pending upgrade and no reply posted (review of #34).
      if (once) { await Promise.allSettled([...inflight]); return 0; }
    } catch (e) {
      if (once) await Promise.allSettled([...inflight]);   // every exit of --once, not only the clean one
      if (e.status === 401 || e.status === 403) { console.error(`agentd: the relay refused this token (HTTP ${e.status}); rotated? run fabric-secrets sync`); if (once) return 4; }
      else if (!down) { console.error(`agentd: relay unreachable at ${cfg.relay_url} (${e.message}) — retrying every 30 s`); down = true; }
      if (once) return 1;
      await new Promise(r => setTimeout(r, 30000));
    }
  }
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) main().then(c => process.exit(c)).catch(e => { console.error(`agentd: ${e.message}`); process.exit(1); });
