<script setup lang="ts">
import { computed } from 'vue';
import { useTickersStore } from '../stores/tickers';

const tickers = useTickersStore();

const rows = computed(() => tickers.order.map(t => tickers.rows[t]).filter(Boolean));

function fmtDate(iso: string | null): string {
  if (!iso) return '未同步';
  const d = new Date(iso);
  const diffDays = Math.floor((Date.now() - d.getTime()) / 86400000);
  if (diffDays === 0) return '今天';
  if (diffDays === 1) return '昨天';
  return `${diffDays}天前`;
}

function metaLabel(row: { syncState: string; lastPriceDate: string | null }): string {
  if (row.syncState === 'running') return '同步中';
  return fmtDate(row.lastPriceDate);
}

function isStale(row: { syncState: string; lastPriceDate: string | null; daysStale: number | null }): boolean {
  if (row.syncState === 'running') return false;
  if (!row.lastPriceDate) return true;
  return (row.daysStale ?? 0) >= 1;
}
</script>

<template>
  <aside class="w-[180px] min-w-[180px] bg-sidebar text-gray-200 flex flex-col py-4 px-2 gap-1.5 overflow-y-auto">
    <h3 class="text-[11px] uppercase tracking-wider text-gray-400 px-2 pt-1 pb-2">Tickers</h3>

    <div
      v-for="row in rows"
      :key="row.ticker"
      class="flex items-center gap-1 py-1 px-1 rounded-md hover:bg-sidebar-hover"
    >
      <button
        class="flex-1 min-w-0 text-left px-1.5 py-1 rounded text-[13px] font-medium hover:text-white"
        @click="$emit('pick', row.ticker)"
      >{{ row.ticker }}</button>

      <span
        class="text-[10px] whitespace-nowrap px-0.5"
        :class="isStale(row) ? 'text-red-400' : 'text-gray-400'"
      >{{ metaLabel(row) }}</span>

      <button
        class="border-0 bg-transparent cursor-pointer text-[13px] py-0.5 px-1 rounded leading-none flex-shrink-0 hover:text-white hover:bg-[#3a3b42]"
        :class="row.syncState === 'running' ? 'spinning text-accent' : 'text-gray-400'"
        :title="row.syncState === 'running' ? '同步中...' : '同步数据'"
        @click.stop="tickers.triggerSync(row.ticker)"
      >⟳</button>
    </div>
  </aside>
</template>
