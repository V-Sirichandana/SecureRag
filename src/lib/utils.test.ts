import { describe, expect, it } from "vitest";
import { greetingFor, greetingName } from "@/lib/utils";

describe("greeting helpers", () => {
  it("returns a time-of-day greeting", () => {
    expect(greetingFor(new Date(2026, 10, 5, 9, 0, 0))).toBe("Good morning");
    expect(greetingFor(new Date(2026, 10, 5, 14, 30, 0))).toBe("Good afternoon");
    expect(greetingFor(new Date(2026, 10, 5, 21, 0, 0))).toBe("Good evening");
  });

  it("uses the authenticated user's name in the greeting", () => {
    expect(greetingName("Vishvendra Vadla")).toBe("Vishvendra");
    expect(greetingName("Rahul Kumar")).toBe("Rahul");
  });

  it("falls back when the user has no profile name", () => {
    expect(greetingName(null)).toBe("there");
    expect(greetingName(undefined)).toBe("there");
    expect(greetingName("   ")).toBe("there");
  });
});
