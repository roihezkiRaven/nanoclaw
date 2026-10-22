import { initialCoverage, connectionCoverage, capturedCoverage, uploadedCoverage, type Coverage } from '../src/modules/personal-assistant/whatsapp-coverage.js';
/** Deterministic, allow-listed WhatsApp group archive collector. */
import { spawn } from 'child_process';
import { createHash } from 'crypto';
import fs from 'fs';
import path from 'path';

import {
  Browsers,
  BufferJSON,
  DisconnectReason,
  fetchLatestWaWebVersion,
  getContentType,
  makeCacheableSignalKeyStore,
  makeWASocket,
  proto,
  useMultiFileAuthState,
} from '@whiskeysockets/baileys';
import { pino } from 'pino';
import QRCode from 'qrcode';

const ROOT = '/home/assistant/nanoclaw';
const CONFIG = path.join(ROOT, 'config', 'whatsapp-collector.json');
const AUTH_DIR = path.join(ROOT, 'store', 'whatsapp-collector-auth');
const STATE_DIR = path.join(ROOT, 'store', 'whatsapp-collector');
const SEEN_FILE = path.join(STATE_DIR, 'seen.json');
const PENDING_DIR = path.join(STATE_DIR, 'pending');
const HEARTBEAT_FILE = path.join(STATE_DIR, 'heartbeat');
const MAX_TEXT_BYTES = 8_000;
const MAX_SEEN = 5_000;
const MAX_BATCH_RECORDS = 50;
const UPLOAD_INTERVAL_MS = 30_000;
const logger = pino({ level: 'silent' });

type AllowedGroup = { jid: string; label: string };
type Config = { allowedGroups: AllowedGroup[]; archiveParentId: string; activationAfter: number };
type ArchiveRecord = {
  collectedAt: string;
  groupJid: string;
  groupLabel: string;
  messageId: string;
  timestamp: string;
  senderJid: string;
  text: string;
};

function fail(message: string, code = 1): never {
  console.error(`whatsapp-collector: ${message}`);
  process.exit(code);
}

function loadConfig(): Config {
  let raw: unknown;
  try { raw = JSON.parse(fs.readFileSync(CONFIG, 'utf8')); } catch { fail('missing or invalid config'); }
  if (!raw || typeof raw !== 'object' || !Array.isArray((raw as Config).allowedGroups)) fail('allowedGroups is required');
  const archiveParentId = (raw as Config).archiveParentId;
  if (typeof archiveParentId !== 'string' || !/^[A-Za-z0-9_-]{10,100}$/.test(archiveParentId)) fail('archiveParentId is required');
  const activationAfter = (raw as Config).activationAfter;
  if (!Number.isInteger(activationAfter) || activationAfter < 1_577_836_800 || activationAfter > Math.floor(Date.now() / 1000) + 60) fail('activationAfter is required');
  const allowedGroups = (raw as Config).allowedGroups;
  if (!allowedGroups.length || allowedGroups.length > 100) fail('allowedGroups must contain 1–100 groups');
  const seen = new Set<string>();
  for (const group of allowedGroups) {
    if (!group || typeof group.jid !== 'string' || !/^[0-9-]+@g\.us$/.test(group.jid)) fail('invalid group JID');
    if (typeof group.label !== 'string' || !/^[\p{L}\p{N} ._()-]{1,80}$/u.test(group.label)) fail('invalid group label');
    if (seen.has(group.jid)) fail('duplicate group JID');
    seen.add(group.jid);
  }
  return { allowedGroups, archiveParentId, activationAfter };
}

function atomicWrite(file: string, contents: string | Buffer): void {
  fs.mkdirSync(path.dirname(file), { recursive: true, mode: 0o700 });
  const temporary = `${file}.${process.pid}.${Date.now()}.tmp`;
  const fd = fs.openSync(temporary, 'w', 0o600);
  try { fs.writeFileSync(fd, contents); fs.fsyncSync(fd); } finally { fs.closeSync(fd); }
  fs.renameSync(temporary, file);
  const directory = fs.openSync(path.dirname(file), 'r');
  try { fs.fsyncSync(directory); } finally { fs.closeSync(directory); }
}

async function collectorAuth(pairing = false) {
  const file = path.join(AUTH_DIR, 'creds.json');
  if (!pairing) {
    try {
      const creds = JSON.parse(fs.readFileSync(file, 'utf8'));
      if (!creds.me?.id || !creds.signedIdentityKey?.private || !creds.noiseKey?.private) throw new Error();
    } catch { fail('missing/corrupt credentials; stop collector and run pair to relink', 78); }
  }
  const { state } = await useMultiFileAuthState(AUTH_DIR);
  state.keys.set = async (data) => {
    for (const [category, entries] of Object.entries(data)) {
      for (const [id, value] of Object.entries(entries ?? {})) {
        const name = `${category}-${id}.json`.replace(/\//g, '__').replace(/:/g, '-');
        const target = path.join(AUTH_DIR, name);
        if (value) atomicWrite(target, JSON.stringify(value, BufferJSON.replacer));
        else fs.rmSync(target, { force: true });
      }
    }
  };
  const saveCreds = () => {
    if (fs.existsSync(file) && fs.statSync(file).size > 0) {
      atomicWrite(`${file}.backup`, fs.readFileSync(file, 'utf8'));
    }
    atomicWrite(file, JSON.stringify(state.creds, BufferJSON.replacer));
  };
  return { state, saveCreds };
}

async function pair(): Promise<void> {
  const service = spawn('systemctl', ['--user', 'is-active', '--quiet', 'whatsapp-collector.service']);
  const running = await new Promise<boolean>((resolve) => service.on('exit', (code) => resolve(code === 0)));
  if (running) fail('stop whatsapp-collector.service before pairing');
  if (fs.existsSync(AUTH_DIR)) fs.renameSync(AUTH_DIR, `${AUTH_DIR}.prelink-${Date.now()}`);
  const { state, saveCreds } = await collectorAuth(true);
  const sock = makeWASocket({ version: await version(), auth: state, logger,
    browser: Browsers.macOS('Chrome'), syncFullHistory: false });
  sock.ev.on('creds.update', saveCreds);
  sock.ev.on('connection.update', ({ connection, lastDisconnect, qr }) => {
    if (qr) void savePairingQr(qr);
    if (connection === 'open') {
      saveCreds();
      sock.end(undefined);
      void finishPairing();
    }
    if (connection === 'close') {
      const code = (lastDisconnect?.error as { output?: { statusCode?: number } })?.output?.statusCode;
      if (code === DisconnectReason.restartRequired) { void finishPairing(); return; }
      fail(`pairing failed (code=${code ?? 'unknown'})`);
    }
  });
}

async function savePairingQr(qr: string): Promise<void> {
  const file = path.join(AUTH_DIR, 'pairing-qr.png');
  try {
    const png = await QRCode.toBuffer(qr, { width: 512, margin: 4 });
    atomicWrite(file, png);
    console.log('whatsapp-collector: pairing QR ready');
  } catch { fail('could not render pairing QR'); }
}

async function finishPairing(): Promise<void> {
  await collectorAuth();
  fs.rmSync(path.join(AUTH_DIR, 'pairing-qr.png'), { force: true });
  const child = spawn('systemctl', ['--user', 'start', 'whatsapp-collector.service']);
  child.on('error', () => fail('pairing saved but collector could not start'));
  const code = await new Promise<number | null>((resolve) => child.on('exit', resolve));
  if (code !== 0) fail('pairing saved but collector could not start');
  console.log('whatsapp-collector: pairing saved; collector started');
  process.exit(0);
}

function heartbeat(): void {
  atomicWrite(HEARTBEAT_FILE, `${new Date().toISOString()}\n`);
}

function loadSeen(): Set<string> {
  try {
    const items = JSON.parse(fs.readFileSync(SEEN_FILE, 'utf8')) as unknown;
    return new Set(Array.isArray(items) ? items.filter((item): item is string => typeof item === 'string').slice(-MAX_SEEN) : []);
  } catch { return new Set(); }
}

function saveSeen(seen: Set<string>): void {
  atomicWrite(SEEN_FILE, JSON.stringify([...seen].slice(-MAX_SEEN)));
}

function recordKey(record: ArchiveRecord): string {
  return `${record.groupJid}:${record.messageId}`;
}

function pendingFile(record: ArchiveRecord): string {
  return path.join(PENDING_DIR, `${createHash('sha256').update(recordKey(record)).digest('hex')}.json`);
}

function enqueue(record: ArchiveRecord): boolean {
  const file = pendingFile(record);
  if (fs.existsSync(file)) return false;
  atomicWrite(file, JSON.stringify(record));
  return true;
}

type PendingRecord = { file: string; record: ArchiveRecord };

function pendingRecords(seen: Set<string>): PendingRecord[] {
  fs.mkdirSync(PENDING_DIR, { recursive: true, mode: 0o700 });
  const records: PendingRecord[] = [];
  for (const name of fs.readdirSync(PENDING_DIR).filter((entry) => entry.endsWith('.json')).sort()) {
    const file = path.join(PENDING_DIR, name);
    try {
      const record = JSON.parse(fs.readFileSync(file, 'utf8')) as ArchiveRecord;
      if (!record || typeof record.messageId !== 'string' || typeof record.groupJid !== 'string' || typeof record.text !== 'string') throw new Error('invalid queued record');
      if (seen.has(recordKey(record))) {
        fs.rmSync(file, { force: true });
        continue;
      }
      records.push({ file, record });
    } catch (error) {
      console.error(`whatsapp-collector: retaining unreadable pending file ${name}: ${error instanceof Error ? error.message : String(error)}`);
    }
    if (records.length === MAX_BATCH_RECORDS) break;
  }
  return records;
}

async function version(): Promise<[number, number, number]> {
  const { version: current } = await fetchLatestWaWebVersion({});
  if (!current) fail('cannot resolve WhatsApp Web version');
  return current as [number, number, number];
}

function textFrom(message: proto.IMessage | null | undefined): string | null {
  if (!message) return null;
  const type = getContentType(message);
  if (type === 'conversation') return message.conversation ?? null;
  if (type === 'extendedTextMessage') return message.extendedTextMessage?.text ?? null;
  return null;
}

function archive(records: ArchiveRecord[], parentId: string): Promise<{ id: string; modifiedTime: string }> {
  if (!records.length) throw new Error("empty upload batch");
  const stamp = new Date().toISOString().replace(/[:.]/g, '-');
  const file = path.join(STATE_DIR, `batch-${stamp}.jsonl`);
  atomicWrite(file, records.map((record) => JSON.stringify(record)).join('\n') + '\n');
  return new Promise((resolve, reject) => {
    const child = spawn(`${ROOT}/.venv-gdrive/bin/python`, [
      `${ROOT}/tools/gdrive_assistant.py`, 'writer', 'write', '--name', `whatsapp-raw-${stamp}.jsonl`, '--text-file', file, '--parent-id', parentId,
    ], { stdio: ['ignore', 'pipe', 'pipe'] });
    let output = '';
    child.stdout.on('data', (chunk) => { output += String(chunk); });
    let error = '';
    child.stderr.on('data', (chunk) => { error += String(chunk); });
    child.on('error', (error) => {
      fs.rmSync(file, { force: true });
      reject(error);
    });
    child.on('exit', (code) => {
      fs.rmSync(file, { force: true });
      if (code !== 0) return reject(new Error(error || `Drive archive exit ${code}`));
      try {
        const file = JSON.parse(output);
        if (!file.id || !file.modifiedTime || JSON.stringify(file.parents) !== JSON.stringify([parentId])) throw new Error('unverified archive result');
        resolve(file);
      } catch { reject(new Error('Archive created but metadata is unverified; inspect before retrying')); }
    });
  });
}

async function listGroups(): Promise<void> {
  const { state, saveCreds } = await collectorAuth();
  const sock = makeWASocket({ version: await version(), auth: { creds: state.creds, keys: makeCacheableSignalKeyStore(state.keys, logger) }, logger, browser: Browsers.macOS('Chrome'), syncFullHistory: false });
  sock.ev.on('creds.update', saveCreds);
  sock.ev.on('connection.update', async ({ connection, lastDisconnect }) => {
    if (connection === 'open') {
      const groups = await sock.groupFetchAllParticipating();
      console.log(JSON.stringify(Object.values(groups).map((group) => ({ jid: group.id, name: group.subject })).sort((a, b) => a.name.localeCompare(b.name)), null, 2));
      sock.end(undefined);
      process.exit(0);
    }
    if (connection === 'close') fail(`connection closed (${String(lastDisconnect?.error ?? 'unknown')})`);
  });
}

async function collect(): Promise<void> {
  const config = loadConfig();
  const groups = new Map(config.allowedGroups.map((group) => [group.jid, group]));
  const seen = loadSeen();
  const coverageFile = path.join(STATE_DIR, 'coverage.json');
  let coverage: Coverage;
  try { coverage = JSON.parse(fs.readFileSync(coverageFile, 'utf8')); if (coverage.version !== 1) throw new Error(); }
  catch (error) { if (fs.existsSync(coverageFile)) throw new Error('Invalid coverage checkpoint; preserve and repair it'); coverage = initialCoverage(config.allowedGroups, new Date().toISOString()); }
  const defaults = initialCoverage(config.allowedGroups, new Date().toISOString());
  for (const [jid, value] of Object.entries(defaults.groups)) coverage.groups[jid] ??= value;
  connectionCoverage(coverage, false, coverage.heartbeat);
  const saveCoverage = () => atomicWrite(coverageFile, JSON.stringify(coverage));
  saveCoverage();
  let flushing = false;
  const flush = async () => {
    if (flushing) return;
    const batch = pendingRecords(seen);
    if (!batch.length) return;
    flushing = true;
    try {
      const archived = await archive(batch.map(({ record }) => record), config.archiveParentId);
      uploadedCoverage(coverage, batch.map(({ record }) => record), archived, new Date().toISOString());
      saveCoverage();
      for (const { record } of batch) seen.add(recordKey(record));
      saveSeen(seen);
      atomicWrite(path.join(STATE_DIR, 'last-upload'), `${new Date().toISOString()}\n`);
      console.log(`whatsapp-collector: archived ${batch.length} records`);
      for (const { file } of batch) {
        fs.rmSync(file, { force: true });
      }
    } catch (error) {
      coverage.upload_error = new Date().toISOString() + ': upload failed or verification unavailable';
      saveCoverage();
      console.error(`whatsapp-collector: archive failed: ${error instanceof Error ? error.message : String(error)}`);
    } finally { flushing = false; }
  };
  fs.rmSync(HEARTBEAT_FILE, { force: true });
  const { state, saveCreds } = await collectorAuth();
  let connected = false;
  const sock = makeWASocket({
    version: await version(), auth: { creds: state.creds, keys: makeCacheableSignalKeyStore(state.keys, logger) }, logger,
    browser: Browsers.macOS('Chrome'), syncFullHistory: false,
    shouldIgnoreJid: (jid) => !groups.has(jid),
  });
  sock.ev.on('creds.update', saveCreds);
  sock.ev.on('messages.upsert', ({ type, messages }) => {
    if (type !== 'notify') return;
    for (const item of messages) {
      const jid = item.key.remoteJid;
      const id = item.key.id;
      if (!jid || !id || item.key.fromMe || !groups.has(jid) || seen.has(`${jid}:${id}`)) continue;
      const messageTimestamp = Number(item.messageTimestamp ?? 0);
      if (!Number.isFinite(messageTimestamp) || messageTimestamp < config.activationAfter) continue;
      const text = textFrom(item.message);
      if (!text || Buffer.byteLength(text, 'utf8') > MAX_TEXT_BYTES) continue;
      const record = { collectedAt: new Date().toISOString(), groupJid: jid, groupLabel: groups.get(jid)!.label, messageId: id, timestamp: new Date(messageTimestamp * 1000).toISOString(), senderJid: item.key.participant ?? 'unknown', text };
      if (enqueue(record)) { capturedCoverage(coverage, record); saveCoverage(); }
    }
  });
  sock.ev.on('connection.update', ({ connection, lastDisconnect }) => {
    if (connection === 'open') {
      connected = true;
      connectionCoverage(coverage, true, new Date().toISOString()); saveCoverage();
      heartbeat();
      console.log('whatsapp-collector: connected');
    }
    if (connection === 'close') {
      connected = false;
      connectionCoverage(coverage, false, new Date().toISOString()); saveCoverage();
      fs.rmSync(HEARTBEAT_FILE, { force: true });
      const code = (lastDisconnect?.error as { output?: { statusCode?: number } } | undefined)?.output?.statusCode;
      if (code === DisconnectReason.loggedOut) fail('logged out; relink required', 78);
      console.error(`whatsapp-collector: connection closed (code=${code ?? 'unknown'}); systemd will restart the collector`);
      process.exit(1);
    }
  });
  void flush();
  setInterval(() => { if (connected) { heartbeat(); coverage.heartbeat = new Date().toISOString(); saveCoverage(); } }, 30_000).unref();
  setInterval(() => void flush(), UPLOAD_INTERVAL_MS).unref();
  process.on('SIGTERM', () => { connectionCoverage(coverage, false, new Date().toISOString()); saveCoverage(); void flush().finally(() => process.exit(0)); });
}

if (process.argv[2] === 'list-groups') void listGroups();
else if (process.argv[2] === 'collect') void collect();
else if (process.argv[2] === 'pair') void pair();
else fail('usage: whatsapp_collector.ts <list-groups|collect|pair>');
