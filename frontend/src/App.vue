<script setup lang="ts">
import { onMounted } from 'vue';
import Sidebar from './components/Sidebar.vue';
import ChatPanel from './components/ChatPanel.vue';
import History from './components/History.vue';
import { useTickersStore } from './stores/tickers';
import { useSessionsStore } from './stores/sessions';
import { useChatStore } from './stores/chat';

const tickers = useTickersStore();
const sessions = useSessionsStore();
const chat = useChatStore();

onMounted(async () => {
  tickers.loadAll();
  await sessions.loadAll();
  // Resume the previously-active session if it still exists
  if (sessions.activeId && sessions.list.find(s => s.id === sessions.activeId)) {
    await chat.hydrate(sessions.activeId);
  } else {
    sessions.setActive(null);
    chat.clear();
  }
});
</script>

<template>
  <div class="flex h-full">
    <Sidebar />
    <ChatPanel class="flex-1 min-w-0" />
    <History />
  </div>
</template>
