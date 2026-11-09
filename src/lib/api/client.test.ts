import { afterEach, describe, expect, it, vi } from "vitest";

describe("API client mock mode flag (P0-1)", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.resetModules();
  });

  it("defaults to the real backend when NEXT_PUBLIC_USE_MOCKS is not enabled", async () => {
    vi.stubEnv("NEXT_PUBLIC_USE_MOCKS", "");
    const { USE_MOCKS } = await import("@/lib/api/client");
    expect(USE_MOCKS).toBe(false);
  });

  it("enables mocks only when NEXT_PUBLIC_USE_MOCKS=true", async () => {
    vi.stubEnv("NEXT_PUBLIC_USE_MOCKS", "true");
    const { USE_MOCKS } = await import("@/lib/api/client");
    expect(USE_MOCKS).toBe(true);
  });
});
