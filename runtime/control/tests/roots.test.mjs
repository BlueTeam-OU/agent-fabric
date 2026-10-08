// The control plane's readers of instance data follow the operator root
// (agent-fabric ADR-045 §5 rule 1): a tree of the test's own, with names no
// checkout carries, so a reader that still joined the engine's would not find them.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { scratch } from '../../../tests/scratch.mjs';
import { operatorAddresses, accountAddresses } from '../agentd.mjs';
import { placements } from '../ctl.mjs';
import { findTaxonomy, integrationConfig } from '../gzcoord.mjs';

const write = (root, rel, doc) => {
  fs.mkdirSync(path.dirname(path.join(root, rel)), { recursive: true });
  fs.writeFileSync(path.join(root, rel), JSON.stringify(doc));
};

function withOperator(fn) {
  const op = scratch('roots-operator-');
  write(op, 'runtime/hosts/registry.json', {
    hosts: { 'op-host': { ssh: null } }, placement: { 'op-login': 'op-host', 'op-agent': 'op-host' },
  });
  write(op, 'identities/roles/catalog.json', { roles: [{ id: 'op-role', description: 'x' }] });
  write(op, 'projects/opproj/integration/gzcoord/config.json', { relay_url: 'http://127.0.0.1:1', channel: 'op:chan' });
  const saved = { op: process.env.AGENT_FABRIC_OPERATOR, reg: process.env.AGENT_FABRIC_HOSTS_REGISTRY };
  process.env.AGENT_FABRIC_OPERATOR = op;
  delete process.env.AGENT_FABRIC_HOSTS_REGISTRY;
  try { return fn(op); } finally {
    for (const [k, v] of [['AGENT_FABRIC_OPERATOR', saved.op], ['AGENT_FABRIC_HOSTS_REGISTRY', saved.reg]])
      if (v === undefined) delete process.env[k]; else process.env[k] = v;
  }
}

test('placements reads the operator root\'s hosts registry', () => withOperator(() => {
  assert.deepEqual(placements().map(p => p.address).sort(), ['op-host/op-agent', 'op-host/op-login']);
}));

test('the daemon\'s address sets come from the operator root\'s hosts registry', () => withOperator(() => {
  assert.deepEqual([...accountAddresses()].sort(), ['op-host/op-agent', 'op-host/op-login']);
  assert.deepEqual([...operatorAddresses()], ['op-host/user']);
}));

test('the catalogue and a project\'s integration are the operator root\'s', () => withOperator(op => {
  assert.equal(findTaxonomy(), path.join(op, 'identities', 'roles', 'catalog.json'));
  const cfg = integrationConfig('opproj', {});
  assert.equal(cfg.configured, true);
  assert.equal(cfg.channel, 'op:chan');
}));
