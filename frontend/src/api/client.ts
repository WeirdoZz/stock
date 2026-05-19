import type {
  TickerStatus, SyncStatus, ChatSessionMeta, PersistedMessage,
  Plan, PlanInput, OverviewCard,
} from '../types';

async function jsonOrNull<T>(p: Promise<Response>): Promise<T | null> {
  try {
    const r = await p;
    if (!r.ok) return null;
    return (await r.json()) as T;
  } catch {
    return null;
  }
}

export const api = {
  listTickers(): Promise<string[]> {
    return jsonOrNull<string[]>(fetch('/api/tickers')).then(r => r ?? []);
  },

  tickerStatus(ticker: string): Promise<TickerStatus | null> {
    return jsonOrNull<TickerStatus>(fetch('/api/status/' + ticker));
  },

  syncStatus(ticker: string): Promise<SyncStatus | null> {
    return jsonOrNull<SyncStatus>(fetch('/api/sync/status/' + ticker));
  },

  triggerSync(ticker: string): Promise<{ status: string; ticker: string } | null> {
    return jsonOrNull(fetch('/api/sync/' + ticker, { method: 'POST' }));
  },

  // ── Sessions ──────────────────────────────────────────────────────────────
  listSessions(includeArchived = false): Promise<ChatSessionMeta[]> {
    const q = includeArchived ? '?include_archived=true' : '';
    return jsonOrNull<ChatSessionMeta[]>(fetch('/api/sessions' + q)).then(r => r ?? []);
  },

  createSession(title?: string): Promise<ChatSessionMeta | null> {
    return jsonOrNull<ChatSessionMeta>(fetch('/api/sessions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: title ?? null }),
    }));
  },

  patchSession(id: string, body: { title?: string; archived?: boolean }): Promise<ChatSessionMeta | null> {
    return jsonOrNull<ChatSessionMeta>(fetch('/api/sessions/' + id, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }));
  },

  deleteSession(id: string): Promise<{ deleted: string } | null> {
    return jsonOrNull(fetch('/api/sessions/' + id, { method: 'DELETE' }));
  },

  getMessages(id: string): Promise<PersistedMessage[]> {
    return jsonOrNull<PersistedMessage[]>(fetch(`/api/sessions/${id}/messages`)).then(r => r ?? []);
  },

  // ── Plans ─────────────────────────────────────────────────────────────────
  listPlans(filter: { ticker?: string; status?: string } = {}): Promise<Plan[]> {
    const params = new URLSearchParams();
    if (filter.ticker) params.set('ticker', filter.ticker);
    if (filter.status) params.set('status', filter.status);
    const qs = params.toString() ? `?${params}` : '';
    return jsonOrNull<Plan[]>(fetch('/api/plans' + qs)).then(r => r ?? []);
  },

  createPlan(body: PlanInput): Promise<Plan | null> {
    return jsonOrNull<Plan>(fetch('/api/plans', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }));
  },

  updatePlan(id: number, body: Partial<PlanInput>): Promise<Plan | null> {
    return jsonOrNull<Plan>(fetch('/api/plans/' + id, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }));
  },

  deletePlan(id: number): Promise<{ deleted: number } | null> {
    return jsonOrNull(fetch('/api/plans/' + id, { method: 'DELETE' }));
  },

  // ── Overview ──────────────────────────────────────────────────────────────
  getOverview(): Promise<OverviewCard[]> {
    return jsonOrNull<OverviewCard[]>(fetch('/api/overview')).then(r => r ?? []);
  },

  // Chat itself is streamed via SSE (see composables/useSSE.ts).
};
