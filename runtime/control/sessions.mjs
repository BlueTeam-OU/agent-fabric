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
// id, nothing a prompt holds.

import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { stateDir } from './upgrade.mjs';

export const STATE_FILE = 'session-state.json';
export const STATE_POLL_MS = 2000;
export const STATE_HEARTBEAT_MS = 10 * 60 * 1000;
const STATES = new Set(['working', 'blocked', 'idle']);

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
 * @returns {import('./protocol.mjs').State}
 */
export function stateRecord(address, { sessions, role, project, last_session, resumable }, ts = new Date().toISOString()) {
  return { v: 1, kind: 'state', from: address, ts, sessions, ...(role ? { role } : {}), ...(project ? { project } : {}),
    ...(last_session ? { last_session, resumable: resumable === true } : {}) };
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
export function stateWatcher({ address, post, file = path.join(stateDir(), STATE_FILE), binding, proc = '/proc',
  now = Date.now, heartbeatMs = STATE_HEARTBEAT_MS, log = m => console.error(m), configDir }) {
  let lastKey = null, lastAt = 0, busy = false, failing = false;
  return {
    async tick() {
      if (busy) return false;
      busy = true;
      try {
        const now_ = now();
        const said = { sessions: readSessions(file, { proc }),
          ...(binding ? bound(binding, configDir) : { role: null, project: null, last_session: null, resumable: false }) };
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
