import { describe, it, expect, vi } from 'vitest';
import { applyEvent } from './useSSE';
import type { ChatMessage, SSEEvent } from '../types';

function emptyMsg(): ChatMessage {
  return { id: 'm1', role: 'assistant', text: '' };
}

function ctx() {
  return {
    setSessionId: vi.fn(),
    registerTicker: vi.fn(),
  };
}

describe('applyEvent', () => {
  it('session sets the session id via the provided callback', () => {
    const c = ctx();
    const msg = emptyMsg();
    applyEvent(
      { type: 'session', content: '', session_id: 'sess-123' } as SSEEvent,
      msg,
      c,
    );
    expect(c.setSessionId).toHaveBeenCalledWith('sess-123');
    expect(msg.text).toBe('');
  });

  it('status sets the transient status field', () => {
    const msg = emptyMsg();
    applyEvent({ type: 'status', content: 'collecting...' }, msg, ctx());
    expect(msg.status).toBe('collecting...');
  });

  it('chunk appends to text and clears any pending status', () => {
    const msg = emptyMsg();
    msg.status = 'collecting...';
    applyEvent({ type: 'chunk', content: 'hello' }, msg, ctx());
    applyEvent({ type: 'chunk', content: ' world' }, msg, ctx());
    expect(msg.text).toBe('hello world');
    expect(msg.status).toBeUndefined();
  });

  it('chart parses JSON content into msg.chart', () => {
    const msg = emptyMsg();
    const payload = { mode: 'single', tickers: ['AAPL'], prices: {}, sentiment: {} };
    applyEvent({ type: 'chart', content: JSON.stringify(payload) }, msg, ctx());
    expect(msg.chart).toEqual(payload);
  });

  it('chart with malformed JSON is silently ignored', () => {
    const msg = emptyMsg();
    applyEvent({ type: 'chart', content: 'not valid json' }, msg, ctx());
    expect(msg.chart).toBeUndefined();
  });

  it('ticker_registered fires the callback with the ticker', () => {
    const c = ctx();
    applyEvent({ type: 'ticker_registered', content: 'AMD' }, emptyMsg(), c);
    expect(c.registerTicker).toHaveBeenCalledWith('AMD');
  });

  it('done clears any pending status', () => {
    const msg = emptyMsg();
    msg.status = 'finishing';
    msg.text = 'final answer';
    applyEvent({ type: 'done', content: '' }, msg, ctx());
    expect(msg.status).toBeUndefined();
    expect(msg.text).toBe('final answer'); // text stays
  });

  it('error flips the error flag and replaces text', () => {
    const msg = emptyMsg();
    msg.text = 'partial...';
    msg.status = 'something';
    applyEvent({ type: 'error', content: 'invalid ticker' }, msg, ctx());
    expect(msg.error).toBe(true);
    expect(msg.text).toBe('invalid ticker');
    expect(msg.status).toBeUndefined();
  });
});
