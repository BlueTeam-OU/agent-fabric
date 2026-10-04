// runtime/control/ops/util.mjs — the three helpers the parts share; ops.mjs never exported them, and does not now.
// A part of ops.mjs, which re-exports it; ops.mjs's header is the contract
// every extractor here keeps.

import fs from 'node:fs';
import crypto from 'node:crypto';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';


export function readJson(file) {
  try { return JSON.parse(fs.readFileSync(file, 'utf8')); } catch { return null; }
}


export const sha12 = v => crypto.createHash('sha256').update(v).digest('hex').slice(0, 12);

export const execFileP = promisify(execFile);
