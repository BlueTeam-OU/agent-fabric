// runtime/control/jobs.mjs — the job list on the control plane
// (agent-fabric ADR-037 rule 6, ADR-029).
//
// `jobs` is a read op: this account's open jobs, as bin/fabric-jobs holds
// them, for an operator. Not public: peers see each other's presence, not
// each other's lists. `jobs-add` is an ACTION (sign.mjs ACTION_OPS): the
// owner's job, added to this login's list with source `owner` and the
// operator's address. Both run tools/fabric/jobs.py as this login, by
// argv — no field of a request reaches a shell — with the root it was
// given, so the tool and the identity it loads are one tree's; the arguments of
// jobs-add are a closed set, checked before anything runs.

import os from 'node:os';
import path from 'node:path';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';

const execFileP = promisify(execFile);
const JOBS_TIMEOUT_MS = 15000;
export const PROJECT_SLUG = /^[a-z0-9][a-z0-9-]{0,62}$/;
export const TITLE_MAX = 300;
export const TOPIC_MAX = 60;
// ADR-037 rule 7; tools/fabric/jobs.py PRIORITIES is the same list.
export const PRIORITIES = ['blocking', 'high', 'normal', 'low'];

const jobsPy = root => path.join(root, 'tools', 'fabric', 'jobs.py');
const defaultRoot = home => process.env.AGENT_FABRIC_ROOT ?? path.join(home, 'projects', 'agent-fabric');
// A control character in a title would reach the list, the prompt of a
// fresh session and every operator's terminal: C0, DEL and C1 (U+009B is
// a terminal's CSI as surely as ESC [ is).
const plain = s => typeof s === 'string' && !/[\u0000-\u001f\u007f-\u009f]/.test(s);

export async function jobs({ home = os.homedir(), root = defaultRoot(home), exec = execFileP } = {}) {
  const r = await exec('python3', [jobsPy(root), 'list', '--json'], { encoding: 'utf8', timeout: JOBS_TIMEOUT_MS, env: { ...process.env, AGENT_FABRIC_ROOT: root } });
  const list = JSON.parse(typeof r === 'string' ? r : r.stdout);
  // The log stays on the account: the owner reads where each job is, not its history.
  return { status: 'ok', jobs: list.map(j => ({ id: j.id, state: j.state, title: j.title, project: j.project ?? null, topic: j.topic ?? null, priority: j.priority ?? 'normal',
                                                 source: j.source?.kind ?? 'self', blocked_on: j.blocked_on ?? null, artifacts: j.artifacts ?? [], updated: j.updated ?? null })) };
}

export function checkJobArgs(args) {
  if (!args || typeof args !== 'object' || Array.isArray(args)) return 'jobs-add takes { title, topic, project, priority }';
  const extra = Object.keys(args).filter(k => !['title', 'topic', 'project', 'priority'].includes(k));
  if (extra.length) return `jobs-add takes only title, topic, project and priority, not ${extra.join(', ')}`;
  if (!plain(args.title) || !args.title.trim() || args.title.length > TITLE_MAX) return `title is one line of 1 to ${TITLE_MAX} characters`;
  if (args.topic !== undefined && (!plain(args.topic) || !args.topic.trim() || args.topic.length > TOPIC_MAX)) return `topic is one line of 1 to ${TOPIC_MAX} characters`;
  if (args.project !== undefined && !PROJECT_SLUG.test(String(args.project))) return 'project is a registry id (lowercase, digits, dashes)';
  if (args.priority !== undefined && !PRIORITIES.includes(args.priority)) return `priority is one of ${PRIORITIES.join(', ')}`;
  return null;
}

export async function jobsAdd(request, { home = os.homedir(), root = defaultRoot(home), exec = execFileP } = {}) {
  // One login's, never the fleet's: fabric-ctl refuses `all`, and a signed
  // request that names more than this account is refused here too.
  const to = Array.isArray(request.to) ? request.to : [request.to];
  if (to.length !== 1 || to[0] === '*') return { status: 'refused', reason: 'jobs-add names one login, never all' };
  const bad = checkJobArgs(request.args);
  if (bad) return { status: 'refused', reason: bad };
  const { title, topic, project, priority } = request.args;
  // `--` before the title: a title that begins with a dash is a title.
  const argv = [jobsPy(root), 'add', '--owner', String(request.from), ...(topic ? ['--topic', topic] : []), ...(project ? ['--project', project] : []), ...(priority ? ['--priority', priority] : []), '--', title];
  try {
    const r = await exec('python3', argv, { encoding: 'utf8', timeout: JOBS_TIMEOUT_MS, cwd: home, env: { ...process.env, AGENT_FABRIC_ROOT: root } });
    const out = String(typeof r === 'string' ? r : r.stdout).trim();
    // What fabric-jobs says on stderr of a job it added (no working copy
    // of the project found) is the owner's to read, not dropped.
    const warning = String(typeof r === 'string' ? '' : r.stderr ?? '').trim().replace(/\s+/g, ' ');
    return { status: 'added', job: out.replace(/^added\s+/, ''), ...(warning ? { warning: warning.slice(0, 300) } : {}) };
  } catch (e) {
    const why = String(e?.stderr ?? e?.message ?? e).trim().split('\n').pop().replace(/^fabric-jobs:\s*/, '');
    return { status: 'refused', reason: why.slice(0, 200) };
  }
}
