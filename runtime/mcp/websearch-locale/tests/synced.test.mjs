// runtime/mcp/websearch-locale/synced.mjs: the cases of runtime/control/tests/
// gzcoord.test.mjs on syncedVar and shellWord, moved with the functions when
// the Node control plane was deleted (ADR-040 Wave 8, s8).
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { scratch } from '../../../../tests/scratch.mjs';
import { syncedVar, shellWord } from '../synced.mjs';

const secretsHome = text => {
  const home = scratch('home-');
  fs.mkdirSync(path.join(home, '.config', 'agent-fabric'), { recursive: true });
  if (text !== undefined) fs.writeFileSync(path.join(home, '.config', 'agent-fabric', 'secrets.env'), text);
  return home;
};
test('syncedVar reads one export line of the synced secrets file, unquoted', () => {
  const home = secretsHome("# x\nexport A='single'\nexport B=\"double\"\nexport C=bare  \nexport D=''\nexport AXB=not-a-dot\nexport A.B=dot\n");
  assert.equal(syncedVar('A', home), 'single');
  assert.equal(syncedVar('B', home), 'double');
  assert.equal(syncedVar('C', home), 'bare');
  assert.equal(syncedVar('D', home), undefined, 'an empty value is no value');
  assert.equal(syncedVar('MISSING', home), undefined);
  assert.equal(syncedVar('A.B', home), 'dot', 'the name is matched literally');
  assert.equal(syncedVar('A', secretsHome(undefined)), undefined, 'no file: not enrolled');
});

// sync writes each value with Python's shlex.quote and the Python readers
// take it back with shlex.split; this reader must agree with both on every
// value a store can hold on one line. The file is written by Python, as
// sync writes it, so the case is the real round trip, not a copy of it.
test('syncedVar reads back what shlex.quote wrote, as shlex.split does', () => {
  const values = ["it's", "'", "''", 'a"b', 'a\\b', '$HOME `x`', 'two words', ' lead', 'trail ', 'tab\there',
                  "x'\"'\"'y", '\\', 'ünïcödé', '#hash', 'a=b', 'plain'];
  const home = secretsHome(undefined);
  const file = path.join(home, '.config', 'agent-fabric', 'secrets.env');
  const py = spawnSync('python3', ['-I', '-c', `import json, shlex, sys
vals = json.load(sys.stdin)
with open(sys.argv[1], "w", encoding="utf-8") as fh:
    for i, v in enumerate(vals):
        fh.write(f"export V{i}={shlex.quote(v)}\\n")
back = []
for line in open(sys.argv[1], encoding="utf-8"):
    back.append((shlex.split(line.split("=", 1)[1]) or [None])[0])
print(json.dumps(back))`, file], { input: JSON.stringify(values), encoding: 'utf8' });
  assert.equal(py.status, 0, py.stderr);
  assert.deepEqual(JSON.parse(py.stdout), values, 'the Python reader takes back what was written');
  values.forEach((v, i) => assert.equal(syncedVar(`V${i}`, home), v, `value ${JSON.stringify(v)}`));
});

test('shellWord: the first word as shlex.split reads it; unterminated is no value', () => {
  assert.equal(shellWord("'a'\"'\"'b' tail"), "a'b");
  assert.equal(shellWord('"a\\"b\\\\c\\d"'), 'a"b\\c\\d', 'inside "…" a backslash escapes only " and \\');
  assert.equal(shellWord('a\\ b c'), 'a b');
  assert.equal(shellWord('  x  '), 'x');
  assert.equal(shellWord(''), null);
  assert.equal(shellWord("''"), '');
  for (const bad of ["'open", '"open', 'end\\', '"end\\']) assert.equal(shellWord(bad), null, bad);
  assert.equal(syncedVar('U', secretsHome("export U='open\n")), undefined, 'a malformed line gives no value');
});
