import { defineStore } from 'pinia';
import { ref } from 'vue';
import { api } from '../api/client';
import type { OverviewCard } from '../types';

export const useOverviewStore = defineStore('overview', () => {
  const cards = ref<OverviewCard[]>([]);
  const loading = ref(false);
  const lastFetched = ref<Date | null>(null);

  async function load() {
    loading.value = true;
    try {
      cards.value = await api.getOverview();
      lastFetched.value = new Date();
    } finally {
      loading.value = false;
    }
  }

  return { cards, loading, lastFetched, load };
});
