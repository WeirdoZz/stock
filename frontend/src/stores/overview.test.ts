import { describe, it, expect, beforeEach, vi } from 'vitest';
import { setActivePinia, createPinia } from 'pinia';
import { useOverviewStore } from './overview';
import { api } from '../api/client';
import type { OverviewCard } from '../types';

vi.mock('../api/client', () => ({
  api: { getOverview: vi.fn() },
}));

function card(overrides: Partial<OverviewCard> = {}): OverviewCard {
  return {
    ticker: 'AAPL',
    current_price: 200,
    change_5d_pct: 2.5,
    last_price_date: '2026-05-06',
    news_count_7d: 12,
    avg_sentiment_7d: 0.4,
    pe_ttm: 28,
    week_52_high: 220,
    week_52_low: 150,
    analyst_target_mean: 230,
    pending_plans: 1,
    ...overrides,
  };
}

describe('overview store', () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    vi.mocked(api.getOverview).mockReset();
  });

  it('starts empty', () => {
    const s = useOverviewStore();
    expect(s.cards).toEqual([]);
    expect(s.loading).toBe(false);
    expect(s.lastFetched).toBeNull();
  });

  it('load populates cards and stamps lastFetched', async () => {
    vi.mocked(api.getOverview).mockResolvedValue([card({ ticker: 'AAPL' }), card({ ticker: 'NVDA' })]);
    const s = useOverviewStore();
    await s.load();
    expect(s.cards.map(c => c.ticker)).toEqual(['AAPL', 'NVDA']);
    expect(s.loading).toBe(false);
    expect(s.lastFetched).toBeInstanceOf(Date);
  });

  it('load sets loading true during fetch', async () => {
    let resolve: ((v: OverviewCard[]) => void) | null = null;
    vi.mocked(api.getOverview).mockImplementation(
      () => new Promise(r => { resolve = r; }),
    );
    const s = useOverviewStore();
    const p = s.load();
    expect(s.loading).toBe(true);
    resolve!([]);
    await p;
    expect(s.loading).toBe(false);
  });
});
