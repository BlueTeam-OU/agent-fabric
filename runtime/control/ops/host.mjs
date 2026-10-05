// runtime/control/ops/host.mjs — the machine the account shares, and the account's own home measured.
// A part of ops.mjs, which re-exports it; ops.mjs's header is the contract
// every extractor here keeps.

import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { execFileP } from './util.mjs';


// The MACHINE this account shares — what develop-qzapp's crash of
// 2026-09-19 was diagnosed from by hand, after the fact, with free, df,
// xenstore-read and find (docs/live-checks/2026-09-19-develop-qzapp-crash.md;
// the layers: ADR-010). Load and cpus; memory and swap from
// /proc/meminfo; the Xen balloon where there is one (current and target
// from sysfs, static-max — the ceiling this boot — from xenstore, null on
// a host that is not a Xen guest); every mounted block device once, by
// statfs; the leases held under /run/lock/agent-fabric, each probed with
// a read-only flock (held or not is the kernel's answer, the record line
// only says by whom); the largest processes by RSS, with the login they
// run as. Numbers and names of programs and logins, never a command
// line. Every daemon on one host answers the same numbers: fabric-ctl
// collapses the rows by host.
export function host({ proc = '/proc', sys = '/sys', leases = '/run/lock/agent-fabric', exec = execFileSync, cpus = os.cpus().length, statfs = fs.statfsSync } = {}) {
  const read = f => { try { return fs.readFileSync(f, 'utf8'); } catch { return null; } };
  const run = (cmd, args) => { try { const r = exec(cmd, args, { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'], timeout: 5000 }); return typeof r === 'string' ? r : r.stdout; } catch { return null; } };
  const mb = kb => kb == null ? null : Math.round(kb / 1024);
  const out = { status: 'ok', cpus, loadavg: null, mem_mb: null, balloon_mb: null, disk: [], leases: [], top_rss: [] };
  const la = read(path.join(proc, 'loadavg'));
  if (la) out.loadavg = la.trim().split(/\s+/).slice(0, 3).map(Number);
  const mi = read(path.join(proc, 'meminfo'));
  if (mi) {
    const kb = {}; for (const m of mi.matchAll(/^(\w+):\s+(\d+) kB/gm)) kb[m[1]] = Number(m[2]);
    out.mem_mb = { total: mb(kb.MemTotal), available: mb(kb.MemAvailable), swap_total: mb(kb.SwapTotal), swap_free: mb(kb.SwapFree) };
  }
  const xm = path.join(sys, 'devices', 'system', 'xen_memory', 'xen_memory0');
  const cur = read(path.join(xm, 'info', 'current_kb')), tgt = read(path.join(xm, 'target_kb'));
  if (cur != null || tgt != null) {
    const smax = run('xenstore-read', ['memory/static-max']);
    // static-max is xenstore's, and /dev/xen/xenbus is root:qubes on this
    // deployment: an account's daemon reads null, the operator's the number;
    // fabric-ctl prefers the row that has it. A half-present sysfs is null
    // per field, never 0 (Number(null) is 0).
    out.balloon_mb = { current: cur == null ? null : mb(Number(cur)), target: tgt == null ? null : mb(Number(tgt)), static_max: smax ? mb(Number(smax.trim())) : null };
  }
  const mounts = read(path.join(proc, 'mounts'));
  if (mounts) {
    const seen = new Set();
    for (const line of mounts.split('\n')) {
      const [dev, mnt] = line.split(' ');
      if (!dev?.startsWith('/dev/') || seen.has(dev)) continue;
      seen.add(dev);
      try { const st = statfs(mnt.replace(/\\040/g, ' ')); const size = st.blocks * st.bsize, avail = st.bavail * st.bsize;
        out.disk.push({ mount: mnt, size_gb: Math.round(size / 2 ** 30), avail_gb: Math.round(avail / 2 ** 30), use_pct: size ? Math.round(100 * (size - avail) / size) : null }); }
      catch { /* a mount that vanished between the read and the statfs: not a row */ }
    }
  }
  // Only what fabric-lease itself can create is a lease: its name grammar,
  // [A-Za-z0-9][A-Za-z0-9._-]{0,63}. The directory is world-writable, so any
  // login can drop any name there; a name outside the grammar is not a lease
  // and never reaches the probe — and the name reaches only fs.openSync,
  // never a command line; the grammar is the first gate, not the only one.
  const LEASE_NAME = /^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/;
  let names = []; try { names = fs.readdirSync(leases).filter(n => LEASE_NAME.test(n)); } catch { /* no lease directory: no leases */ }
  for (const n of names) {
    const f = path.join(leases, n);
    // The file is opened READ-ONLY here and the descriptor handed to
    // flock(1) as fd 3 — no shell, no command text built from a name in a
    // world-writable directory. The flock command opening the path itself
    // would use O_CREAT, which fs.protected_regular refuses on another
    // login's file in the sticky directory. O_NONBLOCK and O_NOFOLLOW, then
    // fstat on the descriptor rather than stat before the open: any login
    // can rename a fifo or a symlink over its own grammar-named entry in
    // between, and a blocking open of a reader-less fifo would hang this
    // synchronous op — and the daemon with it — for good. A SHARED lock,
    // not exclusive: an exclusive probe would hold a free lease for a
    // moment, and sixteen daemons probing at once could refuse a real
    // caller and each report the other's hold as a stale holder; a shared
    // probe is refused only by a real holder's exclusive lock (exit 1). A
    // file that cannot be opened (a hand-made 0600) is not a lease row.
    let fd; try { fd = fs.openSync(f, fs.constants.O_RDONLY | fs.constants.O_NONBLOCK | fs.constants.O_NOFOLLOW); } catch { continue; }
    try {
      if (!fs.fstatSync(fd).isFile()) continue;
      let held = false;
      try { exec('flock', ['-s', '-n', '3'], { stdio: ['ignore', 'ignore', 'ignore', fd], timeout: 5000 }); }
      catch (e) { held = e?.status === 1; }
      if (!held) continue;
      // The record is the holder's own line — informational, and read
      // bounded: the first 256 bytes, never a whole file a login has grown.
      const buf = Buffer.alloc(256); const nread = fs.readSync(fd, buf, 0, 256, 0);
      const rec = buf.toString('utf8', 0, nread).split('\n')[0];
      const [login, pid, since] = rec.split(' ');
      // The job the holder named with --label: "<name> (<job>)" at the end.
      const label = /\(([A-Za-z0-9._-]{1,64})\)$/.exec(rec)?.[1] ?? null;
      out.leases.push({ name: n, holder: login || null, pid: Number(pid) || null, since: since || null, label });
    } finally { try { fs.closeSync(fd); } catch { /* already closed */ } }
  }
  const ps = run('ps', ['-eo', 'user:32,pid,rss,comm', '--sort=-rss']);
  if (ps) out.top_rss = ps.trim().split('\n').slice(1, 7).map(l => { const [user, pid, rss, ...comm] = l.trim().split(/\s+/); return { user, pid: Number(pid), rss_mb: mb(Number(rss)), comm: comm.join(' ') }; });
  return out;
}


// The account's own home, measured: what /home's space is spent on, and by
// whom (2026-10-04: /home on a host reached 90% and no account could say
// whose homes held it; the owner ran sudo du by hand). Each daemon
// measures its OWN home and nothing else: its largest top-level entries
// and every target/ directory under ~/projects to depth 3 — names and
// sizes only, never contents. One scan: du -xsk over the top-level entries
// but projects/, and du -xk -d 3 over projects/, whose own line is its
// total and whose target/ lines are the build directories (a target/
// inside a target/ is not counted twice). The total is the sum of the
// entries. du runs through the injected exec, bounded: one that stops at
// its bound or reads part of a tree (exit 1 on an unreadable file) still
// reports what it measured, the status says partial and `errors` says
// why; a home that cannot be listed is failed, never a crash. Sizes in
// KiB, du's own unit. du's records end in NUL (-0), never a newline: a
// file name may hold one, and split on lines it invented entries, totals
// and target/ paths; a record whose path is not under the home is dropped
// (review of #92, round 4).
export const DISK_TIMEOUT_MS = 150000;

export const DISK_MAX_BUFFER = 64 * 1024 * 1024;

export const DISK_TOP = 5;

export async function disk(home = os.homedir(), { exec = execFileP, timeoutMs = DISK_TIMEOUT_MS, readdir = fs.readdirSync } = {}) {
  let names;
  try { names = readdir(home); }
  catch (e) { return { status: 'failed', error: `${home} could not be listed (${e.code ?? e.message})` }; }
  const errors = [];
  const du = async (args, what) => {
    let text = '', said = '';
    // LC_ALL=C: du's complaints are read below, so they must not be translated.
    const opts = { encoding: 'utf8', timeout: timeoutMs, maxBuffer: DISK_MAX_BUFFER, env: { ...process.env, LC_ALL: 'C' } };
    try { const r = await exec('du', args, opts); text = String(typeof r === 'string' ? r : r?.stdout ?? ''); said = String(r?.stderr ?? ''); }
    catch (e) {
      text = String(e?.stdout ?? ''); said = String(e?.stderr ?? '');
      const why = e?.code === 'ERR_CHILD_PROCESS_STDIO_MAXBUFFER' ? `du's output passed its ${DISK_MAX_BUFFER / 1048576} MiB bound`
        : e?.killed || e?.signal ? `du stopped at its ${timeoutMs / 1000} s bound` : `du exit ${e?.code ?? '?'}`;
      errors.push(`${what}: ${why}${text.trim() ? ', partial' : ''}`);
    }
    // What du could not read is not in the total: say how much, and where to
    // look first. A rootless podman's volumes are owned by a sub-UID, so a
    // home that runs containers has some.
    const unread = said.split('\n').map(l => /^du: cannot (?:read directory|access) (.*): [^:]*$/.exec(l)?.[1]).filter(Boolean);
    if (unread.length) errors.push(`${what}: ${unread.length} path${unread.length === 1 ? '' : 's'} du could not read, not counted; the first: ${unread[0]}`);
    const sizes = new Map(), outside = [];
    const inside = p => p === home || p.startsWith(home.endsWith(path.sep) ? home : home + path.sep);
    // Each record ends in NUL (-0): a newline is part of a name, never a separator.
    for (const rec of text.split('\0')) {
      const m = /^(\d+)\t([\s\S]+)$/.exec(rec);
      if (!m) continue;
      if (inside(m[2])) sizes.set(m[2], Number(m[1])); else outside.push(m[2]);
    }
    if (outside.length) errors.push(`${what}: ${outside.length} record${outside.length === 1 ? '' : 's'} outside ${home} dropped; the first: ${outside[0]}`);
    return sizes;
  };
  const projects = path.join(home, 'projects');
  const others = names.filter(n => n !== 'projects').map(n => path.join(home, n));
  const [entries, tree] = await Promise.all([
    others.length ? du(['-0', '-xsk', '--', ...others], 'home entries') : Promise.resolve(new Map()),
    names.includes('projects') ? du(['-0', '-xk', '--max-depth=3', '--', projects], 'projects') : Promise.resolve(new Map()),
  ]);
  const largest = [...entries].map(([p, kb]) => ({ name: path.basename(p), kb }));
  if (tree.has(projects)) largest.push({ name: 'projects', kb: tree.get(projects) });
  largest.sort((a, b) => b.kb - a.kb);
  const targets = [...tree].filter(([p]) => path.basename(p) === 'target' && !path.relative(projects, path.dirname(p)).split(path.sep).includes('target'))
    .map(([p, kb]) => ({ path: path.relative(home, p), kb })).sort((a, b) => b.kb - a.kb);
  return { status: errors.length ? 'partial' : 'ok', home, total_kb: largest.reduce((n, e) => n + e.kb, 0),
           largest: largest.slice(0, DISK_TOP), targets, targets_kb: targets.reduce((n, t) => n + t.kb, 0),
           ...(errors.length ? { errors } : {}) };
}
