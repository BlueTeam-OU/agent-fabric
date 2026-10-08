// The tools report on the control plane: the control agent runs
// `fabric-tools --all --json` at start and every hour and keeps the last
// good result in <state>/tools.json; the `tools` op returns it with its
// age; fabric-ctl names each account's missing required tools.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { scratch } from '../../../tests/scratch.mjs';
import { parseRun, runTools, writeReport, toolsKeeper, startToolsReport, tools, reportFile, TOOLS_INTERVAL_MS } from '../tools.mjs';
import { collect, OPS, PUBLIC_OPS } from '../ops.mjs';
import { ACTION_OPS } from '../sign.mjs';
import { table, rows, parseArgs } from '../ctl.mjs';

const DOC = { projects: ['gzapp'], ok: false, tools: [
  { project: 'gzapp', name: 'pnpm', status: 'missing', found: 'pnpm not found', version: '11.6.0', where: 'account', optional: false, why: 'x' },
  { project: 'gzapp', name: 'doppler', status: 'missing', found: '', version: '', where: 'account', optional: true, why: 'x' },
  { project: 'gzapp', name: 'git', status: 'ok', found: 'git 2', version: '', where: 'host', optional: false, why: 'x' }] };

// A root with a bin/fabric-tools of its own: the keeper runs a real
// executable by argv, as in production, and what it prints is the fixture.
function fakeRoot(script) {
  const root = scratch('tools-root-');
  fs.mkdirSync(path.join(root, 'bin'));
  fs.writeFileSync(path.join(root, 'bin', 'fabric-tools'), `#!/usr/bin/env bash\n${script}\n`, { mode: 0o755 });
  return root;
}
const quiet = () => { const said = []; return { said, log: m => said.push(m) }; };

test('tools is an operator read: neither an action nor public', () => {
  assert.ok(OPS.includes('tools'));
  assert.ok(!ACTION_OPS.includes('tools') && !PUBLIC_OPS.includes('tools'));
});

test('parseRun: exit 1 with a document that says not ok is an answer; every other disagreement is a failure', () => {
  assert.deepEqual(parseRun(1, JSON.stringify(DOC)).doc, DOC);
  assert.deepEqual(parseRun(0, JSON.stringify({ ...DOC, ok: true })).doc, { ...DOC, ok: true });
  assert.match(parseRun(0, JSON.stringify(DOC)).error, /exited 0 but the document says ok: false/);
  assert.match(parseRun(1, JSON.stringify({ ...DOC, ok: true })).error, /exited 1 but/);
  assert.match(parseRun(2, JSON.stringify(DOC)).error, /exited 2/);
  assert.match(parseRun(127, '').error, /exited 127/);
  assert.match(parseRun(0, 'not json').error, /no JSON document/);
  assert.match(parseRun(0, JSON.stringify({ ok: true })).error, /without projects, tools and ok/);
});

test('runTools: runs the account\'s bin/fabric-tools by argv; exit 1 is an answer, exit 2, a timeout and no command are failures', async () => {
  const argvFile = path.join(scratch('tools-argv-'), 'argv');
  const root = fakeRoot(`printf '%s\\n' "$@" > '${argvFile}'\ncat <<'J'\n${JSON.stringify(DOC)}\nJ\nexit 1`);
  const got = await runTools({ root, home: scratch('tools-home-') });
  assert.deepEqual(got.doc, DOC);
  assert.deepEqual(fs.readFileSync(argvFile, 'utf8').split('\n').filter(Boolean), ['--all', '--json']);
  assert.match((await runTools({ root: fakeRoot('echo "bad registry" >&2; exit 2') })).error, /exited 2/);
  assert.match((await runTools({ root: fakeRoot('sleep 30'), timeoutMs: 200 })).error, /did not finish within 0.2 s/);
  assert.match((await runTools({ root: scratch('tools-empty-') })).error, /could not run \(ENOENT\)/);
});

test('the keeper writes the report atomically and leaves no temporary file', async () => {
  const dir = scratch('tools-state-'), file = path.join(dir, 'agents', 'a', 'tools.json');
  const k = toolsKeeper({ run: async () => ({ doc: DOC }), file, ...quiet() });
  assert.deepEqual(await k.refresh(), { status: 'written' });
  assert.deepEqual(JSON.parse(fs.readFileSync(file, 'utf8')), DOC);
  assert.deepEqual(fs.readdirSync(path.dirname(file)), ['tools.json']);
  // A reader that already has the old report open sees it whole: the new
  // one replaced the file, it was not written over it.
  const old = fs.openSync(file, 'r');
  try {
    await toolsKeeper({ run: async () => ({ doc: { ...DOC, ok: true } }), file, ...quiet() }).refresh();
    assert.deepEqual(JSON.parse(fs.readFileSync(old, 'utf8')), DOC);
    assert.equal(JSON.parse(fs.readFileSync(file, 'utf8')).ok, true);
  } finally { fs.closeSync(old); }
});

test('a failed run keeps the previous report and says so once per cause; a success re-arms the line', async () => {
  const file = path.join(scratch('tools-state-'), 'tools.json');
  const { said, log } = quiet();
  let next = { doc: DOC };
  const k = toolsKeeper({ run: async () => next, file, log });
  await k.refresh();
  const before = fs.readFileSync(file, 'utf8');
  next = { error: 'fabric-tools exited 127' };
  assert.deepEqual(await k.refresh(), { status: 'kept', error: 'fabric-tools exited 127' });
  await k.refresh();
  assert.equal(fs.readFileSync(file, 'utf8'), before, 'the old report stays');
  assert.equal(said.length, 1, said.join('|'));
  next = { error: 'fabric-tools exited 2' };
  await k.refresh();
  assert.equal(said.length, 2, 'another cause is another line');
  next = { doc: { ...DOC, ok: true } };
  await k.refresh();
  next = { error: 'fabric-tools exited 2' };
  await k.refresh();
  assert.equal(said.length, 3, 'after a success the same failure is news again');
});

test('a run that throws, or a report that cannot be written, is a kept report too', async () => {
  const dir = scratch('tools-state-'), file = path.join(dir, 'tools.json');
  const { said, log } = quiet();
  assert.equal((await toolsKeeper({ run: async () => { throw new Error('boom'); }, file, log }).refresh()).status, 'kept');
  fs.mkdirSync(file);   // a directory where the report goes: the rename fails
  const k = toolsKeeper({ run: async () => ({ doc: DOC }), file, log });
  const r = await k.refresh();
  assert.equal(r.status, 'kept');
  assert.match(r.error, /could not be written/);
  assert.deepEqual(fs.readdirSync(dir), ['tools.json'], 'no temporary file left behind');
});

test('two refreshes that overlap share one run', async () => {
  let runs = 0, release;
  const gate = new Promise(r => { release = r; });
  const k = toolsKeeper({ run: async () => { runs++; await gate; return { doc: DOC }; }, file: path.join(scratch('tools-state-'), 'tools.json'), ...quiet() });
  const a = k.refresh(), b = k.refresh();
  release();
  await Promise.all([a, b]);
  assert.equal(runs, 1);
  await k.refresh();
  assert.equal(runs, 2, 'and the next one runs again');
});

test('startToolsReport refreshes at once and then every hour, on a timer that does not hold the daemon up', () => {
  let refreshed = 0, timer = null, unref = 0;
  startToolsReport({ keeper: { refresh: () => { refreshed++; } }, setTimer: (fn, ms) => { timer = { fn, ms }; return { unref: () => { unref++; } }; } });
  assert.equal(refreshed, 1);
  assert.equal(timer.ms, 3600 * 1000);
  assert.equal(TOOLS_INTERVAL_MS, 3600 * 1000);
  timer.fn();
  assert.equal(refreshed, 2);
  assert.equal(unref, 1);
});

test('the tools op: none yet, the report with its age, and an unreadable one named', async () => {
  const dir = scratch('tools-state-');
  assert.deepEqual(await tools({ dir }), { status: 'none' });
  writeReport(reportFile(dir), DOC);
  const mtime = fs.statSync(reportFile(dir)).mtimeMs;
  const got = await tools({ dir, now: () => mtime + 3 * 3600 * 1000 });
  assert.deepEqual(got, { status: 'ok', age_s: 10800, ok: false, tools: DOC.tools });
  fs.writeFileSync(reportFile(dir), 'not json');
  assert.deepEqual(await tools({ dir }), { status: 'failed', error: 'tools.json is not JSON' });
  fs.writeFileSync(reportFile(dir), '{}');
  assert.match((await tools({ dir })).error, /holds no tools list/);
});

test('collect answers the tools op from the account\'s own state directory', async () => {
  const dir = scratch('tools-state-');
  writeReport(reportFile(dir), DOC);
  const d = await collect('tools', { toolsOpts: { dir } });
  assert.equal(d.tools.status, 'ok');
  assert.deepEqual(Object.keys(d), ['tools']);
});

test('fabric-ctl: tools is an op, and its row carries the account\'s section', () => {
  assert.equal(parseArgs(['all', 'tools']).op, 'tools');
  const [row] = rows([{ login: 'a', host: 'h', address: 'h/a' }], [{ from: 'h/a', op: 'tools', data: { tools: { status: 'none' } } }]);
  assert.deepEqual(row.tools, { status: 'none' });
});

test('fabric-ctl: the tools table names missing required tools only, the account once, with the report\'s age', () => {
  const out = table('tools', [
    { account: 'python-dev-03', status: 'ok', tools: { status: 'ok', age_s: 7500, ok: false, tools: DOC.tools } },
    { account: 'web-dev-01', status: 'ok', tools: { status: 'ok', age_s: 30, ok: true, tools: [DOC.tools[2]] } },
    { account: 'db-admin', status: 'ok', tools: { status: 'none' } },
    { account: 'qa', status: 'ok', tools: { status: 'failed', error: 'tools.json is not JSON' } },
    { account: 'old', status: 'silent' }]);
  const lines = out.split('\n');
  assert.equal(lines.length, 5, out);
  assert.match(lines[0], /^python-dev-03 +gzapp +pnpm +missing +needs 11\.6\.0, account +\(report 2 h old\)$/);
  assert.ok(!out.includes('doppler') && !out.includes(' git '), 'optional and present tools are not listed');
  assert.match(lines[1], /^web-dev-01 +nothing required is missing \(report 30 s old\)$/);
  assert.match(lines[2], /^db-admin +no report yet$/);
  assert.match(lines[3], /^qa +tools failed: tools\.json is not JSON$/);
  assert.match(lines[4], /^old +silent$/);
});

test('fabric-ctl: what an account put in a tools row cannot move the operator\'s terminal', () => {
  const evil = { project: 'p\u001b[2J', name: 'n\u009b', status: 'missing', version: '1', where: 'host', optional: false };
  const out = table('tools', [{ account: 'a', status: 'ok', tools: { status: 'ok', age_s: 5, ok: false, tools: [evil] } }]);
  assert.ok(!/[\u0000-\u0008\u000b-\u001f\u007f-\u009f]/.test(out), JSON.stringify(out));
  assert.ok(out.includes('\\x1b') && out.includes('\\x9b'));
});
