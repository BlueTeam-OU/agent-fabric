// The lines the inbox prints, in the language of the login that reads
// them (scripts/i18n.mjs, i18n/README.md, docs/adr/ADR-028-house-i18n-standard-gzcoord-speaks-the-readers-language.md).
//
// The load-bearing case is the last one: a default-locale login's output
// is byte-identical to what it was before a dictionary existed.
// Everything else here is the seam — that a locale reaches the fabric's
// own lines and stops at the wire's.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import { scratch } from '../../../tests/scratch.mjs';
import { DEFAULT_LOCALE, DEFAULT_PATH, defaultDictionary, dictionary, dictionaryPath,
         fill, localeReminder, localeTag, printer, suffix } from '../scripts/i18n.mjs';
import { checkKeywords, render } from '../scripts/inbox.mjs';
import { validate, whoami } from '../scripts/gzmsg.mjs';

const SCRIPTS = fileURLToPath(new URL('../scripts/', import.meta.url));
const FABRIC = fileURLToPath(new URL('../../../', import.meta.url));
// The key shape is the schema's, read — not a third copy of the rule
// (blind review F6 on PR #28).
// A tool may print a diagnostic before the line under test — the
// pinned-locale notice does, on a login that has a dictionary.
const lastLine = (text) => text.trim().split('\n').pop();
const SLUG = new RegExp(JSON.parse(
  fs.readFileSync(fileURLToPath(new URL('../i18n/i18n.schema.json', import.meta.url)), 'utf8')
).propertyNames.pattern);

test('the default dictionary is the house i18n shape: dotted slugs, non-empty strings', () => {
  const en = defaultDictionary();
  assert.equal(path.basename(DEFAULT_PATH), `${DEFAULT_LOCALE}.json`);
  for (const [k, v] of Object.entries(en)) {
    assert.match(k, SLUG, `key ${k}`);
    assert.equal(typeof v, 'string', `value of ${k}`);
    assert.notEqual(v, '', `value of ${k}`);
  }
});

test('the locale a login reads is the launcher\'s rule: what follows the last dash', () => {
  assert.equal(suffix('language-culture-ge'), 'ge');
  assert.equal(suffix('language-culture-ru'), 'ru');
  assert.equal(suffix('brand-comms-01'), '01');   // no locale/01: the default
  assert.equal(suffix('user'), 'user');
});

test('the suffix names its tag in locale.json — ge is Georgian, not German', () => {
  const root = FABRIC;
  const dir = s => path.join(root, 'identities', 'roles', 'language-culture', 'locale', s);
  assert.equal(localeTag(dir('ge')), 'ka-GE');
  assert.equal(localeTag(dir('ru')), 'ru-RU');
  assert.equal(localeTag(dir('nothing-here')), undefined);
});

test('every key the code prints is in en-US.json, and en-US.json has no key nothing prints', () => {
  const en = defaultDictionary();
  const used = new Set();
  // Every module that prints a dictionary line, not just the inbox: the
  // validator's diagnostics are keys too, and a guard scoped to one file
  // would call every one of them dead (the automated review's claim 2).
  for (const file of ['inbox.mjs', 'gzmsg.mjs', 'send.mjs']) {
    const src = fs.readFileSync(path.join(SCRIPTS, file), 'utf8');
    for (const m of src.matchAll(/\bt\('([a-z][a-z.-]+)'/g)) used.add(m[1]);
    for (const m of src.matchAll(/\ben\(\)\('([a-z][a-z.-]+)'/g)) used.add(m[1]);
  }
  assert.deepEqual([...used].filter(k => !(k in en)).sort(), [], 'printed but not in en-US.json');
  assert.deepEqual(Object.keys(en).filter(k => !used.has(k)).sort(), [], 'in en-US.json but nothing prints it');
});

test('a helper that defaults its printer to English is handed the caller\'s at every call', () => {
  // send.mjs called integrationConfig and assertNotControlChannel without
  // its printer, so on a login with an active locale two refusals were an
  // English body in a translated frame (review of #29). The defaults exist
  // for callers with no locale at all; every script here has one.
  const inbox = fs.readFileSync(path.join(SCRIPTS, 'inbox.mjs'), 'utf8');
  // The capture stops at en()'s own ")"; a printer inside an options
  // object ({ t = en() }) is passed by name, not positionally, and is not
  // what this rule reads.
  const helpers = [...inbox.matchAll(/export (?:async )?function (\w+)\(([^)]*)\)/g)]
    .filter(m => /\bt = en\($/.test(m[2]) && !m[2].includes('{')).map(m => m[1]);
  assert.ok(helpers.includes('integrationConfig') && helpers.includes('assertNotControlChannel'), `helpers found: ${helpers}`);
  const bare = [];
  for (const file of ['inbox.mjs', 'gzmsg.mjs', 'send.mjs']) {
    const src = fs.readFileSync(path.join(SCRIPTS, file), 'utf8');
    for (const name of helpers) {
      for (const m of src.matchAll(new RegExp(`(?<![\\w.])${name}\\(`, 'g'))) {
        const lineStart = src.lastIndexOf('\n', m.index) + 1;
        const line = src.slice(lineStart, src.indexOf('\n', m.index));
        // Its definition, or a default parameter value (token's cfg): that
        // supplies fields, and prints nothing.
        if (/^\s*(export )?(async )?function /.test(line) && m.index - lineStart < line.indexOf(') {')) continue;
        let depth = 0, i = m.index + name.length, args = '';
        for (; i < src.length; i++) { const ch = src[i]; if (ch === '(') depth++; else if (ch === ')' && --depth === 0) break; args += ch; }
        if (!/,\s*t\s*$/.test(args.slice(1))) bare.push(`${file}: ${name}${args})`);
      }
    }
  }
  assert.deepEqual(bare, [], 'called without the caller\'s printer');
});

const active = (body, { tag = 'ka-GE', locale = { tag } } = {}) => {
  const root = scratch('locale-');
  const dir = path.join(root, 'identities', 'roles', 'language-culture', 'locale', 'ge');
  fs.mkdirSync(dir, { recursive: true });
  if (locale) fs.writeFileSync(path.join(dir, 'locale.json'), JSON.stringify(locale));
  if (body !== null) fs.writeFileSync(path.join(dir, `${tag}.json`), body);
  return { root, dir, me: { agent: 'language-culture-ge', role: 'language-culture' } };
};

test('a login with no active dictionary reads the default locale', () => {
  const root = scratch('locale-');
  assert.equal(dictionaryPath({ agent: 'user', role: 'fabric-coordinator' }, root, {}), null);
  assert.equal(dictionaryPath({ agent: 'language-culture-ge' }, root, {}), null, 'no role bound');
  const { root: r1, me } = active(null);
  assert.equal(dictionaryPath(me, r1, {}), null, 'a tag with no dictionary file');
  const { root: r2 } = active('{}', { locale: null });
  assert.equal(dictionaryPath({ agent: 'language-culture-ge', role: 'language-culture' }, r2, {}), null, 'no tag');
});

test('an active locale is found by its tag', () => {
  const { root, dir, me } = active('{}');
  assert.equal(dictionaryPath(me, root, {}), path.join(dir, 'ka-GE.json'));
});

test('an active locale covers the keys it carries; the default stands for the rest', () => {
  const { root, me } = active(JSON.stringify({
    'inbox.others-header': 'ᲗᲐᲠᲒᲛᲐᲜᲘ (SPEC §17):',
    'inbox.head': '',                     // not a localization value
    'nothing.like-this': 'invented',      // not a key of the default
  }));
  const dict = dictionary(me, { root, env: {} }), en = defaultDictionary();
  assert.equal(dict['inbox.others-header'], 'ᲗᲐᲠᲒᲛᲐᲜᲘ (SPEC §17):');
  assert.equal(dict['inbox.head'], en['inbox.head'], 'an empty value is not a translation');
  assert.equal(dict['delivery.title'], en['delivery.title'], 'a key it lacks falls back, never invented');
  assert.ok(!('nothing.like-this' in dict), 'a key the default does not have is not added');
});

test('an unreadable dictionary leaves the default standing — a session start never fails on it', () => {
  const { root, me } = active('{ this is not json');
  assert.deepEqual(dictionary(me, { root, env: {} }), defaultDictionary());
});

test('a placeholder the caller did not supply is left standing, not blanked', () => {
  assert.equal(fill('seq {first}–{last}', { first: 1, last: 9 }), 'seq 1–9');
  assert.equal(fill('a {who} and {missing}', { who: 'x' }), 'a x and {missing}');
});

test('an unknown key prints as itself: a bug report, not a crash', () => {
  assert.equal(printer(defaultDictionary())('no.such-key'), 'no.such-key');
});

const fixture = () => {
  const body = (id, to) => `[GZCOORD/1] OBSERVATION\nFROM: h/sender\nROLE: backend-dev\nPROJECT: gzapp\nMESSAGE-ID: ${id}\n${to}\nSUBJECT: a subject\n\nNOTES:\nthe body, as its sender wrote it\n`;
  const rec = (seq, content) => ({ seq, id: `r${seq}`, sender: 'h/sender', timestamp: '2026-09-21T08:00:00Z', content });
  return { delivered: true, classified: [
    { rec: rec(1, body('01a0-1', 'TO: h/me')), msg: { type: 'OBSERVATION', metadata: { 'MESSAGE-ID': '01a0-1', TO: 'h/me', SUBJECT: 'a subject' } }, isMine: true },
    { rec: rec(2, body('01a0-2', 'TO: h/other')), msg: { type: 'OBSERVATION', metadata: { 'MESSAGE-ID': '01a0-2', TO: 'h/other', SUBJECT: 'other' } }, isMine: false },
  ] };
};
const ME = { address: 'h/me', instance: 'me', slug: 'language-culture' };

test('the locale reaches the fabric\'s own lines and stops at the wire', () => {
  const { root, me } = active(JSON.stringify({
    'inbox.head': 'ᲨᲔᲛᲝᲡᲣᲚᲘ {who}: {mine} / {others}, {channel}',
    'inbox.others-header': 'ᲐᲠ ᲐᲠᲘᲡ ᲨᲔᲜᲗᲕᲘᲡ (SPEC §17):',
  }));
  const out = render(fixture(), ME, 'gzapp:gzcoord', undefined, { t: printer(dictionary(me, { root, env: {} })) });
  assert.match(out, /^ᲨᲔᲛᲝᲡᲣᲚᲘ h\/me \(language-culture\): 1 \/ 1, gzapp:gzcoord$/m);
  assert.match(out, /^ᲐᲠ ᲐᲠᲘᲡ ᲨᲔᲜᲗᲕᲘᲡ \(SPEC §17\):$/m);
  // The wire, untouched: the sender's body, the metadata keys, the type,
  // and the addressing vocabulary a reader matches by name.
  assert.match(out, /^\[GZCOORD\/1\] OBSERVATION$/m);
  assert.match(out, /^MESSAGE-ID: 01a0-1$/m);
  assert.match(out, /^the body, as its sender wrote it$/m);
  assert.match(out, /01a0-2 {2}OBSERVATION {2}TO h\/other {2}other/);
});

test('the locale\'s standing reminder rides the head line, and only it', () => {
  const { root, me } = active(JSON.stringify({ 'inbox.head': 'ᲨᲔᲛᲝᲡᲣᲚᲘ {who}, {channel}' }),
                              { locale: { tag: 'ka-GE', reminder: ' - ᲘᲤᲘᲥᲠᲔ' } });
  const reminder = localeReminder(me, root, {});
  assert.equal(reminder, ' - ᲘᲤᲘᲥᲠᲔ');
  const out = render(fixture(), ME, 'gzapp:gzcoord', undefined,
                     { t: printer(dictionary(me, { root, env: {} })), reminder });
  assert.match(out, /^ᲨᲔᲛᲝᲡᲣᲚᲘ h\/me \(language-culture\), gzapp:gzcoord - ᲘᲤᲘᲥᲠᲔ$/m);
  assert.equal(out.split('\n').filter(l => l.includes('ᲘᲤᲘᲥᲠᲔ')).length, 1, 'the head line and no other');
});

test('no locale, no reminder: nothing is appended for a default-locale login', () => {
  const root = scratch('locale-');
  assert.equal(localeReminder({ agent: 'user', role: 'fabric-coordinator' }, root, {}), '');
  assert.equal(localeReminder({ agent: 'language-culture-ge' }, root, {}), '', 'no role bound');
  const { root: r } = active('{}', { locale: { tag: 'ka-GE' } });
  assert.equal(localeReminder({ agent: 'language-culture-ge', role: 'language-culture' }, r, {}), '',
               'a locale that declares none');
});

test('the reminder each real locale carries is the owner\'s, in that locale', () => {
  const root = FABRIC;
  const of = s => localeReminder({ agent: `language-culture-${s}`, role: 'language-culture' }, root, {});
  for (const s of ['ge', 'ru']) {
    assert.notEqual(of(s), '', `${s} carries one`);
    assert.match(of(s), /^ - /, `${s} appends to the head line`);
    assert.ok(/[^\u0000-\u024F]/.test(of(s)), `${s} is in its own script`);
  }
});

// The dictionary is the one thing whose failure the last-resort handler
// cannot report through the dictionary. Copying scripts/ and i18n/ into a
// scratch tree is what makes a damaged en-US.json reachable at all: the
// default is resolved from the MODULE, deliberately, so nothing in the
// environment can point it elsewhere (blind review F1 on PR #28).
const brokenTree = (contents) => {
  const dir = scratch('i18n-broken-');
  fs.mkdirSync(path.join(dir, 'scripts'), { recursive: true });
  fs.mkdirSync(path.join(dir, 'i18n'), { recursive: true });
  for (const f of fs.readdirSync(SCRIPTS)) fs.copyFileSync(path.join(SCRIPTS, f), path.join(dir, 'scripts', f));
  fs.writeFileSync(path.join(dir, 'i18n', 'en-US.json'), contents);
  return path.join(dir, 'scripts', 'inbox.mjs');
};

for (const [what, contents] of [['unparsable', '{ not json'], ['absent', null]]) {
  test(`a ${what} default dictionary degrades loudly and the tool still runs`, () => {
    const entry = brokenTree(contents ?? '{}');
    if (contents === null) fs.rmSync(path.join(path.dirname(entry), '..', 'i18n', 'en-US.json'));
    const r = spawnSync(process.execPath, [entry, '--held'],
                        { env: { ...process.env, AGENT_FABRIC_ROOT: FABRIC.replace(/\/$/, '') }, encoding: 'utf8' });
    const { status, stdout, stderr } = r;
    // Constrained, not unconstrained: --held answers 0 held / 1 not held,
    // and an uncaught throw also exits 1, so the stdout assertion below is
    // what separates them — but an exit outside that pair is a new failure
    // mode and this says so (re-review risk).
    // Never a stack trace, and never silence: the tool says which file it
    // could not read and what that costs, then finishes its job with every
    // line printed as its own key.
    assert.ok(!/^\s+at /m.test(stderr), `a stack trace reached the session:\n${stderr}`);
    assert.match(stderr, /could not be read .*every line will print as its own key/, stderr);
    assert.match(stdout, /^held\.(not-)?held/m, `the tool did not finish: ${stdout}|${stderr}`);
    assert.ok(status === 0 || status === 1, `exited ${status}: ${stderr}`);
  });
}

test('--replay with no value is a usage line and exit 1', () => {
  const r = spawnSync(process.execPath, [path.join(SCRIPTS, 'inbox.mjs'), '--replay'], { encoding: 'utf8' });
  assert.equal(r.status, 1, r.stderr);
  assert.equal(lastLine(r.stderr), defaultDictionary()['replay.usage']);
});

test('a keyword refusal reads in the login\'s own language', () => {
  const ka = printer({ ...defaultDictionary(), 'keyword.too-short': 'ᲛᲝᲙᲚᲔᲐ {keyword} — {min}' });
  assert.throws(() => checkKeywords(['ab'], ka), /ᲛᲝᲙᲚᲔᲐ "ab" — 3/);
  const many = Array.from({ length: 9 }, (_, i) => `kw${i}`);
  const ka2 = printer({ ...defaultDictionary(), 'keyword.too-many': 'ᲖᲔᲓᲐ ᲖᲦᲕᲐᲠᲘ {max}' });
  assert.throws(() => checkKeywords(many, ka2), /ᲖᲔᲓᲐ ᲖᲦᲕᲐᲠᲘ 8/);
});

test('a validator diagnostic reaches a locale reader whole, not just its prefix', () => {
  const { root, me } = active(JSON.stringify({
    'delivery.invalid': 'ᲐᲠᲐᲡᲬᲝᲠᲘ: {detail}',
    'validate.missing': 'ᲐᲙᲚᲘᲐ {key}',
    'validate.no-addressing': 'ᲐᲠᲐᲕᲘᲡᲗᲕᲘᲡ: TO, TO-ROLE ᲐᲜ BROADCAST: true',
  }));
  const t = printer(dictionary(me, { root, env: {} }));
  // FROM is malformed on purpose: validate.from-shape is a key this
  // locale does NOT carry, so the same call proves both halves at once.
  const v = validate('[GZCOORD/1] INFO\nFROM: not-an-address\nROLE: backend-dev\nPROJECT: gzapp\n', { t, maxColumns: 0 });
  // The substance, not only the wrapper — the whole point of the finding.
  assert.ok(v.errors.includes('ᲐᲙᲚᲘᲐ MESSAGE-ID'), v.errors.join(' | '));
  assert.ok(v.errors.includes('ᲐᲠᲐᲕᲘᲡᲗᲕᲘᲡ: TO, TO-ROLE ᲐᲜ BROADCAST: true'), v.errors.join(' | '));
  // A key the locale lacks falls back to en-US, never to invented text.
  assert.ok(v.errors.includes(defaultDictionary()['validate.from-shape']), v.errors.join(' | '));
});

test('the assignment diagnostic agrees with its own number', () => {
  // The old code built both from one template with a `${plural}` on the
  // noun only, so the singular read "REQUEST section make this an
  // assignment". Splitting the key fixed the verb; these pin both, which
  // nothing did before — the blind review found the change by reading.
  const msg = n => `[GZCOORD/1] INFO\nFROM: h/s\nROLE: backend-dev\nPROJECT: gzapp\nMESSAGE-ID: x\nTO-ROLE: backend-dev\n\n${n}`;
  const one = validate(msg('REQUEST:\na\n'), { maxColumns: 0 }).errors.join(' | ');
  const two = validate(msg('REQUEST:\na\n\nACCEPTANCE:\nb\n'), { maxColumns: 0 }).errors.join(' | ');
  assert.match(one, /REQUEST section makes this an assignment/);
  assert.match(two, /REQUEST and ACCEPTANCE sections make this an assignment/);
});

test('the default locale still produces the validator\'s English, byte for byte', () => {
  const v = validate('[GZCOORD/1] INFO\nFROM: h/s\nROLE: backend-dev\nPROJECT: gzapp\n', { maxColumns: 0 });
  assert.ok(v.errors.includes('missing MESSAGE-ID'), v.errors.join(' | '));
  assert.ok(v.errors.includes('missing TO, TO-ROLE or BROADCAST: true'), v.errors.join(' | '));
  assert.deepEqual(validate('nonsense').errors, ['invalid GZCOORD/1 first line']);
});

// Nothing exercised the tools AS a login that has a dictionary — every
// case either had no locale or called render()/validate() with a printer
// built by hand. So the suite asserted English and was green on a login
// with no locale directory and red on every holder's, which is how the
// first real dictionary found it (the ru holder, agent-fabric#29).
//
// The fixture owns the IDENTITY as well as the dictionary. Taking the
// role from the running login's binding was the first attempt and simply
// inverted the dependency: CI's login has no binding, so `role` is unset,
// `dictionaryPath` refuses before it ever looks for a tag, and the case
// went red exactly where the old one was green (blind review F1 on
// PR #30, confirmed by this PR's own CI).
const ROLE = 'language-culture';
const liveLocale = (values) => {
  // The LOGIN is whatever is running the suite — os.userInfo() reads the
  // uid's passwd entry and no environment variable can dress it up — so
  // the fixture supplies the one thing that varies and must not: the
  // BINDING, and with it the role. A scratch root carries no
  // identity.py, so whoami() falls back to the login plus this binding.
  const agent = os.userInfo().username;
  const root = scratch('live-locale-');
  const state = scratch('live-state-');
  fs.mkdirSync(path.join(state, 'agents', agent), { recursive: true });
  fs.writeFileSync(path.join(state, 'agents', agent, 'binding.json'),
                   JSON.stringify({ role: ROLE, project: 'agent-fabric' }));
  const dir = path.join(root, 'identities', 'roles', ROLE, 'locale', suffix(agent));
  fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(path.join(dir, 'locale.json'), JSON.stringify({ tag: 'xx-XX', reminder: ' - ᲛᲘᲜᲘᲨᲜᲔᲑᲐ' }));
  const en = defaultDictionary();
  fs.writeFileSync(path.join(dir, 'xx-XX.json'),
                   JSON.stringify(Object.fromEntries(Object.keys(en).map(k => [k, values[k] ?? `ᲗᲐᲠᲒᲛᲐᲜᲘ ${en[k]}`]))));
  const env = { ...process.env, AGENT_FABRIC_ROOT: root, AGENT_FABRIC_STATE_DIR: state };
  return { root, me: { agent, role: ROLE }, env };
};

const USAGE_KA = 'ᲒᲐᲛᲝᲧᲔᲜᲔᲑᲐ: inbox.mjs --replay <seq|message-id>';

test('the tools run as a login that HAS a dictionary, and print it', () => {
  const { env } = liveLocale({ 'replay.usage': USAGE_KA });
  const r = spawnSync(process.execPath, [path.join(SCRIPTS, 'inbox.mjs'), '--replay'],
                      { env: { ...env, GZCOORD_DEFAULT_LOCALE_ONLY: '' }, encoding: 'utf8' });
  assert.equal(r.status, 1, r.stderr);
  assert.equal(lastLine(r.stderr), USAGE_KA);
});

test('a locale dictionary that cannot be read falls back to English, and says so', () => {
  const { root, me, env } = liveLocale({});
  const file = path.join(root, 'identities', 'roles', me.role, 'locale', suffix(me.agent), 'xx-XX.json');
  fs.writeFileSync(file, '{ not json');
  const r = spawnSync(process.execPath, [path.join(SCRIPTS, 'inbox.mjs'), '--replay'],
                      { env: { ...env, GZCOORD_DEFAULT_LOCALE_ONLY: '' }, encoding: 'utf8' });
  assert.equal(r.status, 1, r.stderr);
  assert.equal(lastLine(r.stderr), defaultDictionary()['replay.usage']);
  assert.match(r.stderr, /xx-XX\.json could not be read .*; printing the default locale/);
});

test('and the same run pinned to the default locale prints English, whoever runs it', () => {
  const { env } = liveLocale({ 'replay.usage': USAGE_KA });
  const r = spawnSync(process.execPath, [path.join(SCRIPTS, 'inbox.mjs'), '--replay'],
                      { env: { ...env, GZCOORD_DEFAULT_LOCALE_ONLY: '1' }, encoding: 'utf8' });
  assert.equal(r.status, 1, r.stderr);
  // The English line, and the notice that a configured locale was pinned
  // away — silence there is what the switch's threat model asks about.
  assert.match(r.stderr, new RegExp(`^${defaultDictionary()['replay.usage'].replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}$`, 'm'));
  assert.match(r.stderr, /GZCOORD_DEFAULT_LOCALE_ONLY=1 — printing the default locale, not /);
  assert.ok(!r.stderr.includes(USAGE_KA), r.stderr);
});

test('the switch silences the standing reminder too, and only for exactly 1', () => {
  const { root, me } = liveLocale({});
  assert.equal(localeReminder(me, root, {}), ' - ᲛᲘᲜᲘᲨᲜᲔᲑᲐ');
  assert.equal(localeReminder(me, root, { GZCOORD_DEFAULT_LOCALE_ONLY: '1' }), '');
  assert.equal(dictionaryPath(me, root, { GZCOORD_DEFAULT_LOCALE_ONLY: '1' }), null);
  // A value that reads as "no" must not pin.
  for (const off of ['0', 'false', 'no', 'off', '']) {
    assert.equal(localeReminder(me, root, { GZCOORD_DEFAULT_LOCALE_ONLY: off }), ' - ᲛᲘᲜᲘᲨᲜᲔᲑᲐ', off);
    assert.ok(dictionaryPath(me, root, { GZCOORD_DEFAULT_LOCALE_ONLY: off }), off);
  }
});

test('a default-locale login renders exactly what it rendered before a dictionary existed', () => {
  const out = render(fixture(), ME, 'gzapp:gzcoord', undefined, {});
  assert.match(out, /^gzcoord inbox for h\/me \(language-culture\): 1 for you, 1 not addressed to you, on gzapp:gzcoord$/m);
  assert.match(out, /^Not addressed to you — listed, bodies not read \(SPEC §17\):$/m);
  assert.match(out, /^--- relay seq 1, from h\/sender, 2026-09-21T08:00:00Z$/m);
});
