#!/usr/bin/env node
/** Native task gates: skip empty work before spending model tokens. */
import fs from 'node:fs';
import http from 'node:http';
const root = process.env.PA_WORKSPACE || '/workspace/agent';
const file = `${root}/work/state.json`;
const state = fs.existsSync(file) ? JSON.parse(fs.readFileSync(file, 'utf8')) : { records: {} };
const records = Object.values(state.records);
const mode = process.argv[2];
const emit = (data) => console.log(JSON.stringify({ wakeAgent: data.length > 0, data }));
if (['work', 'improve'].includes(mode)) {
  emit(records.filter((r) => ['active', 'blocked', 'proposed'].includes(r.status) &&
    (mode === 'improve' ? r.kind === 'improvement' : ['project', 'commitment', 'research'].includes(r.kind)) &&
    (!r.review_at || Date.parse(r.review_at) <= Date.now())).map((r) => ({ id: r.id, title: r.title, next_action: r.next_action })));
} else if (mode === 'meetings') {
  const now = new Date();
  const request = http.request({ hostname: '172.17.0.1', port: 8765, path: '/', method: 'POST',
    headers: { 'Content-Type': 'application/json' }, agent: new http.Agent(), timeout: 20000 }, (response) => {
    let text = '';
    response.on('data', (chunk) => { text += chunk; });
    response.on('end', () => {
      try {
        if (response.statusCode !== 200) throw new Error(`Calendar gate HTTP ${response.statusCode}`);
        const output = JSON.parse(text);
        if (!output.ok || !Array.isArray(output.events)) throw new Error('Calendar gate returned invalid data.');
        const followups = records.filter((r) => r.kind === 'meeting' && r.prepared_at && r.end_time &&
          !r.follow_up_drafted_at && !r.follow_up_requested_at && r.status !== 'cancelled' &&
          Date.parse(r.end_time) + 15 * 60000 <= now.getTime() &&
          Date.parse(r.end_time) >= now.getTime() - 24 * 3600000)
          .map((r) => ({ stage: 'follow_up', record_id: r.id, event_id: r.event_id, title: r.title, end_time: r.end_time }));
        const upcoming = output.events.filter((event) => event.status !== 'cancelled' && !event.attendees?.some((a) => a.self && a.responseStatus === 'declined') && event.start?.dateTime &&
          Date.parse(event.start.dateTime) >= now.getTime() &&
          !records.some((r) => r.kind === 'meeting' && r.event_id === event.id && r.calendar_id === event.calendar?.id &&
            r.start_time === event.start.dateTime && r.prepared_at));
        emit([...upcoming, ...followups]);
      } catch (error) { console.error(error.message); process.exitCode = 1; }
    });
  });
  request.on('timeout', () => request.destroy(new Error('Calendar gate timeout.')));
  request.on('error', (error) => { console.error(error.message); process.exitCode = 1; });
  request.end(JSON.stringify({ action: 'calendar', start: now.toISOString(), end: new Date(now.getTime() + 90 * 60000).toISOString(), limit: 50 }));
} else { console.error('Use work, improve, or meetings.'); process.exitCode = 1; }
