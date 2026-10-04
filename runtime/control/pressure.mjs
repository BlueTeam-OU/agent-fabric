// runtime/control/pressure.mjs — the machine's memory pressure, sampled by
// this account's agentd once a minute into a bounded ring in its own state.
//
// The host froze on 2026-10-04 and left nothing to read: journald fell
// silent at 16:33, and `fabric-ctl host` only answers for the moment it is
// asked. So the daemon samples /proc/pressure/memory — some and full
// avg10, the share of the last ten seconds in which some, or all,
// non-idle tasks stalled on memory — and MemAvailable, and keeps them in
// <stateDir>/memory-pressure.json, where the run-up to a freeze is still
// there after the reboot. Numbers only. The file is this account's own;
// no other account's state is read or written.
//
// A reading the kernel did not give is null, never 0: a kernel without
// PSI and a calm machine are different answers.

import fs from 'node:fs';
import path from 'node:path';
import { stateDir } from './upgrade.mjs';

export const SAMPLE_INTERVAL_MS = 60_000;
export const RING_MAX = 1440;   // a day of minutes: the evening before a morning's look
export const HOUR_MS = 3600_000;
export const LAST_N = 3;
export const ringFile = (dir = stateDir()) => path.join(dir, 'memory-pressure.json');

export function sample({ proc = '/proc', now = Date.now } = {}) {
  const read = f => { try { return fs.readFileSync(path.join(proc, f), 'utf8'); } catch { return null; } };
  const psi = read(path.join('pressure', 'memory'));
  const avg10 = kind => { const m = psi && new RegExp(`^${kind} avg10=(\\d+(?:\\.\\d+)?) `, 'm').exec(psi); return m ? Number(m[1]) : null; };
  const av = /^MemAvailable:\s+(\d+) kB$/m.exec(read('meminfo') ?? '');
  return { ts: new Date(now()).toISOString(), some_avg10: avg10('some'), full_avg10: avg10('full'), mem_available_mb: av ? Math.round(Number(av[1]) / 1024) : null };
}

const READINGS = ['some_avg10', 'full_avg10', 'mem_available_mb'];
const isSample = s => s && typeof s === 'object' && typeof s.ts === 'string' && Number.isFinite(Date.parse(s.ts))
  && READINGS.every(k => s[k] === null || Number.isFinite(s[k]));

// What the file holds is wrong, as against a file that could not be read.
export class BadRing extends Error {}

// null when there is no ring yet; a ring that is not a list of samples
// throws BadRing — it is never read as an empty one; a read that failed
// throws its own error.
export function readRing(file = ringFile()) {
  let text;
  try { text = fs.readFileSync(file, 'utf8'); }
  catch (e) { if (e.code === 'ENOENT') return null; throw e; }
  let ring;
  try { ring = JSON.parse(text); } catch { throw new BadRing(`${file}: not JSON`); }
  if (!Array.isArray(ring) || !ring.every(isSample)) throw new BadRing(`${file}: not a list of samples`);
  return ring;
}

function writeRing(file, ring) {
  fs.mkdirSync(path.dirname(file), { recursive: true, mode: 0o700 });
  const tmp = `${file}.${process.pid}.tmp`;
  fs.writeFileSync(tmp, JSON.stringify(ring) + '\n', { mode: 0o600 });
  fs.renameSync(tmp, file);   // whole or not at all: a freeze mid-write must not cost the ring
}

// One per daemon. tick() takes a sample and persists the ring; a failure is
// one line when it starts and one when it ends, not one a minute. A ring
// whose content is bad is kept aside as <file>.unreadable and a new one
// begun: sampling that stopped for good on a bad file would be the silence
// this exists to end. A ring that could not be read is retried next tick,
// never replaced: a passing I/O error must not cost a day of samples.
export function sampler({ file = ringFile(), proc, now = Date.now, max = RING_MAX, log = m => console.error(m) } = {}) {
  let ring = null, failing = false;
  const tick = () => {
    try {
      if (ring === null) {
        try { ring = readRing(file) ?? []; }
        catch (e) {
          if (!(e instanceof BadRing)) throw e;
          fs.renameSync(file, `${file}.unreadable`);
          log(`agentd: memory pressure: ${e.message}; kept as ${path.basename(file)}.unreadable, a new ring begun`);
          ring = [];
        }
      }
      ring.push(sample({ proc, now }));
      if (ring.length > max) ring.splice(0, ring.length - max);
      writeRing(file, ring);
      if (failing) { log('agentd: memory pressure: sampling again'); failing = false; }
    } catch (e) {
      if (!failing) log(`agentd: memory pressure: cannot keep the ring (${e.code ?? e.message})`);
      failing = true;
    }
  };
  return { tick };
}

// The last readings and, per reading, the worst of the last hour with when
// it was: the highest stall shares, the lowest MemAvailable. A sample
// dated ahead of now (a clock set back) is not in the hour.
export function summary(ring, now = Date.now()) {
  const hour = ring.filter(s => { const t = Date.parse(s.ts); return t > now - HOUR_MS && t <= now; });
  const worst = (key, worse) => {
    let w = null;
    for (const s of hour) if (s[key] !== null && (w === null || worse(s[key], w.value))) w = { value: s[key], ts: s.ts };
    return w;
  };
  return { status: 'ok', interval_s: SAMPLE_INTERVAL_MS / 1000, samples: ring.length, since: ring[0]?.ts ?? null, last: ring.slice(-LAST_N),
           hour: { samples: hour.length, some_avg10: worst('some_avg10', (a, b) => a > b), full_avg10: worst('full_avg10', (a, b) => a > b),
                   mem_available_mb: worst('mem_available_mb', (a, b) => a < b) } };
}

// For the `host` op: `none` before the first sample, `failed` with the
// reason for a ring that cannot be read.
export function memoryPressure({ file = ringFile(), now = Date.now } = {}) {
  try {
    const ring = readRing(file);
    return ring === null ? { status: 'none' } : summary(ring, now());
  } catch (e) { return { status: 'failed', error: String(e.code ?? e.message).slice(0, 200) }; }
}
