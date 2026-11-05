import { describe, expect, it } from "vitest";
import { useAuthStore, type SessionUser } from "@/stores/ui";

const userA: SessionUser = {
  id: "usr_vishv",
  name: "Vishvendra Vadla",
  email: "vishvendra@acmetech.io",
  role: "owner",
  department: "Executive",
  organizationId: "org_acme",
};

const userB: SessionUser = {
  id: "usr_rahul",
  name: "Rahul Kumar",
  email: "rahul.kumar@acmetech.io",
  role: "admin",
  department: "Engineering",
  organizationId: "org_acme",
};

describe("auth store user handling", () => {
  it("exposes the authenticated user after login", () => {
    useAuthStore.getState().login(userA, []);
    expect(useAuthStore.getState().user?.name).toBe("Vishvendra Vadla");
  });

  it("clears the user on logout", () => {
    useAuthStore.getState().logout();
    expect(useAuthStore.getState().user).toBeNull();
  });

  it("switches to the newly authenticated user on re-login", () => {
    useAuthStore.getState().login(userA, []);
    useAuthStore.getState().logout();
    useAuthStore.getState().login(userB, []);
    expect(useAuthStore.getState().user?.name).toBe("Rahul Kumar");
  });
});
