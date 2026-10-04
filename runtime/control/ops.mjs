// runtime/control/ops.mjs — what a control agent can say about its own
// account, as pure extractors: each takes its inputs (a home, a fetch, an
// exec) so a test runs them against a scratch home and a fake relay, and
// each returns only fixed, whitelisted keys — never a value from a secret.
// The fingerprints are the one place a secret is read: hashed in place,
// twelve hex digits of its sha256, enough to tell two keys apart and
// nothing else (the CEO, 2026-09-17: "the username it logs in with, or
// the api key hash").
//
// A section that cannot be read says so inline ({status: ...}) rather than
// throwing: a reply always arrives, and its gaps are named.

import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import crypto from 'node:crypto';
import { execFileSync, execFile } from 'node:child_process';
import { promisify } from 'node:util';
import zlib from 'node:zlib';
import { whoami, findTaxonomy, loadTaxonomy, syncedVar, holdStatus, identity as gzIdentity } from './gzcoord.mjs';
import { jobs } from './jobs.mjs';
import { memoryPressure } from './pressure.mjs';
import { readJson, sha12, execFileP } from './ops/util.mjs';
import { identity, fabric, session, presence } from './ops/identity.mjs';
export { identity, fabric, session, presence } from './ops/identity.mjs';
import { USAGE_URL, usage, ACCOUNTS_TIMEOUT_MS, ACCOUNT_SLUG, accountsDir, takeReadLock, accountSlugs, claudeBin, parseUsageReport, readAccount, accounts, TOKEN_RATIOS, TOKENS_DAYS, equivalent, tokens } from './ops/usage.mjs';
export { USAGE_URL, usage, ACCOUNTS_TIMEOUT_MS, ACCOUNT_SLUG, accountsDir, takeReadLock, accountSlugs, claudeBin, parseUsageReport, readAccount, accounts, TOKEN_RATIOS, TOKENS_DAYS, equivalent, tokens } from './ops/usage.mjs';
import { KEY_NAMES, keys, STORE_ROW, storeRefusal, SIGNING_ROW, signingSecret } from './ops/keys.mjs';
export { KEY_NAMES, keys, STORE_ROW, storeRefusal, SIGNING_ROW, signingSecret } from './ops/keys.mjs';
import { host, DISK_TIMEOUT_MS, DISK_MAX_BUFFER, DISK_TOP, disk } from './ops/host.mjs';
export { host, DISK_TIMEOUT_MS, DISK_MAX_BUFFER, DISK_TOP, disk } from './ops/host.mjs';

export const OPS = ['ping', 'identity', 'usage', 'keys', 'fabric', 'session', 'script', 'recall', 'tokens', 'memory', 'host', 'disk', 'accounts', 'upgrade', 'secrets-sync', 'status', 'presence', 'jobs', 'jobs-add'];

// Answered for any placed account, not only an operator: whether a session
// is running is what every sender needs before it writes to one, and it
// names nothing a relay reader could not already infer (the owner,
// 2026-09-25: presence moves from HELLO/GOODBYE, now retired, to the
// control plane).
export const PUBLIC_OPS = ['presence'];

// Which SCRIPT the account writes in — the signature of the language it
// reasons in. A role that must think in the language it answers for
// (language-culture) leaves exactly one artifact that differs when it
// does not: the letters of its own session records. The harness keeps
// every assistant turn, thinking blocks included, under
// ~/.claude/projects/<launch dir>/<session>.jsonl; this counts the LETTERS
// of those blocks by script (Unicode block: Latin, Georgian, Cyrillic,
// Greek, Arabic, Hebrew, Armenian, CJK, other) and reports shares —
// thinking and visible text apart, since a session that reasons in one
// language and translates its answers shows a low share in thinking and
// a higher one in text. Nothing of the text itself leaves the account:
// counts and percentages only. Records touched in the last `hours`
// (default 24), newest `limit` files (default 5).
//
// Measured 2026-09-17: the reasoning itself is NOT on disk — the API
// returns most thinking blocks with a signature and no text, and the
// ones that carry text are 120–400-character summaries; one session
// with 117k thinking tokens had no stored thinking text at all. So the
// signature the charter names is the holder's NOTES: the directory
// `${XDG_STATE_HOME:-~/.local/state}/agent-fabric/agents/<login>/notes/`,
// where the role keeps the translated request, its working notes and
// the original answer in the locale's language, one file per day. The
// op counts those files (touched in the window) the same way, by
// script, and bins their paragraphs; that is the artifact the holder
// controls and the transcript's text share is the second number.
//
// The CEO's criterion (2026-09-17) is per BLOCK, not per total: most
// thinking blocks must be in the locale's script alone, some will be
// about half and half (a term quoted, a name), and a session that
// reasons in English shows the opposite — so each thinking block is
// also binned by the share of its dominant non-Latin script: `only`
// (≥ 90 %), `mixed` (30–90 %), `latin` (< 30 %), and the bins are
// reported as counts of blocks. `empty` is the block the API returned
// with a signature and no text: measured 2026-09-17 across the fleet,
// most thinking blocks are stored that way (one org: about a fifth
// carry text; the other: none on the same model), so the signature is
// read from the blocks that carry text, and `empty` says how many did
// not — a row of only empties is unmeasured, not clean.
const SCRIPT_RANGES = [
  ['georgian', [[0x10A0, 0x10FF], [0x1C90, 0x1CBF], [0x2D00, 0x2D2F]]],
  ['cyrillic', [[0x0400, 0x052F], [0x2DE0, 0x2DFF], [0xA640, 0xA69F]]],
  ['greek', [[0x0370, 0x03FF], [0x1F00, 0x1FFF]]],
  ['armenian', [[0x0530, 0x058F]]],
  ['hebrew', [[0x0590, 0x05FF]]],
  ['arabic', [[0x0600, 0x06FF], [0x0750, 0x077F], [0x08A0, 0x08FF]]],
  ['cjk', [[0x3040, 0x30FF], [0x4E00, 0x9FFF], [0xAC00, 0xD7AF]]],
  ['latin', [[0x0041, 0x005A], [0x0061, 0x007A], [0x00C0, 0x024F], [0x1E00, 0x1EFF]]],
];

export function scriptCounts(text, counts = {}) {
  for (const ch of text) {
    const cp = ch.codePointAt(0);
    if (cp < 0x41) continue;                      // digits, punctuation, space
    let name = null;
    for (const [n, ranges] of SCRIPT_RANGES) { if (ranges.some(([a, b]) => cp >= a && cp <= b)) { name = n; break; } }
    if (!name) { if (/\p{L}/u.test(ch)) name = 'other'; else continue; }
    counts[name] = (counts[name] ?? 0) + 1;
  }
  return counts;
}

const shares = counts => {
  const total = Object.values(counts).reduce((a, b) => a + b, 0);
  const out = { letters: total };
  for (const [k, v] of Object.entries(counts).sort((a, b) => b[1] - a[1])) out[k] = Math.round(1000 * v / total) / 10;
  return out;
};

// A block (a thinking block, a paragraph) binned by its non-Latin share:
// `only` at 90 %, `mixed` from 30 %, `latin` below, `empty` under 20 letters.
const binInto = (blocks, counts) => {
  const total = Object.values(counts).reduce((a, b) => a + b, 0);
  if (total < 20) { blocks.empty += 1; return; }
  const nonLatin = total - (counts.latin ?? 0) - (counts.other ?? 0);
  const share = nonLatin / total;
  blocks[share >= 0.9 ? 'only' : share >= 0.3 ? 'mixed' : 'latin'] += 1;
};

const paragraphs = (text, counts, blocks, sink) => { for (const para of text.split(/\n\s*\n/)) { const c = scriptCounts(para); binInto(blocks, c); for (const [k, v] of Object.entries(c)) counts[k] = (counts[k] ?? 0) + v; sink?.push(para); } };

// THE LANGUAGE, not only the script (the CEO, 2026-09-17: CLD2). Script
// shares cannot tell English from Italian or Russian from Ukrainian, and
// a single-label classifier cannot see the English inside a Georgian
// paragraph (fastText named a half-and-half paragraph `ka 0.83`); CLD2
// names up to three languages per paragraph with the share of each, and
// says when it is unreliable. The detector runs in the account's own venv
// on the account's own text (runtime/langid/, installed by bootstrap.sh);
// only the verdicts come back. `shares` is the text by language, each
// paragraph's percentages weighted by its letters; `dominant` counts
// paragraphs by their first language; `unreliable` counts the paragraphs
// CLD2 would only guess at (a code line, a two-letter answer, Georgian in
// Latin letters — the script shares still see that one). A paragraph
// under 20 letters is not sent. Without the venv the section says
// `unavailable`, never a guess.
const lettersOf = p => Object.values(scriptCounts(p)).reduce((a, b) => a + b, 0);

export function langidCmd(home = os.homedir(), root = process.env.AGENT_FABRIC_ROOT ?? path.join(home, 'projects', 'agent-fabric')) {
  return [path.join(home, '.cache', 'agent-fabric', 'langid', 'venv', 'bin', 'python'), path.join(root, 'runtime', 'langid', 'langid.py')];
}

export function languages(paragraphs, { home, root, exec = execFileSync } = {}) {
  const judged = paragraphs.filter(p => lettersOf(p) >= 20);
  const [py, script] = langidCmd(home, root);
  if (!fs.existsSync(py)) return { status: 'unavailable', why: 'no detector venv (runtime/langid/install.sh)' };
  if (!judged.length) return { status: 'ok', paragraphs: 0, unreliable: 0, shares: {}, dominant: {} };
  let out;
  try { out = exec(py, [script], { input: JSON.stringify(judged), encoding: 'utf8', maxBuffer: 16 * 1024 * 1024, timeout: 60000 }); }
  catch (e) { return { status: 'unavailable', why: String(e?.stderr ?? e?.message ?? e).trim().split('\n').pop().slice(0, 160) }; }
  let verdicts; try { verdicts = JSON.parse(out); } catch { return { status: 'unavailable', why: 'the detector answered something that is not JSON' }; }
  if (!Array.isArray(verdicts) || verdicts.length !== judged.length) return { status: 'unavailable', why: 'the detector answered for a different number of paragraphs' };
  const weight = {}, dominant = {}; let total = 0, unreliable = 0;
  verdicts.forEach((v, i) => {
    const [reliable, , details] = Array.isArray(v) ? v : [false, 0, []];
    if (!reliable || !Array.isArray(details) || !details.length) { unreliable += 1; return; }
    const n = lettersOf(judged[i]); total += n;
    for (const [code, pct] of details) weight[code] = (weight[code] ?? 0) + n * pct / 100;
    dominant[details[0][0]] = (dominant[details[0][0]] ?? 0) + 1;
  });
  const sorted = o => Object.fromEntries(Object.entries(o).sort((x, y) => y[1] - x[1]));
  const shares = total ? sorted(Object.fromEntries(Object.entries(weight).map(([k, v]) => [k, Math.round(1000 * v / total) / 10]))) : {};
  return { status: 'ok', paragraphs: judged.length, unreliable, shares, dominant: sorted(dominant) };
}

// RECALL — is the corpus read? A drain is instrumented end to end; the
// read-back never was: a slice read is a plain Read in the session's
// record and nothing counted them, so a slice with a poor cue could be
// written and never opened and nobody would know (the owner, 2026-09-20).
// This walks the account's session records in the window — every
// session and its subagents, not the newest five — and counts the tool
// calls that touch the corpus: an index (`INDEX.md` under a project's
// .agent-fabric/memory/<role>/ or the fabric's memory/domains/<x>/), a
// slice (any other .md there, or under memory/shared/), the authored
// identity (identities/roles/<role>/charter|brief|recall.md), and a
// search (Grep/Glob whose path is one of those directories, or a Bash
// command naming one). Counts and paths only — never a line of what was
// read. `sessions_without_recall` is the number that matters: a session
// that opened neither an index nor a slice worked without the corpus.
// Anchored at a path boundary, not at a slash: a session that reads
// `.agent-fabric/memory/<role>/INDEX.md` relative to its working copy —
// the shape every instruction file shows — is reading the corpus.
const CORPUS_RE = /(?:^|\/)(?:\.agent-fabric\/memory\/|memory\/(?:domains|shared)\/)/;

const IDENTITY_RE = /(?:^|\/)identities\/roles\/[a-z0-9-]+\/(?:charter|brief|recall)\.md$/;

export function recallKind(tool, input) {
  const p = typeof input?.file_path === 'string' ? input.file_path : typeof input?.path === 'string' ? input.path : '';
  if (tool === 'Read') {
    if (IDENTITY_RE.test(p)) return { kind: 'identity', path: p };
    if (!CORPUS_RE.test(p) || !/\.md$/.test(p) || /\/README\.md$/.test(p)) return null;   // crossref.json, a drain report, a README: not a slice
    return { kind: /\/INDEX\.md$/.test(p) ? 'index' : 'slice', path: p };
  }
  if (tool === 'Grep' || tool === 'Glob') return CORPUS_RE.test(p) || CORPUS_RE.test(String(input?.pattern ?? '')) ? { kind: 'search', path: p || String(input?.pattern ?? '') } : null;
  if (tool === 'Bash') {
    const m = String(input?.command ?? '').match(/(?:^|[\s'"=])((?:\S*\/)?(?:\.agent-fabric\/memory\/|memory\/(?:domains|shared)\/)\S*)/);
    return m ? { kind: 'search', path: m[1].replace(/["'`;|)]+$/, '') } : null;
  }
  return null;
}

export function recall(home = os.homedir(), { hours = 24, now = Date.now() } = {}) {
  const root = path.join(home, '.claude', 'projects');
  const files = [];
  try {
    for (const d of fs.readdirSync(root)) {
      const dir = path.join(root, d);
      let names; try { names = fs.readdirSync(dir); } catch { continue; }
      for (const n of names) {
        if (n.endsWith('.jsonl')) files.push(path.join(dir, n));
        const subs = path.join(dir, n, 'subagents');
        let inner; try { inner = fs.readdirSync(subs); } catch { continue; }
        for (const a of inner) if (/^agent-.*\.jsonl$/.test(a)) files.push(path.join(subs, a));
      }
    }
  } catch { return { status: 'no-records', hours }; }
  const recent = files.filter(f => { try { return now - fs.statSync(f).mtimeMs <= hours * 3600000; } catch { return false; } });
  if (!recent.length) return { status: 'no-records', hours };
  const counts = { index: 0, slice: 0, search: 0, identity: 0 };
  const slices = {}; let sessions = 0, turns = 0, without = 0;
  const since = now - hours * 3600000;
  for (const f of recent) {
    let body; try { body = fs.readFileSync(f, 'utf8'); } catch { continue; }
    let mine = 0, own = 0;
    // The window applies to each RECORD: a long or resumed session's file
    // is touched today and holds weeks of turns; counting them all
    // inflated reads and turns and let an old index read stand for
    // recent work. A record without a parseable timestamp is inside the
    // window (the file is).
    for (const line of body.split('\n')) {
      if (!line.includes('"assistant"')) continue;
      let d; try { d = JSON.parse(line); } catch { continue; }
      if (d?.type !== 'assistant') continue;
      const ts = Date.parse(d.timestamp); if (Number.isFinite(ts) && ts < since) continue;
      own += 1;
      for (const b of d.message?.content ?? []) {
        if (b?.type !== 'tool_use') continue;
        const r = recallKind(b.name, b.input);
        if (!r) continue;
        counts[r.kind] += 1;
        if (r.kind === 'index' || r.kind === 'slice') { mine += 1; slices[r.path] = (slices[r.path] ?? 0) + 1; }
      }
    }
    if (!own) continue;   // a record with no assistant turn is not a session
    sessions += 1; turns += own;
    if (!mine) without += 1;
  }
  const top = Object.entries(slices).sort((a, b) => b[1] - a[1]).slice(0, 10).map(([p, n]) => ({ path: p.replace(home, '~'), reads: n }));
  return { status: 'ok', hours, sessions, turns, ...counts, sessions_without_recall: without, top };
}

export function notesDir(home = os.homedir(), env = process.env, login = (() => { try { return os.userInfo().username; } catch { return 'unknown'; } })()) {
  return path.join(env.XDG_STATE_HOME ?? path.join(home, '.local', 'state'), 'agent-fabric', 'agents', login, 'notes');
}

export function script(home = os.homedir(), { hours = 24, limit = 5, now = Date.now(), notes = notesDir(home), langid = languages } = {}) {
  const root = path.join(home, '.claude', 'projects');
  let files = [];
  try {
    for (const d of fs.readdirSync(root)) {
      const dir = path.join(root, d);
      let names; try { names = fs.readdirSync(dir); } catch { continue; }
      for (const n of names) {
        if (!n.endsWith('.jsonl')) continue;
        const f = path.join(dir, n);
        let st; try { st = fs.statSync(f); } catch { continue; }
        if (now - st.mtimeMs <= hours * 3600000) files.push({ f, mtime: st.mtimeMs });
      }
    }
  } catch { return { status: 'no-records' }; }
  files.sort((a, b) => b.mtime - a.mtime); files = files.slice(0, limit);
  // The notes: every file under the notes directory touched in the window,
  // its paragraphs binned like thinking blocks.
  const noteCounts = {}; const noteBlocks = { only: 0, mixed: 0, latin: 0, empty: 0 }; let noteFiles = 0; const noteParas = [];
  try {
    for (const n of fs.readdirSync(notes)) {
      const f = path.join(notes, n);
      let st; try { st = fs.statSync(f); } catch { continue; }
      if (!st.isFile() || now - st.mtimeMs > hours * 3600000) continue;
      let body; try { body = fs.readFileSync(f, 'utf8'); } catch { continue; }
      noteFiles += 1;
      paragraphs(body, noteCounts, noteBlocks, noteParas);
    }
  } catch { /* no notes directory: reported as none */ }
  const notesOut = noteFiles ? { status: 'ok', files: noteFiles, ...shares(noteCounts), blocks: noteBlocks, language: langid(noteParas, { home }) } : { status: 'none', dir: notes };
  if (!files.length) return { status: 'no-records', hours, notes: notesOut };
  const thinking = {}, text = {}; let turns = 0;
  const blocks = { only: 0, mixed: 0, latin: 0, empty: 0 };
  const bin = counts => binInto(blocks, counts);
  for (const { f } of files) {
    let body; try { body = fs.readFileSync(f, 'utf8'); } catch { continue; }
    for (const line of body.split('\n')) {
      if (!line.includes('"assistant"')) continue;
      let d; try { d = JSON.parse(line); } catch { continue; }
      if (d?.type !== 'assistant') continue;
      turns += 1;
      for (const b of d.message?.content ?? []) {
        if (b?.type === 'thinking' && typeof b.thinking === 'string') { const c = scriptCounts(b.thinking); bin(c); for (const [k, v] of Object.entries(c)) thinking[k] = (thinking[k] ?? 0) + v; }
        else if (b?.type === 'text' && typeof b.text === 'string') scriptCounts(b.text, text);
      }
    }
  }
  return { status: 'ok', hours, files: files.length, turns, thinking: shares(thinking), thinking_blocks: blocks, text: shares(text), notes: notesOut, workers: workerTranscripts(files, { hours, now, langid: p => langid(p, { home }) }) };
}

// THE WORKERS. A subagent's transcript is stored beside its session's
// (<session>/subagents/agent-*.jsonl) with a sidecar the harness writes,
// agent-*.meta.json, whose agentType names the type dispatched: the
// locale worker of the language-culture bridge
// (identities/roles/language-culture/charter.md) is the one whose sidecar
// says locale-worker — read back 2026-09-17, when "no tool_use block"
// turned out to fit no transcript: the hand-back itself is a tool_use
// (SubagentHandback), and the harness refuses to spawn an agent with no
// tool at all, so the worker carries one inert tool. Its USER records are
// the worker's input, which the bridge composed, less the harness's own
// <system-reminder> spans (English, injected into every subagent, and not
// the bridge's doing): a Latin paragraph left is English reaching the
// worker, the leak the construction exists to prevent. Its assistant text
// is the answer. Any tool_use but the hand-back is counted as tool_uses —
// a worker that used a tool is a worker with one. Paragraphs binned like
// the notes; counts only.
export const WORKER_TYPE = 'locale-worker';

const REMINDER_RE = /<system-reminder>[\s\S]*?(<\/system-reminder>|$)/g;

export function workerTranscripts(files, { hours = 24, now = Date.now(), type = WORKER_TYPE, langid = null } = {}) {
  const input = {}, text = {}; const inputBlocks = { only: 0, mixed: 0, latin: 0, empty: 0 }, textBlocks = { only: 0, mixed: 0, latin: 0, empty: 0 }; const inputParas = [], textParas = [];
  let n = 0, turns = 0, others = 0, toolUses = 0;
  for (const { f } of files) {
    const dir = path.join(path.dirname(f), path.basename(f, '.jsonl'), 'subagents');
    let names; try { names = fs.readdirSync(dir); } catch { continue; }
    for (const name of names) {
      if (!/^agent-.*\.jsonl$/.test(name)) continue;
      const p = path.join(dir, name);
      let st; try { st = fs.statSync(p); } catch { continue; }
      if (now - st.mtimeMs > hours * 3600000) continue;
      let meta = null; try { meta = JSON.parse(fs.readFileSync(p.replace(/\.jsonl$/, '.meta.json'), 'utf8')); } catch { /* no sidecar: not a worker */ }
      if (meta?.agentType !== type) { others += 1; continue; }
      let body; try { body = fs.readFileSync(p, 'utf8'); } catch { continue; }
      n += 1;
      for (const line of body.split('\n')) {
        let d; try { d = JSON.parse(line); } catch { continue; }
        const c = d?.message?.content;
        if (d?.type === 'user') {
          const texts = typeof c === 'string' ? [c] : Array.isArray(c) ? c.filter(b => b?.type === 'text' && typeof b.text === 'string').map(b => b.text) : [];
          for (const t of texts) { const own = t.replace(REMINDER_RE, ''); if (own.trim()) paragraphs(own, input, inputBlocks, inputParas); }
        } else if (d?.type === 'assistant') {
          turns += 1;
          for (const b of Array.isArray(c) ? c : []) {
            if (b?.type === 'text' && typeof b.text === 'string') paragraphs(b.text, text, textBlocks, textParas);
            else if (b?.type === 'tool_use' && b.name !== 'SubagentHandback') toolUses += 1;
          }
        }
      }
    }
  }
  if (!n) return { status: 'none', other_subagents: others };
  return { status: 'ok', files: n, other_subagents: others, turns, tool_uses: toolUses,
           input: { ...shares(input), blocks: inputBlocks, ...(langid ? { language: langid(inputParas) } : {}) }, text: { ...shares(text), blocks: textBlocks, ...(langid ? { language: langid(textParas) } : {}) } };
}

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

export function memoryDirs(home = os.homedir(), projectsDir = path.join(home, 'projects')) {
  const root = path.join(home, '.claude', 'projects');
  let slugs; try { slugs = fs.readdirSync(root); } catch { return []; }
  let copies = []; try { copies = fs.readdirSync(projectsDir).map(d => path.join(projectsDir, d)).filter(d => { try { return fs.statSync(d).isDirectory(); } catch { return false; } }); } catch { /* no projects dir */ }
  const bySlug = new Map(); const ambiguous = new Set();
  for (const d of copies) { const k = memorySlug(d); if (bySlug.has(k)) ambiguous.add(k); else bySlug.set(k, d); }
  const out = [];
  for (const slug of slugs) {
    const memory = path.join(root, slug, 'memory');
    let n = 0; try { n = fs.readdirSync(memory).filter(f => f.endsWith('.md') && f !== 'MEMORY.md').length; } catch { continue; }
    if (!n) continue;
    // Two working copies with one slug (foo.bar and foo-bar): the
    // harness cannot tell them apart and neither can this; named, not guessed.
    out.push({ slug, memory, files: n, working_copy: ambiguous.has(slug) ? null : (bySlug.get(slug) ?? null), ...(ambiguous.has(slug) ? { ambiguous: true } : {}) });
  }
  return out;
}

export async function memory(home = os.homedir(), { root = process.env.AGENT_FABRIC_ROOT ?? path.join(home, 'projects', 'agent-fabric'), exec = execFileP, dirs = memoryDirs(home), all = false, partBytes = MEMORY_PART_BYTES } = {}) {
  const tool = path.join(root, 'tools', 'fabric', 'harvest_memory.py');
  const bundles = [];
  for (const d of dirs) {
    if (!d.working_copy) { bundles.push({ slug: d.slug, files: d.files, status: d.ambiguous ? 'ambiguous-working-copy' : 'no-working-copy' }); continue; }
    // The tar on stdout, the report on stderr: one run gives both.
    const args = [tool, '--bundle', '-', '--memory', d.memory, '--working-copy', d.working_copy, ...(all ? ['--all'] : [])];
    let r;
    try { r = await exec('python3', args, { encoding: 'buffer', maxBuffer: 64 * 1024 * 1024, env: { ...process.env, AGENT_FABRIC_ROOT: root }, timeout: 120000 }); }
    catch (e) { bundles.push({ slug: d.slug, files: d.files, working_copy: d.working_copy, status: 'harvest-failed', error: String(e?.stderr ?? e?.message ?? e).slice(-400) }); continue; }
    const tar = Buffer.from(r.stdout ?? '');
    let report = null;
    try { const j = JSON.parse(String(r.stderr ?? '')); report = { claims: j.claims, counts: j.counts, needs_rendering: j.needs_rendering ?? [], skipped_no_roles_class: j.skipped_no_roles_class ?? [] }; } catch { report = null; }
    const gz = zlib.gzipSync(tar, { level: 9 });
    const b64 = gz.toString('base64');
    const parts = [];
    for (let i = 0; i < b64.length; i += partBytes) parts.push(b64.slice(i, i + partBytes));
    bundles.push({ slug: d.slug, files: d.files, working_copy: d.working_copy, status: 'ok', bytes: tar.length, gzip_bytes: gz.length,
                   sha256: crypto.createHash('sha256').update(tar).digest('hex'), parts: parts.length, report, _parts: parts });
  }
  return { status: 'ok', bundles };
}

// Everything, for `status`; the sections a request names, otherwise.
export async function collect(op, ctx = {}) {
  const wants = op === 'status' ? ['identity', 'usage', 'keys', 'fabric', 'session'] : op === 'tokens' ? ['identity', 'tokens'] : [op];
  const data = {};
  const guard = async (name, fn) => { try { data[name] = await fn(); } catch (e) { data[name] = { status: 'failed', error: String(e?.message ?? e).slice(0, 200) }; } };
  await Promise.all(wants.map(name => {
    if (name === 'identity') return guard(name, () => identity(ctx.home, ctx.who));   // ctx.who unset: whoami() per request, so a rebind shows
    if (name === 'usage') return guard(name, () => ctx.usageCached ? ctx.usageCached() : usage(ctx.home, ctx.fetch));
    if (name === 'keys') return guard(name, async () => [...keys(ctx.home), await signingSecret(ctx.exec), storeRefusal(ctx.home, ctx.storeDir)]);
    if (name === 'fabric') return guard(name, () => fabric(ctx.root, ctx.exec));
    if (name === 'session') return guard(name, () => session(ctx.uid, ctx.exec));
    if (name === 'presence') return guard(name, () => presence(ctx.presenceOpts));
    if (name === 'script') return guard(name, () => script(ctx.home));
    if (name === 'recall') return guard(name, () => recall(ctx.home));
    if (name === 'tokens') return guard(name, () => tokens(ctx.home, ctx.days ? { days: ctx.days } : {}));
    if (name === 'memory') return guard(name, () => memory(ctx.home, { exec: ctx.exec, all: true }));
    // The machine now, and the pressure this daemon sampled up to now (pressure.mjs).
    if (name === 'host') return guard(name, () => ({ ...host(ctx.hostOpts), memory_pressure: memoryPressure(ctx.pressureOpts) }));
    // One scan per daemon however many ask at once (agentd's diskKeeper).
    if (name === 'disk') return guard(name, () => ctx.diskCached ? ctx.diskCached() : disk(ctx.home, ctx.diskOpts));
    if (name === 'jobs') return guard(name, () => jobs({ home: ctx.home, root: ctx.root, ...(ctx.jobsOpts ?? {}) }));
    if (name === 'accounts') return guard(name, () => ctx.accountsCached ? ctx.accountsCached() : accounts(ctx.home, ctx.accountsOpts));
    return Promise.resolve();
  }));
  return data;
}
