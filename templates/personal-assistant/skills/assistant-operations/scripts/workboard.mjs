#!/usr/bin/env node
/** Durable projects, commitments, preferences, and versioned local procedures. */
import fs from 'node:fs';
import path from 'node:path';

const root = path.resolve(process.env.PA_WORKSPACE || '/workspace/agent');
const directory = path.join(root, 'work');
fs.mkdirSync(directory, { recursive: true });
const file = path.join(directory, 'state.json');
const lock = path.join(directory, '.lock');
const kinds = ['project', 'commitment', 'meeting', 'research', 'improvement'];
const empty = () => ({ version: 1, records: {}, preferences: [], capabilities: {}, history: [] });
const read = () => fs.existsSync(file) ? JSON.parse(fs.readFileSync(file, 'utf8')) : empty();
const [action = 'list', ...args] = process.argv.slice(2);
const idPattern = /^[a-z0-9][a-z0-9-]{0,63}$/;
const validId = (id) => { if (!idPattern.test(id || '')) throw new Error('Invalid record id.'); return id; };
const today = new Date().toISOString();

function mutate(operation) {
  let acquired = false;
  for (let attempt = 0; attempt < 50 && !acquired; attempt++) {
    try { fs.mkdirSync(lock); acquired = true; }
    catch (error) { if (error.code !== 'EEXIST') throw error; Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 100); }
  }
  if (!acquired) throw new Error('Workboard is busy. Retry; inspect work/.lock if a previous writer crashed.');
  try {
    const state = read();
    const result = operation(state);
    state.history.push({ at: today, action, id: args[0] || null });
    const temporary = `${file}.${process.pid}.tmp`;
    const fd = fs.openSync(temporary, 'w', 0o600);
    try { fs.writeFileSync(fd, JSON.stringify(state, null, 2) + '\n'); fs.fsyncSync(fd); }
    finally { fs.closeSync(fd); }
    fs.renameSync(temporary, file);
    const directoryFd = fs.openSync(directory, 'r');
    try { fs.fsyncSync(directoryFd); } finally { fs.closeSync(directoryFd); }
    return result;
  } finally { fs.rmdirSync(lock); }
}

function put(state) {
  const id = validId(args[0]);
  const input = JSON.parse(args[1] || '{}');
  if (Object.keys(input).some((key) => ['__proto__', 'constructor', 'prototype'].includes(key))) throw new Error('Invalid field.');
  const record = { ...state.records[id], ...input, id, updated_at: today };
  if (!kinds.includes(record.kind) || typeof record.title !== 'string' || !record.title.trim()) throw new Error('Record needs kind and title.');
  if (!['active', 'blocked', 'done', 'cancelled', 'proposed'].includes(record.status)) throw new Error('Invalid status.');
  if (record.kind === 'commitment' && (!record.source || record.explicit_owner !== true)) throw new Error('Commitments require explicit owner instruction and its source.');
  if (record.review_at && Number.isNaN(Date.parse(record.review_at))) throw new Error('review_at must be an ISO date.');
  if (JSON.stringify(record).length > 64000) throw new Error('Record too large; store artifacts in files.');
  state.records[id] = record;
  return record;
}

function capability(state) {
  const [id, mode, raw] = args;
  validId(id);
  const existing = state.capabilities[id] || { versions: [], active: null };
  if (mode === 'candidate') {
    const candidate = JSON.parse(raw || '{}');
    if (!candidate.procedure || !candidate.failure || !Array.isArray(candidate.cases) || !candidate.cases.length)
      throw new Error('Candidate requires observed failure, procedure, and acceptance cases.');
    if (JSON.stringify(candidate).length > 64000) throw new Error('Candidate too large.');
    existing.versions.push({ ...candidate, number: existing.versions.length + 1, created_at: today });
  } else if (mode === 'promote') {
    const candidate = existing.versions[Number(raw) - 1];
    if (!candidate || candidate.evaluation?.ok !== true || candidate.evaluation?.baseline_compared !== true || !candidate.evaluation?.evidence)
      throw new Error('Promotion requires passing evaluation, baseline comparison, and evidence path.');
    const evidencePath = path.resolve(root, candidate.evaluation.evidence);
    const labs = path.join(root, 'labs') + path.sep;
    if (!evidencePath.startsWith(labs) || !fs.realpathSync(evidencePath).startsWith(fs.realpathSync(path.join(root, 'labs')) + path.sep))
      throw new Error('Evaluation evidence must be a real file under labs/.');
    if (fs.statSync(evidencePath).size > 128000) throw new Error('Evidence exceeds 128K.');
    const proof = JSON.parse(fs.readFileSync(evidencePath, 'utf8'));
    if (proof.ok !== true || proof.baseline_compared !== true || !Array.isArray(proof.cases) ||
        !candidate.cases.every((label) => proof.cases.some((test) => test.name === label && test.pass === true)))
      throw new Error('Evidence must show every acceptance case passed and baseline was compared.');
    existing.previous = existing.active;
    existing.active = candidate.number;
    existing.monitor = { since: today, successes: 0, failures: 0 };
  } else if (mode === 'evaluate') {
    const evaluation = JSON.parse(raw || '{}');
    const candidate = existing.versions[existing.versions.length - 1];
    if (!candidate) throw new Error('No candidate.');
    candidate.evaluation = evaluation;
  } else if (mode === 'rollback') {
    const active = existing.active; existing.active = existing.previous ?? null; existing.previous = active;
  } else if (mode === 'monitor') {
    if (!existing.monitor) throw new Error('No promoted capability.');
    if (!['success', 'failure'].includes(raw)) throw new Error('Use success or failure.');
    existing.monitor[raw === 'success' ? 'successes' : 'failures']++;
    if (raw === 'failure') { existing.active = existing.previous ?? null; existing.monitor.rolled_back_at = today; }
  } else throw new Error('Use candidate, evaluate, promote, rollback, or monitor.');
  state.capabilities[id] = existing;
  return existing;
}

try {
  let result;
  if (action === 'put') result = mutate(put);
  else if (action === 'refine') result = mutate((state) => {
    const text = args[0]?.trim();
    if (!text || text.length > 4000) throw new Error('Preference needs 1–4000 characters.');
    state.preferences.push({ at: today, text, source: args[1] || 'owner Telegram instruction' });
    return state.preferences;
  });
  else if (action === 'capability') result = mutate(capability);
  else if (action === 'get') result = read().records[validId(args[0])] ?? null;
  else if (action === 'preferences') result = { preferences: read().preferences, capabilities: read().capabilities };
  else if (action === 'list' || action === 'due') {
    const state = read();
    result = Object.values(state.records).filter((r) => !['done', 'cancelled'].includes(r.status) &&
      (action !== 'due' || !r.review_at || Date.parse(r.review_at) <= Date.now()));
  } else throw new Error('Use list, due, get, put, refine, preferences, or capability.');
  console.log(JSON.stringify(result, null, 2));
} catch (error) { console.error(error.message); process.exitCode = 1; }
