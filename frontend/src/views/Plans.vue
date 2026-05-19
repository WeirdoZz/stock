<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { usePlansStore } from '../stores/plans';
import PlanForm from '../components/PlanForm.vue';
import type { Plan, PlanInput, PlanStatus } from '../types';

const plans = usePlansStore();
const showForm = ref(false);
const editing = ref<Plan | null>(null);

onMounted(() => { if (!plans.list.length) plans.loadAll(); });

function openCreate() {
  editing.value = null;
  showForm.value = true;
}

function openEdit(p: Plan) {
  editing.value = p;
  showForm.value = true;
}

async function onSubmit(payload: PlanInput) {
  if (editing.value) {
    await plans.update(editing.value.id, payload);
  } else {
    await plans.create(payload);
  }
  showForm.value = false;
  editing.value = null;
}

async function quickStatus(p: Plan, status: PlanStatus) {
  await plans.update(p.id, { status });
}

async function remove(p: Plan) {
  if (!confirm(`确认删除 ${p.ticker} 的这条计划？`)) return;
  await plans.remove(p.id);
}

const ACTION_LABELS: Record<string, string> = {
  buy: '买入', sell: '卖出', hold: '持有', watch: '观察',
};

const ACTION_COLORS: Record<string, string> = {
  buy: 'bg-green-100 text-green-700',
  sell: 'bg-red-100 text-red-700',
  hold: 'bg-blue-100 text-blue-700',
  watch: 'bg-amber-100 text-amber-700',
};

const STATUS_LABELS: Record<string, string> = {
  pending: '待执行', completed: '已完成', cancelled: '已取消',
};

function fmtDate(iso: string | null): string {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString();
}
</script>

<template>
  <div class="h-full flex flex-col p-6 overflow-y-auto">
    <header class="flex items-center justify-between mb-4">
      <div>
        <h1 class="text-xl font-semibold text-gray-900">持股计划</h1>
        <p class="text-xs text-gray-500 mt-0.5">
          记录买卖意图，避免遗忘 ·
          <span class="text-accent font-medium">{{ plans.pendingCount }}</span> 待执行
        </p>
      </div>
      <button
        class="px-3 py-1.5 text-sm rounded-md bg-accent text-white hover:bg-accent-hover"
        @click="openCreate"
      >+ 新建</button>
    </header>

    <!-- Filters -->
    <div class="flex items-center gap-3 mb-3 text-sm">
      <select
        v-model="plans.filterStatus"
        class="border border-gray-300 rounded px-2 py-1 bg-white outline-none focus:border-accent"
      >
        <option value="all">全部状态</option>
        <option value="pending">待执行</option>
        <option value="completed">已完成</option>
        <option value="cancelled">已取消</option>
      </select>
      <input
        v-model="plans.filterTicker"
        type="text"
        placeholder="按 ticker 过滤..."
        class="border border-gray-300 rounded px-2 py-1 outline-none focus:border-accent font-mono uppercase w-32"
      />
    </div>

    <!-- Form -->
    <div v-if="showForm" class="mb-4">
      <PlanForm
        :initial="editing"
        @submit="onSubmit"
        @cancel="showForm = false; editing = null"
      />
    </div>

    <!-- List -->
    <div v-if="plans.loading && !plans.list.length" class="text-gray-400 text-sm m-auto">
      加载中...
    </div>
    <div v-else-if="!plans.visible.length" class="text-gray-400 text-sm text-center mt-8">
      <p v-if="plans.list.length">没有匹配过滤条件的计划。</p>
      <p v-else>还没有计划，点「+ 新建」添加一条。</p>
    </div>
    <table v-else class="w-full text-sm bg-white border border-gray-200 rounded-lg overflow-hidden">
      <thead class="bg-gray-50 text-gray-500 text-xs uppercase">
        <tr>
          <th class="px-3 py-2 text-left">Ticker</th>
          <th class="px-3 py-2 text-left">操作</th>
          <th class="px-3 py-2 text-right">目标价</th>
          <th class="px-3 py-2 text-right">股数</th>
          <th class="px-3 py-2 text-left">目标日期</th>
          <th class="px-3 py-2 text-left">状态</th>
          <th class="px-3 py-2 text-left">备注</th>
          <th class="px-3 py-2"></th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="p in plans.visible"
          :key="p.id"
          class="border-t border-gray-100 hover:bg-gray-50"
        >
          <td class="px-3 py-2 font-mono font-medium">{{ p.ticker }}</td>
          <td class="px-3 py-2">
            <span :class="['inline-block px-2 py-0.5 rounded text-[11px] font-medium', ACTION_COLORS[p.action]]">
              {{ ACTION_LABELS[p.action] }}
            </span>
          </td>
          <td class="px-3 py-2 text-right tabular-nums">
            {{ p.target_price !== null ? `$${p.target_price.toFixed(2)}` : '—' }}
          </td>
          <td class="px-3 py-2 text-right tabular-nums">{{ p.quantity ?? '—' }}</td>
          <td class="px-3 py-2 text-gray-600">{{ fmtDate(p.target_date) }}</td>
          <td class="px-3 py-2">
            <select
              :value="p.status"
              class="text-xs border border-gray-200 rounded px-1.5 py-0.5 bg-white"
              @change="quickStatus(p, ($event.target as HTMLSelectElement).value as PlanStatus)"
            >
              <option v-for="(label, key) in STATUS_LABELS" :key="key" :value="key">
                {{ label }}
              </option>
            </select>
          </td>
          <td class="px-3 py-2 text-gray-600 max-w-[240px] truncate" :title="p.note ?? ''">
            {{ p.note ?? '—' }}
          </td>
          <td class="px-3 py-2 text-right whitespace-nowrap">
            <button class="text-gray-400 hover:text-accent text-xs px-1" title="编辑" @click="openEdit(p)">✎</button>
            <button class="text-gray-400 hover:text-red-500 text-xs px-1 ml-1" title="删除" @click="remove(p)">✕</button>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
