// runtime/control/tools.mjs — the tools report: what `fabric-tools --all
// --json` says this account has of the tools every project declares
// (projects/registry.json `tools`), kept in <state>/tools.json and read
// back by the `tools` op.
//
// WHY A FILE. The proofs are 15 s each and a session start must not wait
// on a dozen of them, so the control agent runs them in the background
// and the session-start hook (runtime/claude-code/hooks/session-start.py
// tools_line) reads the result. The file IS fabric-tools' --json document,
// byte for byte in meaning: the hook reads `tools` rows and takes the age
// from the file's mtime, so no field is added to it.
//
// A run that fails (the Python pin absent, a registry that does not parse,
// the bound exceeded) leaves the previous report in place: an old answer
// that says how old it is beats none, and a missing tool must not look
// present because a later run could not look. The failure is logged once
// per distinct cause, not every hour.
//
// `tools` is an operator read like `jobs`: not public.

import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { fileURLToPath } from 'node:url';
import { stateDir } from './upgrade.mjs';

const execFileP = promisify(execFile);
const HERE = path.dirname(fileURLToPath(import.meta.url));
export const TOOLS_REPORT = 'tools.json';
export const TOOLS_INTERVAL_MS = 3600 * 1000;
export const BINDING_POLL_MS = 30 * 1000;
// The proofs run one after another at 15 s each at worst, so this holds sixty
// of them; the registry declares sixteen. A registry past that would time every
// run out and keep the first report for ever, with one log line.
export const TOOLS_RUN_TIMEOUT_MS = 15 * 60 * 1000;
const MAX_BUFFER = 4 * 1024 * 1024;

const defaultRoot = () => path.resolve(HERE, '..', '..');
export const reportFile = (dir = stateDir()) => path.join(dir, TOOLS_REPORT);

// fabric-tools exits 1 when a required tool is missing, with the complete
// document on stdout: that is an answer, not a failure. Exit 2 (a bad
// registry), 127 (no pinned Python) and a timeout are failures. A document
// whose `ok` disagrees with the exit status is not trusted either way.
export function parseRun(code, stdout) {
  if (code !== 0 && code !== 1) return { error: `fabric-tools exited ${code}` };
  let doc;
  try { doc = JSON.parse(stdout); } catch { return { error: 'fabric-tools --json printed no JSON document' }; }
  if (!doc || typeof doc !== 'object' || !Array.isArray(doc.projects) || !Array.isArray(doc.tools) || typeof doc.ok !== 'boolean') {
    return { error: 'fabric-tools --json printed a document without projects, tools and ok' };
  }
  if (doc.ok !== (code === 0)) return { error: `fabric-tools exited ${code} but the document says ok: ${doc.ok}` };
  return { doc };
}

export async function runTools({ root = defaultRoot(), exec = execFileP, home = os.homedir(), timeoutMs = TOOLS_RUN_TIMEOUT_MS } = {}) {
  try {
    const r = await exec(path.join(root, 'bin', 'fabric-tools'), ['--all', '--json'], { encoding: 'utf8', timeout: timeoutMs, maxBuffer: MAX_BUFFER, cwd: home });
    return parseRun(0, typeof r === 'string' ? r : r.stdout);
  } catch (e) {
    // execFile ends a run that outlives its timeout with SIGTERM; any other
    // signal (the OOM killer's SIGKILL) is not the bound being too small.
    if (e?.killed && e.signal === 'SIGTERM') return { error: `fabric-tools did not finish within ${timeoutMs / 1000} s` };
    if (e?.signal) return { error: `fabric-tools was killed by ${e.signal}` };
    if (typeof e?.code === 'number') return parseRun(e.code, String(e.stdout ?? ''));
    return { error: `fabric-tools could not run (${e?.code ?? e?.message})` };
  }
}

// tmp beside the target and a rename, so the hook and the op read either
// the old report or the new one, never half of one.
export function writeReport(file, doc) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  const tmp = `${file}.${process.pid}.tmp`;
  try {
    fs.writeFileSync(tmp, JSON.stringify(doc, null, 2) + '\n', { mode: 0o600 });
    fs.renameSync(tmp, file);
  } catch (e) {
    try { fs.unlinkSync(tmp); } catch { /* nothing was written */ }
    throw e;
  }
}

// One run at a time; a failure is said once per distinct cause until a run succeeds.
export function toolsKeeper({ run = () => runTools(), file = reportFile(), log = m => console.error(m) } = {}) {
  let running = null;
  const said = new Set();
  const once = async () => {
    let r;
    try { r = await run(); } catch (e) { r = { error: String(e?.message ?? e) }; }
    if (r.doc) {
      try { writeReport(file, r.doc); said.clear(); return { status: 'written' }; }
      catch (e) { r = { error: `the report could not be written (${e.code ?? e.message})` }; }
    }
    if (!said.has(r.error)) { said.add(r.error); log(`agentd: tools report not refreshed, the previous one stays: ${r.error}`); }
    return { status: 'kept', error: r.error };
  };
  const refresh = () => (running ??= once().finally(() => { running = null; }));
  // A run already in flight began under the binding that has since changed,
  // so its answer is stale on arrival: wait for it, then run once more (the
  // callers waiting meanwhile join that one more run: refresh is single-flight).
  const refreshAgain = () => (running ? running.then(refresh) : refresh());
  return { refresh, refreshAgain };
}

// At start, then every `every` ms, and when the binding file changes. The
// timers are unref'd: the report is never a reason for the daemon to stay up.
export function startToolsReport({ keeper = toolsKeeper(), every = TOOLS_INTERVAL_MS, setTimer = setInterval,
                                   bindingFile = null, watchEvery = BINDING_POLL_MS, stat = f => fs.statSync(f).mtimeMs } = {}) {
  keeper.refresh();
  setTimer(() => keeper.refresh(), every)?.unref?.();
  // `fabric-tools --all` keeps the tools of the account's bound role only, and
  // a rebind (fabric-role bind, then a relaunch) does not restart the daemon:
  // the next session would start on the previous role's report for up to an
  // hour. The binding file's mtime is the signal; an unreadable one is no change.
  if (bindingFile) {
    const mtime = () => { try { return stat(bindingFile); } catch { return null; } };
    let seen = mtime();
    setTimer(() => {
      const now = mtime();
      if (now !== null && now !== seen) { seen = now; keeper.refreshAgain(); }
    }, watchEvery)?.unref?.();
  }
  return keeper;
}

// The `tools` op: the report as the last good run left it, and its age.
export async function tools({ dir = stateDir(), now = Date.now } = {}) {
  const file = reportFile(dir);
  let text, at;
  try { text = fs.readFileSync(file, 'utf8'); at = fs.statSync(file).mtimeMs; }
  catch (e) {
    if (e.code === 'ENOENT') return { status: 'none' };
    return { status: 'failed', error: `${TOOLS_REPORT}: ${e.code ?? e.message}` };
  }
  let doc;
  try { doc = JSON.parse(text); } catch { return { status: 'failed', error: `${TOOLS_REPORT} is not JSON` }; }
  if (!doc || !Array.isArray(doc.tools)) return { status: 'failed', error: `${TOOLS_REPORT} holds no tools list` };
  return { status: 'ok', age_s: Math.max(0, Math.round((now() - at) / 1000)), ok: doc.ok === true, tools: doc.tools };
}

// `tools-install <tool>`, a signed action: the account installs the tool a
// project pins for it (tools/fabric/tools_install.py has the rules: the
// pin, the hash, the proof, the working copy that makes it this account's
// to have). The control agent only runs it and carries the verdict back;
// it decides nothing about which account gets what, so the Doppler CLI
// stays off every account the registry does not name it for.
export const TOOL_NAME = /^[a-z0-9][a-z0-9._-]{0,63}$/;
export const INSTALL_TIMEOUT_MS = 5 * 60 * 1000;
// The operator waits past the account's own bound, so a hung fetch is the account's verdict, not a silence.
export const TOOLS_INSTALL_BUDGET_S = INSTALL_TIMEOUT_MS / 1000 + 30;
const INSTALL_STATUS = { installed: 0, current: 0, skipped: 0, failed: 1, refused: 2 };

// A verdict is fabric-tools' document or nothing: exit 1 and 2 carry one on
// stdout (failed, refused), and a document whose status disagrees with the
// exit status, or names a status it never gives, is not an answer.
export function parseInstall(code, stdout) {
  let doc;
  try { doc = JSON.parse(stdout); } catch { return { status: 'failed', reason: `fabric-tools --install exited ${code} and printed no verdict` }; }
  if (!doc || typeof doc !== 'object' || !Object.hasOwn(INSTALL_STATUS, doc.status) || INSTALL_STATUS[doc.status] !== code) {
    return { status: 'failed', reason: `fabric-tools --install exited ${code} with a verdict that does not agree` };
  }
  const text = v => (typeof v === 'string' ? v.slice(0, 300) : undefined);
  return { status: doc.status, tool: text(doc.tool), version: text(doc.version), path: text(doc.path), reason: text(doc.reason) };
}

export async function toolsInstall(request, { root = defaultRoot(), exec = execFileP, home = os.homedir(), timeoutMs = INSTALL_TIMEOUT_MS } = {}) {
  const a = request?.args;
  const keys = a && typeof a === 'object' && !Array.isArray(a) ? Object.keys(a) : [];
  if (keys.length !== 1 || keys[0] !== 'tool' || typeof a.tool !== 'string' || !TOOL_NAME.test(a.tool)) {
    return { status: 'refused', reason: 'tools-install takes one argument, a tool name' };
  }
  try {
    const r = await exec(path.join(root, 'bin', 'fabric-tools'), ['--install', a.tool, '--json'],
      { encoding: 'utf8', timeout: timeoutMs, maxBuffer: MAX_BUFFER, cwd: home, env: { ...process.env, HOME: home } });
    return parseInstall(0, typeof r === 'string' ? r : r.stdout);
  } catch (e) {
    if (e?.killed && e.signal === 'SIGTERM') return { status: 'failed', reason: `fabric-tools --install did not finish within ${timeoutMs / 1000} s` };
    if (e?.signal) return { status: 'failed', reason: `fabric-tools --install was killed by ${e.signal}` };
    if (typeof e?.code === 'number') return parseInstall(e.code, String(e.stdout ?? ''));
    return { status: 'failed', reason: `fabric-tools could not run (${e?.code ?? e?.message})` };
  }
}
