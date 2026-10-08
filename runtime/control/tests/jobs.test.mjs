// The job list on the control plane (agent-fabric ADR-037): `jobs`, an
// operator's read of one account's open jobs, and `jobs-add`, a signed
// action putting the owner's job on one login's list. Both through the
// real tools/fabric/jobs.py, against a scratch state directory.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { scratch } from '../../../tests/scratch.mjs';
import { jobs, jobsAdd, checkJobArgs } from '../jobs.mjs';
import { OPS, PUBLIC_OPS } from '../ops.mjs';
import { ACTION_OPS } from '../sign.mjs';
import { parseArgs, table, ACTION_OK } from '../ctl.mjs';

const ROOT = fileURLToPath(new URL('../../../', import.meta.url));

function account() {
  const home = scratch('jobs-home-');
  const state = scratch('jobs-state-');
  const prev = process.env.AGENT_FABRIC_STATE_DIR;
  process.env.AGENT_FABRIC_STATE_DIR = state;
  return { home, state, done: () => { if (prev === undefined) delete process.env.AGENT_FABRIC_STATE_DIR; else process.env.AGENT_FABRIC_STATE_DIR = prev; } };
}

test('jobs is an operator read, jobs-add a signed action; neither is public', () => {
  assert.ok(OPS.includes('jobs') && OPS.includes('jobs-add'));
  assert.ok(ACTION_OPS.includes('jobs-add') && !ACTION_OPS.includes('jobs'));
  assert.ok(!PUBLIC_OPS.includes('jobs') && !PUBLIC_OPS.includes('jobs-add'));
  assert.deepEqual(ACTION_OK['jobs-add'], ['added']);
});

test('jobs-add takes a closed set of plain arguments', () => {
  assert.equal(checkJobArgs({ title: 'ship it' }), null);
  assert.equal(checkJobArgs({ title: 'ship it', topic: 'drain', project: 'gzapp' }), null);
  assert.match(checkJobArgs({ title: 'x', command: 'rm' }), /only title, topic, project and priority/);
  assert.match(checkJobArgs({ title: '' }), /title is one line/);
  assert.match(checkJobArgs({ title: 'a\nb' }), /title is one line/);
  assert.match(checkJobArgs({ title: 'x'.repeat(301) }), /title is one line/);
  assert.match(checkJobArgs({ title: 'x', project: '../etc' }), /registry id/);
  assert.match(checkJobArgs(undefined), /takes \{ title/);
  assert.equal(checkJobArgs({ title: 'x', priority: 'blocking' }), null);
  assert.match(checkJobArgs({ title: 'x', priority: 'urgent' }), /priority is one of blocking, high, normal, low/);
});

test('jobs-add carries a priority to the list, and jobs reads it; a job without one reads normal', async () => {
  const a = account();
  try {
    const r = await jobsAdd({ from: 'h/op', to: ['h/a'], args: { title: 'first', priority: 'high' } }, { home: a.home, root: ROOT });
    assert.equal(r.status, 'added', JSON.stringify(r));
    assert.match(r.job, /^j1 +queued +high /);
    await jobsAdd({ from: 'h/op', to: ['h/a'], args: { title: 'second' } }, { home: a.home, root: ROOT });
    const got = await jobs({ home: a.home, root: ROOT });
    assert.deepEqual(got.jobs.map(j => j.priority), ['high', 'normal']);
  } finally { a.done(); }
});

test('jobs-add puts the owner\'s job on the list; jobs reads it back without its log', async () => {
  const a = account();
  try {
    const r = await jobsAdd({ from: 'develop-qzapp/user', to: ['develop-qzapp/user'], args: { title: '-a title with a leading dash', topic: 'routing' } }, { home: a.home, root: ROOT });
    assert.equal(r.status, 'added', JSON.stringify(r));
    assert.match(r.job, /^j1 +queued/);
    const got = await jobs({ home: a.home, root: ROOT });
    assert.equal(got.status, 'ok');
    assert.equal(got.jobs.length, 1);
    const [j] = got.jobs;
    assert.deepEqual([j.id, j.state, j.title, j.topic, j.source], ['j1', 'queued', '-a title with a leading dash', 'routing', 'owner']);
    assert.ok(!('log' in j));
    const login = fs.readdirSync(path.join(a.state, 'agents'))[0];
    const doc = JSON.parse(fs.readFileSync(path.join(a.state, 'agents', login, 'jobs.json'), 'utf8'));
    assert.deepEqual(doc.jobs[0].source, { kind: 'owner', from: 'develop-qzapp/user' });
  } finally { a.done(); }
});

test('a refused jobs-add runs nothing and says why', async () => {
  let ran = false;
  const r = await jobsAdd({ from: 'h/op', to: ['h/a'], args: { title: 'x', extra: 1 } }, { exec: async () => { ran = true; return ''; } });
  assert.equal(r.status, 'refused');
  assert.equal(ran, false);
  const failed = await jobsAdd({ from: 'h/op', to: ['h/a'], args: { title: 'x' } }, { exec: async () => { const e = new Error('exit 1'); e.stderr = 'fabric-jobs: identity: jobs.json is not a job list\n'; throw e; } });
  assert.deepEqual(failed, { status: 'refused', reason: 'identity: jobs.json is not a job list' });
});

test('fabric-ctl: jobs-add names one login, and its title is the word after it', () => {
  const a = parseArgs(['backend-dev-01', 'jobs-add', 'fix it', '--topic', 'drain']);
  assert.deepEqual([a.op, a.title, a.topic, a.targets], ['jobs-add', 'fix it', 'drain', ['backend-dev-01']]);
  assert.throws(() => parseArgs(['all', 'jobs-add', 'fix it']), /names one login/);
  assert.throws(() => parseArgs(['backend-dev-01', 'jobs-add']), /title is one line/);
  assert.throws(() => parseArgs(['backend-dev-01', 'status', '--topic', 'x']), /jobs-add only/);
  assert.equal(parseArgs(['backend-dev-01', 'jobs-add', 'fix it', '--priority', 'blocking']).priority, 'blocking');
  assert.throws(() => parseArgs(['backend-dev-01', 'jobs-add', 'fix it', '--priority', 'urgent']), /priority is one of/);
  assert.throws(() => parseArgs(['backend-dev-01', 'status', '--priority', 'high']), /jobs-add only/);
});

test('fabric-ctl: the jobs table, one row per job, the account named once', () => {
  const out = table('jobs', [
    { account: 'backend-dev-01', status: 'ok', jobs: { status: 'ok', jobs: [
      { id: 'j1', state: 'active', project: 'gzapp', title: 'drain', topic: 'memory', source: 'self' },
      { id: 'j2', state: 'blocked', project: 'gzapp', title: 'wait', source: 'owner', blocked_on: 'a review', priority: 'high' }] } },
    { account: 'web-dev-01', status: 'ok', jobs: { status: 'ok', jobs: [] } },
    { account: 'db-admin', status: 'silent' }]);
  const lines = out.split('\n');
  assert.match(lines[0], /^backend-dev-01 +j1 +active +normal +gzapp +drain \[memory\]$/);
  assert.match(lines[1], /^ +j2 +blocked +high +gzapp +wait \(owner\) — on a review$/);
  assert.match(lines[2], /^web-dev-01 +no open jobs$/);
  assert.match(lines[3], /^db-admin +silent$/);
});

test('the jobs tool the ops run exists where they look for it', () => {
  execFileSync('python3', [path.join(ROOT, 'tools', 'fabric', 'jobs.py'), '--help'], { stdio: 'ignore' });
});

// Review of #61: a dash-leading title after `--`; one login, checked by
// the daemon too; C1 controls refused; the no-working-copy warning kept;
// an inbox exit 2 that is not {"addressed": false} is not "not addressed".
test('fabric-ctl: a title that starts with a dash follows --, and options may come first', () => {
  const a = parseArgs(['backend-dev-01', 'jobs-add', '--topic', 'drain', '--', '--not an option']);
  assert.deepEqual([a.title, a.topic], ['--not an option', 'drain']);
  assert.throws(() => parseArgs(['backend-dev-01', 'jobs-add', '--not an option']), /unknown option/);
});

test('the daemon refuses a jobs-add addressed to more than this account', async () => {
  let ran = false;
  const exec = async () => { ran = true; return { stdout: 'added j1 queued', stderr: '' }; };
  for (const to of ['*', ['h/a', 'h/b'], ['*']]) {
    const r = await jobsAdd({ from: 'h/op', to, args: { title: 't' } }, { exec });
    assert.deepEqual(r, { status: 'refused', reason: 'jobs-add names one login, never all' });
  }
  assert.equal(ran, false);
  assert.equal((await jobsAdd({ from: 'h/op', to: ['h/a'], args: { title: 't' } }, { exec })).status, 'added');
});

test('a C1 control character is refused like a C0 one', () => {
  assert.match(checkJobArgs({ title: 'a\u009b31mred' }), /title is one line/);
  assert.match(checkJobArgs({ title: 't', topic: 'x\u0085y' }), /topic is one line/);
});

test('jobs-add carries fabric-jobs\'s warning to the owner, and the table prints it', async () => {
  const exec = async () => ({ stdout: 'added j3    queued    x: t\n', stderr: '  no working copy of x found beside this one: re-add it\n' });
  const r = await jobsAdd({ from: 'h/op', to: ['h/a'], args: { title: 't', project: 'x' } }, { exec });
  assert.equal(r.warning, 'no working copy of x found beside this one: re-add it');
  const out = table('jobs-add', [{ account: 'a', status: 'ok', jobsAdd: r }]);
  assert.match(out, /^a +added +j3/);
  assert.match(out.split('\n')[1], /^ +no working copy of x/);
});
