// The control agent's extractors, against a scratch home: every section
// says what it knows or why not, and no output ever carries a secret value.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import zlib from 'node:zlib';
import { execFileSync } from 'node:child_process';
import { scratch } from '../../../tests/scratch.mjs';
import { identity, usage, keys, fabric, session, host, script, recall, recallKind, scriptCounts, notesDir, workerTranscripts, languages, langidCmd, memoryDirs, memorySlug, memory, tokens, equivalent, TOKEN_RATIOS, collect, KEY_NAMES, OPS, MEMORY_PART_BYTES, accounts, readAccount, parseUsageReport, accountsDir, accountSlugs, takeReadLock, presence, signingSecret, SIGNING_ROW, storeRefusal, STORE_ROW, disk, DISK_TIMEOUT_MS, DISK_MAX_BUFFER } from '../ops.mjs';
// A fence for any presence() a test forgets to give a hold: never the
// runner's own ~/.cache/agent-fabric/hold (review of #49).
process.env.AGENT_FABRIC_HOLD_DIR = scratch('ops-hold-');

const SECRETS = { OPENROUTER_API_KEY: 'sk-or-v1-abcdefghijklmnopqrstuvwxyz0123456789', GH_TOKEN: 'ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789', CLAUDE_BRIDGE_AUTH_TOKEN: 'bridge-token-value-1234567890' };
const ACCESS = 'oauth-access-token-value-XYZ';
function home() {
  const h = scratch('ctl-home-');
  fs.mkdirSync(path.join(h, '.config', 'agent-fabric'), { recursive: true });
  fs.mkdirSync(path.join(h, '.claude'), { recursive: true });
  fs.writeFileSync(path.join(h, '.config', 'agent-fabric', 'secrets.env'), Object.entries(SECRETS).map(([k, v]) => `export ${k}='${v}'`).join('\n') + '\n');
  fs.writeFileSync(path.join(h, '.claude', '.credentials.json'), JSON.stringify({ claudeAiOauth: { accessToken: ACCESS, refreshToken: 'refresh-XYZ', subscriptionType: 'max' } }));
  fs.writeFileSync(path.join(h, '.claude.json'), JSON.stringify({ oauthAccount: { emailAddress: 'someone@example.org', organizationName: 'Example Org', accountUuid: 'u-1' } }));
  return h;
}
const who = { agent: 'db-admin', host: 'develop-qzapp', role: 'db-admin', project: 'gzapp', working_copy: '/home/db-admin/projects/gzapp' };
function assertNoSecret(obj) {
  const s = JSON.stringify(obj);
  for (const v of [...Object.values(SECRETS), ACCESS, 'refresh-XYZ']) assert.ok(!s.includes(v), `a secret value leaked into the output: ${v.slice(0, 6)}…`);
}

test('identity: the account and the Claude account it is signed into, no secret', () => {
  const h = home();
  const id = identity(h, who);
  assert.deepEqual(id, { agent: 'db-admin', host: 'develop-qzapp', role: 'db-admin', project: 'gzapp', working_copy: '/home/db-admin/projects/gzapp',
                         claude_account: { email: 'someone@example.org', organization: 'Example Org' }, credentials_present: true });
  assertNoSecret(id);
  fs.unlinkSync(path.join(h, '.claude.json'));
  assert.equal(identity(h, who).claude_account, null, 'no profile record: null, not a throw');
});

test('usage: the two windows through the account\'s own token, which goes into one header and nowhere else', async () => {
  const h = home();
  const seen = [];
  const fetchOk = async (url, init) => { seen.push({ url, auth: init.headers.Authorization, beta: init.headers['anthropic-beta'] });
    return { ok: true, status: 200, json: async () => ({ five_hour: { utilization: 12.5, resets_at: '2026-09-17T10:00:00+00:00' }, seven_day: { utilization: 80, resets_at: '2026-09-21T16:00:00+00:00' } }) }; };
  const u = await usage(h, fetchOk);
  assert.deepEqual(u, { status: 'ok', five_hour: { utilization: 12.5, resets_at: '2026-09-17T10:00:00+00:00' }, seven_day: { utilization: 80, resets_at: '2026-09-21T16:00:00+00:00' }, subscription: 'max' });
  assert.equal(seen[0].auth, `Bearer ${ACCESS}`); assert.equal(seen[0].beta, 'oauth-2025-04-20');
  assertNoSecret(u);
  assert.deepEqual(await usage(h, async () => ({ ok: false, status: 401 })), { status: 'read-failed', http: 401 });
  assert.deepEqual(await usage(h, async () => { throw new Error('ECONNREFUSED'); }), { status: 'read-failed' });
  assert.deepEqual(await usage(h, async () => ({ ok: true, status: 200, json: async () => { throw new Error('bad json'); } })), { status: 'unreadable' });
  fs.unlinkSync(path.join(h, '.claude', '.credentials.json'));
  assert.deepEqual(await usage(h, fetchOk), { status: 'no-credentials' });
});

test('signing key secret: asked of the key git signs with, a usable signing key, never a count', async () => {
  const asked = [];
  const KEY = 'ABCDEF0123456789';
  const usable = `sec:u:255:22:${KEY}:1:::::::scSC:::+:::23::0:\nssb:u:255:22:0448AC70CD742422:1::::::s:::+:::23:\n`;
  const stub = `sec:u:255:22:${KEY}:1:::::::cC:::#:::23::0:\nssb:u:255:22:0448AC70CD742422:1::::::s:::#:::23:\n`;
  const exec = (listing, key = KEY) => async (cmd, args) => {
    asked.push([cmd, ...args].join(' '));
    if (cmd === 'git') { if (!key) throw new Error('exit 1'); return { stdout: key + '\n' }; }
    if (cmd === 'gpg' && listing !== null) return { stdout: listing };
    throw new Error('gpg: error reading key: No secret key');
  };
  assert.deepEqual(await signingSecret(exec(usable)), { name: SIGNING_ROW, present: true });
  assert.ok(asked.includes(`gpg --list-secret-keys --with-colons -- ${KEY}`), asked.join('; '));
  assert.deepEqual(await signingSecret(exec(null)), { name: SIGNING_ROW, present: false }, 'the store key alone is not it');
  assert.deepEqual(await signingSecret(exec(stub)), { name: SIGNING_ROW, present: false }, 'a stub cannot sign');
  assert.deepEqual(await signingSecret(exec(usable, '')), { name: SIGNING_ROW, present: false }, 'no signing key configured');
});

test('keys: names and twelve-digit fingerprints, never a value; an absent key says so', () => {
  const h = home();
  const k = keys(h);
  assert.deepEqual(k.map(x => x.name), KEY_NAMES);
  const or = k.find(x => x.name === 'OPENROUTER_API_KEY');
  assert.equal(or.present, true);
  assert.equal(or.sha256_12, crypto.createHash('sha256').update(SECRETS.OPENROUTER_API_KEY).digest('hex').slice(0, 12));
  assert.deepEqual(k.find(x => x.name === 'OPENAI_API_KEY'), { name: 'OPENAI_API_KEY', present: false });
  assertNoSecret(k);
  assert.deepEqual(keys('/nonexistent').map(x => x.present), KEY_NAMES.map(() => false));
});

test('fabric: head, branch, behind, dirty, through a fake git; a fetch that fails is said', async () => {
  const calls = [];
  const exec = (cmd, args) => { calls.push(args.slice(2).join(' '));
    const a = args.slice(2).join(' ');
    if (a.startsWith('rev-parse --short')) return 'abc1234\n';
    if (a.startsWith('rev-parse --abbrev-ref')) return 'main\n';
    if (a.startsWith('status')) return '';
    if (a.startsWith('fetch')) throw new Error('offline');
    if (a.startsWith('rev-list')) return '3\n';
    return ''; };
  assert.deepEqual(await fabric('/some/root', exec), { status: 'ok', root: '/some/root', head: 'abc1234', branch: 'main', dirty: false, fetch: 'failed', behind: 3 });
  assert.equal((await fabric('/no/checkout', () => { throw new Error('not a git repository'); })).status, 'not-a-checkout');
  const asyncExec = async (...a) => ({ stdout: exec(...a) });   // the real execFile shape
  assert.equal((await fabric('/some/root', asyncExec)).head, 'abc1234');
});

test('script: letters by script, thinking and text apart, from the account\'s own session records; nothing of the text leaves', () => {
  assert.deepEqual(scriptCounts('Hello, world! 123'), { latin: 10 });
  assert.deepEqual(scriptCounts('გამარჯობა hello'), { georgian: 9, latin: 5 });
  assert.deepEqual(scriptCounts('привет'), { cyrillic: 6 });
  const h = scratch('script-home-');
  const dir = path.join(h, '.claude', 'projects', '-home-x-projects-demo'); fs.mkdirSync(dir, { recursive: true });
  const turn = (thinking, text) => JSON.stringify({ type: 'assistant', message: { content: [{ type: 'thinking', thinking }, { type: 'text', text }] } });
  const lines = [turn('I think in English about this', 'გამარჯობა — the answer in Georgian, then its rendering'), turn('ვფიქრობ ქართულად', 'ok'),
                 JSON.stringify({ type: 'user', message: { content: 'ignored' } }), 'not json'];
  fs.writeFileSync(path.join(dir, 'live.jsonl'), lines.join('\n') + '\n');
  const old = path.join(dir, 'old.jsonl'); fs.writeFileSync(old, turn('ძველი', 'old') + '\n');
  const past = new Date(Date.now() - 48 * 3600000); fs.utimesSync(old, past, past);
  const s = script(h);
  assert.equal(s.status, 'ok'); assert.equal(s.files, 1, 'a record older than the window is not read'); assert.equal(s.turns, 2);
  assert.equal(s.thinking.letters, 24 + 15); assert.ok(s.thinking.latin > s.thinking.georgian, JSON.stringify(s));
  assert.ok(s.text.georgian > 0 && s.text.latin > 0);
  assert.deepEqual(s.thinking_blocks, { only: 0, mixed: 0, latin: 1, empty: 1 }, 'the English block is latin; the short Georgian one is under the 20-letter floor');
  fs.appendFileSync(path.join(dir, 'live.jsonl'), turn('ვფიქრობ ქართულად და ვწერ ქართულად, ეს ბლოკი მხოლოდ ქართულია', 'x') + '\n' + turn('ნახევარი ქართული ნახევარი and half of it English text', 'x') + '\n');
  assert.deepEqual(script(h).thinking_blocks, { only: 1, mixed: 1, latin: 1, empty: 1 });
  assert.ok(!JSON.stringify(s).includes('answer'), 'no text leaves, only counts');
  assert.equal(script(h, { hours: 72 }).files, 2);
  assert.equal(script('/nonexistent').status, 'no-records');
  // The notes: the signature the holder controls, one file a day in the locale, paragraphs binned.
  assert.equal(s.notes.status, 'none');
  const nd = path.join(h, 'state', 'agent-fabric', 'agents', 'ge', 'notes'); fs.mkdirSync(nd, { recursive: true });
  fs.writeFileSync(path.join(nd, '2026-09-17.md'), 'მოთხოვნა: გადათარგმნილი მოთხოვნა ქართულად, სრული აბზაცი.\n\nჩემი მსჯელობა ქართულად: ეს ტექსტი მხოლოდ ქართულია და საკმაოდ გრძელი.\n\nA paragraph written in English, long enough to count as a block here.\n');
  const fakeLang = paras => ({ status: 'ok', paragraphs: paras.length, unreliable: 0, shares: { ka: 100 }, dominant: { ka: paras.length } });
  assert.equal(script(h, { notes: nd }).notes.language.status, 'unavailable', 'no venv on this scratch home: said, not guessed');
  const withNotes = script(h, { notes: nd, langid: fakeLang });
  assert.deepEqual(withNotes.notes.language, { status: 'ok', paragraphs: 3, unreliable: 0, shares: { ka: 100 }, dominant: { ka: 3 } }, 'every note paragraph reaches the detector');
  assert.equal(withNotes.notes.status, 'ok'); assert.equal(withNotes.notes.files, 1);
  assert.deepEqual(withNotes.notes.blocks, { only: 2, mixed: 0, latin: 1, empty: 0 }, JSON.stringify(withNotes.notes));
  assert.ok(withNotes.notes.georgian > withNotes.notes.latin);
  assert.ok(!JSON.stringify(withNotes).includes('მოთხოვნა'), 'no note text leaves');
  assert.equal(notesDir('/h', { XDG_STATE_HOME: '/st' }, 'ge'), '/st/agent-fabric/agents/ge/notes');
  assert.equal(notesDir('/h', {}, 'ge'), '/h/.local/state/agent-fabric/agents/ge/notes');
  // The workers: the subagent transcripts beside the session whose sidecar names the locale worker; its USER records the input.
  assert.deepEqual(s.workers, { status: 'none', other_subagents: 0 });
  const sub = path.join(dir, 'live', 'subagents'); fs.mkdirSync(sub, { recursive: true });
  const user = c => JSON.stringify({ type: 'user', message: { role: 'user', content: c } });
  const meta = (name, agentType) => fs.writeFileSync(path.join(sub, `${name}.meta.json`), JSON.stringify({ agentType, model: 'opus' }));
  const handback = JSON.stringify({ type: 'assistant', message: { content: [{ type: 'tool_use', id: 't', name: 'SubagentHandback', input: {} }] } });
  const worker = [user('თხოვნა: გადახედე ამ ტექსტს და უპასუხე ქართულად, სრული აბზაცი აქ.'),
                  turn('', 'პასუხი ქართულად, საკმაოდ გრძელი აბზაცი რომ დაითვალოს ბლოკად.'),
                  user([{ type: 'text', text: 'მეორე თხოვნა ქართულად, ისევ საკმაოდ გრძელი აბზაცი, სამოცამდე ასო.' }]),
                  user('<system-reminder>\nYour final report is delivered through SubagentHandback; a plain final message is NOT delivered. Call it now.\n</system-reminder>'),
                  JSON.stringify({ type: 'attachment', attachment: { type: 'x' } }),
                  turn('', 'მეორე პასუხი ქართულად, საკმაოდ გრძელი ტექსტი აქაც.'), handback];
  fs.writeFileSync(path.join(sub, 'agent-aaa.jsonl'), worker.join('\n') + '\n'); meta('agent-aaa', 'locale-worker');
  const reviewer = [user('Repository: /x. Review the range a..b'), JSON.stringify({ type: 'assistant', message: { content: [{ type: 'tool_use', id: 't', name: 'Read', input: {} }] } }), turn('', 'Findings: none.'), handback];
  fs.writeFileSync(path.join(sub, 'agent-bbb.jsonl'), reviewer.join('\n') + '\n'); meta('agent-bbb', 'code-review');
  fs.writeFileSync(path.join(sub, 'agent-nometa.jsonl'), user('a subagent with no sidecar, long enough to be a block') + '\n');
  const w = script(h, { langid: fakeLang }).workers;
  assert.equal(w.input.language.paragraphs, 2); assert.equal(w.text.language.paragraphs, 2);
  assert.equal(w.status, 'ok'); assert.equal(w.files, 1, 'only the sidecar that says locale-worker'); assert.equal(w.other_subagents, 2); assert.equal(w.turns, 3);
  assert.equal(w.tool_uses, 0, 'the hand-back is not a tool use of the worker');
  assert.deepEqual(w.input.blocks, { only: 2, mixed: 0, latin: 0, empty: 0 }, `the injected reminder is not the bridge's input: ${JSON.stringify(w.input)}`);
  assert.deepEqual(w.text.blocks, { only: 2, mixed: 0, latin: 0, empty: 0 });
  assert.equal(w.input.georgian, 100); assert.ok(w.input.letters > 0);
  assert.ok(!JSON.stringify(w).includes('თხოვნა'), 'no worker text leaves');
  // English reaching the worker is counted in the INPUT bins, from the user records — not from the answers; a real tool use is counted.
  fs.appendFileSync(path.join(sub, 'agent-aaa.jsonl'), user('A paragraph of English that the bridge let through to the worker.') + '\n' + JSON.stringify({ type: 'assistant', message: { content: [{ type: 'tool_use', id: 'u', name: 'TaskStop', input: {} }] } }) + '\n' + turn('', 'მოკლე პასუხი ქართულად, საკმაოდ გრძელი რომ ბლოკი გამოვიდეს.') + '\n');
  const leak = script(h).workers;
  assert.deepEqual(leak.input.blocks, { only: 2, mixed: 0, latin: 1, empty: 0 }, 'the leak is one latin input block');
  assert.deepEqual(leak.text.blocks, { only: 3, mixed: 0, latin: 0, empty: 0 }, 'the answers stay Georgian');
  assert.equal(leak.tool_uses, 1);
  const stale = path.join(sub, 'agent-ccc.jsonl'); fs.writeFileSync(stale, user('old English input, long enough to be a block') + '\n'); meta('agent-ccc', 'locale-worker'); fs.utimesSync(stale, past, past);
  assert.equal(script(h).workers.files, 1, 'a worker transcript older than the window is not read');
  assert.deepEqual(workerTranscripts([{ f: '/nonexistent/s.jsonl' }]), { status: 'none', other_subagents: 0 });
});

// The drain over the control plane: the account's own memory directories,
// each matched to the working copy it was written from, harvested by the
// account's own harvester and answered as a gzipped bundle in relay-sized
// parts with the report beside it. Nothing of a memory's text is in the
// reply but the bundle itself.
test('memoryDirs: every memory directory with a memory in it, matched to ~/projects/<wc> by slug; MEMORY.md alone is nothing', () => {
  const h = scratch('mem-home-');
  const wc = path.join(h, 'projects', 'gzapp'); fs.mkdirSync(wc, { recursive: true });
  const dotted = path.join(h, 'projects', 'gzapi.ge'); fs.mkdirSync(dotted, { recursive: true });
  fs.mkdirSync(path.join(h, 'projects', 'agent-fabric'), { recursive: true });
  fs.writeFileSync(path.join(h, 'projects', 'notes.txt'), 'not a working copy');
  const mem = slug => { const d = path.join(h, '.claude', 'projects', slug, 'memory'); fs.mkdirSync(d, { recursive: true }); return d; };
  fs.writeFileSync(path.join(mem(memorySlug(wc)), 'fact.md'), '---\nname: fact\n---\nx');
  fs.writeFileSync(path.join(mem(memorySlug(wc)), 'MEMORY.md'), '- index');
  fs.writeFileSync(path.join(mem('-home-elsewhere-old-checkout'), 'stray.md'), 'x');
  fs.writeFileSync(path.join(mem(memorySlug(dotted)), 'brand.md'), 'x');
  fs.writeFileSync(path.join(mem(memorySlug(path.join(h, 'projects', 'agent-fabric'))), 'MEMORY.md'), '- only the index');
  fs.mkdirSync(path.join(h, '.claude', 'projects', '-no-memory-dir'), { recursive: true });
  const ds = memoryDirs(h).sort((a, b) => a.slug.localeCompare(b.slug));
  assert.deepEqual(ds, [
    { slug: '-home-elsewhere-old-checkout', memory: path.join(h, '.claude', 'projects', '-home-elsewhere-old-checkout', 'memory'), files: 1, working_copy: null },
    { slug: memorySlug(dotted), memory: path.join(h, '.claude', 'projects', memorySlug(dotted), 'memory'), files: 1, working_copy: dotted },
    { slug: memorySlug(wc), memory: path.join(h, '.claude', 'projects', memorySlug(wc), 'memory'), files: 1, working_copy: wc },
  ]);
  assert.ok(memorySlug(dotted).endsWith('-projects-gzapi-ge'), 'the dotted copy is matched under the harness\'s spelling');
  assert.deepEqual(memoryDirs('/nonexistent'), []);
  fs.mkdirSync(path.join(h, 'projects', 'gzapi-ge'), { recursive: true });   // the same slug as gzapi.ge
  const amb = memoryDirs(h).find(d => d.slug === memorySlug(dotted));
  assert.deepEqual({ wc: amb.working_copy, ambiguous: amb.ambiguous }, { wc: null, ambiguous: true }, 'two working copies with one slug: neither is guessed');
  assert.equal(memorySlug('/home/x/projects/gzapp'), '-home-x-projects-gzapp');
  assert.equal(memorySlug('/home/x/projects/gzapp.decks'), '-home-x-projects-gzapp-decks', 'a dot is a dash too, as the harness names it');
  assert.equal(memorySlug('/home/x/.claude-mem'), '-home-x--claude-mem');
});

test('memoryDirs: the projects root\'s own memory is filed under the fabric checkout, marked; with none there it stays a no-working-copy row', () => {
  const h = scratch('mem-root-');
  const projects = path.join(h, 'projects'); const fabric = path.join(projects, 'agent-fabric');
  fs.mkdirSync(fabric, { recursive: true });
  const d = path.join(h, '.claude', 'projects', memorySlug(projects), 'memory'); fs.mkdirSync(d, { recursive: true });
  fs.writeFileSync(path.join(d, 'fact.md'), '---\nname: fact\n---\nx');
  assert.deepEqual(memoryDirs(h), [{ slug: memorySlug(projects), memory: d, files: 1, working_copy: fabric, projects_root: true }]);
  const elsewhere = path.join(h, 'checkouts', 'fabric'); fs.mkdirSync(elsewhere, { recursive: true });
  assert.equal(memoryDirs(h, projects, elsewhere)[0].working_copy, elsewhere, 'the checkout the op runs from, wherever it is');
  fs.rmSync(fabric, { recursive: true });
  assert.deepEqual(memoryDirs(h), [{ slug: memorySlug(projects), memory: d, files: 1, working_copy: null }], 'no checkout: not guessed');
});

test('memory: the projects root\'s store is harvested as its own (--store projects-root), the checkout\'s as before', async () => {
  const calls = [];
  const exec = async (cmd, args) => { calls.push(args); return { stdout: Buffer.from('x'), stderr: Buffer.from('{}') }; };
  const dirs = [{ slug: 's-root', memory: '/m/root', files: 1, working_copy: '/h/projects/agent-fabric', projects_root: true },
                { slug: 's-fab', memory: '/m/fab', files: 1, working_copy: '/h/projects/agent-fabric' }];
  const m = await memory('/h', { root: '/r', exec, dirs });
  assert.equal(m.bundles[0].projects_root, true);
  assert.deepEqual(calls[0].slice(calls[0].indexOf('--store'), calls[0].indexOf('--store') + 2), ['--store', 'projects-root']);
  assert.ok(!calls[1].includes('--store'), 'the checkout\'s own store keeps its key');
});

test('memory: one harvester run per directory — the tar from stdout, the report from stderr — gzipped, base64, in parts; a failure and a strayed directory are rows, not throws', async () => {
  const tar = crypto.randomBytes(3000);   // incompressible: the parts are real
  const report = { role: 'db-admin', claims: 2, counts: { in_scope: 3, total: 3 }, needs_rendering: ['ka-note'], skipped_no_roles_class: ['private'], memory_dir: '/never/leaves' };
  const calls = [];
  const exec = async (cmd, args, opts) => { calls.push({ cmd, args, opts });
    if (args.includes('/m/broken')) throw Object.assign(new Error('exit 1'), { stderr: 'harvest_memory: refusing rather than guessing where these belong:\n  private-secret.md' });
    return { stdout: tar, stderr: Buffer.from(JSON.stringify(report)) }; };
  const dirs = [{ slug: 's-gzapp', memory: '/m/gzapp', files: 3, working_copy: '/home/x/projects/gzapp' },
                { slug: 's-stray', memory: '/m/stray', files: 1, working_copy: null },
                { slug: 's-broken', memory: '/m/broken', files: 1, working_copy: '/home/x/projects/broken' }];
  const m = await memory('/home/x', { root: '/r', exec, dirs, all: true, partBytes: 1000 });
  assert.equal(m.status, 'ok'); assert.equal(m.bundles.length, 3);
  const [ok, stray, broken] = m.bundles;
  assert.equal(ok.status, 'ok'); assert.equal(ok.bytes, 3000); assert.equal(ok.sha256, crypto.createHash('sha256').update(tar).digest('hex'));
  assert.ok(ok.parts >= 4 && ok._parts.length === ok.parts, `${ok.parts} parts of 1000 chars for ~4 KB of base64`);
  assert.ok(ok._parts.every((p, i) => p.length === 1000 || i === ok._parts.length - 1));
  assert.deepEqual(zlib.gunzipSync(Buffer.from(ok._parts.join(''), 'base64')), tar, 'the parts reassemble to the tar');
  assert.deepEqual(ok.report, { claims: 2, counts: { in_scope: 3, total: 3 }, needs_rendering: ['ka-note'], skipped_no_roles_class: ['private'] });
  assert.ok(!('memory_dir' in ok.report), 'only the whitelisted report keys travel');
  assert.deepEqual(stray, { slug: 's-stray', files: 1, status: 'no-working-copy' });
  assert.equal(broken.status, 'harvest-failed'); assert.match(broken.error, /refusing rather than guessing/);
  assert.equal(calls.length, 2, 'one run per harvestable directory, none for the stray');
  assert.equal(calls[0].cmd, 'python3'); assert.equal(calls[0].args[0], '/r/tools/fabric/harvest_memory.py');
  assert.deepEqual(calls[0].args.slice(1), ['--bundle', '-', '--memory', '/m/gzapp', '--working-copy', '/home/x/projects/gzapp', '--all']);
  assert.equal(calls[0].opts.env.AGENT_FABRIC_ROOT, '/r');
  const noAll = []; await memory('/home/x', { root: '/r', exec: async (c, a) => { noAll.push(a); return { stdout: tar, stderr: 'not json' }; }, dirs: [dirs[0]] });
  assert.ok(!noAll[0].includes('--all'), 'the watermark applies unless asked'); 
  assert.equal(MEMORY_PART_BYTES, 90 * 1024, 'under the relay\'s 128 KiB message limit with the envelope');
  const whole = await memory('/home/x', { root: '/r', exec, dirs: [dirs[0]] });
  assert.equal(whole.bundles[0].parts, 1, 'a 3 KB tar is one part at the real size');
});

test('languages: CLD2 judges only paragraphs of twenty letters; shares weighted by letters, dominant per paragraph, unreliable counted; no venv is unavailable', () => {
  const h = scratch('lang-home-');
  assert.equal(languages(['ქართული აბზაცი საკმაოდ გრძელი'], { home: h }).status, 'unavailable');
  const venvPy = langidCmd(h, '/r')[0]; fs.mkdirSync(path.dirname(venvPy), { recursive: true }); fs.writeFileSync(venvPy, '');
  assert.equal(langidCmd(h, '/r')[1], '/r/runtime/langid/langid.py');
  const seen = [];
  const paras = ['ქართული აბზაცი, საკმაოდ გრძელი რომ განისაჯოს', 'An English paragraph long enough to be judged here', 'ops.mjs:294 memory() exec harvest --bundle -', 'ნახევარი ქართული ნახევარი and half of it English text', 'ok'];
  const exec = (cmd, args, opts) => { seen.push({ cmd, args, input: JSON.parse(opts.input) }); return JSON.stringify([[true, 90, [['ka', 100]]], [true, 50, [['en', 98]]], [false, 40, []], [true, 60, [['ka', 56], ['en', 43]]]]); };
  const l = languages(paras, { home: h, root: '/r', exec });
  assert.equal(l.status, 'ok'); assert.equal(l.paragraphs, 4); assert.equal(l.unreliable, 1);
  assert.deepEqual(l.dominant, { ka: 2, en: 1 });
  assert.ok(l.shares.ka > l.shares.en && l.shares.ka + l.shares.en > 95 && l.shares.ka + l.shares.en <= 100, JSON.stringify(l.shares));
  assert.deepEqual(Object.keys(l.shares), ['ka', 'en'], 'sorted by share');
  assert.equal(seen[0].cmd, venvPy); assert.deepEqual(seen[0].args, ['/r/runtime/langid/langid.py']); assert.equal(seen[0].input.length, 4, 'the two-letter answer is not sent');
  assert.deepEqual(languages([], { home: h, root: '/r', exec }), { status: 'ok', paragraphs: 0, unreliable: 0, shares: {}, dominant: {} });
  assert.equal(languages([paras[1]], { home: h, root: '/r', exec: () => { throw Object.assign(new Error('x'), { stderr: 'langid: no pycld2 in this interpreter (runtime/langid/install.sh)\n' }); } }).why, 'langid: no pycld2 in this interpreter (runtime/langid/install.sh)');
  assert.equal(languages([paras[1]], { home: h, root: '/r', exec: () => 'nope' }).status, 'unavailable');
  assert.equal(languages([paras[1]], { home: h, root: '/r', exec: () => '[]' }).status, 'unavailable', 'a verdict count that does not match is not read');
});

test('session: counts the harness processes of the uid; none is zero, not a throw', () => {
  const s = session(4242, (cmd, args) => { assert.deepEqual(args, ['-u', '4242', '-x', 'claude']); return '111\n222\n'; });
  assert.equal(s.claude_processes, 2); assert.equal(typeof s.planning, 'boolean');
  assert.equal(session(4242, () => { throw Object.assign(new Error('no match'), { status: 1 }); }).claude_processes, 0);
});

test('tokens: per model from the login\'s own records — deduplicated by request, in the window by timestamp, direct and broker apart, subagents counted, synthetic dropped; nothing of the text leaves', async () => {
  const h = home();
  const now = Date.parse('2026-09-19T12:00:00Z');
  const day = 86400000;
  const proj = path.join(h, '.claude', 'projects', '-home-x-projects-gzapp');
  const sub = path.join(proj, 's1', 'subagents');
  fs.mkdirSync(sub, { recursive: true });
  const rec = (ts, model, u, extra = {}) => JSON.stringify({ type: 'assistant', timestamp: new Date(ts).toISOString(), requestId: extra.req, message: { id: extra.id ?? 'm-' + Math.random(), model, usage: u, content: [{ type: 'text', text: 'SECRET-TEXT-NEVER-COUNTED' }] } }) + '\n';
  const u1 = { input_tokens: 10, cache_creation_input_tokens: 100, cache_read_input_tokens: 1000, output_tokens: 20 };
  fs.writeFileSync(path.join(proj, 's1.jsonl'),
    rec(now - day, 'claude-opus-5', u1, { req: 'r1' }) +
    rec(now - day, 'claude-opus-5', u1, { req: 'r1' }) +          // the same request, one record per content block
    rec(now - 2 * day, 'z-ai/glm-5.3', { input_tokens: 500, output_tokens: 5 }, { req: 'r2' }) +
    rec(now - 30 * day, 'claude-opus-5', u1, { req: 'r-old' }) +   // outside the window by its own timestamp
    rec(now - day, '<synthetic>', { input_tokens: 0, output_tokens: 0 }, { req: 'r-syn' }) +
    JSON.stringify({ type: 'user', message: { content: 'hi' } }) + '\nnot json\n');
  fs.writeFileSync(path.join(sub, 'agent-a1.jsonl'), rec(now - day, 'claude-sonnet-5', { input_tokens: 1, cache_read_input_tokens: 50, output_tokens: 7 }, { id: 'msg-sub' }));
  const stale = path.join(proj, 'old.jsonl');
  fs.writeFileSync(stale, rec(now - day, 'claude-opus-5', u1, { req: 'r-stale' }));
  fs.utimesSync(stale, new Date(now - 40 * day), new Date(now - 40 * day));   // a file older than the window is not read
  const t = tokens(h, { now });
  assert.equal(t.status, 'ok');
  assert.equal(t.days, 7);
  assert.deepEqual(t.requests, { session: 2, subagent: 1 });
  assert.deepEqual(Object.keys(t.models), ['z-ai/glm-5.3', 'claude-opus-5', 'claude-sonnet-5'], 'ordered by equivalents (525, 335, 41), synthetic absent');
  assert.deepEqual(t.models['claude-opus-5'], { requests: 1, input: 10, cache_write: 100, cache_read: 1000, output: 20, equiv: 335, path: 'claude' });
  assert.equal(equivalent({ input: 10, cache_write: 100, cache_read: 1000, output: 20 }), 10 + 125 + 100 + 100);
  assert.deepEqual(t.models['z-ai/glm-5.3'], { requests: 1, input: 500, cache_write: 0, cache_read: 0, output: 5, equiv: 525, path: 'broker' });
  assert.deepEqual(t.claude, { requests: 2, input: 11, cache_write: 100, cache_read: 1050, output: 27, equiv: 335 + 41 });
  assert.deepEqual(t.broker, { requests: 1, input: 500, cache_write: 0, cache_read: 0, output: 5, equiv: 525 });
  assert.equal(t.ratios, TOKEN_RATIOS);
  assert.equal(t.first, new Date(now - 2 * day).toISOString()); assert.equal(t.last, new Date(now - day).toISOString());
  assert.ok(!JSON.stringify(t).includes('SECRET-TEXT'), 'counts only');
  assert.equal(tokens(h, { now, days: 0.5 }).status, 'no-records', 'a narrower window with nothing in it says so');
  assert.equal(tokens(scratch('ctl-empty-')).status, 'no-records');
  const c = await collect('tokens', { home: h, who, days: 3 });
  assert.deepEqual(Object.keys(c).sort(), ['identity', 'tokens'], 'tokens rides with identity, so the coordinator can group by Claude account');
  assert.equal(c.tokens.days, 3);
});

test('collect: status is every section, a single op its own, and a failing section is inline', async () => {
  const h = home();
  const calls = [];
  const ctx = { home: h, who, fetch: async () => ({ ok: true, status: 200, json: async () => ({}) }), root: '/r', exec: (cmd, args) => { calls.push([cmd, ...args].join(' ')); throw new Error('boom'); }, uid: 1 };
  const all = await collect('status', ctx);
  assert.deepEqual(Object.keys(all).sort(), ['fabric', 'identity', 'keys', 'session', 'usage']);
  assert.equal(all.fabric.status, 'not-a-checkout');
  assert.equal(all.session.claude_processes, 0);
  assertNoSecret(all);
  calls.length = 0;
  const one = await collect('keys', ctx);
  assert.deepEqual(Object.keys(one), ['keys']);
  // ctx.exec throws: the probe reads absent and never reaches a real git or
  // gpg (review of #89: the keyring of whoever runs the suite). Absent
  // alone cannot show that — the real binaries read absent too where no
  // key is set — so the probe's question is asked of ctx.exec, recorded.
  assert.deepEqual(one.keys.find(k => k.name === SIGNING_ROW), { name: SIGNING_ROW, present: false });
  assert.deepEqual(calls, ['git config --global user.signingkey'], 'the signing probe went through ctx.exec');
  assert.ok(OPS.includes('ping') && OPS.includes('status') && OPS.includes('memory'));
  assert.ok(!('memory' in all), 'a drain is asked for, never part of status');
  const mem = await collect('memory', { home: h, exec: () => { throw new Error('never runs'); } });
  assert.deepEqual(mem, { memory: { status: 'ok', bundles: [] } }, 'a home with no memory answers an empty drain');
});

test('host: the machine from a scratch /proc and /sys — load, memory, the balloon, disks once per device, leases probed with flock, the largest processes; nothing but numbers, logins and program names', () => {
  const root = scratch('ctl-host-');
  const proc = path.join(root, 'proc'), sys = path.join(root, 'sys'), leases = path.join(root, 'leases');
  fs.mkdirSync(proc); fs.mkdirSync(leases, { recursive: true });
  fs.writeFileSync(path.join(proc, 'loadavg'), '3.37 3.44 3.22 5/1200 999\n');
  fs.writeFileSync(path.join(proc, 'meminfo'), 'MemTotal:       31563000 kB\nMemFree:         9750000 kB\nMemAvailable:   21901000 kB\nSwapTotal:       9437176 kB\nSwapFree:        9437176 kB\n');
  // two mounts of one device (/ and /usr/lib/modules) and one of another: two rows
  fs.writeFileSync(path.join(proc, 'mounts'), '/dev/mapper/dmroot / ext4 rw 0 0\nnone /usr/lib/modules ext4 ro 0 0\n/dev/mapper/dmroot /usr/lib/modules ext4 ro 0 0\n/dev/xvdb /rw ext4 rw 0 0\ntmpfs /run tmpfs rw 0 0\n');
  const xm = path.join(sys, 'devices', 'system', 'xen_memory', 'xen_memory0'); fs.mkdirSync(path.join(xm, 'info'), { recursive: true });
  fs.writeFileSync(path.join(xm, 'target_kb'), '31900000\n'); fs.writeFileSync(path.join(xm, 'info', 'current_kb'), '31899000\n');
  fs.writeFileSync(path.join(leases, 'backend-test'), 'db-admin 4242 2026-09-19T08:26:43Z backend-test (suite)\n');
  fs.writeFileSync(path.join(leases, 'free-one'), 'user 1 2026-09-19T00:00:00Z free-one\n');
  fs.writeFileSync(path.join(leases, '.lock'), '');
  fs.writeFileSync(path.join(leases, 'not a lease; $(id)'), 'x 1 t n\n');   // outside fabric-lease's name grammar: never probed
  const calls = [];
  const exec = (cmd, args, opts = {}) => {
    calls.push([cmd, ...args, opts.stdio?.[3] != null ? fs.readlinkSync(`/proc/self/fd/${opts.stdio[3]}`) : null]);
    if (cmd === 'xenstore-read') return '31916000\n';
    if (cmd === 'ps') return 'USER PID RSS COMMAND\nbackend-dev-02 667140 2191360 VBCSCompiler\np2p-network-dev-01 674834 159744 rustc\n';
    if (cmd === 'flock') { const target = fs.readlinkSync(`/proc/self/fd/${opts.stdio[3]}`); if (target.endsWith('backend-test') || target.endsWith('big-one')) { const e = new Error('held'); e.status = 1; throw e; } return ''; }
    throw new Error('unexpected ' + cmd);
  };
  const statfs = mnt => ({ bsize: 4096, blocks: mnt === '/rw' ? 77332480 : 10485760, bavail: mnt === '/rw' ? 22020096 : 5505024 });
  // A fifo with no writer under a grammar-conforming name, and a symlink:
  // neither hangs the probe nor becomes a row (O_NONBLOCK, O_NOFOLLOW, fstat).
  execFileSync('mkfifo', [path.join(leases, 'a-fifo')]);
  fs.symlinkSync(path.join(leases, 'backend-test'), path.join(leases, 'a-link'));
  // a record grown past the bound: only the first line's first 256 bytes are read
  fs.writeFileSync(path.join(leases, 'big-one'), 'db-admin 7 2026-09-19T00:00:00Z big-one' + ' '.repeat(5000) + '\n' + 'x'.repeat(100000));
  const before = fs.readdirSync('/proc/self/fd').length;
  const h = host({ proc, sys, leases, exec, cpus: 6, statfs });
  assert.equal(fs.readdirSync('/proc/self/fd').length, before, 'every probed descriptor is closed, on the held path and the free path alike');
  assert.equal(h.status, 'ok'); assert.equal(h.cpus, 6);
  assert.deepEqual(h.loadavg, [3.37, 3.44, 3.22]);
  assert.deepEqual(h.mem_mb, { total: 30823, available: 21388, swap_total: 9216, swap_free: 9216 });
  assert.deepEqual(h.balloon_mb, { current: 31151, target: 31152, static_max: 31168 });
  assert.deepEqual(h.disk.map(d => d.mount), ['/', '/rw'], 'one row per block device, tmpfs and none excluded');
  assert.deepEqual(h.disk[1], { mount: '/rw', size_gb: 295, avail_gb: 84, use_pct: 72 });
  assert.deepEqual(h.leases, [{ name: 'backend-test', holder: 'db-admin', pid: 4242, since: '2026-09-19T08:26:43Z', label: 'suite' }, { name: 'big-one', holder: 'db-admin', pid: 7, since: '2026-09-19T00:00:00Z', label: null }], 'the held leases only; the free one, the dotfile, the fifo, the symlink and the name outside the grammar are not rows; the grown record is read bounded');
  assert.ok(!calls.some(c => c[0] === 'flock' && (String(c[4]).endsWith('/a-fifo') || String(c[4]).endsWith('/a-link'))), 'a fifo or a symlink never reaches flock');
  assert.ok(!calls.some(c => c[0] === 'flock' && String(c[4]).includes('not a lease')), 'a name outside the grammar never reaches the probe');
  assert.ok(calls.some(c => c[0] === 'flock' && c[1] === '-s' && c[2] === '-n' && c[3] === '3' && String(c[4]).endsWith('/backend-test')), 'the probe hands flock an already-open read-only descriptor as fd 3 and asks for a SHARED lock — no shell, no O_CREAT, never the exclusive lock a caller needs');
  // a file the probe cannot open is not a lease row, and flock is never asked about it
  fs.chmodSync(path.join(leases, 'free-one'), 0o000);
  if (process.getuid() !== 0) {
    calls.length = 0;
    const unreadable = host({ proc, sys, leases, exec, cpus: 6, statfs });
    assert.ok(!calls.some(c => String(c[4]).endsWith('/free-one')), 'an unopenable file never reaches flock');
    assert.deepEqual(unreadable.leases.map(l => l.name), ['backend-test', 'big-one']);
  }
  fs.chmodSync(path.join(leases, 'free-one'), 0o644);
  // half a balloon in sysfs: the missing half is null, never 0
  fs.rmSync(path.join(xm, 'info', 'current_kb'));
  const half = host({ proc, sys, leases, exec, cpus: 6, statfs });
  assert.equal(half.balloon_mb.current, null); assert.equal(half.balloon_mb.target, 31152);
  fs.writeFileSync(path.join(xm, 'info', 'current_kb'), '31899000\n');
  assert.deepEqual(h.top_rss[0], { user: 'backend-dev-02', pid: 667140, rss_mb: 2140, comm: 'VBCSCompiler' });
  assert.equal(JSON.stringify(h).includes('/home/'), false, 'no path of a home in the record');
  // not a Xen guest, no lease directory, no ps: null and empty, never a throw
  const bare = host({ proc, sys: path.join(root, 'nosys'), leases: path.join(root, 'noleases'), exec: () => { throw new Error('no such command'); }, cpus: 2, statfs });
  assert.equal(bare.balloon_mb, null); assert.deepEqual(bare.leases, []); assert.deepEqual(bare.top_rss, []);
  assert.ok(OPS.includes('host'));
});

test('recall: the corpus reads in the account\'s session records — index, slice, search, identity — and the sessions that read none; paths only', () => {
  const h = scratch('recall-home-');
  const dir = path.join(h, '.claude', 'projects', '-home-x-projects-demo'); fs.mkdirSync(dir, { recursive: true });
  const fresh = new Date().toISOString(), stale = new Date(Date.now() - 72 * 3600000).toISOString();
  const use = (name, input, timestamp = fresh) => JSON.stringify({ type: 'assistant', timestamp, message: { content: [{ type: 'tool_use', name, input }] } });
  const say = (text, timestamp = fresh) => JSON.stringify({ type: 'assistant', timestamp, message: { content: [{ type: 'text', text }] } });
  const wc = `${h}/projects/demo`, fab = `${h}/projects/agent-fabric`;
  // Session one: reads its index, two slices (one twice), greps the domain
  // directory, cats a slice from bash, reads its charter — and a file that
  // is none of these.
  fs.writeFileSync(path.join(dir, 'one.jsonl'), [
    say('hello'),
    use('Read', { file_path: `${wc}/.agent-fabric/memory/backend-dev/INDEX.md` }),
    use('Read', { file_path: `${wc}/.agent-fabric/memory/backend-dev/solution/auth.md` }),
    use('Read', { file_path: `${wc}/.agent-fabric/memory/backend-dev/solution/auth.md` }),
    use('Read', { file_path: `${fab}/memory/domains/backend-dev/domain/idempotency.md` }),
    use('Grep', { pattern: 'outbox', path: `${fab}/memory/domains/backend-dev` }),
    use('Grep', { pattern: `outbox-pattern-only ${wc}/.agent-fabric/memory/backend-dev` }),
    use('Read', { file_path: `${wc}/.agent-fabric/memory/backend-dev/crossref.json` }),
    use('Read', { file_path: `${wc}/.agent-fabric/memory/last-drain-report.json` }),
    use('Bash', { command: `sed -n 1,40p ${wc}/.agent-fabric/memory/backend-dev/workflow.md` }),
    use('Read', { file_path: `${fab}/identities/roles/backend-dev/charter.md` }),
    use('Read', { file_path: `${wc}/src/main.rs` }),
    // Repository-relative paths — the shape every instruction file shows.
    use('Read', { file_path: '.agent-fabric/memory/backend-dev/INDEX.md' }),
    use('Read', { file_path: 'memory/domains/backend-dev/domain/idempotency.md' }),
    // A long session's file is touched today and holds older turns: the
    // window applies to the record, so these two count for nothing.
    say('weeks ago', stale),
    use('Read', { file_path: `${wc}/.agent-fabric/memory/backend-dev/solution/auth.md` }, stale),
    'not json',
  ].join('\n') + '\n');
  // Session two: worked without the corpus. A subagent record beside it
  // read a slice; it counts as its own session.
  fs.writeFileSync(path.join(dir, 'two.jsonl'), [say('x'), use('Read', { file_path: `${wc}/README.md` })].join('\n') + '\n');
  const subs = path.join(dir, 'two', 'subagents'); fs.mkdirSync(subs, { recursive: true });
  fs.writeFileSync(path.join(subs, 'agent-1.jsonl'), use('Read', { file_path: `${fab}/memory/shared/domain-x.md` }) + '\n');
  // A record older than the window is not read.
  const old = path.join(dir, 'old.jsonl'); fs.writeFileSync(old, use('Read', { file_path: `${wc}/.agent-fabric/memory/backend-dev/INDEX.md` }) + '\n');
  const past = new Date(Date.now() - 48 * 3600000); fs.utimesSync(old, past, past);

  const r = recall(h);
  assert.equal(r.status, 'ok');
  assert.equal(r.sessions, 3, 'two sessions and one subagent record');
  assert.equal(r.turns, 14 + 2 + 1, 'the two stale records are outside the window');
  assert.deepEqual({ index: r.index, slice: r.slice, search: r.search, identity: r.identity }, { index: 2, slice: 5, search: 3, identity: 1 },
    'relative paths count; the crossref and the drain report are not slices; a grep naming a corpus directory only in its pattern is a search; the stale read does not count');
  assert.equal(r.sessions_without_recall, 1, 'session two opened neither an index nor a slice');
  assert.equal(r.top[0].reads, 2, 'the stale third read of auth.md is not counted'); assert.match(r.top[0].path, /^~\/projects\/demo\/.agent-fabric\/memory\/backend-dev\/solution\/auth\.md$/, 'the home is folded to ~');
  // A file touched today whose every record is old is not a session in the window.
  const olddir = path.join(h, '.claude', 'projects', '-home-x-projects-old'); fs.mkdirSync(olddir, { recursive: true });
  fs.writeFileSync(path.join(olddir, 'resumed.jsonl'), [say('x', stale), use('Read', { file_path: `${wc}/.agent-fabric/memory/backend-dev/INDEX.md` }, stale)].join('\n') + '\n');
  const r2 = recall(h);
  assert.equal(r2.sessions, 3, 'a file with no record in the window is not a session'); assert.equal(r2.index, 2);
  assert.ok(!JSON.stringify(r).includes('outbox'), 'a grep pattern is never reported: paths of reads and counts only');
  assert.ok(!JSON.stringify(r).includes('crossref') && !JSON.stringify(r).includes('drain-report'), 'non-slice reads under the corpus are not in top');
  assert.equal(recall(scratch('recall-empty-')).status, 'no-records');
  // The classifier alone.
  assert.equal(recallKind('Read', { file_path: '/x/memory/domains/a/INDEX.md' }).kind, 'index');
  assert.equal(recallKind('Read', { file_path: '/x/memory/shared/domain-y.md' }).kind, 'slice');
  assert.equal(recallKind('Read', { file_path: '/x/memory/README.md' }), null, 'the corpus README is not a slice');
  assert.equal(recallKind('Read', { file_path: '/x/memory/shared/README.md' }), null, 'nor the shared README');
  assert.equal(recallKind('Read', { file_path: '/x/.agent-fabric/memory/last-drain-report.json' }), null, 'nor a drain report');
  assert.equal(recallKind('Edit', { file_path: '/x/memory/domains/a/b.md' }), null, 'a write is not a recall');
  assert.equal(recallKind('Bash', { command: 'ls' }), null);
  assert.equal(recallKind('Read', { file_path: '.agent-fabric/memory/db-admin/INDEX.md' }).kind, 'index', 'a repository-relative index');
  assert.equal(recallKind('Bash', { command: 'sed -n 1,20p memory/domains/db-admin/domain/x.md' }).kind, 'search', 'a relative path in a command');
  assert.equal(recallKind('Read', { file_path: '/x/some-memory/domains/a/b.md' }), null, 'a directory merely ending in memory is not the corpus');
});

// THE CLAUDE ACCOUNTS: the harness's own headless /usage per observed
// config directory. The events below are the shape 2.1.281 printed live
// (docs/live-checks/2026-09-24-claude-accounts.md), trimmed.
const USAGE_EVENTS = JSON.stringify([
  { type: 'system', subtype: 'init', model: 'claude-opus-5-5' },
  { type: 'assistant', message: { content: [{ type: 'text', text: 'Current session: 11% used' }] },
    usage_report: { rate_limits: { limits: [
      { kind: 'session', group: 'session', percent: 11, resets_at: '2026-09-24T18:49:59Z', scope: null },
      { kind: 'weekly_all', group: 'weekly', percent: 83, resets_at: '2026-09-28T15:59:59Z', scope: null },
      { kind: 'weekly_scoped', group: 'weekly', percent: 86, resets_at: '2026-09-28T15:59:59Z', scope: { model: { display_name: 'Opus' } } }] } } },
  { type: 'result', subtype: 'success', is_error: false, num_turns: 0, total_cost_usd: 0, result: 'Current session: 11% used' }]);
function accountsHome(slugs = { 'claude-example-org': true }) {
  const h = scratch('ctl-accounts-');
  const dir = accountsDir(h, {});
  for (const [slug, signedIn] of Object.entries(slugs)) {
    fs.mkdirSync(path.join(dir, slug), { recursive: true });
    fs.writeFileSync(path.join(dir, slug, '.claude.json'), JSON.stringify({ oauthAccount: { emailAddress: `${slug}@example.org`, organizationUuid: 'org-1234' } }));
    if (signedIn) fs.writeFileSync(path.join(dir, slug, '.credentials.json'), JSON.stringify({ claudeAiOauth: { accessToken: ACCESS, refreshToken: 'refresh-XYZ' } }));
  }
  return { h, dir };
}

test('parseUsageReport: the meters in the server\'s order, fixed keys only; an error result is a failure, not an empty ok', () => {
  const r = parseUsageReport(USAGE_EVENTS);
  assert.equal(r.status, 'ok');
  assert.deepEqual(r.limits.map(l => [l.kind, l.percent, l.model]), [['session', 11, null], ['weekly_all', 83, null], ['weekly_scoped', 86, 'Opus']]);
  const failed = JSON.stringify([{ type: 'result', is_error: true, result: 'Failed to refresh OAuth token: another Claude Code process is refreshing it' }]);
  assert.deepEqual(parseUsageReport(failed), { status: 'failed', error: 'Failed to refresh OAuth token: another Claude Code process is refreshing it' });
  assert.equal(parseUsageReport('not json').status, 'unreadable');
  assert.equal(parseUsageReport(JSON.stringify([{ type: 'result', is_error: false }])).status, 'no-report', 'a success without the report is said, not read as zero usage');
});

test('readAccount: the child runs in the account\'s own config directory, with no inherited token that would outrank its sign-in', async () => {
  const { h, dir } = accountsHome();
  const seen = [];
  const saved = process.env.CLAUDE_CODE_OAUTH_TOKEN; process.env.CLAUDE_CODE_OAUTH_TOKEN = 'sk-ant-oat01-inherited-template-token';
  try {
    const r = await readAccount(path.join(dir, 'claude-example-org'), { home: h, bin: '/fake/claude', now: () => new Date('2026-09-24T20:00:00Z'),
      exec: async (bin, args, opts) => { seen.push({ bin, args, opts, cwdExisted: fs.existsSync(opts.cwd) }); return { stdout: USAGE_EVENTS }; } });
    assert.equal(r.status, 'ok');
    assert.equal(r.email, 'claude-example-org@example.org');
    assert.equal(r.organization_uuid, 'org-1234');
    assert.equal(r.read_at, '2026-09-24T20:00:00.000Z');
    assert.deepEqual(seen[0].args, ['-p', '/usage', '--output-format', 'json', '--no-session-persistence']);
    assert.equal(seen[0].opts.env.CLAUDE_CONFIG_DIR, path.join(dir, 'claude-example-org'));
    for (const k of ['CLAUDE_CODE_OAUTH_TOKEN', 'ANTHROPIC_API_KEY', 'ANTHROPIC_AUTH_TOKEN', 'ANTHROPIC_BASE_URL']) assert.ok(!(k in seen[0].opts.env), `${k} reached the child`);
    assert.ok(seen[0].cwdExisted, 'the child had a working directory');
    assert.equal(seen[0].opts.cwd, path.join(dir, 'claude-example-org', 'work'), 'one fixed cwd inside the account: the harness records a project per cwd');
    await readAccount(path.join(dir, 'claude-example-org'), { home: h, bin: '/fake/claude', exec: async (b, a, o) => { seen.push({ opts: o }); return { stdout: USAGE_EVENTS }; } });
    assert.equal(seen[1].opts.cwd, seen[0].opts.cwd, 'the same one on the next read');
    assertNoSecret(r);
  } finally { if (saved === undefined) delete process.env.CLAUDE_CODE_OAUTH_TOKEN; else process.env.CLAUDE_CODE_OAUTH_TOKEN = saved; }
});

test('readAccount: never signed in, a timeout and a failed run each say so; none is a reading', async () => {
  const { h, dir } = accountsHome({ 'not-yet': false, 'slow-one': true, 'broken-one': true });
  let ran = 0;
  const notYet = await readAccount(path.join(dir, 'not-yet'), { home: h, exec: async () => { ran++; return ''; } });
  assert.equal(notYet.status, 'not-signed-in'); assert.equal(ran, 0, 'no harness is started for an account with no sign-in');
  const slow = await readAccount(path.join(dir, 'slow-one'), { home: h, exec: async () => { const e = new Error('Command failed: claude -p /usage'); e.killed = true; throw e; } });
  assert.equal(slow.status, 'timeout');
  const broken = await readAccount(path.join(dir, 'broken-one'), { home: h, exec: async () => { throw new Error('spawn /fake/claude ENOENT\nsecond line'); } });
  assert.deepEqual([broken.status, broken.error], ['failed', 'spawn /fake/claude ENOENT']);
});

test('accounts: every observed account, one at a time; slugs that are not an account name are ignored; none is said', async () => {
  const { h, dir } = accountsHome({ 'claude-a': true, 'claude-b': true });
  fs.mkdirSync(path.join(dir, 'Not A Slug'));
  fs.writeFileSync(path.join(dir, 'stray-file'), '');
  assert.deepEqual(accountSlugs(dir), ['claude-a', 'claude-b']);
  let live = 0, peak = 0;
  const r = await accounts(h, { exec: async () => { live++; peak = Math.max(peak, live); await new Promise(res => setTimeout(res, 5)); live--; return USAGE_EVENTS; } });
  assert.equal(r.status, 'ok');
  assert.deepEqual(r.accounts.map(a => [a.slug, a.status]), [['claude-a', 'ok'], ['claude-b', 'ok']]);
  assert.equal(peak, 1, 'two harness runs never overlap');
  assert.equal((await accounts(scratch('ctl-noaccounts-'))).status, 'none');
});

test('a login on a template: identity names the token by fingerprint, not the old account its ~/.claude.json keeps; usage points at the observer', async () => {
  const h = home();
  const TEMPLATE = 'sk-ant-oat01-TEMPLATE-TOKEN-VALUE';
  fs.appendFileSync(path.join(h, '.config', 'agent-fabric', 'secrets.env'), `export CLAUDE_CODE_OAUTH_TOKEN='${TEMPLATE}'\n`);
  const id = identity(h, who);
  const fp = crypto.createHash('sha256').update(TEMPLATE).digest('hex').slice(0, 12);
  assert.deepEqual(id.claude_account, { via: 'setup-token', token_sha256_12: fp, email: null, organization: null });
  assert.deepEqual(id.own_sign_in, { email: 'someone@example.org', organization: 'Example Org' }, 'the own sign-in is still said, as what it is');
  let fetched = false;
  assert.deepEqual(await usage(h, async () => { fetched = true; return { ok: true, json: async () => ({}) }; }), { status: 'setup-token', see: 'fabric-ctl <observer> accounts' });
  assert.equal(fetched, false, 'the old sign-in\'s windows are another account\'s: not read');
  assert.deepEqual(keys(h).find(k => k.name === 'CLAUDE_CODE_OAUTH_TOKEN'), { name: 'CLAUDE_CODE_OAUTH_TOKEN', present: true, sha256_12: fp });
  const s2 = JSON.stringify([id, keys(h)]);
  assert.ok(!s2.includes(TEMPLATE), 'the template token leaked'); assertNoSecret(id);
});

test('the read lock: one reader per account across processes; a dead holder does not keep it; the fabric state root is honoured', async () => {
  const { h, dir } = accountsHome({ 'claude-a': true });
  const acct = path.join(dir, 'claude-a');
  const release = takeReadLock(acct, process.pid);
  assert.ok(release, 'the first reader takes it');
  fs.writeFileSync(path.join(acct, '.fabric-read.lock'), `${process.ppid}\n`);   // a live process that is not us
  let ran = 0;
  const busy = await readAccount(acct, { home: h, exec: async () => { ran++; return USAGE_EVENTS; } });
  assert.equal(busy.status, 'busy'); assert.equal(ran, 0, 'no second harness on a held account');
  fs.writeFileSync(path.join(acct, '.fabric-read.lock'), '999999999\n');   // a pid that cannot exist
  const r = await readAccount(acct, { home: h, exec: async () => { ran++; return USAGE_EVENTS; } });
  assert.equal(r.status, 'ok', 'a killed reader\'s lock is taken over'); assert.equal(ran, 1);
  assert.ok(!fs.existsSync(path.join(acct, '.fabric-read.lock')), 'released after the read');
  assert.equal(accountsDir('/home/x', { AGENT_FABRIC_STATE_DIR: '/srv/state' }), '/srv/state/accounts');
  assert.equal(accountsDir('/home/x', { XDG_STATE_HOME: '/xdg' }), '/xdg/agent-fabric/accounts');
});

test('the read lock is released when the read fails before the harness starts (work/ cannot be made)', async () => {
  const { h, dir } = accountsHome({ 'claude-a': true });
  const acct = path.join(dir, 'claude-a');
  fs.writeFileSync(path.join(acct, 'work'), 'not a directory');
  const r = await readAccount(acct, { home: h, exec: async () => assert.fail('no harness without a working directory') });
  assert.equal(r.status, 'failed');
  assert.ok(!fs.existsSync(path.join(acct, '.fabric-read.lock')), 'the lock did not outlive the failed read');
});

test('the read lock: a lock that cannot be read is a loud failure, not a permanent busy', async () => {
  const { h, dir } = accountsHome({ 'claude-a': true });
  const acct = path.join(dir, 'claude-a');
  fs.mkdirSync(path.join(acct, '.fabric-read.lock'));
  assert.throws(() => takeReadLock(acct), /EISDIR/);
  const r = await readAccount(acct, { home: h, exec: async () => assert.fail('no harness') });
  assert.deepEqual([r.status, r.error], ['failed', 'read lock: EISDIR'], 'the reason is named, never "another reader holds it"');
  fs.mkdirSync(path.join(dir, 'claude-b')); fs.writeFileSync(path.join(dir, 'claude-b', '.credentials.json'), '{}');
  const all = await accounts(h, { exec: async () => USAGE_EVENTS });
  assert.deepEqual(all.accounts.map(a => [a.slug, a.status]), [['claude-a', 'failed'], ['claude-b', 'ok']], 'one broken lock does not blank the sibling accounts');
});

test('presence: a session is a claude process that is not the daemon\'s own child; since is its start; role and project are the binding\'s', () => {
  const proc = scratch('presence-proc-');
  fs.writeFileSync(path.join(proc, 'stat'), 'cpu  1 2 3\nbtime 1790000000\n');
  // stat after the comm: state ppid pgrp session tty tpgid flags minflt cminflt majflt cmajflt utime stime cutime cstime priority nice threads itrealvalue starttime
  const stat = (pid, ppid, ticks) => { fs.mkdirSync(path.join(proc, String(pid))); fs.writeFileSync(path.join(proc, String(pid), 'stat'), `${pid} (claude) S ${ppid} 1 1 0 -1 0 0 0 0 0 0 0 0 0 20 0 1 0 ${ticks} 0 0`); };
  stat(100, 50, 1000); stat(200, 999, 500); stat(300, 60, 3000);
  const binding = { role: 'web-dev', project: 'gzapp' };
  const who = { agent: 'web-dev-01', host: 'h', role: 'web-dev', binding: '/nonexistent' };
  const notHeld = () => ({ held: false });
  const r = presence({ proc, self: 999, exec: () => '100\n200\n300\n', who, binding, hold: notHeld });
  assert.deepEqual(r, { status: 'ok', online: true, sessions: 2, since: new Date((1790000000 + 10) * 1000).toISOString(), role: 'web-dev', project: 'gzapp', planning: false },
    'the daemon\'s child (200) is not a session; the earliest start is the since');
  // A login with no role recorded is its name's slug, as the inbox's delivery reads it (review of #38).
  const unbound = presence({ proc, self: 999, exec: () => '100\n', who: { agent: 'web-dev-02', host: 'h', role: undefined, binding: '/nonexistent' }, binding: {}, hold: notHeld });
  assert.equal(unbound.role, 'web-dev', 'no binding role: the slug the login carries');
  const none = presence({ proc, self: 999, exec: () => { const e = new Error('exit 1'); e.status = 1; throw e; }, who, binding });
  assert.deepEqual([none.online, none.sessions, none.since], [false, 0, null], 'pgrep finding nothing is offline');
  const broken = presence({ proc, self: 999, exec: () => { const e = new Error('spawn pgrep ENOENT'); e.code = 'ENOENT'; throw e; }, who, binding });
  assert.equal(broken.status, 'failed', 'a pgrep that cannot run is not "offline"');
  assert.equal(presence({ proc, self: 999, exec: () => '100\n', who, binding, hold: () => ({ held: true }) }).planning, true, 'a held inbox is planning');
  assert.equal(presence({ proc, self: 999, exec: () => { const e = new Error('exit 1'); e.status = 1; throw e; }, who, binding, hold: () => ({ held: true }) }).planning, false, 'no session is never planning, whatever a stale marker says');
  assert.equal(presence({ proc, self: 999, exec: () => '100\n', who, binding, hold: () => { throw new Error('no hold dir'); } }).planning, false, 'an unreadable hold is not planning');
});

test('collect(presence) answers under the presence key — the name fabric-ctl reads', async () => {
  const data = await collect('presence', { presenceOpts: { exec: () => '', who: { agent: 'web-dev-01', host: 'h', role: 'web-dev', binding: '/nonexistent' }, binding: {} } });
  assert.deepEqual(Object.keys(data), ['presence']);
  assert.equal(data.presence.status, 'ok');
});

// ADR-042 rule 5: a store's refused commit is said by fabric-ctl keys until
// the store is repaired — the record secret_store.py keeps beside it, read
// for its commit, time and reason, never an entry.
test('storeRefusal: no store, no base, verified, refused or unreadable; and each mirror\'s refusal, named (review of ADR-042, F3 F4)', () => {
  const home = scratch('store-home-');
  const store = path.join(home, 'store'), children = path.join(home, 'children');
  const row = () => storeRefusal(home, store, children);
  assert.deepEqual(row(), { name: STORE_ROW, present: false, state: 'no store' }, 'no .git: no store, never verified');
  fs.mkdirSync(path.join(store, '.git'), { recursive: true });
  fs.writeFileSync(path.join(store, '.git', 'config'), '[core]\n\tbare = false\n');
  assert.deepEqual(row(), { name: STORE_ROW, present: false, state: 'no base' }, 'no trusted base: it verifies nothing');
  fs.writeFileSync(path.join(store, '.git', 'config'), `[core]\n\tbare = false\n[agent-fabric]\n\ttrustedbase = ${'a'.repeat(40)}\n`);
  assert.deepEqual(row(), { name: STORE_ROW, present: true, state: 'verified' });
  // As the verifier reads it: the last value, and only lowercase hex.
  fs.writeFileSync(path.join(store, '.git', 'config'), `[agent-fabric]\n\ttrustedbase = ${'A'.repeat(40)}\n`);
  assert.equal(row().state, 'no base', 'an uppercase base is none to the verifier, so none here');
  fs.writeFileSync(path.join(store, '.git', 'config'), `[agent-fabric]\n\tTrustedBase = ${'a'.repeat(40)}\n\ttrustedbase = x\n`);
  assert.equal(row().state, 'no base', 'git reads the last value: a good line before a bad one is no base');
  fs.writeFileSync(path.join(store, '.git', 'config'), `[agent-fabric]\n\ttrustedbase = x\n\tTRUSTEDBASE = ${'a'.repeat(40)}\n`);
  assert.equal(row().state, 'verified', '…and a good last line, the key in any case, is the base');
  fs.writeFileSync(path.join(store, '.git', 'agent-fabric-refusal.json'),
    JSON.stringify({ commit: '0123456789abcdef0123', reason: 'not signed', at: '2026-10-04T10:00:00Z' }));
  assert.deepEqual(row(), { name: STORE_ROW, present: false, state: 'refused',
    refused: { commit: '0123456789ab', at: '2026-10-04T10:00:00Z', reason: 'not signed' } });
  fs.writeFileSync(path.join(store, '.git', 'agent-fabric-refusal.json'), 'not json');
  assert.equal(row().state, 'unreadable', 'a record that cannot be read is no clean bill');
  fs.rmSync(path.join(store, '.git', 'agent-fabric-refusal.json'));
  const kid = '01a106ee-84ec-74bc-84ef-3720a55d6a3f';
  fs.mkdirSync(path.join(children, kid, '.git'), { recursive: true });
  assert.deepEqual(row().mirrors, [{ agent_id: kid, state: 'unreadable' }], 'a mirror whose config cannot be read is said (review of #94)');
  fs.writeFileSync(path.join(children, kid, '.git', 'config'), '[core]\n\tbare = false\n');
  assert.deepEqual(row(), { name: STORE_ROW, present: false, state: 'verified', mirrors: [{ agent_id: kid, state: 'no base' }] },
    'a mirror with no base refuses every verified operation: not clean, said by name');
  fs.writeFileSync(path.join(children, kid, '.git', 'config'), `[agent-fabric]\n\ttrustedbase = ${'b'.repeat(40)}\n`);
  fs.mkdirSync(path.join(children, 'not-an-id', '.git'), { recursive: true });
  fs.writeFileSync(path.join(children, 'not-an-id', '.git', 'agent-fabric-refusal.json'), '{}');
  assert.deepEqual(row(), { name: STORE_ROW, present: true, state: 'verified' }, 'a clean mirror adds nothing; a name that is no agent id is no mirror');
  fs.writeFileSync(path.join(children, kid, '.git', 'agent-fabric-refusal.json'), JSON.stringify({ commit: 'ffff', reason: 'outsider', at: 'T' }));
  assert.deepEqual(row(), { name: STORE_ROW, present: false, state: 'verified',
    mirrors: [{ agent_id: kid, commit: 'ffff', at: 'T', reason: 'outsider' }] }, 'the own store verified, a mirror refused: not clean');
  // A refused rebuild removes the mirror and keeps its refusal beside it
  // (review of #96): said by that record alone, no base to read.
  fs.rmSync(path.join(children, kid), { recursive: true });
  assert.deepEqual(row(), { name: STORE_ROW, present: true, state: 'verified' }, 'control: no mirror and no record, nothing said');
  fs.writeFileSync(path.join(children, `${kid}.refusal.json`), JSON.stringify({ commit: 'eeee', reason: 'not signed', at: 'U' }));
  assert.deepEqual(row(), { name: STORE_ROW, present: false, state: 'verified',
    mirrors: [{ agent_id: kid, commit: 'eeee', at: 'U', reason: 'not signed' }] }, 'a removed mirror\'s kept refusal is said by name');
});

// The disk op: each daemon measures its own home, through du only — names
// and sizes, never contents. A fake exec answers each du from a table, so
// the case pins what is asked as well as what is made of the answer.
test('disk: the own home in one scan — the largest entries, the target/ directories under projects/ to depth 3, a partial du said, never a crash', async () => {
  const home = scratch('disk-home-');
  for (const d of ['.cache', '.local', 'notes', 'projects']) fs.mkdirSync(path.join(home, d));
  fs.writeFileSync(path.join(home, '.bashrc'), '');
  const P = s => path.join(home, s);
  const calls = [];
  const answers = {
    entries: [[400, '.cache'], [9000, '.local'], [4, '.bashrc'], [100, 'notes']],
    tree: [[50000, 'projects'], [30000, 'projects/a'], [20000, 'projects/a/target'], [1000, 'projects/a/target/target'],
           [12000, 'projects/b/c'], [9000, 'projects/b/c/target'], [5, 'projects/target-notes'], [700, 'projects/target']],
  };
  // du -0: each record ends in NUL, a newline is part of a name.
  const out = rows => rows.map(([kb, rel]) => `${kb}\t${P(rel)}\0`).join('');
  const exec = async (cmd, args, opts) => {
    calls.push([cmd, ...args, opts.timeout]);
    return { stdout: args.includes('-xsk') ? out(answers.entries) : out(answers.tree) };
  };
  const d = await disk(home, { exec });
  assert.equal(d.status, 'ok', JSON.stringify(d));
  assert.deepEqual(d.largest.map(e => e.name), ['projects', '.local', '.cache', 'notes', '.bashrc'], 'the largest first; projects counted by its own line');
  assert.equal(d.total_kb, 50000 + 9000 + 400 + 100 + 4, 'the total is the sum of the entries');
  assert.deepEqual(d.targets.map(t => [t.path, t.kb]), [['projects/a/target', 20000], ['projects/b/c/target', 9000], ['projects/target', 700]],
    'every target/ to depth 3, largest first; one inside a target/ is not counted twice, a name only starting with target is not one');
  assert.equal(d.targets_kb, 29700);
  // Only du was run, bounded, and projects/ is scanned once, to depth 3.
  assert.ok(calls.every(c => c[0] === 'du' && c.at(-1) === DISK_TIMEOUT_MS), JSON.stringify(calls));
  assert.deepEqual(calls.find(c => c.includes('-xk')).slice(1, 5), ['-0', '-xk', '--max-depth=3', '--'], 'NUL-ended records');
  assert.equal(calls.find(c => c.includes('-xsk'))[1], '-0');
  assert.ok(!calls.find(c => c.includes('-xsk')).includes(P('projects')), 'projects/ is not scanned twice');
  // A du that read part of a tree (exit 1) or stopped at its bound: what it
  // measured stands, the status says partial, errors say why.
  const partial = await disk(home, { exec: async (cmd, args) => {
    if (args.includes('-xsk')) throw Object.assign(new Error('exit 1'), { code: 1, stdout: out(answers.entries) });
    throw Object.assign(new Error('killed'), { killed: true, signal: 'SIGTERM', stdout: '' });
  } });
  assert.equal(partial.status, 'partial');
  assert.equal(partial.total_kb, 9504, 'the entries du could read are counted');
  assert.deepEqual(partial.errors, ['home entries: du exit 1, partial', `projects: du stopped at its ${DISK_TIMEOUT_MS / 1000} s bound`]);
  // A home that cannot be listed: failed, said, nothing run.
  const failed = await disk(path.join(home, 'gone'), { exec: async () => { throw new Error('ran'); } });
  assert.equal(failed.status, 'failed');
  assert.match(failed.error, /could not be listed \(ENOENT\)/);
  // A home with no projects/: no tree scan, no targets.
  const bare = scratch('disk-bare-'); fs.mkdirSync(path.join(bare, 'x'));
  const bareCalls = [];
  const b = await disk(bare, { exec: async (cmd, args) => { bareCalls.push(args[1]); return `7\t${path.join(bare, 'x')}\0`; } });
  assert.deepEqual([b.status, b.total_kb, b.targets, bareCalls], ['ok', 7, [], ['-xsk']]);
  assert.ok(OPS.includes('disk'), 'a known op');
  // and collect() answers it under its own name, a failure inline
  const c = await collect('disk', { home: path.join(home, 'gone') });
  assert.equal(c.disk.status, 'failed');
});

// Review of #92, round 4: a name with a newline is one entry, never an
// invented one; a path du reports outside the home counts for nothing; a du
// killed for its output says so, not that it ran out of time.
test('disk: NUL-ended records — a newline in a name invents nothing; outside the home is dropped; maxBuffer said', async () => {
  const home = scratch('disk-nul-');
  fs.mkdirSync(path.join(home, 'a\nb'));
  fs.mkdirSync(path.join(home, 'projects'));
  const answer = `100\t${path.join(home, 'a\nb')}\0` + `999999\t/etc\0`;
  const d = await disk(home, { exec: async (cmd, args) => (args.includes('-xsk') ? answer : `50\t${path.join(home, 'projects')}\0`) });
  assert.deepEqual(d.largest.map(e => [e.name, e.kb]), [['a\nb', 100], ['projects', 50]], 'one entry, its newline kept; /etc dropped');
  assert.equal(d.total_kb, 150);
  const big = await disk(home, { exec: async () => { throw Object.assign(new Error('stdout maxBuffer length exceeded'), { code: 'ERR_CHILD_PROCESS_STDIO_MAXBUFFER', killed: true, signal: 'SIGTERM', stdout: '' }); } });
  assert.ok(big.errors.every(e => e.endsWith(`du's output passed its ${DISK_MAX_BUFFER / 1048576} MiB bound`)), JSON.stringify(big.errors));
});

// Carried from #92: a dropped record is named, not silent; what du could
// not read is counted and the first named (a rootless podman's volumes are
// sub-UID owned); du is asked in the C locale so its complaints read the
// same everywhere; a record begins at a NUL, never after a newline.
test('disk: records outside the home named; unreadable paths counted, the first named; du in the C locale', async () => {
  const home = scratch('disk-carry-');
  fs.mkdirSync(path.join(home, 'projects'));
  fs.mkdirSync(path.join(home, 'x'));
  const envs = [];
  const exec = async (cmd, args, opts) => {
    envs.push(opts.env?.LC_ALL);
    if (args.includes('-xsk')) return `100\t${path.join(home, 'x')}\0` + `999\t/etc\0` + `7\t/root\0` + `\n5\t${path.join(home, 'x', 'y')}\0`;
    throw Object.assign(new Error('exit 1'), { code: 1, stdout: `50\t${path.join(home, 'projects')}\0`,
      stderr: `du: cannot read directory '${home}/projects/p/volumes/v1': Permission denied\n` +
              `du: cannot read directory "${home}/projects/it's": Permission denied\n` });
  };
  const d = await disk(home, { exec });
  assert.deepEqual(envs, ['C', 'C'], 'du is asked in the C locale');
  assert.equal(d.total_kb, 150, 'outside the home and a record after a newline count for nothing');
  assert.equal(d.status, 'partial');
  assert.deepEqual(d.errors, [
    `home entries: 2 records outside ${home} dropped; the first: /etc`,
    'projects: du exit 1, partial',
    `projects: 2 paths du could not read, not counted; the first: '${home}/projects/p/volumes/v1'`,
  ]);
});

