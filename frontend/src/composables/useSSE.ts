import type { ChartPayload, ChatMessage, SSEEvent } from '../types';
import { useChatStore } from '../stores/chat';
import { useTickersStore } from '../stores/tickers';
import { useSessionsStore } from '../stores/sessions';
import { parseSSEBuffer } from '../lib/sse';

interface SendOptions {
  message: string;
}

/**
 * Apply a single SSE event to the active assistant message and to the
 * cross-cutting stores. Pure-ish: it mutates the inputs (the way Pinia/Vue
 * reactivity wants) but doesn't reach into anything else, so it's testable.
 */
export function applyEvent(
  event: SSEEvent,
  msg: ChatMessage,
  ctx: { setSessionId: (id: string) => void; registerTicker: (t: string) => void },
): void {
  switch (event.type) {
    case 'session':
      ctx.setSessionId(event.session_id);
      break;
    case 'status':
      msg.status = event.content;
      break;
    case 'chunk':
      msg.status = undefined;
      msg.text += event.content;
      break;
    case 'chart':
      try {
        msg.chart = JSON.parse(event.content) as ChartPayload;
      } catch {
        // ignore malformed chart payload
      }
      break;
    case 'ticker_registered':
      ctx.registerTicker(event.content);
      break;
    case 'done':
      msg.status = undefined;
      break;
    case 'error':
      msg.error = true;
      msg.text = event.content;
      msg.status = undefined;
      break;
  }
}

/**
 * Send a chat request and stream the response.
 *
 * Why not EventSource: SSE-over-POST is required for the request body, and
 * the browser EventSource API only supports GET. So we use fetch + a manual
 * ReadableStream parser (see lib/sse.ts).
 */
export function useSSE() {
  const chat = useChatStore();
  const tickers = useTickersStore();
  const sessionsStore = useSessionsStore();

  async function send({ message }: SendOptions) {
    if (chat.streaming) return;
    chat.streaming = true;

    chat.appendUser(message);
    const assistantMsg = chat.startAssistant();
    const previousSessionId = chat.sessionId;
    const ctx = {
      setSessionId: (id: string) => {
        chat.sessionId = id;
        // First message of a brand-new session → tell the history rail to refresh
        if (!previousSessionId) sessionsStore.notePendingActive(id);
      },
      registerTicker: (t: string) => tickers.registerNew(t),
    };

    try {
      const resp = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message, session_id: chat.sessionId }),
      });

      if (!resp.ok || !resp.body) {
        assistantMsg.error = true;
        assistantMsg.text = 'Server error: ' + resp.status;
        return;
      }

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      // eslint-disable-next-line no-constant-condition
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const { events, remaining } = parseSSEBuffer(buffer);
        buffer = remaining;
        for (const event of events) {
          applyEvent(event, assistantMsg, ctx);
        }
      }
    } catch (err) {
      assistantMsg.error = true;
      assistantMsg.text = 'Connection error: ' + (err as Error).message;
    } finally {
      chat.streaming = false;
    }
  }

  return { send };
}
