import { describe, it, expect } from "bun:test";
import { sumUsageFromMessages, parseTeamBlocks, parseApiMessages } from "@/utils/messages";
import type { MessageResponse } from "@/api/types";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeMsg(overrides: Partial<MessageResponse> = {}): MessageResponse {
  return {
    id: "msg-" + Math.random().toString(36).slice(2),
    session_id: "sess-1",
    role: "assistant",
    content: "hello",
    reasoning_content: null,
    tool_calls: null,
    tool_call_id: null,
    name: null,
    is_summary: false,
    is_hidden: false,
    extra: null,
    created_at: new Date().toISOString(),
    attachments: null,
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// sumUsageFromMessages
// ---------------------------------------------------------------------------

describe("sumUsageFromMessages", () => {
  it("returns zeros when no messages", () => {
    const result = sumUsageFromMessages([]);
    expect(result).toEqual({ promptTokens: 0, completionTokens: 0, totalTokens: 0, cachedTokens: 0 });
  });

  it("returns zeros when no assistant messages have usage", () => {
    const msgs = [makeMsg({ extra: null }), makeMsg({ role: "user" })];
    const result = sumUsageFromMessages(msgs);
    expect(result.totalTokens).toBe(0);
  });

  it("sums single assistant message with usage", () => {
    const msgs = [makeMsg({ extra: { usage: { input: 100, output: 40, cache: 10 } } })];
    const result = sumUsageFromMessages(msgs);
    expect(result.promptTokens).toBe(100);
    expect(result.completionTokens).toBe(40);
    expect(result.totalTokens).toBe(140);
    expect(result.cachedTokens).toBe(10);
  });

  it("uses last turn input for promptTokens, sums output, uses last turn cache", () => {
    // Me input = latest turn only (context window size), output = cumulative, cache = latest
    const msgs = [
      makeMsg({ extra: { usage: { input: 50, output: 20, cache: 0 } } }),
      makeMsg({ extra: { usage: { input: 80, output: 30, cache: 5 } } }),
    ];
    const result = sumUsageFromMessages(msgs);
    expect(result.promptTokens).toBe(80);      // latest turn input only
    expect(result.completionTokens).toBe(50);  // sum: 20 + 30
    expect(result.totalTokens).toBe(130);      // latest input + total output
    expect(result.cachedTokens).toBe(5);       // latest turn cache only
  });

  it("skips non-assistant messages", () => {
    const msgs = [
      makeMsg({ role: "user", extra: { usage: { input: 999, output: 999, cache: 0 } } }),
      makeMsg({ role: "tool", extra: { usage: { input: 999, output: 999, cache: 0 } } }),
      makeMsg({ role: "assistant", extra: { usage: { input: 10, output: 5, cache: 0 } } }),
    ];
    const result = sumUsageFromMessages(msgs);
    expect(result.promptTokens).toBe(10);
    expect(result.totalTokens).toBe(15);
  });

  it("treats missing cache field as 0", () => {
    const msgs = [makeMsg({ extra: { usage: { input: 10, output: 5 } } })];
    const result = sumUsageFromMessages(msgs);
    expect(result.cachedTokens).toBe(0);
  });

  it("skips hidden messages (not filtered here — caller responsibility)", () => {
    // sumUsageFromMessages does NOT filter is_hidden — it trusts the caller
    // parseTeamBlocks filters is_hidden; sumUsageFromMessages sums all assistant msgs
    const msgs = [makeMsg({ is_hidden: true, extra: { usage: { input: 10, output: 5, cache: 0 } } })];
    const result = sumUsageFromMessages(msgs);
    // Me still counts hidden messages — this matches DatabaseHook behaviour (all turns are stored)
    expect(result.totalTokens).toBe(15);
  });
});

// ---------------------------------------------------------------------------
// parseTeamBlocks — basic coverage
// ---------------------------------------------------------------------------

describe("parseTeamBlocks", () => {
  it("returns empty array for empty input", () => {
    expect(parseTeamBlocks([])).toEqual([]);
  });

  it("converts user message to type:user block", () => {
    const msgs = [makeMsg({ role: "user", content: "hello team" })];
    const blocks = parseTeamBlocks(msgs);
    expect(blocks).toHaveLength(1);
    expect(blocks[0].type).toBe("user");
    expect(blocks[0].content).toBe("hello team");
  });

  it("converts assistant message to text block", () => {
    const msgs = [makeMsg({ role: "assistant", content: "here is my answer" })];
    const blocks = parseTeamBlocks(msgs);
    const textBlock = blocks.find((b) => b.type === "text");
    expect(textBlock).toBeDefined();
    expect(textBlock?.content).toBe("here is my answer");
  });

  it("converts reasoning_content to thinking block", () => {
    const msgs = [makeMsg({ role: "assistant", reasoning_content: "let me think", content: null })];
    const blocks = parseTeamBlocks(msgs);
    expect(blocks[0].type).toBe("thinking");
    expect(blocks[0].content).toBe("let me think");
  });

  it("skips summary messages", () => {
    const msgs = [makeMsg({ is_summary: true, role: "assistant", content: "summary text" })];
    expect(parseTeamBlocks(msgs)).toHaveLength(0);
  });

  it("shows hidden messages (user sees full history)", () => {
    const msgs = [makeMsg({ is_hidden: true, role: "assistant", content: "old message" })];
    expect(parseTeamBlocks(msgs)).toHaveLength(1);
  });

  it("links tool_call to tool result via tool_call_id", () => {
    const t = new Date().toISOString();
    const msgs = [
      makeMsg({
        role: "assistant",
        content: null,
        tool_calls: [{ id: "tc1", type: "function", function: { name: "search", arguments: '{"q":"x"}' } }],
        created_at: t,
      }),
      makeMsg({
        role: "tool",
        content: "result data",
        tool_call_id: "tc1",
        created_at: t,
      }),
    ];
    const blocks = parseTeamBlocks(msgs);
    const toolBlock = blocks.find((b) => b.type === "tool");
    expect(toolBlock).toBeDefined();
    expect(toolBlock?.toolDone).toBe(true);
    expect(toolBlock?.toolResult).toBe("result data");
  });

  it("sorts messages by created_at asc", () => {
    const earlier = new Date(Date.now() - 10000).toISOString();
    const later = new Date().toISOString();
    const msgs = [
      makeMsg({ role: "user", content: "second", created_at: later }),
      makeMsg({ role: "user", content: "first", created_at: earlier }),
    ];
    const blocks = parseTeamBlocks(msgs);
    expect(blocks[0].content).toBe("first");
    expect(blocks[1].content).toBe("second");
  });
});

// ---------------------------------------------------------------------------
// parseApiMessages
// ---------------------------------------------------------------------------

describe("parseApiMessages", () => {
  it("returns empty array for empty input", () => {
    expect(parseApiMessages([])).toEqual([]);
  });

  it("converts user message to role:user ChatMessage", () => {
    const msgs = [makeMsg({ role: "user", content: "hello" })];
    const result = parseApiMessages(msgs);
    expect(result).toHaveLength(1);
    expect(result[0].role).toBe("user");
    expect(result[0].content).toBe("hello");
    expect(result[0].blocks).toEqual([]);
  });

  it("converts assistant message to role:assistant with text block", () => {
    const msgs = [makeMsg({ role: "assistant", content: "my answer" })];
    const result = parseApiMessages(msgs);
    expect(result).toHaveLength(1);
    expect(result[0].role).toBe("assistant");
    const textBlock = result[0].blocks.find((b) => b.type === "text");
    expect(textBlock?.content).toBe("my answer");
  });

  it("converts reasoning_content to thinking block", () => {
    const msgs = [makeMsg({ role: "assistant", reasoning_content: "thinking...", content: null })];
    const result = parseApiMessages(msgs);
    const thinkBlock = result[0].blocks.find((b) => b.type === "thinking");
    expect(thinkBlock?.content).toBe("thinking...");
  });

  it("converts tool_calls to tool blocks", () => {
    const msgs = [makeMsg({
      role: "assistant",
      content: null,
      tool_calls: [{ id: "tc1", type: "function", function: { name: "search", arguments: '{"q":"x"}' } }],
    })];
    const result = parseApiMessages(msgs);
    const toolBlock = result[0].blocks.find((b) => b.type === "tool");
    expect(toolBlock?.toolName).toBe("search");
    expect(toolBlock?.toolCallId).toBe("tc1");
    expect(toolBlock?.toolDone).toBe(false);
  });

  it("links tool result to tool block via tool_call_id", () => {
    const t = new Date().toISOString();
    const msgs = [
      makeMsg({
        role: "assistant",
        content: null,
        tool_calls: [{ id: "tc1", type: "function", function: { name: "search", arguments: "{}" } }],
        created_at: t,
      }),
      makeMsg({ role: "tool", content: "result!", tool_call_id: "tc1", created_at: t }),
    ];
    const result = parseApiMessages(msgs);
    const toolBlock = result[0].blocks.find((b) => b.type === "tool");
    expect(toolBlock?.toolDone).toBe(true);
    expect(toolBlock?.toolResult).toBe("result!");
  });

  it("skips summary messages", () => {
    const msgs = [makeMsg({ is_summary: true, role: "assistant", content: "summary" })];
    expect(parseApiMessages(msgs)).toHaveLength(0);
  });

  it("extracts usage from extra field", () => {
    const msgs = [makeMsg({ extra: { usage: { input: 100, output: 50, cache: 10 } } })];
    const result = parseApiMessages(msgs);
    expect(result[0].usage?.promptTokens).toBe(100);
    expect(result[0].usage?.completionTokens).toBe(50);
    expect(result[0].usage?.cachedTokens).toBe(10);
    expect(result[0].usage?.totalTokens).toBe(150);
  });

  it("leaves usage undefined when extra has no usage", () => {
    const msgs = [makeMsg({ extra: null })];
    const result = parseApiMessages(msgs);
    expect(result[0].usage).toBeUndefined();
  });

  it("preserves agent name from message.name field", () => {
    const msgs = [makeMsg({ role: "assistant", name: "planner", content: "done" })];
    const result = parseApiMessages(msgs);
    expect(result[0].agent).toBe("planner");
  });

  it("sets timestamp from created_at", () => {
    const ts = "2024-06-01T12:00:00.000Z";
    const msgs = [makeMsg({ role: "user", content: "hi", created_at: ts })];
    const result = parseApiMessages(msgs);
    expect(result[0].timestamp).toEqual(new Date(ts));
  });

  it("sorts and processes messages in chronological order", () => {
    const earlier = new Date(Date.now() - 10000).toISOString();
    const later = new Date().toISOString();
    const msgs = [
      makeMsg({ role: "user", content: "second", created_at: later }),
      makeMsg({ role: "user", content: "first", created_at: earlier }),
    ];
    const result = parseApiMessages(msgs);
    expect(result[0].content).toBe("first");
    expect(result[1].content).toBe("second");
  });

  it("produces thinking block before text block when both present", () => {
    const msgs = [makeMsg({
      role: "assistant",
      reasoning_content: "my reasoning",
      content: "my answer",
    })];
    const result = parseApiMessages(msgs);
    const blocks = result[0].blocks;
    expect(blocks[0].type).toBe("thinking");
    expect(blocks[1].type).toBe("text");
  });

  it("filters out todo_manage tool calls from blocks", () => {
    const msgs = [makeMsg({
      role: "assistant",
      content: null,
      tool_calls: [
        { id: "tc1", type: "function", function: { name: "todo_manage", arguments: '{"action":"create"}' } },
      ],
    })];
    const result = parseApiMessages(msgs);
    expect(result[0].blocks).toHaveLength(0);
  });

  it("includes non-todo tool calls while filtering todo_manage", () => {
    const msgs = [makeMsg({
      role: "assistant",
      content: null,
      tool_calls: [
        { id: "tc1", type: "function", function: { name: "todo_manage", arguments: '{"action":"create"}' } },
        { id: "tc2", type: "function", function: { name: "web_search", arguments: '{"q":"test"}' } },
      ],
    })];
    const result = parseApiMessages(msgs);
    expect(result[0].blocks).toHaveLength(1);
    expect(result[0].blocks[0].toolName).toBe("web_search");
    expect(result[0].blocks[0].toolCallId).toBe("tc2");
  });
});

// ---------------------------------------------------------------------------
// parseTeamBlocks — todo_manage filtering
// ---------------------------------------------------------------------------

describe("parseTeamBlocks — todo_manage filtering", () => {
  it("filters out todo_manage tool calls from blocks", () => {
    const msgs = [makeMsg({
      role: "assistant",
      content: null,
      tool_calls: [
        { id: "tc1", type: "function", function: { name: "todo_manage", arguments: '{"action":"create"}' } },
      ],
    })];
    const blocks = parseTeamBlocks(msgs);
    expect(blocks).toHaveLength(0);
  });

  it("includes non-todo tool calls while filtering todo_manage", () => {
    const msgs = [makeMsg({
      role: "assistant",
      content: null,
      tool_calls: [
        { id: "tc1", type: "function", function: { name: "todo_manage", arguments: '{"action":"create"}' } },
        { id: "tc2", type: "function", function: { name: "web_search", arguments: '{"q":"test"}' } },
      ],
    })];
    const blocks = parseTeamBlocks(msgs);
    expect(blocks).toHaveLength(1);
    expect(blocks[0].type).toBe("tool");
    expect(blocks[0].toolName).toBe("web_search");
    expect(blocks[0].toolCallId).toBe("tc2");
  });

  it("preserves tool result linking when todo_manage is filtered", () => {
    const t = new Date().toISOString();
    const msgs = [
      makeMsg({
        role: "assistant",
        content: null,
        tool_calls: [
          { id: "tc1", type: "function", function: { name: "todo_manage", arguments: '{}' } },
          { id: "tc2", type: "function", function: { name: "web_search", arguments: '{}' } },
        ],
        created_at: t,
      }),
      makeMsg({
        role: "tool",
        content: "search result",
        tool_call_id: "tc2",
        created_at: t,
      }),
    ];
    const blocks = parseTeamBlocks(msgs);
    expect(blocks).toHaveLength(1);
    expect(blocks[0].toolDone).toBe(true);
    expect(blocks[0].toolResult).toBe("search result");
  });
});
