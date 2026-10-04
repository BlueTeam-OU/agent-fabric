#!/usr/bin/env node
// Tests for runtime/control/pressure.mjs: what a sample reads, how the ring
// is kept, what the host op and fabric-ctl host say about it.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { scratch } from '../../../tests/scratch.mjs';
import { sample, sampler, summary, readRing, memoryPressure, HOUR_MS, RING_MAX } from '../pressure.mjs';
import { collect } from '../ops.mjs';
import { table, rows, pressureText } from '../ctl.mjs';

const PSI = 'some avg10=12.50 avg60=3.10 avg300=0.80 total=1453197\nfull avg10=4.25 avg60=1.00 avg300=0.20 total=1328293\n';
const MEMINFO = 'MemTotal:        8000000 kB\nMemFree:          100000 kB\nMemAvailable:     409600 kB\n';
function fakeProc({ psi = PSI, meminfo = MEMINFO } = {}) {
  const proc = scratch('pressure-proc-');
  if (psi !== null) { fs.mkdirSync(path.join(proc, 'pressure')); fs.writeFileSync(path.join(proc, 'pressure', 'memory'), psi); }
  if (meminfo !== null) fs.writeFileSync(path.join(proc, 'meminfo'), meminfo);
  return proc;
}
const T0 = Date.parse('2026-10-04T16:00:00Z');
const at = min => new Date(T0 + min * 60_000).toISOString();

test('sample: PSI some/full avg10 and MemAvailable in MB; a reading the kernel did not give is null, never 0', () => {
  assert.deepEqual(sample({ proc: fakeProc(), now: () => T0 }), { ts: at(0), some_avg10: 12.5, full_avg10: 4.25, mem_available_mb: 400 });
  assert.deepEqual(sample({ proc: fakeProc({ psi: null }), now: () => T0 }), { ts: at(0), some_avg10: null, full_avg10: null, mem_available_mb: 400 }, 'a kernel without PSI is not a calm machine');
  assert.deepEqual(sample({ proc: fakeProc({ psi: 'some avg10=x\nfull nonsense\n', meminfo: 'MemTotal: 1 kB\n' }), now: () => T0 }),
                   { ts: at(0), some_avg10: null, full_avg10: null, mem_available_mb: null }, 'unparseable is unknown');
  assert.equal(sample({ proc: fakeProc({ psi: 'full avg10=1.00 avg60=0 avg300=0 total=0\n' }), now: () => T0 }).some_avg10, null, 'full is not read as some');
});

test('sampler: one sample a tick, persisted whole, bounded, kept across a restart', () => {
  const dir = scratch('pressure-state-');
  const file = path.join(dir, 'agents', 'me', 'memory-pressure.json');
  let t = T0; const now = () => t;
  const proc = fakeProc();
  const s = sampler({ file, proc, now, max: 5, log: () => {} });
  for (let i = 0; i < 7; i++) { s.tick(); t += 60_000; }
  const ring = readRing(file);
  assert.equal(ring.length, 5, 'the oldest go once the ring is full');
  assert.deepEqual(ring.map(x => x.ts), [at(2), at(3), at(4), at(5), at(6)]);
  assert.equal(fs.statSync(file).mode & 0o777, 0o600);
  assert.deepEqual(fs.readdirSync(path.dirname(file)), ['memory-pressure.json'], 'no temporary file is left');
  // A restarted daemon continues the ring it finds.
  sampler({ file, proc, now, max: 5, log: () => {} }).tick();
  assert.deepEqual(readRing(file).map(x => x.ts).slice(-2), [at(6), at(7)]);
  assert.equal(RING_MAX, 1440, 'a day of minutes by default');
});

test('sampler: a bad ring is kept aside and a new one begun; a failure to write is one line when it starts and one when it ends', () => {
  const dir = scratch('pressure-bad-');
  const file = path.join(dir, 'memory-pressure.json');
  fs.writeFileSync(file, '{"not": "a list"}');
  const logs = [];
  sampler({ file, proc: fakeProc(), now: () => T0, log: m => logs.push(m) }).tick();
  assert.equal(readRing(file).length, 1, 'sampling goes on');
  assert.equal(fs.readFileSync(`${file}.unreadable`, 'utf8'), '{"not": "a list"}', 'the bad file is evidence, not deleted');
  assert.equal(logs.length, 1); assert.match(logs[0], /not a list of samples; kept as memory-pressure\.json\.unreadable/);

  // The ring's directory is a file: nothing can be written until it is not.
  const blocked = path.join(scratch('pressure-blocked-'), 'state');
  fs.writeFileSync(blocked, 'a file where the directory goes');
  const logs2 = [];
  const s = sampler({ file: path.join(blocked, 'memory-pressure.json'), proc: fakeProc(), now: () => T0, log: m => logs2.push(m) });
  s.tick(); s.tick(); s.tick();
  assert.equal(logs2.length, 1, `not one line a minute: ${logs2}`); assert.match(logs2[0], /cannot keep the ring \((EEXIST|ENOTDIR)\)/);
  fs.rmSync(blocked);
  s.tick();
  assert.deepEqual(logs2.slice(1), ['agentd: memory pressure: sampling again']);
  assert.equal(readRing(path.join(blocked, 'memory-pressure.json')).length, 1);

  // A ring that cannot be READ is not a bad ring: retried, never replaced.
  if (process.getuid() !== 0) {
    const kept = path.join(scratch('pressure-locked-'), 'memory-pressure.json');
    sampler({ file: kept, proc: fakeProc(), now: () => T0, log: () => {} }).tick();
    fs.chmodSync(kept, 0o000);
    const logs3 = [];
    const s3 = sampler({ file: kept, proc: fakeProc(), now: () => T0 + 60_000, log: m => logs3.push(m) });
    s3.tick();
    fs.chmodSync(kept, 0o600);
    s3.tick();
    assert.equal(fs.existsSync(`${kept}.unreadable`), false);
    assert.match(logs3[0], /cannot keep the ring \(EACCES\)/);
    assert.equal(readRing(kept).length, 2, 'the day already sampled is still there');
  }
});

test('readRing: no file is null; a ring that is not a list of samples throws, never reads as empty', () => {
  const dir = scratch('pressure-read-');
  assert.equal(readRing(path.join(dir, 'none.json')), null);
  for (const bad of ['', '[', '{}', '[{"ts": "x", "some_avg10": 1, "full_avg10": 1, "mem_available_mb": 1}]', `[{"ts": "${at(0)}", "some_avg10": "1", "full_avg10": 1, "mem_available_mb": 1}]`]) {
    fs.writeFileSync(path.join(dir, 'r.json'), bad);
    assert.throws(() => readRing(path.join(dir, 'r.json')), undefined, `refused: ${bad}`);
  }
});

test('summary: the last readings, and the worst of the last hour with when — highest stalls, lowest MemAvailable; older and future samples are not in it', () => {
  const s = (min, some, full, avail) => ({ ts: at(min), some_avg10: some, full_avg10: full, mem_available_mb: avail });
  const ring = [s(-90, 99, 99, 1), s(-50, 10, 1, 900), s(-30, 40, 2, 300), s(-20, null, 8, null), s(-1, 0, 0, 2000), s(0, 1, 0, 1900), s(5, 100, 100, 0)];
  const out = summary(ring, T0);
  assert.deepEqual(out.last, ring.slice(-3));
  assert.deepEqual(out.hour, { samples: 5, some_avg10: { value: 40, ts: at(-30) }, full_avg10: { value: 8, ts: at(-20) }, mem_available_mb: { value: 300, ts: at(-30) } });
  assert.equal(out.samples, 7); assert.equal(out.since, at(-90)); assert.equal(out.interval_s, 60);
  assert.deepEqual(summary([s(-61, 50, 50, 50)], T0).hour, { samples: 0, some_avg10: null, full_avg10: null, mem_available_mb: null }, 'an hour with no samples has no worst');
  assert.equal(HOUR_MS, 3_600_000);
});

test('the host op carries the pressure: none before the first sample, failed for a bad ring, the summary otherwise', async () => {
  const dir = scratch('pressure-op-');
  const file = path.join(dir, 'memory-pressure.json');
  const ctx = { hostOpts: { proc: fakeProc(), sys: path.join(dir, 'nosys'), leases: path.join(dir, 'noleases'), exec: () => { throw new Error('no'); }, cpus: 2, statfs: () => { throw new Error('no'); } },
                pressureOpts: { file, now: () => T0 } };
  assert.deepEqual((await collect('host', ctx)).host.memory_pressure, { status: 'none' });
  fs.writeFileSync(file, 'garbage');
  assert.equal((await collect('host', ctx)).host.memory_pressure.status, 'failed');
  sampler({ file: path.join(dir, 'fresh.json'), proc: fakeProc(), now: () => T0 }).tick();
  const h = (await collect('host', { ...ctx, pressureOpts: { file: path.join(dir, 'fresh.json'), now: () => T0 } })).host;
  assert.equal(h.status, 'ok', 'the machine section is still the machine');
  assert.deepEqual(h.memory_pressure.hour.some_avg10, { value: 12.5, ts: at(0) });
  assert.equal(memoryPressure({ file: path.join(dir, 'fresh.json'), now: () => T0 }).last[0].mem_available_mb, 400);
});

test('fabric-ctl host: a memory line under each host — the last readings and the worst of the hour, from the account sampling longest', () => {
  const machine = { status: 'ok', cpus: 2, loadavg: [0, 0, 0], mem_mb: { total: 8000, available: 400, swap_total: 0, swap_free: 0 }, balloon_mb: null, disk: [], leases: [], top_rss: [] };
  const mp = n => ({ status: 'ok', samples: n, last: [{ ts: at(0), some_avg10: 12.5, full_avg10: 4.25, mem_available_mb: 400 }],
                     hour: { samples: n, some_avg10: { value: 40, ts: at(-30) }, full_avg10: { value: 8, ts: at(-20) }, mem_available_mb: { value: 300, ts: at(-30) } } });
  const expected = [{ login: 'a', host: 'h1', address: 'h1/a' }, { login: 'b', host: 'h1', address: 'h1/b' }];
  const t = table('host', rows(expected, [{ kind: 'reply', from: 'h1/a', op: 'host', data: { host: { ...machine, memory_pressure: mp(3) } } },
                                          { kind: 'reply', from: 'h1/b', op: 'host', data: { host: { ...machine, memory_pressure: mp(60) } } }]));
  assert.match(t, /memory: last 16:00Z 12\.5\/4\.25 400 MB \(some\/full avg10 %, available\); worst of the hour \(60 samples\): some 40 at 15:30Z, full 8 at 15:40Z, available 300 MB at 15:30Z/);
  assert.equal(pressureText([{ status: 'none' }]), 'no samples yet');
  assert.equal(pressureText([{ status: 'none' }, { status: 'failed', error: 'EACCES' }]), 'failed: EACCES');
  assert.equal(pressureText([undefined]), '-', 'an older daemon that sends none');
  assert.match(pressureText([{ status: 'ok', last: [{ ts: at(0), some_avg10: null, full_avg10: null, mem_available_mb: 400 }], hour: { samples: 1, some_avg10: null, full_avg10: null, mem_available_mb: { value: 400, ts: at(0) } } }]),
               /^last 16:00Z -\/- 400 MB .*some -, full -, available 400 MB at 16:00Z$/, 'unknown is a dash, never 0');
});
