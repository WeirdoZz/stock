import type { SSEEvent } from '../types';

/**
 * Pure SSE buffer parser. Given the latest concatenated text from the stream,
 * returns the events that can be fully extracted plus the trailing remainder
 * that the caller should keep and re-feed on the next chunk.
 *
 * Handles two real-world quirks:
 *   - sse-starlette uses CRLF line terminators (`\r\n\r\n` between events);
 *     we normalise to LF before splitting on `\n\n`.
 *   - Malformed JSON in a single `data:` line is silently skipped, not thrown,
 *     so a transient parse hiccup doesn't break the whole stream.
 */
export function parseSSEBuffer(buffer: string): { events: SSEEvent[]; remaining: string } {
  const normalised = buffer.replace(/\r\n/g, '\n');
  const parts = normalised.split('\n\n');
  const remaining = parts.pop() ?? '';
  const events: SSEEvent[] = [];

  for (const part of parts) {
    for (const line of part.split('\n')) {
      if (!line.startsWith('data:')) continue;
      const jsonStr = line.slice(5).trim();
      try {
        events.push(JSON.parse(jsonStr) as SSEEvent);
      } catch {
        // skip malformed line, keep going
      }
    }
  }
  return { events, remaining };
}
