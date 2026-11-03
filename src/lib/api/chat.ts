import { USE_MOCKS, request } from "./client";
import {
  answerFor,
  conversations as mockConversations,
} from "@/lib/mock/conversations";
import { latency } from "@/lib/mock/utils";
import type { ChatMessage, Conversation } from "@/lib/types";

export async function getConversations(): Promise<Conversation[]> {
  if (USE_MOCKS) {
    await latency(250, 550);
    return [...mockConversations].sort(
      (a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime(),
    );
  }
  return request<Conversation[]>("/chat/conversations");
}

export async function getConversation(id: string): Promise<Conversation> {
  if (USE_MOCKS) {
    await latency(200, 450);
    const found = mockConversations.find((item) => item.id === id);
    if (!found) throw new Error("Conversation not found");
    return found;
  }
  return request<Conversation>(`/chat/conversations/${id}`);
}

export async function createConversation(title: string, collectionId: string | null): Promise<Conversation> {
  if (USE_MOCKS) {
    await latency(250, 500);
    const conversation: Conversation = {
      id: `conv_${Math.random().toString(36).slice(2, 9)}`,
      title,
      collectionId,
      updatedAt: new Date().toISOString(),
      messageCount: 0,
      messages: [],
    };
    mockConversations.unshift(conversation);
    return conversation;
  }
  return request<Conversation>("/chat/conversations", {
    method: "POST",
    body: { title, collectionId },
  });
}

export async function deleteConversation(id: string): Promise<void> {
  if (USE_MOCKS) {
    await latency(200, 400);
    const index = mockConversations.findIndex((item) => item.id === id);
    if (index >= 0) mockConversations.splice(index, 1);
    return;
  }
  await request(`/chat/conversations/${id}`, { method: "DELETE" });
}

export interface StreamHandlers {
  onToken: (token: string) => void;
  onCitations: (citations: ChatMessage["citations"]) => void;
  onMeta: (meta: { model: string; latencyMs: number; tokenCount: number }) => void;
  signal?: AbortSignal;
}

export interface ChatResult {
  id?: string;
  content: string;
  citations: ChatMessage["citations"];
  model: string;
  latencyMs: number;
  tokenCount: number;
}

/** The optimistic messages the UI already rendered while the answer loads. */
export interface PendingMessages {
  user: ChatMessage;
  assistant: ChatMessage;
}

async function feedTokens(content: string, handlers: StreamHandlers): Promise<string> {
  const chunks = content.match(/\S+\s*/g) ?? [];
  let produced = "";
  for (const chunk of chunks) {
    if (handlers.signal?.aborted) {
      handlers.onToken("");
      break;
    }
    produced += chunk;
    handlers.onToken(chunk);
    await new Promise((resolve) => setTimeout(resolve, 12 + Math.random() * 26));
  }
  return produced;
}

function persistMockDraft(
  conversationId: string,
  pending: PendingMessages,
  result: ChatResult,
): void {
  const conversation = mockConversations.find((item) => item.id === conversationId);
  if (!conversation) return;
  conversation.messages.push(pending.user, { ...pending.assistant, ...result });
  conversation.messageCount = conversation.messages.length;
  conversation.updatedAt = new Date().toISOString();
  if (conversation.title === "New conversation") {
    conversation.title = pending.user.content.slice(0, 48);
  }
}

/**
 * Delivers an answer to the UI and owns persistence in both modes.
 *
 * Mock mode simulates a token stream, then stores the pending messages in the
 * in-memory conversation. Real mode POSTs the question to the backend, which
 * retrieves, generates and persists both messages server-side (citations are
 * rebuilt from retrieved context there — the provider never supplies them);
 * the backend already returned the complete grounded answer, so it is rendered
 * as-is until a real SSE stream endpoint exists.
 */
export async function streamAnswer(
  question: string,
  handlers: StreamHandlers,
  conversationId: string,
  pending: PendingMessages,
): Promise<ChatResult> {
  if (USE_MOCKS) {
    const { content, citations } = answerFor(question);
    const startedAt = performance.now();
    const latencyMs = 700 + Math.round(Math.random() * 600);

    await latency(latencyMs, latencyMs + 120);
    if (handlers.signal?.aborted) throw new DOMException("Aborted", "AbortError");

    handlers.onCitations(citations);
    handlers.onMeta({ model: "gpt-4o-mini", latencyMs, tokenCount: 0 });

    const produced = await feedTokens(content, handlers);
    const result: ChatResult = {
      id: pending.assistant.id,
      content: produced || content,
      citations,
      model: "gpt-4o-mini",
      latencyMs: Math.round(performance.now() - startedAt),
      tokenCount: Math.round(produced.length / 4),
    };
    persistMockDraft(conversationId, pending, result);
    return result;
  }

  const saved = await request<ChatMessage>(`/chat/conversations/${conversationId}/messages`, {
    method: "POST",
    body: { role: "user", content: question },
    signal: handlers.signal,
  });

  const content = saved.content ?? "";
  const citations = saved.citations ?? [];
  const model = saved.model ?? "assistant";
  const latencyMs = saved.latencyMs ?? 0;
  const tokenCount = saved.tokenCount ?? 0;

  handlers.onCitations(citations);
  handlers.onMeta({ model, latencyMs, tokenCount });

  // No SSE endpoint exists yet: the backend already returned the complete
  // grounded answer, so render it as-is instead of simulating token streaming.
  return {
    id: saved.id,
    content,
    citations,
    model,
    latencyMs,
    tokenCount,
  };
}

export async function submitFeedback(messageId: string, feedback: "up" | "down"): Promise<void> {
  if (USE_MOCKS) {
    for (const conversation of mockConversations) {
      const message = conversation.messages.find((item) => item.id === messageId);
      if (message) message.feedback = feedback;
    }
    await latency(150, 350);
    return;
  }
  await request(`/chat/messages/${messageId}/feedback`, { method: "POST", body: { feedback } });
}
