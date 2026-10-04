// runtime/control/ops.mjs — what a control agent can say about its own
// account, as pure extractors: each takes its inputs (a home, a fetch, an
// exec) so a test runs them against a scratch home and a fake relay, and
// each returns only fixed, whitelisted keys — never a value from a secret.
// The fingerprints are the one place a secret is read: hashed in place,
// twelve hex digits of its sha256, enough to tell two keys apart and
// nothing else (the CEO, 2026-09-17: "the username it logs in with, or
// the api key hash").
//
// A section that cannot be read says so inline ({status: ...}) rather than
// throwing: a reply always arrives, and its gaps are named.

import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import crypto from 'node:crypto';
import { execFileSync, execFile } from 'node:child_process';
import { promisify } from 'node:util';
import zlib from 'node:zlib';
import { whoami, findTaxonomy, loadTaxonomy, syncedVar, holdStatus, identity as gzIdentity } from './gzcoord.mjs';
import { jobs } from './jobs.mjs';
import { memoryPressure } from './pressure.mjs';

export const OPS = ['ping', 'identity', 'usage', 'keys', 'fabric', 'session', 'script', 'recall', 'tokens', 'memory', 'host', 'disk', 'accounts', 'upgrade', 'secrets-sync', 'status', 'presence', 'jobs', 'jobs-add'];
// Answered for any placed account, not only an operator: whether a session
// is running is what every sender needs before it writes to one, and it
// names nothing a relay reader could not already infer (the owner,
// 2026-09-25: presence moves from HELLO/GOODBYE, now retired, to the
// control plane).
export const PUBLIC_OPS = ['presence'];
export const KEY_NAMES = ['OPENROUTER_API_KEY', 'OPENAI_API_KEY', 'GH_TOKEN', 'CLAUDE_BRIDGE_AUTH_TOKEN', 'SERPAPI_API_KEY', 'BRAVE_SEARCH_API_KEY', 'CLAUDE_CODE_OAUTH_TOKEN'];
export const USAGE_URL = 'https://api.anthropic.com/api/oauth/usage';

function readJson(file) {
  try { return JSON.parse(fs.readFileSync(file, 'utf8')); } catch { return null; }
}

const sha12 = v => crypto.createHash('sha256').update(v).digest('hex').slice(0, 12);

// Who this account is, and which Claude account its sessions run on. A
// template's setup-token (CLAUDE_CODE_OAUTH_TOKEN, synced from the
// login's store) outranks the login's own /login, whose ~/.claude.json keeps
// naming its old account — so a switched login is reported by the
// token's fingerprint (`fabric-accounts templates` maps it to an account),
// and its own sign-in separately, never as the account in use.
export function identity(home = os.homedir(), who = whoami()) {
  const claude = readJson(path.join(home, '.claude.json'))?.oauthAccount ?? null;
  const own = claude ? { email: claude.emailAddress ?? null, organization: claude.organizationName ?? null } : null;
  const template = syncedVar('CLAUDE_CODE_OAUTH_TOKEN', home);
  return {
    agent: who.agent ?? null, host: who.host ?? null, role: who.role ?? null,
    project: who.project ?? null, working_copy: who.working_copy ?? null,
    claude_account: template ? { via: 'setup-token', token_sha256_12: sha12(template), email: null, organization: null } : own,
    ...(template && { own_sign_in: own }),
    credentials_present: fs.existsSync(path.join(home, '.claude', '.credentials.json')),
  };
}

// The five-hour and seven-day windows, read with the account's own OAuth
// token, which goes into one header and nowhere else.
export async function usage(home = os.homedir(), fetchFn = globalThis.fetch, url = USAGE_URL) {
  // A login on a template: its own sign-in's windows are another account's,
  // and the setup-token cannot read any (HTTP 403, user:inference only).
  if (syncedVar('CLAUDE_CODE_OAUTH_TOKEN', home)) return { status: 'setup-token', see: 'fabric-ctl <observer> accounts' };
  const creds = readJson(path.join(home, '.claude', '.credentials.json'));
  const tok = creds?.claudeAiOauth?.accessToken;
  if (!tok) return { status: 'no-credentials' };
  let r;
  try {
    r = await fetchFn(url, { headers: { Authorization: `Bearer ${tok}`, 'anthropic-beta': 'oauth-2025-04-20' }, signal: AbortSignal.timeout(15000) });
  } catch { return { status: 'read-failed' }; }
  if (!r.ok) return { status: 'read-failed', http: r.status };
  let u;
  try { u = await r.json(); } catch { return { status: 'unreadable' }; }
  const win = w => (w && typeof w === 'object') ? { utilization: w.utilization ?? null, resets_at: w.resets_at ?? null } : null;
  return { status: 'ok', five_hour: win(u.five_hour), seven_day: win(u.seven_day), subscription: creds?.claudeAiOauth?.subscriptionType ?? null };
}

// THE CLAUDE ACCOUNTS this login observes: one Claude Code config
// directory per Claude account under accountsDir(), each signed in once
// with /login and held by this observer alone — a refresh token has one
// holder, or the first refresh signs the others out. The fleet's working
// sessions run on each account's one-year setup-token, which is
// `user:inference` only and so cannot read these windows
// (docs/adr/ADR-031-claude-accounts-assigned-applied-and-proved-by-signed-action.md).
//
// The read is the harness's own `/usage`, run headless: no model call
// (0 turns, $0), and it renews an expired 8-hour sign-in the official way
// — measured 2026-09-24 on 2.1.281 (docs/live-checks/2026-09-24-claude-
// accounts.md). Reimplementing the OAuth refresh here was the rejected
// alternative: it would present Claude Code's client id without being
// Claude Code. `claude auth status` is not a keep-alive: it starts a
// refresh, exits, and leaves a lock the next run trips on until the
// harness calls it stale (60 s).
export const ACCOUNTS_TIMEOUT_MS = 120000;
export const ACCOUNT_SLUG = /^[a-z0-9][a-z0-9-]{0,62}$/;
// Under the login's fabric state root, the same one runtime/identity.py
// resolves: AGENT_FABRIC_STATE_DIR when set, else the XDG default.
export function accountsDir(home = os.homedir(), env = process.env) {
  const root = env.AGENT_FABRIC_STATE_DIR ? path.resolve(env.AGENT_FABRIC_STATE_DIR) : path.join(env.XDG_STATE_HOME || path.join(home, '.local', 'state'), 'agent-fabric');
  return path.join(root, 'accounts');
}
// One reader per account across PROCESSES, not only inside the daemon: a
// person's `fabric-accounts read` beside the keeper would start a second
// harness on the same config directory, and the loser fails on the
// refresh lock. O_EXCL on a file naming the holder's pid; a holder that
// is gone (a killed read) does not keep the account.
export function takeReadLock(dir, pid = process.pid) {
  const f = path.join(dir, '.fabric-read.lock');
  for (let attempt = 0; attempt < 2; attempt++) {
    try { fs.writeFileSync(f, `${pid}\n`, { flag: 'wx', mode: 0o600 }); return () => { try { fs.unlinkSync(f); } catch { /* gone */ } }; }
    catch (e) {
      if (e.code !== 'EEXIST') throw e;
      let holder;
      try { holder = Number(String(fs.readFileSync(f, 'utf8')).trim()); }
      catch (r) { if (r.code === 'ENOENT') continue; throw r; }   // released between our attempt and this read: try again; anything else is loud
      let alive = false;
      try { process.kill(holder, 0); alive = true; } catch (k) { alive = k.code === 'EPERM'; }
      if (alive && holder !== pid) return null;
      try { fs.unlinkSync(f); } catch { /* raced */ }
    }
  }
  return null;
}
export function accountSlugs(dir) {
  try { return fs.readdirSync(dir, { withFileTypes: true }).filter(d => d.isDirectory() && ACCOUNT_SLUG.test(d.name)).map(d => d.name).sort(); }
  catch { return []; }
}
export function claudeBin(home = os.homedir()) {
  const own = path.join(home, '.local', 'bin', 'claude');
  return fs.existsSync(own) ? own : 'claude';
}
// The /usage events, reduced to fixed keys. `limits` are the server's
// meters in its order: session, weekly_all, weekly_scoped (per model).
export function parseUsageReport(stdout) {
  let events;
  try { events = JSON.parse(stdout); } catch { return { status: 'unreadable' }; }
  if (!Array.isArray(events)) return { status: 'unreadable' };
  const result = events.find(e => e?.type === 'result');
  const report = events.find(e => e?.usage_report)?.usage_report;
  if (result?.is_error) return { status: 'failed', error: String(result.result ?? '').slice(0, 200) };
  const limits = report?.rate_limits?.limits;
  if (!Array.isArray(limits)) return { status: 'no-report' };
  return {
    status: 'ok',
    limits: limits.map(l => ({ kind: l?.kind ?? null, group: l?.group ?? null, percent: typeof l?.percent === 'number' ? l.percent : null,
                               resets_at: l?.resets_at ?? null, model: l?.scope?.model?.display_name ?? null })),
  };
}
// One account's reading. The child gets an environment built from
// nothing: a token variable inherited from the observer's own session
// (CLAUDE_CODE_OAUTH_TOKEN, ANTHROPIC_API_KEY, a base URL) would outrank
// the account's sign-in and report another account's windows.
export async function readAccount(dir, { home = os.homedir(), exec = execFileP, bin = claudeBin(home), now = () => new Date(), timeoutMs = ACCOUNTS_TIMEOUT_MS } = {}) {
  const slug = path.basename(dir);
  const profile = readJson(path.join(dir, '.claude.json'))?.oauthAccount ?? null;
  const out = { slug, email: profile?.emailAddress ?? null, organization_uuid: profile?.organizationUuid ?? null, read_at: now().toISOString() };
  if (!fs.existsSync(path.join(dir, '.credentials.json'))) return { ...out, status: 'not-signed-in' };
  let release;
  try { release = takeReadLock(dir); }
  catch (e) { return { ...out, status: 'failed', error: `read lock: ${e.code ?? String(e.message).slice(0, 80)}` }; }   // this account's row, not the whole section's
  if (!release) return { ...out, status: 'busy', error: 'another reader holds this account (the daemon, or fabric-accounts read)' };
  // A fixed working directory: the harness records a project per cwd even
  // with --no-session-persistence (an empty one, measured), so a fresh
  // temporary cwd per read would leave one more entry every 4 hours.
  const cwd = path.join(dir, 'work');
  try {
    fs.mkdirSync(cwd, { recursive: true, mode: 0o700 });   // inside the try: a throw here must still release the lock
    const env = { HOME: home, PATH: process.env.PATH ?? '/usr/local/bin:/usr/bin:/bin', CLAUDE_CONFIG_DIR: dir, LANG: 'C.UTF-8' };
    const r = await exec(bin, ['-p', '/usage', '--output-format', 'json', '--no-session-persistence'], { cwd, env, encoding: 'utf8', timeout: timeoutMs, maxBuffer: 4 * 1024 * 1024, stdio: ['ignore', 'pipe', 'ignore'] });
    return { ...out, ...parseUsageReport(typeof r === 'string' ? r : r.stdout) };
  } catch (e) {
    return { ...out, status: e?.killed ? 'timeout' : 'failed', error: String(e?.message ?? e).split('\n')[0].slice(0, 200) };
  } finally {
    release();
  }
}
// Every observed account, one at a time: two harness runs on one config
// directory race for its refresh lock.
export async function accounts(home = os.homedir(), { dir = accountsDir(home), ...opts } = {}) {
  const slugs = accountSlugs(dir);
  if (!slugs.length) return { status: 'none', dir };
  const list = [];
  for (const s of slugs) list.push(await readAccount(path.join(dir, s), { home, ...opts }));
  return { status: 'ok', accounts: list };
}

// Which keys the account holds, by name and fingerprint; never a value.
export function keys(home = os.homedir(), names = KEY_NAMES) {
  return names.map(name => {
    const v = syncedVar(name, home);
    return v ? { name, present: true, sha256_12: crypto.createHash('sha256').update(v).digest('hex').slice(0, 12) } : { name, present: false };
  });
}

// Whether this account's stores took only verified commits (ADR-042 rule
// 5): its own store and each child's mirror. A refusal is a security event,
// said until the store is repaired; secret_store.py keeps the last one
// beside the store, and nothing here reads an entry. The row's state:
// verified, refused, no store, no base (it verifies nothing, so takes
// nothing in), or unreadable — never "verified" for a store that is not
// there or has no base (review of ADR-042, F4). A mirror's refusal is the
// parent's to repair, named by the child's agent id (F3).
export const STORE_ROW = 'store commits verified';
const REFUSAL_FILE = 'agent-fabric-refusal.json';
const AGENT_ID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

function readRefusal(store) {
  let r;
  try { r = JSON.parse(fs.readFileSync(path.join(store, '.git', REFUSAL_FILE), 'utf8')); }
  catch (e) { return e?.code === 'ENOENT' ? null : { unreadable: true }; }
  return { refused: { commit: String(r?.commit ?? '?').slice(0, 12), at: r?.at ?? null, reason: String(r?.reason ?? '?').slice(0, 300) } };
}

// The trusted base is agent-fabric.trustedbase in the store's own
// .git/config, which secret_store.py writes through `git config`: read as a
// file, so the keys probe runs no git. true, false, or null (unreadable).
function hasBase(store) {
  let text;
  try { text = fs.readFileSync(path.join(store, '.git', 'config'), 'utf8'); } catch { return null; }
  let inSection = false;
  for (const line of text.split('\n')) {
    const head = /^\s*\[([^\]]*)\]/.exec(line);
    if (head) { inSection = head[1].trim().toLowerCase() === 'agent-fabric'; continue; }
    if (inSection && /^\s*trustedbase\s*=\s*[0-9a-f]{40}\s*$/i.test(line)) return true;
  }
  return false;
}

export function storeRefusal(home = os.homedir(), store = process.env.AGENT_FABRIC_SECRET_STORE ?? path.join(home, '.local', 'share', 'agent-fabric', 'secrets'),
                             children = path.join(home, '.local', 'share', 'agent-fabric', 'children')) {
  let kids = [];
  try { kids = fs.readdirSync(children).filter(n => AGENT_ID_RE.test(n)).sort(); } catch { /* no mirrors */ }
  const mirrors = [];
  // A mirror with no base refuses every verified operation on it, so it is
  // as unclean as a refusal (review of #94): said, as the own store's is.
  for (const aid of kids) {
    const mirror = path.join(children, aid);
    const r = readRefusal(mirror);
    const base = hasBase(mirror);
    if (r) mirrors.push({ agent_id: aid, ...(r.refused ?? { unreadable: true }) });
    else if (base !== true) mirrors.push({ agent_id: aid, state: base === null ? 'unreadable' : 'no base' });
  }
  const own = fs.existsSync(path.join(store, '.git')) ? readRefusal(store) : undefined;
  const base = own === undefined ? null : hasBase(store);
  const state = own === undefined ? 'no store' : own?.unreadable ? 'unreadable' : own?.refused ? 'refused'
    : base === null ? 'unreadable' : base ? 'verified' : 'no base';
  return { name: STORE_ROW, present: state === 'verified' && !mirrors.length, state,
           ...(own?.refused ? { refused: own.refused } : {}), ...(mirrors.length ? { mirrors } : {}) };
}

// Whether the secret of the key git signs with is in this account's
// keyring and can sign: present or not, never the key. A secret-key COUNT
// is no answer, since every account holds its own store key (ADR-038):
// rust-ui-dev-01 held one and could not sign (2026-10-03). A stub (`#` in
// the colon listing's 15th field, an offline primary) cannot sign either,
// so presence is a sec or ssb line with signing capability and no stub
// mark. git config exits 1 when unset, gpg non-zero when the key is
// unknown: both are absent. Asynchronous, beside fabric(), so a slow
// gpg-agent never holds the daemon's loop (review of #89); a test passes
// its own exec, as it does for fabric() and session().
export const SIGNING_ROW = 'signing key secret';
export async function signingSecret(exec = execFileP) {
  const opts = { encoding: 'utf8', timeout: 5000, stdio: ['ignore', 'pipe', 'ignore'] };
  const text = r => String(typeof r === 'string' ? r : r?.stdout ?? '');
  let k;
  try { k = text(await exec('git', ['config', '--global', 'user.signingkey'], opts)).trim(); } catch { k = ''; }
  if (!k) return { name: SIGNING_ROW, present: false };
  let listing;
  try { listing = text(await exec('gpg', ['--list-secret-keys', '--with-colons', '--', k], opts)); }
  catch { return { name: SIGNING_ROW, present: false }; }
  const signs = listing.split('\n').some(line => {
    const f = line.split(':');
    return (f[0] === 'sec' || f[0] === 'ssb') && (f[11] ?? '').includes('s') && f[14] !== '#';
  });
  return { name: SIGNING_ROW, present: signs };
}

// The fabric checkout the account runs on: head, branch, how far behind
// origin/main, and whether the tree is clean. A fetch that cannot reach
// origin is said, not hidden. Asynchronous so the daemon's event loop
// stays live through the fetch's 10 s budget (the source watch, signals,
// the usage read of the same request); the read loop itself still
// answers one record at a time (exec may return a string or a {stdout};
// a test passes a synchronous fake).
const execFileP = promisify(execFile);
export async function fabric(root = process.env.AGENT_FABRIC_ROOT ?? path.join(os.homedir(), 'projects', 'agent-fabric'), exec = execFileP) {
  const git = async (...a) => { const r = await exec('git', ['-C', root, ...a], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'], timeout: 10000 }); return (typeof r === 'string' ? r : r.stdout).trim(); };
  const out = { root };
  try { out.head = await git('rev-parse', '--short', 'HEAD'); } catch { return { ...out, status: 'not-a-checkout' }; }
  try { out.branch = await git('rev-parse', '--abbrev-ref', 'HEAD'); } catch { out.branch = null; }
  try { out.dirty = (await git('status', '--porcelain')).length > 0; } catch { out.dirty = null; }
  try { await git('fetch', '-q', 'origin', 'main'); out.fetch = 'ok'; } catch { out.fetch = 'failed'; }
  try { out.behind = Number(await git('rev-list', '--count', 'HEAD..origin/main')); } catch { out.behind = null; }
  return { status: 'ok', ...out };
}

// Whether a harness runs as this account, and whether it is planning.
export function session(uid = process.getuid(), exec = execFileSync) {
  let n = 0;
  try { n = exec('pgrep', ['-u', String(uid), '-x', 'claude'], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] }).trim().split('\n').filter(Boolean).length; }
  catch { n = 0; }   // pgrep exits 1 when nothing matches
  return { claude_processes: n, planning: holdStatus().held };
}

// Presence: whether this account has a session, from the process table,
// so a crash or a launch that never reached the harness is never
// "present" — the two cases the retired HELLO/GOODBYE pair got wrong on
// 2026-09-25.
// The daemon's own children (the observer's /usage runs) are not a
// session. The role is derived exactly as the inbox's delivery derives it
// (identity() in gzcoord.mjs, moved from the inbox: the binding's
// role, else the slug the login carries), so a TO-ROLE the relay would
// deliver is never refused for a holder with no role recorded (review
// of #38). The project is the
// binding's: where the last session here worked.
export function presence({ uid = process.getuid(), exec = execFileSync, proc = '/proc', self = process.pid, who = null, binding = null, hold = () => holdStatus() } = {}) {
  let pids = [];
  try { pids = String(exec('pgrep', ['-u', String(uid), '-x', 'claude'], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] })).trim().split('\n').filter(Boolean).map(Number); }
  catch (e) { if (e?.status !== 1) return { status: 'failed', error: `pgrep: ${String(e?.message ?? e).split('\n')[0].slice(0, 120)}` }; }
  const stat = p => { try { const s = fs.readFileSync(path.join(proc, String(p), 'stat'), 'utf8'); return s.slice(s.lastIndexOf(')') + 2).split(' '); } catch { return null; } };
  const btime = (() => { try { return Number(/^btime (\d+)/m.exec(fs.readFileSync(path.join(proc, 'stat'), 'utf8'))[1]); } catch { return null; } })();
  const live = pids.map(p => ({ p, f: stat(p) })).filter(x => x.f && Number(x.f[1]) !== self);
  // field 22 of stat, starttime, in clock ticks since boot (USER_HZ, 100 on Linux)
  const starts = live.map(x => btime == null ? null : new Date((btime + Number(x.f[19]) / 100) * 1000).toISOString()).filter(Boolean).sort();
  const me = who ?? whoami();
  const b = binding ?? (readJson(me.binding) ?? {});
  let role = null;
  try { const tp = findTaxonomy(); role = gzIdentity(me, tp ? loadTaxonomy(tp) : undefined).slug ?? null; } catch { /* no catalogue: no role */ }
  // Planning: the account's inbox is held until the plan is approved
  // (docs/adr/ADR-022-the-session-lifecycle.md), so a message sent now is read
  // then, and a sender should not wait on an answer before.
  let planning = false;
  try { planning = live.length > 0 && hold().held === true; } catch { /* no hold directory: not planning */ }
  return { status: 'ok', online: live.length > 0, sessions: live.length, since: starts[0] ?? null, role, project: b.project ?? null, planning };
}

// The MACHINE this account shares — what develop-qzapp's crash of
// 2026-09-19 was diagnosed from by hand, after the fact, with free, df,
// xenstore-read and find (docs/live-checks/2026-09-19-develop-qzapp-crash.md;
// the layers: ADR-010). Load and cpus; memory and swap from
// /proc/meminfo; the Xen balloon where there is one (current and target
// from sysfs, static-max — the ceiling this boot — from xenstore, null on
// a host that is not a Xen guest); every mounted block device once, by
// statfs; the leases held under /run/lock/agent-fabric, each probed with
// a read-only flock (held or not is the kernel's answer, the record line
// only says by whom); the largest processes by RSS, with the login they
// run as. Numbers and names of programs and logins, never a command
// line. Every daemon on one host answers the same numbers: fabric-ctl
// collapses the rows by host.
export function host({ proc = '/proc', sys = '/sys', leases = '/run/lock/agent-fabric', exec = execFileSync, cpus = os.cpus().length, statfs = fs.statfsSync } = {}) {
  const read = f => { try { return fs.readFileSync(f, 'utf8'); } catch { return null; } };
  const run = (cmd, args) => { try { const r = exec(cmd, args, { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'], timeout: 5000 }); return typeof r === 'string' ? r : r.stdout; } catch { return null; } };
  const mb = kb => kb == null ? null : Math.round(kb / 1024);
  const out = { status: 'ok', cpus, loadavg: null, mem_mb: null, balloon_mb: null, disk: [], leases: [], top_rss: [] };
  const la = read(path.join(proc, 'loadavg'));
  if (la) out.loadavg = la.trim().split(/\s+/).slice(0, 3).map(Number);
  const mi = read(path.join(proc, 'meminfo'));
  if (mi) {
    const kb = {}; for (const m of mi.matchAll(/^(\w+):\s+(\d+) kB/gm)) kb[m[1]] = Number(m[2]);
    out.mem_mb = { total: mb(kb.MemTotal), available: mb(kb.MemAvailable), swap_total: mb(kb.SwapTotal), swap_free: mb(kb.SwapFree) };
  }
  const xm = path.join(sys, 'devices', 'system', 'xen_memory', 'xen_memory0');
  const cur = read(path.join(xm, 'info', 'current_kb')), tgt = read(path.join(xm, 'target_kb'));
  if (cur != null || tgt != null) {
    const smax = run('xenstore-read', ['memory/static-max']);
    // static-max is xenstore's, and /dev/xen/xenbus is root:qubes on this
    // deployment: an account's daemon reads null, the operator's the number;
    // fabric-ctl prefers the row that has it. A half-present sysfs is null
    // per field, never 0 (Number(null) is 0).
    out.balloon_mb = { current: cur == null ? null : mb(Number(cur)), target: tgt == null ? null : mb(Number(tgt)), static_max: smax ? mb(Number(smax.trim())) : null };
  }
  const mounts = read(path.join(proc, 'mounts'));
  if (mounts) {
    const seen = new Set();
    for (const line of mounts.split('\n')) {
      const [dev, mnt] = line.split(' ');
      if (!dev?.startsWith('/dev/') || seen.has(dev)) continue;
      seen.add(dev);
      try { const st = statfs(mnt.replace(/\\040/g, ' ')); const size = st.blocks * st.bsize, avail = st.bavail * st.bsize;
        out.disk.push({ mount: mnt, size_gb: Math.round(size / 2 ** 30), avail_gb: Math.round(avail / 2 ** 30), use_pct: size ? Math.round(100 * (size - avail) / size) : null }); }
      catch { /* a mount that vanished between the read and the statfs: not a row */ }
    }
  }
  // Only what fabric-lease itself can create is a lease: its name grammar,
  // [A-Za-z0-9][A-Za-z0-9._-]{0,63}. The directory is world-writable, so any
  // login can drop any name there; a name outside the grammar is not a lease
  // and never reaches the probe — and the name reaches only fs.openSync,
  // never a command line; the grammar is the first gate, not the only one.
  const LEASE_NAME = /^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/;
  let names = []; try { names = fs.readdirSync(leases).filter(n => LEASE_NAME.test(n)); } catch { /* no lease directory: no leases */ }
  for (const n of names) {
    const f = path.join(leases, n);
    // The file is opened READ-ONLY here and the descriptor handed to
    // flock(1) as fd 3 — no shell, no command text built from a name in a
    // world-writable directory. The flock command opening the path itself
    // would use O_CREAT, which fs.protected_regular refuses on another
    // login's file in the sticky directory. O_NONBLOCK and O_NOFOLLOW, then
    // fstat on the descriptor rather than stat before the open: any login
    // can rename a fifo or a symlink over its own grammar-named entry in
    // between, and a blocking open of a reader-less fifo would hang this
    // synchronous op — and the daemon with it — for good. A SHARED lock,
    // not exclusive: an exclusive probe would hold a free lease for a
    // moment, and sixteen daemons probing at once could refuse a real
    // caller and each report the other's hold as a stale holder; a shared
    // probe is refused only by a real holder's exclusive lock (exit 1). A
    // file that cannot be opened (a hand-made 0600) is not a lease row.
    let fd; try { fd = fs.openSync(f, fs.constants.O_RDONLY | fs.constants.O_NONBLOCK | fs.constants.O_NOFOLLOW); } catch { continue; }
    try {
      if (!fs.fstatSync(fd).isFile()) continue;
      let held = false;
      try { exec('flock', ['-s', '-n', '3'], { stdio: ['ignore', 'ignore', 'ignore', fd], timeout: 5000 }); }
      catch (e) { held = e?.status === 1; }
      if (!held) continue;
      // The record is the holder's own line — informational, and read
      // bounded: the first 256 bytes, never a whole file a login has grown.
      const buf = Buffer.alloc(256); const nread = fs.readSync(fd, buf, 0, 256, 0);
      const rec = buf.toString('utf8', 0, nread).split('\n')[0];
      const [login, pid, since] = rec.split(' ');
      // The job the holder named with --label: "<name> (<job>)" at the end.
      const label = /\(([A-Za-z0-9._-]{1,64})\)$/.exec(rec)?.[1] ?? null;
      out.leases.push({ name: n, holder: login || null, pid: Number(pid) || null, since: since || null, label });
    } finally { try { fs.closeSync(fd); } catch { /* already closed */ } }
  }
  const ps = run('ps', ['-eo', 'user:32,pid,rss,comm', '--sort=-rss']);
  if (ps) out.top_rss = ps.trim().split('\n').slice(1, 7).map(l => { const [user, pid, rss, ...comm] = l.trim().split(/\s+/); return { user, pid: Number(pid), rss_mb: mb(Number(rss)), comm: comm.join(' ') }; });
  return out;
}

// Which SCRIPT the account writes in — the signature of the language it
// reasons in. A role that must think in the language it answers for
// (language-culture) leaves exactly one artifact that differs when it
// does not: the letters of its own session records. The harness keeps
// every assistant turn, thinking blocks included, under
// ~/.claude/projects/<launch dir>/<session>.jsonl; this counts the LETTERS
// of those blocks by script (Unicode block: Latin, Georgian, Cyrillic,
// Greek, Arabic, Hebrew, Armenian, CJK, other) and reports shares —
// thinking and visible text apart, since a session that reasons in one
// language and translates its answers shows a low share in thinking and
// a higher one in text. Nothing of the text itself leaves the account:
// counts and percentages only. Records touched in the last `hours`
// (default 24), newest `limit` files (default 5).
//
// Measured 2026-09-17: the reasoning itself is NOT on disk — the API
// returns most thinking blocks with a signature and no text, and the
// ones that carry text are 120–400-character summaries; one session
// with 117k thinking tokens had no stored thinking text at all. So the
// signature the charter names is the holder's NOTES: the directory
// `${XDG_STATE_HOME:-~/.local/state}/agent-fabric/agents/<login>/notes/`,
// where the role keeps the translated request, its working notes and
// the original answer in the locale's language, one file per day. The
// op counts those files (touched in the window) the same way, by
// script, and bins their paragraphs; that is the artifact the holder
// controls and the transcript's text share is the second number.
//
// The CEO's criterion (2026-09-17) is per BLOCK, not per total: most
// thinking blocks must be in the locale's script alone, some will be
// about half and half (a term quoted, a name), and a session that
// reasons in English shows the opposite — so each thinking block is
// also binned by the share of its dominant non-Latin script: `only`
// (≥ 90 %), `mixed` (30–90 %), `latin` (< 30 %), and the bins are
// reported as counts of blocks. `empty` is the block the API returned
// with a signature and no text: measured 2026-09-17 across the fleet,
// most thinking blocks are stored that way (one org: about a fifth
// carry text; the other: none on the same model), so the signature is
// read from the blocks that carry text, and `empty` says how many did
// not — a row of only empties is unmeasured, not clean.
const SCRIPT_RANGES = [
  ['georgian', [[0x10A0, 0x10FF], [0x1C90, 0x1CBF], [0x2D00, 0x2D2F]]],
  ['cyrillic', [[0x0400, 0x052F], [0x2DE0, 0x2DFF], [0xA640, 0xA69F]]],
  ['greek', [[0x0370, 0x03FF], [0x1F00, 0x1FFF]]],
  ['armenian', [[0x0530, 0x058F]]],
  ['hebrew', [[0x0590, 0x05FF]]],
  ['arabic', [[0x0600, 0x06FF], [0x0750, 0x077F], [0x08A0, 0x08FF]]],
  ['cjk', [[0x3040, 0x30FF], [0x4E00, 0x9FFF], [0xAC00, 0xD7AF]]],
  ['latin', [[0x0041, 0x005A], [0x0061, 0x007A], [0x00C0, 0x024F], [0x1E00, 0x1EFF]]],
];
export function scriptCounts(text, counts = {}) {
  for (const ch of text) {
    const cp = ch.codePointAt(0);
    if (cp < 0x41) continue;                      // digits, punctuation, space
    let name = null;
    for (const [n, ranges] of SCRIPT_RANGES) { if (ranges.some(([a, b]) => cp >= a && cp <= b)) { name = n; break; } }
    if (!name) { if (/\p{L}/u.test(ch)) name = 'other'; else continue; }
    counts[name] = (counts[name] ?? 0) + 1;
  }
  return counts;
}
const shares = counts => {
  const total = Object.values(counts).reduce((a, b) => a + b, 0);
  const out = { letters: total };
  for (const [k, v] of Object.entries(counts).sort((a, b) => b[1] - a[1])) out[k] = Math.round(1000 * v / total) / 10;
  return out;
};
// A block (a thinking block, a paragraph) binned by its non-Latin share:
// `only` at 90 %, `mixed` from 30 %, `latin` below, `empty` under 20 letters.
const binInto = (blocks, counts) => {
  const total = Object.values(counts).reduce((a, b) => a + b, 0);
  if (total < 20) { blocks.empty += 1; return; }
  const nonLatin = total - (counts.latin ?? 0) - (counts.other ?? 0);
  const share = nonLatin / total;
  blocks[share >= 0.9 ? 'only' : share >= 0.3 ? 'mixed' : 'latin'] += 1;
};
const paragraphs = (text, counts, blocks, sink) => { for (const para of text.split(/\n\s*\n/)) { const c = scriptCounts(para); binInto(blocks, c); for (const [k, v] of Object.entries(c)) counts[k] = (counts[k] ?? 0) + v; sink?.push(para); } };
// THE LANGUAGE, not only the script (the CEO, 2026-09-17: CLD2). Script
// shares cannot tell English from Italian or Russian from Ukrainian, and
// a single-label classifier cannot see the English inside a Georgian
// paragraph (fastText named a half-and-half paragraph `ka 0.83`); CLD2
// names up to three languages per paragraph with the share of each, and
// says when it is unreliable. The detector runs in the account's own venv
// on the account's own text (runtime/langid/, installed by bootstrap.sh);
// only the verdicts come back. `shares` is the text by language, each
// paragraph's percentages weighted by its letters; `dominant` counts
// paragraphs by their first language; `unreliable` counts the paragraphs
// CLD2 would only guess at (a code line, a two-letter answer, Georgian in
// Latin letters — the script shares still see that one). A paragraph
// under 20 letters is not sent. Without the venv the section says
// `unavailable`, never a guess.
const lettersOf = p => Object.values(scriptCounts(p)).reduce((a, b) => a + b, 0);
export function langidCmd(home = os.homedir(), root = process.env.AGENT_FABRIC_ROOT ?? path.join(home, 'projects', 'agent-fabric')) {
  return [path.join(home, '.cache', 'agent-fabric', 'langid', 'venv', 'bin', 'python'), path.join(root, 'runtime', 'langid', 'langid.py')];
}
export function languages(paragraphs, { home, root, exec = execFileSync } = {}) {
  const judged = paragraphs.filter(p => lettersOf(p) >= 20);
  const [py, script] = langidCmd(home, root);
  if (!fs.existsSync(py)) return { status: 'unavailable', why: 'no detector venv (runtime/langid/install.sh)' };
  if (!judged.length) return { status: 'ok', paragraphs: 0, unreliable: 0, shares: {}, dominant: {} };
  let out;
  try { out = exec(py, [script], { input: JSON.stringify(judged), encoding: 'utf8', maxBuffer: 16 * 1024 * 1024, timeout: 60000 }); }
  catch (e) { return { status: 'unavailable', why: String(e?.stderr ?? e?.message ?? e).trim().split('\n').pop().slice(0, 160) }; }
  let verdicts; try { verdicts = JSON.parse(out); } catch { return { status: 'unavailable', why: 'the detector answered something that is not JSON' }; }
  if (!Array.isArray(verdicts) || verdicts.length !== judged.length) return { status: 'unavailable', why: 'the detector answered for a different number of paragraphs' };
  const weight = {}, dominant = {}; let total = 0, unreliable = 0;
  verdicts.forEach((v, i) => {
    const [reliable, , details] = Array.isArray(v) ? v : [false, 0, []];
    if (!reliable || !Array.isArray(details) || !details.length) { unreliable += 1; return; }
    const n = lettersOf(judged[i]); total += n;
    for (const [code, pct] of details) weight[code] = (weight[code] ?? 0) + n * pct / 100;
    dominant[details[0][0]] = (dominant[details[0][0]] ?? 0) + 1;
  });
  const sorted = o => Object.fromEntries(Object.entries(o).sort((x, y) => y[1] - x[1]));
  const shares = total ? sorted(Object.fromEntries(Object.entries(weight).map(([k, v]) => [k, Math.round(1000 * v / total) / 10]))) : {};
  return { status: 'ok', paragraphs: judged.length, unreliable, shares, dominant: sorted(dominant) };
}
// RECALL — is the corpus read? A drain is instrumented end to end; the
// read-back never was: a slice read is a plain Read in the session's
// record and nothing counted them, so a slice with a poor cue could be
// written and never opened and nobody would know (the owner, 2026-09-20).
// This walks the account's session records in the window — every
// session and its subagents, not the newest five — and counts the tool
// calls that touch the corpus: an index (`INDEX.md` under a project's
// .agent-fabric/memory/<role>/ or the fabric's memory/domains/<x>/), a
// slice (any other .md there, or under memory/shared/), the authored
// identity (identities/roles/<role>/charter|brief|recall.md), and a
// search (Grep/Glob whose path is one of those directories, or a Bash
// command naming one). Counts and paths only — never a line of what was
// read. `sessions_without_recall` is the number that matters: a session
// that opened neither an index nor a slice worked without the corpus.
// Anchored at a path boundary, not at a slash: a session that reads
// `.agent-fabric/memory/<role>/INDEX.md` relative to its working copy —
// the shape every instruction file shows — is reading the corpus.
const CORPUS_RE = /(?:^|\/)(?:\.agent-fabric\/memory\/|memory\/(?:domains|shared)\/)/;
const IDENTITY_RE = /(?:^|\/)identities\/roles\/[a-z0-9-]+\/(?:charter|brief|recall)\.md$/;
export function recallKind(tool, input) {
  const p = typeof input?.file_path === 'string' ? input.file_path : typeof input?.path === 'string' ? input.path : '';
  if (tool === 'Read') {
    if (IDENTITY_RE.test(p)) return { kind: 'identity', path: p };
    if (!CORPUS_RE.test(p) || !/\.md$/.test(p) || /\/README\.md$/.test(p)) return null;   // crossref.json, a drain report, a README: not a slice
    return { kind: /\/INDEX\.md$/.test(p) ? 'index' : 'slice', path: p };
  }
  if (tool === 'Grep' || tool === 'Glob') return CORPUS_RE.test(p) || CORPUS_RE.test(String(input?.pattern ?? '')) ? { kind: 'search', path: p || String(input?.pattern ?? '') } : null;
  if (tool === 'Bash') {
    const m = String(input?.command ?? '').match(/(?:^|[\s'"=])((?:\S*\/)?(?:\.agent-fabric\/memory\/|memory\/(?:domains|shared)\/)\S*)/);
    return m ? { kind: 'search', path: m[1].replace(/["'`;|)]+$/, '') } : null;
  }
  return null;
}
export function recall(home = os.homedir(), { hours = 24, now = Date.now() } = {}) {
  const root = path.join(home, '.claude', 'projects');
  const files = [];
  try {
    for (const d of fs.readdirSync(root)) {
      const dir = path.join(root, d);
      let names; try { names = fs.readdirSync(dir); } catch { continue; }
      for (const n of names) {
        if (n.endsWith('.jsonl')) files.push(path.join(dir, n));
        const subs = path.join(dir, n, 'subagents');
        let inner; try { inner = fs.readdirSync(subs); } catch { continue; }
        for (const a of inner) if (/^agent-.*\.jsonl$/.test(a)) files.push(path.join(subs, a));
      }
    }
  } catch { return { status: 'no-records', hours }; }
  const recent = files.filter(f => { try { return now - fs.statSync(f).mtimeMs <= hours * 3600000; } catch { return false; } });
  if (!recent.length) return { status: 'no-records', hours };
  const counts = { index: 0, slice: 0, search: 0, identity: 0 };
  const slices = {}; let sessions = 0, turns = 0, without = 0;
  const since = now - hours * 3600000;
  for (const f of recent) {
    let body; try { body = fs.readFileSync(f, 'utf8'); } catch { continue; }
    let mine = 0, own = 0;
    // The window applies to each RECORD: a long or resumed session's file
    // is touched today and holds weeks of turns; counting them all
    // inflated reads and turns and let an old index read stand for
    // recent work. A record without a parseable timestamp is inside the
    // window (the file is).
    for (const line of body.split('\n')) {
      if (!line.includes('"assistant"')) continue;
      let d; try { d = JSON.parse(line); } catch { continue; }
      if (d?.type !== 'assistant') continue;
      const ts = Date.parse(d.timestamp); if (Number.isFinite(ts) && ts < since) continue;
      own += 1;
      for (const b of d.message?.content ?? []) {
        if (b?.type !== 'tool_use') continue;
        const r = recallKind(b.name, b.input);
        if (!r) continue;
        counts[r.kind] += 1;
        if (r.kind === 'index' || r.kind === 'slice') { mine += 1; slices[r.path] = (slices[r.path] ?? 0) + 1; }
      }
    }
    if (!own) continue;   // a record with no assistant turn is not a session
    sessions += 1; turns += own;
    if (!mine) without += 1;
  }
  const top = Object.entries(slices).sort((a, b) => b[1] - a[1]).slice(0, 10).map(([p, n]) => ({ path: p.replace(home, '~'), reads: n }));
  return { status: 'ok', hours, sessions, turns, ...counts, sessions_without_recall: without, top };
}

export function notesDir(home = os.homedir(), env = process.env, login = (() => { try { return os.userInfo().username; } catch { return 'unknown'; } })()) {
  return path.join(env.XDG_STATE_HOME ?? path.join(home, '.local', 'state'), 'agent-fabric', 'agents', login, 'notes');
}
export function script(home = os.homedir(), { hours = 24, limit = 5, now = Date.now(), notes = notesDir(home), langid = languages } = {}) {
  const root = path.join(home, '.claude', 'projects');
  let files = [];
  try {
    for (const d of fs.readdirSync(root)) {
      const dir = path.join(root, d);
      let names; try { names = fs.readdirSync(dir); } catch { continue; }
      for (const n of names) {
        if (!n.endsWith('.jsonl')) continue;
        const f = path.join(dir, n);
        let st; try { st = fs.statSync(f); } catch { continue; }
        if (now - st.mtimeMs <= hours * 3600000) files.push({ f, mtime: st.mtimeMs });
      }
    }
  } catch { return { status: 'no-records' }; }
  files.sort((a, b) => b.mtime - a.mtime); files = files.slice(0, limit);
  // The notes: every file under the notes directory touched in the window,
  // its paragraphs binned like thinking blocks.
  const noteCounts = {}; const noteBlocks = { only: 0, mixed: 0, latin: 0, empty: 0 }; let noteFiles = 0; const noteParas = [];
  try {
    for (const n of fs.readdirSync(notes)) {
      const f = path.join(notes, n);
      let st; try { st = fs.statSync(f); } catch { continue; }
      if (!st.isFile() || now - st.mtimeMs > hours * 3600000) continue;
      let body; try { body = fs.readFileSync(f, 'utf8'); } catch { continue; }
      noteFiles += 1;
      paragraphs(body, noteCounts, noteBlocks, noteParas);
    }
  } catch { /* no notes directory: reported as none */ }
  const notesOut = noteFiles ? { status: 'ok', files: noteFiles, ...shares(noteCounts), blocks: noteBlocks, language: langid(noteParas, { home }) } : { status: 'none', dir: notes };
  if (!files.length) return { status: 'no-records', hours, notes: notesOut };
  const thinking = {}, text = {}; let turns = 0;
  const blocks = { only: 0, mixed: 0, latin: 0, empty: 0 };
  const bin = counts => binInto(blocks, counts);
  for (const { f } of files) {
    let body; try { body = fs.readFileSync(f, 'utf8'); } catch { continue; }
    for (const line of body.split('\n')) {
      if (!line.includes('"assistant"')) continue;
      let d; try { d = JSON.parse(line); } catch { continue; }
      if (d?.type !== 'assistant') continue;
      turns += 1;
      for (const b of d.message?.content ?? []) {
        if (b?.type === 'thinking' && typeof b.thinking === 'string') { const c = scriptCounts(b.thinking); bin(c); for (const [k, v] of Object.entries(c)) thinking[k] = (thinking[k] ?? 0) + v; }
        else if (b?.type === 'text' && typeof b.text === 'string') scriptCounts(b.text, text);
      }
    }
  }
  return { status: 'ok', hours, files: files.length, turns, thinking: shares(thinking), thinking_blocks: blocks, text: shares(text), notes: notesOut, workers: workerTranscripts(files, { hours, now, langid: p => langid(p, { home }) }) };
}

// THE TOKENS. The usage windows (`usage`) are the Claude account's, one
// number for every login signed into it; which login consumed what is
// nowhere but in each login's own session records, where every assistant
// message carries the model and its usage (input, cache creation, cache
// read, output). Summed here per model over a window, deduplicated by
// request — the harness writes one record per content block, all with
// the same usage — for the session transcripts and the subagent
// transcripts beside them (a dispatched agent spends the same account).
// A file older than the window holds nothing in it; a record is in the
// window by its own timestamp. `equiv` is the sum in input-token
// equivalents at the API's own ratios — cache write 1.25×, cache read
// 0.1×, output 5× — a proxy for what the subscription meter weighs, not
// its figure: the meter's weighting is unpublished, one model tier is
// not priced here against another, and what the same account spends
// outside this host (the web app, a phone) is invisible. Read back
// 2026-09-19: this login's session, 155 requests, 22.5M cache reads,
// 68k output. Counts only; nothing of the text leaves.
export const TOKEN_RATIOS = { input: 1, cache_write: 1.25, cache_read: 0.1, output: 5 };
export const TOKENS_DAYS = 7;
export function equivalent(u, ratios = TOKEN_RATIOS) {
  return Math.round(u.input * ratios.input + u.cache_write * ratios.cache_write + u.cache_read * ratios.cache_read + u.output * ratios.output);
}
export function tokens(home = os.homedir(), { days = TOKENS_DAYS, now = Date.now() } = {}) {
  const root = path.join(home, '.claude', 'projects');
  const since = now - days * 86400000;
  const files = [];
  try {
    for (const d of fs.readdirSync(root)) {
      const dir = path.join(root, d);
      let names; try { names = fs.readdirSync(dir); } catch { continue; }
      for (const n of names) {
        if (n.endsWith('.jsonl')) { files.push({ f: path.join(dir, n), kind: 'session' }); continue; }
        const sub = path.join(dir, n, 'subagents');
        let subs; try { subs = fs.readdirSync(sub); } catch { continue; }
        for (const a of subs) if (/^agent-.*\.jsonl$/.test(a)) files.push({ f: path.join(sub, a), kind: 'subagent' });
      }
    }
  } catch { return { status: 'no-records', days }; }
  const models = {}; const kinds = { session: 0, subagent: 0 }; const seen = new Set();
  let read = 0, first = null, last = null;
  for (const { f, kind } of files) {
    let st; try { st = fs.statSync(f); } catch { continue; }
    if (st.mtimeMs < since) continue;
    let body; try { body = fs.readFileSync(f, 'utf8'); } catch { continue; }
    read += 1;
    for (const line of body.split('\n')) {
      if (!line.includes('"assistant"') || !line.includes('"usage"')) continue;
      let d; try { d = JSON.parse(line); } catch { continue; }
      if (d?.type !== 'assistant') continue;
      const m = d.message; const u = m?.usage;
      if (!u || typeof u !== 'object') continue;
      const ts = Date.parse(d.timestamp);
      if (!Number.isFinite(ts) || ts < since || ts > now) continue;
      const key = d.requestId ?? m.id;
      if (!key || seen.has(key)) continue;
      seen.add(key);
      if (typeof m.model !== 'string' || m.model.startsWith('<')) continue;   // <synthetic>: the harness's own, no usage
      const model = m.model;
      const t = (models[model] ??= { requests: 0, input: 0, cache_write: 0, cache_read: 0, output: 0 });
      t.requests += 1;
      t.input += Number(u.input_tokens) || 0;
      t.cache_write += Number(u.cache_creation_input_tokens) || 0;
      t.cache_read += Number(u.cache_read_input_tokens) || 0;
      t.output += Number(u.output_tokens) || 0;
      kinds[kind] += 1;
      if (first === null || ts < first) first = ts;
      if (last === null || ts > last) last = ts;
    }
  }
  if (!read || !seen.size) return { status: 'no-records', days };
  // Two paths, two bills: a model id with a vendor prefix (z-ai/glm-5.3,
  // anthropic/claude-opus-5) was served by the broker on the account's
  // OpenRouter key; a bare id (claude-opus-5) by Anthropic directly, on
  // the Claude account's subscription — the one the usage windows meter.
  const zero = () => ({ requests: 0, input: 0, cache_write: 0, cache_read: 0, output: 0 });
  const paths = { claude: zero(), broker: zero() };
  for (const [model, t] of Object.entries(models)) {
    t.equiv = equivalent(t); t.path = model.includes('/') ? 'broker' : 'claude';
    for (const k of Object.keys(paths[t.path])) paths[t.path][k] += t[k];
  }
  for (const t of Object.values(paths)) t.equiv = equivalent(t);
  const sorted = Object.fromEntries(Object.entries(models).sort((a, b) => b[1].equiv - a[1].equiv));
  return { status: 'ok', days, files: read, requests: kinds, first: first ? new Date(first).toISOString() : null, last: last ? new Date(last).toISOString() : null,
           models: sorted, claude: paths.claude, broker: paths.broker, ratios: TOKEN_RATIOS };
}

// THE WORKERS. A subagent's transcript is stored beside its session's
// (<session>/subagents/agent-*.jsonl) with a sidecar the harness writes,
// agent-*.meta.json, whose agentType names the type dispatched: the
// locale worker of the language-culture bridge
// (identities/roles/language-culture/charter.md) is the one whose sidecar
// says locale-worker — read back 2026-09-17, when "no tool_use block"
// turned out to fit no transcript: the hand-back itself is a tool_use
// (SubagentHandback), and the harness refuses to spawn an agent with no
// tool at all, so the worker carries one inert tool. Its USER records are
// the worker's input, which the bridge composed, less the harness's own
// <system-reminder> spans (English, injected into every subagent, and not
// the bridge's doing): a Latin paragraph left is English reaching the
// worker, the leak the construction exists to prevent. Its assistant text
// is the answer. Any tool_use but the hand-back is counted as tool_uses —
// a worker that used a tool is a worker with one. Paragraphs binned like
// the notes; counts only.
export const WORKER_TYPE = 'locale-worker';
const REMINDER_RE = /<system-reminder>[\s\S]*?(<\/system-reminder>|$)/g;
export function workerTranscripts(files, { hours = 24, now = Date.now(), type = WORKER_TYPE, langid = null } = {}) {
  const input = {}, text = {}; const inputBlocks = { only: 0, mixed: 0, latin: 0, empty: 0 }, textBlocks = { only: 0, mixed: 0, latin: 0, empty: 0 }; const inputParas = [], textParas = [];
  let n = 0, turns = 0, others = 0, toolUses = 0;
  for (const { f } of files) {
    const dir = path.join(path.dirname(f), path.basename(f, '.jsonl'), 'subagents');
    let names; try { names = fs.readdirSync(dir); } catch { continue; }
    for (const name of names) {
      if (!/^agent-.*\.jsonl$/.test(name)) continue;
      const p = path.join(dir, name);
      let st; try { st = fs.statSync(p); } catch { continue; }
      if (now - st.mtimeMs > hours * 3600000) continue;
      let meta = null; try { meta = JSON.parse(fs.readFileSync(p.replace(/\.jsonl$/, '.meta.json'), 'utf8')); } catch { /* no sidecar: not a worker */ }
      if (meta?.agentType !== type) { others += 1; continue; }
      let body; try { body = fs.readFileSync(p, 'utf8'); } catch { continue; }
      n += 1;
      for (const line of body.split('\n')) {
        let d; try { d = JSON.parse(line); } catch { continue; }
        const c = d?.message?.content;
        if (d?.type === 'user') {
          const texts = typeof c === 'string' ? [c] : Array.isArray(c) ? c.filter(b => b?.type === 'text' && typeof b.text === 'string').map(b => b.text) : [];
          for (const t of texts) { const own = t.replace(REMINDER_RE, ''); if (own.trim()) paragraphs(own, input, inputBlocks, inputParas); }
        } else if (d?.type === 'assistant') {
          turns += 1;
          for (const b of Array.isArray(c) ? c : []) {
            if (b?.type === 'text' && typeof b.text === 'string') paragraphs(b.text, text, textBlocks, textParas);
            else if (b?.type === 'tool_use' && b.name !== 'SubagentHandback') toolUses += 1;
          }
        }
      }
    }
  }
  if (!n) return { status: 'none', other_subagents: others };
  return { status: 'ok', files: n, other_subagents: others, turns, tool_uses: toolUses,
           input: { ...shares(input), blocks: inputBlocks, ...(langid ? { language: langid(inputParas) } : {}) }, text: { ...shares(text), blocks: textBlocks, ...(langid ? { language: langid(textParas) } : {}) } };
}

// THE DRAIN, over the control plane (the CEO, 2026-09-17: the way out of
// god mode). Until now a drain read another account's home through sudo
// (bin/fabric-host drain). Here the account's own daemon runs the
// harvester on its own memory — one bundle per memory directory Claude
// Code keeps for it (~/.claude/projects/<slug>/memory), each resolved to
// the working copy it belongs to by matching the slug against the
// account's ~/projects/* — and answers with the bundles gzipped and
// base64, in parts that fit the relay's 128 KiB message limit, plus each
// harvest report (`needs_rendering` and the skipped list included). No
// request field reaches argv: the op takes none. The harvester refuses
// the whole drain when a memory carries a credential by shape
// (harvest_memory.CREDENTIAL_PATTERNS), so no secret reaches the channel;
// a memory directory with no working copy beside it, or with two, is
// named and left where it is.
export const MEMORY_PART_BYTES = 90 * 1024;
// The harness's name for a launch directory: every character that is not
// a letter or a digit becomes `-` — `/` and `.` alike (read back 2026-09-17:
// ~/projects/foo.bar is -home-…-projects-foo-bar). The harvester's
// memory_slug is the same rule.
export function memorySlug(dir) { return path.resolve(dir).replace(/[^A-Za-z0-9]/g, '-'); }
export function memoryDirs(home = os.homedir(), projectsDir = path.join(home, 'projects')) {
  const root = path.join(home, '.claude', 'projects');
  let slugs; try { slugs = fs.readdirSync(root); } catch { return []; }
  let copies = []; try { copies = fs.readdirSync(projectsDir).map(d => path.join(projectsDir, d)).filter(d => { try { return fs.statSync(d).isDirectory(); } catch { return false; } }); } catch { /* no projects dir */ }
  const bySlug = new Map(); const ambiguous = new Set();
  for (const d of copies) { const k = memorySlug(d); if (bySlug.has(k)) ambiguous.add(k); else bySlug.set(k, d); }
  const out = [];
  for (const slug of slugs) {
    const memory = path.join(root, slug, 'memory');
    let n = 0; try { n = fs.readdirSync(memory).filter(f => f.endsWith('.md') && f !== 'MEMORY.md').length; } catch { continue; }
    if (!n) continue;
    // Two working copies with one slug (foo.bar and foo-bar): the
    // harness cannot tell them apart and neither can this; named, not guessed.
    out.push({ slug, memory, files: n, working_copy: ambiguous.has(slug) ? null : (bySlug.get(slug) ?? null), ...(ambiguous.has(slug) ? { ambiguous: true } : {}) });
  }
  return out;
}
export async function memory(home = os.homedir(), { root = process.env.AGENT_FABRIC_ROOT ?? path.join(home, 'projects', 'agent-fabric'), exec = execFileP, dirs = memoryDirs(home), all = false, partBytes = MEMORY_PART_BYTES } = {}) {
  const tool = path.join(root, 'tools', 'fabric', 'harvest_memory.py');
  const bundles = [];
  for (const d of dirs) {
    if (!d.working_copy) { bundles.push({ slug: d.slug, files: d.files, status: d.ambiguous ? 'ambiguous-working-copy' : 'no-working-copy' }); continue; }
    // The tar on stdout, the report on stderr: one run gives both.
    const args = [tool, '--bundle', '-', '--memory', d.memory, '--working-copy', d.working_copy, ...(all ? ['--all'] : [])];
    let r;
    try { r = await exec('python3', args, { encoding: 'buffer', maxBuffer: 64 * 1024 * 1024, env: { ...process.env, AGENT_FABRIC_ROOT: root }, timeout: 120000 }); }
    catch (e) { bundles.push({ slug: d.slug, files: d.files, working_copy: d.working_copy, status: 'harvest-failed', error: String(e?.stderr ?? e?.message ?? e).slice(-400) }); continue; }
    const tar = Buffer.from(r.stdout ?? '');
    let report = null;
    try { const j = JSON.parse(String(r.stderr ?? '')); report = { claims: j.claims, counts: j.counts, needs_rendering: j.needs_rendering ?? [], skipped_no_roles_class: j.skipped_no_roles_class ?? [] }; } catch { report = null; }
    const gz = zlib.gzipSync(tar, { level: 9 });
    const b64 = gz.toString('base64');
    const parts = [];
    for (let i = 0; i < b64.length; i += partBytes) parts.push(b64.slice(i, i + partBytes));
    bundles.push({ slug: d.slug, files: d.files, working_copy: d.working_copy, status: 'ok', bytes: tar.length, gzip_bytes: gz.length,
                   sha256: crypto.createHash('sha256').update(tar).digest('hex'), parts: parts.length, report, _parts: parts });
  }
  return { status: 'ok', bundles };
}

// The account's own home, measured: what /home's space is spent on, and by
// whom (2026-10-04: /home on a host reached 90% and no account could say
// whose homes held it; the owner ran sudo du by hand). Each daemon
// measures its OWN home and nothing else: its largest top-level entries
// and every target/ directory under ~/projects to depth 3 — names and
// sizes only, never contents. One scan: du -xsk over the top-level entries
// but projects/, and du -xk -d 3 over projects/, whose own line is its
// total and whose target/ lines are the build directories (a target/
// inside a target/ is not counted twice). The total is the sum of the
// entries. du runs through the injected exec, bounded: one that stops at
// its bound or reads part of a tree (exit 1 on an unreadable file) still
// reports what it measured, the status says partial and `errors` says
// why; a home that cannot be listed is failed, never a crash. Sizes in
// KiB, du's own unit. du's records end in NUL (-0), never a newline: a
// file name may hold one, and split on lines it invented entries, totals
// and target/ paths; a record whose path is not under the home is dropped
// (review of #92, round 4).
export const DISK_TIMEOUT_MS = 150000;
export const DISK_MAX_BUFFER = 64 * 1024 * 1024;
export const DISK_TOP = 5;
export async function disk(home = os.homedir(), { exec = execFileP, timeoutMs = DISK_TIMEOUT_MS, readdir = fs.readdirSync } = {}) {
  let names;
  try { names = readdir(home); }
  catch (e) { return { status: 'failed', error: `${home} could not be listed (${e.code ?? e.message})` }; }
  const errors = [];
  const du = async (args, what) => {
    let text = '', said = '';
    // LC_ALL=C: du's complaints are read below, so they must not be translated.
    const opts = { encoding: 'utf8', timeout: timeoutMs, maxBuffer: DISK_MAX_BUFFER, env: { ...process.env, LC_ALL: 'C' } };
    try { const r = await exec('du', args, opts); text = String(typeof r === 'string' ? r : r?.stdout ?? ''); said = String(r?.stderr ?? ''); }
    catch (e) {
      text = String(e?.stdout ?? ''); said = String(e?.stderr ?? '');
      const why = e?.code === 'ERR_CHILD_PROCESS_STDIO_MAXBUFFER' ? `du's output passed its ${DISK_MAX_BUFFER / 1048576} MiB bound`
        : e?.killed || e?.signal ? `du stopped at its ${timeoutMs / 1000} s bound` : `du exit ${e?.code ?? '?'}`;
      errors.push(`${what}: ${why}${text.trim() ? ', partial' : ''}`);
    }
    // What du could not read is not in the total: say how much, and where to
    // look first. A rootless podman's volumes are owned by a sub-UID, so a
    // home that runs containers has some.
    const unread = said.split('\n').map(l => /^du: cannot (?:read directory|access) (.*): [^:]*$/.exec(l)?.[1]).filter(Boolean);
    if (unread.length) errors.push(`${what}: ${unread.length} path${unread.length === 1 ? '' : 's'} du could not read, not counted; the first: ${unread[0]}`);
    const sizes = new Map(), outside = [];
    const inside = p => p === home || p.startsWith(home.endsWith(path.sep) ? home : home + path.sep);
    // Each record ends in NUL (-0): a newline is part of a name, never a separator.
    for (const rec of text.split('\0')) {
      const m = /^(\d+)\t([\s\S]+)$/.exec(rec);
      if (!m) continue;
      if (inside(m[2])) sizes.set(m[2], Number(m[1])); else outside.push(m[2]);
    }
    if (outside.length) errors.push(`${what}: ${outside.length} record${outside.length === 1 ? '' : 's'} outside ${home} dropped; the first: ${outside[0]}`);
    return sizes;
  };
  const projects = path.join(home, 'projects');
  const others = names.filter(n => n !== 'projects').map(n => path.join(home, n));
  const [entries, tree] = await Promise.all([
    others.length ? du(['-0', '-xsk', '--', ...others], 'home entries') : Promise.resolve(new Map()),
    names.includes('projects') ? du(['-0', '-xk', '--max-depth=3', '--', projects], 'projects') : Promise.resolve(new Map()),
  ]);
  const largest = [...entries].map(([p, kb]) => ({ name: path.basename(p), kb }));
  if (tree.has(projects)) largest.push({ name: 'projects', kb: tree.get(projects) });
  largest.sort((a, b) => b.kb - a.kb);
  const targets = [...tree].filter(([p]) => path.basename(p) === 'target' && !path.relative(projects, path.dirname(p)).split(path.sep).includes('target'))
    .map(([p, kb]) => ({ path: path.relative(home, p), kb })).sort((a, b) => b.kb - a.kb);
  return { status: errors.length ? 'partial' : 'ok', home, total_kb: largest.reduce((n, e) => n + e.kb, 0),
           largest: largest.slice(0, DISK_TOP), targets, targets_kb: targets.reduce((n, t) => n + t.kb, 0),
           ...(errors.length ? { errors } : {}) };
}

// Everything, for `status`; the sections a request names, otherwise.
export async function collect(op, ctx = {}) {
  const wants = op === 'status' ? ['identity', 'usage', 'keys', 'fabric', 'session'] : op === 'tokens' ? ['identity', 'tokens'] : [op];
  const data = {};
  const guard = async (name, fn) => { try { data[name] = await fn(); } catch (e) { data[name] = { status: 'failed', error: String(e?.message ?? e).slice(0, 200) }; } };
  await Promise.all(wants.map(name => {
    if (name === 'identity') return guard(name, () => identity(ctx.home, ctx.who));   // ctx.who unset: whoami() per request, so a rebind shows
    if (name === 'usage') return guard(name, () => ctx.usageCached ? ctx.usageCached() : usage(ctx.home, ctx.fetch));
    if (name === 'keys') return guard(name, async () => [...keys(ctx.home), await signingSecret(ctx.exec), storeRefusal(ctx.home, ctx.storeDir)]);
    if (name === 'fabric') return guard(name, () => fabric(ctx.root, ctx.exec));
    if (name === 'session') return guard(name, () => session(ctx.uid, ctx.exec));
    if (name === 'presence') return guard(name, () => presence(ctx.presenceOpts));
    if (name === 'script') return guard(name, () => script(ctx.home));
    if (name === 'recall') return guard(name, () => recall(ctx.home));
    if (name === 'tokens') return guard(name, () => tokens(ctx.home, ctx.days ? { days: ctx.days } : {}));
    if (name === 'memory') return guard(name, () => memory(ctx.home, { exec: ctx.exec, all: true }));
    // The machine now, and the pressure this daemon sampled up to now (pressure.mjs).
    if (name === 'host') return guard(name, () => ({ ...host(ctx.hostOpts), memory_pressure: memoryPressure(ctx.pressureOpts) }));
    // One scan per daemon however many ask at once (agentd's diskKeeper).
    if (name === 'disk') return guard(name, () => ctx.diskCached ? ctx.diskCached() : disk(ctx.home, ctx.diskOpts));
    if (name === 'jobs') return guard(name, () => jobs({ home: ctx.home, root: ctx.root, ...(ctx.jobsOpts ?? {}) }));
    if (name === 'accounts') return guard(name, () => ctx.accountsCached ? ctx.accountsCached() : accounts(ctx.home, ctx.accountsOpts));
    return Promise.resolve();
  }));
  return data;
}
