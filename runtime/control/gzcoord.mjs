// What the control plane needs of GZCoord: who this account is, the
// role catalogue, the project's relay integration, the token, the relay
// API, and whether the account's inbox is held.
//
// Moved here unchanged from communication/gzcoord/scripts/gzmsg.mjs
// (whoami, FABRIC_ROOT, findTaxonomy, loadTaxonomy) and inbox.mjs (api,
// identity, integrationConfig, inboxRoot, token, syncedToken, syncedVar,
// holdStatus), with the private helpers they call, by agent-fabric
// ADR-040 §7 (amendment 2026-10-04): those scripts move to Python and
// their paths become shims, and the daemon must never depend on a script
// that becomes one. From here on there are two implementations of
// identity and of the relay's API — this one, and the Python one the
// GZCoord tools use — and each keeps its own tests
// (runtime/control/tests/gzcoord.test.mjs is this one's). A change to
// what either answers is made in both.
//
// The lines integrationConfig() and holdStatus() print come from the same
// default dictionary the GZCoord tools read
// (communication/gzcoord/i18n/en-US.json), read here directly rather than
// through the tools' own reader (tools/fabric/gzcoord/i18n.py, Python since
// ADR-040 Wave 7). The daemon prints none of them
// to a person: it reads `configured` and `held`.
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { execFileSync, spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { engineRoot, roleCatalog, projectIntegration } from './roots.mjs';

// The agent-fabric checkout this runtime belongs to (roots.mjs: AGENT_FABRIC_ROOT, set but
// empty is set, else the code's own location).
export const FABRIC_ROOT = engineRoot({ emptyIsSet: true });

// The default dictionary, read once, lazily, and never throwing: an
// unreadable one degrades to key-named lines, said once on stderr, which
// is loud and alive. Beside the code, not under FABRIC_ROOT: a test that
// points AGENT_FABRIC_ROOT at a fixture names where the roles live, never
// where the dictionary ships.
const DEFAULT_PATH = fileURLToPath(new URL('../../communication/gzcoord/i18n/en-US.json', import.meta.url));
function defaultDictionaryOrEmpty(file = DEFAULT_PATH) {
  try {
    const d = JSON.parse(fs.readFileSync(file, 'utf8'));
    if (!d || typeof d !== 'object' || Array.isArray(d)) throw new TypeError('not an object of lines');
    return d;
  } catch (e) {
    console.error(`gzcoord: ${file} could not be read (${e.message}); every line will print as its own key`);
    return {};
  }
}
// `{name}` from `vars`; a placeholder the caller did not supply is left
// standing, and an unknown key prints as itself.
const fill = (template, vars = {}) => template.replace(/\{([a-z_]+)\}/g, (m, k) => (k in vars ? String(vars[k]) : m));
const printer = dict => (key, vars) => (key in dict ? fill(dict[key], vars) : key);
let EN;
const en = () => (EN ??= printer(defaultDictionaryOrEmpty()));

// WHO AM I. The agent is the Linux login of the effective user, and the
// one place that derivation lives is runtime/identity.py — this asks it
// (`--json` also carries the role, project and working copy bound to the
// agent). If python is unavailable the fallback computes the same thing
// (effective uid -> login) and reads the same binding file by the same
// path rule; it never looks at the working directory's name.
function bindingFile(agent) {
  const base = process.env.AGENT_FABRIC_STATE_DIR
    ?? path.join(process.env.XDG_STATE_HOME ?? path.join(os.homedir(), '.local', 'state'), 'agent-fabric');
  return path.join(base, 'agents', agent, 'binding.json');
}
export const WHOAMI_TIMEOUT_MS = 15000;
export function whoami() {
  const script = path.join(FABRIC_ROOT, 'runtime', 'identity.py');
  // Bounded like every relay call: a hung identity.py takes the fallback
  // below, which says it is one (fallback: true), rather than holding the caller.
  const r = spawnSync('python3', [script, '--json'], { encoding: 'utf8', timeout: WHOAMI_TIMEOUT_MS });
  if (r.status === 0) { try { const me = JSON.parse(r.stdout); me.binding = bindingFile(me.agent); return me; } catch { /* fall through */ } }
  const agent = os.userInfo().username;
  let binding = {};
  try { binding = JSON.parse(fs.readFileSync(bindingFile(agent), 'utf8')); } catch { /* none written */ }
  return { agent, host: os.hostname().split('.')[0], role: binding.role, project: binding.project,
           working_copy: binding.working_copy, binding: bindingFile(agent), fallback: true };
}

// The deployment's role catalogue, identities/roles/catalog.json.
// The parameter is `file`, not `path`: `path` is the node:path module
// here, and shadowing it turns a later path.join() in this function into
// a runtime error rather than a compile one.
export function loadTaxonomy(file) {
  const t = JSON.parse(fs.readFileSync(file, 'utf8'));
  const roles = new Map();   // slug (the catalogue id, what goes on the wire) → title (for reading)
  for (const r of t.roles ?? []) if (r.id && r.title) roles.set(r.id, r.title);
  if (roles.size === 0) throw new Error(`${file} holds no roles with id and title`);
  return { path: file, roles };
}
// The AGENT's active-role record: the runtime binding written by
// tools/fabric/role.py in the agent's state directory (never inside a
// working copy). Four outcomes, kept distinct because a record that fails
// to name a usable role must never pass as "no record" and fall through to
// a guess from the address: no binding at all, or one with no role; a
// binding naming a catalogue role; a binding present but unreadable, which
// warns and leaves the caller to decide; and a binding naming a role the
// catalogue does not have, which is an error, since the agent asserts a
// role the deployment does not know.
function recordedRole(taxonomy, me = whoami()) {
  if (!taxonomy?.path) return { role: undefined };
  const file = me.binding ?? bindingFile(me.agent);
  if (me.role === undefined || me.role === null) {
    if (!fs.existsSync(file)) return { role: undefined };
    try { JSON.parse(fs.readFileSync(file, 'utf8')); }
    catch (e) { return { role: undefined, warning: `${file} could not be read (${e.message})` }; }
    return { role: undefined, warning: `${file} records no role` };
  }
  if (!taxonomy.roles.has(me.role)) return { role: undefined, error: `${file} records role "${me.role}", which is not in ${taxonomy.path}; the login's role is used instead` };
  return { role: me.role, file };
}
export function findTaxonomy(_from = process.cwd()) {
  const fabric = roleCatalog({ engine: FABRIC_ROOT });
  return fs.existsSync(fabric) ? fabric : undefined;
}
// The slug an instance name carries, as a whole run of hyphen-separated
// tokens: provisioned accounts are named for the role they were stood up
// as (`architect-cto-01`) while a generic account (`user`) names none. A
// convenience for identity() when no binding records a role — never a
// source of identity.
function slugOf(instance, taxonomy) {
  const tokens = instance.split('-');
  let best;
  for (const slug of taxonomy.roles.keys()) {
    const st = slug.split('-');
    for (let i = 0; i + st.length <= tokens.length; i++)
      if (st.every((s, j) => tokens[i + j] === s) && (!best || slug.length > best.length)) best = slug;
  }
  return best;
}

// Project integration: which relay, which channel, where the token and
// the hosted relay's runtime live. It comes from the PROJECT —
// projects/<id>/integration/gzcoord/config.json — or from the environment
// (CLAUDE_BRIDGE_URL and GZCOORD_CHANNEL together). Nothing else: a
// project with neither is NOT configured. Until 2026-09-16 the defaults
// were one project's, so a working copy of any other project silently
// joined that project's channel with its token file.
// relay_runtime_dir is relative to the WORKSPACE — the projects/
// directory the fabric checkout sits in — because the relay's database,
// token and venv are host state, not project state.
const WORKSPACE = path.dirname(FABRIC_ROOT);
function relayRuntimeDir(cfg, workspace = WORKSPACE) {
  return path.resolve(workspace, cfg.relay_runtime_dir ?? '.gzcoord');
}
export function integrationConfig(project, env = process.env, t = en()) {
  const file = project ? projectIntegration(project, ['gzcoord', 'config.json'], { engine: FABRIC_ROOT }) : null;
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
// Default for a caller that passes no relayUrl to api().
const RELAY = process.env.CLAUDE_BRIDGE_URL ?? 'http://127.0.0.1:8765';

function gitToplevel() {
  try { return execFileSync('git', ['rev-parse', '--show-toplevel'], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] }).trim(); }
  catch { return null; }
}
// The working copy the token is read from. Inside a checkout that is the
// checkout. Outside one — a session started in the workspace (projects/)
// — the binding's own working_copy is the root; the cwd is only the last
// resort.
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

// Who this account is on the channel: the instance half of the address
// is the AGENT — the Linux login, from whoami() — never the working
// copy's basename; the host is the short hostname; the role comes from
// the agent's runtime binding, else from a slug the login happens to
// carry.
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

// A relay that accepts the connection and never answers would otherwise
// hold the caller for good: a CLI never returns, and agentd's loop stops
// reading requests. The bound covers the body too, and adds whatever the
// request itself asks the relay to wait (/api/wait's timeout_seconds), so
// a long poll is never cut short; a caller's own signal replaces it.
export const API_TIMEOUT_MS = 30000;
export function apiTimeoutMs(pathAndQuery) {
  const waits = Number(new URLSearchParams(pathAndQuery.split('?')[1] ?? '').get('timeout_seconds'));
  return API_TIMEOUT_MS + (Number.isFinite(waits) && waits > 0 ? waits * 1000 : 0);
}

export async function api(tok, pathAndQuery, { relayUrl = RELAY, timeoutMs = apiTimeoutMs(pathAndQuery), ...init } = {}) {
  try {
    const r = await fetch(`${relayUrl}${pathAndQuery}`, {
      ...init,
      signal: init.signal ?? AbortSignal.timeout(timeoutMs),
      headers: { Authorization: `Bearer ${tok}`, 'Content-Type': 'application/json', ...(init.headers ?? {}) },
    });
    if (!r.ok) { const e = new Error(`${pathAndQuery} -> HTTP ${r.status}`); e.status = r.status; throw e; }
    return await r.json();
  } catch (e) {
    if (e?.name !== 'TimeoutError') throw e;
    // No status and no connection code: a post that timed out may have
    // been stored, and queue.mjs's unsent() reads it as unknown.
    const t = new Error(`${pathAndQuery} -> no answer within ${timeoutMs / 1000} s`); t.timedOut = true; throw t;
  }
}

// One `export NAME=value` line of the synced secrets file, unquoted, or
// undefined — read fresh, because the environment is a snapshot of it
// taken when the shell started. The value is a secret: a caller prints it
// nowhere and uses it in place (a header, a hash). sync writes the value
// with shlex.quote and the Python readers take it back with shlex.split
// (tools/fabric/relay.py own_token), so this reads the first word as
// they do: a value holding ' is written 'a'"'"'b', which stripping the
// outer quotes once read as a'"'"'b.
export function syncedVar(name, home = os.homedir()) {
  try {
    const prefix = `export ${name}=`;
    for (const line of fs.readFileSync(path.join(home, '.config', 'agent-fabric', 'secrets.env'), 'utf8').split('\n')) {
      if (!line.startsWith(prefix)) continue;
      return shellWord(line.slice(prefix.length)) || undefined;
    }
  } catch { /* not enrolled, or no sync yet */ }
  return undefined;
}

// The first word of a line as Python's shlex.split reads it (POSIX mode,
// no comments): '…' literal; "…" where a backslash escapes only " and \;
// outside quotes a backslash escapes any character. An unterminated quote
// or escape is shlex's ValueError: null, never a guess at the value.
export function shellWord(text) {
  let word = null, i = 0;
  while (i < text.length && /[ \t\r\n]/.test(text[i])) i++;
  while (i < text.length) {
    const c = text[i];
    if (/[ \t\r\n]/.test(c)) break;
    word ??= '';
    if (c === "'") {
      const end = text.indexOf("'", i + 1);
      if (end < 0) return null;
      word += text.slice(i + 1, end); i = end + 1;
    } else if (c === '"') {
      i++;
      for (;;) {
        if (i >= text.length) return null;
        const d = text[i];
        if (d === '"') { i++; break; }
        if (d === '\\' && i + 1 < text.length && (text[i + 1] === '"' || text[i + 1] === '\\')) { word += text[i + 1]; i += 2; continue; }
        if (d === '\\' && i + 1 >= text.length) return null;
        word += d; i++;
      }
    } else if (c === '\\') {
      if (i + 1 >= text.length) return null;
      word += text[i + 1]; i += 2;
    } else { word += c; i++; }
  }
  return word;
}

export function syncedToken(home = os.homedir()) {
  return syncedVar('CLAUDE_BRIDGE_AUTH_TOKEN', home);
}

// THE HOLD: while a session of this login plans, its inbox watch polls
// nothing (runtime/claude-code/hooks/plan-hold.sh writes the markers).
// The account is held while ANY marker names a live harness of this
// login: the pid answers a signal as this uid (EPERM is another login's
// process, never our harness) and, when both sides know it, has the
// start time the marker recorded (a reused pid is not the harness). The
// directory and each file must be this login's, or nothing there is a
// hold — another login must not be able to hold or release this inbox.
function holdDir(home = os.homedir()) {
  return process.env.AGENT_FABRIC_HOLD_DIR ?? path.join(home, '.cache', 'agent-fabric', 'hold');
}
function pidStart(pid) {
  try { return fs.readFileSync(`/proc/${pid}/stat`, 'utf8').replace(/.*\) /s, '').split(' ')[19] ?? ''; } catch { return ''; }
}
function pidAlive(pid) {
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
