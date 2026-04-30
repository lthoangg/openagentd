import { describe, it, expect, afterEach } from "bun:test";
import "@testing-library/jest-dom";
import { render, screen, cleanup } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ToolCall } from "@/components/ToolCall";

afterEach(() => cleanup());

describe("ToolCall generate_video display", () => {
  it("shows 'Filming <filename>' header when filename is provided", () => {
    const args = JSON.stringify({
      prompt: "Create a video of a spinning cube",
      filename: "cube_spin",
    });
    render(<ToolCall name="generate_video" args={args} done={true} />);

    // Header should show "Filming cube_spin.mp4"
    expect(screen.getByText(/Filming/i)).toBeInTheDocument();
    expect(screen.getByText(/cube_spin\.mp4/i)).toBeInTheDocument();
  });

  it("shows 'Filming a video…' when filename is not provided", () => {
    const args = JSON.stringify({
      prompt: "Create a video",
    });
    render(<ToolCall name="generate_video" args={args} done={true} />);

    expect(screen.getByText(/Filming a video/i)).toBeInTheDocument();
  });

  it("sanitizes filename by removing extension and adding .mp4", () => {
    const args = JSON.stringify({
      prompt: "Create a video",
      filename: "my_video.avi",
    });
    render(<ToolCall name="generate_video" args={args} done={true} />);

    // Should show "my_video.mp4" not "my_video.avi"
    expect(screen.getByText(/my_video\.mp4/i)).toBeInTheDocument();
  });

  it("displays first_frame input when present", async () => {
    const user = userEvent.setup();
    const args = JSON.stringify({
      prompt: "Create a video",
      filename: "video",
      images: ["frame1.png", "frame2.png"],
    });
    render(<ToolCall name="generate_video" args={args} done={true} />);

    // Expand to see args
    const button = screen.getByRole("button");
    await user.click(button);

    expect(screen.getByText(/first_frame/i)).toBeInTheDocument();
    expect(screen.getByText(/frame1\.png/i)).toBeInTheDocument();
  });

  it("displays last_frame input when present", async () => {
    const user = userEvent.setup();
    const args = JSON.stringify({
      prompt: "Create a video",
      filename: "video",
      last_frame: "final_frame.png",
    });
    render(<ToolCall name="generate_video" args={args} done={true} />);

    const button = screen.getByRole("button");
    await user.click(button);

    expect(screen.getByText(/last_frame/i)).toBeInTheDocument();
    expect(screen.getByText(/final_frame\.png/i)).toBeInTheDocument();
  });

  it("displays reference_images input when present", async () => {
    const user = userEvent.setup();
    const args = JSON.stringify({
      prompt: "Create a video",
      filename: "video",
      reference_images: ["ref1.png", "ref2.png"],
    });
    render(<ToolCall name="generate_video" args={args} done={true} />);

    const button = screen.getByRole("button");
    await user.click(button);

    expect(screen.getByText(/references/i)).toBeInTheDocument();
    expect(screen.getByText(/ref1\.png/i)).toBeInTheDocument();
  });

  it("displays all inputs together", async () => {
    const user = userEvent.setup();
    const args = JSON.stringify({
      prompt: "Create a smooth animation",
      filename: "animation",
      images: ["start.png"],
      last_frame: "end.png",
      reference_images: ["style.png"],
    });
    render(<ToolCall name="generate_video" args={args} done={true} />);

    const button = screen.getByRole("button");
    await user.click(button);

    expect(screen.getByText(/first_frame/i)).toBeInTheDocument();
    expect(screen.getByText(/last_frame/i)).toBeInTheDocument();
    expect(screen.getByText(/references/i)).toBeInTheDocument();
    expect(screen.getByText(/Create a smooth animation/i)).toBeInTheDocument();
  });

  it("suppresses result display (suppressResult: true)", async () => {
    const user = userEvent.setup();
    const args = JSON.stringify({
      prompt: "Create a video",
      filename: "video",
    });
    const result = "![video](output/video.mp4)";

    render(
      <ToolCall
        name="generate_video"
        args={args}
        done={true}
        result={result}
      />,
    );

    // Expand to see details
    const button = screen.getByRole("button");
    await user.click(button);

    // Result section should NOT be present (suppressResult: true)
    expect(screen.queryByText(/^result$/i)).toBeNull();
    // The markdown result should not appear
    expect(screen.queryByText(/output\/video\.mp4/i)).toBeNull();
  });

  it("renders without crashing when pending (no args, no done)", () => {
    render(<ToolCall name="generate_video" />);

    // When no args, shows tool name instead of custom header
    expect(screen.getByText(/generate_video/i)).toBeInTheDocument();
    expect(screen.getByText(/pending/i)).toBeInTheDocument();
  });

  it("renders without crashing when running (args, no done)", () => {
    const args = JSON.stringify({
      prompt: "Create a video",
      filename: "video",
    });
    render(<ToolCall name="generate_video" args={args} />);

    expect(screen.getByText(/Filming/i)).toBeInTheDocument();
    // Should not show "pending" when args are present
    expect(screen.queryByText(/pending/i)).toBeNull();
  });

  it("shows done status when done=true", () => {
    const args = JSON.stringify({
      prompt: "Create a video",
      filename: "video",
    });
    render(<ToolCall name="generate_video" args={args} done={true} />);

    // Status dot should be present (done state)
    const statusDot = document.querySelector("span.inline-block.h-1\\.5");
    expect(statusDot).not.toBeNull();
  });

  it("shows running status when done=false", () => {
    const args = JSON.stringify({
      prompt: "Create a video",
      filename: "video",
    });
    render(<ToolCall name="generate_video" args={args} done={false} />);

    // Status dot should be present (running state)
    const statusDot = document.querySelector("span.inline-block.h-1\\.5");
    expect(statusDot).not.toBeNull();
  });

  it("handles empty images array gracefully", async () => {
    const user = userEvent.setup();
    const args = JSON.stringify({
      prompt: "Create a video",
      filename: "video",
      images: [],
    });
    render(<ToolCall name="generate_video" args={args} done={true} />);

    const button = screen.getByRole("button");
    await user.click(button);

    // Should not show "first_frame:" line if array is empty
    expect(screen.queryByText(/first_frame:/)).toBeNull();
  });

  it("handles empty reference_images array gracefully", async () => {
    const user = userEvent.setup();
    const args = JSON.stringify({
      prompt: "Create a video",
      filename: "video",
      reference_images: [],
    });
    render(<ToolCall name="generate_video" args={args} done={true} />);

    const button = screen.getByRole("button");
    await user.click(button);

    // Should not show "references:" line if array is empty
    expect(screen.queryByText(/references:/)).toBeNull();
  });

  it("handles missing optional fields", async () => {
    const user = userEvent.setup();
    const args = JSON.stringify({
      prompt: "Create a video",
      filename: "video",
    });
    render(<ToolCall name="generate_video" args={args} done={true} />);

    const button = screen.getByRole("button");
    await user.click(button);

    // Should only show prompt, no first_frame/last_frame/references
    expect(screen.getByText(/Create a video/i)).toBeInTheDocument();
    expect(screen.queryByText(/first_frame/i)).toBeNull();
    expect(screen.queryByText(/last_frame/i)).toBeNull();
    expect(screen.queryByText(/references/i)).toBeNull();
  });

  it("displays filename with special characters correctly", () => {
    const args = JSON.stringify({
      prompt: "Create a video",
      filename: "my-video_v2",
    });
    render(<ToolCall name="generate_video" args={args} done={true} />);

    expect(screen.getByText(/my-video_v2\.mp4/i)).toBeInTheDocument();
  });

  it("is expandable when it has args", async () => {
    const user = userEvent.setup();
    const args = JSON.stringify({
      prompt: "Create a video",
      filename: "video",
    });
    render(<ToolCall name="generate_video" args={args} done={true} />);

    const button = screen.getByRole("button");
    expect(button).toHaveAttribute("aria-expanded", "false");

    await user.click(button);
    expect(button).toHaveAttribute("aria-expanded", "true");
  });

  it("button is clickable when expandable", async () => {
    const user = userEvent.setup();
    const args = JSON.stringify({
      prompt: "Create a video",
      filename: "video",
    });
    render(<ToolCall name="generate_video" args={args} done={true} />);

    const button = screen.getByRole("button");
    // Button should be clickable (not disabled)
    expect(button).not.toHaveAttribute("disabled");

    // Should be able to click to expand
    await user.click(button);
    expect(button).toHaveAttribute("aria-expanded", "true");
  });
});
