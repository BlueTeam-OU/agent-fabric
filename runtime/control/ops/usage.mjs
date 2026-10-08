// runtime/control/ops/usage.mjs — the Claude account's usage windows, the Claude accounts this login observes, and the tokens its own sessions spent.
// A part of ops.mjs, which re-exports it; ops.mjs's header is the contract
// every extractor here keeps.

import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { syncedVar } from '../gzcoord.mjs';
import { readJson, execFileP } from './util.mjs';

export const USAGE_URL = 'https://api.anthropic.com/api/oauth/usage';
export const MESSAGES_URL = 'https://api.anthropic.com/v1/messages';

// A login on a template runs on its setup-token, which cannot read the
// usage endpoint (HTTP 403, user:inference only) — but every inference
// reply carries the account's windows in anthropic-ratelimit-unified-*
// headers (docs/live-checks/2026-10-08-usage-from-inference-headers.md).
// So the windows are read from one reply: the smallest model, one output
// token, against the account's own allowance. The model is a pinned id,
// not routing's: the probe must answer the same way whatever a class rides.
export const PROBE_MODEL = 'claude-haiku-4-5-20251001';

// The headers give a fraction and epoch seconds; the windows are reported
// as the usage endpoint reports them, a percentage and an ISO time.
export function windowsFromHeaders(get) {
  // Number(null) is 0: an absent header must stay absent, never a reading of 0%.
  const num = h => { const v = get(h); return typeof v === 'string' && v.trim() !== '' ? Number(v) : NaN; };
  const win = k => {
    const u = num(`anthropic-ratelimit-unified-${k}-utilization`);
    const r = num(`anthropic-ratelimit-unified-${k}-reset`);
    const status = get(`anthropic-ratelimit-unified-${k}-status`);
    if (!Number.isFinite(u) && !Number.isFinite(r)) return null;
    return { utilization: Number.isFinite(u) ? Math.round(u * 1000) / 10 : null,
             resets_at: Number.isFinite(r) && r > 0 ? new Date(r * 1000).toISOString() : null,
             ...(typeof status === 'string' && /^[a-z_]{1,32}$/.test(status) ? { status } : {}) };
  };
  return { five_hour: win('5h'), seven_day: win('7d') };
}

async function fromInference(tok, fetchFn, url) {
  let r;
  try {
    r = await fetchFn(url, { method: 'POST', signal: AbortSignal.timeout(15000),
      headers: { Authorization: `Bearer ${tok}`, 'anthropic-beta': 'oauth-2025-04-20', 'anthropic-version': '2023-06-01', 'content-type': 'application/json' },
      body: JSON.stringify({ model: PROBE_MODEL, max_tokens: 1, messages: [{ role: 'user', content: '.' }] }) });
  } catch { return { status: 'read-failed', via: 'setup-token' }; }
  // A full window answers 429 and still names its windows: that is a reading.
  const w = windowsFromHeaders(k => r.headers?.get?.(k) ?? null);
  if (!w.five_hour && !w.seven_day) return { status: 'read-failed', via: 'setup-token', http: r.status };
  return { status: 'ok', via: 'setup-token', ...w, subscription: null };
}

// The five-hour and seven-day windows, read with the account's own OAuth
// token, which goes into one header and nowhere else.
export async function usage(home = os.homedir(), fetchFn = globalThis.fetch, url = USAGE_URL, messagesUrl = MESSAGES_URL) {
  const setup = syncedVar('CLAUDE_CODE_OAUTH_TOKEN', home);
  if (setup) return fromInference(setup, fetchFn, messagesUrl);
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
// `user:inference` only: the usage endpoint refuses it, and usage() above
// reads its five-hour and seven-day windows from the headers of an
// inference call it pays for. A sign-in here reads the account's whole
// report, the per-model weekly meter included, with no model call
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
