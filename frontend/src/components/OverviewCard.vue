<script setup lang="ts">
import { computed } from 'vue';
import type { OverviewCard } from '../types';

const props = defineProps<{ card: OverviewCard }>();
defineEmits<{ (e: 'pick', ticker: string): void }>();

function fmtPct(n: number | null): string {
  if (n === null) return '—';
  const sign = n > 0 ? '+' : '';
  return `${sign}${n.toFixed(2)}%`;
}

function fmtPrice(n: number | null): string {
  if (n === null) return '—';
  return n >= 1000 ? n.toFixed(0) : n.toFixed(2);
}

function fmtNum(n: number | null, fixed = 1): string {
  if (n === null) return '—';
  return n.toFixed(fixed);
}

const changeClass = computed(() => {
  const v = props.card.change_5d_pct;
  if (v === null) return 'text-gray-400';
  return v > 0 ? 'text-green-600' : v < 0 ? 'text-red-600' : 'text-gray-500';
});

const sentimentClass = computed(() => {
  const v = props.card.avg_sentiment_7d;
  if (v === null) return 'text-gray-400';
  return v > 0.1 ? 'text-green-600' : v < -0.1 ? 'text-red-600' : 'text-gray-500';
});

const targetUpsidePct = computed(() => {
  const t = props.card.analyst_target_mean;
  const p = props.card.current_price;
  if (t === null || p === null || p === 0) return null;
  return ((t - p) / p) * 100;
});

const range52wPos = computed(() => {
  const lo = props.card.week_52_low;
  const hi = props.card.week_52_high;
  const p = props.card.current_price;
  if (lo === null || hi === null || p === null || hi === lo) return null;
  return Math.min(100, Math.max(0, ((p - lo) / (hi - lo)) * 100));
});
</script>

<template>
  <div
    class="bg-white border border-gray-200 rounded-lg p-4 hover:shadow-md transition-shadow cursor-pointer flex flex-col gap-2"
    @click="$emit('pick', card.ticker)"
  >
    <!-- header -->
    <div class="flex items-baseline justify-between gap-2">
      <h3 class="font-mono font-semibold text-base text-gray-900">{{ card.ticker }}</h3>
      <span
        v-if="card.pending_plans > 0"
        class="text-[10px] px-1.5 py-0.5 rounded bg-amber-100 text-amber-700"
      >{{ card.pending_plans }} 计划</span>
    </div>

    <!-- price + 5d change -->
    <div class="flex items-baseline gap-2">
      <span class="text-2xl font-semibold tabular-nums">${{ fmtPrice(card.current_price) }}</span>
      <span :class="['text-sm font-medium tabular-nums', changeClass]">
        {{ fmtPct(card.change_5d_pct) }}
        <span class="text-[10px] text-gray-400 font-normal ml-1">5D</span>
      </span>
    </div>

    <!-- 52-week range bar -->
    <div v-if="range52wPos !== null" class="text-[10px] text-gray-500">
      <div class="flex items-center justify-between mb-0.5 tabular-nums">
        <span>${{ fmtPrice(card.week_52_low) }}</span>
        <span class="text-gray-400">52W</span>
        <span>${{ fmtPrice(card.week_52_high) }}</span>
      </div>
      <div class="h-1 bg-gray-100 rounded relative">
        <div
          class="absolute h-2 -top-0.5 w-1 bg-accent rounded"
          :style="{ left: `calc(${range52wPos}% - 2px)` }"
        ></div>
      </div>
    </div>

    <!-- metrics row -->
    <div class="grid grid-cols-3 gap-2 text-xs pt-1">
      <div>
        <div class="text-gray-400 text-[10px]">P/E</div>
        <div class="tabular-nums">{{ fmtNum(card.pe_ttm) }}</div>
      </div>
      <div>
        <div class="text-gray-400 text-[10px]">目标价</div>
        <div class="tabular-nums">
          {{ card.analyst_target_mean !== null ? `$${fmtPrice(card.analyst_target_mean)}` : '—' }}
          <span v-if="targetUpsidePct !== null" class="text-[10px] text-gray-400 ml-0.5">
            ({{ fmtPct(targetUpsidePct) }})
          </span>
        </div>
      </div>
      <div>
        <div class="text-gray-400 text-[10px]">7D 情感</div>
        <div :class="['tabular-nums', sentimentClass]">
          {{ fmtNum(card.avg_sentiment_7d, 2) }}
          <span class="text-[10px] text-gray-400 ml-0.5">({{ card.news_count_7d }})</span>
        </div>
      </div>
    </div>
  </div>
</template>
