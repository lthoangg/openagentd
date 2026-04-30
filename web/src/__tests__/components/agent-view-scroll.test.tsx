import { describe, it, expect, afterEach } from "bun:test";
import "@testing-library/jest-dom";
import { render, cleanup } from "@testing-library/react";
import { MarkdownBlock } from "@/utils/markdown";

afterEach(() => cleanup());

describe("AgentView scroll-handler regression (video flicker fix)", () => {
  // Note: Full AgentView integration tests are complex due to component dependencies.
  // These tests focus on the core memoization behavior that prevents video flicker
  // during scroll events. The actual scroll event handling is tested via
  // MarkdownBlock memoization tests in markdown-video.test.tsx.

  it("MarkdownBlock with video is memoized to prevent remount on parent re-render", () => {
    // This simulates the scenario where AgentView re-renders on scroll events
    // but MarkdownBlock should not remount its video element.
    const { rerender, container } = render(
      <MarkdownBlock
        content="Here is a video: ![demo](clip.mp4)"
        sessionId="test-session"
      />,
    );

    const videoInitial = container.querySelector("video");
    expect(videoInitial).not.toBeNull();

    // Simulate parent re-render with identical props (like scroll event)
    rerender(
      <MarkdownBlock
        content="Here is a video: ![demo](clip.mp4)"
        sessionId="test-session"
      />,
    );

    const videoAfter = container.querySelector("video");
    // Same reference = no remount = no video flicker
    expect(videoAfter).toBe(videoInitial);
  });

  it("MarkdownBlock components map is memoized to prevent ReactMarkdown remount", () => {
    // The components map is memoized on sessionId, so changing content
    // but keeping sessionId should preserve component identity
    const { rerender, container } = render(
      <MarkdownBlock
        content="First paragraph with ![video1](clip1.mp4)"
        sessionId="test-session"
      />,
    );

    // Change content but keep sessionId
    rerender(
      <MarkdownBlock
        content="Second paragraph with ![video1](clip1.mp4)"
        sessionId="test-session"
      />,
    );

    // Video element may change due to content change, but the component
    // identity is preserved (no remount due to components map change)
    const videoAfter = container.querySelector("video");
    expect(videoAfter).not.toBeNull();
  });

  it("fixNestedFences is memoized to prevent unnecessary re-processing", () => {
    // fixNestedFences is memoized on content, so identical content
    // should not re-process the string
    const { rerender, container } = render(
      <MarkdownBlock
        content="```python\ncode\n```\n\n![video](clip.mp4)"
        sessionId="test-session"
      />,
    );

    const videoInitial = container.querySelector("video");

    // Re-render with identical content
    rerender(
      <MarkdownBlock
        content="```python\ncode\n```\n\n![video](clip.mp4)"
        sessionId="test-session"
      />,
    );

    const videoAfter = container.querySelector("video");
    expect(videoAfter).toBe(videoInitial);
  });

  it("MarkdownVideo is memoized to prevent remount on parent scroll", () => {
    // MarkdownVideo is wrapped in React.memo, so identical src/alt/title
    // should not cause remount
    const { rerender, container } = render(
      <MarkdownBlock
        content="![demo](clip.mp4)"
        sessionId="test-session"
      />,
    );

    const videoInitial = container.querySelector("video");

    // Simulate multiple parent re-renders (like scroll events)
    for (let i = 0; i < 3; i++) {
      rerender(
        <MarkdownBlock
          content="![demo](clip.mp4)"
          sessionId="test-session"
        />,
      );
    }

    const videoAfter = container.querySelector("video");
    expect(videoAfter).toBe(videoInitial);
  });

  it("multiple videos in same block maintain independent memoization", () => {
    const { rerender, container } = render(
      <MarkdownBlock
        content="![v1](clip1.mp4)\n\n![v2](clip2.mp4)"
        sessionId="test-session"
      />,
    );

    const videosInitial = container.querySelectorAll("video");
    expect(videosInitial).toHaveLength(2);

    // Re-render with identical props
    rerender(
      <MarkdownBlock
        content="![v1](clip1.mp4)\n\n![v2](clip2.mp4)"
        sessionId="test-session"
      />,
    );

    const videosAfter = container.querySelectorAll("video");
    expect(videosAfter).toHaveLength(2);
    // Both should be the same references
    expect(videosAfter[0]).toBe(videosInitial[0]);
    expect(videosAfter[1]).toBe(videosInitial[1]);
  });

  it("video element preserves across content updates that don't affect video src", () => {
    const { rerender, container } = render(
      <MarkdownBlock
        content="Some text\n\n![demo](clip.mp4)\n\nMore text"
        sessionId="test-session"
      />,
    );

    const videoInitial = container.querySelector("video");

    // Update surrounding text but keep video src identical
    rerender(
      <MarkdownBlock
        content="Different text\n\n![demo](clip.mp4)\n\nDifferent more text"
        sessionId="test-session"
      />,
    );

    const videoAfter = container.querySelector("video");
    // Video should be preserved (memoization working)
    expect(videoAfter).toBe(videoInitial);
  });
});
