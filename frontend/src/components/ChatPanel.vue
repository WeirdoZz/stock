<script setup lang="ts">
import { ref, watch, nextTick, onMounted, onBeforeUnmount } from 'vue';
import { useChatStore } from '../stores/chat';
import MessageBubble from './MessageBubble.vue';
import InputBox from './InputBox.vue';
import HistoryDropdown from './HistoryDropdown.vue';

const chat = useChatStore();
const scroller = ref<HTMLDivElement | null>(null);
const inputBox = ref<InstanceType<typeof InputBox> | null>(null);

watch(
  () => [chat.messages.length, chat.messages[chat.messages.length - 1]?.text],
  async () => {
    await nextTick();
    if (scroller.value) scroller.value.scrollTop = scroller.value.scrollHeight;
  },
);

// Allow other views (e.g., Overview cards) to seed the input via a custom event.
function onPrefill(e: Event) {
  const detail = (e as CustomEvent<string>).detail;
  inputBox.value?.insertTicker(detail.trim());
}

onMounted(() => document.addEventListener('chat:prefill', onPrefill));
onBeforeUnmount(() => document.removeEventListener('chat:prefill', onPrefill));
</script>

<template>
  <aside class="flex flex-col min-w-0 bg-white border-l border-gray-200">
    <HistoryDropdown />
    <div ref="scroller" class="flex-1 overflow-y-auto py-4 px-3 flex flex-col gap-3">
      <div v-if="!chat.messages.length" class="text-center text-gray-400 m-auto">
        <h2 class="text-sm mb-1 text-gray-700 font-semibold">Stock Analysis Agent</h2>
        <p class="text-xs">问任意 ticker — 例如「AAPL 趋势怎么样？」</p>
      </div>
      <MessageBubble
        v-for="m in chat.messages"
        :key="m.id"
        :message="m"
      />
    </div>
    <InputBox ref="inputBox" />
  </aside>
</template>
