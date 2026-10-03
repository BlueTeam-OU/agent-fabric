import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { spawnSync } from 'node:child_process';
import os from 'node:os';
import path from 'node:path';
import { parse, validate, columns, normalize, loadTaxonomy, findTaxonomy, slugOf, recordedRole, parseArgs, nearestKnownKey, whoami } from '../scripts/gzmsg.mjs';
import { fileURLToPath } from 'node:url';

const taxonomy = loadTaxonomy(fileURLToPath(new URL('../../../identities/roles/catalog.json', import.meta.url)));

const gzmsg = (...args) =>
  spawnSync(process.execPath, [fileURLToPath(new URL('../scripts/gzmsg.mjs', import.meta.url)), ...args],
            { encoding: 'utf8' });

// The format document's own inline examples are copied as much as the
// files under examples/: every fenced block that opens with the protocol
// header must validate under the deployment's catalogue, ids elided
// ("01a0…") tolerated. The one under "Asking for an undo" was a REQUEST
// addressed TO-ROLE — the shape §13 now refuses — for a day after the rule.
test('every inline GZCOORD example in MESSAGE-FORMAT.md validates', () => {
  const doc = fs.readFileSync(new URL('../protocol/MESSAGE-FORMAT.md', import.meta.url), 'utf8');
  // The §Shape template ("[GZCOORD/1] TYPE", placeholder keys) is the grammar shown, not a message.
  const blocks = [...doc.matchAll(/```text\n(\[GZCOORD\/1\] (?!TYPE\b)[^\n]*\n[\s\S]*?)```/g)].map(m => m[1]);
  assert.ok(blocks.length >= 2, `expected the document's inline examples, found ${blocks.length}`);
  for (const b of blocks) {
    // [ \t]*, never \s*: with the m flag \s* eats the newline and the blank
    // line that separates metadata from body, gluing NOTES: onto the block.
    const text = b.replace(/^(MESSAGE-ID|IN-REPLY-TO): .*…[ \t]*$/gm, (line, key) => `${key}: 01a09fc1-0000-7000-8000-000000000000`);
    const r = validate(text, { taxonomy });
    assert.deepEqual(r.errors, [], `${b.split('\n')[0]} / ${b.match(/^SUBJECT: (.*)$/m)?.[1] ?? '(no subject)'}: ${r.errors}`);
  }
});

for (const name of ['observation','observation-diagnosis','reply','review']) {
  test(`${name} example is valid`, () => {
    const text = fs.readFileSync(new URL(`../protocol/examples/${name}.txt`, import.meta.url), 'utf8');
    // Under the deployment's catalogue: the examples are what sessions copy.
    const result = validate(text, { taxonomy });
    assert.deepEqual(result.errors, []);
    assert.deepEqual(result.warnings, []);
  });
}

test('runtime model must not leak into protocol', () => {
  const text = `[GZCOORD/1] INFO\nFROM: develop-gzapp/gzapp\nROLE: Application Architect\nPROJECT: gzapp\nMESSAGE-ID: test-0001\nBROADCAST: true\nMODEL: secret-model\n`;
  assert.equal(validate(text).ok, false);
});

test('normal messages require a routing target or broadcast', () => {
  const text = `[GZCOORD/1] INFO\nFROM: develop-gzapp/gzapp\nROLE: Application Architect\nPROJECT: gzapp\nMESSAGE-ID: test-0001\n`;
  assert.equal(validate(text).ok, false);
});

test('address is logical host/instance', () => {
  const text = `[GZCOORD/1] INFO\nFROM: /srv/gzapp/mobile\nROLE: Mobile Engineer\nPROJECT: gzapp\nMESSAGE-ID: test-0001\nBROADCAST: true\n`;
  assert.deepEqual(validate(text).errors, ['FROM must be <host>/<instance>']);
});

// One entry per runtime/transport term SPEC.md §14-§15 keeps off the wire,
// in the spelling the spec itself uses — a near-miss spelling in FORBIDDEN
// silently admits the exact field the spec names.
test('transport-native identifiers are forbidden core metadata', () => {
  for (const field of ['TELEGRAM-CHAT-ID','SLACK-CHANNEL-ID','DISCORD-GUILD-ID',
                       'TOKEN-BUDGET','REASONING-BUDGET',
                       'MODEL','PROVIDER','WORKING-DIRECTORY','SUBAGENT-DEPTH']) {
    const text = `[GZCOORD/1] INFO\nFROM: develop-gzapp/gzapp\nROLE: Application Architect\nPROJECT: gzapp\nMESSAGE-ID: test-0001\nBROADCAST: true\n${field}: leaked\n`;
    assert.equal(validate(text).ok, false, `${field} must be rejected`);
  }
});

test('a malformed metadata line is reported, not silently dropped', () => {
  // `_` is not a metadata key character, so this never became metadata and the
  // forbidden-field check could not see it — the message validated clean while
  // carrying runtime config the sender believed it had sent.
  const text = `[GZCOORD/1] INFO\nFROM: develop-gzapp/gzapp\nROLE: Application Architect\nPROJECT: gzapp\nMESSAGE-ID: test-0001\nBROADCAST: true\nTOKEN_BUDGET: leaked\n`;
  const result = validate(text);
  assert.equal(result.ok, false);
  assert.ok(result.errors.some(e => e.includes('TOKEN_BUDGET')));
  assert.equal(result.message.metadata.TOKEN_BUDGET, undefined);
});

test('body lines after a section marker are never malformed metadata', () => {
  const text = `[GZCOORD/1] INFO\nFROM: develop-gzapp/gzapp\nROLE: Application Architect\nPROJECT: gzapp\nMESSAGE-ID: test-0001\nBROADCAST: true\n\nNOTES:\nplain prose, no colon at all\nTOKEN_BUDGET: quoted from another message\n`;
  assert.deepEqual(validate(text).errors, []);
});

test('TO must be a logical address when present', () => {
  const text = `[GZCOORD/1] INFO\nFROM: develop-gzapp/gzapp\nROLE: Application Architect\nPROJECT: gzapp\nMESSAGE-ID: test-0001\nTO: @telegram_username\n`;
  assert.equal(validate(text).ok, false);
});

test('a repeated section marker resumes the section instead of replacing it', () => {
  // MESSAGE-FORMAT.md does not require section names to be unique, so a second
  // marker used to blank the first block and still validate clean — the sender
  // was told the message was good while half its content was gone.
  const text = `[GZCOORD/1] INFO\nFROM: develop-gzapp/gzapp\nROLE: Application Architect\nPROJECT: gzapp\nMESSAGE-ID: test-0001\nBROADCAST: true\n\nNOTES:\nfirst block\n\nNOTES:\nsecond block\n`;
  const msg = parse(text);
  assert.ok(msg.sections.NOTES.includes('first block'));
  assert.ok(msg.sections.NOTES.includes('second block'));
  assert.deepEqual(validate(text).errors, []);
});

test('metadata block ends at the first section marker', () => {
  const text = `[GZCOORD/1] INFO\nFROM: develop-gzapp/gzapp\nROLE: Application Architect\nPROJECT: gzapp\nMESSAGE-ID: test-0001\nBROADCAST: true\n\nREFERENCES:\nPR: #184\n- path: contracts/passenger/eta.yaml\n\nNOTES:\nKEY: value shaped lines stay in the body.\n`;
  const msg = parse(text);
  assert.equal(msg.metadata.PR, undefined);
  assert.equal(msg.metadata.KEY, undefined);
  assert.ok(msg.sections.REFERENCES.includes('PR: #184'));
  assert.ok(msg.sections.NOTES.includes('KEY: value shaped lines'));
  assert.equal(validate(text).ok, true);
});

// SPEC §7.4: REPLY-EXPECTED is an optional common field, so it must pass as
// ordinary metadata and survive the forbidden-field check untouched.
test('REPLY-EXPECTED is ordinary optional metadata', () => {
  const text = `[GZCOORD/1] INFO\nFROM: develop-gzapp/gzapp\nROLE: Application Architect\nPROJECT: gzapp\nMESSAGE-ID: test-0001\nBROADCAST: true\nREPLY-EXPECTED: no\n`;
  const result = validate(text);
  assert.deepEqual(result.errors, []);
  assert.equal(result.message.metadata['REPLY-EXPECTED'], 'no');
});

// SPEC §7.4 gives REPLY-EXPECTED a closed grammar, and the relay procedure
// makes senders rely on this validator — so a value outside it must fail
// here, not reach the carrier with undefined reply semantics. Lowercase
// only, matching the exact-match convention for BROADCAST: true.
test('REPLY-EXPECTED rejects a value outside yes | no', () => {
  for (const value of ['maybe', 'Yes', 'NO', 'true']) {
    const text = `[GZCOORD/1] INFO\nFROM: develop-gzapp/gzapp\nROLE: Application Architect\nPROJECT: gzapp\nMESSAGE-ID: test-0001\nBROADCAST: true\nREPLY-EXPECTED: ${value}\n`;
    const result = validate(text);
    assert.equal(result.ok, false, `${value} must be rejected`);
    assert.ok(result.errors.some(e => e.includes('REPLY-EXPECTED')));
  }
});

test('REPLY-EXPECTED accepts yes and no', () => {
  for (const value of ['yes', 'no']) {
    const text = `[GZCOORD/1] INFO\nFROM: develop-gzapp/gzapp\nROLE: Application Architect\nPROJECT: gzapp\nMESSAGE-ID: test-0001\nBROADCAST: true\nREPLY-EXPECTED: ${value}\n`;
    assert.deepEqual(validate(text).errors, []);
  }
});

// SPEC §6: a repeated metadata key has no defined meaning, and last-write-wins
// let an invalid earlier value hide behind a valid later one — observed for
// REPLY-EXPECTED and for a malformed FROM, which §18 already MUST reject.
test('a duplicated metadata key is rejected even when the last value is valid', () => {
  for (const [dup, first, last] of [['REPLY-EXPECTED','maybe','no'], ['FROM','bad','develop-gzapp/gzapp']]) {
    const base = dup === 'FROM' ? '' : 'FROM: develop-gzapp/gzapp\n';
    const text = `[GZCOORD/1] INFO\n${base}${dup}: ${first}\n${dup}: ${last}\nROLE: Application Architect\nPROJECT: gzapp\nMESSAGE-ID: test-0001\nBROADCAST: true\n`;
    const result = validate(text);
    assert.equal(result.ok, false, `${dup} duplicate must be rejected`);
    assert.ok(result.errors.some(e => e.includes(dup) && e.includes('more than once')));
  }
});

test('a message with no duplicated key reports none', () => {
  const text = `[GZCOORD/1] INFO\nFROM: develop-gzapp/gzapp\nROLE: Application Architect\nPROJECT: gzapp\nMESSAGE-ID: test-0001\nBROADCAST: true\nREPLY-EXPECTED: no\n`;
  const result = validate(text);
  assert.deepEqual(result.errors, []);
  assert.deepEqual(result.message.duplicateKeys, []);
});

// A relay-indented marker is body text by §6 and the message validates, so
// the "ask for a re-send on failure" rule never fires. The validator warns
// instead of failing — content may legitimately look like this — and never
// promotes the line to a marker.
test('an indented marker-shaped body line warns instead of silently merging', () => {
  const text = `[GZCOORD/1] INFO\nFROM: develop-gzapp/gzapp\nROLE: Application Architect\nPROJECT: gzapp\nMESSAGE-ID: test-0001\nBROADCAST: true\n\nNOTES:\n  first body line\n REFERENCES:\n  - path: contracts/passenger/eta.yaml\n`;
  const result = validate(text);
  assert.equal(result.ok, true);
  assert.deepEqual(result.errors, []);
  assert.ok(result.warnings.some(w => w.includes('REFERENCES')));
  assert.equal(result.message.sections.REFERENCES, undefined);
});

// A header the parser cannot read used to escape validate() as an uncaught
// exception — a stack trace on the CLI, and a caller that could not tell a
// bad header from a crashed validator.
test('a bad first line is a validation error, not an exception', () => {
  for (const first of ['GZCOORD/1 INFO', '[GZCOORD/2] INFO', '[GZCOORD/1] INFO ', '[GZCOORD/1] info']) {
    const result = validate(`${first}\nFROM: develop-gzapp/gzapp\nROLE: Application Architect\nPROJECT: gzapp\n`);
    assert.equal(result.ok, false, `${JSON.stringify(first)} must be rejected`);
    assert.ok(result.errors.some(e => e.includes('first line')));
    assert.equal(result.message, null);
  }
});

test('a leading byte-order mark does not invalidate the header', () => {
  const text = `\uFEFF[GZCOORD/1] INFO\nFROM: develop-gzapp/gzapp\nROLE: Application Architect\nPROJECT: gzapp\nMESSAGE-ID: test-0001\nBROADCAST: true\n`;
  assert.deepEqual(validate(text).errors, []);
});

test('validate CLI reports a bad first line on one line and exits 1', () => {
  const file = new URL('./bad-first-line.tmp.txt', import.meta.url);
  fs.writeFileSync(file, 'GZCOORD/1 INFO\nFROM: develop-gzapp/gzapp\nROLE: Tester\nPROJECT: gzapp\nMESSAGE-ID: test-0001\nBROADCAST: true\n');
  try {
    const bad = gzmsg('validate', fileURLToPath(file));
    assert.equal(bad.status, 1);
    // The LAST line: a tool may say something else first — a login whose
    // locale is pinned away is told so — and an assertion that forbids any
    // other line is testing the absence of diagnostics, not this behaviour.
    assert.equal(bad.stderr.trim().split('\n').pop(), 'invalid GZCOORD/1 first line');
    assert.equal(bad.stdout, '');
  } finally { fs.unlinkSync(file); }
});

// SPEC §7.1: BROADCAST has one value. Any other spelling either fell through
// to the routing error — which named the wrong fault — or, next to a TO,
// validated clean with a meaning the spec does not define.
test('BROADCAST rejects a value other than true', () => {
  for (const [value, routing] of [['yes', ''], ['True', ''], ['false', 'TO: develop-gzapp/web\n'], ['1', 'TO-ROLE: Web Engineer\n']]) {
    const text = `[GZCOORD/1] INFO\nFROM: develop-gzapp/gzapp\nROLE: Application Architect\nPROJECT: gzapp\nMESSAGE-ID: test-0001\n${routing}BROADCAST: ${value}\n`;
    const result = validate(text);
    assert.equal(result.ok, false, `${value} must be rejected`);
    assert.ok(result.errors.some(e => e.startsWith('BROADCAST must be true')), `${value}: ${result.errors}`);
  }
});

test('BROADCAST: true routes on its own, and absent BROADCAST is not an error', () => {
  assert.deepEqual(validate(`[GZCOORD/1] INFO\nFROM: develop-gzapp/gzapp\nROLE: Application Architect\nPROJECT: gzapp\nMESSAGE-ID: test-0001\nBROADCAST: true\n`).errors, []);
  assert.deepEqual(validate(`[GZCOORD/1] INFO\nFROM: develop-gzapp/gzapp\nROLE: Application Architect\nPROJECT: gzapp\nMESSAGE-ID: test-0001\nTO: develop-gzapp/web\n`).errors, []);
});

// Trailing whitespace is the other way a marker stops being one, and the
// only way that is invisible in a terminal. Same warning, same rule: named,
// never promoted.
test('a marker-shaped body line with trailing whitespace warns instead of silently merging', () => {
  const text = `[GZCOORD/1] INFO\nFROM: develop-gzapp/gzapp\nROLE: Application Architect\nPROJECT: gzapp\nMESSAGE-ID: test-0001\nBROADCAST: true\n\nNOTES:\nbody\nREFERENCES: \n- adr: ADR-001\n`;
  const result = validate(text);
  assert.equal(result.ok, true);
  assert.ok(result.warnings.some(w => w.includes('REFERENCES')));
  assert.equal(result.message.sections.REFERENCES, undefined);
  assert.ok(result.message.sections.NOTES.includes('- adr: ADR-001'));
});

test('an empty-valued metadata key warns, and the CLI prints the warning beside the errors', () => {
  const text = `[GZCOORD/1] INFO\nFROM: develop-gzapp/gzapp\nROLE: Application Architect\nPROJECT: gzapp\nMESSAGE-ID: test-0001\nBROADCAST: true\nNOTES: \nbody here\n`;
  const result = validate(text);
  assert.equal(result.ok, false);
  assert.ok(result.warnings.some(w => w.startsWith('NOTES has an empty value')));
  const file = new URL('./empty-value.tmp.txt', import.meta.url);
  fs.writeFileSync(file, text);
  try {
    const run = gzmsg('validate', fileURLToPath(file));
    assert.equal(run.status, 1);
    assert.match(run.stderr, /^warning: NOTES has an empty value/m);
    assert.match(run.stderr, /unparsable line in the metadata block: body here/);
  } finally { fs.unlinkSync(file); }
});

// HUMAN-RELAY-TRANSPORT.md "Sending" caps lines at 72 because a terminal
// copy re-breaks longer ones and a re-broken metadata line is no longer
// metadata. Nothing enforced it; three of the five examples broke it.
test('a line over 72 characters warns, naming the line, and stays valid', () => {
  const long = 'x'.repeat(73);
  const text = `[GZCOORD/1] INFO\nFROM: develop-gzapp/gzapp\nROLE: Application Architect\nPROJECT: gzapp\nMESSAGE-ID: test-0001\nBROADCAST: true\nSPECIALTIES: ${long}\n\nABOUT:\n${long}\n`;
  const result = validate(text);
  assert.equal(result.ok, true);
  const lines = result.warnings.filter(w => w.includes('re-breaks it'));
  assert.equal(lines.length, 2);
  assert.match(lines[0], /^line 7 is 86 columns wide; over 72 a terminal copy re-breaks it/);
  assert.match(lines[1], /^line 10 is 73 columns wide/);
  // Off (the bridge path): no width warning at any length.
  assert.deepEqual(validate(text, { maxColumns: 0 }).warnings.filter(w => w.includes('columns wide')), []);
  // Exactly 72 is inside the limit.
  assert.deepEqual(validate(`[GZCOORD/1] INFO\nFROM: develop-gzapp/gzapp\nROLE: Application Architect\nPROJECT: gzapp\nMESSAGE-ID: test-0001\nBROADCAST: true\n\nNOTES:\n${'y'.repeat(72)}\n`).warnings, []);
});

test('validate prints the line-length warning on stderr and still passes the message', () => {
  const file = new URL('./long-line.tmp.txt', import.meta.url);
  fs.writeFileSync(file, `[GZCOORD/1] INFO\nFROM: develop-gzapp/gzapp\nROLE: Tester\nPROJECT: gzapp\nMESSAGE-ID: test-0001\nBROADCAST: true\nSPECIALTIES: ${'z'.repeat(80)}\n`);
  try {
    const ok = gzmsg('validate', '--no-taxonomy', fileURLToPath(file));
    assert.equal(ok.status, 0, ok.stderr);
    assert.match(ok.stderr, /^warning: line 7 is 93 columns wide/m);
    assert.equal(ok.stdout, 'valid GZCOORD/1 message\n');
  } finally { fs.unlinkSync(file); }
});

// SPEC §6: the well-formed separator is one space; a tab or nothing is not
// a separator (normative), and a reader MAY accept a run of spaces and trim
// (an allowance — this pins what the reference does, not what a conforming
// parser must). Nothing pinned any of it: a regex that dropped the space
// requirement altogether left every test green.
test('reference parser: separator is one space, tolerates a run, rejects tab and nothing', () => {
  const base = 'ROLE: Application Architect\nPROJECT: gzapp\nMESSAGE-ID: test-0001\nBROADCAST: true\n';
  for (const [line, ok] of [['FROM: develop-gzapp/gzapp', true], ['FROM:   develop-gzapp/gzapp   ', true],
                            ['FROM:develop-gzapp/gzapp', false], ['FROM:\tdevelop-gzapp/gzapp', false]]) {
    const result = validate(`[GZCOORD/1] INFO\n${line}\n${base}`);
    assert.equal(result.ok, ok, JSON.stringify(line));
    if (ok) assert.equal(result.message.metadata.FROM, 'develop-gzapp/gzapp');
    else assert.ok(result.errors.some(e => e.startsWith('unparsable line in the metadata block: FROM')), JSON.stringify(line));
  }
});

// The relay re-breaks on columns, and String.length is UTF-16 code units:
// 40 CJK characters counted 49 and rendered at 89, no warning; 40 combining
// sequences counted 89 and rendered at 49, a false warning. Each row is
// what `wc -L` reports for the same line.
test('columns() approximates terminal width where String.length does not', () => {
  for (const [line, width] of [
    ['SUBJECT: ' + '\u7DDA'.repeat(40), 89],          // CJK: 2 each
    ['SUBJECT: ' + '\u{1F68C}'.repeat(40), 89],       // wide emoji: 2 each
    ['SUBJECT: ' + '\u00A9'.repeat(32), 41],          // text-default pictograph ©: 1 each
    ['SUBJECT: instance\u2194instance', 26],           // ↔ as the repo writes it: 1
    ['SUBJECT: \u{1F1EC}\u{1F1EA}', 11],              // flag pair: 2 total, not 4
    ['SUBJECT: ' + '\uFF21'.repeat(32), 73],          // fullwidth Latin: 2 each (was 1)
    ['SUBJECT: \u3000\u3001\u3002', 15],              // ideographic space and punctuation: 2 each
    ['SUBJECT: ' + '\uFF76'.repeat(40), 49],          // halfwidth katakana: 1 each (was 2, a false warning)
    ['SUBJECT: ' + '\u{1B001}'.repeat(40), 89],       // kana supplement: 2, outside the classic table
    ['SUBJECT: ' + '\u{1D400}'.repeat(40), 49],       // narrow astral: 1 each
    ['SUBJECT: ' + 'e\u0301'.repeat(40), 49],         // combining: 0
    ['SUBJECT: \u10DB\u10D0\u10E0\u10E8 \u043C\u0430\u0440\u0448', 18], // Georgian, Cyrillic: 1 each
    ['SUBJECT: a\tb', 17],                           // tab to next multiple of 8
    ['x'.repeat(72), 72],
    ['SUBJECT: ' + '\u2630'.repeat(36), 81],          // trigrams: Wide since Unicode 16, missed by the classic table
  ]) assert.equal(columns(line), width, JSON.stringify(line.slice(0, 20)));
  // Every boundary of the range table, from both sides, so an off-by-one
  // or a deleted range cannot pass: [code point, width]. A hand-written
  // table ships exactly this class of error. Rows expecting 0 are
  // combining or format characters decided by the ZERO branch before
  // the table is consulted; they pin that branch, not a boundary, so
  // every range edge also has a real neighbour with width 1 or 2.
  for (const [cp, width] of [
    [0x10FF, 1], [0x1100, 2], [0x115F, 2], [0x1160, 1],   // Jamo; U+1160 (filler) is EAW N, outside the range — `wc -L` says 0, a known deviation
    [0x2328, 1], [0x2329, 2], [0x232A, 2], [0x232B, 1],
    [0x262F, 1], [0x2630, 2], [0x2637, 2], [0x2638, 1], [0x2689, 1], [0x268A, 2], [0x268F, 2], [0x2690, 1],
    [0x2E7F, 1], [0x2E80, 2], [0x303E, 2], [0x303F, 1], [0x3040, 1], [0x3041, 2], [0x3248, 2], [0x33FF, 2],
    [0x3400, 2], [0x4DBF, 2], [0x4DC0, 2], [0x4DFF, 2], [0x4E00, 2], [0x9FFF, 2], [0xA000, 2], [0xA4CF, 2], [0xA4D0, 1],
    [0xA95F, 1], [0xA960, 2], [0xA97C, 2], [0xA97F, 2], [0xA980, 0], [0xABFF, 1], [0xAC00, 2], [0xD7A3, 2], [0xD7A4, 1],
    [0xF8FF, 1], [0xF900, 2], [0xFAFF, 2], [0xFB00, 1], [0xFE0F, 0], [0xFE10, 2], [0xFE19, 2], [0xFE1A, 1],
    [0xFE2F, 0], [0xFE30, 2], [0xFE4F, 2], [0xFE50, 2], [0xFE6B, 2], [0xFE6C, 1],
    [0xFEFF, 0], [0xFF00, 2], [0xFF60, 2], [0xFF61, 1], [0xFF9F, 1], [0xFFDF, 1], [0xFFE0, 2], [0xFFE6, 2], [0xFFE7, 1],
    [0x16FDF, 1], [0x16FE0, 2], [0x16FF1, 2], [0x16FF2, 2], [0x16FFF, 2], [0x17000, 2], [0x18AFF, 2],
    [0x18B00, 2], [0x18CD5, 2], [0x18CFF, 2], [0x18D00, 2], [0x18D08, 2], [0x18D09, 2],   // Khitan Small Script, its own range
    [0x18D8F, 2], [0x18D90, 2], [0x18DF2, 2], [0x18DFF, 2], [0x18E00, 1],   // Tangut Supplement to its Unicode 17 block end
    [0x1AFEF, 1], [0x1AFF0, 2], [0x1B000, 2], [0x1B001, 2], [0x1B2FB, 2], [0x1B2FF, 2], [0x1B300, 1],
    [0x1D2FF, 1], [0x1D300, 2], [0x1D376, 2], [0x1D377, 1], [0x1F1FF, 1], [0x1F200, 2], [0x1F26F, 2], [0x1F270, 1],
    [0x1FFFD, 1], [0x20000, 2], [0x2FFFD, 2], [0x2FFFE, 1], [0x30000, 2], [0x3FFFD, 2], [0x3FFFE, 1],
  ]) assert.equal(columns(String.fromCodePoint(cp)), width, `U+${cp.toString(16).toUpperCase()}`);
  const head = 'FROM: develop-gzapp/gzapp\nROLE: Application Architect\nPROJECT: gzapp\nBROADCAST: true\n';
  const cjk = validate(`[GZCOORD/1] INFO\n${head}SUBJECT: ${'\u7DDA'.repeat(40)}\n`);
  assert.ok(cjk.warnings.some(w => w.startsWith('line 6 is 89 columns wide')), cjk.warnings);
  const combining = validate(`[GZCOORD/1] INFO\n${head}SUBJECT: ${'e\u0301'.repeat(40)}\n`);
  assert.deepEqual(combining.warnings, []);
});

// The address outlives a session; the counter has to. A session that
// restarted at 0001 repeated four numbers a peer had already seen.
// Superseded by the mint tests: the sequential counter this test pinned is
// gone (ids are UUIDv7, minted unique by construction — no counter file,
// nothing to continue across processes).

// The relay indents on paste — every line by two, the first by one, a
// single marker by a third — observed twice on the first day. normalize()
// is the documented two-step rule: metadata block stripped
// unconditionally, body stripped only of a uniform prefix, never a body
// line reclassified by shape.
test('normalize undoes paste indentation without reclassifying body text', () => {
  const pasted = ' [GZCOORD/1] INFO\n  FROM: develop-gzapp/gzapp\n  ROLE: Application Architect\n  PROJECT: gzapp\nMESSAGE-ID: test-0001\n  BROADCAST: true\n  \n  NOTES:\n  first\n   NOTES:\n  second\n  \n  REFERENCES:\n  - adr: ADR-001\n';
  const text = normalize(pasted);
  assert.match(text, /^\[GZCOORD\/1\] INFO\nFROM: /);
  const result = validate(text);
  assert.deepEqual(result.errors, []);
  assert.ok(result.message.sections.REFERENCES.includes('- adr: ADR-001'));
  // The odd-one-out marker keeps its one extra space and is warned about, not promoted.
  assert.ok(result.message.sections.NOTES.includes(' NOTES:'));
  assert.ok(result.warnings.some(w => w.includes('swallowed section marker')));
  // The carrier prefix comes from the metadata block, never from the body:
  // a clean message whose only section is uniformly indented keeps it,
  // and a content line shaped like a marker stays content.
  const cleanIndented = '[GZCOORD/1] INFO\nFROM: develop-gzapp/gzapp\nROLE: R\nPROJECT: gzapp\nMESSAGE-ID: test-0001\nBROADCAST: true\n\nNOTES:\n  the config we discussed:\n  YAML:\n  key: value\n';
  assert.equal(normalize(cleanIndented), cleanIndented);
  assert.deepEqual(Object.keys(validate(cleanIndented).message.sections), ['NOTES']);
  // Under a uniform paste the sender's indented marker-shaped line comes
  // back indented and stays body; a marker-shaped line at exactly the
  // carrier prefix was written at column 0 and is a marker.
  const uniform = normalize('  [GZCOORD/1] INFO\n  FROM: develop-gzapp/gzapp\n  ROLE: R\n  PROJECT: gzapp\nMESSAGE-ID: test-0001\n  BROADCAST: true\n\n  NOTES:\n  flush\n    YAML:\n  key: value\n  REFERENCES:\n  - adr: ADR-001\n');
  assert.equal(uniform, '[GZCOORD/1] INFO\nFROM: develop-gzapp/gzapp\nROLE: R\nPROJECT: gzapp\nMESSAGE-ID: test-0001\nBROADCAST: true\n\nNOTES:\nflush\n  YAML:\nkey: value\nREFERENCES:\n- adr: ADR-001\n');
  assert.deepEqual(Object.keys(validate(uniform).message.sections), ['NOTES', 'REFERENCES']);
  // The first marker is not the source: a paste that indented it oddly
  // still strips the body by the metadata block's prefix.
  const oddFirstMarker = normalize(' [GZCOORD/1] INFO\n  FROM: develop-gzapp/gzapp\n  ROLE: R\n  PROJECT: gzapp\nMESSAGE-ID: test-0001\n  BROADCAST: true\n  \n   NOTES:\n  first\n  \n  REFERENCES:\n  - adr: ADR-001\n');
  assert.ok(validate(oddFirstMarker).message.sections.REFERENCES.includes('- adr: ADR-001'));
  // Already-clean input is unchanged, and a message with no body is handled.
  for (const name of ['observation','observation-diagnosis','reply','review']) {
    const clean = fs.readFileSync(new URL(`../protocol/examples/${name}.txt`, import.meta.url), 'utf8');
    assert.equal(normalize(clean), clean, name);
  }
  assert.equal(normalize('  [GZCOORD/1] INFO\n  FROM: a/b\n  ROLE: R\n  PROJECT: p\n'), '[GZCOORD/1] INFO\nFROM: a/b\nROLE: R\nPROJECT: p\n');
});

test('normalize CLI prints the normalised message for validate to read', () => {
  const file = new URL('./pasted.tmp.txt', import.meta.url);
  fs.writeFileSync(file, '  [GZCOORD/1] INFO\n  FROM: develop-gzapp/gzapp\n  ROLE: Tester\n  PROJECT: gzapp\nMESSAGE-ID: test-0001\n  BROADCAST: true\n');
  try {
    const run = gzmsg('normalize', fileURLToPath(file));
    assert.equal(run.status, 0);
    assert.equal(run.stdout, '[GZCOORD/1] INFO\nFROM: develop-gzapp/gzapp\nROLE: Tester\nPROJECT: gzapp\nMESSAGE-ID: test-0001\nBROADCAST: true\n');
    assert.deepEqual(validate(run.stdout).errors, []);
  } finally { fs.unlinkSync(file); }
});

// SPEC §13: an assignment goes TO one instance. Both holders of a role
// executed one OBSERVATION with a REQUEST: section (2026-09-19, two PRs on
// the same hunk); a REQUEST type or a REQUEST:/ACCEPTANCE:/DELIVER-TO:
// section addressed TO-ROLE is refused, and the same body TO an instance
// or an INFO/DECISION/QUESTION TO-ROLE without those sections passes.
test('an assignment TO-ROLE is refused; the same TO an instance, and a non-assignment TO-ROLE, pass', () => {
  const head = t => `[GZCOORD/1] ${t}\nFROM: develop-gzapp/gzapp\nROLE: Application Architect\nPROJECT: gzapp\nMESSAGE-ID: test-0001\n`;
  let r = validate(`${head('REQUEST')}TO-ROLE: Web Engineer\n\nREQUEST:\nmove the line\n`);
  assert.ok(r.errors.some(e => e.includes('a REQUEST is an assignment')), r.errors);
  assert.deepEqual(validate(`${head('REQUEST')}TO: develop-gzapp/web\n\nREQUEST:\nmove the line\n`).errors, []);
  for (const section of ['REQUEST', 'ACCEPTANCE', 'DELIVER-TO']) {
    r = validate(`${head('OBSERVATION')}TO-ROLE: Web Engineer\n\nOBSERVATION:\nseen\n\n${section}:\nfix it\n`);
    assert.ok(r.errors.some(e => e.includes(`${section} section`) && e.includes('never TO-ROLE')), `${section}: ${r.errors}`);
    assert.deepEqual(validate(`${head('OBSERVATION')}TO: develop-gzapp/web\n\nOBSERVATION:\nseen\n\n${section}:\nfix it\n`).errors, [], section);
  }
  r = validate(`${head('OBSERVATION')}TO-ROLE: Web Engineer\n\nOBSERVATION:\nseen\n\nREQUEST:\nfix it\n\nACCEPTANCE:\nit is fixed\n`);
  assert.ok(r.errors.some(e => e.includes('REQUEST and ACCEPTANCE sections')), r.errors);
  for (const [type, body] of [['INFO', 'INFO:\nfyi\n'], ['DECISION', 'DECISION:\nso decided\n'], ['QUESTION', 'QUESTION:\nwhich?\n'], ['OBSERVATION', 'OBSERVATION:\nseen, no ask\n']])
    assert.deepEqual(validate(`${head(type)}TO-ROLE: Web Engineer\n\n${body}`).errors, [], type);
});

// SPEC §7.1: one addressing field, the delivery scope. Live traffic
// carried TO beside a TO-ROLE that matched no recorded role, and nothing
// noticed, because the address had already routed the message; a
// transport filtering by addressee could not obey two.
test('exactly one of TO, TO-ROLE, BROADCAST', () => {
  const head = '[GZCOORD/1] INFO\nFROM: develop-gzapp/gzapp\nROLE: Application Architect\nPROJECT: gzapp\nMESSAGE-ID: test-0001\n';
  for (const pair of ['TO: develop-gzapp/web\nTO-ROLE: Web Engineer\n', 'TO: develop-gzapp/web\nBROADCAST: true\n', 'BROADCAST: true\nTO-ROLE: Web Engineer\n']) {
    const r = validate(`${head}${pair}`);
    assert.equal(r.ok, false, pair);
    assert.ok(r.errors.some(e => e.includes('are exclusive')), r.errors);
  }
  for (const one of ['TO: develop-gzapp/web\n', 'TO-ROLE: Web Engineer\n', 'BROADCAST: true\n'])
    assert.deepEqual(validate(`${head}${one}`).errors, [], one);
  assert.ok(validate(head).errors.includes('missing TO, TO-ROLE or BROADCAST: true'), 'none at all');
});

// SPEC §8, §18: HELLO and GOODBYE are retired, and a parser rejects one
// naming the type as retired — with or without an addressing field, which
// the old special case forbade — while every other core type still passes.
test('HELLO and GOODBYE are rejected as retired; every other core type passes', () => {
  const head = type => `[GZCOORD/1] ${type}\nFROM: develop-gzapp/gzapp\nROLE: Application Architect\nPROJECT: gzapp\nMESSAGE-ID: test-0001\n`;
  for (const type of ['HELLO', 'GOODBYE']) {
    for (const addressing of ['', 'BROADCAST: true\n', 'TO: develop-gzapp/web\n']) {
      const r = validate(`${head(type)}${addressing}`);
      assert.equal(r.ok, false, `${type} ${JSON.stringify(addressing)}`);
      assert.ok(r.errors.includes(`${type} is retired (SPEC §8): whether an instance is running is presence, not an announcement`), r.errors);
      assert.ok(!r.errors.some(e => e.startsWith('unknown type')), r.errors);
    }
  }
  const file = new URL('./retired.tmp.txt', import.meta.url);
  fs.writeFileSync(file, `${head('HELLO')}BROADCAST: true\n`);
  try {
    const cli = gzmsg('validate', '--no-taxonomy', fileURLToPath(file));
    assert.equal(cli.status, 1);
    assert.match(cli.stderr, /^HELLO is retired \(SPEC §8\)/m);
  } finally { fs.unlinkSync(file); }
  for (const type of ['INFO', 'OBSERVATION', 'QUESTION', 'REQUEST', 'REVIEW', 'DECISION', 'HANDOFF', 'REPLY'])
    assert.deepEqual(validate(`${head(type)}TO: develop-gzapp/web\n`).errors, [], type);
});

// SPEC §4 deployment catalogue: ROLE and TO-ROLE are taxonomy slugs,
// matched by equality. One role was live in three spellings on the
// relay's first day. The address is NOT bound to the role: a role can
// change without the address changing (§4), and a legacy clone directory is a live
// clone holding backend-dev with no slug in its name — an earlier cut of
// this rule silenced it.
test('with a taxonomy, ROLE and TO-ROLE are slugs; the address is not bound to the role', () => {
  const ok = validate('[GZCOORD/1] INFO\nFROM: develop-qzapp/architect-cto-01\nROLE: architect-cto\nPROJECT: gzapp\nMESSAGE-ID: architect-cto-01-0033\nTO: develop-qzapp/gzapp-devex-tooling\n', { taxonomy });
  assert.deepEqual(ok.errors, []);
  assert.deepEqual(ok.warnings, [], 'a well-formed message under the profile warns about nothing');
  for (const role of ['Application Architect', 'Architect / CTO']) {
    const r = validate(`[GZCOORD/1] INFO\nFROM: develop-qzapp/architect-cto-01\nROLE: ${role}\nPROJECT: gzapp\nMESSAGE-ID: test-0001\nBROADCAST: true\n`, { taxonomy });
    assert.ok(r.errors.some(e => e.startsWith(`ROLE "${role}" is not a role slug`)), `${role}: ${r.errors}`);
  }
  // A role change without a rename: valid, with a warning naming the disagreement.
  const switched = validate('[GZCOORD/1] INFO\nFROM: develop-qzapp/architect-cto-01\nROLE: backend-dev\nPROJECT: gzapp\nMESSAGE-ID: test-0001\nBROADCAST: true\n', { taxonomy });
  assert.deepEqual(switched.errors, []);
  assert.ok(switched.warnings.some(w => w.startsWith('FROM names architect-cto but ROLE is backend-dev')), switched.warnings);
  // A clone named for no role is a session like any other, as sender and as addressee.
  assert.deepEqual(validate('[GZCOORD/1] INFO\nFROM: develop-qzapp/gzapp-claude2\nROLE: backend-dev\nPROJECT: gzapp\nMESSAGE-ID: test-0001\nBROADCAST: true\n', { taxonomy }).errors, []);
  assert.deepEqual(validate('[GZCOORD/1] INFO\nFROM: develop-qzapp/db-admin\nROLE: db-admin\nPROJECT: gzapp\nMESSAGE-ID: test-0001\nTO: develop-qzapp/gzapp-claude2\n', { taxonomy }).errors, []);
  for (const bad of ['Architect / CTO', 'Application Architect']) {
    const r = validate(`[GZCOORD/1] INFO\nFROM: develop-qzapp/db-admin\nROLE: db-admin\nPROJECT: gzapp\nMESSAGE-ID: test-0001\nTO-ROLE: ${bad}\n`, { taxonomy });
    assert.ok(r.errors.some(e => e.startsWith(`TO-ROLE "${bad}" is not a role slug`)), r.errors);
  }
  assert.deepEqual(validate('[GZCOORD/1] INFO\nFROM: develop-qzapp/db-admin\nROLE: db-admin\nPROJECT: gzapp\nMESSAGE-ID: test-0001\nTO-ROLE: architect-cto\n', { taxonomy }).errors, []);
  // Without a taxonomy none of this applies: the wire grammar is generic.
  assert.deepEqual(validate('[GZCOORD/1] INFO\nFROM: develop-qzapp/gzapp-claude2\nROLE: Anything\nPROJECT: gzapp\nMESSAGE-ID: test-0001\nTO-ROLE: Whoever\n').errors, []);
});

test('slugOf finds the longest whole-token slug an instance carries', () => {
  assert.equal(slugOf('agent-fabric-coordinator', taxonomy), 'fabric-coordinator');
  assert.equal(slugOf('legacy-old-role', taxonomy), undefined);   // renamed role: the old slug is not in the catalogue
  assert.equal(slugOf('architect-cto-01', taxonomy), 'architect-cto');
  assert.equal(slugOf('db-admin', taxonomy), 'db-admin');
  assert.equal(slugOf('legacy-clone-2', taxonomy), undefined);
  assert.equal(slugOf('web-developer', taxonomy), undefined);   // token match, not substring
  assert.ok(findTaxonomy(fileURLToPath(new URL('.', import.meta.url))).endsWith('/identities/roles/catalog.json'));
});

// A fixture for the derivation tests: a throwaway agent-fabric STATE
// directory holding this agent's binding (or none, or a broken one), with
// AGENT_FABRIC_STATE_DIR pointing at it for the duration so the CLI is
// kept off the developer's real binding. The catalogue is a temp copy.
// System temp, not the tests directory: a run interrupted between the
// mkdtemp and the finally would otherwise leave an untracked file in a
// tree whose workflow blesses `git add -A`.
const login = os.userInfo().username;
function fixtureRoot(state) {
  const root = scratch('gzcoord-fixture-');
  fs.mkdirSync(`${root}/state/agents/${login}`, { recursive: true });
  fs.copyFileSync(taxonomy.path, `${root}/catalog.json`);
  if (state !== undefined) fs.writeFileSync(`${root}/state/agents/${login}/binding.json`, state);
  return root;
}
// Synchronous callbacks only: the finally fires when fn RETURNS, so an
// async fn would have its fixture removed while still running.
const withFixture = (state, fn) => {
  const root = fixtureRoot(state);
  const saved = process.env.AGENT_FABRIC_STATE_DIR;
  process.env.AGENT_FABRIC_STATE_DIR = `${root}/state`;
  try {
    const r = fn(root, `${root}/catalog.json`);
    if (r instanceof Promise) throw new TypeError('withFixture takes a synchronous callback');
    return r;
  } finally {
    if (saved === undefined) delete process.env.AGENT_FABRIC_STATE_DIR; else process.env.AGENT_FABRIC_STATE_DIR = saved;
    fs.rmSync(root, { recursive: true, force: true });
  }
};
const bound = (role) => JSON.stringify({ agent: login, host: 'h', role, updated_at: 'x' });

test('whoami: the agent is the effective login, never the directory', () => {
  const me = whoami();
  assert.equal(me.agent, login);
  assert.notEqual(me.agent, path.basename(process.cwd()) === login ? 'x' : path.basename(process.cwd()));
});

// The derivation a session's identity runs on (inbox.mjs identity(), which
// the control plane's presence also reads), against a real binding file
// read through the real resolver: whoami() runs in-process under the
// fixture's AGENT_FABRIC_STATE_DIR. The login is overridden AFTER the
// binding is read, so a slug-carrying account name can be exercised from
// whatever login runs the suite.
const asLogin = (agent, me = whoami()) => ({ ...me, agent });
test('identity derives the slug from the login when no role is recorded', () => withFixture(undefined, (root, tax) => {
  const me = identity(asLogin('architect-cto-01'), loadTaxonomy(tax));
  assert.equal(me.slug, 'architect-cto');
  assert.equal(me.address, `${whoami().host}/architect-cto-01`);
  assert.equal(identity(asLogin('gzapp-claude2'), loadTaxonomy(tax)).slug, undefined, 'a login naming no role derives none');
}));

// The record wins over the login; a record the catalogue does not know
// is an error naming the file and the value; a malformed record warns,
// and the login's slug is what identity() is left with.
test('the recorded role wins over the login, and a recorded role outside the catalogue is an error', () => {
  withFixture(bound('backend-dev'), (root, tax) => {
    assert.equal(identity(asLogin('architect-cto-01'), loadTaxonomy(tax)).slug, 'backend-dev');
    assert.equal(identity(asLogin('architect-cto-01'), loadTaxonomy(tax)).roleError, undefined);
    assert.equal(recordedRole(loadTaxonomy(tax)).role, 'backend-dev');
    assert.match(recordedRole(loadTaxonomy(tax)).file, /binding\.json$/);
  });
  withFixture(bound('security-engineer'), (root, tax) => {
    const rec = recordedRole(loadTaxonomy(tax));
    assert.equal(rec.role, undefined);
    assert.match(rec.error, /binding\.json records role "security-engineer", which is not in .*catalog\.json; the login's role is used instead/);
    // The fallback is said: the error travels with the identity every caller prints.
    assert.match(identity(asLogin('architect-cto-01'), loadTaxonomy(tax)).roleError, /records role "security-engineer"/);
  });
  for (const state of ['not json', JSON.stringify({ agent: login, host: 'h', updated_at: 'x' })]) {
    withFixture(state, (root, tax) => {
      const cause = state === 'not json' ? /could not be read/ : /records no role/;
      assert.equal(recordedRole(loadTaxonomy(tax)).role, undefined);
      assert.match(recordedRole(loadTaxonomy(tax)).warning, cause);
      assert.equal(identity(asLogin('architect-cto-01'), loadTaxonomy(tax)).slug, 'architect-cto');
      assert.equal(identity(asLogin('gzapp-claude2'), loadTaxonomy(tax)).slug, undefined);
    });
  }
  assert.throws(() => withFixture(undefined, async () => {}), /synchronous callback/);
  // With a binding, the address and the role both come from the agent
  // (login + host) and what it is bound to.
  withFixture(JSON.stringify({ agent: login, host: 'h', role: 'web-dev', project: 'gzapp', updated_at: 'x' }), (root, tax) => {
    const me = identity(whoami(), loadTaxonomy(tax));
    assert.equal(me.address, `${os.hostname().split('.')[0]}/${login}`);
    assert.equal(me.slug, 'web-dev');
    // The project is the WORKING COPY's when the suite runs inside a
    // registered one (agent-fabric is a managed project itself); the
    // binding's project applies only outside any.
    assert.equal(me.project, whoami().project ?? 'gzapp');
  });
});

// Reported from live use: a message with no MESSAGE-ID, and one whose id
// sat under a bogus `ID:` key, both validated clean -- so nothing caught
// the error. MESSAGE-ID is now REQUIRED (§7.1): absence is an error, and
// a misspelled key still warns, never rejects (§6 preserves unknown
// metadata -- that is how the protocol extends).
test('a missing MESSAGE-ID is an error; a key that misspells one is named', () => {
  const head = '[GZCOORD/1] INFO\nFROM: develop-qzapp/db-admin\nROLE: db-admin\nPROJECT: gzapp\nBROADCAST: true\n';
  const none = validate(head);
  assert.equal(none.ok, false, 'required since #641');
  assert.ok(none.errors.some(e => e === 'missing MESSAGE-ID'), none.errors);

  const bogus = validate(`${head}ID: db-admin-0007\n`);
  assert.equal(bogus.ok, false, 'the bogus key does not satisfy the required field');
  assert.ok(bogus.errors.some(e => e === 'missing MESSAGE-ID'), bogus.errors);
  assert.ok(bogus.warnings.some(w => w === 'ID is not a known field — did you mean MESSAGE-ID?'), bogus.warnings);

  // Caught by the value's shape rather than the key's spelling.
  const msgid = validate(`${head}MSG-ID: db-admin-0007\n`);
  assert.ok(msgid.warnings.some(w => w.startsWith('MSG-ID carries an id-shaped value')), msgid.warnings);

  // A real id silences everything.
  const good = validate(`${head}MESSAGE-ID: db-admin-0007\n`);
  assert.deepEqual(good.warnings, []);

  // The converse, seen live (seq 3445): the id field holds the shell
  // variable's NAME. Valid — §7.2 keeps the id opaque — but said.
  const unexpanded = validate(`${head}MESSAGE-ID: $ID\n`);
  assert.equal(unexpanded.ok, true, 'the grammar admits any identifier');
  assert.ok(unexpanded.warnings.some(w => w === 'MESSAGE-ID is the literal $ID — the shell variable was not expanded; mint the id with gzmsg.mjs new-id and write its value'), unexpanded.warnings);
  const odd = validate(`${head}MESSAGE-ID: 01a09fc1-0000-7000-8000-000000000001\nIN-REPLY-TO: yesterday's message\n`);
  assert.ok(odd.warnings.some(w => w.startsWith("IN-REPLY-TO is yesterday's message, not an identifier this deployment mints")), odd.warnings);
});

test('unknown fields that are real extensions stay silent — §6 preserves them', () => {
  const head = '[GZCOORD/1] INFO\nFROM: develop-qzapp/db-admin\nROLE: db-admin\nPROJECT: gzapp\nBROADCAST: true\nMESSAGE-ID: db-admin-0007\n';
  for (const key of ['X-PRIORITY', 'X-TRACE', 'SEVERITY', 'DEADLINE', 'ATTN', 'THREAD', 'LOCALE']) {
    const r = validate(`${head}${key}: something\n`);
    assert.deepEqual(r.warnings, [], `${key} must not warn`);
    assert.equal(r.message.metadata[key], 'something', `${key} must be preserved`);
  }
  for (const [key, want] of [['ID','MESSAGE-ID'], ['MESSAGEID','MESSAGE-ID'], ['IN-REPLY','IN-REPLY-TO'], ['SUBJET','SUBJECT']])
    assert.equal(nearestKnownKey(key), want, key);
  for (const key of ['FROM', 'TO-ROLE', 'X-PRIORITY', 'MSG-ID'])
    assert.equal(nearestKnownKey(key), undefined, key);
});

// MESSAGE-ID is minted UUIDv7 (RFC 9562): time-ordered, unique without
// coordination, no shared counter state. The sequential counter this
// replaces existed for loss visibility on the lossy human relay; the
// durable carrier has no gap to detect, and the counter was the
// subsystem's largest defect source — five incidents. SPEC §7.2 says
// "opaque identifier": the format is a deployment convention.
test('mintId: RFC 9562 v7 shape, unique across calls, time-ordered', async () => {
  const { mintId } = await import('../scripts/gzmsg.mjs');
  const ids = Array.from({ length: 5 }, () => mintId());
  for (const id of ids) assert.match(id, /^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/, id);
  assert.equal(new Set(ids).size, ids.length, 'distinct');
  // The 48-bit ms timestamp is the ordering guarantee: non-decreasing
  // across mints. Within one millisecond the random part is random, so
  // full lexicographic order is NOT a v7 property and is not asserted.
  const ts = ids.map(id => parseInt(id.slice(0, 12).replace('-', ''), 16));
  for (let i = 1; i < ts.length; i++) assert.ok(ts[i] >= ts[i-1], `timestamp regressed: ${ids[i-1]} then ${ids[i]}`);
});

test('new-id CLI mints; next-id is gone; --seed is refused', () => {
  const a = gzmsg('new-id');
  assert.equal(a.status, 0, a.stderr);
  assert.match(a.stdout.trim(), /^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
  const b = gzmsg('next-id');
  assert.equal(b.status, 2, 'the counter-era name is an unknown command, not an alias');
  assert.match(b.stderr, /usage:/);
  // new-id declares no flags at all, so the generic unknown-flag refusal
  // fires before the retired-flag message is reachable.
  {
    const r = gzmsg('new-id', '--seed', '9');
    assert.equal(r.status, 2);
    assert.match(r.stderr, /unknown flag --seed/);
  }
});

// A checkout that predated --peek once accepted `next-id --peek` (the
// retired counter command) in silence and took a number: a gap nothing
// could fill. Every flag a command takes is now declared, and an
// unrecognised one is refused BEFORE any side effect.
test('parseArgs: unknown, valueless, repeated and surplus arguments are refused', () => {
  const spec = { valued: ['instance', 'seed'], boolean: ['peek'], positional: 0 };
  assert.deepEqual(parseArgs(['--instance', 'x', '--peek'], spec), { flags: { instance: 'x', peek: true }, positional: [] });
  assert.throws(() => parseArgs(['--instance', 'x', '--seeed', '9'], spec), /unknown flag --seeed; this command takes --instance, --seed, --peek/);
  assert.throws(() => parseArgs(['--instance', 'x', '--seed'], spec), /--seed needs a value/);
  assert.throws(() => parseArgs(['--seed', '--peek'], spec), /--seed needs a value/, 'a following flag is not a value');
  assert.throws(() => parseArgs(['--instance', 'a', '--instance', 'b'], spec), /--instance given twice/);
  assert.throws(() => parseArgs(['stray'], spec), /unexpected argument: stray/);
  const one = { valued: [], boolean: [], positional: 1 };
  assert.deepEqual(parseArgs(['file.txt'], one), { flags: {}, positional: ['file.txt'] });
  assert.throws(() => parseArgs(['a', 'b'], one), /unexpected argument: b/);
  assert.throws(() => parseArgs(['--nope'], one), /this command takes no flags/);
});

test('CLI: an unknown flag is refused before any side effect', () => {
  const dir = scratch('gzcoord-flags-');
  try {
    const typo = gzmsg('new-id', '--seeed', '9');
    assert.equal(typo.status, 2);
    assert.match(typo.stderr, /unknown flag --seeed/);
    assert.equal(typo.stdout, '');
    const peek = gzmsg('new-id', '--peek');
    assert.equal(peek.status, 2, 'the counter-era flag is unknown on new-id');
    assert.match(peek.stderr, /unknown flag --peek/);
    assert.equal(peek.stdout, '');
    const retired = gzmsg('hello', '--no-taxonomy', '--from', 'develop-gzapp/web', '--role', 'R', '--project', 'p');
    assert.equal(retired.status, 2, 'hello is no longer a command');
    assert.match(retired.stderr, /^usage: gzmsg\.mjs validate/);
    assert.equal(retired.stdout, '');
    const file = path.join(dir, 'm.txt'); fs.writeFileSync(file, '[GZCOORD/1] INFO\nFROM: a/b\nROLE: R\nPROJECT: p\nMESSAGE-ID: b-0001\nBROADCAST: true\n');
    const v = gzmsg('validate', file, '--nope');
    assert.equal(v.status, 2);
    assert.match(v.stderr, /unknown flag --nope/);
    // and the declared paths are untouched
    assert.equal(gzmsg('validate', file, '--no-taxonomy').status, 0);
    assert.match(gzmsg('new-id').stdout.trim(), /^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab]/, 'the declared path mints');
  } finally { fs.rmSync(dir, { recursive: true, force: true }); }
});

// inbox.mjs applies SPEC §7.1 addressing and the §17 reading rule at
// delivery: the body of a message not addressed to this session is never
// printed. forMe() is that decision, kept pure so it can be pinned.
import { ensureRelay, forMe, identity, waitLoop, checkKeywords, keywordHit, inboxRoot, relayRuntimeDir, WORKSPACE, integrationConfig, holdDir, holdStatus, pidStart, pidAlive, render, splitMessage, NOTIFICATION_CAP, REPLAY_CMD, assertNotControlChannel, markRetransmissions, journalInbound, JOURNAL_RETRY_MS } from '../scripts/inbox.mjs';
test('inbox forMe: exactly the messages SPEC §7.1 addresses to this session', () => {
  const me = { address: 'develop-qzapp/db-admin', instance: 'db-admin', slug: 'db-admin' };
  const mk = (type, extra) => parse(`[GZCOORD/1] ${type}\nFROM: develop-qzapp/x\nROLE: architect-cto\nPROJECT: gzapp\nMESSAGE-ID: x-0001\n${extra}`);
  assert.equal(forMe(mk('INFO', 'TO: develop-qzapp/db-admin\n'), me), true, 'TO is my address');
  assert.equal(forMe(mk('INFO', 'TO: develop-qzapp/web-dev-01\n'), me), false, 'TO is someone else');
  assert.equal(forMe(mk('INFO', 'TO-ROLE: db-admin\n'), me), true, 'TO-ROLE is my slug');
  assert.equal(forMe(mk('INFO', 'TO-ROLE: backend-dev\n'), me), false, 'TO-ROLE is another slug');
  assert.equal(forMe(mk('INFO', 'BROADCAST: true\n'), me), true, 'broadcast reaches everyone');
  assert.equal(forMe(mk('HELLO', ''), me), false, 'a retired HELLO carries no addressing field: addressed to nobody');
  assert.equal(forMe(mk('INFO', ''), me), false, 'no addressing field at all: not for anyone');
  // A session with no resolvable role never matches a TO-ROLE.
  assert.equal(forMe(mk('INFO', 'TO-ROLE: db-admin\n'), { ...me, slug: undefined }), false);
});

test('inbox identity: address is <host>/<login>; the slug comes from the binding, then from the login', () => {
  // The resolver's answer is what identity() consumes; the working copy
  // the process runs in is not an input at all.
  const host = 'box';
  const noRole = { agent: 'architect-cto-01', host, role: undefined, binding: '/nonexistent/binding.json' };
  assert.deepEqual(identity(noRole, taxonomy), { address: 'box/architect-cto-01', instance: 'architect-cto-01', slug: 'architect-cto', project: undefined });
  // a binding wins over the login's slug
  assert.equal(identity({ ...noRole, role: 'backend-dev', project: 'gzapp' }, taxonomy).slug, 'backend-dev');
  assert.equal(identity({ ...noRole, role: 'backend-dev', project: 'gzapp' }, taxonomy).project, 'gzapp');
  // a generic login carries no slug; the address still derives
  assert.deepEqual(identity({ agent: 'user', host, binding: '/nonexistent' }, taxonomy), { address: 'box/user', instance: 'user', slug: undefined, project: undefined });
  // no catalogue at all: address still derives, slug does not
  assert.deepEqual(identity(noRole, undefined), { address: 'box/architect-cto-01', instance: 'architect-cto-01', slug: undefined, project: undefined });
  // and the real resolver names this process's login
  assert.equal(identity(whoami(), undefined).instance, login);
});

// The wait exits ONLY on a message addressed to this session: a slice
// holding only others' traffic is acknowledged and the arm CONTINUES —
// waking a session for its neighbours' messages is the noise the tool
// exists to remove. Injected fetch/ack pages make the loop deterministic.
test('waitLoop exits only on an addressed message; others pass acknowledged', async () => {
  const me = { address: 'develop-qzapp/db-admin', instance: 'db-admin', slug: 'db-admin' };
  const rec = (id, type, extra) => ({ id, sender: 'develop-qzapp/x', timestamp: 't', content: `[GZCOORD/1] ${type}\nFROM: develop-qzapp/x\nROLE: architect-cto\nPROJECT: gzapp\nMESSAGE-ID: x-${id}\n${extra}` });
  const forYou = rec('m3', 'INFO', 'BROADCAST: true\n');
  const othersPage = { messages: [rec('m1', 'INFO', 'TO: develop-qzapp/web-dev-01\n'), rec('m2', 'OBSERVATION', 'TO-ROLE: backend-dev\n')] };
  const acked = [];
  const ack = id => { acked.push(id); return Promise.resolve(); };
  const pages = [othersPage, { messages: [forYou] }];
  const fetchPage = async () => pages.shift();
  let fetches = 0;
  const countingFetch = async () => { fetches += 1; return pages.shift(); };
  const r = await waitLoop({ fetchPage: countingFetch, ack, waitTotal: 1800, forMeFn: msg => forMe(msg, me) });
  assert.equal(r.delivered, true, 'exits on the addressed message, not the neighbours\' one');
  assert.equal(fetches, 2, 'two slices: the passed one and the delivering one');
  assert.equal(r.waited, 110, 'budget accounting: two 55 s slices');
  assert.equal(r.classified.find(c => c.rec.id === 'm3').isMine, true);
  assert.deepEqual(acked.sort(), ['m1', 'm2', 'm3'], 'every shown message is acknowledged');
  // A page of nothing-but-others at budget end: quiet exit, counted.
  const r2 = await waitLoop({
    fetchPage: async () => ({ messages: [rec('m9', 'INFO', 'TO: develop-qzapp/web-dev-01\n')] }),
    ack: async () => {}, waitTotal: 4, forMeFn: msg => forMe(msg, me) });
  assert.equal(r2.delivered, false);
  assert.equal(r2.othersPassed, 1);
  assert.equal(r2.waited, 4, 'spent the whole budget');
  // Drain mode returns the first page whatever it holds.
  const r3 = await waitLoop({
    fetchPage: async () => ({ messages: [rec('m1', 'INFO', 'TO: develop-qzapp/web-dev-01\n')] }),
    ack: async () => {}, waitTotal: 0, forMeFn: msg => forMe(msg, me) });
  assert.equal(r3.delivered, false, 'drain does not exit early — it lists');
  assert.equal(r3.classified.length, 1);
  // A retired HELLO or GOODBYE an old session still sends is acknowledged
  // and never delivered, not even listed: presence is the control plane's (docs/adr/ADR-030-presence-replaces-hello-and-goodbye.md).
  const acked4 = [];
  const r4 = await waitLoop({
    fetchPage: async () => ({ messages: [rec('h', 'HELLO', ''), rec('g', 'GOODBYE', 'NOTES:\nsession ended\n')] }),
    ack: async id => { acked4.push(id); }, waitTotal: 4, forMeFn: msg => forMe(msg, me) });
  assert.deepEqual([r4.delivered, r4.classified.length, r4.othersPassed], [false, 0, 0], 'a HELLO wakes nobody and is not listed');
  assert.deepEqual(acked4, ['h', 'g'], 'but the cursor moves past it');
});

// The episodic journal (ADR-041 rule 4): what is addressed to this session
// is journaled before the page is acknowledged; a journal that cannot take
// it holds the messages — unacknowledged, unshown — and says why.
test('waitLoop journals the addressed records before acknowledging, and only those', async () => {
  const me = { address: 'develop-qzapp/db-admin', instance: 'db-admin', slug: 'db-admin' };
  const rec = (id, extra) => ({ id, seq: id.length, content: `[GZCOORD/1] INFO\nFROM: develop-qzapp/x\nROLE: r\nMESSAGE-ID: x-${id}\n${extra}` });
  const order = [];
  const r = await waitLoop({
    fetchPage: async () => ({ messages: [rec('other', 'TO: develop-qzapp/web-dev-01\n'), rec('mine', 'TO: develop-qzapp/db-admin\n')] }),
    ack: async id => { order.push(`ack ${id}`); }, waitTotal: 4, forMeFn: msg => forMe(msg, me),
    journal: async recs => { order.push(`journal ${recs.map(x => x.id).join(',')}`); return { ok: true }; } });
  assert.equal(r.delivered, true);
  assert.deepEqual(order, ['journal mine', 'ack other', 'ack mine'], 'only the addressed record is journaled, and before any ack');
});
test('a journal that cannot keep them: the addressed records are held — not acknowledged, not shown — said once, retried after a pause', async () => {
  const me = { address: 'develop-qzapp/db-admin', instance: 'db-admin', slug: 'db-admin' };
  const rec = (id, seq, extra) => ({ id, seq, content: `[GZCOORD/1] INFO\nFROM: develop-qzapp/x\nROLE: r\nMESSAGE-ID: x-${id}\n${extra}` });
  const page = { messages: [rec('other', 1, 'TO: develop-qzapp/web-dev-01\n'), rec('mine', 2, 'BROADCAST: true\n')] };
  const acked = [], said = [], slept = [];
  let tries = 0;
  const r = await waitLoop({
    fetchPage: async () => page, ack: async id => { acked.push(id); }, waitTotal: 3600, forMeFn: msg => forMe(msg, me),
    sleep: async ms => { slept.push(ms); },
    journal: async () => (++tries < 3 ? { ok: false, reason: 'episodic: disk full' } : { ok: true }),
    onJournalFail: (reason, n) => said.push([reason, n]) });
  assert.equal(r.delivered, true, 'shown once the journal could keep it');
  assert.deepEqual(acked.filter(id => id === 'mine'), ['mine'], 'acknowledged once, only after it was kept');
  assert.deepEqual(said, [['episodic: disk full', 1], ['episodic: disk full', 1]], 'each failure reported to the caller, which says it once per cause');
  assert.deepEqual(slept, [JOURNAL_RETRY_MS, JOURNAL_RETRY_MS], 'a pause before the carrier is asked again: a broken journal does not spin');
  const drained = await waitLoop({
    fetchPage: async () => page, ack: async id => { acked.push(`drain ${id}`); }, waitTotal: 0, forMeFn: msg => forMe(msg, me),
    journal: async () => ({ ok: false, reason: 'episodic: x' }) });
  assert.deepEqual([drained.delivered, drained.journalFailed], [false, 'episodic: x'], 'a drain returns at once, held');
  assert.ok(!acked.includes('drain mine') && acked.includes('drain other'), 'others acknowledged; the addressed one not');
});
// The relay's acknowledgement is a cursor (claude_bridge advance_cursor:
// one last_seq per consumer, moved forward only), so this fake honours one:
// a page is every record above it, and an ack of seq N passes all below.
function cursorRelay(records) {
  let cursor = 0;
  return {
    fetchPage: async () => ({ messages: records.filter(r => !(r.seq <= cursor)) }),
    ack: async id => { cursor = Math.max(cursor, records.find(r => r.id === id).seq ?? cursor); },
    cursor: () => cursor,
  };
}
test('a held record is not passed by acknowledging a later one: the relay\'s cursor stays before it (review of #78)', async () => {
  const me = { address: 'develop-qzapp/db-admin', instance: 'db-admin', slug: 'db-admin' };
  const rec = (id, seq, extra) => ({ id, seq, content: `[GZCOORD/1] INFO\nFROM: develop-qzapp/x\nROLE: r\nMESSAGE-ID: x-${id}\n${extra}` });
  const relay = cursorRelay([rec('before', 1, 'TO: develop-qzapp/web-dev-01\n'), rec('mine', 2, 'TO: develop-qzapp/db-admin\n'),
                             rec('retired', 3, '').content.startsWith('[') && { id: 'retired', seq: 3, content: '[GZCOORD/1] HELLO\nFROM: develop-qzapp/x\n' },
                             rec('after', 4, 'TO: develop-qzapp/web-dev-01\n')]);
  let tries = 0;
  const kept = [];
  const r = await waitLoop({ ...relay, waitTotal: 3600, forMeFn: msg => forMe(msg, me), sleep: async () => {},
    journal: async recs => { if (++tries === 1) { assert.equal(relay.cursor(), 0); return { ok: false, reason: 'episodic: x' }; } kept.push(...recs.map(x => x.id)); return { ok: true }; } });
  assert.equal(tries, 2, 'the held record came back and was journaled');
  assert.deepEqual([r.delivered, kept], [true, ['mine']], 'then shown');
  assert.equal(relay.cursor(), 4, 'and the page acknowledged only after it was kept');
  const relay2 = cursorRelay([rec('mine', 1, 'TO: develop-qzapp/db-admin\n'), rec('after', 2, 'TO: develop-qzapp/web-dev-01\n')]);
  const d = await waitLoop({ ...relay2, waitTotal: 0, forMeFn: msg => forMe(msg, me), journal: async () => ({ ok: false, reason: 'episodic: x' }) });
  assert.deepEqual([d.journalFailed, relay2.cursor()], ['episodic: x', 0], 'a drain held first in the page acknowledges nothing after it');
  const relay3 = cursorRelay([{ id: 'nos', content: rec('mine', 0, 'TO: develop-qzapp/db-admin\n').content }, { ...rec('after', 0, 'TO: develop-qzapp/web-dev-01\n'), seq: 5 }]);
  await waitLoop({ ...relay3, waitTotal: 0, forMeFn: msg => forMe(msg, me), journal: async () => ({ ok: false, reason: 'episodic: x' }) });
  assert.equal(relay3.cursor(), 0, 'a held record with no comparable seq: nothing acknowledged');
});
test('a keyword among records acknowledged before a held one is the exit reason (review of #78)', async () => {
  const me = { address: 'develop-qzapp/db-admin', instance: 'db-admin', slug: 'db-admin' };
  const relay = cursorRelay([
    { id: 'kw', seq: 1, content: '[GZCOORD/1] INFO\nFROM: develop-qzapp/x\nROLE: r\nTO: develop-qzapp/web-dev-01\nMESSAGE-ID: x-1\n\nINFO:\nthe geocode outage\n' },
    { id: 'mine', seq: 2, content: '[GZCOORD/1] INFO\nFROM: develop-qzapp/x\nROLE: r\nTO: develop-qzapp/db-admin\nMESSAGE-ID: x-2\n' }]);
  const r = await waitLoop({ ...relay, waitTotal: 3600, forMeFn: msg => forMe(msg, me), keywords: ['geocode'], ownAddress: me.address,
    sleep: async () => { throw new Error('waited instead of exiting on the keyword'); },
    journal: async () => ({ ok: false, reason: 'episodic: x' }) });
  assert.deepEqual([r.keywordHit?.id, r.journalFailed, relay.cursor()], ['kw', 'episodic: x', 1],
    'the passed keyword record is named, the held one stays unacknowledged');
});
test('--wait ends within its budget while the journal stays broken, the hold reported (review of #78)', async () => {
  const me = { address: 'develop-qzapp/db-admin', instance: 'db-admin', slug: 'db-admin' };
  const relay = cursorRelay([{ id: 'mine', seq: 1, content: '[GZCOORD/1] INFO\nFROM: develop-qzapp/x\nROLE: r\nTO: develop-qzapp/db-admin\nMESSAGE-ID: x-1\n' }]);
  let tries = 0;
  const slept = [];
  const r = await waitLoop({ ...relay, waitTotal: 70, forMeFn: msg => forMe(msg, me), sleep: async ms => { slept.push(ms); },
    journal: async () => { if (++tries > 20) throw new Error('never ended'); return { ok: false, reason: 'episodic: x' }; } });
  assert.deepEqual([r.delivered, r.journalFailed, relay.cursor()], [false, 'episodic: x', 0], 'held, said, unacknowledged');
  // A 55 s slice, one failed attempt, a pause of the 15 s left: then back,
  // with no fetch or journal attempt past the budget (re-review of #78).
  assert.deepEqual([r.waited, tries, slept], [70, 1, [15000]], `returned at the budget (waited ${r.waited}, ${tries} tries)`);
  assert.ok(slept.every(ms => ms <= JOURNAL_RETRY_MS));
});
test('journalInbound sends the records as JSON lines and reads a failure from the journal\'s own last line', () => {
  let call;
  const run = (py, args, opts) => { call = { py, args, input: opts.input }; return { status: 0, stderr: '' }; };
  const ok = journalInbound([{ content: 'C', seq: 7, ts_full: 'T' }], { project: 'p', working_copy: '/w' }, { env: { AGENT_FABRIC_PYTHON: '/py' }, run });
  assert.equal(ok.ok, true);
  assert.equal(call.py, '/py');
  assert.deepEqual(call.args.slice(1), ['gzcoord-in', '--project', 'p', '--working-copy', '/w']);
  assert.deepEqual(JSON.parse(call.input.trim()), { content: 'C', seq: 7, ts: 'T' });
  const bad = journalInbound([{ content: 'C' }], {}, { env: {}, run: () => ({ status: 1, stderr: 'noise\nepisodic: the store has no id\n' }) });
  assert.deepEqual(bad, { ok: false, reason: 'episodic: the store has no id' });
  const thrown = journalInbound([{ content: 'C' }], {}, { env: {}, run: () => { throw new Error('ENOENT'); } });
  assert.equal(thrown.ok, false); assert.match(thrown.reason, /ENOENT/);
});

// --keyword: reasons to stop waiting on a message NOT addressed to this
// session. Guardrails exist because the abusable shape — a keyword that
// fires on every message — is the address-blind wake with extra steps.
test('checkKeywords: minimum length, hard cap, dedup', () => {
  assert.deepEqual(checkKeywords(['663', 'geocode']), ['663', 'geocode']);
  assert.deepEqual(checkKeywords(['663', '663']), ['663'], 'deduplicated');
  for (const bad of ['ab', '6', '', 'a']) assert.throws(() => checkKeywords([bad]), /shorter than 3 characters/, JSON.stringify(bad));
  assert.throws(() => checkKeywords(['aaa','bbb','ccc','ddd','eee','fff','ggg','hhh','iii']), /at most 8 keywords/);
  assert.doesNotThrow(() => checkKeywords(['aaa','bbb','ccc','ddd','eee','fff','ggg','hhh']), 'exactly 8 is allowed');
});

test('keywordHit: whole-token, case-insensitive, full text; own echo never hits', () => {
  const text = '[GZCOORD/1] INFO\nFROM: develop-qzapp/x\nPROJECT: gzapp\nMESSAGE-ID: x-0001\nBROADCAST: true\nSUBJECT: PR 663 discussion\n\nNOTES:\nsee REFERENCES - github-pr: #663 and #2663\n';
  const own = 'develop-qzapp/x';
  for (const [kw, want] of [['663', true], ['pr', true], ['2663', true], ['references', true], ['6', false], ['66', false], ['GEQ', false], ['266', false], ['663-x', false]])
    assert.equal(keywordHit(text, [kw], own), want, kw);
  // multiple keywords: any hit wakes
  assert.equal(keywordHit(text, ['zzz', 'geocode'], own), false);
  assert.equal(keywordHit(text, ['zzz', 'pr-'], own), false, 'whole-token, not substring');
  // the armed session's own messages never wake it — the echo exemption
  assert.equal(keywordHit(text, ['663'], undefined), true, 'no ownAddress known: token match stands');
  assert.equal(keywordHit(text, ['develop-qzapp'], own), false, 'own FROM token removed');
  assert.equal(keywordHit(text, ['pr'], undefined), true, 'PR token matches without own address too');
  assert.equal(keywordHit('', ['anything'], undefined), false, 'empty text never hits');
});

test('waitLoop --keyword: a passing non-addressed message ends the arm with code-3 data', async () => {
  const me = { address: 'develop-qzapp/db-admin', instance: 'db-admin', slug: 'db-admin' };
  const rec = (id, type, extra) => ({ id, sender: 'develop-qzapp/x', timestamp: 't', content: `[GZCOORD/1] ${type}\nFROM: develop-qzapp/x\nROLE: architect-cto\nPROJECT: gzapp\nMESSAGE-ID: x-${id}\n${extra}` });
  // a message addressed to SOMEONE ELSE whose body mentions the keyword
  const pages = [
    { messages: [rec('m1', 'INFO', 'TO: develop-qzapp/web-dev-01\n'), rec('m2', 'OBSERVATION', 'TO-ROLE: backend-dev\nSUBJECT: unrelated schema review\n')] },
    { messages: [rec('m3', 'REPLY', 'TO: develop-qzapp/web-dev-01\n\nREFERENCES:\n- github-pr: #663\n')] },
  ];
  let fetches = 0; const acked = [];
  const r = await waitLoop({
    fetchPage: async () => { fetches += 1; return pages.shift(); },
    ack: async id => { acked.push(id); },
    waitTotal: 1800, forMeFn: msg => forMe(msg, me), keywords: checkKeywords(['663']), ownAddress: me.address });
  assert.equal(r.delivered, false, 'never addressed to me');
  assert.equal(r.keywordHit.id, 'm3', 'the keyword message is the exit reason');
  assert.equal(fetches, 2, 'the first slice (no hit) continued the arm');
  assert.deepEqual(acked.sort(), ['m1', 'm2', 'm3'], 'passed messages are acknowledged too');
  assert.equal(r.othersPassed, 1, 'one other in the delivering slice is passed');
  // the echo exemption inside waitLoop: a message FROM my address never ends the arm
  const selfPage = () => ({ messages: [rec('me-1', 'INFO', 'BROADCAST: true\n')] });
  const echoFromSelf = rec('echo', 'INFO', 'BROADCAST: true\n');
  echoFromSelf.sender = me.address; echoFromSelf.content = echoFromSelf.content.replace('develop-qzapp/x', me.address);
  const r2 = await waitLoop({
    fetchPage: async () => ({ messages: [echoFromSelf] }),
    ack: async () => {}, waitTotal: 1800, forMeFn: msg => forMe(msg, me), keywords: checkKeywords(['663']), ownAddress: me.address });
  assert.equal(r2.keywordHit, null, 'own echo: no hit');
  assert.equal(r2.delivered, true, 'a broadcast from self is still addressed to me (unchanged)');
  // budget expiry with a keyword set and no hit: quiet, counted
  const r3 = await waitLoop({
    fetchPage: async () => ({ messages: [rec('m9', 'INFO', 'TO: develop-qzapp/web-dev-01\n')] }),
    ack: async () => {}, waitTotal: 4, forMeFn: msg => forMe(msg, me), keywords: checkKeywords(['663']), ownAddress: me.address });
  assert.equal(r3.keywordHit, null); assert.equal(r3.delivered, false); assert.equal(r3.waited, 4);
});

// The inbox reads its token and integration from the project's working
// copy. A session started in the workspace (projects/, no git toplevel)
// still has one: the binding names the checkout the role was activated
// in. Found live on architect-cto-01, 2026-09-14: the workspace launch
// drained nothing because the root fell back to the cwd.
test('inboxRoot uses the binding working copy outside a checkout', () => {
  const tmp = scratch('inbox-root-');
  const wc = path.join(tmp, 'clone'); fs.mkdirSync(wc);
  const binding = path.join(tmp, 'binding.json');
  fs.writeFileSync(binding, JSON.stringify({ working_copy: wc }));
  const cwd = process.cwd();
  try {
    process.chdir(tmp);                       // tmp is outside any repository
    assert.equal(inboxRoot({ working_copy: null, binding }), wc);
    assert.equal(inboxRoot({ working_copy: wc, binding: '/nonexistent' }), wc);
    fs.rmSync(wc, { recursive: true });
    assert.equal(inboxRoot({ working_copy: null, binding }), tmp, 'a vanished working copy falls back to the cwd');
  } finally { process.chdir(cwd); fs.rmSync(tmp, { recursive: true, force: true }); }
});

// The relay's runtime (venv, token, database) is host state and lives in
// the workspace — the projects/ directory the fabric checkout sits in —
// never inside a working copy: a repository, gitignored or not, is the
// wrong owner for the channel's only record and a secret.
test('relay runtime dir resolves against the workspace, not a working copy', () => {
  assert.equal(WORKSPACE, path.dirname(path.resolve(import.meta.dirname, '..', '..', '..')));
  assert.equal(relayRuntimeDir({ relay_runtime_dir: '.gzcoord' }, '/ws'), '/ws/.gzcoord');
  assert.equal(relayRuntimeDir({}, '/ws'), '/ws/.gzcoord');
  assert.equal(relayRuntimeDir({ relay_runtime_dir: '/var/lib/gzcoord' }, '/ws'), '/var/lib/gzcoord');
  assert.ok(!relayRuntimeDir({ relay_runtime_dir: '.gzcoord' }).includes('/gzapp/'));
});

// send.mjs is the other half of the inbox: same identity, same relay,
// same token resolution. It validates last, refuses a FROM that is not
// this login's address, and posts exactly {channel, sender, content}.
import http from 'node:http';
import { execFile, spawn } from 'node:child_process';
import { scratch } from '../../../tests/scratch.mjs';
const SEND = fileURLToPath(new URL('../scripts/send.mjs', import.meta.url));
function withRelay(fn) {
  const posts = [];
  const server = http.createServer((req, res) => {
    let body = ''; req.on('data', c => body += c); req.on('end', () => {
      posts.push({ url: req.url, auth: req.headers.authorization, body: JSON.parse(body || '{}') });
      res.setHeader('content-type', 'application/json'); res.end(JSON.stringify({ seq: 42, id: 'relay-id', deduplicated: false }));
    });
  });
  return new Promise((resolve, reject) => server.listen(0, '127.0.0.1', async () => {
    try { resolve(await fn(`http://127.0.0.1:${server.address().port}`, posts)); } catch (e) { reject(e); } finally { server.close(); }
  }));
}
// A scratch secrets store holding an agent id: send keeps every message in
// the sender's episodic journal (ADR-041), and a journal has an owner. Its
// own directory, never HOME — one test makes the message's directory
// read-only.
const AGENT_ID = '01a0f782-7e06-7dee-811f-0a860ed93bf3';
function idStore() {
  const d = scratch('send-store-'); fs.writeFileSync(path.join(d, '.agent-id'), `${AGENT_ID}\n`); return d;
}
// Asynchronous on purpose: the stub relay lives in this process, and a
// synchronous exec would block the event loop the server answers on.
function sendWith(relay, text, extra = [], moreEnv = {}) {
  const f = path.join(scratch('send-'), 'm.txt'); fs.writeFileSync(f, text);
  // HOME is a scratch dir: the runner's own synced secrets.env must not be the token here.
  // The state dir too: send records every id it sends, and a test must never write that record into the runner's own.
  const env = { ...process.env, HOME: path.dirname(f), AGENT_FABRIC_STATE_DIR: path.join(path.dirname(f), 'state'), AGENT_FABRIC_SECRET_STORE: idStore(), CLAUDE_BRIDGE_URL: relay, CLAUDE_BRIDGE_AUTH_TOKEN: 'tok-fixture', GZCOORD_CHANNEL: 'fixture:chan', ...moreEnv };
  return new Promise(resolve => execFile('node', [SEND, f, ...extra], { env, encoding: 'utf8' },
    (e, out, err) => resolve({ code: e ? e.code : 0, out: String(out), err: String(err) })));
}
const ME = whoami();
const MY_ADDRESS = `${ME.host}/${ME.agent}`;
const valid = `[GZCOORD/1] INFO\nFROM: ${MY_ADDRESS}\nROLE: backend-dev\nPROJECT: fixture\nBROADCAST: true\nMESSAGE-ID: 01a09fc1-0000-7000-8000-000000000001\nSUBJECT: fixture\n\nNOTES:\nhello\n`;

test('send posts a valid message as this login, to the configured channel', async () => {
  await withRelay(async (relay, posts) => {
    const r = await sendWith(relay, valid);
    assert.equal(r.code, 0, r.err);
    assert.match(r.out, /^sent seq 42 INFO 01a09fc1-0000-7000-8000-000000000001/);
    assert.equal(posts.length, 1);
    assert.equal(posts[0].url, '/api/send');
    assert.equal(posts[0].auth, 'Bearer tok-fixture');
    assert.deepEqual(Object.keys(posts[0].body).sort(), ['channel', 'content', 'sender']);
    assert.equal(posts[0].body.sender, MY_ADDRESS);
    assert.equal(posts[0].body.channel, 'fixture:chan');
    assert.equal(posts[0].body.content, valid);
  });
});

// The episodic journal (ADR-041): the message is kept before the post and
// marked with its outcome after; a journal that cannot take it stops the send.
function journalRows(state, store) {
  const py = process.env.AGENT_FABRIC_PYTHON || '/usr/local/bin/fabric-python';
  const r = spawnSync(py, ['-c', `import sqlite3,json,sys
sys.path.insert(0, sys.argv[1]); import episodic
c = sqlite3.connect(episodic.db_path())
print(json.dumps(c.execute("SELECT direction, state, message_id, carrier_seq, content FROM episodes ORDER BY recorded_at").fetchall()))`,
    fileURLToPath(new URL('../../../tools/fabric', import.meta.url))],
    { encoding: 'utf8', env: { ...process.env, AGENT_FABRIC_STATE_DIR: state, AGENT_FABRIC_SECRET_STORE: store } });
  assert.equal(r.status, 0, r.stderr);
  return JSON.parse(r.stdout);
}
test('send keeps the message in its journal before posting, and marks it accepted with the relay seq', async () => {
  await withRelay(async (relay, posts) => {
    const state = path.join(scratch('send-journal-'), 'state'); const store = idStore();
    const r = await sendWith(relay, valid, [], { AGENT_FABRIC_STATE_DIR: state, AGENT_FABRIC_SECRET_STORE: store });
    assert.equal(r.code, 0, r.err);
    assert.deepEqual(journalRows(state, store), [['outbound', 'accepted', '01a09fc1-0000-7000-8000-000000000001', 42, valid]]);
    assert.equal(posts.length, 1);
  });
});
test('a journal that cannot take the message stops the send: nothing posted, exit 2, said', async () => {
  await withRelay(async (relay, posts) => {
    const r = await sendWith(relay, valid, [], { AGENT_FABRIC_SECRET_STORE: scratch('send-no-id-') });
    assert.equal(r.code, 2, r.err);
    assert.match(r.err, /no agent id/);
    assert.match(r.err, /not sent: a message is kept before it leaves/);
    assert.equal(posts.length, 0, 'the carrier never saw it');
    const off = await sendWith(relay, valid, [], { AGENT_FABRIC_SECRET_STORE: scratch('send-no-id-'), GZCOORD_JOURNAL: 'off' });
    assert.equal(off.code, 0, off.err);
    assert.match(off.err, /GZCOORD_JOURNAL=off — this message is sent without being kept/);
    assert.equal(posts.length, 1, 'the explicit bypass sends, and says so');
  });
});
test('a post the relay refuses leaves the journal row failed, not accepted', async () => {
  const server = http.createServer((req, res) => { res.statusCode = 500; res.end('{}'); });
  await new Promise(r => server.listen(0, '127.0.0.1', r));
  try {
    const state = path.join(scratch('send-journal-fail-'), 'state'); const store = idStore();
    const r = await sendWith(`http://127.0.0.1:${server.address().port}`, valid, [], { AGENT_FABRIC_STATE_DIR: state, AGENT_FABRIC_SECRET_STORE: store });
    assert.equal(r.code, 3, r.err);
    assert.deepEqual(journalRows(state, store).map(x => x.slice(0, 3)), [['outbound', 'failed', '01a09fc1-0000-7000-8000-000000000001']]);
  } finally { server.closeAllConnections(); server.close(); }
});

test('a failed retransmission leaves a row pending whose earlier outcome was never written (review of #78)', async () => {
  const server = http.createServer((req, res) => { res.statusCode = 500; res.end('{}'); });
  await new Promise(r => server.listen(0, '127.0.0.1', r));
  try {
    const state = path.join(scratch('send-journal-unknown-'), 'state'); const store = idStore();
    const env = { ...process.env, AGENT_FABRIC_STATE_DIR: state, AGENT_FABRIC_SECRET_STORE: store };
    // An earlier send that died after its post: a pending row and no outcome.
    const py = process.env.AGENT_FABRIC_PYTHON || '/usr/local/bin/fabric-python';
    const first = spawnSync(py, [fileURLToPath(new URL('../../../tools/fabric/episodic.py', import.meta.url)), 'gzcoord-out-pending'],
      { encoding: 'utf8', env, input: valid });
    assert.deepEqual([first.status, first.stdout.trim()], [0, 'pending'], first.stderr);
    const r = await sendWith(`http://127.0.0.1:${server.address().port}`, valid, [], { AGENT_FABRIC_STATE_DIR: state, AGENT_FABRIC_SECRET_STORE: store });
    assert.equal(r.code, 3, r.err);
    assert.match(r.err, /may have reached the relay; its row stays pending/);
    assert.deepEqual(journalRows(state, store).map(x => x.slice(0, 3)), [['outbound', 'pending', '01a09fc1-0000-7000-8000-000000000001']]);
  } finally { server.closeAllConnections(); server.close(); }
});

// A message with no MESSAGE-ID gets one from the sender, written into the
// file before it posts, so a retry of the same file carries the same id
// (SPEC §7.2) — and the command on screen is the message that goes out.
function sendFile(relay, f, extra = [], state = path.join(path.dirname(f), 'state')) {
  const env = { ...process.env, HOME: path.dirname(f), AGENT_FABRIC_STATE_DIR: state, AGENT_FABRIC_SECRET_STORE: idStore(), CLAUDE_BRIDGE_URL: relay, CLAUDE_BRIDGE_AUTH_TOKEN: 'tok-fixture', GZCOORD_CHANNEL: 'fixture:chan' };
  return new Promise(resolve => execFile('node', [SEND, f, ...extra], { env, encoding: 'utf8' },
    (e, out, err) => resolve({ code: e ? e.code : 0, out: String(out), err: String(err) })));
}
const noId = valid.replace(/^MESSAGE-ID: .*\n/m, '');
const idOf = text => /^MESSAGE-ID: (.+)$/m.exec(text)?.[1];

test('send mints a missing MESSAGE-ID, writes it into the file, and a retry of the file sends the same id', async () => {
  await withRelay(async (relay, posts) => {
    const f = path.join(scratch('send-mint-'), 'm.txt'); fs.writeFileSync(f, noId);
    const r = await sendFile(relay, f);
    assert.equal(r.code, 0, r.err);
    const id = idOf(fs.readFileSync(f, 'utf8'));
    assert.match(id, /^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/, 'a UUIDv7, the deployment\'s own shape');
    assert.match(r.out, new RegExp(`^sent seq 42 INFO ${id}`));
    assert.match(r.err, /minted .* and wrote it into/);
    assert.equal(idOf(posts[0].body.content), id, 'the posted message carries the id the file now holds');
    assert.ok(/^SUBJECT: fixture$/m.test(posts[0].body.content) && posts[0].body.content.indexOf('MESSAGE-ID:') < posts[0].body.content.indexOf('\n\n'), 'the id sits in the metadata block');
    const again = await sendFile(relay, f);
    assert.equal(again.code, 0, again.err);
    assert.equal(idOf(posts[1].body.content), id, 'the retry sends the same id');
    assert.doesNotMatch(again.err, /minted/, 'nothing is minted the second time');
  });
});

test('a dry run mints in memory only; stdin is said to keep nothing; a present id is kept; a placeholder is still refused', async () => {
  await withRelay(async (relay, posts) => {
    const f = path.join(scratch('send-mint-dry-'), 'm.txt'); fs.writeFileSync(f, noId);
    const dry = await sendFile(relay, f, ['--dry-run']);
    assert.equal(dry.code, 0, dry.err);
    assert.equal(fs.readFileSync(f, 'utf8'), noId, 'the dry run changed nothing');
    assert.match(dry.err, /would mint one \(dry run/);
    const env = { ...process.env, HOME: path.dirname(f), AGENT_FABRIC_STATE_DIR: path.join(path.dirname(f), 'state'), AGENT_FABRIC_SECRET_STORE: idStore(), CLAUDE_BRIDGE_URL: relay, CLAUDE_BRIDGE_AUTH_TOKEN: 'tok-fixture', GZCOORD_CHANNEL: 'fixture:chan' };
    const piped = await new Promise(resolve => { const c = execFile('node', [SEND, '-'], { env, encoding: 'utf8' }, (e, out, err) => resolve({ code: e ? e.code : 0, out, err })); c.stdin.end(noId); });
    assert.equal(piped.code, 0, piped.err);
    assert.match(piped.err, /from stdin it is kept nowhere/);
    const kept = await sendWith(relay, valid);
    assert.match(kept.out, /01a09fc1-0000-7000-8000-000000000001/);
    assert.doesNotMatch(kept.err, /minted/);
    const placeholder = await sendWith(relay, valid.replace(/^MESSAGE-ID: .*$/m, 'MESSAGE-ID: MSGID'));
    assert.equal(placeholder.code, 2);
    assert.match(placeholder.err, /MSGID.*not sent/);
  });
});

test('an id that already went out with another message is refused — a reused file does not send its new message under the old id', async () => {
  await withRelay(async (relay, posts) => {
    const dir = scratch('send-reuse-'); const f = path.join(dir, 'm.txt'); const state = path.join(dir, 'state');
    fs.writeFileSync(f, noId);
    const first = await sendFile(relay, f, [], state);
    assert.equal(first.code, 0, first.err);
    const again = await sendFile(relay, f, [], state);
    assert.equal(again.code, 0, 'the same message again is a retry, and passes');
    fs.writeFileSync(f, fs.readFileSync(f, 'utf8').replace('hello', 'a different message'));
    const reused = await sendFile(relay, f, [], state);
    assert.equal(reused.code, 2);
    assert.match(reused.err, /already went out with a different message \(seq 42\).*delete the MESSAGE-ID line/);
    assert.equal(posts.length, 2, 'the reused-id message was not posted');
    fs.writeFileSync(f, fs.readFileSync(f, 'utf8').replace(/^MESSAGE-ID: .*\n/m, ''));
    const fresh = await sendFile(relay, f, [], state);
    assert.equal(fresh.code, 0, fresh.err);
    assert.notEqual(idOf(fs.readFileSync(f, 'utf8')), idOf(posts[0].body.content), 'deleting the line mints a new id');
  });
});

test('a header send cannot parse is refused by the validator (exit 2), never a crash; a file that cannot be rewritten is refused unchanged and not posted', async () => {
  await withRelay(async (relay, posts) => {
    const bad = await sendWith(relay, 'GZCOORD INFO\nFROM: a/b\n\nNOTES:\nx\n');
    assert.equal(bad.code, 2, bad.err); assert.match(bad.err, /does not validate/);
    const dir = scratch('send-ro-'); const f = path.join(dir, 'm.txt'); fs.writeFileSync(f, noId);
    fs.chmodSync(dir, 0o555);
    try {
      if (process.getuid && process.getuid() === 0) return;   // root writes anywhere: nothing to show
      const r = await sendFile(relay, f, [], path.join(scratch('send-ro-state-'), 'state'));
      assert.equal(r.code, 1); assert.match(r.err, /could not write the minted MESSAGE-ID/);
      assert.equal(fs.readFileSync(f, 'utf8'), noId, 'the file is unchanged');
      assert.deepEqual(fs.readdirSync(dir), ['m.txt'], 'no temporary left');
      assert.equal(posts.length, 0);
    } finally { fs.chmodSync(dir, 0o755); }
  });
});

// Presence before sending (runtime/control/presence.mjs): a relay stub that
// answers `presence` requests on the control channel from a fixture table,
// and a registry that places the addressees.
function withPresenceRelay(answers, fn) {
  const posts = []; const asked = [];
  const server = http.createServer((req, res) => {
    res.setHeader('content-type', 'application/json');
    if (req.method === 'GET') {
      const u = new URL(req.url, 'http://x');
      const messages = u.searchParams.get('channel') === 'fabric:control' ? asked.flatMap(r => (r.to === '*' ? Object.keys(answers) : r.to).filter(a => answers[a]).map((a, i) =>
        ({ id: `${r.id}-${i}`, content: JSON.stringify({ kind: 'reply', in_reply_to: r.id, from: a, data: { presence: answers[a] } }) }))) : [];
      return res.end(JSON.stringify({ messages }));
    }
    let body = ''; req.on('data', c => body += c); req.on('end', () => {
      const b = JSON.parse(body || '{}');
      if (b.channel === 'fabric:control') { asked.push(JSON.parse(b.content)); return res.end(JSON.stringify({ id: 'ctl', seq: 1 })); }
      posts.push({ url: req.url, body: b }); res.end(JSON.stringify({ seq: 42, id: 'relay-id', deduplicated: false }));
    });
  });
  const reg = path.join(scratch('presence-reg-'), 'hosts.json');
  fs.writeFileSync(reg, JSON.stringify({ version: 1, hosts: { h: { operator: 'user' } }, placement: { alpha: 'h', beta: 'h', gamma: 'h' } }));
  return new Promise((resolve, reject) => server.listen(0, '127.0.0.1', async () => {
    try { resolve(await fn(`http://127.0.0.1:${server.address().port}`, posts, asked, { AGENT_FABRIC_HOSTS_REGISTRY: reg, GZCOORD_PRESENCE_WAIT_MS: '1200' })); }
    catch (e) { reject(e); } finally { server.closeAllConnections(); server.close(); }
  }));
}
const addressed = field => valid.replace('BROADCAST: true', field).replace('[GZCOORD/1] INFO', '[GZCOORD/1] OBSERVATION');
const failedRead = { status: 'failed', error: 'pgrep: spawn pgrep ENOENT' };
const up = role => ({ status: 'ok', online: true, sessions: 1, since: '2026-09-25T09:00:00.000Z', role, project: 'gzapp' });
const down = role => ({ status: 'ok', online: false, sessions: 0, since: null, role, project: 'gzapp' });

test('an addressee that is planning: sent, and the sender told its inbox is held until the plan is approved', async () => {
  await withPresenceRelay({ 'h/alpha': { ...up('web-dev'), planning: true } }, async (relay, posts, asked, env) => {
    const r = await sendWith(relay, addressed('TO: h/alpha'), [], env);
    assert.equal(r.code, 0, r.err);
    assert.match(r.err, /h\/alpha is planning — its inbox is held until the plan is approved; the message waits in the relay, and no answer comes before then/);
    assert.equal(posts.length, 1, 'planning never blocks the send');
  });
});

test('send checks presence first: a running addressee is sent to; one with no session, a silent agent or an unplaced address is refused, named, unless --force', async () => {
  await withPresenceRelay({ 'h/alpha': up('web-dev'), 'h/beta': down('web-dev') }, async (relay, posts, asked, env) => {
    const ok = await sendWith(relay, addressed('TO: h/alpha'), [], env);
    assert.equal(ok.code, 0, ok.err); assert.equal(posts.length, 1, 'sent');
    assert.deepEqual([asked[0].op, asked[0].to, asked[0].from], ['presence', ['h/alpha'], MY_ADDRESS]);
    const offline = await sendWith(relay, addressed('TO: h/beta'), [], env);
    assert.equal(offline.code, 4, offline.err);
    assert.match(offline.err, /h\/beta has no session running[\s\S]*not sent — --force sends it anyway/);
    assert.equal(posts.length, 1, 'nothing posted for an addressee with no session');
    const silent = await sendWith(relay, addressed('TO: h/gamma'), [], env);
    assert.equal(silent.code, 4); assert.match(silent.err, /h\/gamma's control agent did not answer within 1\.2 s/);
    const stranger = await sendWith(relay, addressed('TO: other/nobody'), [], env);
    assert.equal(stranger.code, 4); assert.match(stranger.err, /other\/nobody is not an account any host places/);
    const forced = await sendWith(relay, addressed('TO: h/beta'), ['--force'], env);
    assert.equal(forced.code, 0, forced.err); assert.match(forced.err, /sending anyway \(--force\)/);
    assert.equal(posts.length, 2, '--force sends it');
  });
});

test('a dry run posts nothing, not even a presence request; a refused token is the post\'s to report', async () => {
  await withPresenceRelay({ 'h/beta': down('web-dev') }, async (relay, posts, asked, env) => {
    const dry = await sendWith(relay, addressed('TO: h/beta'), ['--dry-run'], env);
    assert.equal(dry.code, 0, dry.err); assert.match(dry.err, /would post/);
    assert.deepEqual([posts.length, asked.length], [0, 0], 'no record of any kind (review of #38)');
  });
  const hits = [];
  const server = http.createServer((req, res) => { hits.push(`${req.method} ${req.url.split('?')[0]}`); res.statusCode = 401; res.end('{}'); });
  await new Promise(r => server.listen(0, '127.0.0.1', r));
  try {
    const reg = path.join(scratch('presence-reg-'), 'hosts.json');
    fs.writeFileSync(reg, JSON.stringify({ version: 1, hosts: { h: { operator: 'user' } }, placement: { alpha: 'h' } }));
    const r = await sendWith(`http://127.0.0.1:${server.address().port}`, addressed('TO: h/alpha'), [], { AGENT_FABRIC_HOSTS_REGISTRY: reg, GZCOORD_PRESENCE_WAIT_MS: '800' });
    assert.equal(r.code, 3, r.err); assert.match(r.err, /refused/); assert.doesNotMatch(r.err, /presence is unknown/);
    assert.match(r.err, /presence not asked — the relay refused the token in hand/, 'the skipped check is said, never silent');
    assert.equal(hits.filter(h => h === 'POST /api/send').length, 2, 'the presence request, then the post itself — which owns the token refusal');
  } finally { server.closeAllConnections(); server.close(); }
});

test('an addressee whose control agent could not tell is named as unknown, never as having no session', async () => {
  await withPresenceRelay({ 'h/alpha': failedRead }, async (relay, posts, asked, env) => {
    const r = await sendWith(relay, addressed('TO: h/alpha'), [], env);
    assert.equal(r.code, 4, r.err); assert.match(r.err, /presence is unknown \(h\/alpha: pgrep: spawn pgrep ENOENT\)/);
    assert.doesNotMatch(r.err, /has no session running/); assert.equal(posts.length, 0);
  });
});

test('send to a role: reached when any holder runs; a broadcast asks nothing', async () => {
  await withPresenceRelay({ 'h/alpha': down('web-dev'), 'h/beta': up('web-dev'), 'h/gamma': up('db-admin') }, async (relay, posts, asked, env) => {
    const r = await sendWith(relay, addressed('TO-ROLE: web-dev'), [], env);
    assert.equal(r.code, 0, r.err); assert.equal(asked[0].to, '*');
    const none = await sendWith(relay, addressed('TO-ROLE: flutter-dev'), [], env);
    assert.equal(none.code, 4); assert.match(none.err, /no account holds flutter-dev/);
    const n = asked.length;
    const b = await sendWith(relay, valid, [], env);
    assert.equal(b.code, 0, b.err); assert.equal(asked.length, n, 'a broadcast is not checked');
  });
});

// A project with no integration, and no environment naming one, is NOT
// configured: the defaults were gzapp's until 2026-09-16, so any other
// project's working copy joined gzapp's channel with gzapp's token file.
test('integrationConfig comes from the project or the environment, never a default of another project', () => {
  const none = integrationConfig('no-such-project', {});
  assert.equal(none.configured, false);
  assert.match(none.reason, /projects\/no-such-project\/integration\/gzcoord\/config.json/);
  assert.match(none.reason, /CLAUDE_BRIDGE_URL and GZCOORD_CHANNEL/);
  assert.equal(none.channel, undefined, 'no channel is ever guessed');
  assert.equal(integrationConfig(undefined, {}).configured, false, 'no project: not configured either');
  const fromEnv = integrationConfig('no-such-project', { CLAUDE_BRIDGE_URL: 'http://127.0.0.1:1', GZCOORD_CHANNEL: 'x:y' });
  assert.deepEqual([fromEnv.configured, fromEnv.source, fromEnv.relay_url, fromEnv.channel, fromEnv.token_env_file], [true, 'environment', 'http://127.0.0.1:1', 'x:y', undefined]);
  assert.equal(integrationConfig('no-such-project', { CLAUDE_BRIDGE_URL: 'http://127.0.0.1:1' }).configured, false, 'half an environment override configures nothing');
  const gz = integrationConfig('gzapp', {});
  assert.equal(gz.configured, true);
  assert.match(gz.source, /projects\/gzapp\/integration\/gzcoord\/config.json$/);
  assert.equal(gz.channel, 'gzapp:gzcoord');
  assert.equal(integrationConfig('gzapp', { GZCOORD_CHANNEL: 'over:ride' }).channel, 'over:ride', 'the environment overrides a project file');
});

test('send stops, named, when no integration is configured — nothing is posted anywhere', async () => {
  await withRelay(async (relay, posts) => {
    const f = path.join(scratch('send-'), 'm.txt'); fs.writeFileSync(f, valid);
    // Outside any working copy, with no channel in the environment: whoami()
    // reports whatever project the runner's binding names; the fixture
    // strips the environment and points the fabric at an empty root so no
    // project file can be found.
    const emptyFabric = scratch('fabric-');
    const env = { ...process.env, HOME: path.dirname(f), CLAUDE_BRIDGE_URL: relay, CLAUDE_BRIDGE_AUTH_TOKEN: 'tok', AGENT_FABRIC_ROOT: emptyFabric };
    delete env.GZCOORD_CHANNEL;
    const r = await new Promise(resolve => execFile('node', [SEND, f], { env, encoding: 'utf8', cwd: emptyFabric },
      (e, out, err) => resolve({ code: e ? e.code : 0, out: String(out), err: String(err) })));
    assert.equal(r.code, 3, r.err);
    assert.match(r.err, /no GZCoord integration configured/);
    assert.match(r.err, /not sent/);
    assert.equal(posts.length, 0);
  });
});

test('send refuses a message that does not validate, and posts nothing', async () => {
  await withRelay(async (relay, posts) => {
    // Two addresses at once (SPEC §7.1). A missing MESSAGE-ID was the
    // example here until the sender began minting one.
    const r = await sendWith(relay, valid.replace('BROADCAST: true', 'BROADCAST: true\nTO-ROLE: backend-dev'));
    assert.equal(r.code, 2); assert.match(r.err, /not sent/); assert.equal(posts.length, 0);
  });
});

test('send refuses an id the deployment did not mint — the literal $ID reached the channel once', async () => {
  await withRelay(async (relay, posts) => {
    const r = await sendWith(relay, valid.replace('MESSAGE-ID: 01a09fc1-0000-7000-8000-000000000001', 'MESSAGE-ID: $ID'));
    assert.equal(r.code, 2); assert.match(r.err, /MESSAGE-ID is the literal \$ID — the shell variable was not expanded/); assert.match(r.err, /not sent/); assert.equal(posts.length, 0);
    // ONCE: the complaint is also the refusal, and send suppresses the
    // duplicate warning. That suppression matched its own English until a
    // translated warning silently stopped matching, and nothing counted —
    // so this counts (blind review, PR #28).
    assert.equal(r.err.match(/is the literal \$ID/g).length, 1, r.err);
    const reply = await sendWith(relay, valid.replace('SUBJECT: fixture', 'IN-REPLY-TO: ${PREV}\nSUBJECT: fixture'));
    assert.equal(reply.code, 2); assert.match(reply.err, /IN-REPLY-TO is the literal \$\{PREV\}/); assert.equal(posts.length, 0);
    // The retired counter shape is still an id: older traffic is answered by it.
    const old = await sendWith(relay, valid.replace('SUBJECT: fixture', 'IN-REPLY-TO: db-admin-0007\nSUBJECT: fixture'));
    assert.equal(old.code, 0, old.err); assert.equal(posts.length, 1);
  });
});

test('send refuses a FROM that is not this session', async () => {
  await withRelay(async (relay, posts) => {
    const r = await sendWith(relay, valid.replace(`FROM: ${MY_ADDRESS}`, 'FROM: other-host/someone'));
    assert.equal(r.code, 2); assert.match(r.err, /FROM is other-host\/someone but this session is/); assert.equal(posts.length, 0);
  });
});

test('send --dry-run validates and resolves but posts nothing', async () => {
  await withRelay(async (relay, posts) => {
    const r = await sendWith(relay, valid, ['--dry-run']);
    assert.equal(r.code, 0); assert.equal(posts.length, 0);
  });
});

test('send carries a long line as written, with no width warning (the bridge does not re-break)', async () => {
  await withRelay(async (relay, posts) => {
    const wide = valid.replace(/\n$/, '') + '\n' + 'a path or an id that is longer than seventy-two columns: /home/x/projects/agent-fabric/runtime/claude-code/hooks/plan-hold.sh\n';
    const r = await sendWith(relay, wide);
    assert.equal(r.code, 0, r.err);
    assert.ok(!/columns wide/.test(r.err), `no width warning on the send path: ${r.err}`);
    assert.equal(posts[0].body.content, wide, 'the line is posted as written');
  });
});

test('send reminds a session that fell back that the flagged text must not travel', async () => {
  await withRelay(async (relay, posts) => {
    const dir = scratch('fallback-');
    fs.writeFileSync(path.join(dir, `${process.pid}.json`), JSON.stringify({ session_id: 's', pid: process.pid, from_model: 'claude-opus-5[1m]', to_model: 'claude-opus-4-8', at: '2026-09-16T11:46:21Z', category: 'cyber', topic: 'a cybersecurity issue' }));
    const r = await sendWith(relay, valid, [], { AGENT_FABRIC_FALLBACK_DIR: dir, CLAUDE_PID: String(process.pid) });
    assert.equal(r.code, 0, r.err);
    assert.match(r.err, /send: reminder — this session fell back from claude-opus-5\[1m\] to claude-opus-4-8 at 2026-09-16T11:46:21Z/, 'the reminder names the switch');
    assert.match(r.err, /flagged a request as a cybersecurity issue; filter anything that could be read as a cybersecurity issue out of this message/);
    assert.equal(posts.length, 1, 'a reminder, not a refusal: the message is posted');
    // a marker whose session is gone is not a fallback
    fs.writeFileSync(path.join(dir, `${process.pid}.json`), JSON.stringify({ session_id: 's', pid: 4194304000, from_model: 'a', to_model: 'b' }));
    const r2 = await sendWith(relay, valid, [], { AGENT_FABRIC_FALLBACK_DIR: dir, CLAUDE_PID: String(process.pid) });
    assert.equal(r2.code, 0); assert.ok(!/reminder/.test(r2.err), r2.err);
  });
});

test('send normalizes a pasted, indented message before validating', async () => {
  await withRelay(async (relay, posts) => {
    const r = await sendWith(relay, valid.split('\n').map(l => l ? '    ' + l : l).join('\n'));
    assert.equal(r.code, 0, r.err); assert.equal(posts[0].body.content, valid);
  });
});

// A refused token is not "unreachable": the relay answered. The inbox
// says the token was rotated and exits 4, so a watch loop can stop.
test('inbox reports a refused token as a rotation, exit 4', async () => {
  const server = http.createServer((req, res) => { res.statusCode = 401; res.setHeader('connection', 'close'); res.end('{}'); });
  await new Promise(r => server.listen(0, '127.0.0.1', r));
  const INBOX = fileURLToPath(new URL('../scripts/inbox.mjs', import.meta.url));
  const env = { ...process.env, HOME: scratch('home-'), AGENT_FABRIC_SECRET_STORE: idStore(), CLAUDE_BRIDGE_URL: `http://127.0.0.1:${server.address().port}`, CLAUDE_BRIDGE_AUTH_TOKEN: 'dead', GZCOORD_CHANNEL: 'fixture:chan' };
  const r = await new Promise(resolve => execFile('node', [INBOX, '--wait', '1'], { env, encoding: 'utf8' }, (e, out, err) => resolve({ code: e ? e.code : 0, err: String(err) })));
  server.closeAllConnections(); server.close();
  assert.equal(r.code, 4, r.err);
  assert.match(r.err, /refused this token \(HTTP 401\) — it was rotated; run bin\/fabric-secrets sync/);
});

// --replay re-reads one message without a consumer id (the cursor does
// not move) and shows a body only when the message is addressed to me.
test('inbox --replay shows a broadcast, withholds a body not for me, moves no cursor, and says so in --json', async () => {
  const mine = `[GZCOORD/1] INFO\nFROM: x/y\nROLE: backend-dev\nPROJECT: fixture\nBROADCAST: true\nMESSAGE-ID: 01a09fc1-0000-7000-8000-00000000000a\nSUBJECT: for all\n\nNOTES:\nBODY-FOR-ALL\n`;
  const theirs = `[GZCOORD/1] REPLY\nFROM: x/y\nROLE: backend-dev\nPROJECT: fixture\nTO: other-host/someone\nMESSAGE-ID: 01a09fc1-0000-7000-8000-00000000000b\nSUBJECT: private\n\nNOTES:\nBODY-PRIVATE\n`;
  const hits = [];
  const server = http.createServer((req, res) => {
    hits.push(req.url); res.setHeader('content-type', 'application/json'); res.setHeader('connection', 'close');
    res.end(JSON.stringify({ channel: 'fixture:chan', messages: [
      { seq: 7, id: 'r7', ts: 'T7', sender: 'x/y', content: mine }, { seq: 8, id: 'r8', ts: 'T8', sender: 'x/y', content: theirs }] }));
  });
  await new Promise(r => server.listen(0, '127.0.0.1', r));
  const INBOX = fileURLToPath(new URL('../scripts/inbox.mjs', import.meta.url));
  const env = { ...process.env, HOME: scratch('home-'), AGENT_FABRIC_SECRET_STORE: idStore(), CLAUDE_BRIDGE_URL: `http://127.0.0.1:${server.address().port}`, CLAUDE_BRIDGE_AUTH_TOKEN: 'tok', GZCOORD_CHANNEL: 'fixture:chan' };
  const run = args => new Promise(resolve => execFile('node', [INBOX, ...args], { env, encoding: 'utf8' }, (e, out, err) => resolve({ code: e ? e.code : 0, out: String(out), err: String(err) })));
  const a = await run(['--replay', '7']);
  const b = await run(['--replay', '01a09fc1-0000-7000-8000-00000000000b']);
  const c = await run(['--replay', '99']);
  const aj = await run(['--replay', '7', '--json']);
  const bj = await run(['--replay', '8', '--json']);
  server.closeAllConnections(); server.close();
  // --json, for fabric-jobs add --request: the same read, the same withholding.
  assert.equal(aj.code, 0, aj.err);
  const aDoc = JSON.parse(aj.out);
  assert.deepEqual([aDoc.addressed, aDoc.seq, aDoc.type, aDoc.metadata.SUBJECT], [true, 7, 'INFO', 'for all']);
  assert.match(aDoc.text, /BODY-FOR-ALL/);
  assert.equal(bj.code, 2); assert.deepEqual(JSON.parse(bj.out), { addressed: false, seq: 8 });
  assert.equal(a.code, 0, a.err); assert.match(a.out, /BODY-FOR-ALL/); assert.match(a.out, /cursor unchanged/);
  assert.equal(b.code, 2); assert.doesNotMatch(b.out, /BODY-PRIVATE/); assert.match(b.out, /not addressed to/);
  assert.equal(c.code, 1); assert.match(c.err, /no message 99/);
  // /status is ensureRelay's liveness probe; nothing names a consumer and nothing acks.
  assert.ok(hits.every(u => u === '/status' || (u.startsWith('/api/messages?') && !u.includes('consumer_id'))), hits);
  assert.ok(!hits.some(u => u.includes('/api/ack') || u.includes('/api/wait')), hits);
});

// --history lists what is addressed to me in one call, from a seq on,
// withholding what is not, reading no body into the listing and moving no cursor.
test('inbox --history lists the messages addressed to me, from a seq, and moves no cursor', async () => {
  const msg = (n, to, subject) => `[GZCOORD/1] INFO\nFROM: x/y\nROLE: backend-dev\nPROJECT: fixture\n${to}\nMESSAGE-ID: 01a09fc1-0000-7000-8000-00000000000${n}\nSUBJECT: ${subject}\n\nNOTES:\nBODY-${n}\n`;
  const hits = [];
  const server = http.createServer((req, res) => {
    hits.push(req.url); res.setHeader('content-type', 'application/json'); res.setHeader('connection', 'close');
    res.end(JSON.stringify({ channel: 'fixture:chan', messages: [
      { seq: 5, id: 'r5', ts: 'T5', sender: 'x/y', content: msg(5, 'BROADCAST: true', 'early') },
      { seq: 7, id: 'r7', ts: 'T7', sender: 'x/y', content: msg(7, 'BROADCAST: true', 'for all') },
      { seq: 8, id: 'r8', ts: 'T8', sender: 'x/y', content: msg(8, 'TO: other-host/someone', 'private') }] }));
  });
  await new Promise(r => server.listen(0, '127.0.0.1', r));
  const INBOX = fileURLToPath(new URL('../scripts/inbox.mjs', import.meta.url));
  const env = { ...process.env, HOME: scratch('home-'), AGENT_FABRIC_SECRET_STORE: idStore(), CLAUDE_BRIDGE_URL: `http://127.0.0.1:${server.address().port}`, CLAUDE_BRIDGE_AUTH_TOKEN: 'tok', GZCOORD_CHANNEL: 'fixture:chan' };
  const run = args => new Promise(resolve => execFile('node', [INBOX, ...args], { env, encoding: 'utf8' }, (e, out, err) => resolve({ code: e ? e.code : 0, out: String(out), err: String(err) })));
  const all = await run(['--history']);
  const from = await run(['--history', '6']);
  const bad = await run(['--history', 'x']);
  server.closeAllConnections(); server.close();
  assert.equal(all.code, 0, all.err);
  assert.match(all.out, /2 addressed to you in the relay's last 3/); assert.match(all.out, / 5 .*early/); assert.match(all.out, / 7 .*for all/);
  assert.doesNotMatch(all.out, /private|BODY-/); assert.match(all.out, /gzcoord-inbox --replay <seq>/);
  assert.equal(from.code, 0, from.err); assert.match(from.out, /1 addressed to you/); assert.doesNotMatch(from.out, /early/);
  assert.equal(bad.code, 1); assert.match(bad.err, /usage: inbox\.mjs --history/);
  assert.ok(hits.every(u => u === '/status' || (u.startsWith('/api/messages?') && !u.includes('consumer_id'))), hits);
  assert.ok(!hits.some(u => u.includes('/api/ack') || u.includes('/api/wait')), hits);
});

// SPEC §7.2: a retransmission keeps its MESSAGE-ID. The watch shows the
// copy — the first may never have been read — marked with the earlier seq.
test('a retransmitted delivery is marked with the seq of the earlier copy; a first copy is not', async () => {
  const text = (id, from = 'x/y') => `[GZCOORD/1] INFO\nFROM: ${from}\nROLE: backend-dev\nPROJECT: fixture\nBROADCAST: true\nMESSAGE-ID: ${id}\nSUBJECT: s\n\nNOTES:\nn\n`;
  const rec = (seq, id, from) => ({ seq, id: `r${seq}`, sender: from ?? 'x/y', timestamp: `T${seq}`, content: text(id, from) });
  const A = '01a09fc1-0000-7000-8000-0000000000a1', B = '01a09fc1-0000-7000-8000-0000000000b1';
  const recent = { messages: [rec(4, A), rec(6, B, 'other/z'), rec(9, A), rec(10, B)] };
  const classify = r => ({ rec: r, msg: parse(r.content), isMine: true });
  const got = [classify(rec(9, A)), classify(rec(10, B))];
  await markRetransmissions(got, async () => recent);
  assert.equal(got[0].retransmitOf, 4);
  assert.equal(got[1].retransmitOf, undefined, 'the same id from another FROM is another message');
  const out = render({ classified: got }, { address: 'h/me' }, 'fixture:chan', undefined, {});
  assert.match(out, /retransmission: the same FROM and MESSAGE-ID arrived before as relay seq 4/);
  assert.equal((out.match(/retransmission:/g) ?? []).length, 1);
  const failed = [classify(rec(9, A))];
  await markRetransmissions(failed, async () => { throw new Error('relay down'); });
  assert.equal(failed[0].retransmitOf, undefined);
  await markRetransmissions(failed, async () => ({}));
  assert.equal(failed[0].retransmitOf, undefined, 'an answer that is not a list marks nothing');
  // A relay that never answers: the lookup gives up at its bound, marking nothing.
  const t0 = Date.now();
  await markRetransmissions(failed, () => new Promise(() => {}), 200);
  assert.ok(Date.now() - t0 < 1500, `the lookup waited ${Date.now() - t0} ms`);
  assert.equal(failed[0].retransmitOf, undefined);
  // A lookup that settles at once leaves nothing behind: a process that ran
  // it with a ten-second bound exits at once, not when the bound expires
  // (the timer is cleared on settle; #57 re-review N2).
  const INBOX = fileURLToPath(new URL('../scripts/inbox.mjs', import.meta.url));
  const t1 = Date.now();
  const child = spawnSync(process.execPath, ['--input-type=module', '-e',
    `import { markRetransmissions } from ${JSON.stringify(INBOX)}; await markRetransmissions([], async () => ({ messages: [] }), 10000); await markRetransmissions([{ isMine: true, rec: { seq: 2 }, msg: { metadata: { FROM: 'a', 'MESSAGE-ID': 'x' } } }], async () => ({ messages: [] }), 10000);`],
    { encoding: 'utf8', timeout: 9000 });
  assert.equal(child.status, 0, child.stderr);
  assert.ok(Date.now() - t1 < 5000, `the process lingered ${Date.now() - t1} ms after the lookup settled`);
});

// The environment is a snapshot; the synced file is current. A refused
// token is retried once with the file's value, and that is what recovers
// a watch re-armed from a pre-rotation shell.
test('the synced file is the token; the environment snapshot is not consulted while it exists', async () => {
  const home = scratch('home-');
  fs.mkdirSync(path.join(home, '.config', 'agent-fabric'), { recursive: true });
  fs.writeFileSync(path.join(home, '.config', 'agent-fabric', 'secrets.env'), "# x\nexport CLAUDE_BRIDGE_AUTH_TOKEN='fresh-token'\n");
  const seen = [];
  const server = http.createServer((req, res) => {
    seen.push(req.headers.authorization); res.setHeader('connection', 'close'); res.setHeader('content-type', 'application/json');
    if (req.url === '/status') { res.end('{}'); return; }
    if (req.headers.authorization !== 'Bearer fresh-token') { res.statusCode = 401; res.end('{}'); return; }
    res.end(JSON.stringify({ messages: [], next_cursor: null }));
  });
  await new Promise(r => server.listen(0, '127.0.0.1', r));
  const INBOX = fileURLToPath(new URL('../scripts/inbox.mjs', import.meta.url));
  const env = { ...process.env, HOME: home, AGENT_FABRIC_SECRET_STORE: idStore(), CLAUDE_BRIDGE_URL: `http://127.0.0.1:${server.address().port}`, CLAUDE_BRIDGE_AUTH_TOKEN: 'dead', GZCOORD_CHANNEL: 'fixture:chan' };
  const r = await new Promise(resolve => execFile('node', [INBOX, '--wait', '1'], { env, encoding: 'utf8' }, (e, out, err) => resolve({ code: e ? e.code : 0, out: String(out), err: String(err) })));
  server.closeAllConnections(); server.close();
  assert.equal(r.code, 0, r.err);
  assert.ok(seen.includes('Bearer fresh-token') && !seen.includes('Bearer dead'), seen);
  assert.doesNotMatch(r.err, /retrying/);
  assert.match(r.out + r.err, /nothing for you/);
});

// --follow is the watch: it blocks, prints a delivery as it lands, and
// does not return on a quiet spell. We cannot let it run forever in a
// test, so a stub relay returns one message then stalls; the child is
// killed after the message is observed.
test('inbox --follow prints a delivery and keeps running', async () => {
  const mine = `[GZCOORD/1] INFO\nFROM: x/y\nROLE: backend-dev\nPROJECT: fixture\nBROADCAST: true\nMESSAGE-ID: 01a09fc1-0000-7000-8000-00000000000f\nSUBJECT: live\n\nNOTES:\nFOLLOW-BODY\n`;
  let served = false;
  const server = http.createServer((req, res) => {
    res.setHeader('content-type', 'application/json'); res.setHeader('connection', 'close');
    if (req.url === '/status') { res.end('{}'); return; }
    if (req.url.startsWith('/api/wait')) {
      if (!served) { served = true; res.end(JSON.stringify({ messages: [{ seq: 5, id: 'r5', ts: 'T', sender: 'x/y', content: mine }], next_cursor: 'c' })); }
      else { /* stall: never respond, --follow keeps waiting */ }
      return;
    }
    res.end('{}');   // ack
  });
  await new Promise(r => server.listen(0, '127.0.0.1', r));
  const INBOX = fileURLToPath(new URL('../scripts/inbox.mjs', import.meta.url));
  const env = { ...process.env, HOME: scratch('home-'), AGENT_FABRIC_SECRET_STORE: idStore(), CLAUDE_BRIDGE_URL: `http://127.0.0.1:${server.address().port}`, CLAUDE_BRIDGE_AUTH_TOKEN: 'tok', GZCOORD_CHANNEL: 'fixture:chan' };
  const child = spawn('node', [INBOX, '--follow'], { env });
  let out = '';
  const done = new Promise(resolve => {
    child.stdout.on('data', d => { out += d; if (out.includes('FOLLOW-BODY')) resolve(); });
    setTimeout(resolve, 8000);
  });
  await done;
  const stillRunning = child.exitCode === null;
  child.kill('SIGKILL'); server.closeAllConnections(); server.close();
  assert.match(out, /FOLLOW-BODY/, 'the delivery was printed');
  assert.ok(stillRunning, '--follow did not exit after the delivery');
});

test('inbox --follow bounds a long delivery to one notification and names the replay', async () => {
  const body = Array.from({ length: 200 }, (_, i) => `line ${i} LONG-BODY`).join('\n') + '\nTHE-END\n';
  const mine = `[GZCOORD/1] INFO\nFROM: x/y\nROLE: backend-dev\nPROJECT: fixture\nBROADCAST: true\nMESSAGE-ID: 01a09fc1-0000-7000-8000-00000000002f\nSUBJECT: long\n\nNOTES:\n${body}`;
  let served = false;
  const server = http.createServer((req, res) => {
    res.setHeader('content-type', 'application/json'); res.setHeader('connection', 'close');
    if (req.url === '/status') { res.end('{}'); return; }
    if (req.url.startsWith('/api/wait')) {
      if (!served) { served = true; res.end(JSON.stringify({ messages: [{ seq: 77, id: 'r77', ts: 'T', sender: 'x/y', content: mine }], next_cursor: 'c' })); }
      return;
    }
    res.end('{}');
  });
  await new Promise(r => server.listen(0, '127.0.0.1', r));
  const INBOX = fileURLToPath(new URL('../scripts/inbox.mjs', import.meta.url));
  const env = { ...process.env, HOME: scratch('home-'), AGENT_FABRIC_SECRET_STORE: idStore(), CLAUDE_BRIDGE_URL: `http://127.0.0.1:${server.address().port}`, CLAUDE_BRIDGE_AUTH_TOKEN: 'tok', GZCOORD_CHANNEL: 'fixture:chan' };
  const child = spawn('node', [INBOX, '--follow'], { env });
  let out = '';
  await new Promise(resolve => { child.stdout.on('data', d => { out += d; if (out.includes('--replay 77]')) setTimeout(resolve, 200); }); setTimeout(resolve, 8000); });
  child.kill('SIGKILL'); server.closeAllConnections(); server.close();
  assert.ok(out.length <= NOTIFICATION_CAP + 1, `the event is bounded: ${out.length}`);
  assert.ok(out.includes('SUBJECT: long\n\nNOTES:\nline 0 LONG-BODY'), 'metadata and the body head are there');
  assert.ok(!out.includes('THE-END'), 'the tail is not');
  assert.ok(out.includes('[gzcoord: body cut here to fit one notification — the whole message: gzcoord-inbox --replay 77]'));
});

// The hold: while the session plans, the watch polls nothing.
test('holdStatus: held iff some marker names a live harness of this login', () => {
  const dir = scratch('hold-');
  const f = pid => path.join(dir, `${pid}.json`);
  const uid = process.getuid();
  assert.equal(holdStatus(path.join(dir, 'none')).held, false, 'no directory');
  assert.equal(holdStatus(dir).held, false, 'empty directory');
  fs.writeFileSync(f(11), 'not json');
  assert.match(holdStatus(dir).reason, /11\.json: unreadable/);
  fs.writeFileSync(f(12), JSON.stringify({ session_id: 's' }));
  assert.match(holdStatus(dir).reason, /12\.json: names no pid/);
  fs.writeFileSync(f(process.pid), JSON.stringify({ session_id: 'me', pid: process.pid, start: pidStart(process.pid), since: 't' }));
  const h = holdStatus(dir);
  assert.equal(h.held, true, 'our own pid, alive, same start time');
  assert.deepEqual(h.sessions.map(x => x.pid), [process.pid]);
  // liveness is "answers a signal as this login": EPERM (another login's process) is not a hold
  assert.equal(holdStatus(dir, { isAlive: () => false }).held, false, 'a dead pid is not a hold');
  assert.match(holdStatus(dir, { isAlive: () => false }).reason, /is gone/);
  // the production liveness: pid 1 answers EPERM to an unprivileged login and is nobody's harness
  if (process.getuid() !== 0) {
    assert.equal(pidAlive(1), false, 'EPERM is not alive');
    fs.writeFileSync(f(1), JSON.stringify({ session_id: 'forged', pid: 1, start: '' }));
    const forged = holdStatus(dir);
    assert.deepEqual(forged.sessions.map(x => x.pid), [process.pid], 'a forged marker naming pid 1 does not hold, with the default isAlive');
    fs.unlinkSync(f(1));
  }
  assert.equal(pidAlive(4194304000), false, 'ESRCH is not alive');
  assert.equal(pidAlive(process.pid), true);
  // a reused pid: the start time differs
  assert.equal(holdStatus(dir, { startOf: () => 'other' }).held, false, 'a pid with another start time is not the harness');
  assert.match(holdStatus(dir, { startOf: () => 'other' }).reason, /reused/);
  assert.equal(holdStatus(dir, { startOf: () => '' }).held, true, 'an unknown start time (off Linux) falls back to the pid');
  // two sessions: held while either is live
  fs.writeFileSync(f(4194304000), JSON.stringify({ session_id: 'gone', pid: 4194304000 }));
  assert.equal(holdStatus(dir).held, true, 'one live marker among dead ones holds');
  // ownership: the directory and each file must be this login's
  assert.equal(holdStatus(dir, { uid: uid + 1 }).held, false);
  assert.match(holdStatus(dir, { uid: uid + 1 }).reason, /not this login's/);
  const link = path.join(scratch('hold-link-'), 'link');
  fs.symlinkSync(dir, link);
  assert.match(holdStatus(link).reason, /not a directory/, 'a symlinked directory is refused');
  // the path is under the login's home, overridable for tests
  assert.equal(holdDir('/h'), '/h/.cache/agent-fabric/hold');
  process.env.AGENT_FABRIC_HOLD_DIR = dir;
  assert.equal(holdDir(), dir);
  delete process.env.AGENT_FABRIC_HOLD_DIR;
});

test('waitLoop: held polls nothing, a hold mid-slice cuts the slice, release delivers', async () => {
  const me = { address: 'develop-qzapp/db-admin', instance: 'db-admin', slug: 'db-admin' };
  const rec = id => ({ id, sender: 'develop-qzapp/x', timestamp: 't', content: `[GZCOORD/1] INFO\nFROM: develop-qzapp/x\nROLE: architect-cto\nPROJECT: gzapp\nMESSAGE-ID: x-${id}\nBROADCAST: true\n` });
  let held = true;
  let fetches = 0;
  const transitions = [];
  const sleep = () => new Promise(r => setImmediate(r));
  // 1. Held from the start: the fetch is never called until the hold clears.
  let ticks = 0;
  const p = waitLoop({ fetchPage: async () => { fetches += 1; return { messages: [rec('m1')] }; }, ack: async () => {}, waitTotal: 1800,
                       forMeFn: msg => forMe(msg, me), held: () => { ticks += 1; if (ticks > 5) held = false; return held; },
                       onHold: h => transitions.push(h), sleep });
  const r = await p;
  assert.equal(r.delivered, true, 'delivered once released');
  assert.equal(fetches, 1, 'no poll while held');
  assert.ok(ticks > 5, 'the hold was checked repeatedly');
  assert.deepEqual(transitions, [true, false], 'told once on hold and once on release');
  // 2. A hold that begins during a slice aborts it; nothing is acknowledged; the
  //    message waits on the relay (the fake re-serves it) and lands after release.
  let holdNow = false;
  const acked = [];
  let served = 0;
  const fetchPage = (slice, signal) => new Promise((resolve, reject) => {
    served += 1;
    if (served === 1) {
      // a long poll that would deliver m2 after a while; the hold arrives first
      signal.addEventListener('abort', () => reject(Object.assign(new Error('aborted'), { name: 'AbortError' })));
      setTimeout(() => holdNow = true, 5);
    } else resolve({ messages: [rec('m2')] });
  });
  let checks = 0;
  const r2 = await waitLoop({ fetchPage, ack: async id => { acked.push(id); }, waitTotal: 1800, forMeFn: msg => forMe(msg, me),
                              held: () => { if (holdNow) { checks += 1; if (checks > 3) holdNow = false; } return holdNow; },
                              holdPollMs: 1 });
  assert.equal(r2.delivered, true);
  assert.equal(served, 2, 'the cut slice was retried after release');
  assert.deepEqual(acked, ['m2'], 'nothing was acknowledged for the cut slice');
  // 3. A page that resolves in the same tick the hold begins is dropped unread: nothing acked, re-shown after release.
  let calls = 0, checksAfterFirst = 0;
  const acked3 = [];
  // held: false before the first fetch; true for the four checks after it returns (the
  // post-fetch check, the loop-top check and two sleeps); false from then on.
  const r3 = await waitLoop({ fetchPage: async () => { calls += 1; return { messages: [rec('m3')] }; }, ack: async id => { acked3.push(id); }, waitTotal: 1800,
                              forMeFn: msg => forMe(msg, me), held: () => calls >= 1 && ++checksAfterFirst <= 4, holdPollMs: 1, sleep });
  assert.equal(r3.delivered, true);
  assert.deepEqual(acked3, ['m3'], 'the page that landed with the hold was not acknowledged; the retry was');
  assert.ok(calls >= 2, 'fetched again after release');
  // 4. A fetch that fails for its own reason still throws (the watch reports the relay).
  await assert.rejects(waitLoop({ fetchPage: async () => { throw new Error('relay down'); }, ack: async () => {}, waitTotal: 4, forMeFn: () => false }), /relay down/);
});

test('inbox --follow polls nothing while the hold marker names a live pid', async () => {
  const mine = `[GZCOORD/1] INFO\nFROM: x/y\nROLE: backend-dev\nPROJECT: fixture\nBROADCAST: true\nMESSAGE-ID: 01a09fc1-0000-7000-8000-00000000001f\nSUBJECT: live\n\nNOTES:\nHELD-BODY\n`;
  let waits = 0;
  const server = http.createServer((req, res) => {
    res.setHeader('content-type', 'application/json'); res.setHeader('connection', 'close');
    if (req.url === '/status') { res.end('{}'); return; }
    if (req.url.startsWith('/api/wait')) {
      waits += 1;
      res.end(JSON.stringify({ messages: [{ seq: 5, id: 'r5', ts: 'T', sender: 'x/y', content: mine }], next_cursor: 'c' }));
      return;
    }
    res.end('{}');
  });
  await new Promise(r => server.listen(0, '127.0.0.1', r));
  const holdDir = scratch('hold-');
  fs.chmodSync(holdDir, 0o700);
  const marker = path.join(holdDir, `${process.pid}.json`);
  fs.writeFileSync(marker, JSON.stringify({ session_id: 'plan', pid: process.pid, start: pidStart(process.pid), since: 'T' }));
  const INBOX = fileURLToPath(new URL('../scripts/inbox.mjs', import.meta.url));
  const env = { ...process.env, HOME: scratch('home-'), AGENT_FABRIC_SECRET_STORE: idStore(), AGENT_FABRIC_HOLD_DIR: holdDir,
                CLAUDE_BRIDGE_URL: `http://127.0.0.1:${server.address().port}`, CLAUDE_BRIDGE_AUTH_TOKEN: 'tok', GZCOORD_CHANNEL: 'fixture:chan' };
  const child = spawn('node', [INBOX, '--follow'], { env });
  let out = '', err = '';
  child.stdout.on('data', d => { out += d; });
  child.stderr.on('data', d => { err += d; });
  await new Promise(r => setTimeout(r, 2500));
  const waitsWhileHeld = waits;
  const outWhileHeld = out;
  fs.unlinkSync(marker);                       // the plan is approved
  await new Promise(resolve => { const t = setInterval(() => { if (out.includes('HELD-BODY')) { clearInterval(t); resolve(); } }, 50); setTimeout(() => { clearInterval(t); resolve(); }, 8000); });
  child.kill('SIGKILL'); server.closeAllConnections(); server.close();
  assert.equal(waitsWhileHeld, 0, 'the relay was not polled while held');
  assert.equal(outWhileHeld, '', 'nothing on stdout while held');
  assert.match(err, /inbox held/, 'the hold is said on stderr');
  assert.match(out, /HELD-BODY/, 'delivered once the marker was gone');
  // --held answers from the same marker
  fs.writeFileSync(marker, JSON.stringify({ session_id: 'plan', pid: process.pid, start: pidStart(process.pid), since: 'T' }));
  const h = spawnSync('node', [INBOX, '--held'], { env, encoding: 'utf8' });
  assert.equal(h.status, 0); assert.match(h.stdout, /^held: .* session plan \(pid \d+\)/);
  fs.unlinkSync(marker);
  fs.writeFileSync(path.join(holdDir, '4194304000.json'), JSON.stringify({ session_id: 'plan', pid: 4194304000, since: 'T' }));
  const n = spawnSync('node', [INBOX, '--held'], { env, encoding: 'utf8' });
  assert.equal(n.status, 1); assert.match(n.stdout, /^not held: 4194304000\.json: session 4194304000 is gone/);
});

// The notification cap: what one --follow event carries.
test('render under a cap: metadata whole, body cut at a line, the replay command last', () => {
  const me = { address: 'develop-qzapp/user', slug: 'fabric-coordinator' };
  const meta = (id, to = 'develop-qzapp/user') => `[GZCOORD/1] OBSERVATION\nFROM: develop-qzapp/x\nROLE: architect-cto\nPROJECT: gzapp\nTO: ${to}\nREPLY-EXPECTED: no\nMESSAGE-ID: 01a0a9dd-e876-73e2-a329-c5b7cf28ba${id}\nSUBJECT: subject ${id}`;
  const longBody = 'OBSERVATION:\n' + Array.from({ length: 150 }, (_, i) => `line ${i} of a long body`).join('\n') + '\nREQUEST:\nthe ask at the very end\n';
  const rec = (seq, content) => ({ id: `r${seq}`, seq, sender: 'develop-qzapp/x', timestamp: 'T', content });
  const mine = (seq, content) => ({ rec: rec(seq, content), msg: parse(content), isMine: true });
  const other = seq => { const c = meta(String(seq).padStart(2, '0'), 'develop-qzapp/z') + '\n'; return { rec: rec(seq, c), msg: parse(c), isMine: false }; };
  // a short delivery is untouched by the cap
  const short = render({ classified: [mine(1, meta('01') + '\n\nNOTES:\nshort\n')] }, me, 'c', undefined, { cap: NOTIFICATION_CAP });
  assert.equal(short, render({ classified: [mine(1, meta('01') + '\n\nNOTES:\nshort\n')] }, me, 'c'), 'under the cap, the same text as without one');
  assert.ok(!short.includes('--replay'));
  // a long one is cut by us, not by the harness
  const long = render({ classified: [mine(405, meta('05') + '\n\n' + longBody), other(406), other(407)] }, me, 'c', undefined, { cap: NOTIFICATION_CAP });
  assert.ok(long.length <= NOTIFICATION_CAP, `over the cap: ${long.length}`);
  assert.ok(long.includes('SUBJECT: subject 05\n\nOBSERVATION:\nline 0 of a long body\n'), 'metadata whole, body from its first line');
  assert.ok(!long.includes('the ask at the very end'), 'the tail was cut');
  assert.match(long, /\nline \d+ of a long body\n\n\[gzcoord: body cut here to fit one notification — the whole message: gzcoord-inbox --replay 405\]\n```/, 'cut at a line boundary; the replay command names the seq');
  assert.match(long, /Not addressed to you — listed, bodies not read \(SPEC §17\):\n  01a0a9dd-e876-73e2-a329-c5b7cf28ba406  OBSERVATION  TO develop-qzapp\/z  subject 406\n  01a0a9dd-e876-73e2-a329-c5b7cf28ba407/, 'others keep their metadata lines while they fit');
  // others fall back to a count naming their seqs only when even their lines do not fit
  const crowded = render({ classified: [mine(405, meta('05') + '\n\n' + longBody), ...Array.from({ length: 40 }, (_, i) => other(600 + i))] }, me, 'c', undefined, { cap: NOTIFICATION_CAP });
  assert.ok(crowded.length <= NOTIFICATION_CAP);
  assert.match(crowded, /40 not addressed to you \(seq 600–639\), not listed here: over the notification cap\./);
  assert.ok(!crowded.includes('output file'), 'nothing is claimed to be somewhere it is not');
  // F1: a wide line in an arrived message is not a warning, and cannot displace the metadata
  const wideBody = 'NOTES:\n' + Array.from({ length: 30 }, (_, i) => `line ${i} ` + 'w'.repeat(90)).join('\n') + '\n';
  const wide = render({ classified: [mine(430, meta('30') + '\n\n' + wideBody)] }, me, 'c', undefined, { cap: NOTIFICATION_CAP });
  assert.ok(!wide.includes('columns wide'), 'no width warning on the receive side');
  assert.ok(wide.includes('SUBJECT: subject 30\n\nNOTES:\nline 0 '), 'metadata whole, body from its first line');
  // validator lines are capped only under a cap: the drain shows them all
  const invalid = '[GZCOORD/1] INFO\nFROM: nobody\n\nNOTES:\nstray one\nstray two\nstray three\nstray four\nstray five\n';
  const invRec = { rec: rec(460, invalid), msg: { type: 'INFO', metadata: { BROADCAST: 'true' } }, isMine: true };
  const drained = render({ classified: [invRec] }, me, 'c');
  const watched = render({ classified: [invRec] }, me, 'c', undefined, { cap: NOTIFICATION_CAP });
  assert.ok(!drained.includes('more validator lines') && (drained.match(/INVALID:/g) || []).length > 4, 'the drain shows every validator line');
  assert.ok(watched.includes('more validator lines') && (watched.match(/INVALID:/g) || []).length === 4, 'the watch caps them');
  // F2: no blank line after the metadata (SPEC §6 MAY), and CRLF — still split at the section marker
  assert.deepEqual(splitMessage('A: 1\nB: 2\nNOTES:\nx\n\ny\n'), { meta: 'A: 1\nB: 2', body: 'NOTES:\nx\n\ny' });
  assert.deepEqual(splitMessage('A: 1\r\nB: 2\r\n\r\nNOTES:\r\nx\r\n'), { meta: 'A: 1\nB: 2', body: 'NOTES:\nx' });
  assert.deepEqual(splitMessage('A: 1\nB: 2\n'), { meta: 'A: 1\nB: 2', body: '' });
  const noBlank = render({ classified: [mine(440, meta('40') + '\n' + longBody)] }, me, 'c', undefined, { cap: NOTIFICATION_CAP });
  assert.ok(noBlank.length <= NOTIFICATION_CAP);
  assert.ok(noBlank.includes('SUBJECT: subject 40\n\nOBSERVATION:\nline 0 of a long body') && noBlank.includes('--replay 440]'), 'metadata and body head present without a blank line in the source');
  // F5: the cut is always at a line boundary — a first line longer than the budget keeps nothing of the body
  const oneLine = render({ classified: [mine(450, meta('50') + '\n\nNOTES:\n' + 'z'.repeat(5000) + '\n')] }, me, 'c', undefined, { cap: NOTIFICATION_CAP });
  assert.ok(oneLine.length <= NOTIFICATION_CAP);
  assert.ok(!oneLine.includes('zzzzzzzz'), 'no mid-line slice');
  assert.ok(oneLine.includes('SUBJECT: subject 50\n\nNOTES:\n\n[gzcoord: body cut here'), 'metadata, the section marker that fits, then the notice');
  assert.equal(REPLAY_CMD, 'gzcoord-inbox --replay');
  // two long messages share the budget; each carries its own replay line
  const two = render({ classified: [mine(410, meta('10') + '\n\n' + longBody), mine(411, meta('11') + '\n\n' + longBody)] }, me, 'c', undefined, { cap: NOTIFICATION_CAP });
  assert.ok(two.length <= NOTIFICATION_CAP);
  assert.ok(two.includes('--replay 410]') && two.includes('--replay 411]'));
  assert.ok(two.includes('SUBJECT: subject 10\n\nOBSERVATION:\nline 0') && two.includes('SUBJECT: subject 11\n\nOBSERVATION:\nline 0'));
  // a short and a long one: the short one is whole, the long one gets the rest
  const mixed = render({ classified: [mine(420, meta('20') + '\n\nNOTES:\nwhole\n'), mine(421, meta('21') + '\n\n' + longBody)] }, me, 'c', undefined, { cap: NOTIFICATION_CAP });
  assert.ok(mixed.length <= NOTIFICATION_CAP);
  assert.ok(mixed.includes('NOTES:\nwhole\n```') && !mixed.includes('--replay 420]'), 'the short message is whole and carries no cut notice');
  assert.ok(mixed.includes('--replay 421]'));
  // more messages than the metadata alone allows: one line each
  const many = render({ classified: Array.from({ length: 20 }, (_, i) => mine(500 + i, meta(String(i).padStart(2, '0')) + '\n\n' + longBody)) }, me, 'c', undefined, { cap: NOTIFICATION_CAP });
  assert.ok(many.length <= NOTIFICATION_CAP);
  assert.match(many, /\(over the notification cap: each message by its seq/);
  assert.ok(many.includes('  seq 500  01a0a9dd-e876-73e2-a329-c5b7cf28ba00  OBSERVATION  TO develop-qzapp/user  subject 00'));
  assert.ok(many.includes('  seq 519  '), 'twenty one-liners fit');
  assert.ok(!many.includes('… and'), 'nothing was dropped from the listing');
  // F4: when even the one-liners do not fit, the tail says how many and which seqs
  const fifty = render({ classified: Array.from({ length: 50 }, (_, i) => mine(700 + i, meta(String(i).padStart(2, '0')) + '\n\n' + longBody)), ...[] }, me, 'c', undefined, { cap: NOTIFICATION_CAP });
  assert.ok(fifty.length <= NOTIFICATION_CAP);
  assert.match(fifty, /\n  … and \d+ more for you \(seq 7\d\d–749\), each read with --replay <seq>$/, `a listing that dropped lines says so: ${fifty.slice(-200)}`);
});

// The control channel: machine records, never a session's.
test('a :control channel is refused by the drain, the watch and send, before any request reaches the relay', async () => {
  assert.throws(() => assertNotControlChannel('fabric:control'), /control channel/);
  assert.doesNotThrow(() => assertNotControlChannel('gzapp:gzcoord'));
  assert.doesNotThrow(() => assertNotControlChannel('x:controls'));
  const hits = [];
  const server = http.createServer((req, res) => { hits.push(req.url); res.setHeader('content-type', 'application/json'); res.end('{"messages":[]}'); });
  await new Promise(r => server.listen(0, '127.0.0.1', r));
  const INBOX = fileURLToPath(new URL('../scripts/inbox.mjs', import.meta.url));
  const env = { ...process.env, HOME: scratch('home-'), AGENT_FABRIC_SECRET_STORE: idStore(), CLAUDE_BRIDGE_URL: `http://127.0.0.1:${server.address().port}`, CLAUDE_BRIDGE_AUTH_TOKEN: 'tok', GZCOORD_CHANNEL: 'fabric:control' };
  for (const args of [[], ['--follow'], ['--wait', '1']]) {
    const r = spawnSync('node', [INBOX, ...args], { env, encoding: 'utf8', timeout: 10000 });
    assert.equal(r.status, 2, `inbox ${args.join(' ')}: exit ${r.status}\n${r.stderr}`);
    assert.match(r.stderr, /control channel/);
  }
  const f = path.join(env.HOME, 'm.txt'); fs.writeFileSync(f, valid);
  const s = spawnSync('node', [SEND, f], { env, encoding: 'utf8', timeout: 10000 });
  server.closeAllConnections(); server.close();
  assert.equal(s.status, 2, `send: exit ${s.status}\n${s.stderr}`);
  assert.match(s.stderr, /is a control channel[\s\S]*not sent/);
  assert.deepEqual(hits.filter(u => u.startsWith('/api/')), [], `a request reached the relay: ${hits}`);
});

// The hosting account's relay is a user unit once bootstrap installed it:
// ensureRelay starts the unit by name and never spawns beside it; a
// workspace without the venv is a client and hosts nothing; without a
// unit file (or a user manager) the detached spawn stays the fallback.
test('ensureRelay: a client hosts nothing; with the unit installed the relay is started by name, not spawned', () => {
  const runtime = scratch('gzc-');
  assert.deepEqual(ensureRelay(runtime, 'http://127.0.0.1:1'), { hosted: false, started: false }, 'no venv: a client');
  fs.mkdirSync(path.join(runtime, 'venv', 'bin'), { recursive: true });
  // a "claude-bridge" that would betray itself if spawned
  fs.writeFileSync(path.join(runtime, 'venv', 'bin', 'claude-bridge'), '#!/usr/bin/env bash\necho SPAWNED >> "$(dirname "$0")/../../spawned"\nsleep 30\n', { mode: 0o755 });
  fs.writeFileSync(path.join(runtime, 'bridge-token'), 'tok\n');
  const home = scratch('home-'); const bin = scratch('bin-');
  const xdg = scratch('xdg-'); fs.writeFileSync(path.join(xdg, 'bus'), '');
  fs.mkdirSync(path.join(home, '.config', 'systemd', 'user'), { recursive: true });
  fs.writeFileSync(path.join(home, '.config', 'systemd', 'user', 'gzcoord-relay.service'), '[Service]\n');
  // fake systemctl records the call; fake curl answers the probe only after systemctl ran
  fs.writeFileSync(path.join(bin, 'systemctl'), `#!/usr/bin/env bash\necho "$*" >> ${JSON.stringify(path.join(runtime, 'systemctl.log'))}\n`, { mode: 0o755 });
  fs.writeFileSync(path.join(bin, 'curl'), `#!/usr/bin/env bash\n[[ -f ${JSON.stringify(path.join(runtime, 'systemctl.log'))} ]]\n`, { mode: 0o755 });
  const saved = { HOME: process.env.HOME, PATH: process.env.PATH, XDG_RUNTIME_DIR: process.env.XDG_RUNTIME_DIR, GZCOORD_TEST_BUS_ANY: process.env.GZCOORD_TEST_BUS_ANY };
  // the fixture's bus is a plain file, not a socket: the test switch admits it
  Object.assign(process.env, { HOME: home, PATH: `${bin}:${process.env.PATH}`, XDG_RUNTIME_DIR: xdg, GZCOORD_TEST_BUS_ANY: '1' });
  try {
    const r = ensureRelay(runtime, 'http://127.0.0.1:1');
    assert.deepEqual(r, { hosted: true, started: true, unit: 'gzcoord-relay' }, JSON.stringify(r));
    assert.equal(fs.readFileSync(path.join(runtime, 'systemctl.log'), 'utf8').trim(), '--user start gzcoord-relay');
    assert.ok(!fs.existsSync(path.join(runtime, 'spawned')), 'the venv binary was not spawned beside the unit');
    // no unit file: the fallback spawns (and the fake binary says so)
    fs.rmSync(path.join(home, '.config', 'systemd', 'user', 'gzcoord-relay.service')); fs.rmSync(path.join(runtime, 'systemctl.log'));
    fs.writeFileSync(path.join(bin, 'curl'), `#!/usr/bin/env bash\n[[ -f ${JSON.stringify(path.join(runtime, 'spawned'))} ]]\n`, { mode: 0o755 });
    const f = ensureRelay(runtime, 'http://127.0.0.1:1');
    assert.equal(f.started, true); assert.ok(f.pid, 'the fallback spawned and reports a pid');
    assert.ok(fs.existsSync(path.join(runtime, 'spawned')));
    try { process.kill(f.pid, 'SIGKILL'); } catch { /* gone */ }
    // systemctl itself failing (no manager reachable): the spawn is the fallback, not an 8 s wait on nothing
    fs.writeFileSync(path.join(home, '.config', 'systemd', 'user', 'gzcoord-relay.service'), '[Service]\n');
    fs.rmSync(path.join(runtime, 'spawned')); fs.rmSync(path.join(runtime, 'systemctl.log'), { force: true });
    fs.writeFileSync(path.join(bin, 'systemctl'), '#!/usr/bin/env bash\nexit 1\n', { mode: 0o755 });
    const t0 = Date.now(); const s2 = ensureRelay(runtime, 'http://127.0.0.1:1');
    assert.equal(s2.started, true); assert.ok(s2.pid && !s2.unit, 'a failed systemctl falls back to the spawn');
    assert.ok(Date.now() - t0 < 6000, 'no eight-second wait on a unit that was never asked');
    try { process.kill(s2.pid, 'SIGKILL'); } catch { /* gone */ }
    // the passed environment: systemctl sees XDG_RUNTIME_DIR even when the shell had none
    fs.writeFileSync(path.join(bin, 'systemctl'), `#!/usr/bin/env bash\necho "XDG=$XDG_RUNTIME_DIR" >> ${JSON.stringify(path.join(runtime, 'systemctl.log'))}\n`, { mode: 0o755 });
    fs.writeFileSync(path.join(bin, 'curl'), `#!/usr/bin/env bash\n[[ -f ${JSON.stringify(path.join(runtime, 'systemctl.log'))} ]]\n`, { mode: 0o755 });
    delete process.env.XDG_RUNTIME_DIR;   // the shell has none: the resolved /run/user/<uid> must reach systemctl anyway
    const s3 = ensureRelay(runtime, 'http://127.0.0.1:1');
    if (s3.pid) { try { process.kill(s3.pid, 'SIGKILL'); } catch { /* gone */ } }
    assert.equal(s3.unit, 'gzcoord-relay', `the unit path must be taken with no XDG_RUNTIME_DIR in the shell: ${JSON.stringify(s3)}`);
    assert.match(fs.readFileSync(path.join(runtime, 'systemctl.log'), 'utf8'), /^XDG=\/run\/user\/\d+$/m, 'systemctl received the resolved runtime dir');
  } finally { for (const [k, v] of Object.entries(saved)) { if (v === undefined) delete process.env[k]; else process.env[k] = v; } }
});

// agent-fabric ADR-037 rule 5: the automatic request intake is built and
// off. Nothing runs without AGENT_FABRIC_JOBS_AUTO_INTAKE=1; with it, only
// a REPLY naming the message it answers reaches fabric-jobs.
test('send: the automatic job intake is off unless switched on, and then takes only a REPLY', async () => {
  const { autoIntake } = await import('../scripts/send.mjs');
  const calls = [];
  const opts = [];
  const run = (cmd, args, o) => { calls.push([cmd, ...args]); opts.push(o); return { status: 0, stdout: 'added j1\n', stderr: '' }; };
  const reply = { type: 'REPLY', metadata: { 'IN-REPLY-TO': '01a09fc1-0000-7000-8000-00000000000a' } };
  assert.equal(autoIntake(reply, {}, run), null, 'off by default');
  assert.equal(autoIntake(reply, { AGENT_FABRIC_JOBS_AUTO_INTAKE: '0' }, run), null, 'off unless exactly 1');
  assert.equal(autoIntake({ type: 'REQUEST', metadata: {} }, { AGENT_FABRIC_JOBS_AUTO_INTAKE: '1' }, run), null);
  assert.equal(autoIntake({ type: 'REPLY', metadata: {} }, { AGENT_FABRIC_JOBS_AUTO_INTAKE: '1' }, run), null);
  assert.equal(calls.length, 0);
  assert.equal(autoIntake(reply, { AGENT_FABRIC_JOBS_AUTO_INTAKE: '1' }, run).stdout, 'added j1\n');
  assert.equal(calls.length, 1);
  assert.deepEqual(calls[0].slice(0, 1).concat(calls[0].slice(2)),
    ['python3', 'add', '--request', '01a09fc1-0000-7000-8000-00000000000a', '--auto']);
  assert.match(calls[0][1], /tools\/fabric\/jobs\.py$/);
  assert.ok(opts[0].timeout > 0 && opts[0].timeout <= 30000, 'bounded: a hung relay must not hold a send that succeeded');
  // The launcher never sets the switch. Since Wave 4 (ADR-040) the launcher
  // is a module behind a shim: both are read, and a source that moves fails
  // the read rather than passing it by finding nothing.
  for (const rel of ['runtime/openrouter/launch', 'tools/fabric/launch.py'])
    assert.doesNotMatch(fs.readFileSync(new URL(`../../../${rel}`, import.meta.url), 'utf8'), /AGENT_FABRIC_JOBS_AUTO_INTAKE/, rel);
});

test('a trimmed sent ledger starts with one watermark, the oldest kept entry\'s time (review of #84)', async () => {
  const { recordSent, spentElsewhere } = await import('../scripts/send.mjs');
  const ledger = path.join(scratch('ledger-trim-'), 'gzcoord-sent.jsonl');
  const at = i => new Date(Date.UTC(2026, 9, 1) + i * 1000).toISOString();
  for (let i = 0; i < 9; i++) recordSent(ledger, { id: `m-${i}`, sha256: `h${i}`, seq: i, at: at(i) }, 3);
  assert.ok(!fs.readFileSync(ledger, 'utf8').includes('trimmed_before'), 'under the bound: no trim, no mark');
  for (let i = 9; i < 1012; i++) recordSent(ledger, { id: `m-${i}`, sha256: `h${i}`, seq: i, at: at(i) }, 3);
  const lines = fs.readFileSync(ledger, 'utf8').split('\n').filter(Boolean);
  const marks = lines.filter(l => l.includes('trimmed_before'));
  assert.equal(marks.length, 1, 'one watermark, however many trims');
  assert.equal(lines[0], marks[0], 'and it is the first line');
  const firstKept = JSON.parse(lines[1]);
  assert.equal(JSON.parse(marks[0]).trimmed_before, firstKept.at, 'it names the oldest kept entry\'s time');
  assert.deepEqual(spentElsewhere(ledger, firstKept.id, 'other'), firstKept, 'entries are still read past it');
});
