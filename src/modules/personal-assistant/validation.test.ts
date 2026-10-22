import { describe, expect, it } from 'vitest';
import { experimentPayload, mailPayload } from './validation.js';

describe('assistant trust boundaries', () => {
  it('rejects injected email headers and multiple recipients', () => {
    expect(() => mailPayload({ to: 'a@example.com\r\nBcc: b@example.com', subject: 'Hello', text: 'Hi' })).toThrow();
    expect(() => mailPayload({ to: 'a@example.com,b@example.com', subject: 'Hello', text: 'Hi' })).toThrow();
    expect(() => mailPayload({ to: 'a@example.com', subject: 'Hello\r\nX: y', text: 'Hi' })).toThrow();
  });
  it('rejects an email that cannot fit its exact approval preview', () => {
    expect(() => mailPayload({ to: 'a@example.com', subject: 'Hello', text: '\n'.repeat(1000) + 'X' })).toThrow();
  });
  it('accepts an exact bounded message', () => {
    expect(mailPayload({ to: 'a@example.com', subject: 'Hello', text: 'Hi' }).text).toBe('Hi');
  });
  it('rejects host path traversal and arbitrary runtimes', () => {
    expect(() => experimentPayload({ id: '../config', command: ['node', 'test.js'], files: {} })).toThrow();
    expect(() => experimentPayload({ id: 'test', command: ['docker', 'run'], files: {} })).toThrow();
    expect(() =>
      experimentPayload({ id: 'test', command: ['node', 'test.js'], files: { '../secret': 'x' } }),
    ).toThrow();
  });
  it('accepts a bounded source snapshot without host paths', () => {
    expect(
      experimentPayload({ id: 'test', command: ['node', 'test.js'], files: { 'test.js': 'console.log(1)' } }).id,
    ).toBe('test');
  });
});
