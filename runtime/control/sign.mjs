// runtime/control/sign.mjs — the operator's signature on a control request.
//
// The relay verifies no sender: any holder of the shared relay token can
// post a record whose `from` is the operator's address. That was a fence
// worth having while every op only reported (docs/adr/ADR-029-the-control-plane-a-control-agent-per-account.md
// §5 rule 4); an op that stops a session and installs software
// needs a proof. So an ACTION op is answered only when the request
// carries `sig`, an Ed25519 signature over its canonical form made with a
// key only the operator's Doppler config holds
// (FABRIC_CONTROL_SIGNING_KEY, synced into that login's secrets.env), and
// verified against the public key its host commits in
// runtime/hosts/registry.json (`operator_key`). Read-only ops stay
// unsigned-compatible: a daemon that cannot verify still reports.
//
// What the signature covers is every field but `sig`, keys sorted at
// every depth, so a relay or a re-serialisation that reorders keys cannot
// break it and no field — `to`, `ts`, the op's arguments — can be changed
// without breaking it. Replay is refused by the daemon's persisted
// per-operator action ledger (agentd.mjs actionLedger), inside the action
// ttl cap; an action dated in the future is refused before it can raise it.

import crypto from 'node:crypto';

export const ACTION_OPS = ['upgrade', 'secrets-sync'];
export const ACTION_TTL_MAX_S = 600;
export const KEY_PREFIX = 'ed25519:';
export const PRIVATE_PREFIX = 'ed25519-pkcs8:';   // one line: secrets.env is read a line at a time

export function canonical(value) {
  if (Array.isArray(value)) return `[${value.map(canonical).join(',')}]`;
  if (value && typeof value === 'object') {
    return `{${Object.keys(value).filter(k => value[k] !== undefined).sort().map(k => `${JSON.stringify(k)}:${canonical(value[k])}`).join(',')}}`;
  }
  return JSON.stringify(value);
}

function payload(request) {
  const { sig, ...rest } = request;
  return Buffer.from(canonical(rest), 'utf8');
}

export function privateKeyFrom(spec) {
  if (typeof spec !== 'string' || !spec.startsWith(PRIVATE_PREFIX)) return null;
  try { return crypto.createPrivateKey({ key: Buffer.from(spec.slice(PRIVATE_PREFIX.length), 'base64'), format: 'der', type: 'pkcs8' }); }
  catch { return null; }
}

export function signRequest(request, privateSpec) {
  const key = privateKeyFrom(privateSpec);
  if (!key) throw new Error('not an operator signing key (ed25519-pkcs8:<base64>)');
  return { ...request, sig: crypto.sign(null, payload(request), key).toString('base64') };
}

export function publicKeyFrom(spec) {
  if (typeof spec !== 'string' || !spec.startsWith(KEY_PREFIX)) return null;
  try { return crypto.createPublicKey({ key: Buffer.from(spec.slice(KEY_PREFIX.length), 'base64'), format: 'der', type: 'spki' }); }
  catch { return null; }
}

// True only for a well-formed signature by exactly this key.
export function verifyRequest(request, publicKey) {
  if (!publicKey || typeof request?.sig !== 'string' || !request.sig) return false;
  try { return crypto.verify(null, payload(request), publicKey, Buffer.from(request.sig, 'base64')); }
  catch { return false; }
}

// A new operator key pair: the private half for the operator's Doppler
// config, the public half for runtime/hosts/registry.json.
export function generateOperatorKey() {
  const { privateKey, publicKey } = crypto.generateKeyPairSync('ed25519');
  return {
    privateKeySpec: PRIVATE_PREFIX + privateKey.export({ type: 'pkcs8', format: 'der' }).toString('base64'),
    publicKeySpec: KEY_PREFIX + publicKey.export({ type: 'spki', format: 'der' }).toString('base64'),
  };
}
