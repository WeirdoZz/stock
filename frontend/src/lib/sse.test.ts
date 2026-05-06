import { describe, it, expect } from 'vitest';
import { parseSSEBuffer } from './sse';

describe('parseSSEBuffer', () => {
  it('parses a single complete event', () => {
    const buf = 'data: {"type":"chunk","content":"hello"}\n\n';
    const { events, remaining } = parseSSEBuffer(buf);
    expect(events).toEqual([{ type: 'chunk', content: 'hello' }]);
    expect(remaining).toBe('');
  });

  it('parses multiple events in one buffer', () => {
    const buf =
      'data: {"type":"status","content":"working"}\n\n' +
      'data: {"type":"chunk","content":"foo"}\n\n';
    const { events } = parseSSEBuffer(buf);
    expect(events).toHaveLength(2);
    expect(events[0]).toEqual({ type: 'status', content: 'working' });
    expect(events[1]).toEqual({ type: 'chunk', content: 'foo' });
  });

  it('keeps trailing partial event in remaining', () => {
    const buf = 'data: {"type":"chunk","content":"a"}\n\ndata: {"type":"chu';
    const { events, remaining } = parseSSEBuffer(buf);
    expect(events).toEqual([{ type: 'chunk', content: 'a' }]);
    expect(remaining).toBe('data: {"type":"chu');
  });

  it('normalises CRLF to LF (sse-starlette quirk)', () => {
    // sse-starlette uses \r\n\r\n boundaries
    const buf = 'data: {"type":"done","content":""}\r\n\r\n';
    const { events, remaining } = parseSSEBuffer(buf);
    expect(events).toEqual([{ type: 'done', content: '' }]);
    expect(remaining).toBe('');
  });

  it('skips malformed JSON without breaking subsequent events', () => {
    const buf =
      'data: {oops not json}\n\n' +
      'data: {"type":"chunk","content":"ok"}\n\n';
    const { events } = parseSSEBuffer(buf);
    expect(events).toEqual([{ type: 'chunk', content: 'ok' }]);
  });

  it('ignores non-data lines (event:, id:, comments)', () => {
    const buf =
      'event: ping\n' +
      'id: 1\n' +
      'data: {"type":"chunk","content":"x"}\n\n';
    const { events } = parseSSEBuffer(buf);
    expect(events).toEqual([{ type: 'chunk', content: 'x' }]);
  });

  it('returns empty result for empty buffer', () => {
    const { events, remaining } = parseSSEBuffer('');
    expect(events).toEqual([]);
    expect(remaining).toBe('');
  });

  it('handles streaming chunks split mid-event across calls', () => {
    // Simulate two TCP chunks splitting one event
    const part1 = 'data: {"type":"chunk","con';
    const part2 = 'tent":"hello"}\n\n';

    const r1 = parseSSEBuffer(part1);
    expect(r1.events).toEqual([]);
    expect(r1.remaining).toBe(part1);

    const r2 = parseSSEBuffer(r1.remaining + part2);
    expect(r2.events).toEqual([{ type: 'chunk', content: 'hello' }]);
    expect(r2.remaining).toBe('');
  });
});
