import type { TickerStatus, SyncStatus } from '../types';

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

  // Chat is handled separately via SSE composable, not here.
};
