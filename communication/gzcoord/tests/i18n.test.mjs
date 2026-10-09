// The lines the inbox prints, in the language of the login that reads
// them (i18n/README.md, docs/adr/ADR-028-house-i18n-standard-gzcoord-speaks-the-readers-language.md).
//
// The tools are Python now (tools/fabric/gzcoord/, agent-fabric ADR-040
// §7); this file keeps the cases that run them as commands, unchanged.
// The function cases are tests/test_gzcoord_i18n.py's, case for case.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import { scratch } from '../../../tests/scratch.mjs';

const FABRIC = fileURLToPath(new URL('../../../', import.meta.url));

// The dictionary is the one thing whose failure the last-resort handler
// cannot report through the dictionary. Copying the tools and i18n/ into a
// scratch tree is what makes a damaged en-US.json reachable at all: the
// default is resolved from the MODULE, deliberately, so nothing in the
// environment can point it elsewhere (blind review F1 on PR #28). The tree
// is the checkout's shape, the Python modules beside the shims that run
// them (ADR-040's 2026-10-01 amendment: a fixture may copy the modules of
// the scripts it copies); the entry is bin/gzcoord-inbox, beside them.
const brokenTree = (contents) => {
  const dir = scratch('i18n-broken-');
  const gz = path.join(dir, 'communication', 'gzcoord');
  for (const [from, to] of [['communication/gzcoord/scripts', path.join(gz, 'scripts')],
                            ['tools/fabric/gzcoord', path.join(dir, 'tools', 'fabric', 'gzcoord')]]) {
    fs.mkdirSync(to, { recursive: true });
    for (const f of fs.readdirSync(path.join(FABRIC, from)))
      if (fs.statSync(path.join(FABRIC, from, f)).isFile()) fs.copyFileSync(path.join(FABRIC, from, f), path.join(to, f));
  }
  // Every top-level module of tools/fabric, which the modules import as
  // siblings (roots, httpsafe, git): a list of the ones imported today went
  // stale the day relay.py took httpsafe, and the case failed on a missing
  // module, never on the dictionary.
  for (const f of fs.readdirSync(path.join(FABRIC, 'tools', 'fabric')))
    if (f.endsWith('.py') && fs.statSync(path.join(FABRIC, 'tools', 'fabric', f)).isFile())
      fs.copyFileSync(path.join(FABRIC, 'tools', 'fabric', f), path.join(dir, 'tools', 'fabric', f));
  // The modules' subpackages too (gzcoord/inbox_parts/): a module whose
  // parts were left behind does not import, and the case would fail on a
  // missing module, never on the dictionary it means to break.
  const mods = path.join(FABRIC, 'tools', 'fabric', 'gzcoord');
  for (const d of fs.readdirSync(mods))
    if (d !== '__pycache__' && fs.statSync(path.join(mods, d)).isDirectory())
      fs.cpSync(path.join(mods, d), path.join(dir, 'tools', 'fabric', 'gzcoord', d),
                { recursive: true, filter: src => !src.split(path.sep).includes('__pycache__') });
  fs.mkdirSync(path.join(gz, 'i18n'), { recursive: true });
  fs.writeFileSync(path.join(gz, 'i18n', 'en-US.json'), contents);
  fs.mkdirSync(path.join(dir, 'bin'));
  fs.copyFileSync(path.join(FABRIC, 'bin', 'gzcoord-inbox'), path.join(dir, 'bin', 'gzcoord-inbox'));
  fs.chmodSync(path.join(dir, 'bin', 'gzcoord-inbox'), 0o755);
  return path.join(dir, 'bin', 'gzcoord-inbox');
};

for (const [what, contents] of [['unparsable', '{ not json'], ['absent', null]]) {
  test(`a ${what} default dictionary degrades loudly and the tool still runs`, () => {
    const entry = brokenTree(contents ?? '{}');
    if (contents === null) fs.rmSync(path.join(path.dirname(entry), '..', 'communication', 'gzcoord', 'i18n', 'en-US.json'));
    const r = spawnSync(entry, ['--held'],
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
