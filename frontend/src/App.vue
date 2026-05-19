<script setup lang="ts">
import { onMounted } from 'vue';
import ChatPanel from './components/ChatPanel.vue';
import NavTabs from './components/NavTabs.vue';
import { useSessionsStore } from './stores/sessions';
import { useChatStore } from './stores/chat';

const sessions = useSessionsStore();
const chat = useChatStore();

onMounted(async () => {
  await sessions.loadAll();
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
    <!-- Center: tabbed router view (Overview / Plans) -->
    <main class="flex-1 min-w-0 flex flex-col">
      <NavTabs />
      <div class="flex-1 min-h-0 overflow-hidden">
        <RouterView />
      </div>
    </main>

    <!-- Right: chat panel (auxiliary) -->
    <ChatPanel class="w-[400px] min-w-[400px]" />
  </div>
</template>
