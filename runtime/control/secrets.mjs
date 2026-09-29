// runtime/control/secrets.mjs — the control agent's second ACTION: re-sync
// this account's secrets from its source — its own store (ADR-038), or
// Doppler until it migrates — (bin/fabric-secrets sync), so a change
// the coordinator made to the login's config — which Claude account it runs
// on (`fabric-accounts assign`, docs/adr/ADR-031-claude-accounts-assigned-applied-and-proved-by-signed-action.md) — reaches the
// account without anyone logging in to it.
//
// An action, signed, for the same reason `upgrade` is: it changes what the
// account's next session runs on. What it applies is whatever the login's
// own Doppler config says, read with the login's own read-only token; the
// request only says what to expect and whether to act on it now:
//
//   expect   the fingerprint the coordinator's template holds. The synced
//            token must match it, or the sync is a failure: a move the
//            account did not take is said by the account, not assumed.
//   restart  a running session not already on the token — read from its
//            own environment, not from the record; a broker session holds
//            none by design and is left alone — is stopped (SIGTERM,
//            never harder) and its launcher resumes it on the new sign-in
//            — the upgrade's restart marker, written already done: nothing
//            is left to wait for. A restart asked for and not done is a
//            failed reply. The
//            requester's own session is never stopped (it is waiting for
//            the reply). Without it a running session keeps the sign-in it
//            started with, and the reply says it needs a relaunch.
//
// So a move is messages end to end: `fabric-accounts assign` writes the
// reference, and every account applies, verifies and restarts by itself.
// What comes back names the sign-in by fingerprint, never by value.

import os from 'node:os';
import path from 'node:path';
import crypto from 'node:crypto';
import { execFile, execFileSync } from 'node:child_process';
import { promisify } from 'node:util';
import { syncedVar } from '../../communication/gzcoord/scripts/inbox.mjs';
import fs from 'node:fs';
import { sessionPids, stateDir, writeMarker, markerPath, upgradeRunning, restartInFlight, STOP_WAIT_MS } from './upgrade.mjs';

const execFileP = promisify(execFile);
export const SYNC_TIMEOUT_MS = 120000;
const SHA12 = /^[0-9a-f]{12}$/;
const sha12 = v => crypto.createHash('sha256').update(v).digest('hex').slice(0, 12);

export function checkArgs(args) {
  if (args === undefined) return null;
  if (typeof args !== 'object' || args === null || Array.isArray(args)) return 'secrets-sync takes { expect, restart }';
  const extra = Object.keys(args).filter(k => !['expect', 'restart'].includes(k));
  if (extra.length) return `secrets-sync takes only expect and restart, not ${extra.join(', ')}`;
  if (args.expect !== undefined && !SHA12.test(String(args.expect))) return 'expect is a 12-hex fingerprint';
  if (args.restart !== undefined && typeof args.restart !== 'boolean') return 'restart is true or false';
  return null;
}

// fabric-secrets sync's exit codes: 0 applied, 2 applied with names
// missing in Doppler (the env file is still written), 1 Doppler unreadable,
// 3 the config names another login. Only the first two changed anything.
const APPLIED = new Set([0, 2]);

// The migration off Doppler (agent-fabric ADR-038 §5 rule 8), a third
// ACTION, run by the account's own daemon so no value leaves the account.
// It is verified by `values_sha256`: the sha256 of every name sync applies
// and its value (the SSH key and the git strings included, which
// secrets.env does not carry), computed by fabric-secrets in-process —
// only hashes cross into this daemon.
//   1. a baseline sync from Doppler: its report's values_sha256;
//   2. the login's Doppler config imported into its store;
//   3. `fabric-secrets digest --source store`: the same hash, from the
//      store, BEFORE anything switches — a difference stops here, and the
//      account never left Doppler (an interruption anywhere before step 4
//      leaves it on Doppler too);
//   4. the source switched to `store` and synced; that report's hash must
//      be the baseline's again, or the source goes back to `doppler`,
//      syncs, and the action fails.
// A store must exist first (fabric-secrets store init, at provisioning or
// store-enroll.sh): the key is made and certified deliberately, never as
// a side effect of a migration.
// Five calls at most (baseline, import, digest, sync, the fallback sync)
// must fit fabric-ctl's 420 s for secrets-migrate.
export const MIGRATE_TIMEOUT_MS = 80000;
export function checkMigrateArgs(args) {
  return args === undefined ? null : 'secrets-migrate takes no arguments';
}
const sourceFile = home => path.join(home, '.config', 'agent-fabric', 'secrets-source');
const envFile = home => path.join(home, '.config', 'agent-fabric', 'secrets.env');
export const envDigest = text => sha12(String(text).split('\n').filter(l => l && !l.startsWith('#')).join('\n'));

export function secretsMigrate(request, opts = {}) {
  if (syncing) return Promise.resolve({ status: 'busy', note: 'a secrets-sync or migration is already running on this account' });
  syncing = secretsMigrateOnce(request, opts).finally(() => { syncing = null; });
  return syncing;
}

export async function secretsMigrateOnce(request, {
  home = os.homedir(), root = process.env.AGENT_FABRIC_ROOT ?? path.join(home, 'projects', 'agent-fabric'), exec = execFileP,
} = {}) {
  const bad = checkMigrateArgs(request.args);
  if (bad) return { status: 'refused', reason: bad };
  const read = f => { try { return fs.readFileSync(f, 'utf8'); } catch { return null; } };
  if ((read(sourceFile(home)) ?? '').trim() === 'store') return { status: 'current', note: 'this account already reads its store' };
  if (read(path.join(process.env.AGENT_FABRIC_SECRET_STORE ?? path.join(home, '.local', 'share', 'agent-fabric', 'secrets'), '.gpg-id')) === null)
    return { status: 'refused', reason: 'no store yet: fabric-secrets store init, and the parent\'s certification, come first' };
  const bin = path.join(root, 'bin', 'fabric-secrets');
  const run = async args => {
    try { const r = await exec(bin, args, { encoding: 'utf8', timeout: MIGRATE_TIMEOUT_MS }); return { code: 0, out: typeof r === 'string' ? r : r.stdout, err: '' }; }
    catch (e) { return { code: typeof e?.code === 'number' ? e.code : -1, out: e?.stdout ?? '', err: String(e?.stderr ?? e?.message ?? e) }; }
  };
  const json = r => { try { return JSON.parse(r.out); } catch { return {}; } };
  const last = r => (json(r).error ?? String(r.err || r.out).trim().split('\n').filter(l => !l.startsWith('hint:')).pop() ?? '').slice(0, 200);
  const setSource = v => { fs.mkdirSync(path.dirname(sourceFile(home)), { recursive: true }); fs.writeFileSync(sourceFile(home), `${v}\n`); };
  const short = h => (h ? String(h).slice(0, 12) : null);
  const base = await run(['sync', '--json']);
  const d0 = json(base).values_sha256;
  if (!APPLIED.has(base.code) || !d0) return { status: 'failed', reason: `the baseline sync from Doppler failed: ${last(base)}` };
  const imp = await run(['store', 'import-doppler']);
  if (imp.code !== 0) return { status: 'failed', reason: `import: ${last(imp)}` };
  const dg = await run(['digest', '--source', 'store']);
  const d1 = json(dg).values_sha256;
  if (dg.code !== 0 || d1 !== d0)
    return { status: 'failed', reason: d1 ? `the store holds other values than Doppler (${short(d0)} vs ${short(d1)}); still on doppler`
      : `the store could not be read: ${last(dg)}; still on doppler`, sha_before: short(d0), sha_after: short(d1) };
  setSource('store');
  const moved = await run(['sync', '--json']);
  const d2 = APPLIED.has(moved.code) ? json(moved).values_sha256 : null;
  if (d2 !== d0) {
    setSource('doppler');
    await run(['sync', '--json']);
    return { status: 'failed', reason: d2 ? `the sync from the store applied other values (${short(d0)} vs ${short(d2)}); back on doppler`
      : `the sync from the store failed (${last(moved)}); back on doppler`, sha_before: short(d0), sha_after: short(d2) };
  }
  return { status: 'migrated', sha: short(d0), env_sha: envDigest(read(envFile(home)) ?? ''), imported: (imp.out.match(/imported (\d+)/) ?? [])[1] ?? null };
}

// A running session's own environment says what it runs on: the token
// (the launcher exports it before the harness execs) and the provider the
// launcher stamped, both readable by this daemon — same uid. The session,
// not the record, says whether it is already on the account: a record
// synced earlier under a session that was never restarted must not read
// as "already on it" (review of #37). A broker session holds no Claude
// account by design — the launcher removes the token — so it is never
// "not on" one: restarting it would bring it back just as tokenless, on
// every run (re-review of #37). A session without the stamp is taken as
// plain claude, the only path a token reaches.
export function sessionEnv(pid, { envOf = p => fs.readFileSync(`/proc/${p}/environ`) } = {}) {
  const out = { token: null, provider: null };
  for (const kv of String(envOf(pid)).split('\0')) {
    if (kv.startsWith('CLAUDE_CODE_OAUTH_TOKEN=')) out.token = kv.slice('CLAUDE_CODE_OAUTH_TOKEN='.length) || null;
    else if (kv.startsWith('AGENT_FABRIC_LAUNCH_PROVIDER=')) out.provider = kv.slice('AGENT_FABRIC_LAUNCH_PROVIDER='.length) || null;
  }
  return out;
}

let syncing = null;   // one secrets-sync at a time per daemon
export function secretsSync(request, opts = {}) {
  if (syncing) return Promise.resolve({ status: 'busy', note: 'a secrets-sync is already running on this account' });
  syncing = secretsSyncOnce(request, opts).finally(() => { syncing = null; });
  return syncing;
}

export async function secretsSyncOnce(request, {
  home = os.homedir(), root = process.env.AGENT_FABRIC_ROOT ?? path.join(home, 'projects', 'agent-fabric'),
  exec = execFileP, sessions = null, me = null, dir = stateDir(home), now = () => new Date(),
  kill = process.kill.bind(process), alive = pid => { try { process.kill(pid, 0); return true; } catch { return false; } },
  sleep = ms => new Promise(r => setTimeout(r, ms)), stopWaitMs = STOP_WAIT_MS, envOf = undefined, upgrading = upgradeRunning, pgrep = null,
} = {}) {
  const bad = checkArgs(request.args);
  if (bad) return { status: 'refused', reason: bad };
  const { expect = null, restart = false } = request.args ?? {};
  let code = 0, out = '';
  try {
    const r = await exec(path.join(root, 'bin', 'fabric-secrets'), ['sync', '--json'], { encoding: 'utf8', timeout: SYNC_TIMEOUT_MS });
    out = typeof r === 'string' ? r : r.stdout;
  } catch (e) {
    code = typeof e?.code === 'number' ? e.code : -1;
    out = e?.stdout ?? '';
    if (code === -1) return { status: 'failed', reason: `fabric-secrets: ${String(e?.message ?? e).split('\n')[0].slice(0, 160)}` };
  }
  let report = {};
  try { report = JSON.parse(out); } catch { /* the reason below says so */ }
  if (!APPLIED.has(code)) return { status: 'failed', reason: String(report.error ?? `fabric-secrets sync exited ${code}`).slice(0, 200) };
  const tok = syncedVar('CLAUDE_CODE_OAUTH_TOKEN', home);
  const sign = tok ? { via: 'setup-token', token_sha256_12: sha12(tok) } : { via: 'none: its next session is refused' };
  const missing = Array.isArray(report.missing) && report.missing.length ? { missing: report.missing } : {};
  const fail = reason => ({ status: 'failed', claude_sign_in: sign, ...missing, reason });
  if (expect && sign.token_sha256_12 !== expect)
    return fail(`the synced record holds ${sign.token_sha256_12 ? `setup-token ${sign.token_sha256_12}` : 'no token'}, not the expected ${expect}; nothing restarted`);
  // No token is nothing to move to: the launcher would refuse the resume.
  if (restart && !tok) return fail('the synced record holds no token; nothing stopped');
  let running;
  try { running = sessions ?? sessionPids({ exec: pgrep ?? ((c, a) => execFileSync(c, a, { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] })) }); }
  catch (e) {
    const why = `could not tell whether a session is running (pgrep: ${String(e?.message ?? e).split('\n')[0].slice(0, 120)})`;
    return restart ? fail(`${why}; nothing restarted`) : { status: 'synced', claude_sign_in: sign, ...missing, session: 'unknown', reason: why };
  }
  const done = session => ({ status: 'synced', claude_sign_in: sign, ...missing, session });
  if (!running.length) return done('none');
  const envs = new Map(running.map(pid => { try { return [pid, sessionEnv(pid, envOf ? { envOf } : {})]; } catch { return [pid, null]; } }));
  const broker = running.filter(pid => { const e = envs.get(pid); return e?.provider && e.provider !== 'anthropic'; });
  const stale = running.filter(pid => { if (broker.includes(pid)) return false; const t = envs.get(pid)?.token; return !(t && tok && sha12(t) === sha12(tok)); });
  if (!stale.length) return done(broker.length === running.length ? 'running (broker): no Claude account to move' : 'running, already on it');
  const own = me && request.from === me;
  if (own) return done('yours: relaunch to use it');
  if (!restart) return done('running: relaunch to use it');
  if (upgrading()) return fail('an upgrade is running on this account (it owns the restart marker); synced, nothing stopped — run it again after');
  restartInFlight(true);
  try {
    // The launcher reads the marker when the session returns: written
    // first, and done already, so it resumes at once on what was synced.
    const before = envs.get(stale[0])?.token ?? null;
    writeMarker(dir, { request_id: request.id, requested_at: now().toISOString(), piece: 'the Claude account', from: before ? `setup-token ${sha12(before)}` : 'no token', to: `setup-token ${sign.token_sha256_12}`, installed: `setup-token ${sign.token_sha256_12}`, pids: stale, status: 'done' });
    for (const pid of stale) { try { kill(pid, 'SIGTERM'); } catch { /* gone */ } }
    const until = Date.now() + stopWaitMs;
    while (stale.some(alive) && Date.now() < until) await sleep(500);
    if (stale.some(alive)) {
      // Not stopped: our marker goes (only ours — an upgrade may have
      // written its own since), or the session would be resumed the moment
      // it is ended on purpose, long after this action.
      try { if (JSON.parse(fs.readFileSync(markerPath(dir), 'utf8')).request_id === request.id) fs.rmSync(markerPath(dir), { force: true }); } catch { /* gone */ }
      return fail(`synced, but the session (pid ${stale.filter(alive).join(', ')}) did not stop within ${Math.round(stopWaitMs / 1000)} s; nothing forced — run it again, or relaunch it`);
    }
    return done('restarting');
  } finally { restartInFlight(false); }
}
