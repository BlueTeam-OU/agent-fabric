// runtime/control/sessions.mjs — what this account's sessions are doing,
// told to the control channel when it changes (ADR-029 rule 16).
//
// The harness hook runtime/claude-code/hooks/session-state.py keeps
// <state>/session-state.json: per session id, working, blocked or idle,
// since when, and the session's `claude` process with its start time.
// agentd reads it every STATE_POLL_MS and posts a `state` record
// (protocol.mjs) on the state channel (config.json `state_channel`) when
// what it would say differs from what it last said,
// and again every STATE_HEARTBEAT_MS, so a listener that starts late, or
// missed a record while the relay was down, converges without asking.
//
// A session whose process is gone is left out: a kill or a crash never
// sends SessionEnd, and an entry that outlived its process would read as
// a session forever idle. The start time tells a reused pid from the
// session's own. The hook's file is never rewritten here; the hook owns it.
//
// What leaves the account is the session id, its state and since when,
// the binding's role and project, and its last session's id with whether
// its transcript is here (resumable), which Fleet Deck reads before it
// re-enters a tab with `moveto <account> --resume`: no path, no process
// id, nothing a prompt holds. And `waits_on`, present when any: the
// GZCoord message ids this login's blocked jobs wait on (`fabric-jobs
// block <id> --on-request`), so that whoever holds the job a message asked
// for ranks it blocking (ADR-037 rule 8). Message ids only, never a title
// or a job id: peers see presence, not lists (rule 6).

import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { stateDir } from './upgrade.mjs';

export const STATE_FILE = 'session-state.json';
export const STATE_POLL_MS = 2000;
export const STATE_HEARTBEAT_MS = 10 * 60 * 1000;
const STATES = new Set(['working', 'blocked', 'idle']);
// A GZCoord MESSAGE-ID (a UUID, as gzmsg mints it); tools/fabric/jobs.py
// stores waits_on only in this shape. The cap keeps a record a record.
export const MESSAGE_ID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
export const WAITS_ON_MAX = 64;

/** Whether the process the hook recorded is still the session's own. */
export function alive(pid, start, proc = '/proc') {
  // An entry the hook wrote outside a harness names no process: it is
  // kept, since nothing says it is gone.
  if (!Number.isInteger(pid)) return true;
  let raw;
  try { raw = fs.readFileSync(path.join(proc, String(pid), 'stat'), 'utf8'); } catch { return false; }
  const rest = raw.slice(raw.lastIndexOf(')') + 2).split(' ');
  return !Number.isInteger(start) || Number(rest[19]) === start;
}

/** The sessions the file names whose process lives, sorted by id. */
export function readSessions(file, { proc = '/proc' } = {}) {
  let doc;
  try { doc = JSON.parse(fs.readFileSync(file, 'utf8')); } catch { return []; }
  const sessions = doc && typeof doc.sessions === 'object' && !Array.isArray(doc.sessions) ? doc.sessions : {};
  return Object.entries(sessions)
    .filter(([, s]) => s && STATES.has(s.state) && alive(s.pid, s.start, proc))
    .map(([session, s]) => ({ session, state: s.state, since: String(s.since ?? '') }))
    .sort((a, b) => (a.session < b.session ? -1 : a.session > b.session ? 1 : 0));
}

/**
 * The message ids this login's blocked jobs wait on, sorted, from its job
 * list (agents/<login>/jobs.json, written by runtime/identity.py and only
 * read here). No list waits on nothing; a list that cannot be read is
 * null — unknown, which the watcher never says as "nothing".
 * @returns {string[] | null}
 */
export function waitsOn(file) {
  if (!file) return [];
  let doc;
  try { doc = JSON.parse(fs.readFileSync(file, 'utf8')); } catch (e) { return e?.code === 'ENOENT' ? [] : null; }
  if (!doc || !Array.isArray(doc.jobs)) return null;
  const ids = doc.jobs.filter(j => j && j.state === 'blocked' && typeof j.waits_on === 'string' && MESSAGE_ID.test(j.waits_on)).map(j => j.waits_on);
  return [...new Set(ids)].sort().slice(0, WAITS_ON_MAX);
}

/**
 * @returns {import('./protocol.mjs').State}
 */
export function stateRecord(address, { sessions, role, project, last_session, resumable, waits_on }, ts = new Date().toISOString()) {
  return { v: 1, kind: 'state', from: address, ts, sessions, ...(role ? { role } : {}), ...(project ? { project } : {}),
    ...(last_session ? { last_session, resumable: resumable === true } : {}), ...(waits_on?.length ? { waits_on } : {}) };
}

// The harness's session id is a UUID; anything else in a binding is no
// session, never a path. tools/fabric/resume.py's SESSION_RE is the same
// pattern, and ctl.mjs checks a state record's last_session with this one.
export const SESSION_ID = /^[A-Za-z0-9-]{8,64}$/;

// Whether a session's transcript is on this account: the file
// ~/.claude/projects/<launch dir>/<id>.jsonl that fabric-resume would hand
// to --resume. Which directory is not said; only that one exists.
export function transcriptExists(id, configDir = process.env.CLAUDE_CONFIG_DIR || path.join(os.homedir(), '.claude')) {
  if (!SESSION_ID.test(id ?? '')) return false;
  const projects = path.join(configDir, 'projects');
  let dirs;
  try { dirs = fs.readdirSync(projects); } catch { return false; }
  return dirs.some(d => fs.existsSync(path.join(projects, d, `${id}.jsonl`)));
}

function bound(file, configDir) {
  try {
    const b = JSON.parse(fs.readFileSync(file, 'utf8'));
    const id = typeof b.session === 'string' && SESSION_ID.test(b.session) ? b.session : null;
    return { role: b.role ?? null, project: b.project ?? null, last_session: id,
      resumable: id ? transcriptExists(id, configDir) : false };
  } catch { return { role: null, project: null, last_session: null, resumable: false }; }
}

// tick() never throws and never runs twice at once (setInterval does not
// wait for a post). A post that fails leaves the last record unchanged, so
// the next tick tries again; it is said once, not every two seconds — the
// relay loop already reports the relay down.
export function stateWatcher({ address, post, file = path.join(stateDir(), STATE_FILE), binding, jobs = null, proc = '/proc',
  now = Date.now, heartbeatMs = STATE_HEARTBEAT_MS, log = m => console.error(m), configDir }) {
  let lastKey = null, lastAt = 0, busy = false, failing = false, lastWaits = [], unreadable = false;
  // An unreadable list keeps what was last said, and is said once: identity.py
  // replaces the file whole, so this is a broken file, not a torn write.
  const waitsNow = () => {
    const w = waitsOn(jobs);
    if (w === null) { if (!unreadable) log(`agentd: the job list ${jobs} cannot be read; waits_on kept as last said`); unreadable = true; return lastWaits; }
    if (unreadable) { log('agentd: the job list is readable again'); unreadable = false; }
    lastWaits = w;
    return w;
  };
  return {
    async tick() {
      if (busy) return false;
      busy = true;
      try {
        const now_ = now();
        const said = { sessions: readSessions(file, { proc }),
          ...(binding ? bound(binding, configDir) : { role: null, project: null, last_session: null, resumable: false }),
          waits_on: waitsNow() };
        const key = JSON.stringify(said);
        if (key === lastKey && now_ - lastAt < heartbeatMs) return false;
        await post(stateRecord(address, said, new Date(now_).toISOString()));
        lastKey = key; lastAt = now_;
        if (failing) { log('agentd: session state posted again'); failing = false; }
        return true;
      } catch (e) {
        if (!failing) { log(`agentd: session state not posted (${e.message}); retrying`); failing = true; }
        return false;
      } finally { busy = false; }
    },
  };
}
