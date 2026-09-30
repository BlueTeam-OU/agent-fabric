// `upgrade fabric`, against real git: a bare origin and the account's
// checkout, with a bootstrap that records how it was run. The checkout
// fast-forwards to the requested commit or is left alone; bootstrap runs
// with the daemon's restart deferred to the daemon, and for the provider
// a running session was launched with.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { scratch } from '../../../tests/scratch.mjs';
import { upgrade, upgradeFabric, checkArgs, sessionProvider } from '../upgrade.mjs';

const git = (cwd, ...a) => execFileSync('git', ['-C', cwd, ...a], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'], env: { ...process.env, GIT_AUTHOR_NAME: 't', GIT_AUTHOR_EMAIL: 't@t', GIT_COMMITTER_NAME: 't', GIT_COMMITTER_EMAIL: 't@t' } }).trim();

function fixture({ bootstrapFails = false, unitChanged = false } = {}) {
  const base = scratch('upgrade-fabric-');
  const origin = path.join(base, 'origin.git'), seed = path.join(base, 'seed'), root = path.join(base, 'agent-fabric');
  const record = path.join(base, 'bootstrap.log');
  git(base, 'init', '-q', '--bare', '-b', 'main', origin);
  git(base, 'init', '-q', '-b', 'main', seed);
  fs.mkdirSync(path.join(seed, 'runtime', 'claude-code'), { recursive: true });
  fs.writeFileSync(path.join(seed, 'runtime', 'claude-code', 'bootstrap.sh'),
    bootstrapFails
      ? (unitChanged ? 'echo "  *  agent-fabric-agentd: unit changed; restart left to the caller"\n' : '') + 'echo "  *  settings"\necho "bootstrap: the agent files could not be written" >&2\nexit 1\n'
      : `printf 'defer=%s provider=%s\\n' "\${AGENT_FABRIC_DEFER_AGENTD_RESTART:-}" "\${AGENT_FABRIC_LAUNCH_PROVIDER:-}" >> "${record}"\n`
        + (unitChanged ? 'echo "  *  agent-fabric-agentd: unit changed; restart left to the caller"\n' : ''));
  git(seed, 'add', '-A'); git(seed, 'commit', '-q', '-m', 'one');
  git(seed, 'remote', 'add', 'origin', origin); git(seed, 'push', '-q', 'origin', 'main');
  git(base, 'clone', '-q', origin, root);
  const advance = msg => { fs.writeFileSync(path.join(seed, `${msg}.txt`), msg); git(seed, 'add', '-A'); git(seed, 'commit', '-q', '-m', msg); git(seed, 'push', '-q', 'origin', 'main'); return git(seed, 'rev-parse', 'HEAD'); };
  const runs = () => (fs.existsSync(record) ? fs.readFileSync(record, 'utf8').trim().split('\n') : []);
  return { base, root, advance, runs, head: () => git(root, 'rev-parse', 'HEAD') };
}
const req = commit => ({ id: 'req-1', from: 'h/user', op: 'upgrade', args: { piece: 'fabric', commit } });
const opts = (f, over = {}) => ({ root: f.root, sessions: [], env: { PATH: process.env.PATH, HOME: f.base }, ...over });

test('behind: fast-forwarded to the commit, bootstrapped with the daemon restart deferred, the daemon told to restart', async () => {
  const f = fixture();
  const from = f.head().slice(0, 7);
  const target = f.advance('two');
  const r = await upgradeFabric(req(target), opts(f));
  assert.equal(r.status, 'upgraded');
  assert.equal(r.from, from); assert.equal(r.to, target.slice(0, 7));
  assert.equal(f.head(), target);
  assert.deepEqual(f.runs(), ['defer=1 provider=']);
  assert.equal(r.restart_daemon, true);
  assert.equal(r.session, 'none');
});

test('at the commit: current, bootstrap still runs (a launcher pull never bootstrapped), no daemon restart', async () => {
  const f = fixture();
  const target = f.head();
  const r = await upgradeFabric(req(target), opts(f));
  assert.equal(r.status, 'current'); assert.equal(r.restart_daemon, false);
  assert.equal(f.runs().length, 1);
});

test('an older commit than the checkout: current, never moved back', async () => {
  const f = fixture();
  const old = f.head();
  const target = f.advance('two');
  git(f.root, 'pull', '-q', '--ff-only');
  const r = await upgradeFabric(req(old), opts(f));
  assert.equal(r.status, 'current'); assert.equal(f.head(), target);
});

test('a checkout on a branch is someone\'s work: refused, not moved, not bootstrapped', async () => {
  const f = fixture();
  git(f.root, 'switch', '-q', '-c', 'h/someone/work');
  const target = f.advance('two');
  const before = f.head();
  const r = await upgradeFabric(req(target), opts(f));
  assert.equal(r.status, 'refused'); assert.match(r.reason, /on h\/someone\/work, not main/);
  assert.equal(f.head(), before); assert.deepEqual(f.runs(), []);
});

test('a branch with nothing uncommitted and nothing unpushed: still refused, but the reason says a switch loses nothing', async () => {
  const f = fixture();
  git(f.root, 'switch', '-q', '-c', 'h/someone/locale');
  git(f.root, 'push', '-q', '-u', 'origin', 'h/someone/locale');
  const target = f.advance('two');
  const before = f.head();
  const r = await upgradeFabric(req(target), opts(f));
  assert.equal(r.status, 'refused');
  assert.match(r.reason, /clean and pushed, so nothing is lost by `git switch main`/);
  assert.equal(f.head(), before, 'not moved: a session on the branch would lose its hooks'); assert.deepEqual(f.runs(), []);
  fs.writeFileSync(path.join(f.root, 'unpushed.txt'), 'x'); git(f.root, 'add', '-A'); git(f.root, 'commit', '-q', '-m', 'local');
  const r2 = await upgradeFabric(req(target), opts(f));
  assert.match(r2.reason, /find whose work it is/, 'an unpushed commit: not known safe');
});

test('a main that cannot fast-forward (a local commit): failed, never forced, not bootstrapped', async () => {
  const f = fixture();
  fs.writeFileSync(path.join(f.root, 'local.txt'), 'x'); git(f.root, 'add', '-A');
  execFileSync('git', ['-C', f.root, '-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-q', '-m', 'local']);
  const before = f.head();
  const target = f.advance('two');
  const r = await upgradeFabric(req(target), opts(f));
  assert.equal(r.status, 'failed'); assert.match(r.reason, /cannot fast-forward .*not forced/);
  assert.equal(f.head(), before); assert.deepEqual(f.runs(), []);
});

test('a commit that is not on the account\'s origin/main: refused, not moved', async () => {
  const f = fixture();
  const before = f.head();
  const r = await upgradeFabric(req('0'.repeat(40)), opts(f));
  assert.equal(r.status, 'refused'); assert.match(r.reason, /not on this account's origin\/main/);
  assert.equal(f.head(), before);
});

test('a bootstrap that fails: failed with its last line; the checkout has moved and says so', async () => {
  const f = fixture({ bootstrapFails: true });
  const target = f.advance('two');
  const r = await upgradeFabric(req(target), opts(f));
  assert.equal(r.status, 'failed'); assert.equal(r.to, target.slice(0, 7));
  assert.equal(r.reason, 'bootstrap: bootstrap: the agent files could not be written');
});

test('a running session: bootstrap installs for the provider it was launched with; the session is not stopped', async () => {
  const f = fixture();
  const proc = path.join(f.base, 'proc');
  fs.mkdirSync(path.join(proc, '4242'), { recursive: true });
  fs.writeFileSync(path.join(proc, '4242', 'environ'), 'HOME=/h\0AGENT_FABRIC_LAUNCH_PROVIDER=openrouter\0');
  const target = f.advance('two');
  const r = await upgradeFabric(req(target), opts(f, { sessions: [4242], proc }));
  assert.equal(r.provider, 'openrouter'); assert.equal(r.session, 'running: next launch uses it');
  assert.deepEqual(f.runs(), ['defer=1 provider=openrouter']);
});

test('sessionProvider: an unreadable or malformed value is no provider', () => {
  const proc = scratch('upgrade-fabric-proc-');
  fs.mkdirSync(path.join(proc, '7'), { recursive: true });
  fs.writeFileSync(path.join(proc, '7', 'environ'), 'AGENT_FABRIC_LAUNCH_PROVIDER=$(x)\0');
  assert.equal(sessionProvider([7, 8], proc), null);
});

test('arguments: fabric takes a full sha and no version; claude takes no commit', () => {
  assert.equal(checkArgs({ piece: 'fabric', commit: 'a'.repeat(40) }), null);
  assert.match(checkArgs({ piece: 'fabric', commit: 'abc1234' }), /full 40-hex sha/);
  assert.match(checkArgs({ piece: 'fabric', commit: 'a'.repeat(40), version: '2.1.1' }), /not a version/);
  assert.match(checkArgs({ piece: 'claude', commit: 'a'.repeat(40) }), /not a commit/);
});

test('upgrade() routes the fabric piece, one action at a time', async () => {
  const f = fixture();
  const target = f.advance('two');
  const [a, b] = await Promise.all([upgrade(req(target), opts(f)), upgrade(req(target), opts(f))]);
  assert.equal(a.status, 'upgraded'); assert.equal(b.status, 'busy');
});

test('a current checkout whose bootstrap changed the control agent\'s unit: the daemon still restarts, and the row says so', async () => {
  const f = fixture({ unitChanged: true });
  const r = await upgradeFabric(req(f.head()), opts(f));
  assert.equal(r.status, 'current');
  assert.equal(r.restart_daemon, true);
  assert.match(r.note, /restarts on the new unit/);
});

test('a merge-base that cannot tell (not a "no"): failed with git\'s line, not "not on origin/main"', async () => {
  const f = fixture();
  const real = (await import('node:child_process')).execFile;
  const { promisify } = await import('node:util');
  const run = promisify(real);
  const exec = async (bin, args, o) => {
    if (args.includes('merge-base')) { const e = new Error('Command failed'); e.code = 128; e.stderr = 'fatal: bad object'; throw e; }
    return run(bin, args, o);
  };
  const r = await upgradeFabric(req(f.advance('two')), opts(f, { exec }));
  assert.equal(r.status, 'failed'); assert.match(r.reason, /git merge-base: fatal: bad object; not moved/);
});

test('a commit the account has but not on its origin/main (a pushed branch): refused, not moved', async () => {
  const f = fixture();
  const seed = path.join(f.base, 'seed');
  git(seed, 'switch', '-q', '-c', 'side');
  fs.writeFileSync(path.join(seed, 'side.txt'), 'x'); git(seed, 'add', '-A'); git(seed, 'commit', '-q', '-m', 'side');
  git(seed, 'push', '-q', 'origin', 'side');
  const side = git(seed, 'rev-parse', 'HEAD');
  git(f.root, 'fetch', '-q', 'origin', 'side');
  const before = f.head();
  const r = await upgradeFabric(req(side), opts(f));
  assert.equal(r.status, 'refused'); assert.match(r.reason, /not on this account's origin\/main/);
  assert.equal(f.head(), before);
});

test('a bootstrap that installed the unit and then failed: failed, and the daemon still restarts (no rerun would see the change)', async () => {
  const f = fixture({ bootstrapFails: true, unitChanged: true });
  const r = await upgradeFabric(req(f.head()), opts(f));
  assert.equal(r.status, 'failed'); assert.equal(r.restart_daemon, true);
});
