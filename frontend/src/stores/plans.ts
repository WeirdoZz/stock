import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import { api } from '../api/client';
import type { Plan, PlanInput, PlanStatus } from '../types';

export const usePlansStore = defineStore('plans', () => {
  const list = ref<Plan[]>([]);
  const loading = ref(false);
  const filterStatus = ref<PlanStatus | 'all'>('all');
  const filterTicker = ref<string>('');

  const visible = computed(() => {
    let rows = list.value;
    if (filterStatus.value !== 'all') {
      rows = rows.filter(p => p.status === filterStatus.value);
    }
    if (filterTicker.value.trim()) {
      const t = filterTicker.value.trim().toUpperCase();
      rows = rows.filter(p => p.ticker.includes(t));
    }
    return rows;
  });

  const pendingCount = computed(() => list.value.filter(p => p.status === 'pending').length);

  async function loadAll() {
    loading.value = true;
    try {
      list.value = await api.listPlans();
    } finally {
      loading.value = false;
    }
  }

  async function create(input: PlanInput): Promise<Plan | null> {
    const created = await api.createPlan({ ...input, ticker: input.ticker.toUpperCase() });
    if (created) list.value = [created, ...list.value];
    return created;
  }

  async function update(id: number, patch: Partial<PlanInput>): Promise<Plan | null> {
    const updated = await api.updatePlan(id, patch);
    if (updated) {
      const idx = list.value.findIndex(p => p.id === id);
      if (idx !== -1) list.value[idx] = updated;
    }
    return updated;
  }

  async function remove(id: number): Promise<boolean> {
    const ok = await api.deletePlan(id);
    if (ok) {
      list.value = list.value.filter(p => p.id !== id);
      return true;
    }
    return false;
  }

  return {
    list, loading, visible, pendingCount,
    filterStatus, filterTicker,
    loadAll, create, update, remove,
  };
});
