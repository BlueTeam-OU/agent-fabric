#!/usr/bin/env node
// GZCoord inbox: what the relay holds for THIS session, delivered the way
// SPEC §17 says a recipient receives — body read only if addressed to it.
//
// Two modes, one tool:
//   node communication/gzcoord/scripts/inbox.mjs            drain: return at once
//   node communication/gzcoord/scripts/inbox.mjs --follow   the watch: block for the
//                                        life of the session, print each delivery
//                                        as it lands, never return on a quiet spell
//   node communication/gzcoord/scripts/inbox.mjs --wait [S] block up to S seconds
//   node communication/gzcoord/scripts/inbox.mjs --replay <seq|message-id>
//                                        re-read ONE message already past the cursor
//                                        (the cursor does not move; a body not
//                                        addressed to this session is not shown)
//   node communication/gzcoord/scripts/inbox.mjs --held   is this account's inbox
//                                        held (the session is planning)? exit 0
//                                        held, 1 not; one line either way
//                                                  TOTAL (default 1800 —
//                                                  thirty minutes) and
//                                                  return the moment
//                                                  something lands
//
// The relay's long-poll ceiling is 55 s per HTTP call; --wait chains those
// calls until the TOTAL budget is spent, so one arm covers half an hour
// instead of one poll. Each call is min(55, remaining), and the moment a
// slice returns a message the loop exits and delivers — the wake latency
// is unchanged. A total budget, not a per-call one, is the point: arming
// every 55 seconds was the noise the waiter exists to remove.
//
// The drain runs from the SessionStart hook in .claude/settings.json, so a
// session begins knowing what arrived while it was away. The wait is the
// PRIMITIVE of the watch, not the watch: one arm returns on a message
// addressed to this session or when the budget expires quiet, and the
// harness wakes the session with the return. It is one-shot by design —
// a process that never exits never notifies — and the procedure around
// it is --follow: one process under a Monitor, armed at the session's
// first turn and re-armed at each expiry notice, since the Monitor is
// timed (skills/gzcoord-receive). It prints a delivery when one
// lands and nothing on a quiet spell — no budget, no expiry line, no
// shell loop around it, no restart every half hour. It says once when
// the relay stops answering and once when it is back, and exits 4 on a
// refused token (a rotation: sync, then arm again). The session re-arms
// it at each expiry, and after a resume, which the harness does not
// restore. The
// earlier shapes — a hand-re-armed --wait, then a shell loop around
// --wait 1800 — are retired: the first went deaf when a session forgot,
// the second produced a quiet-expiry line to filter every thirty minutes.
//
// The WAIT exits only on a message addressed to this session (SPEC §7.1:
// a broadcast, `TO` its address, or `TO-ROLE` its slug). Anything else —
// including a message this session itself sent — passes through the arm
// acknowledged but unprinted, and the arm continues: waking a session for
// its neighbours' traffic is the noise this tool exists to remove, and
// every such wake is context spent on someone else's work. The drain
// (SessionStart) still lists non-addressed messages by their metadata
// line; only the wait is silent about them.
//
// The addressee rule is applied HERE, at delivery, not left to the reader:
// a message whose TO is not this address, whose TO-ROLE is not this role,
// and which is not a broadcast is listed by its metadata line and its body
// is not printed. That is the filter the evaluation said a transport should
// do, enforced where it costs nobody's context (the relay host project's projects/<id>/integration/gzcoord/BRIDGE-RELAY-SETUP.md).
//
// Never blocks a session start: relay down, no token, no catalogue — each
// is one line on stderr and exit 0.
//
// THE HOLD (2026-09-16). A plan is written from the context the session
// had when it entered plan mode; a delivery landing mid-plan is context
// the plan was not asked to absorb. The harness cannot pause
// notifications, but a delivery is a notification only because this
// watch polls and prints — so while the session plans, the watch does not
// poll. The session says so through a marker the plan-hold hook writes
// (runtime/claude-code/hooks/plan-hold.sh: ~/.cache/agent-fabric/hold/
// <pid>.json, one per planning session, naming the harness pid and its
// start time); the watch honours a marker while that harness is alive and
// checks before every slice, cutting a slice already in flight the moment
// one appears. Nothing is consumed while held — the
// relay keeps the cursor and re-shows what was not acknowledged — and the
// first poll after the marker clears delivers everything at once, at the
// session's next turn boundary. Held is a line on stderr, never stdout:
// stdout is what the Monitor turns into notifications.

import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { execFileSync, spawn } from 'node:child_process';
import { parse, validate, normalize, loadTaxonomy, findTaxonomy, slugOf, recordedRole, whoami, FABRIC_ROOT, invokedAsMain, RETIRED_TYPES } from './gzmsg.mjs';
import { defaultDictionaryOrEmpty, dictionary, localeReminder, printer } from './i18n.mjs';

// Every line below is printed through `t`, the catalogue of the login
// that reads it (i18n.mjs). main() resolves the login's once and
// passes it down; the default locale here is the default of each exported
// function, so a caller that has no session — a test, another tool —
// gets today's English without a whoami() and without a locale.
let EN;
const en = () => (EN ??= printer(defaultDictionaryOrEmpty()));

// Project integration: which relay, which channel, where the token and
// the hosted relay's runtime live. It comes from the PROJECT —
// projects/<id>/integration/gzcoord/config.json, found through the
// working copy's project (whoami().project) — or from the environment
// (CLAUDE_BRIDGE_URL and GZCOORD_CHANNEL together). Nothing else: a
// project with neither is NOT configured, and both entry points say so
// and stop. Until 2026-09-16 the defaults here were one project's, so a
// working copy of any other project silently joined that project's channel
// with its token file — project truth in generic code (review, 2026-09-16).
// token_env_file is relative to the working copy (a clone carries its
// own token); relay_runtime_dir is relative to the WORKSPACE — the
// projects/ directory the fabric checkout sits in — because the relay's
// database, token and venv are host state, not project state: they must
// not live inside any repository, gitignored or not.
export const WORKSPACE = path.dirname(FABRIC_ROOT);
export function relayRuntimeDir(cfg, workspace = WORKSPACE) {
  return path.resolve(workspace, cfg.relay_runtime_dir ?? '.gzcoord');
}
export function integrationConfig(project, env = process.env, t = en()) {
  const file = project ? path.join(FABRIC_ROOT, 'projects', project, 'integration', 'gzcoord', 'config.json') : null;
  if (file) {
    try {
      const own = JSON.parse(fs.readFileSync(file, 'utf8'));
      if (own.relay_url && own.channel)
        return { configured: true, source: file, relay_runtime_dir: '.gzcoord', ...own,
                 relay_url: env.CLAUDE_BRIDGE_URL ?? own.relay_url, channel: env.GZCOORD_CHANNEL ?? own.channel };
    } catch { /* no file, or not JSON: the environment may still configure it */ }
  }
  if (env.CLAUDE_BRIDGE_URL && env.GZCOORD_CHANNEL)
    return { configured: true, source: 'environment', relay_url: env.CLAUDE_BRIDGE_URL, channel: env.GZCOORD_CHANNEL, relay_runtime_dir: '.gzcoord' };
  const where = project ? `projects/${project}/integration/gzcoord/config.json` : t('config.where-registered');
  return { configured: false, source: null,
           reason: t('config.not-configured', {
             what: project ? t('config.for-project', { project }) : t('config.for-working-copy'), where }) };
}
// Module-level defaults for callers that import ensureRelay/api directly;
// main() resolves the project's own values.
const RELAY = process.env.CLAUDE_BRIDGE_URL ?? 'http://127.0.0.1:8765';

function gitToplevel() {
  try { return execFileSync('git', ['rev-parse', '--show-toplevel'], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] }).trim(); }
  catch { return null; }
}
// The working copy the inbox reads its token and integration from. Inside
// a checkout that is the checkout. Outside one — a session started in the
// workspace (projects/) — identity.py reports the project from the binding
// but no working copy, so the binding's own working_copy (the checkout the
// role was activated in) is the root; the cwd is only the last resort.
// A channel whose name ends in ":control" carries the fabric's machine
// records (runtime/control/: requests a per-account daemon answers with
// usage, identity, key fingerprints), not GZCOORD/1 messages, and no
// session may ever drain or send on it — a control record printed into a
// session's context is exactly what the control plane exists to avoid,
// and the env override GZCOORD_CHANNEL would otherwise let one be named
// (decided 2026-09-17). Throws; the CLIs print it and exit 2 before any
// request reaches the relay.
export function assertNotControlChannel(channel, t = en()) {
  if (typeof channel === 'string' && /:control$/.test(channel))
    throw new Error(t('config.control-channel', { channel }));
}

export function inboxRoot(who) {
  const top = gitToplevel();
  if (top) return top;
  if (who.working_copy) return who.working_copy;
  try {
    const b = JSON.parse(fs.readFileSync(who.binding, 'utf8'));
    if (b.working_copy && fs.existsSync(b.working_copy)) return b.working_copy;
  } catch { /* no binding */ }
  return process.cwd();
}

// The token, from wherever this working copy keeps it; never printed, never logged.
// The environment comes first: fabric-secrets sync exports the token
// there from the account's Doppler config, which is how an enrolled
// account gets it. The file lookups serve a clone provisioned by hand.
export function token(root, cfg = integrationConfig()) {
  // The synced file first: it is what fabric-secrets sync writes, and the
  // environment is only a copy of it taken when the session's shell
  // started — a snapshot the harness never refreshes, so after a rotation
  // it stays wrong for the life of the session while the file is current
  // (web-dev-01, 2026-09-14: one refused call per re-arm, for hours).
  const synced = syncedToken();
  if (synced) return synced;
  if (process.env.CLAUDE_BRIDGE_AUTH_TOKEN) return process.env.CLAUDE_BRIDGE_AUTH_TOKEN;
  const env = cfg.token_env_file ? path.join(root, cfg.token_env_file) : null;
  if (env && fs.existsSync(env))
    for (const line of fs.readFileSync(env, 'utf8').split('\n'))
      if (line.startsWith('CLAUDE_BRIDGE_AUTH_TOKEN=')) return line.slice('CLAUDE_BRIDGE_AUTH_TOKEN='.length).trim();
  const local = path.join(root, '.claude/settings.local.json');
  try { const t = JSON.parse(fs.readFileSync(local, 'utf8')).env?.CLAUDE_BRIDGE_AUTH_TOKEN; if (t) return t; } catch {}
  // The hosting workspace holds the token the relay itself reads
  // (projects/.gzcoord/bridge-token, mode 0600): a session there — in
  // whichever working copy, or in none — is the host and needs no copy.
  try { const t = fs.readFileSync(path.join(relayRuntimeDir(cfg), 'bridge-token'), 'utf8').trim(); if (t) return t; } catch {}
  return undefined;
}

// Who this session is: the instance half of the address is the AGENT — the Linux login, from
// runtime/identity.py via whoami() — never the working copy's basename;
// the host is the short hostname; the role comes from the agent's runtime
// binding, else from a slug the login happens to carry. The working copy
// the session runs in is context (SPEC §3.1) and plays no part here.
export function identity(me = whoami(), taxonomy) {
  const instance = me.agent;
  const host = me.host ?? os.hostname().split('.')[0];
  const recorded = taxonomy ? recordedRole(taxonomy, me) : { role: undefined };
  const slug = recorded.role ?? (taxonomy ? slugOf(instance, taxonomy) : undefined);
  // A binding naming a role the catalogue lacks falls back to the login's
  // role; the error travels with the identity so each caller says it,
  // rather than the fallback happening in silence (review of #55).
  return { address: `${host}/${instance}`, instance, slug, project: me.project, ...(recorded.error ? { roleError: recorded.error } : {}) };
}

// SPEC §7.1 addressing, SPEC §17 reading rule.
export function forMe(msg, me) {
  const m = msg.metadata;
  if (m.BROADCAST === 'true') return true;
  if (m.TO !== undefined) return m.TO === me.address;
  if (m['TO-ROLE'] !== undefined) return me.slug !== undefined && m['TO-ROLE'] === me.slug;
  return false;
}

// The hosting workspace — the one whose runtime dir holds the relay's
// venv, token and database (projects/.gzcoord/, outside every
// repository) — is the fabric-coordinator's (a project integration rule,
// not a protocol one). The host's session start is the activation of
// whatever hosts the relay: the systemd user unit where bootstrap
// installed one (supervised, restarted on failure, outlives the
// session), else a detached spawn that lives as long as the session. If
// the relay is not answering, bring it up before draining, exactly as
// the runbook says. Workspaces without the venv return false and skip
// silently: they are clients, not hosts, and nothing in a client session
// may try to host.
export function ensureRelay(runtimeDir, relayUrl = RELAY, t = en()) {
  const bin = path.join(runtimeDir, 'venv', 'bin', 'claude-bridge');
  if (!fs.existsSync(bin)) return { hosted: false, started: false };
  try { execFileSync('curl', ['-sf', '-m', '2', `${relayUrl}/status`], { stdio: 'ignore' }); return { hosted: true, started: false }; }
  catch { /* down or unreachable: start it */ }
  const tokenFile = path.join(runtimeDir, 'bridge-token');
  const db = path.join(runtimeDir, 'claude-bridge.db');
  if (!fs.existsSync(tokenFile)) return { hosted: true, started: false, note: t('start.relay-no-token-file', { token_file: tokenFile }) };
  // Where bootstrap installed the relay's user unit and a user manager is
  // up, start THAT: a unit is supervised, restarted on failure, found by
  // name, and outlives the session; a detached spawn is none of those and
  // is the fallback for a host with no manager (a bare sudo -u, a test).
  const unit = process.env.GZCOORD_RELAY_UNIT ?? 'gzcoord-relay';
  const unitFile = path.join(process.env.HOME ?? os.homedir(), '.config', 'systemd', 'user', `${unit}.service`);
  // The user manager's bus: XDG_RUNTIME_DIR where the shell has it, else
  // the account's runtime dir — a `sudo -u` or the host executor gives
  // the shell neither, while the lingering account's manager is up all
  // the same. systemctl needs the dir in ITS environment, so it is
  // passed explicitly; a bus that is not a socket is a leftover, not a
  // manager.
  const runtime = process.env.XDG_RUNTIME_DIR ?? `/run/user/${process.getuid()}`;
  const bus = path.join(runtime, 'bus');
  const busIsSocket = () => { try { return fs.statSync(bus).isSocket(); } catch { return false; } };
  if (fs.existsSync(unitFile) && (busIsSocket() || process.env.GZCOORD_TEST_BUS_ANY === '1')) {
    let asked = false;
    try { execFileSync('systemctl', ['--user', 'start', unit], { stdio: 'ignore', timeout: 15000, env: { ...process.env, XDG_RUNTIME_DIR: runtime } }); asked = true; }
    catch { /* systemctl itself failed: the unit was never asked, so the spawn below is the fallback */ }
    if (asked) {
      for (let waited = 0; waited < 8000; waited += 500) {
        try { execFileSync('curl', ['-sf', '-m', '1', `${relayUrl}/status`], { stdio: 'ignore' });
          return { hosted: true, started: true, unit }; } catch { /* not up yet */ }
        Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 500);
      }
      return { hosted: true, started: false, note: t('start.relay-unit-silent', { unit, log: path.join(runtimeDir, 'bridge.log') }) };
    }
  }
  const out = fs.openSync(path.join(runtimeDir, 'bridge.log'), 'a');
  const child = spawn(bin, [
    '--host', '127.0.0.1', '--port', '8765',
    '--db', db, '--auth-token-file', tokenFile,
  ], { detached: true, stdio: ['ignore', out, out], unref: true });
  for (let waited = 0; waited < 8000; waited += 500) {
    try { execFileSync('curl', ['-sf', '-m', '1', `${relayUrl}/status`], { stdio: 'ignore' });
      return { hosted: true, started: true, pid: child.pid }; } catch { /* not up yet */ }
    Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 500);
  }
  return { hosted: true, started: false, note: t('start.relay-silent', { log: path.join(runtimeDir, 'bridge.log') }) };
}

export async function api(tok, pathAndQuery, { relayUrl = RELAY, ...init } = {}) {
  const r = await fetch(`${relayUrl}${pathAndQuery}`, {
    ...init,
    headers: { Authorization: `Bearer ${tok}`, 'Content-Type': 'application/json', ...(init.headers ?? {}) },
  });
  if (!r.ok) { const e = new Error(`${pathAndQuery} -> HTTP ${r.status}`); e.status = r.status; throw e; }
  return r.json();
}

// The synced token file, read fresh. The environment is a copy of it
// taken when the shell started — and in Claude Code every Bash call runs
// from a snapshot of the session's first shell, so after a rotation the
// environment keeps the dead value for the life of the session however
// many times fabric-secrets sync runs (web-dev-01, 2026-09-14). On a 401
// the inbox re-reads this file and retries once; only when the file
// agrees with the refused value is the rotation reported.
// One `export NAME=value` line of the synced secrets file, unquoted, or
// undefined. The value is a secret: a caller prints it nowhere and uses it
// in place (a header, a hash), which is what the control agent's key
// fingerprints and the token below do.
export function syncedVar(name, home = os.homedir()) {
  try {
    const re = new RegExp(`^export ${name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}=(.*)$`);
    for (const line of fs.readFileSync(path.join(home, '.config', 'agent-fabric', 'secrets.env'), 'utf8').split('\n')) {
      const m = re.exec(line);
      if (!m) continue;
      let v = m[1].trim();
      if ((v.startsWith("'") && v.endsWith("'")) || (v.startsWith('"') && v.endsWith('"'))) v = v.slice(1, -1);
      return v || undefined;
    }
  } catch { /* not enrolled, or no sync yet */ }
  return undefined;
}
export function syncedToken(home = os.homedir()) {
  return syncedVar('CLAUDE_BRIDGE_AUTH_TOKEN', home);
}

// A 401 is not "unreachable": the relay answered and refused the token.
// After a rotation every session started before it holds the dead value
// in its environment, and the fix is a re-sync, not a retry — say so, and
// exit 4 so a watch loop can stop instead of printing the same line for
// the rest of the session (web-dev-01, 2026-09-14).
function explainRelayError(e, relayUrl, t = en()) {
  if (e.status === 401 || e.status === 403)
    return { line: t('relay.refused', { relay_url: relayUrl, status: e.status }), code: 4 };
  return { line: t('relay.unreachable', { relay_url: relayUrl, detail: e.message }), code: 0 };
}

// Re-read one message that is already past this session's cursor — the
// case where a read was piped through something that dropped the body.
// Reads the channel's recent history (no consumer id, so no cursor moves),
// and shows the body only when the message is addressed to this session:
// SPEC §17 does not stop applying because the read is a replay.
async function replay(tok, relayUrl, channel, which, me, t = en()) {
  const page = await api(tok, `/api/messages?${new URLSearchParams({ channel, limit: '500', full: '1' })}`, { relayUrl });
  const list = page.messages ?? page;
  // By relay seq, or by the GZCoord MESSAGE-ID inside the body (the
  // relay's own id is a transport detail nobody quotes).
  const midOf = r => { try { return parse(normalize(r.content)).metadata?.['MESSAGE-ID']; } catch { return undefined; } };
  const rec = list.find(r => String(r.seq) === String(which) || r.id === which || midOf(r) === which);
  if (!rec) { console.error(t('replay.no-message', { which, n: list.length, channel })); return 1; }
  const text = normalize(rec.content);
  const when = rec.timestamp ?? rec.ts ?? '';
  let msg = null; try { msg = parse(text); } catch { /* shown as metadata only */ }
  if (!msg || !forMe(msg, me)) {
    console.log(t('replay.not-addressed', { seq: rec.seq, sender: rec.sender, when, address: me.address }));
    if (msg) console.log(`  ${oneLine(msg, t)}`);
    return 2;
  }
  console.log(t('replay.title', { seq: rec.seq, sender: rec.sender, when }));
  console.log('```text'); console.log(text.replace(/\n$/, '')); console.log('```');
  return 0;
}

// The addressing half is the WIRE's vocabulary, not this tool's: TO,
// TO-ROLE, broadcast and the type are matched by name across locales and
// are never translated (i18n.mjs). Only the missing-id placeholder is.
function oneLine(msg, t = en()) {
  const m = msg.metadata;
  const to = m.TO ? `TO ${m.TO}` : m['TO-ROLE'] ? `TO-ROLE ${m['TO-ROLE']}` : 'broadcast';
  return `${m['MESSAGE-ID'] ?? t('inbox.no-id')}  ${msg.type}  ${to}  ${m.SUBJECT ?? ''}`.trimEnd();
}

// One arm of the waiter. `delivered` iff some slice carried a message
// for this session. Every slice's messages are acknowledged before the
// loop continues or returns, so the cursor always advances past what was
// shown — and past what was passed: an acknowledgement means "shown this
// position", not "read the body".
// Alert keywords: reasons to stop waiting on a message that is NOT
// addressed to this session. Whole-token, case-insensitive, matched
// against the full message text (metadata + body — PR numbers live in
// REFERENCES). Guardrails against the abusable shape: 3+ characters (a
// 1–2 char token fires on nearly everything), at most 8 per arm, and a
// message from the armed session's own address never counts — a session
// must not wake on its own echo.
export const KEYWORD_MIN = 3;
export const KEYWORD_MAX = 8;
export function checkKeywords(keywords = [], t = en()) {
  const seen = [];
  for (const k of keywords) {
    if (typeof k !== 'string' || k.length < KEYWORD_MIN)
      throw new Error(t('keyword.too-short', { keyword: JSON.stringify(k), min: KEYWORD_MIN }));
    if (seen.includes(k)) continue;
    if (seen.length >= KEYWORD_MAX) throw new Error(t('keyword.too-many', { max: KEYWORD_MAX }));
    seen.push(k);
  }
  return seen;
}
export function keywordHit(text, keywords, ownAddress) {
  if (!keywords.length || !text) return false;
  const tokens = new Set(text.toLowerCase().split(/[^a-z0-9_-]+/).filter(Boolean));
  if (ownAddress)
    // The exemption removes each TOKEN of the own address — the address is
    // never one token, and a keyword naming another session's instance half
    // must still fire on that session's message.
    for (const t of ownAddress.toLowerCase().split(/[^a-z0-9_-]+/).filter(Boolean)) tokens.delete(t);
  return keywords.some(k => tokens.has(k.toLowerCase()));
}

// The hold markers: written by the plan-hold hook (one per planning
// session, <pid>.json under the login's own hold directory), read here.
// The account is held while ANY marker names a live harness of this
// login: the pid answers a signal as this uid (EPERM is another login's
// process, never our harness) and, when both sides know it, has the
// start time the marker recorded (a reused pid is not the harness). The
// directory and each file must be this login's, or nothing there is a
// hold — another login must not be able to hold or release this inbox.
export function holdDir(home = os.homedir()) {
  return process.env.AGENT_FABRIC_HOLD_DIR ?? path.join(home, '.cache', 'agent-fabric', 'hold');
}
export function pidStart(pid) {
  try { return fs.readFileSync(`/proc/${pid}/stat`, 'utf8').replace(/.*\) /s, '').split(' ')[19] ?? ''; } catch { return ''; }
}
export function pidAlive(pid) {
  try { process.kill(pid, 0); return true; } catch { return false; }
}
export function holdStatus(dir = holdDir(), { isAlive = pidAlive, startOf = pidStart, uid = process.getuid(), t = en() } = {}) {
  let st;
  try { st = fs.lstatSync(dir); } catch { return { held: false, reason: t('held.no-directory'), sessions: [] }; }
  if (st.isSymbolicLink() || !st.isDirectory()) return { held: false, reason: t('held.not-a-directory'), sessions: [] };
  if (st.uid !== uid) return { held: false, reason: t('held.not-this-login'), sessions: [] };
  const sessions = [], stale = [];
  for (const name of fs.readdirSync(dir)) {
    if (!/^\d+\.json$/.test(name)) continue;
    const file = path.join(dir, name);
    let m;
    try {
      if (fs.lstatSync(file).uid !== uid) { stale.push(t('held.stale-not-this-login', { name })); continue; }
      m = JSON.parse(fs.readFileSync(file, 'utf8'));
    } catch { stale.push(t('held.stale-unreadable', { name })); continue; }
    if (!Number.isInteger(m.pid) || m.pid <= 0) { stale.push(t('held.stale-no-pid', { name })); continue; }
    if (!isAlive(m.pid)) { stale.push(t('held.stale-gone', { name, pid: m.pid })); continue; }
    const now = startOf(m.pid);
    if (m.start && now && String(m.start) !== String(now)) { stale.push(t('held.stale-reused', { name, pid: m.pid })); continue; }
    sessions.push({ pid: m.pid, session_id: m.session_id, since: m.since });
  }
  if (!sessions.length) return { held: false, reason: stale.length ? stale.join('; ') : t('held.no-marker'), sessions };
  return { held: true, sessions };
}

export const HOLD_POLL_MS = 1000;
// `held` is consulted before every slice, once a second during one, and
// once more when the slice returns: a hold that begins mid-slice aborts
// the fetch, and a page that landed in the same second as the hold is
// dropped unread (nothing was acknowledged, so the relay re-shows it);
// the loop then waits, polling nothing, until the hold clears. `onHold`
// is told once per transition, for the stderr line. The guard's own
// sleep is cut when the slice ends, so a delivery waits for no tick.
// HELLO and GOODBYE are retired (SPEC §8) and a validator rejects them,
// but a session not yet relaunched may still send one, and the relay does
// not validate. Such a message is acknowledged and never delivered, not
// even as a line among the others: presence is the control plane's to
// answer (`fabric-ctl <login|all> presence`,
// docs/adr/ADR-030-presence-replaces-hello-and-goodbye.md), and on a busy
// day the announcements were most of what every watch printed (the owner,
// 2026-09-25). Tolerated rather than refused: the cursor must move past
// it. A replay by seq still shows one, by its metadata line: it carries no
// addressing field, so it is addressed to nobody (forMe).

export async function waitLoop({ fetchPage, ack, waitTotal, forMeFn = forMe, keywords = [], ownAddress,
                                 held = () => false, onHold = () => {}, holdPollMs = HOLD_POLL_MS, sleep = ms => new Promise(r => setTimeout(r, ms)) }) {
  let waited = 0;
  let hit = null;
  let wasHeld = false;
  for (;;) {
    if (held()) {
      if (!wasHeld) { onHold(true); wasHeld = true; }
      await sleep(holdPollMs);
      continue;
    }
    if (wasHeld) { onHold(false); wasHeld = false; }
    const slice = waitTotal === 0 ? 1 : Math.min(55, Math.max(1, waitTotal - waited));
    const ctl = new AbortController();
    let page;
    const tick = () => new Promise(r => { const t = setTimeout(() => { ctl.signal.removeEventListener('abort', done); r(); }, holdPollMs); const done = () => { clearTimeout(t); r(); }; ctl.signal.addEventListener('abort', done, { once: true }); });
    const guard = (async () => { for (;;) { await tick(); if (ctl.signal.aborted) return; if (held()) { ctl.abort(); return; } } })();
    try { page = await fetchPage(slice, ctl.signal); }
    catch (e) { if (ctl.signal.aborted) page = { messages: [] }; else { ctl.abort(); throw e; } }
    finally { ctl.abort(); await guard; }
    if (held()) page = { messages: [] };   // landed as the hold began: unread, unacknowledged, re-shown later
    waited += slice;
    const classified = [];
    let delivered = false;
    for (const rec of page.messages ?? []) {
      let msg = null;
      try { msg = parse(rec.content); } catch { /* not GZCOORD/1: never addressed */ }
      if (msg && RETIRED_TYPES.includes(msg.type)) { try { await ack(rec.id); } catch { /* re-read next arm */ } continue; }
      const isMine = msg ? forMeFn(msg) : false;
      classified.push({ rec, msg, isMine });
      if (isMine) delivered = true;
    }
    for (const { rec } of classified) { try { await ack(rec.id); } catch { /* the next arm re-shows it */ } }
    // A keyword hit is a reason to stop waiting on a message that is not
    // addressed to this session. A delivered message wins the exit (it is
    // shown in full); a keyword on a passing message names it and exits
    // with code 3. A message from my own address never hits — a session
    // must not wake on its own echo.
    if (!delivered && !hit)
      for (const { rec, msg, isMine } of classified)
        if (!isMine && msg && keywordHit(rec.content, keywords, ownAddress)) { hit = rec; break; }
    if (delivered || hit || waitTotal === 0 || waited >= waitTotal)
      return { classified, waited, delivered, keywordHit: hit, othersPassed: classified.filter(c => !c.isMine).length };
    // Nothing for this session, no keyword hit: the cursor is past the
    // slice, and the remaining budget keeps waiting.
  }
}

// One delivery (or drain) as the session reads it: what is for me in
// full, what is not by its metadata line (SPEC §17).
//
// THE NOTIFICATION CAP. What the watch prints reaches the session as a
// Monitor notification, and the harness shows about 3,000 characters of
// one event, then "...(truncated)" — the rest exists only in the task's
// output file, which the session does not know to open (architect-cto,
// 2026-09-16, four deliveries cut inside REQUEST or VERIFIED; measured
// here at 3,017 characters shown). So --follow renders under a cap of
// its own: a delivery that fits is printed whole; one that does not
// keeps every metadata line, cuts the body at a line boundary, and says
// where it cut and how to read the whole message (--replay, which moves
// no cursor). The cut is ours, at a place we choose, and the last line
// is the instruction; the harness's cut lands anywhere and says only
// "truncated". The drain (SessionStart hook context) is not a
// notification and is rendered whole.
export const NOTIFICATION_CAP = 2800;
// The name on PATH, never a path through an expansion: a session told to
// run it is not asked for approval (runtime/claude-code/commands.json).
export const REPLAY_CMD = 'gzcoord-inbox --replay';
function cutAtLine(text, max) {
  // Always at a line boundary: a body whose first line alone is longer
  // than the budget keeps nothing of it (the notice says where to read).
  if (text.length <= max) return text;
  const nl = text.lastIndexOf('\n', max);
  return nl < 0 ? '' : text.slice(0, nl);
}
const SECTION_RE = /^[A-Z][A-Z0-9-]*:$/;
// The metadata block ends at the first section marker (SPEC §6: the
// blank line before it MAY be absent), not at a blank line.
export function splitMessage(text) {
  const lines = text.replace(/\r\n/g, '\n').replace(/\n$/, '').split('\n');
  const at = lines.findIndex((l, k) => k > 0 && SECTION_RE.test(l));
  if (at < 0) return { meta: lines.join('\n').replace(/\n+$/, ''), body: '' };
  let metaEnd = at;
  while (metaEnd > 0 && lines[metaEnd - 1] === '') metaEnd -= 1;
  return { meta: lines.slice(0, metaEnd).join('\n'), body: lines.slice(at).join('\n') };
}
const MAX_FLAG_LINES = 4;
export function render(res, me, channel, taxonomy, { cap = Infinity, t = en(), reminder = '' } = {}) {
  const mine = [], others = [];
  for (const { rec, msg, isMine } of res.classified) {
    if (!msg) { others.push({ rec, line: t('inbox.not-a-message', { id: rec.id, sender: rec.sender }) }); continue; }
    (isMine ? mine : others).push({ rec, msg });
  }
  // The reminder rides the head line and nothing else: it is the one
  // line read on every drain and every delivery, and the cap arithmetic
  // below measures the head as it will actually print.
  const head = t('inbox.head', { who: `${me.address}${me.slug ? ` (${me.slug})` : ''}`,
                                 mine: mine.length, others: others.length, channel }) + reminder;
  const parts = mine.map(({ rec }) => {
    // The message has arrived: the terminal-copy width warning does not apply.
    const v = validate(rec.content, { taxonomy, maxColumns: 0, t });
    let flags = [...(v.errors.map(e => t('delivery.invalid', { detail: e }))), ...v.warnings.map(w => t('delivery.warning', { detail: w }))];
    // Only under a cap: the drain shows every validator line.
    if (Number.isFinite(cap) && flags.length > MAX_FLAG_LINES) flags = [...flags.slice(0, MAX_FLAG_LINES), t('delivery.flags-more', { n: flags.length - MAX_FLAG_LINES })];
    const title = `${t('delivery.title', { seq: rec.seq, sender: rec.sender, when: rec.timestamp })}${flags.length ? `\n    ${flags.join('\n    ')}` : ''}`;
    const text = rec.content.replace(/\n$/, '');
    return { rec, title, text, ...splitMessage(text) };
  });
  const otherLines = others.map(o => `  ${o.line ?? oneLine(o.msg, t)}`);
  const othersBlock = others.length ? ['', t('inbox.others-header'), ...otherLines] : [];
  const whole = [head, ...parts.flatMap(p => ['', p.title, '```text', p.text, '```']), ...othersBlock].join('\n');
  if (whole.length <= cap) return whole;

  // Over the cap. Metadata whole and others listed if that fits; the
  // bodies share what is left, each cut at a line and ending with the
  // replay command for its seq. Nothing is claimed to be elsewhere.
  const seqs = list => list.length ? t('cap.seq-range', { first: list[0].rec.seq, last: list[list.length - 1].rec.seq }) : '';
  const notice = p => t('cap.notice', { replay_cmd: REPLAY_CMD, seq: p.rec.seq });
  const othersCount = others.length ? ['', t('cap.others-count', { count: others.length, range: seqs(others) })] : [];
  const layout = othersTail => [head, ...parts.flatMap(p => ['', p.title, '```text', p.meta, '', notice(p), '```']), ...othersTail].join('\n').length;
  let othersTail = othersBlock;
  if (layout(othersTail) > cap) othersTail = othersCount;
  const fixed = layout(othersTail);
  if (fixed > cap) {
    // Too many messages for one notification: one line each, read by seq,
    // and the tail says how many lines this listing itself dropped.
    const lines = [head, t('cap.by-seq', { replay_cmd: REPLAY_CMD })];
    const rows = parts.map(p => t('cap.row', { seq: p.rec.seq, line: oneLine(parse(p.rec.content), t) }));
    const tailFor = n => n < parts.length ? t('cap.more-for-you', { n: parts.length - n, range: seqs(parts.slice(n)) }) : '';
    const othersLine = others.length ? t('cap.and-others', { count: others.length, range: seqs(others) }) : '';
    let n = 0;
    while (n < rows.length && [...lines, ...rows.slice(0, n + 1), tailFor(n + 1), othersLine].filter(Boolean).join('\n').length <= cap) n += 1;
    return [...lines, ...rows.slice(0, n), tailFor(n), othersLine].filter(Boolean).join('\n');
  }
  let budget = cap - fixed;
  const shares = parts.map(() => 0);
  // shortest bodies first: what they do not need goes to the longer ones
  const order = parts.map((p, i) => i).sort((a, b) => parts[a].body.length - parts[b].body.length);
  order.forEach((i, k) => { const share = Math.floor(budget / (order.length - k)); const take = Math.min(share, parts[i].body.length + 2); shares[i] = take; budget -= take; });
  const out = [head];
  for (const [i, p] of parts.entries()) {
    const cut = cutAtLine(p.body, Math.max(0, shares[i] - 2));
    const fits = cut.length >= p.body.length;
    out.push('', p.title, '```text', fits ? p.text : p.meta + (cut ? '\n\n' + cut : ''), ...(fits ? [] : ['', notice(p)]), '```');
  }
  return [...out, ...othersTail].join('\n');
}

export async function main(argv = process.argv.slice(2)) {
  const waitIdx = argv.indexOf('--wait');
  const follow = argv.includes('--follow');
  const replayIdx = argv.indexOf('--replay');
  const replayWhich = replayIdx >= 0 ? argv[replayIdx + 1] : null;
  const waitTotal = waitIdx >= 0 ? (Number(argv[waitIdx + 1]) || 1800) : 0;
  // Who this session is (the login) and which project it is working in
  // (from the working copy's remote, or the binding) — the second selects
  // the project's integration: relay, channel, where the token and runtime
  // live. Those live in the project's WORKING COPY: when the session was
  // started outside one (the workspace, projects/), the working copy the
  // binding names is the root, not the current directory.
  const who = whoami();
  // From here on every line is this login's: English, or the locale its
  // name ends in when that locale has an active dictionary — unless
  // GZCOORD_DEFAULT_LOCALE_ONLY=1 pins the default, which says so once
  // on stderr rather than quietly (i18n.mjs).
  const t = printer(dictionary(who));
  const reminder = localeReminder(who);
  // --keyword K, repeatable, validated BEFORE the arm starts: a bad
  // keyword refused at arm time costs nothing, refused mid-wait wastes
  // the budget. After `t`, so the refusal reads in the login's own
  // language like every other line (blind review F3 on PR #28).
  const keywords = checkKeywords(argv.flatMap((a, i) => a === '--keyword' ? [argv[i + 1]] : []), t);
  // Also after `t`: a usage line is one of this login's lines (re-review §3).
  if (replayIdx >= 0 && !replayWhich) { console.error(t('replay.usage')); return 1; }
  if (argv.includes('--held')) {
    const h = holdStatus(undefined, { t });
    const unknown = t('held.unknown');
    console.log(h.held
      ? t('held.held', { agent: who.agent, sessions: h.sessions.map(x =>
          t('held.session', { session: x.session_id ?? unknown, pid: x.pid, since: x.since ?? unknown })).join(', ') })
      : t('held.not-held', { reason: h.reason }));
    return h.held ? 0 : 1;
  }
  const root = inboxRoot(who);
  const cfg = integrationConfig(who.project, process.env, t);
  // Not configured is not an error at a session start, and not a guess
  // either: one line, exit 0, no relay, no channel.
  if (!cfg.configured) { console.error(t('start.skipping', { reason: cfg.reason })); return 0; }
  try { assertNotControlChannel(cfg.channel, t); } catch (e) { console.error(t('start.error', { detail: e.message })); return 2; }
  const relayUrl = cfg.relay_url;
  const channel = cfg.channel;
  // Activate what this session owns before anything else: the hosting
  // working copy starts its relay here, so a session restart is also the relay's.
  const up = ensureRelay(relayRuntimeDir(cfg), relayUrl, t);
  if (up.started) console.error(up.unit ? t('start.relay-started-unit', { unit: up.unit }) : t('start.relay-started-pid', { pid: up.pid }));
  else if (up.note) console.error(t('start.error', { detail: up.note }));
  let tok = token(root, cfg);
  if (!tok) { console.error(t('start.no-token', { token_file: cfg.token_env_file ?? t('config.no-token-file') })); return 0; }
  const taxPath = findTaxonomy(root);
  const taxonomy = taxPath ? loadTaxonomy(taxPath) : undefined;
  const me = identity(who, taxonomy);
  if (me.roleError) console.error(t('start.error', { detail: me.roleError }));
  // Once: a refused token is retried with the synced file's value when
  // that differs from what the environment carried.
  const withFreshToken = async fn => {
    try { return await fn(tok); }
    catch (e) {
      const fresh = (e.status === 401 || e.status === 403) ? syncedToken() : undefined;
      if (fresh && fresh !== tok) { tok = fresh; console.error(t('start.token-retry')); return fn(tok); }
      throw e;
    }
  };
  if (replayWhich) {
    try { return await withFreshToken(tok => replay(tok, relayUrl, channel, replayWhich, me, t)); }
    catch (e) { const x = explainRelayError(e, relayUrl, t); console.error(x.line); return x.code || 1; }
  }

  // Drain mode spends 1 s on the cursor page and lists everything; wait
  // mode chains slices until a message ADDRESSED TO THIS SESSION lands,
  // passing others' traffic through acknowledged and unprinted.
  const CHANNEL = channel;
  const ack = id => api(tok, '/api/ack', { method: 'POST', body: JSON.stringify({ consumer_id: me.address, channel: CHANNEL, message_id: id }), relayUrl });
  const fetchPage = async (slice, signal) => api(tok, `/api/wait?${new URLSearchParams({ channel: CHANNEL, consumer_id: me.address, timeout_seconds: String(slice), limit: '50' })}`, { relayUrl, signal });
  const held = () => holdStatus().held;
  // Each key sits literally beside its t(: tests/i18n.test.mjs reads
  // the source for them, and a key built in an expression is a key the
  // dead-and-missing guard cannot see.
  const onHold = h => console.error(h ? t('watch.held') : t('watch.hold-released'));

  if (follow) {
    // The watch. Each arm waits an hour of slices; a delivery is printed
    // and the next arm starts at once; a quiet hour starts the next arm
    // silently. Transport trouble is one line each way; a refused token
    // ends the watch with exit 4 so the harness reports it once.
    let down = false;
    for (;;) {
      let r;
      try {
        r = await withFreshToken(() => waitLoop({ fetchPage, ack, waitTotal: 3600, forMeFn: msg => forMe(msg, me), keywords: [], ownAddress: me.address, held, onHold }));
      } catch (e) {
        const x = explainRelayError(e, relayUrl, t);
        if (x.code === 4) { console.error(x.line); return 4; }
        if (!down) { console.log(t('watch.relay-down', { relay_url: relayUrl })); down = true; }
        await new Promise(r => setTimeout(r, 30000));
        continue;
      }
      if (down) { console.log(t('watch.relay-back')); down = false; }
      if (r.delivered) console.log(render(r, me, CHANNEL, taxonomy, { cap: NOTIFICATION_CAP, t, reminder }));
    }
  }

  let res;
  try {
    res = await withFreshToken(() => waitLoop({ fetchPage, ack, waitTotal, forMeFn: msg => forMe(msg, me), keywords, ownAddress: me.address }));
  } catch (e) {
    const x = explainRelayError(e, relayUrl, t); console.error(x.line); return x.code;
  }
  if (res.keywordHit && waitIdx >= 0) {
    const m = res.classified.find(c => c.rec.id === res.keywordHit.id);
    console.log(t('keyword.hit', { channel: CHANNEL, keywords: keywords.join(', ') }));
    console.log(`  ${(m?.msg ? oneLine(m.msg, t) : t('keyword.unparsable', { id: res.keywordHit.id, sender: res.keywordHit.sender }))}`);
    process.exit(3);
  }
  if (!res.delivered && waitIdx >= 0)
    console.log(t('wait.nothing', { channel: CHANNEL, waited: res.waited, others_passed: res.othersPassed }));
  if (!res.delivered) return 0;
  console.log(render(res, me, CHANNEL, taxonomy, { t, reminder }));
  // The cursor is already advanced past everything shown — waitLoop
  // acknowledges every slice it sees, delivered or passed.
  return 0;
}

if (invokedAsMain(import.meta.url)) main().then(c => process.exit(c)).catch(e => {
  // NOT through the dictionary: what failed may BE the dictionary, and a
  // throw inside this handler is an unhandled rejection — a stack trace
  // and exit 1 on a path whose whole contract is one line and exit 0
  // (blind review F1 on PR #28).
  console.error(`gzcoord inbox: ${e?.message ?? e}`);
  process.exit(0);
});
