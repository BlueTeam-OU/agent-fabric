// runtime/control/ops/activity.mjs — what the account did: the script and language it writes in, whether it read the corpus, and its locale workers.
// A part of ops.mjs, which re-exports it; ops.mjs's header is the contract
// every extractor here keeps.

import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { localeDir } from '../roots.mjs';
import { whoami } from '../gzcoord.mjs';


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

// THE SOURCE LOCALE. A holder of the fleet's own language translates
// nothing, and its notes are English by design: they are not measured by
// script (ADR-027 §2, A 2026-10-07), so the op says that instead of
// counts that would read as a measurement. The source is the locale whose
// locale.json carries lint's SOURCE_TAG (tools/fabric/lint_rules/locales.py);
// the holder's locale is the suffix after its login's last dash, as i18n
// reads it. A locale.json that cannot be read is not the source: measured,
// as before this rule.
export const SOURCE_TAG = 'en-US';
export function sourceLocale(who = whoami(), o = {}) {   // unset: per request, so a rebind shows
  if (who?.role !== 'language-culture' || typeof who.agent !== 'string') return false;
  const suffix = who.agent.slice(who.agent.lastIndexOf('-') + 1);
  try { return JSON.parse(fs.readFileSync(path.join(localeDir('language-culture', suffix, o), 'locale.json'), 'utf8'))?.tag === SOURCE_TAG; }
  catch { return false; }
}

export function script(home = os.homedir(), { hours = 24, limit = 5, now = Date.now(), notes = notesDir(home), langid = languages, source = false } = {}) {
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
  } catch { /* no transcript directory: no files, and the notes are still said below */ }
  files.sort((a, b) => b.mtime - a.mtime); files = files.slice(0, limit);
  // The notes: every file under the notes directory touched in the window,
  // its paragraphs binned like thinking blocks.
  const noteCounts = {}; const noteBlocks = { only: 0, mixed: 0, latin: 0, empty: 0 }; let noteFiles = 0; const noteParas = [];
  if (!source) try {
    for (const n of fs.readdirSync(notes)) {
      const f = path.join(notes, n);
      let st; try { st = fs.statSync(f); } catch { continue; }
      if (!st.isFile() || now - st.mtimeMs > hours * 3600000) continue;
      let body; try { body = fs.readFileSync(f, 'utf8'); } catch { continue; }
      noteFiles += 1;
      paragraphs(body, noteCounts, noteBlocks, noteParas);
    }
  } catch { /* no notes directory: reported as none */ }
  const notesOut = source ? { status: 'not measured', reason: 'the source locale' } : noteFiles ? { status: 'ok', files: noteFiles, ...shares(noteCounts), blocks: noteBlocks, language: langid(noteParas, { home }) } : { status: 'none', dir: notes };
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
