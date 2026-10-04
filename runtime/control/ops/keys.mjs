// runtime/control/ops/keys.mjs — which keys the account holds, whether its stores took only verified commits, and whether it can sign.
// A part of ops.mjs, which re-exports it; ops.mjs's header is the contract
// every extractor here keeps.

import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import crypto from 'node:crypto';
import { syncedVar } from '../gzcoord.mjs';
import { execFileP } from './util.mjs';

export const KEY_NAMES = ['OPENROUTER_API_KEY', 'OPENAI_API_KEY', 'GH_TOKEN', 'CLAUDE_BRIDGE_AUTH_TOKEN', 'SERPAPI_API_KEY', 'BRAVE_SEARCH_API_KEY', 'CLAUDE_CODE_OAUTH_TOKEN'];


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


// kept: where a child's mirror's refusal is kept once a refused rebuild
// removed the mirror — beside it, `<id>.refusal.json` (secret_store.py).
function readRefusal(store, kept = null) {
  let r;
  try { r = JSON.parse(fs.readFileSync(path.join(store, '.git', REFUSAL_FILE), 'utf8')); }
  catch (e) {
    if (e?.code !== 'ENOENT') return { unreadable: true };
    if (!kept) return null;
    try { r = JSON.parse(fs.readFileSync(kept, 'utf8')); }
    catch (e2) { return e2?.code === 'ENOENT' ? null : { unreadable: true }; }
  }
  return { refused: { commit: String(r?.commit ?? '?').slice(0, 12), at: r?.at ?? null, reason: String(r?.reason ?? '?').slice(0, 300) } };
}


// The trusted base is agent-fabric.trustedbase in the store's own
// .git/config, which secret_store.py writes through `git config`: read as a
// file, so the keys probe runs no git. true, false, or null (unreadable).
// As the verifier reads it (secret_store.trusted_base): the key's name in
// any case, its last value, and that value 40 lowercase hex — an uppercase
// one, or a good line before a bad one, read "verified" here while every
// verified operation refused the store.
function hasBase(store) {
  let text;
  try { text = fs.readFileSync(path.join(store, '.git', 'config'), 'utf8'); } catch { return null; }
  let inSection = false;
  let base = false;
  for (const line of text.split('\n')) {
    const head = /^\s*\[([^\]]*)\]/.exec(line);
    if (head) { inSection = head[1].trim().toLowerCase() === 'agent-fabric'; continue; }
    const kv = /^\s*trustedbase\s*=\s*(.*?)\s*$/i.exec(line);
    if (inSection && kv) base = /^[0-9a-f]{40}$/.test(kv[1]);
  }
  return base;
}


export function storeRefusal(home = os.homedir(), store = process.env.AGENT_FABRIC_SECRET_STORE ?? path.join(home, '.local', 'share', 'agent-fabric', 'secrets'),
                             children = path.join(home, '.local', 'share', 'agent-fabric', 'children')) {
  let kids = [];
  let gone = [];
  try {
    const names = fs.readdirSync(children);
    kids = names.filter(n => AGENT_ID_RE.test(n));
    gone = names.filter(n => n.endsWith('.refusal.json')).map(n => n.slice(0, -'.refusal.json'.length))
      .filter(aid => AGENT_ID_RE.test(aid) && !kids.includes(aid));
  } catch { /* no mirrors */ }
  const mirrors = [];
  // A mirror with no base refuses every verified operation on it, so it is
  // as unclean as a refusal (review of #94): said, as the own store's is. A
  // mirror a refused rebuild removed is said by its kept refusal alone: no
  // base to read where there is no mirror (review of #96).
  for (const aid of [...kids, ...gone].sort()) {
    const mirror = path.join(children, aid);
    const r = readRefusal(mirror, path.join(children, `${aid}.refusal.json`));
    const base = gone.includes(aid) ? true : hasBase(mirror);
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
