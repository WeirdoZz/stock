import { defineStore } from 'pinia';
import { ref } from 'vue';
import type { ChatMessage, ChartPayload, PersistedMessage } from '../types';
import { api } from '../api/client';

let _id = 0;
function nextId() { return `m${Date.now()}_${++_id}`; }

/**
 * Chat store: the message log of the currently-active session plus the
 * server-issued session id. Persistence to DB happens server-side; this
 * store is purely the in-memory rendering buffer.
 */
export const useChatStore = defineStore('chat', () => {
  const sessionId = ref<string | null>(null);
  const messages = ref<ChatMessage[]>([]);
  const streaming = ref(false);

  function appendUser(text: string) {
    messages.value.push({ id: nextId(), role: 'user', text });
  }

  function startAssistant(): ChatMessage {
    const m: ChatMessage = { id: nextId(), role: 'assistant', text: '' };
    messages.value.push(m);
    return m;
  }

  function clear() {
    messages.value = [];
    sessionId.value = null;
  }

  /** Load a session's persisted messages into the in-memory log. */
  async function hydrate(sid: string) {
    const persisted = await api.getMessages(sid);
    sessionId.value = sid;
    messages.value = persisted.map((m: PersistedMessage) => {
      let chart: ChartPayload | undefined;
      if (m.chart_json) {
        try { chart = JSON.parse(m.chart_json) as ChartPayload; } catch { /* ignore */ }
      }
      return {
        id: `db${m.id}`,
        role: m.role,
        text: m.content,
        chart,
      };
    });
  }

  return {
    sessionId, messages, streaming,
    appendUser, startAssistant, clear, hydrate,
  };
});
