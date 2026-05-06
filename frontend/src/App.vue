<script setup lang="ts">
import { onMounted } from 'vue';
import Sidebar from './components/Sidebar.vue';
import ChatPanel from './components/ChatPanel.vue';
import { useTickersStore } from './stores/tickers';

const tickers = useTickersStore();
onMounted(() => { tickers.loadAll(); });
</script>

<template>
  <div class="flex h-full">
    <Sidebar />
    <ChatPanel class="flex-1 min-w-0" />
  </div>
</template>
