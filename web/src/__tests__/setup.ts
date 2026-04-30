// Global test setup — registers Happy DOM so React components can render.
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { afterEach } from "bun:test";

GlobalRegistrator.register();

// Clean up DOM after each test to prevent test interference
afterEach(() => {
  // Clear all children from body
  if (typeof document !== "undefined" && document.body) {
    document.body.innerHTML = "";
  }
});
