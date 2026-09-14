#!/usr/bin/env node
const fs = require('fs');
const path = require('path');

const query = process.argv.slice(2).join(' ').trim().toLowerCase();
const root = process.env.CONVERSATIONS_DIR || '/workspace/agent/conversations';
if (!query) { console.error('usage: search-conversations.js <query>'); process.exit(2); }

let files = [];
try { files = fs.readdirSync(root).filter((name) => name.endsWith('.md')).sort().reverse(); } catch {
  console.log('No conversation archive is available.'); process.exit(0);
}
const results = [];
for (const name of files) {
  const lines = fs.readFileSync(path.join(root, name), 'utf8').split(/\r?\n/);
  lines.forEach((line, index) => {
    if (line.toLowerCase().includes(query) && results.length < 20) {
      results.push(`${name}:${index + 1}: ${line.slice(0, 500)}`);
    }
  });
  if (results.length >= 20) break;
}
console.log(results.length ? results.join('\n') : 'No matching conversation excerpts found.');
