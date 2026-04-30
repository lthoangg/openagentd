import { describe, it, expect } from "bun:test";
import "@testing-library/jest-dom";
import { render, screen } from "@testing-library/react";
import { MarkdownBlock } from "@/utils/markdown";

describe("MarkdownBlock link handling", () => {
  it("renders link with target blank and rel opener", () => {
    render(<MarkdownBlock content="Check [this](https://example.com) out." />);
    const link = screen.getByRole("link", { name: /this/i });
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
  });

  it("opens external link in new tab", () => {
    render(<MarkdownBlock content="Visit [Google](https://google.com)." />);
    const link = screen.getByRole("link", { name: /google/i });
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
  });

  it("renders multiple links with correct attributes", () => {
    render(
      <MarkdownBlock
        content="See [link1](https://a.com) and [link2](https://b.com)."
      />
    );
    const links = screen.getAllByRole("link");
    expect(links).toHaveLength(2);
    for (const link of links) {
      expect(link).toHaveAttribute("target", "_blank");
      expect(link).toHaveAttribute("rel", "noopener noreferrer");
    }
  });

  it("renders link with title attribute", () => {
    render(
      <MarkdownBlock
        content='[Click me](https://example.com "Example Site")'
      />
    );
    const link = screen.getByRole("link", { name: /click me/i });
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
    expect(link).toHaveAttribute("title", "Example Site");
  });

  it("does not break other markdown content", () => {
    render(
      <MarkdownBlock
        content="# Hello\n\nThis is a [link](https://example.com) and some **bold** text."
      />
    );
    expect(screen.getByRole("heading", { name: /hello/i })).toBeInTheDocument();
    expect(screen.getByRole("link")).toHaveAttribute("target", "_blank");
  });
});
