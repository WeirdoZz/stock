<script setup lang="ts">
import { ref, watch } from 'vue';
import type { Plan, PlanInput, PlanAction, PlanStatus } from '../types';

const props = defineProps<{ initial?: Plan | null }>();
const emit = defineEmits<{
  (e: 'submit', payload: PlanInput): void;
  (e: 'cancel'): void;
}>();

const form = ref<PlanInput>(blankForm());

function blankForm(): PlanInput {
  return {
    ticker: '',
    action: 'buy',
    target_price: null,
    quantity: null,
    target_date: null,
    status: 'pending',
    note: null,
  };
}

watch(
  () => props.initial,
  (v) => {
    if (v) {
      form.value = {
        ticker: v.ticker,
        action: v.action,
        target_price: v.target_price,
        quantity: v.quantity,
        target_date: v.target_date,
        status: v.status,
        note: v.note,
      };
    } else {
      form.value = blankForm();
    }
  },
  { immediate: true },
);

const ACTIONS: { value: PlanAction; label: string }[] = [
  { value: 'buy', label: '买入' },
  { value: 'sell', label: '卖出' },
  { value: 'hold', label: '持有' },
  { value: 'watch', label: '观察' },
];

const STATUSES: { value: PlanStatus; label: string }[] = [
  { value: 'pending', label: '待执行' },
  { value: 'completed', label: '已完成' },
  { value: 'cancelled', label: '已取消' },
];

function submit() {
  if (!form.value.ticker.trim() || !form.value.action) return;
  emit('submit', {
    ...form.value,
    ticker: form.value.ticker.trim().toUpperCase(),
    target_price: form.value.target_price === null || (form.value.target_price as unknown) === '' ? null : Number(form.value.target_price),
    quantity: form.value.quantity === null || (form.value.quantity as unknown) === '' ? null : Number(form.value.quantity),
    target_date: form.value.target_date || null,
    note: form.value.note?.trim() || null,
  });
}
</script>

<template>
  <form
    class="bg-white border border-gray-200 rounded-lg p-4 grid grid-cols-2 gap-3 text-sm"
    @submit.prevent="submit"
  >
    <div>
      <label class="block text-xs text-gray-500 mb-1">Ticker *</label>
      <input
        v-model="form.ticker"
        type="text"
        required
        placeholder="AAPL"
        class="w-full border border-gray-300 rounded px-2 py-1.5 font-mono uppercase outline-none focus:border-accent"
      />
    </div>

    <div>
      <label class="block text-xs text-gray-500 mb-1">操作 *</label>
      <select v-model="form.action" required
        class="w-full border border-gray-300 rounded px-2 py-1.5 outline-none focus:border-accent bg-white">
        <option v-for="a in ACTIONS" :key="a.value" :value="a.value">{{ a.label }}</option>
      </select>
    </div>

    <div>
      <label class="block text-xs text-gray-500 mb-1">目标价</label>
      <input
        v-model.number="form.target_price"
        type="number"
        step="0.01"
        placeholder="例如 180"
        class="w-full border border-gray-300 rounded px-2 py-1.5 outline-none focus:border-accent"
      />
    </div>

    <div>
      <label class="block text-xs text-gray-500 mb-1">股数</label>
      <input
        v-model.number="form.quantity"
        type="number"
        min="0"
        placeholder="例如 100"
        class="w-full border border-gray-300 rounded px-2 py-1.5 outline-none focus:border-accent"
      />
    </div>

    <div>
      <label class="block text-xs text-gray-500 mb-1">目标日期</label>
      <input
        v-model="form.target_date"
        type="date"
        class="w-full border border-gray-300 rounded px-2 py-1.5 outline-none focus:border-accent"
      />
    </div>

    <div>
      <label class="block text-xs text-gray-500 mb-1">状态</label>
      <select v-model="form.status"
        class="w-full border border-gray-300 rounded px-2 py-1.5 outline-none focus:border-accent bg-white">
        <option v-for="s in STATUSES" :key="s.value" :value="s.value">{{ s.label }}</option>
      </select>
    </div>

    <div class="col-span-2">
      <label class="block text-xs text-gray-500 mb-1">备注</label>
      <textarea
        v-model="form.note"
        rows="2"
        placeholder="例如：突破 200 阻力位再进场"
        class="w-full border border-gray-300 rounded px-2 py-1.5 outline-none focus:border-accent resize-none"
      ></textarea>
    </div>

    <div class="col-span-2 flex justify-end gap-2 pt-1">
      <button
        type="button"
        class="px-3 py-1.5 text-sm border border-gray-300 rounded hover:bg-gray-50"
        @click="emit('cancel')"
      >取消</button>
      <button
        type="submit"
        class="px-3 py-1.5 text-sm bg-accent text-white rounded hover:bg-accent-hover"
      >{{ initial ? '保存' : '添加' }}</button>
    </div>
  </form>
</template>
