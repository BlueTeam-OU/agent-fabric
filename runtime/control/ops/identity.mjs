// runtime/control/ops/identity.mjs — who the account is, the session it runs and whether one is present, and the fabric checkout it runs on.
// A part of ops.mjs, which re-exports it; ops.mjs's header is the contract
// every extractor here keeps.

import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { whoami, findTaxonomy, loadTaxonomy, syncedVar, holdStatus, identity as gzIdentity } from '../gzcoord.mjs';
import { readJson, sha12, execFileP } from './util.mjs';


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


// The fabric checkout the account runs on: head, branch, how far behind
// origin/main, and whether the tree is clean. A fetch that cannot reach
// origin is said, not hidden. Asynchronous so the daemon's event loop
// stays live through the fetch's 10 s budget (the source watch, signals,
// the usage read of the same request); the read loop itself still
// answers one record at a time (exec may return a string or a {stdout};
// a test passes a synchronous fake).
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
