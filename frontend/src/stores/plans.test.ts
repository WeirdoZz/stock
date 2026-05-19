import { describe, it, expect, beforeEach, vi } from 'vitest';
import { setActivePinia, createPinia } from 'pinia';
import { usePlansStore } from './plans';
import { api } from '../api/client';
import type { Plan } from '../types';

vi.mock('../api/client', () => ({
  api: {
    listPlans: vi.fn(),
    createPlan: vi.fn(),
    updatePlan: vi.fn(),
    deletePlan: vi.fn(),
  },
}));

function makePlan(overrides: Partial<Plan> = {}): Plan {
  return {
    id: 1,
    ticker: 'AAPL',
    action: 'buy',
    target_price: 180,
    quantity: 10,
    target_date: null,
    status: 'pending',
    note: null,
    created_at: '2026-05-06T00:00:00',
    updated_at: '2026-05-06T00:00:00',
    ...overrides,
  };
}

describe('plans store', () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    vi.mocked(api.listPlans).mockReset();
    vi.mocked(api.createPlan).mockReset();
    vi.mocked(api.updatePlan).mockReset();
    vi.mocked(api.deletePlan).mockReset();
  });

  it('loadAll populates list', async () => {
    vi.mocked(api.listPlans).mockResolvedValue([
      makePlan({ id: 1, ticker: 'AAPL' }),
      makePlan({ id: 2, ticker: 'NVDA' }),
    ]);
    const s = usePlansStore();
    await s.loadAll();
    expect(s.list).toHaveLength(2);
    expect(s.loading).toBe(false);
  });

  it('create prepends to list and uppercases ticker', async () => {
    vi.mocked(api.createPlan).mockResolvedValue(makePlan({ id: 99, ticker: 'TSLA' }));
    const s = usePlansStore();
    s.list = [makePlan({ id: 1 })];
    await s.create({ ticker: 'tsla', action: 'buy' });
    expect(s.list[0].id).toBe(99);
    expect(api.createPlan).toHaveBeenCalledWith(expect.objectContaining({ ticker: 'TSLA' }));
  });

  it('update replaces the matching row', async () => {
    vi.mocked(api.updatePlan).mockResolvedValue(makePlan({ id: 1, status: 'completed' }));
    const s = usePlansStore();
    s.list = [makePlan({ id: 1, status: 'pending' })];
    await s.update(1, { status: 'completed' });
    expect(s.list[0].status).toBe('completed');
  });

  it('remove drops the row when API succeeds', async () => {
    vi.mocked(api.deletePlan).mockResolvedValue({ deleted: 1 });
    const s = usePlansStore();
    s.list = [makePlan({ id: 1 }), makePlan({ id: 2 })];
    await s.remove(1);
    expect(s.list.map(p => p.id)).toEqual([2]);
  });

  it('remove returns false when API fails', async () => {
    vi.mocked(api.deletePlan).mockResolvedValue(null);
    const s = usePlansStore();
    s.list = [makePlan({ id: 1 })];
    const ok = await s.remove(1);
    expect(ok).toBe(false);
    expect(s.list).toHaveLength(1);
  });

  it('visible filters by status and ticker', async () => {
    const s = usePlansStore();
    s.list = [
      makePlan({ id: 1, ticker: 'AAPL', status: 'pending' }),
      makePlan({ id: 2, ticker: 'AAPL', status: 'completed' }),
      makePlan({ id: 3, ticker: 'NVDA', status: 'pending' }),
    ];

    expect(s.visible).toHaveLength(3);                 // default: all
    s.filterStatus = 'pending';
    expect(s.visible.map(p => p.id)).toEqual([1, 3]);
    s.filterTicker = 'aapl';
    expect(s.visible.map(p => p.id)).toEqual([1]);
  });

  it('pendingCount counts pending only', () => {
    const s = usePlansStore();
    s.list = [
      makePlan({ id: 1, status: 'pending' }),
      makePlan({ id: 2, status: 'completed' }),
      makePlan({ id: 3, status: 'pending' }),
      makePlan({ id: 4, status: 'cancelled' }),
    ];
    expect(s.pendingCount).toBe(2);
  });
});
