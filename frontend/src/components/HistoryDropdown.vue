<script setup lang="ts">
import { ref, computed } from 'vue';
import { useSessionsStore } from '../stores/sessions';
import { useChatStore } from '../stores/chat';

const sessions = useSessionsStore();
const chat = useChatStore();

const open = ref(false);

const activeTitle = computed(() => {
  if (!sessions.activeId) return '新会话';
  const s = sessions.list.find(x => x.id === sessions.activeId);
  return s?.title ?? '新会话';
});

async function newSession() {
  await sessions.createNew();
  chat.clear();
  open.value = false;
}

async function pick(id: string) {
  if (id !== sessions.activeId) {
    sessions.setActive(id);
    await chat.hydrate(id);
  }
  open.value = false;
}

async function archive(id: string, e: Event) {
  e.stopPropagation();
  await sessions.archive(id);
  if (sessions.activeId === null) chat.clear();
}

async function unarchive(id: string, e: Event) {
  e.stopPropagation();
  await sessions.unarchive(id);
}

async function remove(id: string, e: Event) {
  e.stopPropagation();
  if (!confirm('删除这个会话？')) return;
  await sessions.remove(id);
  if (sessions.activeId === null) chat.clear();
}

async function rename(id: string, currentTitle: string, e: Event) {
  e.stopPropagation();
  const next = prompt('重命名会话：', currentTitle);
  if (next && next.trim() && next !== currentTitle) {
    await sessions.rename(id, next.trim());
  }
}

function fmt(iso: string): string {
  const d = new Date(iso);
  const days = Math.floor((Date.now() - d.getTime()) / 86400000);
  if (days === 0) return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  if (days === 1) return '昨天';
  if (days < 7) return `${days}天前`;
  return d.toLocaleDateString();
}
</script>

<template>
  <div class="relative">
    <button
      class="w-full flex items-center justify-between px-3 py-2 text-sm bg-white border-b border-gray-200 hover:bg-gray-50"
      @click="open = !open"
    >
      <span class="truncate font-medium text-gray-700">{{ activeTitle }}</span>
      <span class="text-gray-400 text-xs flex items-center gap-2">
        <span>历史</span>
        <span :class="open ? 'rotate-180' : ''" class="transition-transform">▾</span>
      </span>
    </button>

    <div
      v-if="open"
      class="absolute top-full left-0 right-0 z-10 bg-white border border-gray-200 shadow-lg max-h-[500px] overflow-y-auto"
    >
      <div class="p-2 border-b border-gray-100 flex items-center justify-between">
        <button class="text-xs text-accent hover:text-accent-hover font-medium" @click="newSession">+ 新会话</button>
        <label class="text-[11px] text-gray-500 flex items-center gap-1.5 cursor-pointer">
          <input
            type="checkbox"
            v-model="sessions.showArchived"
            class="accent-accent"
            @change="sessions.loadAll()"
          />
          已归档
        </label>
      </div>

      <div v-if="!sessions.visible.length" class="text-center text-gray-400 text-xs py-6">
        暂无历史
      </div>

      <div
        v-for="s in sessions.visible"
        :key="s.id"
        class="group px-3 py-2 cursor-pointer text-sm border-b border-gray-50 last:border-0"
        :class="s.id === sessions.activeId ? 'bg-accent/5' : 'hover:bg-gray-50'"
        @click="pick(s.id)"
      >
        <div class="flex items-center justify-between gap-1">
          <span
            class="truncate flex-1"
            :class="s.archived ? 'italic text-gray-400' : 'text-gray-800'"
          >{{ s.title }}</span>
          <div class="flex gap-0.5 opacity-0 group-hover:opacity-100 flex-shrink-0">
            <button v-if="!s.archived" class="text-[11px] text-gray-400 hover:text-gray-700 px-1"
              title="重命名" @click="rename(s.id, s.title, $event)">✎</button>
            <button v-if="!s.archived" class="text-[11px] text-gray-400 hover:text-gray-700 px-1"
              title="归档" @click="archive(s.id, $event)">▤</button>
            <button v-else class="text-[11px] text-gray-400 hover:text-gray-700 px-1"
              title="取消归档" @click="unarchive(s.id, $event)">↺</button>
            <button class="text-[11px] text-gray-400 hover:text-red-500 px-1"
              title="删除" @click="remove(s.id, $event)">✕</button>
          </div>
        </div>
        <div class="flex items-center justify-between text-[10px] text-gray-400 mt-0.5">
          <span>{{ fmt(s.last_active_at) }}</span>
          <span v-if="s.last_ticker" class="font-mono">{{ s.last_ticker }}</span>
        </div>
      </div>
    </div>
  </div>
</template>
