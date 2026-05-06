<script setup lang="ts">
import { useSessionsStore } from '../stores/sessions';
import { useChatStore } from '../stores/chat';

const sessions = useSessionsStore();
const chat = useChatStore();

async function newSession() {
  await sessions.createNew();
  chat.clear();
}

async function pick(id: string) {
  if (id === sessions.activeId) return;
  sessions.setActive(id);
  await chat.hydrate(id);
}

async function archive(id: string, e: Event) {
  e.stopPropagation();
  await sessions.archive(id);
  if (sessions.activeId === null) chat.clear();
}

async function remove(id: string, e: Event) {
  e.stopPropagation();
  if (!confirm('删除这个会话？此操作无法恢复。')) return;
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
  <aside class="w-[260px] min-w-[260px] bg-gray-50 border-l border-gray-200 flex flex-col">
    <div class="p-3 border-b border-gray-200 flex items-center justify-between">
      <h3 class="text-xs uppercase tracking-wider text-gray-500 font-semibold">History</h3>
      <button
        class="text-[11px] text-accent hover:text-accent-hover font-medium"
        @click="newSession"
      >+ 新会话</button>
    </div>

    <div class="px-3 py-2 border-b border-gray-200 flex items-center gap-2">
      <label class="text-[11px] text-gray-500 flex items-center gap-1.5 cursor-pointer">
        <input
          type="checkbox"
          v-model="sessions.showArchived"
          class="accent-accent"
          @change="sessions.loadAll()"
        />
        显示已归档
      </label>
    </div>

    <div class="flex-1 overflow-y-auto px-2 py-2 flex flex-col gap-1">
      <div v-if="!sessions.visible.length" class="text-center text-gray-400 text-xs mt-4">
        暂无历史会话
      </div>

      <div
        v-for="s in sessions.visible"
        :key="s.id"
        class="group rounded-md px-2 py-2 cursor-pointer text-sm flex flex-col gap-1"
        :class="s.id === sessions.activeId
          ? 'bg-accent/10 border border-accent/30'
          : 'hover:bg-gray-100 border border-transparent'"
        @click="pick(s.id)"
      >
        <div class="flex items-center justify-between gap-1">
          <span
            class="truncate font-medium text-gray-800 flex-1"
            :class="s.archived ? 'italic text-gray-500' : ''"
          >{{ s.title }}</span>
          <div class="flex gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0">
            <button
              v-if="!s.archived"
              class="text-[11px] text-gray-400 hover:text-gray-700 px-1"
              title="重命名"
              @click="rename(s.id, s.title, $event)"
            >✎</button>
            <button
              v-if="!s.archived"
              class="text-[11px] text-gray-400 hover:text-gray-700 px-1"
              title="归档"
              @click="archive(s.id, $event)"
            >▤</button>
            <button
              v-else
              class="text-[11px] text-gray-400 hover:text-gray-700 px-1"
              title="取消归档"
              @click.stop="sessions.unarchive(s.id)"
            >↺</button>
            <button
              class="text-[11px] text-gray-400 hover:text-red-500 px-1"
              title="删除"
              @click="remove(s.id, $event)"
            >✕</button>
          </div>
        </div>
        <div class="flex items-center justify-between text-[10px] text-gray-400">
          <span>{{ fmt(s.last_active_at) }}</span>
          <span v-if="s.last_ticker" class="font-mono">{{ s.last_ticker }}</span>
        </div>
      </div>
    </div>
  </aside>
</template>
