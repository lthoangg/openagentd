import { describe, it, expect } from "bun:test";
import { appendThinking, appendText, initTool, addTool, completeTool } from "@/utils/blocks";
import type { ContentBlock } from "@/api/types";

// ---------------------------------------------------------------------------
// appendThinking
// ---------------------------------------------------------------------------

describe("appendThinking", () => {
  it("creates new thinking block when blocks is empty", () => {
    const result = appendThinking([], "hello");
    expect(result).toHaveLength(1);
    expect(result[0].type).toBe("thinking");
    expect(result[0].content).toBe("hello");
  });

  it("appends to last thinking block", () => {
    const blocks: ContentBlock[] = [{ id: "t1", type: "thinking", content: "hello" }];
    const result = appendThinking(blocks, " world");
    expect(result).toHaveLength(1);
    expect(result[0].content).toBe("hello world");
  });

  it("creates new block when last is text type", () => {
    const blocks: ContentBlock[] = [{ id: "t1", type: "text", content: "hello" }];
    const result = appendThinking(blocks, "thought");
    expect(result).toHaveLength(2);
    expect(result[1].type).toBe("thinking");
  });

  it("preserves existing blocks", () => {
    const blocks: ContentBlock[] = [
      { id: "t1", type: "text", content: "first" },
      { id: "t2", type: "thinking", content: "thought" },
    ];
    const result = appendThinking(blocks, " more");
    expect(result).toHaveLength(2);
    expect(result[1].content).toBe("thought more");
  });
});

// ---------------------------------------------------------------------------
// appendText
// ---------------------------------------------------------------------------

describe("appendText", () => {
  it("creates new text block when empty", () => {
    const result = appendText([], "hello");
    expect(result).toHaveLength(1);
    expect(result[0].type).toBe("text");
    expect(result[0].content).toBe("hello");
  });

  it("appends to last text block", () => {
    const blocks: ContentBlock[] = [{ id: "t1", type: "text", content: "hello" }];
    const result = appendText(blocks, " world");
    expect(result).toHaveLength(1);
    expect(result[0].content).toBe("hello world");
  });

  it("creates new text block when last is thinking", () => {
    const blocks: ContentBlock[] = [{ id: "t1", type: "thinking", content: "hmm" }];
    const result = appendText(blocks, "answer");
    expect(result).toHaveLength(2);
    expect(result[1].type).toBe("text");
  });

  it("creates new text block when last is tool", () => {
    const blocks: ContentBlock[] = [{ id: "t1", type: "tool", content: "", toolName: "search", toolDone: false }];
    const result = appendText(blocks, "result");
    expect(result).toHaveLength(2);
    expect(result[1].type).toBe("text");
  });
});

// ---------------------------------------------------------------------------
// initTool
// ---------------------------------------------------------------------------

describe("initTool", () => {
  it("adds pending tool block", () => {
    const result = initTool([], "web_search", "tc1");
    expect(result).toHaveLength(1);
    expect(result[0].type).toBe("tool");
    expect(result[0].toolName).toBe("web_search");
    expect(result[0].toolDone).toBe(false);
    expect(result[0].toolCallId).toBe("tc1");
    expect(result[0].toolArgs).toBeUndefined();
  });

  it("appends to existing blocks", () => {
    const blocks: ContentBlock[] = [{ id: "t1", type: "text", content: "hi" }];
    const result = initTool(blocks, "read_file");
    expect(result).toHaveLength(2);
  });

  it("skips duplicate — same toolCallId already exists (reconnect replay dedup)", () => {
    const blocks: ContentBlock[] = [
      { id: "t1", type: "tool", content: "", toolName: "web_search", toolDone: false, toolCallId: "tc1" },
    ];
    const result = initTool(blocks, "web_search", "tc1");
    expect(result).toHaveLength(1); // no duplicate added
    expect(result).toBe(blocks);    // initTool returns original array ref unchanged
  });

  it("adds new block when toolCallId differs", () => {
    const blocks: ContentBlock[] = [
      { id: "t1", type: "tool", content: "", toolName: "web_search", toolDone: false, toolCallId: "tc1" },
    ];
    const result = initTool(blocks, "web_search", "tc2");
    expect(result).toHaveLength(2);
  });
});

// ---------------------------------------------------------------------------
// addTool
// ---------------------------------------------------------------------------

describe("addTool", () => {
  it("fills args on matching block by toolCallId", () => {
    const blocks: ContentBlock[] = [
      { id: "t1", type: "tool", content: "", toolName: "web_search", toolArgs: undefined, toolDone: false, toolCallId: "tc1" },
    ];
    const result = addTool(blocks, "web_search", '{"q":"test"}', "tc1");
    expect(result[0].toolArgs).toBe('{"q":"test"}');
    expect(result[0].toolDone).toBe(false);
  });

  it("skips args update if block already has args (reconnect replay dedup)", () => {
    const blocks: ContentBlock[] = [
      { id: "t1", type: "tool", content: "", toolName: "web_search", toolArgs: '{"q":"original"}', toolDone: false, toolCallId: "tc1" },
    ];
    const result = addTool(blocks, "web_search", '{"q":"replay"}', "tc1");
    expect(result[0].toolArgs).toBe('{"q":"original"}'); // Me keep original
    expect(result).toHaveLength(1); // no duplicate added
  });

  it("fills args on matching block by name when no toolCallId", () => {
    const blocks: ContentBlock[] = [
      { id: "t1", type: "tool", content: "", toolName: "web_search", toolArgs: undefined, toolDone: false },
    ];
    const result = addTool(blocks, "web_search", '{"q":"test"}');
    expect(result[0].toolArgs).toBe('{"q":"test"}');
  });

  it("creates new block as fallback when no match found", () => {
    const result = addTool([], "web_search", '{"q":"x"}', "tc-missing");
    expect(result).toHaveLength(1);
    expect(result[0].toolArgs).toBe('{"q":"x"}');
  });

  it("matches last incomplete block by name in LIFO order", () => {
    const blocks: ContentBlock[] = [
      { id: "t1", type: "tool", content: "", toolName: "web_search", toolArgs: undefined, toolDone: false, toolCallId: "tc-first" },
      { id: "t2", type: "tool", content: "", toolName: "web_search", toolArgs: undefined, toolDone: false, toolCallId: "tc-second" },
    ];
    const result = addTool(blocks, "web_search", '{"q":"x"}', "tc-second");
    // Only tc-second gets args
    expect(result[0].toolArgs).toBeUndefined();
    expect(result[1].toolArgs).toBe('{"q":"x"}');
  });
});

// ---------------------------------------------------------------------------
// completeTool
// ---------------------------------------------------------------------------

describe("completeTool", () => {
  it("marks tool done by toolCallId", () => {
    const blocks: ContentBlock[] = [
      { id: "t1", type: "tool", content: "", toolName: "web_search", toolDone: false, toolCallId: "tc1" },
    ];
    const result = completeTool(blocks, "web_search", "tc1", "results");
    expect(result[0].toolDone).toBe(true);
    expect(result[0].toolResult).toBe("results");
  });

  it("falls back to name when toolCallId not matched", () => {
    const blocks: ContentBlock[] = [
      { id: "t1", type: "tool", content: "", toolName: "web_search", toolDone: false, toolCallId: "other-id" },
    ];
    const result = completeTool(blocks, "web_search", undefined, "ok");
    expect(result[0].toolDone).toBe(true);
  });

  it("handles parallel calls — marks correct one by toolCallId", () => {
    const blocks: ContentBlock[] = [
      { id: "t1", type: "tool", content: "", toolName: "web_search", toolDone: false, toolCallId: "tc-A" },
      { id: "t2", type: "tool", content: "", toolName: "web_search", toolDone: false, toolCallId: "tc-B" },
    ];
    const result = completeTool(blocks, "web_search", "tc-A", "result-A");
    expect(result[0].toolDone).toBe(true);
    expect(result[0].toolResult).toBe("result-A");
    expect(result[1].toolDone).toBe(false);
  });

  it("returns blocks unchanged when no match", () => {
    const blocks: ContentBlock[] = [{ id: "t1", type: "text", content: "hi" }];
    const result = completeTool(blocks, "web_search", "tc1", "ok");
    expect(result).toEqual(blocks);
  });

  it("skips if block already done (reconnect replay dedup)", () => {
    const blocks: ContentBlock[] = [
      { id: "t1", type: "tool", content: "", toolName: "web_search", toolDone: true, toolResult: "original", toolCallId: "tc1" },
    ];
    const result = completeTool(blocks, "web_search", "tc1", "replay");
    expect(result[0].toolResult).toBe("original"); // Me keep original, not overwrite
    expect(result).toHaveLength(1); // no duplicate added
  });
});
