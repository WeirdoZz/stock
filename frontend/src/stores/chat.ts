import { defineStore } from 'pinia';
import { ref } from 'vue';
import type { ChatMessage } from '../types';

let _id = 0;
function nextId() { return `m${Date.now()}_${++_id}`; }

/**
 * Chat store: server-side session id (ephemeral, server-managed) + message log.
 * Persistence to DB is PR 2's job — for now state lives in memory only.
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

  return {
    sessionId,
    messages,
    streaming,
    appendUser,
    startAssistant,
  };
});
