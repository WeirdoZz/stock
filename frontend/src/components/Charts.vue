<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref, watch } from 'vue';
import { Chart, registerables } from 'chart.js';
import type { ChartPayload } from '../types';

Chart.register(...registerables);

const props = defineProps<{ chart: ChartPayload }>();

const priceCanvas = ref<HTMLCanvasElement | null>(null);
const sentimentCanvas = ref<HTMLCanvasElement | null>(null);

const PALETTE = ['#10a37f', '#3b82f6', '#f59e0b', '#ef4444'];
let priceChart: Chart | null = null;
let sentimentChart: Chart | null = null;

function destroy() {
  priceChart?.destroy();
  sentimentChart?.destroy();
  priceChart = sentimentChart = null;
}

function drawSingle(payload: ChartPayload) {
  const ticker = payload.tickers[0];
  const prices = payload.prices[ticker] || [];
  const sentiment = payload.sentiment[ticker] || [];

  if (priceCanvas.value && prices.length) {
    priceChart = new Chart(priceCanvas.value, {
      type: 'line',
      data: {
        labels: prices.map(p => p.date),
        datasets: [{
          label: `${ticker} Close`,
          data: prices.map(p => p.close),
          borderColor: PALETTE[0],
          backgroundColor: 'rgba(16,163,127,0.08)',
          fill: true, tension: 0.3, pointRadius: 3,
        }],
      },
      options: {
        responsive: true,
        plugins: {
          legend: { display: false },
          title: { display: true, text: `${ticker} — 14-Day Price`, font: { size: 12 } },
        },
        scales: { x: { ticks: { maxRotation: 45, font: { size: 11 } } } },
      },
    });
  }

  if (sentimentCanvas.value && sentiment.length) {
    sentimentChart = new Chart(sentimentCanvas.value, {
      type: 'bar',
      data: {
        labels: sentiment.map(s => s.date),
        datasets: [{
          label: 'Avg Sentiment',
          data: sentiment.map(s => s.avg_score),
          backgroundColor: sentiment.map(s =>
            s.avg_score >= 0 ? 'rgba(16,163,127,0.7)' : 'rgba(239,68,68,0.7)'),
        }],
      },
      options: {
        responsive: true,
        plugins: {
          legend: { display: false },
          title: { display: true, text: `${ticker} — 7-Day News Sentiment`, font: { size: 12 } },
        },
        scales: {
          y: { min: -1, max: 1, ticks: { callback: v => Number(v).toFixed(1), font: { size: 11 } } },
          x: { ticks: { maxRotation: 45, font: { size: 11 } } },
        },
      },
    });
  }
}

function drawComparison(payload: ChartPayload) {
  const tickers = payload.tickers;

  const allDates = [...new Set(
    tickers.flatMap(t => (payload.prices[t] || []).map(p => p.date)),
  )].sort();

  if (priceCanvas.value && allDates.length) {
    const datasets = tickers.map((t, i) => {
      const map: Record<string, number> = {};
      (payload.prices[t] || []).forEach(p => { map[p.date] = p.close; });
      const vals = allDates.map(d => (d in map ? map[d] : null));
      const base = vals.find(v => v !== null) ?? 0;
      const norm = vals.map(v => (v !== null && base !== 0
        ? Number(((v - base) / base * 100).toFixed(2))
        : null));
      return {
        label: t,
        data: norm,
        borderColor: PALETTE[i % PALETTE.length],
        backgroundColor: 'transparent',
        tension: 0.3, pointRadius: 3, spanGaps: true,
      };
    });
    priceChart = new Chart(priceCanvas.value, {
      type: 'line',
      data: { labels: allDates, datasets },
      options: {
        responsive: true,
        plugins: {
          title: { display: true, text: `${tickers.join(' vs ')} — 14-Day % Change`, font: { size: 12 } },
        },
        scales: {
          y: { ticks: { callback: v => `${v}%`, font: { size: 11 } } },
          x: { ticks: { maxRotation: 45, font: { size: 11 } } },
        },
      },
    });
  }

  const sentDates = [...new Set(
    tickers.flatMap(t => (payload.sentiment[t] || []).map(s => s.date)),
  )].sort();

  if (sentimentCanvas.value && sentDates.length) {
    const datasets = tickers.map((t, i) => {
      const map: Record<string, number> = {};
      (payload.sentiment[t] || []).forEach(s => { map[s.date] = s.avg_score; });
      const color = PALETTE[i % PALETTE.length];
      return {
        label: t,
        data: sentDates.map(d => (d in map ? map[d] : null)),
        backgroundColor: color + 'b3', // ~70% alpha
        borderColor: color,
        borderWidth: 1,
      };
    });
    sentimentChart = new Chart(sentimentCanvas.value, {
      type: 'bar',
      data: { labels: sentDates, datasets },
      options: {
        responsive: true,
        plugins: {
          title: { display: true, text: `${tickers.join(' vs ')} — 7-Day Sentiment`, font: { size: 12 } },
        },
        scales: {
          y: { min: -1, max: 1, ticks: { callback: v => Number(v).toFixed(1), font: { size: 11 } } },
          x: { ticks: { maxRotation: 45, font: { size: 11 } } },
        },
      },
    });
  }
}

function render(payload: ChartPayload) {
  destroy();
  if (payload.mode === 'single') drawSingle(payload);
  else drawComparison(payload);
}

onMounted(() => render(props.chart));
watch(() => props.chart, render);
onBeforeUnmount(destroy);
</script>

<template>
  <div class="flex flex-col gap-3">
    <div class="bg-white border border-gray-200 rounded-[10px] p-3 px-4">
      <canvas ref="priceCanvas" class="!max-h-[200px]"></canvas>
    </div>
    <div class="bg-white border border-gray-200 rounded-[10px] p-3 px-4">
      <canvas ref="sentimentCanvas" class="!max-h-[200px]"></canvas>
    </div>
  </div>
</template>
