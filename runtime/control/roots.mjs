// runtime/control/roots.mjs — the Node twin of tools/fabric/roots.py: the
// engine root, the operator root, and where instance data lives under the
// latter. The header of roots.py is the contract; tests/test_roots.py runs
// both on one matrix of environments and requires the same answers.
//
// Each helper takes `{ env, root, engine }`: env is the mapping read (default
// process.env), root an explicit operator tree that wins over everything,
// engine the engine tree the caller was handed (roots.py's header).
import path from 'node:path';
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';

export const ENV_ENGINE = 'AGENT_FABRIC_ROOT';
export const ENV_OPERATOR = 'AGENT_FABRIC_OPERATOR';
export const ENV_HOSTS_REGISTRY = 'AGENT_FABRIC_HOSTS_REGISTRY';

// Real path, as in roots.py: a link's directory is not the checkout's. fileURLToPath,
// not URL.pathname: .pathname keeps the percent-encoding of a checkout path
// with a space in it and names a file nothing has.
export const CODE_ROOT = path.dirname(path.dirname(path.dirname(fs.realpathSync(fileURLToPath(import.meta.url)))));

export function engineRoot({ env = process.env, emptyIsSet = false } = {}) {
  const v = env[ENV_ENGINE];
  if (v === undefined || (v === '' && !emptyIsSet)) return CODE_ROOT;
  return v;
}

export function operatorRoot({ env = process.env, emptyIsSet = false, engine } = {}) {
  const v = env[ENV_OPERATOR];
  if (v) return v;
  if (engine !== undefined) return engine;
  return engineRoot({ env, emptyIsSet });
}

const under = (o, ...parts) => path.join(o.root ?? operatorRoot({ env: o.env, engine: o.engine }), ...parts);

export const roleCatalog = (o = {}) => under(o, 'identities', 'roles', 'catalog.json');
export const rolesDir = (o = {}) => under(o, 'identities', 'roles');
export const roleDir = (role, o = {}) => under(o, 'identities', 'roles', role);
export const localeDir = (role, suffix, o = {}) => under(o, 'identities', 'roles', role, 'locale', suffix);
export const keysDir = (o = {}) => under(o, 'identities', 'keys');
export const recoveryKey = (o = {}) => under(o, 'identities', 'recovery.asc');
export const projectsRegistry = (o = {}) => under(o, 'projects', 'registry.json');
export const projectsDir = (o = {}) => under(o, 'projects');
export const projectIntegration = (project, parts = [], o = {}) => under(o, 'projects', project, 'integration', ...parts);

// AGENT_FABRIC_HOSTS_REGISTRY outranks the tree and an explicit root
// outranks neither, as in roots.py.
export function hostsRegistry(o = {}) {
  const override = (o.env ?? process.env)[ENV_HOSTS_REGISTRY];
  if (override || (override !== undefined && o.emptyIsSet)) return override;
  return under(o, 'runtime', 'hosts', 'registry.json');
}

export const policy = (name, o = {}) => under(o, 'policies', name);
export const policiesDir = (o = {}) => under(o, 'policies');
export const routingProfiles = (o = {}) => under(o, 'routing', 'profiles.json');
export const routingPolicy = (name, o = {}) => under(o, 'routing', 'policies', name);
export const memoryDir = (parts = [], o = {}) => under(o, 'memory', ...parts);
export const adrDir = (o = {}) => under(o, 'docs', 'adr');
