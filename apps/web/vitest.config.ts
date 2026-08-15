import { defineConfig } from "vitest/config";

/**
 * Unit lane (gate tests): pure functions only, node environment, no browser.
 *
 * Deliberately separate from vite.config.ts so `vite build` never loads vitest,
 * and so the default `**\/*.spec.ts` glob cannot swallow the Playwright suite in
 * e2e/ — those run in Docker against a live stack and are a different budget.
 */
export default defineConfig({
  test: {
    include: ["src/**/*.test.ts", "src/**/*.test.tsx"],
    environment: "node",
    passWithNoTests: false,
  },
});
