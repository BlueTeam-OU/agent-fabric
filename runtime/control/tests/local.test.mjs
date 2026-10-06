// Each account's .claude/settings.local.json on the control plane: `local`
// reports names and counts, never a value; `local-prune`, a signed action,
// removes the env entries that duplicate a synced secret and nothing else.
// Through the real tools/fabric/local_settings.py, against a scratch home;
// tests/test_local_settings.py holds the tool's own behaviour.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { scratch } from '../../../tests/scratch.mjs';
import { fileURLToPath } from 'node:url';
import { local, localPrune } from '../local.mjs';
import { OPS, PUBLIC_OPS } from '../ops.mjs';
import { ACTION_OPS } from '../sign.mjs';
import { table, ACTION_OK } from '../ctl.mjs';

const VALUE = 'planted-value-never-reported';
const ROOT = fileURLToPath(new URL('../../../', import.meta.url));

function home() {
  const h = scratch('local-home-');
  const cfg = path.join(h, '.config', 'agent-fabric');
  fs.mkdirSync(cfg, { recursive: true });
  fs.writeFileSync(path.join(cfg, 'secrets.env'), `# agent-fabric secrets\nexport OPENAI_API_KEY='${VALUE}'\nexport DEMO_PORT_OFFSET=640\n`);
  fs.writeFileSync(path.join(cfg, 'env.sh'), '# agent-fabric secrets\nexport DEMO_PORT_OFFSET=640\n');
  const put = (wc, doc, mode = 0o600) => {
    const f = path.join(h, 'projects', wc, '.claude', 'settings.local.json');
    fs.mkdirSync(path.dirname(f), { recursive: true });
    fs.writeFileSync(f, typeof doc === 'string' ? doc : JSON.stringify(doc, null, 2));
    fs.chmodSync(f, mode);
    return f;
  };
  return { h, put };
}

test('local is an operator read, local-prune a signed action; neither is public', () => {
  assert.ok(OPS.includes('local') && OPS.includes('local-prune'));
  assert.ok(ACTION_OPS.includes('local-prune') && !ACTION_OPS.includes('local'));
  assert.ok(!PUBLIC_OPS.includes('local') && !PUBLIC_OPS.includes('local-prune'));
  assert.deepEqual(ACTION_OK['local-prune'], ['pruned', 'clean']);
});

test('local reports names and counts per working copy, never a value', async () => {
  const { h, put } = home();
  put('alpha', { env: { CLAUDE_BRIDGE_AUTH_TOKEN: VALUE, DEMO_PORT_OFFSET: '640', MY_FLAG: '1' }, permissions: { allow: ['Bash(ls)', 'Read'], deny: ['Bash(rm)'] }, enableAllProjectMcpServers: true });
  put('beta', {});
  put('gamma', '{not json');
  fs.mkdirSync(path.join(h, 'projects', 'delta'), { recursive: true });   // no settings file: not listed
  const r = await local({ home: h, root: ROOT });
  assert.equal(r.status, 'ok');
  assert.deepEqual(r.files.map(f => f.working_copy), ['alpha', 'beta', 'gamma']);
  const [a, b, g] = r.files;
  assert.deepEqual(a.env, ['CLAUDE_BRIDGE_AUTH_TOKEN', 'DEMO_PORT_OFFSET', 'MY_FLAG']);
  assert.deepEqual(a.secrets, ['CLAUDE_BRIDGE_AUTH_TOKEN']);
  assert.deepEqual(a.permissions, { allow: 2, deny: 1, ask: 0 });
  assert.deepEqual(a.keys, ['enableAllProjectMcpServers']);
  assert.deepEqual([b.env, b.secrets], [[], []]);
  assert.equal(g.status, 'not json');
  assert.ok(!JSON.stringify(r).includes(VALUE), 'no value in the report');
  const text = table('local', [{ account: 'web-dev-01', status: 'ok', local: r }]);
  assert.match(text, /alpha +ok +CLAUDE_BRIDGE_AUTH_TOKEN\* DEMO_PORT_OFFSET MY_FLAG  allow 2\/deny 1\/ask 0  enableAllProjectMcpServers/);
  assert.ok(!text.includes(VALUE));
});

test('local-prune runs the tool and takes no arguments', async () => {
  const { h, put } = home();
  const f = put('alpha', { env: { GH_TOKEN: VALUE, MY_FLAG: '1' } });
  const r = await localPrune({ from: 'h/op', to: ['h/a'] }, { home: h, root: ROOT });
  assert.equal(r.status, 'pruned', JSON.stringify(r));
  assert.deepEqual(JSON.parse(fs.readFileSync(f, 'utf8')), { env: { MY_FLAG: '1' } });
  assert.ok(!JSON.stringify(r).includes(VALUE));
  const text = table('local-prune', [{ account: 'web-dev-01', status: 'ok', localPrune: r }]);
  assert.match(text, /alpha +pruned +GH_TOKEN/);
  let ran = false;
  const refused = await localPrune({ args: { all: true } }, { home: h, root: ROOT, exec: async () => { ran = true; return '{}'; } });
  assert.deepEqual(refused, { status: 'refused', reason: 'local-prune takes no arguments' });
  assert.equal(ran, false);
});
