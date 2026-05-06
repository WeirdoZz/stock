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
