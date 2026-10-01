// The `upgrade` action, against a fake harness: at the pin nothing moves;
// a running session is stopped gracefully (SIGTERM, never SIGKILL) with the
// launcher's restart marker written first; the install is verified; the
// requester's own session is never stopped; every failure is said; the
// host's install lease is held from before the stop until the read-back.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { scratch } from '../../../tests/scratch.mjs';
import { fileURLToPath } from 'node:url';
import { upgrade, upgradeOnce, holdLease, checkArgs, markerPath, pinnedVersion, sessionPids, lastLine, LEASE_HELD, POST_STOP_BUDGET_S } from '../upgrade.mjs';

function fixture({ installed = '2.1.280', pin = '2.1.281', installFails = false, installsWrong = false, settingsFail = false, settingsWarn = false } = {}) {
  const home = scratch('upgrade-home-');
  const root = scratch('upgrade-root-');
  fs.mkdirSync(path.join(root, 'runtime', 'claude-code'), { recursive: true });
  if (pin) fs.writeFileSync(path.join(root, 'runtime', 'claude-code', 'harness.json'), JSON.stringify({ claude: pin }));
  const dir = path.join(home, 'state');
  const calls = [];
  let current = installed;
  const exec = async (bin, args) => {
    calls.push(bin === 'python3' ? `user-settings ${path.relative(home, args[1])}` : args.join(' '));
    if (args[0] === '--version') return { stdout: `${current} (Claude Code)\n` };
    if (bin === 'python3') { if (settingsFail) { const e = new Error('Command failed: user-settings.py'); e.stderr = '  !  unreadable\n'; throw e; } return { stdout: '  +  settings\n', stderr: settingsWarn ? "  !  s.json: Claude Code's auto-mode defaults could not be read — autoMode left as it is\n" : '' }; }
    if (args[0] === 'install') { if (installFails) { const e = new Error(`Command failed: claude install ${args[1]}`); e.stderr = 'Downloading…\nInstall failed: network\n'; throw e; } current = installsWrong ? '2.1.279' : args[1]; return { stdout: '' }; }
    throw new Error('unexpected ' + args.join(' '));
  };
  // The host lease, faked: held at once, and the calls record when.
  const lease = async () => { calls.push('lease held'); return { release: async () => { calls.push('lease released'); } }; };
  return { home, root, dir, calls, exec, lease, get current() { return current; } };
}
const req = (over = {}) => ({ id: 'req-1', from: 'h/user', op: 'upgrade', args: { piece: 'claude' }, ...over });

test('at the pin: nothing is installed and no session is touched', async () => {
  const f = fixture({ installed: '2.1.281' });
  const killed = [];
  const r = await upgradeOnce(req(), { home: f.home, root: f.root, dir: f.dir, exec: f.exec, lease: f.lease, sessions: [111], kill: pid => killed.push(pid), me: 'h/db-admin' });
  assert.deepEqual(r, { status: 'current', piece: 'claude', version: '2.1.281', session: 'running' });
  assert.deepEqual(killed, []); assert.ok(!f.calls.some(c => c.startsWith('install')));
  assert.ok(!fs.existsSync(markerPath(f.dir)));
});

test('a running session: the marker first, then SIGTERM, wait, install, verify, marker done', async () => {
  const f = fixture();
  const order = [];
  let alive = true;
  const kill = (pid, sig) => { order.push(`kill ${pid} ${sig}`); assert.equal(JSON.parse(fs.readFileSync(markerPath(f.dir))).status, 'pending', 'the marker is written before the session is signalled'); alive = false; };
  const r = await upgradeOnce(req(), { home: f.home, root: f.root, dir: f.dir, exec: f.exec, lease: f.lease, sessions: [4242], kill, alive: () => alive, sleep: async () => {}, me: 'h/db-admin', now: () => new Date('2026-09-24T21:00:00Z') });
  assert.deepEqual(r, { status: 'upgraded', piece: 'claude', from: '2.1.280', to: '2.1.281', settings: 'refreshed', session: 'restarting' });
  assert.deepEqual(order, ['kill 4242 SIGTERM']);
  assert.deepEqual(f.calls, ['--version', 'lease held', 'install 2.1.281', '--version', 'user-settings .claude/settings.json', 'lease released'], 'the lease is taken before the stop and held through the read-back; the settings follow the new build');
  const m = JSON.parse(fs.readFileSync(markerPath(f.dir)));
  assert.deepEqual([m.status, m.from, m.to, m.installed, m.request_id, m.pids], ['done', '2.1.280', '2.1.281', '2.1.281', 'req-1', [4242]]);
  assert.equal(fs.statSync(markerPath(f.dir)).mode & 0o777, 0o600);
});

test('no session: installed, no marker, nothing signalled', async () => {
  const f = fixture();
  const r = await upgradeOnce(req(), { home: f.home, root: f.root, dir: f.dir, exec: f.exec, lease: f.lease, sessions: [], kill: () => assert.fail('nothing to signal'), me: 'h/db-admin' });
  assert.equal(r.status, 'upgraded'); assert.equal(r.session, 'none');
  assert.ok(!fs.existsSync(markerPath(f.dir)));
});

test('the requester\'s own session is never stopped: installed under it, and told to relaunch', async () => {
  const f = fixture();
  const r = await upgradeOnce(req({ from: 'h/user' }), { home: f.home, root: f.root, dir: f.dir, exec: f.exec, lease: f.lease, sessions: [777], kill: () => assert.fail('own session signalled'), me: 'h/user' });
  assert.deepEqual([r.status, r.session], ['upgraded', 'yours: relaunch to use it']);
  assert.ok(!fs.existsSync(markerPath(f.dir)), 'no restart marker for a session nobody stopped');
});

test('a session that does not stop: not installed, not forced, the marker says failed', async () => {
  const f = fixture();
  const sigs = [];
  const r = await upgradeOnce(req(), { home: f.home, root: f.root, dir: f.dir, exec: f.exec, lease: f.lease, sessions: [5], kill: (p, s) => sigs.push(s), alive: () => true, sleep: async () => {}, stopWaitMs: 0, me: 'h/db-admin' });
  assert.equal(r.status, 'failed'); assert.match(r.reason, /did not stop .* nothing forced/);
  assert.deepEqual(sigs, ['SIGTERM'], 'never a second, harder signal');
  assert.ok(!f.calls.some(c => c.startsWith('install')));
  assert.equal(f.calls.at(-1), 'lease released', 'a failure under the lease still releases it');
  assert.equal(JSON.parse(fs.readFileSync(markerPath(f.dir))).status, 'failed', 'the launcher relaunches on what is installed and says why');
});

test('an install that fails, or lands another version, is a failure with its reason; the marker lets the session come back anyway', async () => {
  for (const [opts, re] of [[{ installFails: true }, /claude install 2\.1\.281: Install failed: network$/], [{ installsWrong: true }, /after install, claude --version says 2\.1\.279/]]) {
    const f = fixture(opts);
    let alive = true;
    const r = await upgradeOnce(req(), { home: f.home, root: f.root, dir: f.dir, exec: f.exec, lease: f.lease, sessions: [9], kill: () => { alive = false; }, alive: () => alive, sleep: async () => {}, me: 'h/db-admin' });
    assert.equal(r.status, 'failed'); assert.match(r.reason, re);
    assert.equal(JSON.parse(fs.readFileSync(markerPath(f.dir))).status, 'failed');
  }
});

test('arguments are a closed set; no pin is a refusal; --version overrides the pin; one upgrade at a time', async () => {
  assert.match(checkArgs({ piece: 'kernel' }), /not one of claude, fabric/);
  assert.match(checkArgs({ piece: 'claude', version: '2.1.281; rm -rf /' }), /digits/);
  assert.match(checkArgs(null), /no arguments/);
  assert.equal(checkArgs({ piece: 'claude', version: '2.1.282' }), null);
  const f = fixture({ pin: null });
  assert.match((await upgradeOnce(req(), { home: f.home, root: f.root, dir: f.dir, exec: f.exec, lease: f.lease, sessions: [] })).reason, /no pinned version/);
  const g = fixture();
  const r = await upgradeOnce(req({ args: { piece: 'claude', version: '2.1.279' } }), { home: g.home, root: g.root, dir: g.dir, exec: g.exec, lease: g.lease, sessions: [] });
  assert.equal(r.to, '2.1.279');
  assert.equal(pinnedVersion(g.root), '2.1.281');
  let release; const gate = new Promise(res => { release = res; });
  const slow = fixture();
  const first = upgrade(req(), { home: slow.home, root: slow.root, dir: slow.dir, sessions: [], lease: slow.lease, exec: async (b, a) => { if (a[0] === 'install') await gate; return slow.exec(b, a); } });
  assert.equal((await upgrade(req({ id: 'req-2' }), {})).status, 'busy');
  release(); assert.equal((await first).status, 'upgraded');
});

test('sessionPids: this uid\'s claude processes, except the daemon\'s own children (the observer\'s /usage runs)', () => {
  const proc = scratch('upgrade-proc-');
  for (const [pid, ppid] of [[100, 50], [200, 999], [300, 60]]) { fs.mkdirSync(path.join(proc, String(pid))); fs.writeFileSync(path.join(proc, String(pid), 'stat'), `${pid} (claude) S ${ppid} 1 1 0 -1`); }
  assert.deepEqual(sessionPids({ self: 999, proc, exec: () => '100\n200\n300\n400\n' }), [100, 300], 'the daemon\'s child and a pid already gone are left out');
  assert.deepEqual(sessionPids({ self: 999, proc, exec: () => { const e = new Error('exit 1'); e.status = 1; throw e; } }), [], 'pgrep finding nothing is no session');
  assert.throws(() => sessionPids({ self: 999, proc, exec: () => { const e = new Error('spawn pgrep ENOENT'); e.code = 'ENOENT'; throw e; } }), /ENOENT/, 'pgrep missing is not "no session"');
});

test('a pgrep that fails: nothing installed, nothing signalled, the reason said', async () => {
  const f = fixture();
  const r = await upgradeOnce(req(), { home: f.home, root: f.root, dir: f.dir, exec: f.exec, lease: f.lease, me: 'h/db-admin', kill: () => assert.fail('no signal'),
    pgrep: () => { const e = new Error('spawn pgrep EACCES'); e.code = 'EACCES'; throw e; } });
  assert.equal(r.status, 'failed'); assert.match(r.reason, /could not tell whether a session is running .*EACCES.*nothing installed/);
  assert.ok(!f.calls.some(c => c.startsWith('install')));
});

test('no turn on the host lease: nothing stopped, nothing installed, and the reason says which — held, or no queue at all', async () => {
  for (const [err, re] of [[{ code: LEASE_HELD, line: 'still held' }, /install lease \(claude-install\) stayed held for 900 s; not installed, no session stopped/],
                           [{ code: 2, line: 'fabric-lease: no lease directory at /run/lock/agent-fabric' }, /install queue is unavailable \(fabric-lease: no lease directory .*\); not installed, no session stopped/]]) {
    const f = fixture();
    const r = await upgradeOnce(req(), { home: f.home, root: f.root, dir: f.dir, exec: f.exec, sessions: [31], me: 'h/db-admin',
      lease: async () => { throw err; }, kill: () => assert.fail('a session stopped before the install could start') });
    assert.deepEqual([r.status, r.session], ['failed', 'running']); assert.match(r.reason, re);
    assert.ok(!f.calls.some(c => c.startsWith('install')));
    assert.ok(!fs.existsSync(markerPath(f.dir)), 'no marker: the launcher has nothing to wait for');
  }
});

test('holdLease: the real fabric-lease holds until release; no lease directory and no script are refusals with their line', async () => {
  const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..', '..');
  const saved = process.env.AGENT_FABRIC_LEASES;
  try {
    process.env.AGENT_FABRIC_LEASES = scratch('upgrade-hold-');
    const h = await holdLease(ROOT);
    await assert.rejects(holdLease(ROOT, { waitS: 1 }), e => e.code === LEASE_HELD && e.reason === 'timeout' && /still held/.test(e.line), 'a second holder waits its time, then is refused — the reason as data, the prose as the line');
    await h.release();
    const again = await holdLease(ROOT); await again.release();
    process.env.AGENT_FABRIC_LEASES = path.join(scratch('upgrade-nolease-'), 'absent');
    await assert.rejects(holdLease(ROOT), e => e.code === 2 && e.reason === 'nodir' && /no lease directory/.test(e.line));
    await assert.rejects(holdLease(scratch('upgrade-noscript-')), e => e.code === -1 && /ENOENT/.test(e.line));
  } finally { if (saved === undefined) delete process.env.AGENT_FABRIC_LEASES; else process.env.AGENT_FABRIC_LEASES = saved; }
});

test('a refresh that wrote every key but autoMode is not a refresh', async () => {
  const f = fixture({ settingsWarn: true });
  const r = await upgradeOnce(req(), { home: f.home, root: f.root, dir: f.dir, exec: f.exec, lease: f.lease, sessions: [], kill: () => assert.fail('nothing to signal'), me: 'h/db-admin' });
  assert.equal(r.status, 'upgraded');
  assert.match(r.settings, /^not refreshed: .*auto-mode defaults could not be read/);
});

test('a settings refresh that fails is said, and the install still counts', async () => {
  const f = fixture({ settingsFail: true });
  const r = await upgradeOnce(req(), { home: f.home, root: f.root, dir: f.dir, exec: f.exec, lease: f.lease, sessions: [], kill: () => assert.fail('nothing to signal'), me: 'h/db-admin' });
  assert.equal(r.status, 'upgraded');
  assert.match(r.settings, /^not refreshed: .*unreadable/);
});

test('a failed install says why by its last line; one that timed out says so', async () => {
  const e = new Error('Command failed: /home/x/.local/bin/claude install 2.1.282\nline one'); e.stderr = 'Downloading…\n\nError: checksum mismatch for 2.1.282\n';
  assert.equal(lastLine(e), 'Error: checksum mismatch for 2.1.282', 'the line that says why, not "Command failed: <argv>"');
  assert.equal(lastLine({ message: 'only this' }), 'only this');
  const f = fixture();
  const r = await upgradeOnce(req(), { home: f.home, root: f.root, dir: f.dir, sessions: [], me: 'h/db-admin', lease: f.lease,
    exec: async (cmd, args) => { if (args[0] === 'install') { const k = new Error('Command failed'); k.killed = true; k.stderr = 'Downloading…\n'; throw k; } return f.exec(cmd, args); } });
  assert.match(r.reason, /claude install 2\.1\.281: timed out after 300 s$/);
});

test('the launcher outwaits what the daemon does after the stop', () => {
  const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..', '..');
  const m = fs.readFileSync(path.join(ROOT, 'tools', 'fabric', 'launch.py'), 'utf8').match(/^RESTART_WAIT_S = (\d+)$/m);
  assert.ok(m, 'the launcher\'s restart wait default is where this test reads it');
  assert.ok(Number(m[1]) > POST_STOP_BUDGET_S, `the launcher waits ${m[1]} s; the install and its read-back can take ${POST_STOP_BUDGET_S} s`);
});

test('two accounts upgrading at once on one host: each session stops only on its turn, and the installs run one after the other, through the real fabric-lease', async () => {
  const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..', '..');
  const leases = scratch('upgrade-leases-');
  const log = path.join(scratch('upgrade-log-'), 'installs.log');
  const account = name => {
    const home = scratch(`upgrade-${name}-`);
    fs.mkdirSync(path.join(home, '.local', 'bin'), { recursive: true });
    const state = path.join(home, 'installed');
    fs.writeFileSync(state, '2.1.281');
    // A fake harness: --version reads its state; install records start and end around a 1 s "download".
    fs.writeFileSync(path.join(home, '.local', 'bin', 'claude'), `#!/bin/sh
case "$1" in
  --version) echo "$(cat '${state}') (Claude Code)" ;;
  install) echo "start ${name} $(date +%s%N)" >> '${log}'; sleep 1; printf %s "$2" > '${state}'; echo "end ${name} $(date +%s%N)" >> '${log}' ;;
esac
`, { mode: 0o755 });
    return home;
  };
  const saved = process.env.AGENT_FABRIC_LEASES; process.env.AGENT_FABRIC_LEASES = leases;
  try {
    const [a, b] = ['alpha', 'beta'].map(account);
    const run = (home, name) => { let up = true; return upgradeOnce(req({ args: { piece: 'claude', version: '2.1.282' } }), { home, root: ROOT, dir: path.join(home, 'state'), sessions: [4000], me: 'h/x',
      kill: () => { fs.appendFileSync(log, `stop ${name}\n`); up = false; }, alive: () => up, sleep: async () => {} }); };
    const [ra, rb] = await Promise.all([run(a, 'alpha'), run(b, 'beta')]);
    assert.deepEqual([ra.status, rb.status], ['upgraded', 'upgraded'], JSON.stringify([ra, rb]));
    const ev = fs.readFileSync(log, 'utf8').trim().split('\n').map(l => l.split(' '));
    assert.deepEqual(ev.map(e => e[0]), ['stop', 'start', 'end', 'stop', 'start', 'end'], `a session stopped out of its turn, or the installs overlapped:\n${ev.map(e => e.join(' ')).join('\n')}`);
    assert.ok(ev[0][1] === ev[2][1] && ev[3][1] === ev[5][1], 'each account stops, installs and finishes before the next one stops');
  } finally { if (saved === undefined) delete process.env.AGENT_FABRIC_LEASES; else process.env.AGENT_FABRIC_LEASES = saved; }
});
