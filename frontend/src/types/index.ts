export interface TickerStatus {
  ticker: string;
  news_count: number;
  price_count: number;
  correlation_count: number;
  embedded_count: number;
  last_price_date: string | null;
  last_news_date: string | null;
  days_stale: number | null;
}

export type SyncState = 'idle' | 'running' | 'done' | 'error';

export interface SyncStatus {
  ticker: string;
  status: SyncState;
  started_at?: string | null;
  finished_at?: string | null;
  error?: string | null;
}

// Per-ticker UI row state
export interface TickerRowState {
  ticker: string;
  lastPriceDate: string | null;
  daysStale: number | null;
  syncState: SyncState;
}

// SSE event types
export type SSEEvent =
  | { type: 'session'; content: string; session_id: string }
  | { type: 'status'; content: string }
  | { type: 'chunk'; content: string }
  | { type: 'chart'; content: string }
  | { type: 'ticker_registered'; content: string }
  | { type: 'done'; content: string }
  | { type: 'error'; content: string };

export interface PricePoint { date: string; close: number }
export interface SentimentPoint { date: string; avg_score: number; count?: number }

export interface ChartPayload {
  mode: 'single' | 'comparison';
  tickers: string[];
  prices: Record<string, PricePoint[]>;
  sentiment: Record<string, SentimentPoint[]>;
}

export type MessageRole = 'user' | 'assistant';

export interface ChatMessage {
  id: string;
  role: MessageRole;
  text: string;          // raw markdown (assistant) or plain text (user)
  status?: string;       // transient pipeline status while streaming
  error?: boolean;
  chart?: ChartPayload;  // optional chart attached to an assistant message
}

// Session history (PR 2)
export interface ChatSessionMeta {
  id: string;
  title: string;
  archived: boolean;
  last_ticker: string | null;
  created_at: string;
  last_active_at: string;
}

export interface PersistedMessage {
  id: number;
  role: MessageRole;
  content: string;
  chart_json: string | null;
  created_at: string;
}

// Plans (PR 3)
export type PlanAction = 'buy' | 'sell' | 'hold' | 'watch';
export type PlanStatus = 'pending' | 'completed' | 'cancelled';

export interface Plan {
  id: number;
  ticker: string;
  action: PlanAction;
  target_price: number | null;
  quantity: number | null;
  target_date: string | null;
  status: PlanStatus;
  note: string | null;
  created_at: string;
  updated_at: string;
}

export interface PlanInput {
  ticker: string;
  action: PlanAction;
  target_price?: number | null;
  quantity?: number | null;
  target_date?: string | null;
  status?: PlanStatus;
  note?: string | null;
}

// Overview (PR 3)
export interface OverviewCard {
  ticker: string;
  current_price: number | null;
  change_5d_pct: number | null;
  last_price_date: string | null;
  news_count_7d: number;
  avg_sentiment_7d: number | null;
  pe_ttm: number | null;
  week_52_high: number | null;
  week_52_low: number | null;
  analyst_target_mean: number | null;
  pending_plans: number;
}
