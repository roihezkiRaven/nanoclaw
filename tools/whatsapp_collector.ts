/** Deterministic, allow-listed WhatsApp group archive collector. */
import { spawn } from 'child_process';
import fs from 'fs';
import path from 'path';

import {
  Browsers,
  DisconnectReason,
  fetchLatestWaWebVersion,
  getContentType,
  makeCacheableSignalKeyStore,
  makeWASocket,
  proto,
  useMultiFileAuthState,
} from '@whiskeysockets/baileys';
import { pino } from 'pino';

const ROOT = '/home/assistant/nanoclaw';
const CONFIG = path.join(ROOT, 'config', 'whatsapp-collector.json');
const AUTH_DIR = path.join(ROOT, 'store', 'whatsapp-collector-auth');
const STATE_DIR = path.join(ROOT, 'store', 'whatsapp-collector');
const SEEN_FILE = path.join(STATE_DIR, 'seen.json');
const MAX_TEXT_BYTES = 8_000;
const MAX_SEEN = 5_000;
const logger = pino({ level: 'silent' });

type AllowedGroup = { jid: string; label: string };
type Config = { allowedGroups: AllowedGroup[]; archiveParentId: string };
type ArchiveRecord = {
  collectedAt: string;
  groupJid: string;
  groupLabel: string;
  messageId: string;
  timestamp: string;
  senderJid: string;
  text: string;
};

function fail(message: string): never {
  console.error(`whatsapp-collector: ${message}`);
  process.exit(1);
}

function loadConfig(): Config {
  let raw: unknown;
  try { raw = JSON.parse(fs.readFileSync(CONFIG, 'utf8')); } catch { fail('missing or invalid config'); }
  if (!raw || typeof raw !== 'object' || !Array.isArray((raw as Config).allowedGroups)) fail('allowedGroups is required');
  const archiveParentId = (raw as Config).archiveParentId;
  if (typeof archiveParentId !== 'string' || !/^[A-Za-z0-9_-]{10,100}$/.test(archiveParentId)) fail('archiveParentId is required');
  const allowedGroups = (raw as Config).allowedGroups;
  if (!allowedGroups.length || allowedGroups.length > 100) fail('allowedGroups must contain 1–100 groups');
  const seen = new Set<string>();
  for (const group of allowedGroups) {
    if (!group || typeof group.jid !== 'string' || !/^[0-9-]+@g\.us$/.test(group.jid)) fail('invalid group JID');
    if (typeof group.label !== 'string' || !/^[\p{L}\p{N} ._()-]{1,80}$/u.test(group.label)) fail('invalid group label');
    if (seen.has(group.jid)) fail('duplicate group JID');
    seen.add(group.jid);
  }
  return { allowedGroups, archiveParentId };
}

function loadSeen(): Set<string> {
  try {
    const items = JSON.parse(fs.readFileSync(SEEN_FILE, 'utf8')) as unknown;
    return new Set(Array.isArray(items) ? items.filter((item): item is string => typeof item === 'string').slice(-MAX_SEEN) : []);
  } catch { return new Set(); }
}

function saveSeen(seen: Set<string>): void {
  fs.mkdirSync(STATE_DIR, { recursive: true, mode: 0o700 });
  fs.writeFileSync(SEEN_FILE, JSON.stringify([...seen].slice(-MAX_SEEN)), { mode: 0o600 });
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

function archive(records: ArchiveRecord[], parentId: string): Promise<void> {
  if (!records.length) return Promise.resolve();
  const stamp = new Date().toISOString().replace(/[:.]/g, '-');
  const file = path.join(STATE_DIR, `batch-${stamp}.jsonl`);
  fs.mkdirSync(STATE_DIR, { recursive: true, mode: 0o700 });
  fs.writeFileSync(file, records.map((record) => JSON.stringify(record)).join('\n') + '\n', { mode: 0o600 });
  return new Promise((resolve, reject) => {
    const child = spawn(`${ROOT}/.venv-gdrive/bin/python`, [
      `${ROOT}/tools/gdrive_assistant.py`, 'writer', 'write', '--name', `whatsapp-raw-${stamp}.jsonl`, '--text-file', file, '--parent-id', parentId,
    ], { stdio: ['ignore', 'ignore', 'pipe'] });
    let error = '';
    child.stderr.on('data', (chunk) => { error += String(chunk); });
    child.on('error', reject);
    child.on('exit', (code) => code === 0 ? resolve() : reject(new Error(error || `Drive archive exit ${code}`)));
  });
}

async function listGroups(): Promise<void> {
  const { state, saveCreds } = await useMultiFileAuthState(AUTH_DIR);
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
  const pending: ArchiveRecord[] = [];
  let flushing = false;
  const flush = async () => {
    if (flushing || !pending.length) return;
    flushing = true;
    const batch = pending.splice(0);
    try { await archive(batch, config.archiveParentId); } catch (error) {
      pending.unshift(...batch);
      console.error(`whatsapp-collector: archive failed: ${error instanceof Error ? error.message : String(error)}`);
    } finally { flushing = false; }
  };
  const { state, saveCreds } = await useMultiFileAuthState(AUTH_DIR);
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
      if (!jid || !id || item.key.fromMe || !groups.has(jid) || seen.has(id)) continue;
      const text = textFrom(item.message);
      if (!text || Buffer.byteLength(text, 'utf8') > MAX_TEXT_BYTES) continue;
      seen.add(id);
      pending.push({ collectedAt: new Date().toISOString(), groupJid: jid, groupLabel: groups.get(jid)!.label, messageId: id, timestamp: new Date(Number(item.messageTimestamp ?? Math.floor(Date.now() / 1000)) * 1000).toISOString(), senderJid: item.key.participant ?? 'unknown', text });
    }
    saveSeen(seen);
    void flush();
  });
  sock.ev.on('connection.update', ({ connection, lastDisconnect }) => {
    if (connection === 'close') {
      const code = (lastDisconnect?.error as { output?: { statusCode?: number } } | undefined)?.output?.statusCode;
      if (code === DisconnectReason.loggedOut) fail('logged out; relink required');
      console.error('whatsapp-collector: connection closed; systemd will restart the collector');
      process.exit(1);
    }
  });
  setInterval(() => void flush(), 60_000).unref();
  process.on('SIGTERM', () => { void flush().finally(() => process.exit(0)); });
}

if (process.argv[2] === 'list-groups') void listGroups();
else if (process.argv[2] === 'collect') void collect();
else fail('usage: whatsapp_collector.ts <list-groups|collect>');
