import { describe, it, expect, beforeEach, vi } from 'vitest';
import { setActivePinia, createPinia } from 'pinia';
import { useSessionsStore } from './sessions';
import { api } from '../api/client';
import type { ChatSessionMeta } from '../types';

vi.mock('../api/client', () => ({
  api: {
    listSessions: vi.fn(),
    createSession: vi.fn(),
    patchSession: vi.fn(),
    deleteSession: vi.fn(),
    getMessages: vi.fn(),
  },
}));

function makeSession(overrides: Partial<ChatSessionMeta> = {}): ChatSessionMeta {
  return {
    id: 's1',
    title: 'Test',
    archived: false,
    last_ticker: null,
    created_at: '2026-05-06T00:00:00',
    last_active_at: '2026-05-06T00:00:00',
    ...overrides,
  };
}

const localStorageMock = (() => {
  let store: Record<string, string> = {};
  return {
    getItem: (k: string) => store[k] ?? null,
    setItem: (k: string, v: string) => { store[k] = v; },
    removeItem: (k: string) => { delete store[k]; },
    clear: () => { store = {}; },
  };
})();
Object.defineProperty(globalThis, 'localStorage', { value: localStorageMock });

describe('sessions store', () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    localStorageMock.clear();
    vi.mocked(api.listSessions).mockReset();
    vi.mocked(api.createSession).mockReset();
    vi.mocked(api.patchSession).mockReset();
    vi.mocked(api.deleteSession).mockReset();
  });

  it('loadAll populates list', async () => {
    vi.mocked(api.listSessions).mockResolvedValue([
      makeSession({ id: 'a', title: 'A' }),
      makeSession({ id: 'b', title: 'B' }),
    ]);
    const s = useSessionsStore();
    await s.loadAll();
    expect(s.list).toHaveLength(2);
    expect(s.visible).toHaveLength(2);
  });

  it('visible filters archived when showArchived is false', async () => {
    vi.mocked(api.listSessions).mockResolvedValue([
      makeSession({ id: 'a', archived: false }),
      makeSession({ id: 'b', archived: true }),
    ]);
    const s = useSessionsStore();
    await s.loadAll();
    // Default: showArchived=false → only non-archived rows visible
    expect(s.visible.map(x => x.id)).toEqual(['a']);
    s.showArchived = true;
    expect(s.visible.map(x => x.id)).toEqual(['a', 'b']);
  });

  it('createNew prepends to list and sets active', async () => {
    vi.mocked(api.createSession).mockResolvedValue(makeSession({ id: 'new1' }));
    const s = useSessionsStore();
    s.list = [makeSession({ id: 'old' })];
    const id = await s.createNew();
    expect(id).toBe('new1');
    expect(s.list[0].id).toBe('new1');
    expect(s.activeId).toBe('new1');
    expect(localStorage.getItem('chat_active_session_id')).toBe('new1');
  });

  it('archive removes from list and clears activeId when active', async () => {
    vi.mocked(api.patchSession).mockResolvedValue(makeSession({ id: 'a', archived: true }));
    const s = useSessionsStore();
    s.list = [makeSession({ id: 'a' }), makeSession({ id: 'b' })];
    s.setActive('a');
    await s.archive('a');
    expect(s.list.map(x => x.id)).toEqual(['b']);
    expect(s.activeId).toBeNull();
  });

  it('archive keeps row in list when showArchived is true', async () => {
    vi.mocked(api.patchSession).mockResolvedValue(makeSession({ id: 'a', archived: true }));
    const s = useSessionsStore();
    s.showArchived = true;
    s.list = [makeSession({ id: 'a' }), makeSession({ id: 'b' })];
    await s.archive('a');
    expect(s.list).toHaveLength(2);
    expect(s.list.find(x => x.id === 'a')!.archived).toBe(true);
  });

  it('rename updates the matching list entry', async () => {
    vi.mocked(api.patchSession).mockResolvedValue(makeSession({ id: 'a', title: 'New title' }));
    const s = useSessionsStore();
    s.list = [makeSession({ id: 'a', title: 'Old' })];
    await s.rename('a', 'New title');
    expect(s.list[0].title).toBe('New title');
  });

  it('remove drops the session and clears active', async () => {
    vi.mocked(api.deleteSession).mockResolvedValue({ deleted: 'a' });
    const s = useSessionsStore();
    s.list = [makeSession({ id: 'a' }), makeSession({ id: 'b' })];
    s.setActive('a');
    await s.remove('a');
    expect(s.list.map(x => x.id)).toEqual(['b']);
    expect(s.activeId).toBeNull();
  });

  it('setActive(null) removes the localStorage key', () => {
    const s = useSessionsStore();
    s.setActive('xyz');
    expect(localStorage.getItem('chat_active_session_id')).toBe('xyz');
    s.setActive(null);
    expect(localStorage.getItem('chat_active_session_id')).toBeNull();
  });
});
