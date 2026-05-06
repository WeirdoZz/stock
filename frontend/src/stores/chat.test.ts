import { describe, it, expect, beforeEach, vi } from 'vitest';
import { setActivePinia, createPinia } from 'pinia';
import { useChatStore } from './chat';
import { api } from '../api/client';
import type { PersistedMessage } from '../types';

vi.mock('../api/client', () => ({
  api: { getMessages: vi.fn() },
}));

describe('chat store', () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    vi.mocked(api.getMessages).mockReset();
  });

  it('starts empty', () => {
    const c = useChatStore();
    expect(c.messages).toEqual([]);
    expect(c.sessionId).toBeNull();
    expect(c.streaming).toBe(false);
  });

  it('appendUser pushes a user message', () => {
    const c = useChatStore();
    c.appendUser('hello');
    expect(c.messages).toHaveLength(1);
    expect(c.messages[0].role).toBe('user');
    expect(c.messages[0].text).toBe('hello');
  });

  it('startAssistant returns a fresh assistant message attached to the log', () => {
    const c = useChatStore();
    c.appendUser('q');
    const m = c.startAssistant();
    expect(m.role).toBe('assistant');
    expect(m.text).toBe('');
    // Compare by id rather than reference: Pinia's reactive proxy is not
    // identity-equal to the raw object returned from the action.
    expect(c.messages.at(-1)?.id).toBe(m.id);
  });

  it('messages get unique ids', () => {
    const c = useChatStore();
    c.appendUser('a');
    const m1 = c.startAssistant();
    c.appendUser('b');
    const m2 = c.startAssistant();
    const ids = new Set(c.messages.map(m => m.id));
    expect(ids.size).toBe(4);
    expect(m1.id).not.toBe(m2.id);
  });

  it('clear empties messages and sessionId', () => {
    const c = useChatStore();
    c.sessionId = 's';
    c.appendUser('hi');
    c.clear();
    expect(c.messages).toEqual([]);
    expect(c.sessionId).toBeNull();
  });

  it('hydrate loads persisted messages and parses chart_json', async () => {
    const persisted: PersistedMessage[] = [
      { id: 1, role: 'user', content: 'hi', chart_json: null, created_at: 't' },
      {
        id: 2, role: 'assistant', content: 'reply',
        chart_json: '{"mode":"single","tickers":["AAPL"],"prices":{},"sentiment":{}}',
        created_at: 't',
      },
    ];
    vi.mocked(api.getMessages).mockResolvedValue(persisted);

    const c = useChatStore();
    await c.hydrate('sess-1');

    expect(c.sessionId).toBe('sess-1');
    expect(c.messages).toHaveLength(2);
    expect(c.messages[0].text).toBe('hi');
    expect(c.messages[1].chart).toEqual({
      mode: 'single', tickers: ['AAPL'], prices: {}, sentiment: {},
    });
  });

  it('hydrate ignores malformed chart_json without crashing', async () => {
    vi.mocked(api.getMessages).mockResolvedValue([
      { id: 1, role: 'assistant', content: 'x', chart_json: 'not json', created_at: 't' },
    ]);
    const c = useChatStore();
    await c.hydrate('s');
    expect(c.messages[0].chart).toBeUndefined();
  });
});
