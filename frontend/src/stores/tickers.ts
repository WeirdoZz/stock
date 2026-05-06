import { defineStore } from 'pinia';
import { reactive, ref } from 'vue';
import { api } from '../api/client';
import type { SyncState, TickerRowState } from '../types';

/**
 * Tickers store: maintains per-ticker row state for the sidebar, plus sync polling.
 * Polling timers are kept outside reactive state to avoid Pinia complaints.
 */
export const useTickersStore = defineStore('tickers', () => {
  const order = ref<string[]>([]);
  const rows = reactive<Record<string, TickerRowState>>({});
  // setInterval's return type differs between browser (number) and Node
  // (NodeJS.Timeout); we only care that we can pass it back to clearInterval.
  const pollTimers: Record<string, ReturnType<typeof setInterval> | null> = {};

  function ensureRow(ticker: string): TickerRowState {
    if (!rows[ticker]) {
      rows[ticker] = {
        ticker,
        lastPriceDate: null,
        daysStale: null,
        syncState: 'idle',
      };
      if (!order.value.includes(ticker)) order.value.push(ticker);
    }
    return rows[ticker];
  }

  function setSyncState(ticker: string, state: SyncState) {
    ensureRow(ticker).syncState = state;
  }

  async function refreshStatus(ticker: string) {
    const row = ensureRow(ticker);
    const [s, sync] = await Promise.all([
      api.tickerStatus(ticker),
      api.syncStatus(ticker),
    ]);
    if (s) {
      row.lastPriceDate = s.last_price_date;
      row.daysStale = s.days_stale;
    }
    if (sync) row.syncState = sync.status;
    if (row.syncState === 'running') startPoll(ticker);
  }

  function stopPoll(ticker: string) {
    const t = pollTimers[ticker];
    if (t) {
      clearInterval(t);
      pollTimers[ticker] = null;
    }
  }

  function startPoll(ticker: string) {
    stopPoll(ticker);
    pollTimers[ticker] = setInterval(async () => {
      const sync = await api.syncStatus(ticker);
      if (!sync) {
        stopPoll(ticker);
        return;
      }
      setSyncState(ticker, sync.status);
      if (sync.status !== 'running') {
        stopPoll(ticker);
        // Re-fetch the persistent ticker status (last_price_date) once sync settles.
        const s = await api.tickerStatus(ticker);
        if (s) {
          rows[ticker].lastPriceDate = s.last_price_date;
          rows[ticker].daysStale = s.days_stale;
        }
      }
    }, 2000);
  }

  async function triggerSync(ticker: string) {
    setSyncState(ticker, 'running');
    await api.triggerSync(ticker);
    startPoll(ticker);
  }

  async function loadAll() {
    const list = await api.listTickers();
    list.forEach(ensureRow);
    await Promise.all(list.map(refreshStatus));
  }

  /** Called when the SSE stream emits ticker_registered for a new ticker. */
  function registerNew(ticker: string) {
    ensureRow(ticker);
    setSyncState(ticker, 'running');
    startPoll(ticker);
  }

  return {
    order,
    rows,
    loadAll,
    refreshStatus,
    triggerSync,
    registerNew,
  };
});
