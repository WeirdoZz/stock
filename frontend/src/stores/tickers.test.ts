import { describe, it, expect, beforeEach, vi } from 'vitest';
import { setActivePinia, createPinia } from 'pinia';
import { useTickersStore } from './tickers';
import { api } from '../api/client';

vi.mock('../api/client', () => ({
  api: {
    listTickers: vi.fn(),
    tickerStatus: vi.fn(),
    syncStatus: vi.fn(),
    triggerSync: vi.fn(),
  },
}));

describe('tickers store', () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    vi.useFakeTimers();
    vi.mocked(api.listTickers).mockReset();
    vi.mocked(api.tickerStatus).mockReset();
    vi.mocked(api.syncStatus).mockReset();
    vi.mocked(api.triggerSync).mockReset();
  });

  it('loadAll populates rows from /api/tickers + /api/status', async () => {
    vi.mocked(api.listTickers).mockResolvedValue(['AAPL', 'NVDA']);
    vi.mocked(api.tickerStatus).mockImplementation(async (t) => ({
      ticker: t,
      news_count: 0, price_count: 0, correlation_count: 0, embedded_count: 0,
      last_price_date: '2026-05-01',
      last_news_date: null,
      days_stale: 5,
    }));
    vi.mocked(api.syncStatus).mockResolvedValue({ ticker: 'X', status: 'idle' });

    const store = useTickersStore();
    await store.loadAll();

    expect(store.order).toEqual(['AAPL', 'NVDA']);
    expect(store.rows.AAPL.lastPriceDate).toBe('2026-05-01');
    expect(store.rows.AAPL.daysStale).toBe(5);
    expect(store.rows.AAPL.syncState).toBe('idle');
  });

  it('registerNew appends to order, sets running, and starts polling', () => {
    const store = useTickersStore();
    vi.mocked(api.syncStatus).mockResolvedValue({ ticker: 'AMD', status: 'running' });

    store.registerNew('AMD');

    expect(store.order).toContain('AMD');
    expect(store.rows.AMD.syncState).toBe('running');
  });

  it('triggerSync sets running optimistically and calls the API', async () => {
    const store = useTickersStore();
    vi.mocked(api.triggerSync).mockResolvedValue({ status: 'queued', ticker: 'AAPL' });
    vi.mocked(api.syncStatus).mockResolvedValue({ ticker: 'AAPL', status: 'running' });

    await store.triggerSync('AAPL');

    expect(store.rows.AAPL.syncState).toBe('running');
    expect(api.triggerSync).toHaveBeenCalledWith('AAPL');
  });

  it('registerNew is idempotent (calling twice does not duplicate)', () => {
    const store = useTickersStore();
    store.registerNew('AMD');
    store.registerNew('AMD');
    const occurrences = store.order.filter(t => t === 'AMD').length;
    expect(occurrences).toBe(1);
  });
});
