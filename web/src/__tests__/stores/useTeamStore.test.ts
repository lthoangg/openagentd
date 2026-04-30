import { describe, it, expect, beforeEach } from "bun:test";
import { useTeamStore } from "@/stores/useTeamStore";
import type { ContentBlock } from "@/api/types";

// Me reset store before each test
const INITIAL = {
  agentStreams: {},
  activeAgent: null,
  leadName: null,
  agentNames: [],
  sidebarOpen: false,
  sessionId: null,
  isTeamWorking: false,
  isConnected: false,
  error: null,
  _pendingMessages: [] as import('@/stores/useTeamStore').PendingMessage[],
  _sessionGeneration: 0,
};

beforeEach(() => {
  useTeamStore.setState(INITIAL);
});

function makeStream(overrides: object = {}) {
  return {
    blocks: [] as ContentBlock[],
    currentBlocks: [] as ContentBlock[],
    status: "available" as const,
    usage: { promptTokens: 0, completionTokens: 0, totalTokens: 0, cachedTokens: 0 },
    model: null,
    lastError: null,
    currentText: "",
    currentThinking: "",
    _completionBase: 0,
    ...overrides,
  };
}

// ── newSession ────────────────────────────────────────────────────────────────

describe("newSession", () => {
  it("clears sessionId and resets working state", () => {
    useTeamStore.setState({ sessionId: "old-sid", isTeamWorking: true });
    useTeamStore.getState().newSession();
    const s = useTeamStore.getState();
    expect(s.sessionId).toBeNull();
    expect(s.isTeamWorking).toBe(false);
  });

  it("resets agent blocks but keeps agentNames", () => {
    useTeamStore.setState({
      agentNames: ["lead", "worker"],
      agentStreams: {
        lead: makeStream({ blocks: [{ id: "b1", type: "text" as const, content: "old" }] }),
      },
    });
    useTeamStore.getState().newSession();
    const s = useTeamStore.getState();
    expect(s.agentNames).toEqual(["lead", "worker"]);
    expect(s.agentStreams.lead.blocks).toHaveLength(0);
    expect(s.agentStreams.lead.currentBlocks).toHaveLength(0);
  });

  it("bumps _sessionGeneration", () => {
    const before = useTeamStore.getState()._sessionGeneration;
    useTeamStore.getState().newSession();
    expect(useTeamStore.getState()._sessionGeneration).toBe(before + 1);
  });
});

// ── setActiveAgent ────────────────────────────────────────────────────────────

describe("setActiveAgent", () => {
  it("updates activeAgent", () => {
    useTeamStore.getState().setActiveAgent("researcher");
    expect(useTeamStore.getState().activeAgent).toBe("researcher");
  });
});

// ── cycleActiveAgent ──────────────────────────────────────────────────────────

describe("cycleActiveAgent", () => {
  it("cycles forward through agents", () => {
    useTeamStore.setState({ agentNames: ["lead", "worker", "researcher"], activeAgent: "lead" });
    useTeamStore.getState().cycleActiveAgent("next");
    expect(useTeamStore.getState().activeAgent).toBe("worker");
  });

  it("wraps around at end", () => {
    useTeamStore.setState({ agentNames: ["lead", "worker"], activeAgent: "worker" });
    useTeamStore.getState().cycleActiveAgent("next");
    expect(useTeamStore.getState().activeAgent).toBe("lead");
  });

  it("cycles backward", () => {
    useTeamStore.setState({ agentNames: ["lead", "worker"], activeAgent: "worker" });
    useTeamStore.getState().cycleActiveAgent("prev");
    expect(useTeamStore.getState().activeAgent).toBe("lead");
  });

  it("wraps around at start going backward", () => {
    useTeamStore.setState({ agentNames: ["lead", "worker"], activeAgent: "lead" });
    useTeamStore.getState().cycleActiveAgent("prev");
    expect(useTeamStore.getState().activeAgent).toBe("worker");
  });

  it("does nothing when agentNames is empty", () => {
    useTeamStore.setState({ agentNames: [], activeAgent: null });
    useTeamStore.getState().cycleActiveAgent("next");
    expect(useTeamStore.getState().activeAgent).toBeNull();
  });
});

// ── _handleSSEEvent: message ──────────────────────────────────────────────────

describe("_handleSSEEvent: message", () => {
  it("appends text to agent currentBlocks", () => {
    useTeamStore.getState()._handleSSEEvent("message", { agent: "lead", text: "hello" });
    const stream = useTeamStore.getState().agentStreams["lead"];
    expect(stream).toBeDefined();
    expect(stream.currentBlocks).toHaveLength(1);
    expect(stream.currentBlocks[0].content).toBe("hello");
  });

  it("appends to same text block on subsequent chunks", () => {
    useTeamStore.getState()._handleSSEEvent("message", { agent: "lead", text: "hello" });
    useTeamStore.getState()._handleSSEEvent("message", { agent: "lead", text: " world" });
    const stream = useTeamStore.getState().agentStreams["lead"];
    expect(stream.currentBlocks).toHaveLength(1);
    expect(stream.currentBlocks[0].content).toBe("hello world");
  });

  it("isolates chunks per agent", () => {
    useTeamStore.getState()._handleSSEEvent("message", { agent: "lead", text: "lead says" });
    useTeamStore.getState()._handleSSEEvent("message", { agent: "worker", text: "worker says" });
    expect(useTeamStore.getState().agentStreams["lead"].currentBlocks[0].content).toBe("lead says");
    expect(useTeamStore.getState().agentStreams["worker"].currentBlocks[0].content).toBe("worker says");
  });
});

// ── _handleSSEEvent: thinking ─────────────────────────────────────────────────

describe("_handleSSEEvent: thinking", () => {
  it("creates thinking block", () => {
    useTeamStore.getState()._handleSSEEvent("thinking", { agent: "lead", text: "let me think" });
    const stream = useTeamStore.getState().agentStreams["lead"];
    expect(stream.currentBlocks[0].type).toBe("thinking");
    expect(stream.currentBlocks[0].content).toBe("let me think");
  });
});

// ── _handleSSEEvent: tool lifecycle ──────────────────────────────────────────

describe("_handleSSEEvent: tool lifecycle", () => {
  it("tool_call creates pending tool block", () => {
    useTeamStore.getState()._handleSSEEvent("tool_call", { agent: "lead", name: "web_search", tool_call_id: "tc1" });
    const block = useTeamStore.getState().agentStreams["lead"].currentBlocks[0];
    expect(block.type).toBe("tool");
    expect(block.toolDone).toBe(false);
    expect(block.toolCallId).toBe("tc1");
  });

  it("tool_start fills args", () => {
    useTeamStore.getState()._handleSSEEvent("tool_call", { agent: "lead", name: "web_search", tool_call_id: "tc1" });
    useTeamStore.getState()._handleSSEEvent("tool_start", { agent: "lead", name: "web_search", tool_call_id: "tc1", arguments: '{"q":"test"}' });
    const block = useTeamStore.getState().agentStreams["lead"].currentBlocks[0];
    expect(block.toolArgs).toBe('{"q":"test"}');
  });

  it("tool_end marks done with result", () => {
    useTeamStore.getState()._handleSSEEvent("tool_call", { agent: "lead", name: "web_search", tool_call_id: "tc1" });
    useTeamStore.getState()._handleSSEEvent("tool_start", { agent: "lead", name: "web_search", tool_call_id: "tc1", arguments: "{}" });
    useTeamStore.getState()._handleSSEEvent("tool_end", { agent: "lead", name: "web_search", tool_call_id: "tc1", result: "results" });
    const block = useTeamStore.getState().agentStreams["lead"].currentBlocks[0];
    expect(block.toolDone).toBe(true);
    expect(block.toolResult).toBe("results");
  });
});

// ── _handleSSEEvent: agent_status ────────────────────────────────────────────

describe("_handleSSEEvent: agent_status", () => {
  it("sets agent status to working", () => {
    useTeamStore.getState()._handleSSEEvent("agent_status", { agent: "lead", status: "working" });
    expect(useTeamStore.getState().agentStreams["lead"].status).toBe("working");
  });

  it("sets agent status to available", () => {
    useTeamStore.getState()._handleSSEEvent("agent_status", { agent: "lead", status: "available" });
    expect(useTeamStore.getState().agentStreams["lead"].status).toBe("available");
  });

  it("sets agent status to error with message", () => {
    useTeamStore.getState()._handleSSEEvent("agent_status", { agent: "lead", status: "error", metadata: { message: "something broke" } });
    expect(useTeamStore.getState().agentStreams["lead"].status).toBe("error");
    expect(useTeamStore.getState().agentStreams["lead"].lastError).toBe("something broke");
  });

  it("keeps isTeamWorking=true while any other agent is still working", () => {
    // Lead + worker both working
    useTeamStore.getState()._handleSSEEvent("agent_status", { agent: "lead", status: "working" });
    useTeamStore.getState()._handleSSEEvent("agent_status", { agent: "worker", status: "working" });
    expect(useTeamStore.getState().isTeamWorking).toBe(true);

    // Worker goes idle — lead still working, global flag must stay true
    useTeamStore.getState()._handleSSEEvent("agent_status", { agent: "worker", status: "available" });
    const s = useTeamStore.getState();
    expect(s.agentStreams.worker.status).toBe("available");
    expect(s.agentStreams.lead.status).toBe("working");
    expect(s.isTeamWorking).toBe(true);
  });

  it("clears isTeamWorking when the last working agent goes idle", () => {
    useTeamStore.getState()._handleSSEEvent("agent_status", { agent: "lead", status: "working" });
    useTeamStore.getState()._handleSSEEvent("agent_status", { agent: "worker", status: "working" });
    useTeamStore.getState()._handleSSEEvent("agent_status", { agent: "worker", status: "available" });
    useTeamStore.getState()._handleSSEEvent("agent_status", { agent: "lead", status: "available" });
    expect(useTeamStore.getState().isTeamWorking).toBe(false);
  });

  it("clears isTeamWorking when the last working agent errors out", () => {
    useTeamStore.getState()._handleSSEEvent("agent_status", { agent: "lead", status: "working" });
    useTeamStore.getState()._handleSSEEvent("agent_status", {
      agent: "lead",
      status: "error",
      metadata: { message: "boom" },
    });
    expect(useTeamStore.getState().isTeamWorking).toBe(false);
  });
});

// ── _handleSSEEvent: done ─────────────────────────────────────────────────────

describe("_handleSSEEvent: done", () => {
  it("flushes currentBlocks into blocks and clears working flag", () => {
    useTeamStore.setState({
      isTeamWorking: true,
      leadName: "lead",
      agentStreams: {
        lead: makeStream({
          currentBlocks: [{ id: "b1", type: "text" as const, content: "response" }],
          status: "working" as const,
        }),
      },
    });
    useTeamStore.getState()._handleSSEEvent("done", {});
    const s = useTeamStore.getState();
    expect(s.isTeamWorking).toBe(false);
    expect(s.agentStreams.lead.blocks).toHaveLength(1);
    expect(s.agentStreams.lead.currentBlocks).toHaveLength(0);
  });

  it("flushes worker blocks too", () => {
    useTeamStore.setState({
      isTeamWorking: true,
      leadName: "lead",
      agentStreams: {
        worker: makeStream({
          currentBlocks: [{ id: "b1", type: "text" as const, content: "worker output" }],
          status: "working" as const,
        }),
      },
    });
    useTeamStore.getState()._handleSSEEvent("done", {});
    const s = useTeamStore.getState();
    expect(s.agentStreams.worker.blocks).toHaveLength(1);
    expect(s.agentStreams.worker.currentBlocks).toHaveLength(0);
  });

  it("sets all agent statuses to available", () => {
    useTeamStore.setState({
      isTeamWorking: true,
      leadName: "lead",
      agentStreams: {
        lead: makeStream({ status: "working" as const }),
        worker: makeStream({ status: "working" as const }),
      },
    });
    useTeamStore.getState()._handleSSEEvent("done", {});
    expect(useTeamStore.getState().agentStreams.lead.status).toBe("available");
    expect(useTeamStore.getState().agentStreams.worker.status).toBe("available");
  });
});

// ── _handleSSEEvent: session ──────────────────────────────────────────────────

describe("_handleSSEEvent: session", () => {
  it("sets sessionId from event data", () => {
    useTeamStore.getState()._handleSSEEvent("session", { session_id: "new-sid" });
    expect(useTeamStore.getState().sessionId).toBe("new-sid");
  });
});

// ── _handleSSEEvent: usage ────────────────────────────────────────────────────

describe("_handleSSEEvent: usage", () => {
  it("reads agent from metadata.agent (backend wire format)", () => {
    useTeamStore.getState()._handleSSEEvent("usage", {
      prompt_tokens: 10,
      completion_tokens: 5,
      total_tokens: 15,
      cached_tokens: 2,
      metadata: { agent: "lead" },
    });
    const usage = useTeamStore.getState().agentStreams["lead"].usage;
    expect(usage.totalTokens).toBe(15);
    expect(usage.promptTokens).toBe(10);
    expect(usage.cachedTokens).toBe(2);
  });

  it("falls back to top-level agent field", () => {
    useTeamStore.getState()._handleSSEEvent("usage", {
      agent: "worker",
      prompt_tokens: 20,
      completion_tokens: 8,
      total_tokens: 28,
      cached_tokens: 0,
    });
    const usage = useTeamStore.getState().agentStreams["worker"].usage;
    expect(usage.totalTokens).toBe(28);
  });

  it("accumulates usage across multiple events (multi-turn)", () => {
    // Me input = latest turn only, output = sum all turns, cache = latest turn
    // Turn 1: fire usage then done (done commits _completionBase)
    useTeamStore.getState()._handleSSEEvent("usage", {
      prompt_tokens: 10, completion_tokens: 5, total_tokens: 15,
      cached_tokens: 0, metadata: { agent: "lead" },
    });
    useTeamStore.setState((s) => ({
      agentStreams: {
        ...s.agentStreams,
        lead: { ...s.agentStreams.lead, status: "working" as const },
      },
    }));
    useTeamStore.getState()._handleSSEEvent("done", {});
    // Turn 2: fire second usage event — completionBase now = 5
    useTeamStore.getState()._handleSSEEvent("usage", {
      prompt_tokens: 20, completion_tokens: 10, total_tokens: 30,
      cached_tokens: 3, metadata: { agent: "lead" },
    });
    const usage = useTeamStore.getState().agentStreams["lead"].usage;
    expect(usage.promptTokens).toBe(20);      // latest turn input only
    expect(usage.completionTokens).toBe(15);  // sum: 5 (turn1) + 10 (turn2)
    expect(usage.totalTokens).toBe(35);       // latest input + total output
    expect(usage.cachedTokens).toBe(3);       // latest turn cache only
  });

  it("ignores event with no agent field", () => {
    useTeamStore.getState()._handleSSEEvent("usage", {
      prompt_tokens: 10, completion_tokens: 5, total_tokens: 15,
    });
    // Me no stream created for unknown agent
    expect(Object.keys(useTeamStore.getState().agentStreams)).toHaveLength(0);
  });

  it("resets usage on newSession", () => {
    useTeamStore.getState()._handleSSEEvent("usage", {
      prompt_tokens: 100, completion_tokens: 50, total_tokens: 150,
      cached_tokens: 5, metadata: { agent: "lead" },
    });
    useTeamStore.getState().newSession();
    expect(useTeamStore.getState().agentStreams["lead"].usage.totalTokens).toBe(0);
  });
});

// ── _handleSSEEvent: title_update ─────────────────────────────────────────────

describe("_handleSSEEvent: title_update", () => {
  it("sets sessionTitle from event data", () => {
    useTeamStore.getState()._handleSSEEvent("title_update", { title: "Team Chat Title" });
    expect(useTeamStore.getState().sessionTitle).toBe("Team Chat Title");
  });

  it("overwrites previous sessionTitle", () => {
    useTeamStore.getState()._handleSSEEvent("title_update", { title: "First Title" });
    expect(useTeamStore.getState().sessionTitle).toBe("First Title");

    useTeamStore.getState()._handleSSEEvent("title_update", { title: "Second Title" });
    expect(useTeamStore.getState().sessionTitle).toBe("Second Title");
  });

  it("does not affect other state when title updates", () => {
    useTeamStore.setState({
      sessionId: "test-sid",
      isTeamWorking: true,
      activeAgent: "lead",
      agentNames: ["lead", "worker"],
    });

    useTeamStore.getState()._handleSSEEvent("title_update", { title: "New Title" });

    const s = useTeamStore.getState();
    expect(s.sessionTitle).toBe("New Title");
    // Other state unchanged
    expect(s.sessionId).toBe("test-sid");
    expect(s.isTeamWorking).toBe(true);
    expect(s.activeAgent).toBe("lead");
    expect(s.agentNames).toEqual(["lead", "worker"]);
  });

  it("newSession() resets sessionTitle to null", () => {
    useTeamStore.getState()._handleSSEEvent("title_update", { title: "Some Title" });
    expect(useTeamStore.getState().sessionTitle).toBe("Some Title");

    useTeamStore.getState().newSession();

    expect(useTeamStore.getState().sessionTitle).toBeNull();
  });

  it("sessionTitle initializes as null", () => {
    const s = useTeamStore.getState();
    expect(s.sessionTitle).toBeNull();
  });

  it("handles empty string title", () => {
    useTeamStore.getState()._handleSSEEvent("title_update", { title: "" });
    expect(useTeamStore.getState().sessionTitle).toBe("");
  });

  it("handles special characters in title", () => {
    const specialTitle = "Team: @research & analysis <2024>";
    useTeamStore.getState()._handleSSEEvent("title_update", { title: specialTitle });
    expect(useTeamStore.getState().sessionTitle).toBe(specialTitle);
  });

  it("title_update does not affect agent streams", () => {
    useTeamStore.setState({
      agentStreams: {
        lead: makeStream({ blocks: [{ id: "b1", type: "text" as const, content: "old" }] }),
      },
    });

    useTeamStore.getState()._handleSSEEvent("title_update", { title: "New Title" });

    const s = useTeamStore.getState();
    expect(s.sessionTitle).toBe("New Title");
    expect(s.agentStreams.lead.blocks).toHaveLength(1);
    expect(s.agentStreams.lead.blocks[0].content).toBe("old");
  });
});
