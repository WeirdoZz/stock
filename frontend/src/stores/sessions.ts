import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import { api } from '../api/client';
import type { ChatSessionMeta } from '../types';

const ACTIVE_SESSION_KEY = 'chat_active_session_id';

/**
 * Sessions store: maintains the history rail (right side).
 *
 * Persists the active session id in localStorage so a refresh resumes the
 * same conversation; the actual messages are loaded from the backend on
 * demand by the chat store.
 */
export const useSessionsStore = defineStore('sessions', () => {
  const list = ref<ChatSessionMeta[]>([]);
  const activeId = ref<string | null>(localStorage.getItem(ACTIVE_SESSION_KEY));
  const showArchived = ref(false);

  const visible = computed(() =>
    showArchived.value ? list.value : list.value.filter(s => !s.archived),
  );

  async function loadAll() {
    list.value = await api.listSessions(showArchived.value);
  }

  function setActive(id: string | null) {
    activeId.value = id;
    if (id) localStorage.setItem(ACTIVE_SESSION_KEY, id);
    else localStorage.removeItem(ACTIVE_SESSION_KEY);
  }

  async function createNew(): Promise<string | null> {
    const sess = await api.createSession();
    if (!sess) return null;
    list.value = [sess, ...list.value];
    setActive(sess.id);
    return sess.id;
  }

  async function rename(id: string, title: string) {
    const sess = await api.patchSession(id, { title });
    if (sess) {
      const idx = list.value.findIndex(s => s.id === id);
      if (idx !== -1) list.value[idx] = sess;
    }
  }

  async function archive(id: string) {
    const sess = await api.patchSession(id, { archived: true });
    if (sess) {
      // Remove from active list when hiding archived
      if (showArchived.value) {
        const idx = list.value.findIndex(s => s.id === id);
        if (idx !== -1) list.value[idx] = sess;
      } else {
        list.value = list.value.filter(s => s.id !== id);
      }
      if (activeId.value === id) setActive(null);
    }
  }

  async function unarchive(id: string) {
    const sess = await api.patchSession(id, { archived: false });
    if (sess) {
      const idx = list.value.findIndex(s => s.id === id);
      if (idx !== -1) list.value[idx] = sess;
    }
  }

  async function remove(id: string) {
    const ok = await api.deleteSession(id);
    if (ok) {
      list.value = list.value.filter(s => s.id !== id);
      if (activeId.value === id) setActive(null);
    }
  }

  /** Bump local cache when a new session was just created via /api/chat. */
  function notePendingActive(id: string) {
    setActive(id);
    // Refresh the list so the new (auto-created) session appears immediately
    loadAll();
  }

  return {
    list, activeId, showArchived,
    visible,
    loadAll, setActive,
    createNew, rename, archive, unarchive, remove,
    notePendingActive,
  };
});
