// runtime/control/accounts.mjs — the Claude accounts this login observes
// (ops.mjs `accounts`; docs/adr/ADR-031-claude-accounts-assigned-applied-and-proved-by-signed-action.md). Run as the observing login,
// in practice the coordinator's.
//
//   fabric-accounts login <account>   sign one Claude account in, once: opens the harness
//                                     in that account's own config directory; /login in the
//                                     browser AS THAT ACCOUNT, then /exit. A real terminal.
//   fabric-accounts list              each observed account: signed in, email, sign-in expiry
//   fabric-accounts read              read every account's windows now (the harness's /usage)
//   fabric-accounts assign <login…|all> <account> [--no-restart] [--no-sync]
//                                     which Claude account those logins run on: the reference in each
//                                     login's Doppler config, then `fabric-ctl <logins> secrets-sync
//                                     --expect <template's fingerprint> --restart` — every account
//                                     applies it, proves it, and resumes a running session on it
//   fabric-accounts templates         each Doppler template's token fingerprint, to name the account
//                                     behind a login's `setup-token <sha>` (fabric-ctl, fabric-status)
//
// Prints no token: a sign-in is described by its email, its expiry and
// whether a refresh token is held — never by a value.

import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync, execFileSync } from 'node:child_process';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { accountsDir, accountSlugs, accounts, claudeBin, ACCOUNT_SLUG, takeReadLock } from './ops.mjs';
import { placements } from './ctl.mjs';
import { FABRIC_ROOT } from '../../communication/gzcoord/scripts/gzmsg.mjs';

const USAGE = `usage: fabric-accounts login <account> | list | read | templates | assign <login…|all> <account> [--no-restart] [--no-sync]
  <account>: lowercase letters, digits and hyphens — the account's email with @ and . as -,
             e.g. claude-pzhuy-8alias-com (the Doppler template's name without its prefix)`;

function readJson(file) { try { return JSON.parse(fs.readFileSync(file, 'utf8')); } catch { return null; } }

// What a config directory holds, in words: no token leaves this function.
export function describe(dir, now = Date.now()) {
  const oauth = readJson(path.join(dir, '.credentials.json'))?.claudeAiOauth ?? null;
  const profile = readJson(path.join(dir, '.claude.json'))?.oauthAccount ?? null;
  const exp = Number(oauth?.expiresAt);
  return {
    slug: path.basename(dir),
    email: profile?.emailAddress ?? null,
    signed_in: Boolean(oauth?.accessToken),
    refresh_token: Boolean(oauth?.refreshToken),
    expires_at: Number.isFinite(exp) ? new Date(exp).toISOString() : null,
    expired: Number.isFinite(exp) ? exp <= now : null,
  };
}

export function listLines(dir, now = Date.now()) {
  const slugs = accountSlugs(dir);
  if (!slugs.length) return [`no Claude account observed under ${dir} — fabric-accounts login <account>`];
  return slugs.map(s => {
    const d = describe(path.join(dir, s), now);
    const state = !d.signed_in ? 'not signed in' : !d.refresh_token ? 'signed in, NO refresh token (will lapse)' : d.expired ? `sign-in lapsed at ${d.expires_at} (the next read renews it)` : `signed in until ${d.expires_at}`;
    return `${s.padEnd(34)} ${(d.email ?? '-').padEnd(34)} ${state}`;
  });
}

// The Doppler templates (environment `claude-accounts`, one config per
// Claude account) by fingerprint: the value goes from doppler into a hash
// and nowhere else. Needs a Doppler token that can read that environment —
// the coordinator's; a login's own read-only token cannot.
export const TEMPLATE_ENV = 'claude-accounts';
export function templates({ exec = execFileSync, project = 'agent-fabric' } = {}) {
  const run = args => exec('doppler', args, { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'], timeout: 30000 });
  const configs = JSON.parse(run(['configs', '--project', project, '--environment', TEMPLATE_ENV, '--json']))
    .map(c => c.name).filter(n => n.startsWith(`${TEMPLATE_ENV}_`)).sort();
  return configs.map(name => {
    let v = '';
    try { v = run(['secrets', 'get', 'CLAUDE_CODE_OAUTH_TOKEN', '--plain', '--project', project, '--config', name]).replace(/\n$/, ''); } catch { v = ''; }
    return { account: name.slice(TEMPLATE_ENV.length + 1), config: name, token_sha256_12: v ? crypto.createHash('sha256').update(v).digest('hex').slice(0, 12) : null };
  });
}

// Which Claude account a login runs on is one line in its own Doppler
// config: a reference to a template (docs/adr/ADR-031-claude-accounts-assigned-applied-and-proved-by-signed-action.md). With none
// it is 'none', and the launcher refuses its plain-claude sessions. Written with the coordinator's Doppler token — a
// login's own is read-only — and read back raw, so the account is named
// by its template, not by a token.
export const templateRef = slug => `\${agent-fabric.${TEMPLATE_ENV}_${slug}.CLAUDE_CODE_OAUTH_TOKEN}`;
export function loginConfigs({ exec = execFileSync, project = 'agent-fabric' } = {}) {
  const names = JSON.parse(exec('doppler', ['configs', '--project', project, '--json'], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'], timeout: 30000 })).map(c => c.name);
  const out = new Map();
  for (const n of names) { const m = /^(agents\d*)_(.+)$/.exec(n); if (m) out.set(m[2], n); }
  return out;
}
export function currentAccount(config, { exec = execFileSync, project = 'agent-fabric' } = {}) {
  let raw = '';
  try { raw = String(exec('doppler', ['secrets', 'get', 'CLAUDE_CODE_OAUTH_TOKEN', '--raw', '--plain', '--project', project, '--config', config], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'], timeout: 30000 })).trim(); }
  catch { return 'none'; }   // no such secret
  const m = new RegExp(`^\\$\\{${project}\\.${TEMPLATE_ENV}_([a-z0-9-]+)\\.CLAUDE_CODE_OAUTH_TOKEN\\}$`).exec(raw);
  return m ? m[1] : raw ? '(not a template reference)' : 'none';
}
export function assign(logins, account, { exec = execFileSync, project = 'agent-fabric' } = {}) {
  const configs = loginConfigs({ exec, project });
  const rows = [];
  for (const login of logins) {
    const config = configs.get(login);
    if (!config) { rows.push({ login, status: 'no-config' }); continue; }
    const from = currentAccount(config, { exec, project });
    if (from === account) { rows.push({ login, config, from, to: account, status: 'unchanged' }); continue; }
    try {
      exec('doppler', ['secrets', 'set', `CLAUDE_CODE_OAUTH_TOKEN=${templateRef(account)}`, '--project', project, '--config', config, '--silent'], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'], timeout: 30000 });
      const now = currentAccount(config, { exec, project });
      rows.push({ login, config, from, to: now, status: now === account ? 'written' : 'not-written' });
    } catch (e) { rows.push({ login, config, from, status: 'failed', reason: String(e.message).split('\n').pop().slice(0, 160) }); }
  }
  return rows;
}

// Once the coordinator's own secrets are on its store (ADR-038), the
// templates live there too, as CLAUDE_ACCOUNT_<SLUG> entries, and an
// assignment is the coordinator writing the token into each login's
// store (it cannot read it back): fabric-secrets store templates and
// assign, which keep every value inside that process. Doppler is read
// until then, exactly as before.
export const onStore = (home = os.homedir()) => {
  try { return fs.readFileSync(path.join(home, '.config', 'agent-fabric', 'secrets-source'), 'utf8').trim() === 'store'; }
  catch { return false; }
};
const store = (args, exec) => JSON.parse(String(exec(path.join(FABRIC_ROOT, 'bin', 'fabric-secrets'), ['store', ...args, '--json'],
  { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'], timeout: 120000 })));
export function storeTemplates({ exec = execFileSync } = {}) {
  return store(['templates'], exec).map(t => ({ ...t, config: 'store' }));
}
export function storeAssign(logins, account, { exec = execFileSync } = {}) {
  try { return store(['assign', account, ...logins], exec); }
  catch (e) {
    // assign exits 1 when a row failed and still prints every row.
    try { return JSON.parse(String(e.stdout)); } catch { return logins.map(login => ({ login, status: 'failed', reason: String(e.stderr ?? e.message).trim().split('\n').pop().slice(0, 160) })); }
  }
}

export async function main(argv = process.argv.slice(2), { home = os.homedir(), env = process.env, stdinTTY = process.stdin.isTTY, spawn = spawnSync, read = accounts, exec = execFileSync, registry } = {}) {
  const [cmd, arg] = argv;
  const dir = accountsDir(home, env);
  if (cmd === 'list' && argv.length === 1) { console.log(listLines(dir).join('\n')); return 0; }
  if (cmd === 'assign') {
    const noSync = argv.includes('--no-sync'), noRestart = argv.includes('--no-restart');
    const rest = argv.slice(1).filter(a => a !== '--no-sync' && a !== '--no-restart');
    if (rest.length < 2) { console.error(USAGE); return 2; }
    const account = rest.at(-1); const who = rest.slice(0, -1);
    const placed = placements(registry).map(p => p.login);
    const logins = who.length === 1 && who[0] === 'all' ? placed : who;
    const unknown = logins.filter(l => !placed.includes(l));
    if (unknown.length) { console.error(`fabric-accounts: not a placed account (runtime/hosts/registry.json): ${unknown.join(', ')}`); return 2; }
    // No way back to a login's own /login: the launcher refuses a session
    // without a template's long-lived token (runtime/openrouter/launch).
    const viaStore = onStore(home);
    const t = (viaStore ? storeTemplates({ exec }) : templates({ exec })).find(x => x.account === account);
    if (!t) { console.error(`fabric-accounts: ${JSON.stringify(account)} is not a template in Doppler environment ${TEMPLATE_ENV} (fabric-accounts templates)${account === 'own' || account === 'none' ? ' — a login runs only on a template\'s token; assign it another account' : ''}`); return 2; }
    if (!t.token_sha256_12) { console.error(`fabric-accounts: template ${account} holds no CLAUDE_CODE_OAUTH_TOKEN yet; nothing written`); return 2; }
    const rows = viaStore ? storeAssign(logins, account, { exec }) : assign(logins, account, { exec });
    for (const r of rows) console.log(`${r.login.padEnd(22)} ${String(r.from ?? '-').padEnd(30)} → ${String(r.to ?? '-').padEnd(30)} ${r.status}${r.reason ? `  ${r.reason}` : ''}`);
    const bad = rows.some(r => !['written', 'unchanged'].includes(r.status));
    const changed = rows.filter(r => r.status === 'written').map(r => r.login);
    const reached = rows.filter(r => ['written', 'unchanged'].includes(r.status)).map(r => r.login);
    if (noSync || !reached.length) { if (changed.length) console.error('fabric-accounts: --no-sync — each changed login applies it at its next fabric-secrets sync'); return bad ? 1 : 0; }
    // Every named login applies it now through its own daemon (a signed
    // action) — the unchanged ones too, since a Doppler reference says
    // nothing of what the account last synced — and proves it against the
    // template's fingerprint; a running session is resumed on it.
    const r = spawn(path.join(FABRIC_ROOT, 'bin', 'fabric-ctl'), [...reached, 'secrets-sync', '--expect', t.token_sha256_12, ...(noRestart ? [] : ['--restart'])], { stdio: 'inherit', env });
    return bad || r.status !== 0 ? 1 : 0;
  }
  if (cmd === 'templates' && argv.length === 1) {
    const t = onStore(home) ? storeTemplates({ exec }) : templates({ exec });
    if (!t.length) { console.log(onStore(home) ? 'no template in this store (fabric-secrets store template-set <slug>)' : `no template in Doppler environment ${TEMPLATE_ENV}`); return 1; }
    for (const x of t) console.log(`${x.account.padEnd(34)} ${x.token_sha256_12 ? `setup-token ${x.token_sha256_12}` : 'no CLAUDE_CODE_OAUTH_TOKEN'}  (${x.config})`);
    return t.every(x => x.token_sha256_12) ? 0 : 1;
  }
  if (cmd === 'read' && argv.length === 1) {
    const r = await read(home, { dir });
    if (r.status === 'none') { console.log(listLines(dir).join('\n')); return 1; }
    for (const a of r.accounts) {
      const m = (a.limits ?? []).map(l => `${l.kind} ${l.percent ?? '-'}%${l.model ? ` (${l.model})` : ''} resets ${String(l.resets_at ?? '-').slice(0, 16)}`).join('; ');
      console.log(`${(a.email ?? a.slug).padEnd(34)} ${a.status}${m ? `  ${m}` : ''}${a.error ? `  ${a.error}` : ''}`);
    }
    return r.accounts.every(a => a.status === 'ok') ? 0 : 1;
  }
  if (cmd === 'login' && argv.length === 2) {
    if (!ACCOUNT_SLUG.test(arg)) { console.error(`fabric-accounts: ${JSON.stringify(arg)} is not an account name\n${USAGE}`); return 2; }
    if (!stdinTTY) { console.error('fabric-accounts: login opens the harness for /login in a browser — run it in a real terminal, not through a tool or `!`'); return 2; }
    const target = path.join(dir, arg);
    fs.mkdirSync(target, { recursive: true, mode: 0o700 });
    fs.chmodSync(target, 0o700);
    // The same lock the reads take: a keeper read overlapping a /login would
    // be two harnesses on one config directory.
    const release = takeReadLock(target);
    if (!release) { console.error(`fabric-accounts: ${arg} is being read right now (the daemon's keeper); try again in a minute`); return 1; }
    console.error(`fabric-accounts: ${arg} — in the harness that opens now: /login, approve in the browser SIGNED IN AS THAT ACCOUNT, then /exit`);
    // The same clean environment the reads use: an inherited token would
    // make the harness think it is already signed in, as someone else.
    const clean = Object.fromEntries(Object.entries(env).filter(([k]) => !['CLAUDE_CODE_OAUTH_TOKEN', 'ANTHROPIC_API_KEY', 'ANTHROPIC_AUTH_TOKEN', 'ANTHROPIC_BASE_URL'].includes(k)));
    let r;
    try { r = spawn(claudeBin(home), [], { cwd: target, env: { ...clean, CLAUDE_CONFIG_DIR: target }, stdio: 'inherit' }); }
    finally { release(); }
    const d = describe(target);
    console.error(d.signed_in ? `fabric-accounts: ${arg} signed in as ${d.email ?? '(email not yet recorded)'}${d.refresh_token ? '' : ' — but with no refresh token; it will lapse'}` : `fabric-accounts: ${arg} is not signed in (no /login completed)`);
    return d.signed_in && r.status === 0 ? 0 : 1;
  }
  console.error(USAGE);
  return 2;
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) main().then(c => process.exit(c)).catch(e => { console.error(`fabric-accounts: ${e.message}`); process.exit(1); });
