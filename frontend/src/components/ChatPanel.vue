<script setup lang="ts">
import { ref, watch, nextTick } from 'vue';
import { useChatStore } from '../stores/chat';
import MessageBubble from './MessageBubble.vue';
import InputBox from './InputBox.vue';

const chat = useChatStore();
const scroller = ref<HTMLDivElement | null>(null);

// Auto-scroll on new messages and on streaming chunks.
watch(
  () => [chat.messages.length, chat.messages[chat.messages.length - 1]?.text],
  async () => {
    await nextTick();
    if (scroller.value) scroller.value.scrollTop = scroller.value.scrollHeight;
  },
);
</script>

<template>
  <main class="flex flex-col min-w-0">
    <div ref="scroller" class="flex-1 overflow-y-auto py-6 px-4 flex flex-col gap-4">
      <div v-if="!chat.messages.length" class="text-center text-gray-400 m-auto">
        <h2 class="text-lg mb-2 text-gray-900">Stock Analysis Agent</h2>
        <p class="text-sm">Ask about any tracked ticker — e.g. "AAPL 趋势怎么样？"</p>
      </div>
      <MessageBubble
        v-for="m in chat.messages"
        :key="m.id"
        :message="m"
      />
    </div>
    <InputBox />
  </main>
</template>
