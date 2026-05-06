<script setup lang="ts">
import { ref, nextTick } from 'vue';
import { useChatStore } from '../stores/chat';
import { useSSE } from '../composables/useSSE';

const chat = useChatStore();
const { send } = useSSE();

const text = ref('');
const inputEl = ref<HTMLTextAreaElement | null>(null);

async function autoresize() {
  await nextTick();
  if (!inputEl.value) return;
  inputEl.value.style.height = 'auto';
  inputEl.value.style.height = Math.min(inputEl.value.scrollHeight, 120) + 'px';
}

async function submit() {
  const t = text.value.trim();
  if (!t || chat.streaming) return;
  text.value = '';
  await autoresize();
  await send({ message: t });
  inputEl.value?.focus();
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    submit();
  }
}

defineExpose({
  insertTicker(t: string) {
    text.value = t + ' ' + text.value;
    inputEl.value?.focus();
  },
});
</script>

<template>
  <div class="border-t border-gray-200 bg-white py-3.5 px-4 flex gap-2.5 items-end">
    <textarea
      ref="inputEl"
      v-model="text"
      rows="1"
      placeholder="Ask about a stock..."
      class="flex-1 border border-gray-300 rounded-lg px-3.5 py-2.5 text-sm resize-none outline-none max-h-[120px] leading-normal font-[inherit] focus:border-accent"
      @input="autoresize"
      @keydown="onKeydown"
    ></textarea>
    <button
      class="bg-accent text-white border-0 rounded-lg py-2.5 px-4 text-sm cursor-pointer whitespace-nowrap hover:bg-accent-hover disabled:bg-gray-400 disabled:cursor-not-allowed"
      :disabled="chat.streaming || !text.trim()"
      @click="submit"
    >Send</button>
  </div>
</template>
