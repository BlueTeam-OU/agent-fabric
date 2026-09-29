// runtime/control/ctl.mjs — the coordinator's side of the control plane:
// post one request on the control channel, read the replies, print them.
// Front door: bin/fabric-ctl.
//
//   fabric-ctl <login|all> [status|usage|identity|keys|fabric|session|script|recall|host|accounts|ping] [--json] [--timeout S]
//   fabric-ctl <login|all> host                     the machine, one row per host: load, memory, balloon, disks, leases, largest processes
//   fabric-ctl <login|all> memory --out <dir>       each account's drain bundles, <dir>/<login>/<working copy>.tar
//   fabric-ctl <login|all> upgrade claude [--version V]   an ACTION, signed with the operator's key: bring the harness
//                                                   to the pinned version, restarting a running session (ADR-009)
//   fabric-ctl <login|all> upgrade fabric             an ACTION: fast-forward each account's fabric to this checkout's
//                                                   origin/main and bootstrap it; no session stopped (ADR-009)
//   fabric-ctl <login|all> secrets-sync [--expect SHA12] [--restart]   an ACTION: re-apply the login's Doppler config,
//                                                   check its setup-token, restart a running session on it (docs/adr/ADR-031-claude-accounts-assigned-applied-and-proved-by-signed-action.md)
//   fabric-ctl <login|all> presence                 whether each has a session, since when, as what — any
//                                                   placed account may ask this one (ops.mjs PUBLIC_OPS)
//   fabric-ctl <login|all> secrets-migrate          an ACTION: the account moves its secrets from Doppler to its
//                                                   own store, verified by sha256 of secrets.env (ADR-038)
//   fabric-ctl <login|all> jobs                     each account's open jobs (bin/fabric-jobs; ADR-037)
//   fabric-ctl <login> jobs-add [--topic T] [--project P] [--] "<title>"   an ACTION: the owner's job on that
//                                                   login's list, source `owner` (ADR-037 rule 4)
//   fabric-ctl keygen [--force]                     the operator's signing key: private half into Doppler, public into the registry
//
// A login becomes an address through the registry's placement
// (<host>/<login>); `all` is every placement, addressed as "*". The
// request goes out once; the replies are read from the relay's history
// after the request's own id (since_id, no cursor, nothing left behind)
// every half second until every expected address has answered or the
// timeout is spent (the operation's own budget, below: 20 s by default,
// 5 s for ping). An address that stayed silent is
// a row that says so, and the exit code is 1 — a table is never short.
// Stateless: a run leaves one request record and the agents' replies on
// the channel, and nothing else anywhere.

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { whoami, FABRIC_ROOT } from '../../communication/gzcoord/scripts/gzmsg.mjs';
import { api, syncedToken, syncedVar, identity as gzIdentity, integrationConfig, inboxRoot, token as gzToken } from '../../communication/gzcoord/scripts/inbox.mjs';
import { execFileSync } from 'node:child_process';
import { ACTION_OPS, ACTION_TTL_MAX_S, signRequest, generateOperatorKey, publicKeyFrom } from './sign.mjs';
import { PIECES, VERSION_RE, UPGRADE_BUDGET_S, FABRIC_UPGRADE_BUDGET_S, pinnedVersion } from './upgrade.mjs';
import zlib from 'node:zlib';
import crypto from 'node:crypto';
import { OPS, PUBLIC_OPS } from './ops.mjs';
import { controlConfig, newId, operatorAddresses, accountAddresses } from './agentd.mjs';
import { checkJobArgs } from './jobs.mjs';

// The commit `upgrade fabric` moves every account to: this checkout's
// origin/main after a fetch, never its HEAD — a coordinator on a branch
// must not ship the branch. A fetch that fails leaves no commit, and
// nothing is sent.
export function originMain(root = FABRIC_ROOT, exec = execFileSync) {
  const git = (...a) => String(exec('git', ['-C', root, ...a], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'], timeout: 60000 })).trim();
  try { git('fetch', '-q', 'origin', 'main'); return git('rev-parse', 'origin/main'); } catch { return null; }
}

export function placements(registry = process.env.AGENT_FABRIC_HOSTS_REGISTRY ?? path.join(FABRIC_ROOT, 'runtime', 'hosts', 'registry.json')) {
  const d = JSON.parse(fs.readFileSync(registry, 'utf8'));
  return Object.entries(d.placement ?? {}).map(([login, host]) => ({ login, host, address: `${host}/${login}` }));
}

const jobArgs = a => ({ title: a.title ?? undefined, ...(a.topic !== null ? { topic: a.topic } : {}), ...(a.project !== null ? { project: a.project } : {}) });

export function parseArgs(argv) {
  const out = { targets: [], op: 'status', json: false, timeout: null, out: null, days: null, piece: null, version: null, force: false, expect: null, restart: false, title: null, topic: null, project: null };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    // A jobs-add title that starts with a dash follows `--`, as for
    // fabric-jobs itself: after it the next word is the title, never an option.
    if (out.op === 'jobs-add' && out.title === null && a === '--') { out.title = argv[++i] ?? null; continue; }
    if (a === '--json') out.json = true;
    else if (a === '--timeout') out.timeout = Number(argv[++i]);
    else if (a.startsWith('--timeout=')) out.timeout = Number(a.slice(10));
    else if (a === '--out') out.out = argv[++i];
    else if (a.startsWith('--out=')) out.out = a.slice(6);
    else if (a === '--days') out.days = Number(argv[++i]);
    else if (a.startsWith('--days=')) out.days = Number(a.slice(7));
    else if (a === '--version') out.version = argv[++i];
    else if (a.startsWith('--version=')) out.version = a.slice(10);
    else if (a === '--force') out.force = true;
    else if (a === '--expect') out.expect = argv[++i];
    else if (a.startsWith('--expect=')) out.expect = a.slice(9);
    else if (a === '--restart') out.restart = true;
    else if (a === '--topic') out.topic = argv[++i];
    else if (a.startsWith('--topic=')) out.topic = a.slice(8);
    else if (a === '--project') out.project = argv[++i];
    else if (a.startsWith('--project=')) out.project = a.slice(10);
    else if (a === '-h' || a === '--help') out.help = true;
    else if (a.startsWith('--')) throw new Error(`unknown option ${a}`);
    else if (a === 'keygen' && !out.targets.length) out.op = 'keygen';
    else if (out.op === 'upgrade' && out.piece === null) out.piece = a;   // the word after `upgrade` is the piece, never a login
    else if (out.op === 'jobs-add' && out.title === null) out.title = a;  // the word after `jobs-add` is the title, never a login
    else if (OPS.includes(a) && out.targets.length) out.op = a;
    else out.targets.push(a);
  }
  if (out.timeout === null) out.timeout = out.op === 'ping' ? 5 : out.op === 'memory' ? 120 : out.op === 'tokens' ? 60 : out.op === 'accounts' ? 300 : out.op === 'upgrade' ? (out.piece === 'fabric' ? FABRIC_UPGRADE_BUDGET_S : UPGRADE_BUDGET_S) : out.op === 'secrets-sync' ? 240 : out.op === 'secrets-migrate' ? 420 : 20;
  if (out.op === 'upgrade' && !PIECES.includes(out.piece)) throw new Error(`upgrade takes a piece: ${PIECES.join(', ')}`);
  if (out.version !== null && (out.op !== 'upgrade' || !VERSION_RE.test(out.version))) throw new Error('--version takes digits.digits.digits, with upgrade only');
  if (out.version !== null && out.piece === 'fabric') throw new Error('upgrade fabric takes no --version: it moves every account to this checkout\'s origin/main');
  if ((out.expect !== null || out.restart) && out.op !== 'secrets-sync') throw new Error('--expect and --restart go with secrets-sync only');
  if (out.expect !== null && !/^[0-9a-f]{12}$/.test(out.expect)) throw new Error('--expect takes a 12-hex setup-token fingerprint (fabric-accounts templates)');
  if (out.days !== null && (out.op !== 'tokens' || !Number.isFinite(out.days) || out.days <= 0)) throw new Error('--days takes a positive number of days, with tokens only');
  if ((out.topic !== null || out.project !== null) && out.op !== 'jobs-add') throw new Error('--topic and --project go with jobs-add only');
  if (out.op === 'jobs-add') {
    const bad = checkJobArgs(jobArgs(out));
    if (bad) throw new Error(`jobs-add: ${bad}`);
    if (out.targets.length !== 1 || out.targets[0] === 'all') throw new Error('jobs-add names one login: a job is one agent\'s, never the fleet\'s');
  }
  if (out.op === 'memory' && !out.out) throw new Error('memory takes --out <dir>: where the drain bundles are written');
  if (!Number.isFinite(out.timeout) || out.timeout <= 0) throw new Error('--timeout takes seconds, a positive number');
  return out;
}

// The drain bundles: <out>/<login>/<working copy>.tar, each reassembled from its
// parts, gunzipped, checked against the sha256 the first reply named, and
// checked to be that login's — the tar's manifest names who harvested it,
// and a reply is only a record on a channel every token holder can write,
// so a bundle whose manifest says another agent is refused as `wrong-agent`
// rather than filed under a name it did not come from. A bundle that does
// not verify is not written, and the row says so. Directories 0700, files
// 0600: a drain is other people's memory.
export function manifestAgent(tar) {
  // The harvester writes manifest.json as the first member: a 512-byte
  // header (name at 0, size in octal at 124), then the bytes.
  if (tar.length < 512 || tar.subarray(0, 100).toString('utf8').replace(/\0.*$/s, '') !== 'manifest.json') return null;
  const size = parseInt(tar.subarray(124, 136).toString('utf8').replace(/\0.*$/s, '').trim(), 8);
  try { return JSON.parse(tar.subarray(512, 512 + size).toString('utf8')).agent ?? null; } catch { return null; }
}
export function partKey(from, p) { return `${from}\u0000${p?.slug}\u0000${p?.part}`; }
export function writeBundles(out, expected, replies, parts) {
  for (const e of expected) {
    const r = replies.find(x => x.from === e.address); if (!r) continue;
    const got = [...(parts[e.address] ?? new Map()).values()];
    for (const b of r.data?.memory?.bundles ?? []) {
      if (b.status !== 'ok') continue;
      const mine = got.filter(p => p.slug === b.slug).sort((x, y) => x.part - y.part);
      if (mine.length !== b.parts || mine.some((p, i) => p.part !== i + 1)) { b.written = null; b.status = 'incomplete'; continue; }
      let tar;
      try { tar = zlib.gunzipSync(Buffer.from(mine.map(p => p.chunk).join(''), 'base64')); } catch { b.status = 'unreadable'; continue; }
      const sha = crypto.createHash('sha256').update(tar).digest('hex');
      if (sha !== b.sha256) { b.status = 'sha-mismatch'; continue; }
      const agent = manifestAgent(tar);
      if (agent !== e.login) { b.status = 'wrong-agent'; b.manifest_agent = agent; continue; }
      // mkdir's mode and writeFile's apply only on creation: a directory or a
      // tar left by an earlier drain keeps its mode unless set again.
      const dir = path.join(out, e.login); fs.mkdirSync(dir, { recursive: true, mode: 0o700 }); fs.chmodSync(dir, 0o700);
      const file = path.join(dir, `${path.basename(b.working_copy)}.tar`); fs.writeFileSync(file, tar, { mode: 0o600 }); fs.chmodSync(file, 0o600); b.written = file;
    }
  }
}

// One row per expected address from the replies collected.
export function rows(expected, replies) {
  const by = new Map(replies.map(r => [r.from, r]));
  return expected.map(e => {
    const r = by.get(e.address);
    if (!r) return { account: e.login, host: e.host, status: 'no answer' };
    const d = r.data ?? {};
    return { account: e.login, host: e.host, status: 'ok', op: r.op, latency_ms: r.latency_ms ?? null,
             email: d.identity?.claude_account?.email ?? (d.identity?.claude_account?.via === 'setup-token' ? `setup-token ${d.identity.claude_account.token_sha256_12}` : null), role: d.identity?.role ?? null,
             five_hour: d.usage?.five_hour ?? null, seven_day: d.usage?.seven_day ?? null, usage_status: d.usage?.status ?? null,
             keys: d.keys ?? null, fabric: d.fabric ?? null, session: d.session ?? null, script: d.script ?? null, recall: d.recall ?? null, tokens: d.tokens ?? null, memory: d.memory ?? null, machine: d.host ?? null, accounts: d.accounts ?? null, upgrade: d.upgrade ?? null, secretsSync: d['secrets-sync'] ?? null, presence: d.presence ?? null, secretsMigrate: d['secrets-migrate'] ?? null, jobs: d.jobs ?? null, jobsAdd: d['jobs-add'] ?? null, agentd: d.agentd ?? null };
  });
}

const pct = w => (w && w.utilization != null) ? `${Number(w.utilization).toFixed(0).padStart(3)}%` : '   -';
const at = w => (w && w.resets_at) ? String(w.resets_at).slice(0, 16) : '-';
// What counts as success for each action; anything else fails the run.
export const ACTION_OK = { upgrade: ['current', 'upgraded'], 'secrets-sync': ['synced'], 'jobs-add': ['added'], 'secrets-migrate': ['migrated', 'current'] };

export function table(op, rs) {
  const lines = [];
  if (op === 'secrets-sync') {
    lines.push(`${'account'.padEnd(22)} ${'status'.padEnd(10)} ${'claude sign-in'.padEnd(34)} ${'session'.padEnd(28)} reason`);
    for (const r of rs) {
      const u = r.secretsSync;
      if (r.status !== 'ok' || !u) { lines.push(`${r.account.padEnd(22)} ${r.status}`); continue; }
      const si = u.claude_sign_in?.via === 'setup-token' ? `setup-token ${u.claude_sign_in.token_sha256_12}` : (u.claude_sign_in?.via ?? '-');
      lines.push(`${r.account.padEnd(22)} ${String(u.status ?? 'no status').padEnd(10)} ${si.padEnd(34)} ${String(u.session ?? '-').padEnd(28)} ${u.reason ?? u.note ?? (u.missing ? `missing in Doppler: ${u.missing.join(', ')}` : '')}`.trimEnd());
    }
    return lines.join('\n');
  }
  if (op === 'secrets-migrate') {
    lines.push(`${'account'.padEnd(22)} ${'status'.padEnd(10)} ${'secrets.env sha256'.padEnd(20)} reason`);
    for (const r of rs) {
      const u = r.secretsMigrate;
      if (r.status !== 'ok' || !u) { lines.push(`${r.account.padEnd(22)} ${r.status}`); continue; }
      lines.push(`${r.account.padEnd(22)} ${String(u.status ?? 'no status').padEnd(10)} ${String(u.sha ?? u.sha_after ?? '-').padEnd(20)} ${u.reason ?? u.note ?? ''}`.trimEnd());
    }
    return lines.join('\n');
  }
  if (op === 'jobs') {
    for (const r of rs) {
      if (r.status !== 'ok' || !r.jobs) { lines.push(`${r.account.padEnd(22)} ${r.status}`); continue; }
      if (r.jobs.status !== 'ok') { lines.push(`${r.account.padEnd(22)} jobs ${r.jobs.status}${r.jobs.error ? `: ${r.jobs.error}` : ''}`); continue; }
      if (!r.jobs.jobs.length) { lines.push(`${r.account.padEnd(22)} no open jobs`); continue; }
      r.jobs.jobs.forEach((j, i) => lines.push(`${(i ? '' : r.account).padEnd(22)} ${j.id.padEnd(5)} ${j.state.padEnd(9)} ${String(j.project ?? '-').padEnd(14)} ${j.title}`
        + `${j.topic ? ` [${j.topic}]` : ''}${j.source !== 'self' ? ` (${j.source})` : ''}${j.blocked_on ? ` — on ${j.blocked_on}` : ''}`));
    }
    return lines.join('\n');
  }
  if (op === 'jobs-add') {
    for (const r of rs) {
      const u = r.jobsAdd;
      lines.push(`${r.account.padEnd(22)} ${r.status !== 'ok' || !u ? r.status : `${u.status}  ${u.job ?? u.reason ?? ''}`}`.trimEnd());
      if (u?.warning) lines.push(`${''.padEnd(22)} ${u.warning}`);
    }
    return lines.join('\n');
  }
  if (op === 'presence') {
    lines.push(`${'account'.padEnd(22)} ${'session'.padEnd(12)} ${'since (UTC)'.padEnd(20)} ${'role'.padEnd(20)} project`);
    for (const r of rs) {
      const p = r.presence;
      if (r.status !== 'ok' || !p) { lines.push(`${r.account.padEnd(22)} ${r.status}`); continue; }
      if (p.status !== 'ok') { lines.push(`${r.account.padEnd(22)} ${'unknown'.padEnd(12)} ${p.error ?? ''}`.trimEnd()); continue; }
      const since = p.since ? p.since.slice(0, 19).replace('T', ' ') : '-';
      lines.push(`${r.account.padEnd(22)} ${(p.online ? `${p.planning ? 'planning' : 'running'}${p.sessions > 1 ? ` ×${p.sessions}` : ''}` : 'none').padEnd(12)} ${since.padEnd(20)} ${String(p.role ?? '-').padEnd(20)} ${p.project ?? '-'}`.trimEnd());
    }
    return lines.join('\n');
  }
  if (op === 'upgrade') {
    lines.push(`${'account'.padEnd(22)} ${'status'.padEnd(10)} ${'from → to'.padEnd(22)} ${'session'.padEnd(26)} reason`);
    for (const r of rs) {
      const u = r.upgrade;
      if (r.status !== 'ok' || !u) { lines.push(`${r.account.padEnd(22)} ${r.status}`); continue; }
      const ft = u.status === 'current' ? (u.piece === 'fabric' ? `${u.to} (main)` : `${u.version} (pinned)`) : `${u.from ?? '-'} → ${u.to ?? '-'}`;
      lines.push(`${r.account.padEnd(22)} ${String(u.status ?? 'no status').padEnd(10)} ${ft.padEnd(22)} ${String(u.session ?? '-').padEnd(26)} ${u.reason ?? u.note ?? ''}`.trimEnd());
    }
    return lines.join('\n');
  }
  if (op === 'accounts') {
    // One row per observed CLAUDE account, not per login: only the
    // observer's daemon has any; the rest answer `none` and are not rows.
    const meter = (a, kind) => { const l = (a.limits ?? []).find(x => x.kind === kind); return l ? `${String(l.percent ?? '-').padStart(3)}% ${String(l.resets_at ?? '-').slice(0, 16)}` : '   -'; };
    lines.push(`${'claude account'.padEnd(34)} ${'status'.padEnd(14)} ${'session / resets'.padEnd(22)} ${'weekly / resets'.padEnd(22)} ${'per-model weekly / resets'.padEnd(34)} ${'read at'.padEnd(17)} observer`);
    let n = 0, answered = 0;
    for (const r of rs) {
      if (r.status !== 'ok') { lines.push(`${'-'.padEnd(34)} ${r.status.padEnd(14)} (${r.account})`); continue; }
      answered++;
      if (!r.accounts || r.accounts.status === 'none') continue;
      if (r.accounts.status !== 'ok') { lines.push(`${'-'.padEnd(34)} ${String(r.accounts.status).padEnd(14)} ${r.accounts.error ?? ''}`.trimEnd() + `  (${r.account})`); n++; continue; }
      for (const a of r.accounts.accounts ?? []) {
        n++;
        const scoped = (a.limits ?? []).find(x => x.kind === 'weekly_scoped');
        const sc = scoped ? `${meter(a, 'weekly_scoped')}${scoped.model ? ` ${scoped.model}` : ''}` : '   -';
        lines.push(`${(a.email ?? a.slug).padEnd(34)} ${String(a.status).padEnd(14)} ${meter(a, 'session').padEnd(22)} ${meter(a, 'weekly_all').padEnd(22)} ${sc.padEnd(34)} ${String(a.read_at ?? '-').slice(0, 16).padEnd(17)} ${r.account}${a.error ? `  ${a.error}` : ''}`);
      }
    }
    // "Nothing observed" is a finding only when a daemon said so; silence is not.
    if (!n && answered) lines.push('no Claude account is observed — bin/fabric-accounts login <account> on the coordinator\'s login (docs/adr/ADR-031-claude-accounts-assigned-applied-and-proved-by-signed-action.md)');
    return lines.join('\n');
  }
  if (op === 'ping') {
    lines.push(`${'account'.padEnd(22)} ${'status'.padEnd(10)} latency`);
    for (const r of rs) lines.push(`${r.account.padEnd(22)} ${r.status.padEnd(10)} ${r.latency_ms != null ? r.latency_ms + ' ms' : ''}`.trimEnd());
    return lines.join('\n');
  }
  if (op === 'memory') {
    lines.push(`${'account'.padEnd(22)} ${'status'.padEnd(10)} bundles`);
    for (const r of rs) {
      if (r.status !== 'ok') { lines.push(`${r.account.padEnd(22)} ${r.status}`); continue; }
      if (r.memory && r.memory.status !== 'ok') { lines.push(`${r.account.padEnd(22)} ${'ok'.padEnd(10)} memory ${r.memory.status}${r.memory.error ? `: ${r.memory.error}` : ''}`); continue; }
      const bs = r.memory?.bundles ?? [];
      if (!bs.length) { lines.push(`${r.account.padEnd(22)} ${'ok'.padEnd(10)} no memory`); continue; }
      for (const b of bs) {
        const rep = b.report ? `${b.report.claims} claim(s), ${b.report.needs_rendering.length} need rendering, ${b.report.skipped_no_roles_class.length} skipped` : 'no report';
        const why = b.status === 'harvest-failed' ? `: ${String(b.error ?? '').trim().split('\n').slice(-2).join(' ')}` : b.status === 'wrong-agent' ? `: manifest names ${b.manifest_agent ?? 'nobody'}` : '';
        lines.push(`${r.account.padEnd(22)} ${'ok'.padEnd(10)} ${(b.working_copy ? path.basename(b.working_copy) : b.slug).padEnd(24)} ${b.files} memories  ${b.status}${why}${b.written ? ` -> ${b.written}` : ''}  ${b.status === 'ok' ? rep : ''}`.trimEnd());
      }
    }
    return lines.join('\n');
  }
  if (op === 'script') {
    const top = s => !s || s.status !== 'ok' ? null : s;
    // The shares are the numeric entries but `letters` and `files`; the section's status, blocks and language ride beside them.
    const fmt = sh => !sh || !sh.letters ? '-' : Object.entries(sh).filter(([k, v]) => typeof v === 'number' && k !== 'letters' && k !== 'files').slice(0, 3).map(([k, v]) => `${k} ${v}%`).join(', ') + ` (${sh.letters} letters)`;
    const bins = b => !b ? '-' : `${b.only} only / ${b.mixed} mixed / ${b.latin} latin`;
    const lang = l => !l ? '' : l.status !== 'ok' ? ' — lang unavailable' : !l.paragraphs ? '' : ' — lang ' + (Object.entries(l.shares).slice(0, 3).map(([k, v]) => `${k} ${v}%`).join(', ') || '-') + (l.unreliable ? ` (${l.unreliable} unreliable)` : '');
    const notes = n => !n || n.status !== 'ok' ? 'none' : `${n.files} file(s): ${bins(n.blocks)}${lang(n.language)} — ${fmt(n)}`;
    // The workers: the locale worker's input (the bridge's leak signal) and its answers, paragraphs by script.
    const workers = w => !w || w.status !== 'ok' ? '-' : `${w.files} file(s): in ${bins(w.input.blocks)}${lang(w.input.language)} / out ${bins(w.text.blocks)}${lang(w.text.language)}`;
    lines.push(`${'account'.padEnd(22)} ${'status'.padEnd(10)} ${'notes (the signature: paragraphs by script)'.padEnd(70)} ${'turns'.padStart(5)}  ${'text, by script'.padEnd(44)} ${'thinking (stored text only)'.padEnd(40)} workers (input / answers)`);
    for (const r of rs) {
      if (r.status !== 'ok') { lines.push(`${r.account.padEnd(22)} ${r.status}`); continue; }
      const s = top(r.script);
      const th = s => !s.thinking_blocks ? '-' : `${bins(s.thinking_blocks)} / ${s.thinking_blocks.empty} unreadable`;
      if (!s) { lines.push(`${r.account.padEnd(22)} ${'ok'.padEnd(10)} ${notes(r.script?.notes).padEnd(70)} ${(r.script?.status ?? '-')}`); continue; }
      lines.push(`${r.account.padEnd(22)} ${'ok'.padEnd(10)} ${notes(s.notes).padEnd(70)} ${String(s.turns).padStart(5)}  ${fmt(s.text).padEnd(44)} ${th(s).padEnd(40)} ${workers(s.workers)}`);
    }
    return lines.join('\n');
  }
  if (op === 'recall') {
    // Is the corpus read? One row per account: sessions in the window,
    // how many opened neither an index nor a slice, the reads by kind,
    // and the slice read most. Paths only, never text.
    lines.push(`${'account'.padEnd(22)} ${'status'.padEnd(10)} ${'sessions'.padStart(8)} ${'no recall'.padStart(9)} ${'turns'.padStart(6)}  ${'index'.padStart(5)} ${'slice'.padStart(5)} ${'search'.padStart(6)} ${'identity'.padStart(8)}  most read`);
    for (const r of rs) {
      if (r.status !== 'ok') { lines.push(`${r.account.padEnd(22)} ${r.status}`); continue; }
      const c = r.recall;
      if (!c || c.status !== 'ok') { lines.push(`${r.account.padEnd(22)} ${'ok'.padEnd(10)} ${(c?.status ?? '-')}`); continue; }
      const most = c.top?.[0] ? `${c.top[0].path} (${c.top[0].reads})` : '-';
      lines.push(`${r.account.padEnd(22)} ${'ok'.padEnd(10)} ${String(c.sessions).padStart(8)} ${String(c.sessions_without_recall).padStart(9)} ${String(c.turns).padStart(6)}  ${String(c.index).padStart(5)} ${String(c.slice).padStart(5)} ${String(c.search).padStart(6)} ${String(c.identity).padStart(8)}  ${most}`);
    }
    return lines.join('\n');
  }
  if (op === 'host') {
    // Every daemon on a host reads the same machine, so the table is BY
    // HOST: the first answered row of each host speaks for it, the others
    // only count. A host none of whose accounts answered is a row too.
    const G = n => n == null ? '-' : `${n}`;
    const byHost = new Map();
    for (const r of rs) (byHost.get(r.host) ?? byHost.set(r.host, []).get(r.host)).push(r);
    lines.push(`${'host'.padEnd(16)} ${'answered'.padEnd(9)} ${'load 1/5/15'.padEnd(17)} ${'cpus'.padStart(4)}  ${'mem avail/total MB'.padEnd(19)} ${'swap free'.padStart(9)}  ${'balloon cur/max MB'.padEnd(19)} disks`);
    for (const [host, group] of [...byHost.entries()].sort((a, b) => a[0].localeCompare(b[0]))) {
      const ok = group.filter(r => r.status === 'ok' && r.machine?.status === 'ok');
      const answered = `${group.filter(r => r.status === 'ok').length}/${group.length}`;
      if (!ok.length) {
        // Every account failed or stayed silent: the failure text, then each account's own line.
        const f = group.find(r => r.status === 'ok')?.machine;
        lines.push(`${host.padEnd(16)} ${answered.padEnd(9)} ${f ? `${f.status}${f.error ? `: ${f.error}` : ''}` : 'no answer'}`);
        for (const r of group) lines.push(`${''.padEnd(16)} ${''.padEnd(9)} ${r.account}: ${r.status === 'ok' ? (r.machine?.status ?? '-') : r.status}`);
        continue;
      }
      // The balloon's static-max is xenstore's, readable by the operator's
      // login and not by an account's: the row that has it speaks for the host.
      const m = (ok.find(r => r.machine.balloon_mb?.static_max != null) ?? ok[0]).machine;
      const load = m.loadavg ? m.loadavg.map(x => x.toFixed(2)).join(' ') : '-';
      const mem = m.mem_mb ? `${G(m.mem_mb.available)}/${G(m.mem_mb.total)}` : '-';
      const swap = m.mem_mb ? G(m.mem_mb.swap_free) : '-';
      const bal = m.balloon_mb ? `${G(m.balloon_mb.current)}/${G(m.balloon_mb.static_max)}` : 'none';
      const disks = (m.disk ?? []).map(d => `${d.mount} ${d.avail_gb}G free (${d.use_pct}%)`).join(', ') || '-';
      lines.push(`${host.padEnd(16)} ${answered.padEnd(9)} ${load.padEnd(17)} ${G(m.cpus).padStart(4)}  ${mem.padEnd(19)} ${swap.padStart(9)}  ${bal.padEnd(19)} ${disks}`);
      const leases = (m.leases ?? []).map(l => `${l.name}${l.label ? ` (${l.label})` : ''}: ${l.holder ?? '?'}${l.pid ? ` pid ${l.pid}` : ''}${l.since ? ` since ${l.since.slice(11, 16)}Z` : ''}`).join('; ') || 'none';
      const top = (m.top_rss ?? []).slice(0, 5).map(p => `${p.comm} ${p.user} ${p.rss_mb} MB`).join(', ') || '-';
      lines.push(`${''.padEnd(16)} ${''.padEnd(9)} leases: ${leases}`);
      lines.push(`${''.padEnd(16)} ${''.padEnd(9)} largest: ${top}`);
      for (const r of group) if (r.status !== 'ok') lines.push(`${''.padEnd(16)} ${''.padEnd(9)} ${r.account}: ${r.status}`);
    }
    return lines.join('\n');
  }
  if (op === 'tokens') {
    // Grouped by Claude account: a login's share is its direct-path
    // equivalents over the account's, from the logins that answered — the
    // meter counts what this host cannot see, so the shares are of the
    // visible spend. The broker column is the login's own key, no share.
    const M = n => n >= 1e9 ? `${(n / 1e9).toFixed(2)}G` : n >= 1e6 ? `${(n / 1e6).toFixed(1)}M` : n >= 1e3 ? `${(n / 1e3).toFixed(0)}k` : String(n);
    const ok = rs.filter(r => r.status === 'ok' && r.tokens?.status === 'ok');
    const days = ok[0]?.tokens?.days ?? '-';
    const byAccount = new Map();
    for (const r of ok) { const k = r.email ?? '(no Claude account)'; (byAccount.get(k) ?? byAccount.set(k, []).get(k)).push(r); }
    lines.push(`${'account'.padEnd(22)} ${'status'.padEnd(10)} ${'claude account'.padEnd(30)} ${'share'.padStart(6)}  ${'claude equiv'.padStart(12)} ${'requests'.padStart(8)} ${'cache read'.padStart(10)} ${'output'.padStart(8)}  ${'broker equiv'.padStart(12)} ${'requests'.padStart(8)}  top model (${days} days)`);
    for (const [email, group] of [...byAccount.entries()].sort((a, b) => a[0].localeCompare(b[0]))) {
      const sum = group.reduce((n, r) => n + r.tokens.claude.equiv, 0);
      for (const r of group.sort((a, b) => b.tokens.claude.equiv - a.tokens.claude.equiv)) {
        const t = r.tokens; const top = Object.entries(t.models)[0];
        const share = sum ? `${(100 * t.claude.equiv / sum).toFixed(0).padStart(5)}%` : '     -';
        lines.push(`${r.account.padEnd(22)} ${'ok'.padEnd(10)} ${email.padEnd(30)} ${share}  ${M(t.claude.equiv).padStart(12)} ${String(t.claude.requests).padStart(8)} ${M(t.claude.cache_read).padStart(10)} ${M(t.claude.output).padStart(8)}  ${M(t.broker.equiv).padStart(12)} ${String(t.broker.requests).padStart(8)}  ${top ? `${top[0]} ${M(top[1].equiv)}` : '-'}`.trimEnd());
      }
      if (group.length > 1) lines.push(`${''.padEnd(22)} ${''.padEnd(10)} ${`= ${email}`.padEnd(30)} ${' 100%'.padStart(6)}  ${M(sum).padStart(12)} ${String(group.reduce((n, r) => n + r.tokens.claude.requests, 0)).padStart(8)}`);
    }
    for (const r of rs) if (!(r.status === 'ok' && r.tokens?.status === 'ok')) lines.push(`${r.account.padEnd(22)} ${r.status !== 'ok' ? r.status : `ok         ${(r.email ?? '-').padEnd(30)} tokens ${r.tokens?.status ?? '-'}`}`);
    return lines.join('\n');
  }
  lines.push(`${'account'.padEnd(22)} ${'status'.padEnd(10)} ${'claude account'.padEnd(30)} ${'5h'.padStart(4)}  ${'5h resets (UTC)'.padEnd(16)} ${'7d'.padStart(4)}  ${'7d resets (UTC)'.padEnd(16)} ${'role'.padEnd(18)} fabric`);
  for (const r of rs) {
    if (r.status !== 'ok') { lines.push(`${r.account.padEnd(22)} ${r.status}`); continue; }
    const fab = r.fabric?.status === 'ok' ? `${r.fabric.head}${r.fabric.behind ? ` (${r.fabric.behind} behind)` : ''}${r.fabric.dirty ? ' dirty' : ''}` : (r.fabric?.status ?? '-');
    const usage = r.usage_status === 'ok' ? `${pct(r.five_hour)}  ${at(r.five_hour).padEnd(16)} ${pct(r.seven_day)}  ${at(r.seven_day).padEnd(16)}` : `${(r.usage_status ?? '-').padEnd(42)}`;
    lines.push(`${r.account.padEnd(22)} ${'ok'.padEnd(10)} ${(r.email ?? '-').padEnd(30)} ${usage} ${(r.role ?? '-').padEnd(18)} ${fab}`);
  }
  return lines.join('\n');
}

export async function main(argv = process.argv.slice(2), { registry, fetchImpl } = {}) {
  let args;
  try { args = parseArgs(argv); } catch (e) { console.error(`fabric-ctl: ${e.message}`); return 2; }
  if (args.help || (!args.targets.length && args.op !== 'keygen')) { console.error('usage: fabric-ctl <login|all> [status|usage|identity|keys|fabric|session|script|recall|host|accounts|ping] [--json] [--timeout S]\n       fabric-ctl <login|all> tokens [--days N]\n       fabric-ctl <login|all> memory --out <dir>\n       fabric-ctl <login|all> upgrade claude [--version V]\n       fabric-ctl <login|all> upgrade fabric   (every account to this checkout\'s origin/main, then bootstrap)\n       fabric-ctl <login|all> secrets-sync [--expect SHA12] [--restart]\n       fabric-ctl <login|all> presence   (any placed account may ask)\n       fabric-ctl <login|all> secrets-migrate\n       fabric-ctl <login|all> jobs\n       fabric-ctl <login> jobs-add [--topic T] [--project P] [--] "<title>"\n       fabric-ctl keygen [--force]'); return args.help ? 0 : 2; }
  if (args.op === 'keygen') return keygen(args, { registry });
  const all = placements(registry);
  let expected;
  if (args.targets.length === 1 && args.targets[0] === 'all') expected = all;
  else {
    expected = [];
    for (const t of args.targets) {
      const p = all.find(x => x.login === t);
      if (!p) { console.error(`fabric-ctl: ${t} is not a placed account (runtime/hosts/registry.json)`); return 2; }
      expected.push(p);
    }
  }
  const who = whoami();
  const me = gzIdentity(who);
  // What the daemons will answer: an operator anything, a placed account a public op (agentd accept()).
  if (!operatorAddresses().has(me.address) && !(PUBLIC_OPS.includes(args.op) && accountAddresses().has(me.address))) { console.error(`fabric-ctl: ${me.address} is not a host operator in runtime/hosts/registry.json — no agent would answer; not sent`); return 2; }
  const cfg = controlConfig();
  const gz = integrationConfig(who.project);
  const tok = gzToken(inboxRoot(who), gz.configured ? gz : undefined) ?? syncedToken();
  if (!tok) { console.error('fabric-ctl: no CLAUDE_BRIDGE_AUTH_TOKEN (fabric-secrets sync)'); return 3; }
  const q = o => new URLSearchParams(o).toString();
  const call = (p, init) => api(tok, p, { relayUrl: cfg.relay_url, ...init });

  const id = newId();
  // An action's signed ttl_s is how long an account may still ACCEPT it,
  // capped; how long this command waits for replies is --timeout, which
  // for a queued fleet upgrade is far longer — the last account replies
  // long after every account accepted.
  let request = { v: 1, kind: 'request', id, from: me.address, to: expected === all ? '*' : expected.map(e => e.address), op: args.op, ts: new Date().toISOString(), ttl_s: Math.min(ACTION_OPS.includes(args.op) ? ACTION_TTL_MAX_S : Infinity, Math.max(cfg.ttl_s, Math.ceil(args.timeout))), ...(args.days ? { days: args.days } : {}),
                  ...(args.op === 'upgrade' ? { args: args.piece === 'fabric' ? { piece: 'fabric', commit: originMain() } : { piece: args.piece, version: args.version ?? pinnedVersion(FABRIC_ROOT) } } : {}),
                  ...(args.op === 'jobs-add' ? { args: jobArgs(args) } : {}),
                  ...(args.op === 'secrets-sync' && (args.expect || args.restart) ? { args: { ...(args.expect ? { expect: args.expect } : {}), ...(args.restart ? { restart: true } : {}) } } : {}) };
  // One command, one version: the coordinator's pin travels in the signed
  // request. Left to each account, an account that had not pulled the pin
  // bump would read its own older pin and answer `current` (review of #34).
  if (args.op === 'upgrade' && args.piece === 'fabric' && !request.args.commit) { console.error(`fabric-ctl: could not read origin/main in ${FABRIC_ROOT} after a fetch; nothing sent`); return 2; }
  if (args.op === 'upgrade' && args.piece !== 'fabric' && !request.args.version) { console.error(`fabric-ctl: no pinned version in ${path.join(FABRIC_ROOT, 'runtime', 'claude-code', 'harness.json')} and no --version; nothing sent`); return 2; }
  if (ACTION_OPS.includes(args.op)) {
    // An action is signed or not sent: an unsigned one is refused by every
    // daemon, and a silent table would read as agents that did not answer.
    const key = process.env.FABRIC_CONTROL_SIGNING_KEY ?? syncedVar('FABRIC_CONTROL_SIGNING_KEY');
    if (!key) { console.error('fabric-ctl: no FABRIC_CONTROL_SIGNING_KEY (fabric-ctl keygen, then fabric-secrets sync) — an action is signed or not sent'); return 3; }
    try { request = signRequest(request, key); } catch (e) { console.error(`fabric-ctl: ${e.message}`); return 3; }
  }
  let sent;
  try { sent = await call('/api/send', { method: 'POST', body: JSON.stringify({ channel: cfg.channel, sender: me.address, content: JSON.stringify(request) }) }); }
  catch (e) { console.error(`fabric-ctl: relay ${e.status ? `refused (HTTP ${e.status})` : `unreachable at ${cfg.relay_url}`}`); return 3; }
  const t0 = Date.now();
  const replies = []; const parts = {};
  const want = new Set(expected.map(e => e.address));   // no reply yet
  // A memory reply is complete only when every part it announced arrived.
  // Distinct parts, keyed by slug and number, the first record for a key
  // winning: a replayed or duplicated part neither completes a reply early
  // nor breaks its reassembly.
  const short = () => args.op === 'memory' ? replies.filter(r => (parts[r.from]?.size ?? 0) < (r.data?.parts ?? 0)).length : 0;
  const deadline = t0 + args.timeout * 1000;
  let since = sent.id;
  while (Date.now() < deadline && (want.size || short())) {
    let page;
    try { page = await call(`/api/messages?${q({ channel: cfg.channel, since_id: since, limit: '500', full: '1' })}`); }
    catch (e) { console.error(`fabric-ctl: relay read failed (${e.message})`); break; }
    if (page.warning === 'since_id_not_found') { console.error('fabric-ctl: the relay no longer holds the request (history cleared); the replies cannot be read'); break; }
    for (const rec of page.messages ?? []) {
      since = rec.id;
      let r; try { r = JSON.parse(rec.content); } catch { continue; }
      if (r?.kind !== 'reply' || r.in_reply_to !== id) continue;
      if (r.data?.part) { const m = (parts[r.from] ??= new Map()); const k = partKey(r.from, r.data.part); if (!m.has(k)) m.set(k, r.data.part); continue; }
      if (want.has(r.from)) { r.latency_ms = Date.now() - t0; replies.push(r); want.delete(r.from); }
    }
    if (want.size || short()) await new Promise(r => setTimeout(r, 500));
  }
  let refused = 0;
  if (args.op === 'memory') {
    writeBundles(args.out, expected, replies, parts);
    for (const r of replies) { if (r.data?.memory && r.data.memory.status !== 'ok') refused += 1; for (const b of r.data?.memory?.bundles ?? []) if (b.status !== 'ok' && b.status !== 'no-working-copy') refused += 1; }
  }
  const rs = rows(expected, replies);
  if (args.json) for (const r of rs) console.log(JSON.stringify(r));
  else console.log(table(args.op, rs));
  // An action that failed on an account is a failed run, whatever else
  // answered: the first fleet upgrade printed nine failed rows and exited 0.
  const actionFailed = ACTION_OPS.includes(args.op) && replies.some(r => !(ACTION_OK[args.op] ?? []).includes(r.data?.[args.op]?.status));
  return want.size || short() || refused || actionFailed ? 1 : 0;
}

// The operator's signing key, made once (or rotated): the private half goes
// from this process into the operator's own Doppler config on stdin — never
// printed, never a file — and the public half into this host's
// `operator_key` in the registry, to commit like any other change. A key
// already registered is kept unless --force: a rotation invalidates every
// daemon's trust until the registry change is pulled.
export function keygen(args, { registry = process.env.AGENT_FABRIC_HOSTS_REGISTRY ?? path.join(FABRIC_ROOT, 'runtime', 'hosts', 'registry.json'), exec = execFileSync, who = whoami() } = {}) {
  const reg = JSON.parse(fs.readFileSync(registry, 'utf8'));
  const host = reg.hosts?.[who.host];
  if (!host || (host.operator ?? 'user') !== who.agent) { console.error(`fabric-ctl: ${who.host}/${who.agent} is not this host's operator in the registry; no key made`); return 2; }
  if (publicKeyFrom(host.operator_key) && !args.force) { console.error('fabric-ctl: this host already has an operator_key; --force to rotate it'); return 2; }
  const cfg = String(exec('doppler', ['configure', 'get', 'enclave.config', '--plain', '--scope', '/'], { encoding: 'utf8' })).trim();
  if (!cfg) { console.error('fabric-ctl: no Doppler config recorded for this login (enclave.config at scope /)'); return 3; }
  const k = generateOperatorKey();
  exec('doppler', ['secrets', 'set', 'FABRIC_CONTROL_SIGNING_KEY', '--project', 'agent-fabric', '--config', cfg, '--silent'], { input: k.privateKeySpec, encoding: 'utf8', stdio: ['pipe', 'ignore', 'inherit'] });
  host.operator_key = k.publicKeySpec;
  fs.writeFileSync(registry, JSON.stringify(reg, null, 2) + '\n');
  console.log(`fabric-ctl: signing key made — private half in Doppler ${cfg} (FABRIC_CONTROL_SIGNING_KEY), public half in ${path.relative(FABRIC_ROOT, registry)} (operator_key of ${who.host}).`);
  console.log('  next: bin/fabric-secrets sync; commit the registry change; the fleet trusts it once it has pulled that commit.');
  return 0;
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) main().then(c => process.exit(c)).catch(e => { console.error(`fabric-ctl: ${e.message}`); process.exit(1); });
