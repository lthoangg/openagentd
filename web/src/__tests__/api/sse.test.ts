import { describe, it, expect } from "bun:test";
import { readSSE } from "@/api/sse";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function fakeResponse(text: string): Response {
  const encoder = new TextEncoder();
  const bytes = encoder.encode(text);
  const stream = new ReadableStream({
    start(controller) {
      controller.enqueue(bytes);
      controller.close();
    },
  });
  return new Response(stream, { status: 200 });
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("readSSE", () => {
  it("dispatches a single event with event: and data: fields", async () => {
    const events: Array<{ type: string; data: unknown }> = [];
    let done = false;

    const text = "event: message\ndata: {\"text\":\"hello\",\"agent\":\"lead\"}\n\n";
    const res = fakeResponse(text);

    await new Promise<void>((resolve) => {
      readSSE(res, {
        onEvent: (type, data) => events.push({ type, data }),
        onDone: () => { done = true; resolve(); },
      });
    });

    expect(events).toHaveLength(1);
    expect(events[0].type).toBe("message");
    expect((events[0].data as Record<string, string>).text).toBe("hello");
    expect(done).toBe(true);
  });

  it("falls back to data.type when no event: line", async () => {
    const events: Array<{ type: string; data: unknown }> = [];

    const text = "data: {\"type\":\"session\",\"session_id\":\"abc\"}\n\n";
    const res = fakeResponse(text);

    await new Promise<void>((resolve) => {
      readSSE(res, {
        onEvent: (type, data) => events.push({ type, data }),
        onDone: () => resolve(),
      });
    });

    expect(events[0].type).toBe("session");
  });

  it("dispatches multiple events from one response", async () => {
    const events: Array<{ type: string }> = [];

    const text =
      "event: thinking\ndata: {\"text\":\"hmm\"}\n\n" +
      "event: message\ndata: {\"text\":\"ok\"}\n\n";
    const res = fakeResponse(text);

    await new Promise<void>((resolve) => {
      readSSE(res, {
        onEvent: (type) => events.push({ type }),
        onDone: () => resolve(),
      });
    });

    expect(events).toHaveLength(2);
    expect(events[0].type).toBe("thinking");
    expect(events[1].type).toBe("message");
  });

  it("calls onError when response has no body", () => {
    const errors: Error[] = [];
    const res = new Response(null, { status: 200 });
    Object.defineProperty(res, "body", { get: () => null });

    readSSE(res, {
      onEvent: () => {},
      onError: (e) => errors.push(e),
    });

    expect(errors).toHaveLength(1);
    expect(errors[0].message).toContain("No response body");
  });

  it("calls onError for invalid JSON in data line", async () => {
    const errors: Error[] = [];

    const text = "event: message\ndata: not-json\n\n";
    const res = fakeResponse(text);

    await new Promise<void>((resolve) => {
      readSSE(res, {
        onEvent: () => {},
        onError: (e) => errors.push(e),
        onDone: () => resolve(),
      });
    });

    expect(errors.length).toBeGreaterThan(0);
    expect(errors[0].message).toContain("SSE parse error");
  });

  it("ignores id: and retry: lines", async () => {
    const events: Array<{ type: string }> = [];

    const text = "id: 123\nretry: 1000\nevent: done\ndata: {}\n\n";
    const res = fakeResponse(text);

    await new Promise<void>((resolve) => {
      readSSE(res, {
        onEvent: (type) => events.push({ type }),
        onDone: () => resolve(),
      });
    });

    expect(events).toHaveLength(1);
    expect(events[0].type).toBe("done");
  });

  it("resets event type between events", async () => {
    const events: Array<{ type: string }> = [];

    const text =
      "event: thinking\ndata: {\"text\":\"t\"}\n\n" +
      "data: {\"type\":\"message\",\"text\":\"m\"}\n\n";
    const res = fakeResponse(text);

    await new Promise<void>((resolve) => {
      readSSE(res, {
        onEvent: (type) => events.push({ type }),
        onDone: () => resolve(),
      });
    });

    expect(events[0].type).toBe("thinking");
    expect(events[1].type).toBe("message");
  });
});
