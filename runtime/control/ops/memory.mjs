// runtime/control/ops/memory.mjs — the drain over the control plane: the account's own memory, harvested by its own daemon.
// A part of ops.mjs, which re-exports it; ops.mjs's header is the contract
// every extractor here keeps.

import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import crypto from 'node:crypto';
import zlib from 'node:zlib';
import { execFileP } from './util.mjs';


// THE DRAIN, over the control plane (the CEO, 2026-09-17: the way out of
// god mode). Until now a drain read another account's home through sudo
// (bin/fabric-host drain). Here the account's own daemon runs the
// harvester on its own memory — one bundle per memory directory Claude
// Code keeps for it (~/.claude/projects/<slug>/memory), each resolved to
// the working copy it belongs to by matching the slug against the
// account's ~/projects/* — and answers with the bundles gzipped and
// base64, in parts that fit the relay's 128 KiB message limit, plus each
// harvest report (`needs_rendering` and the skipped list included). No
// request field reaches argv: the op takes none. The harvester refuses
// the whole drain when a memory carries a credential by shape
// (harvest_memory.CREDENTIAL_PATTERNS), so no secret reaches the channel;
// a memory directory with no working copy beside it, or with two, is
// named and left where it is.
export const MEMORY_PART_BYTES = 90 * 1024;

// The harness's name for a launch directory: every character that is not
// a letter or a digit becomes `-` — `/` and `.` alike (read back 2026-09-17:
// ~/projects/foo.bar is -home-…-projects-foo-bar). The harvester's
// memory_slug is the same rule.
export function memorySlug(dir) { return path.resolve(dir).replace(/[^A-Za-z0-9]/g, '-'); }

// A session started in ~/projects itself keeps its memory under the
// projects root's slug, which names no working copy: that workspace's
// CLAUDE.md is the fabric's, so its memory is filed under the account's
// fabric checkout, and the row says so (projects_root). Without a checkout
// there it stays a no-working-copy row: reported, never guessed.
export function memoryDirs(home = os.homedir(), projectsDir = path.join(home, 'projects'), fabric = path.join(projectsDir, 'agent-fabric')) {
  const root = path.join(home, '.claude', 'projects');
  let slugs; try { slugs = fs.readdirSync(root); } catch { return []; }
  let copies = []; try { copies = fs.readdirSync(projectsDir).map(d => path.join(projectsDir, d)).filter(d => { try { return fs.statSync(d).isDirectory(); } catch { return false; } }); } catch { /* no projects dir */ }
  const bySlug = new Map(); const ambiguous = new Set();
  for (const d of copies) { const k = memorySlug(d); if (bySlug.has(k)) ambiguous.add(k); else bySlug.set(k, d); }
  const rootSlug = memorySlug(projectsDir);
  let fabricHere = false; try { fabricHere = fs.statSync(fabric).isDirectory(); } catch { /* no checkout */ }
  const out = [];
  for (const slug of slugs) {
    const memory = path.join(root, slug, 'memory');
    let n = 0; try { n = fs.readdirSync(memory).filter(f => f.endsWith('.md') && f !== 'MEMORY.md').length; } catch { continue; }
    if (!n) continue;
    // Two working copies with one slug (foo.bar and foo-bar): the
    // harness cannot tell them apart and neither can this; named, not guessed.
    if (slug === rootSlug && fabricHere) { out.push({ slug, memory, files: n, working_copy: fabric, projects_root: true }); continue; }
    out.push({ slug, memory, files: n, working_copy: ambiguous.has(slug) ? null : (bySlug.get(slug) ?? null), ...(ambiguous.has(slug) ? { ambiguous: true } : {}) });
  }
  return out;
}

export async function memory(home = os.homedir(), { root = process.env.AGENT_FABRIC_ROOT ?? path.join(home, 'projects', 'agent-fabric'), exec = execFileP, dirs = memoryDirs(home, path.join(home, 'projects'), root), all = false, partBytes = MEMORY_PART_BYTES } = {}) {
  const tool = path.join(root, 'tools', 'fabric', 'harvest_memory.py');
  const bundles = [];
  for (const d of dirs) {
    if (!d.working_copy) { bundles.push({ slug: d.slug, files: d.files, status: d.ambiguous ? 'ambiguous-working-copy' : 'no-working-copy' }); continue; }
    // The tar on stdout, the report on stderr: one run gives both.
    const args = [tool, '--bundle', '-', '--memory', d.memory, '--working-copy', d.working_copy, ...(all ? ['--all'] : [])];
    let r;
    try { r = await exec('python3', args, { encoding: 'buffer', maxBuffer: 64 * 1024 * 1024, env: { ...process.env, AGENT_FABRIC_ROOT: root }, timeout: 120000 }); }
    catch (e) { bundles.push({ slug: d.slug, files: d.files, working_copy: d.working_copy, ...(d.projects_root ? { projects_root: true } : {}), status: 'harvest-failed', error: String(e?.stderr ?? e?.message ?? e).slice(-400) }); continue; }
    const tar = Buffer.from(r.stdout ?? '');
    let report = null;
    try { const j = JSON.parse(String(r.stderr ?? '')); report = { claims: j.claims, counts: j.counts, needs_rendering: j.needs_rendering ?? [], skipped_no_roles_class: j.skipped_no_roles_class ?? [] }; } catch { report = null; }
    const gz = zlib.gzipSync(tar, { level: 9 });
    const b64 = gz.toString('base64');
    const parts = [];
    for (let i = 0; i < b64.length; i += partBytes) parts.push(b64.slice(i, i + partBytes));
    bundles.push({ slug: d.slug, files: d.files, working_copy: d.working_copy, ...(d.projects_root ? { projects_root: true } : {}), status: 'ok', bytes: tar.length, gzip_bytes: gz.length,
                   sha256: crypto.createHash('sha256').update(tar).digest('hex'), parts: parts.length, report, _parts: parts });
  }
  return { status: 'ok', bundles };
}
