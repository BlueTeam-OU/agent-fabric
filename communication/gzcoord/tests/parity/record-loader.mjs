// The load hook record-hook.mjs registers: see there.
const WRAPPED = ['validate', 'parse', 'normalize'];
export async function load(url, context, next) {
  const result = await next(url, context);
  if (!url.endsWith('/communication/gzcoord/scripts/gzmsg.mjs') || !process.env.GZCOORD_PARITY_RECORD) return result;
  let src = String(result.source);
  for (const name of WRAPPED) {
    const decl = `export function ${name}(`;
    if (!src.includes(decl)) throw new Error(`parity hook: gzmsg.mjs no longer declares ${name}`);
    src = src.replace(decl, `function __parity_${name}(`);
  }
  src += `
import { appendFileSync as __parity_append } from 'node:fs';
function __parity_record(entry) { __parity_append(process.env.GZCOORD_PARITY_RECORD, JSON.stringify(entry) + '\\n'); }
// Declarations, not consts: gzmsg.mjs's CLI runs at module top level, before
// anything appended here would be initialised; a function is hoisted.
function __parity_tax(tx) { return tx ? { path: tx.path ?? null, roles: [...tx.roles.keys()] } : null; }
// The verdict recorded is the default printer's, whatever printer the
// caller passed: the corpus compares the validators' logic, in English.
export function validate(text, opts = {}) {
  const r = __parity_validate(text, opts);
  if (typeof text === 'string')
    __parity_record({ fn: 'validate', text, maxColumns: opts.maxColumns ?? null, taxonomy: __parity_tax(opts.taxonomy),
                      result: opts.t ? __parity_validate(text, { ...opts, t: undefined }) : r });
  return r;
}
export function parse(text, t) {
  let r, err = null;
  try { r = __parity_parse(text, t); } catch (e) { err = e; }
  if (typeof text === 'string') {
    // The default printer's answer, computed on its own: a throw is recorded
    // as its message, whichever printer the caller passed.
    let golden, goldenErr = null;
    try { golden = __parity_parse(text); } catch (e) { goldenErr = e; }
    __parity_record(goldenErr ? { fn: 'parse', text, error: goldenErr.message } : { fn: 'parse', text, result: golden });
  }
  if (err) throw err;
  return r;
}
export function normalize(text) {
  const r = __parity_normalize(text);
  if (typeof text === 'string') __parity_record({ fn: 'normalize', text, result: r });
  return r;
}
`;
  return { ...result, source: src, shortCircuit: true };
}
