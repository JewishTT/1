/* eslint-disable @typescript-eslint/no-explicit-any */

/** Pipeline reactivity channel for the webapp (SSE).

The control plane exposes ``GET /api/v1/stream`` (see ``api/sse.py``): a
bounded backlog replay followed by live events. Browsers subscribe with one
``EventSource``; jsdom test environments have no ``EventSource`` so the hook
degrades to a no-op (components still render, just without live updates).
*/

import { useEffect, useRef } from "react";

export interface StreamEvent {
  event: string;
  data: unknown;
}

export const STREAM_URL = "/api/v1/stream";

/** Event types the UI reacts to (mirrors the pipeline publish vocabulary). */
const SUBSCRIBED_EVENTS = ["entity.updated", "science.invariant", "pipeline.advance"] as const;

/**
 * Parses raw SSE text into the first described event. SSE blocks carry
 * ``event: <type>`` plus ``data: <json>`` lines; comment/heartbeat lines are
 * skipped. Returns null when the chunk carries no event.
 */
export function parseStreamChunk(text: string): StreamEvent | null {
  for (const raw of text.split(/\r?\n\r?\n/)) {
    const block = raw.trim();
    if (!block || block.startsWith(":")) continue;
    let event = "";
    let data = "";
    for (const line of block.split(/\r?\n/)) {
      if (line.startsWith("event: ")) {
        event = line.slice("event: ".length).trim();
      } else if (line.startsWith("data: ")) {
        data += line.slice("data: ".length);
      }
    }
    if (!event) continue;
    return { event, data: data === "" ? null : JSON.parse(data) };
  }
  return null;
}

/**
 * Opens one SSE channel and forwards subscribed events to `onEvent`, with a
 * 2s reconnect backoff on drops. No-op when the runtime lacks EventSource.
 */
export function usePipelineStream(onEvent: (event: StreamEvent) => void): void {
  const handler = useRef(onEvent);
  handler.current = onEvent;

  useEffect(() => {
    if (typeof EventSource === "undefined") return;
    let disposed = false;
    let retryTimer: number | undefined;

    const deliver = (type: string, data: string) => {
      const parsed = parseStreamChunk(`event: ${type}\ndata: ${data}\n\n`);
      if (parsed) handler.current(parsed);
    };

    const open = () => {
      const source = new EventSource(STREAM_URL);
      source.onopen = () => {
        if (disposed) source.close();
      };
      source.onerror = () => {
        source.close();
        if (!disposed) retryTimer = window.setTimeout(open, 2000);
      };
      // Server sends named events (event: <type>); an EventSource dispatches
      // each to its own listener, so register the vocabulary we react to.
      for (const name of SUBSCRIBED_EVENTS) {
        source.addEventListener(name, (evt: MessageEvent) => deliver(name, evt.data as string));
      }
      // Default-typed messages (no event: line) land on onmessage.
      source.onmessage = (evt: MessageEvent) => deliver("message", evt.data as string);
    };
    open();

    return () => {
      disposed = true;
      if (retryTimer !== undefined) window.clearTimeout(retryTimer);
    };
  }, []);
}