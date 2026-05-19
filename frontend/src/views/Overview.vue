<script setup lang="ts">
import { onMounted, computed } from 'vue';
import { useOverviewStore } from '../stores/overview';
import OverviewCard from '../components/OverviewCard.vue';

const overview = useOverviewStore();

onMounted(() => { if (!overview.cards.length) overview.load(); });

function pick(ticker: string) {
  // TODO: deep-link to filter Plans by this ticker, or open a chat about it.
  // For now, just bump it into the chat input via a custom event on the body.
  document.dispatchEvent(new CustomEvent('chat:prefill', { detail: ticker + ' ' }));
}

const fetchedLabel = computed(() => {
  if (!overview.lastFetched) return '';
  return overview.lastFetched.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
});
</script>

<template>
  <div class="h-full flex flex-col p-6 overflow-y-auto">
    <header class="flex items-center justify-between mb-4">
      <div>
        <h1 class="text-xl font-semibold text-gray-900">总览</h1>
        <p class="text-xs text-gray-500 mt-0.5">所有监控股票的近期数据汇总</p>
      </div>
      <button
        class="px-3 py-1.5 text-sm rounded-md bg-white border border-gray-300 hover:border-accent hover:text-accent disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-1.5"
        :disabled="overview.loading"
        @click="overview.load()"
      >
        <span :class="overview.loading ? 'spinning inline-block' : ''">⟳</span>
        刷新
        <span v-if="fetchedLabel" class="text-[10px] text-gray-400 ml-1">{{ fetchedLabel }}</span>
      </button>
    </header>

    <div v-if="overview.loading && !overview.cards.length" class="text-gray-400 text-sm m-auto">
      正在加载总览数据...
    </div>

    <div v-else-if="!overview.cards.length" class="text-gray-400 text-sm m-auto text-center">
      <p>还没有任何监控股票。</p>
      <p class="text-xs mt-1">在右侧聊天框问任意 ticker 即可注册。</p>
    </div>

    <div
      v-else
      class="grid gap-3"
      style="grid-template-columns: repeat(auto-fill, minmax(280px, 1fr))"
    >
      <OverviewCard
        v-for="c in overview.cards"
        :key="c.ticker"
        :card="c"
        @pick="pick"
      />
    </div>
  </div>
</template>
