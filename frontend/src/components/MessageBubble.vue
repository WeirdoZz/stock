<script setup lang="ts">
import { computed } from 'vue';
import { marked } from 'marked';
import type { ChatMessage } from '../types';
import Charts from './Charts.vue';

const props = defineProps<{ message: ChatMessage }>();

// Render assistant markdown; user/error bubbles render plain text via {{ }}.
const renderedHtml = computed(() => {
  if (props.message.role !== 'assistant' || !props.message.text) return '';
  return marked.parse(props.message.text);
});
</script>

<template>
  <div
    class="flex gap-2.5 max-w-[860px] w-full mx-auto"
    :class="message.role === 'user' ? 'flex-row-reverse' : ''"
  >
    <div class="max-w-[80%]">
      <!-- Status placeholder while pipeline runs -->
      <div
        v-if="message.status && !message.text"
        class="text-gray-400 italic py-1 text-sm"
      >{{ message.status }}</div>

      <!-- Error bubble -->
      <div
        v-else-if="message.error"
        class="px-4 py-3 rounded-xl text-sm bg-red-50 border border-red-300 text-red-700 whitespace-pre-wrap break-words"
      >{{ message.text }}</div>

      <!-- User bubble -->
      <div
        v-else-if="message.role === 'user'"
        class="px-4 py-3 rounded-xl text-sm bg-accent text-white rounded-br-[4px] whitespace-pre-wrap break-words leading-relaxed"
      >{{ message.text }}</div>

      <!-- Assistant bubble (markdown) -->
      <div
        v-else
        class="bubble-md px-4 py-3 rounded-xl text-sm bg-white border border-gray-200 rounded-bl-[4px] leading-relaxed"
        v-html="renderedHtml"
      />

      <!-- Status footer once we have text -->
      <div
        v-if="message.status && message.text"
        class="text-gray-400 italic text-xs mt-1"
      >{{ message.status }}</div>

      <!-- Inline charts -->
      <Charts v-if="message.chart" :chart="message.chart" class="mt-2" />
    </div>
  </div>
</template>
