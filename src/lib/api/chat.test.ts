import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ChatMessage, Citation } from "@/lib/types";

const { requestMock } = vi.hoisted(() => ({ requestMock: vi.fn() }));

vi.mock("@/lib/api/client", () => ({
  USE_MOCKS: false,
  request: requestMock,
  ApiError: class extends Error {},
}));

vi.mock("@/lib/mock/conversations", () => ({
  answerFor: vi.fn(),
  conversations: [],
}));

vi.mock("@/lib/mock/utils", () => ({
  latency: vi.fn(),
  DEMO_NOTICE: "Demo data - backend not connected",
}));

import { streamAnswer, type StreamHandlers, type PendingMessages } from "@/lib/api/chat";

describe("chat streamAnswer real backend mode (P0-1)", () => {
  beforeEach(() => {
    requestMock.mockReset();
  });

  it("returns the backend answer and citations without simulating token streaming", async () => {
    const citation: Citation = {
      index: 1,
      documentId: "doc_1",
      documentName: "policy.pdf",
      collectionName: "Policies",
      pageNumber: 1,
      quote: "Grounded text.",
    };
    const saved: ChatMessage = {
      id: "msg_1",
      role: "assistant",
      content: "Grounded answer. [1]",
      citations: [citation],
      createdAt: new Date().toISOString(),
      model: "test-model",
      latencyMs: 12,
      tokenCount: 7,
    };
    requestMock.mockResolvedValue(saved);

    const handlers: StreamHandlers = {
      onToken: vi.fn(),
      onCitations: vi.fn(),
      onMeta: vi.fn(),
      signal: undefined,
    };
    const pending: PendingMessages = {
      user: {
        id: "msg_u",
        role: "user",
        content: "What is the policy?",
        createdAt: new Date().toISOString(),
      },
      assistant: {
        id: "msg_a",
        role: "assistant",
        content: "",
        createdAt: new Date().toISOString(),
      },
    };

    const result = await streamAnswer("What is the policy?", handlers, "conv_1", pending);

    expect(requestMock).toHaveBeenCalledTimes(1);
    expect(requestMock.mock.calls[0]?.[0]).toBe("/chat/conversations/conv_1/messages");
    expect(result.content).toBe("Grounded answer. [1]");
    expect(result.citations).toEqual([citation]);
    expect(handlers.onToken).not.toHaveBeenCalled();
    expect(handlers.onCitations).toHaveBeenCalledWith([citation]);
    expect(handlers.onMeta).toHaveBeenCalledWith({
      model: "test-model",
      latencyMs: 12,
      tokenCount: 7,
    });
  });
});
