import { describe, it, expect, beforeEach } from 'vitest';
import { setActivePinia, createPinia } from 'pinia';
import { useChatStore } from './chat';

describe('chat store', () => {
  beforeEach(() => {
    setActivePinia(createPinia());
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
});
