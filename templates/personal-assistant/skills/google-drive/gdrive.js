#!/usr/bin/env node
const http = require('http');

const action = process.argv[2];
if (!['search', 'tree', 'read', 'write', 'mkdir', 'calendar'].includes(action)) {
  console.error('usage: gdrive.js <search|tree|read|write|mkdir|calendar>');
  process.exit(2);
}

let input = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', (chunk) => { input += chunk; });
process.stdin.on('end', () => {
  let payload;
  try { payload = { action, ...JSON.parse(input) }; } catch {
    console.error('stdin must be a JSON object');
    process.exit(2);
  }
  const request = http.request({
    host: '172.17.0.1', port: 8765, path: '/', method: 'POST',
    headers: { 'content-type': 'application/json' }, agent: new http.Agent(),
  }, (response) => {
    let output = '';
    response.setEncoding('utf8');
    response.on('data', (chunk) => { output += chunk; });
    response.on('end', () => {
      process.stdout.write(output + '\n');
      process.exit(response.statusCode === 200 ? 0 : 1);
    });
  });
  request.on('error', (error) => { console.error(error.message); process.exit(1); });
  request.end(JSON.stringify(payload));
});
