"use client";

import * as React from "react";
import { toast } from "sonner";
import {
  Eraser,
  Menu,
  PanelLeftClose,
  Sparkles,
  SquarePen,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Sheet, SheetContent } from "@/components/ui/sheet";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/common/skeletons";
import { ConversationList } from "@/components/chat/conversation-list";
import { Message, StreamingIndicator } from "@/components/chat/message";
import { MessageInput } from "@/components/chat/message-input";
import { SourcePreview } from "@/components/chat/source-preview";
import {
  createConversation,
  streamAnswer,
  submitFeedback,
} from "@/lib/api/chat";
import { ApiError } from "@/lib/api/client";
import { useCollections, useConversations, useDeleteConversation } from "@/lib/queries";
import { suggestedQuestions as mockSuggestedQuestions } from "@/lib/mock/conversations";
import { USE_MOCKS } from "@/lib/api/client";
import type { ChatMessage, Citation, Conversation } from "@/lib/types";

const suggestedQuestions = USE_MOCKS ? mockSuggestedQuestions : [];

const followUps: Record<string, string[]> = {
  default: [
    "What exceptions apply?",
    "Who approves this?",
    "Where is this documented?",
  ],
  security: ["What is the escalation path?", "How often are reviews run?", "Show the data classes"],
  finance: ["Break this down by cost centre", "What is the runway?", "Compare to last quarter"],
};

function pickFollowUps(content: string): string[] {
  if (/security|access|mfa|incident/i.test(content)) return followUps.security;
  if (/expense|cash|budget|financ/i.test(content)) return followUps.finance;
  return followUps.default;
}

function newId(prefix: string) {
  return `${prefix}_${Date.now().toString(36)}${Math.random().toString(36).slice(2, 7)}`;
}

export function ChatWindow() {
  const conversationsQuery = useConversations();
  const collections = useCollections();
  const deleteConversation = useDeleteConversation();

  const [conversations, setConversations] = React.useState<Conversation[] | null>(null);
  const [activeId, setActiveId] = React.useState<string | null>(null);
  const [collectionId, setCollectionId] = React.useState("all");
  const [input, setInput] = React.useState("");
  const [generating, setGenerating] = React.useState(false);
  const [activeCitation, setActiveCitation] = React.useState<Citation | null>(null);
  const [mobileListOpen, setMobileListOpen] = React.useState(false);

  const abortRef = React.useRef<AbortController | null>(null);
  const scrollRef = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    if (conversations === null && conversationsQuery.data) {
      setConversations(conversationsQuery.data);
      setActiveId(conversationsQuery.data[0]?.id ?? null);
    }
  }, [conversations, conversationsQuery.data]);

  React.useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  });

  const active = conversations?.find((item) => item.id === activeId) ?? null;
  const messages = active?.messages ?? [];

  const patchConversation = (id: string, updater: (conversation: Conversation) => Conversation) =>
    setConversations((current) =>
      current ? current.map((item) => (item.id === id ? updater(item) : item)) : current,
    );

  const patchMessage = (conversationId: string, messageId: string, patch: Partial<ChatMessage>) =>
    patchConversation(conversationId, (conversation) => ({
      ...conversation,
      messages: conversation.messages.map((message) =>
        message.id === messageId ? { ...message, ...patch } : message,
      ),
      updatedAt: new Date().toISOString(),
    }));

  const ensureConversation = async (): Promise<string> => {
    if (activeId) return activeId;
    const created = await createConversation(
      "New conversation",
      collectionId === "all" ? null : collectionId,
    );
    setConversations((current) => [created, ...(current ?? [])]);
    setActiveId(created.id);
    return created.id;
  };

  const send = async (raw: string) => {
    const question = raw.trim();
    if (!question || generating) return;

    setGenerating(true);
    const controller = new AbortController();
    abortRef.current = controller;

    let conversationId: string | null = null;
    let assistantId: string | null = null;

    try {
      conversationId = await ensureConversation();
      const userMessage: ChatMessage = {
        id: newId("msg"),
        role: "user",
        content: question,
        createdAt: new Date().toISOString(),
      };
      assistantId = newId("msg");
      const assistantMessage: ChatMessage = {
        id: assistantId,
        role: "assistant",
        content: "",
        citations: [],
        createdAt: new Date().toISOString(),
      };

      setConversations((current) =>
        (current ?? []).map((item) =>
          item.id === conversationId
            ? {
                ...item,
                title:
                  item.messages.length === 0 && item.title === "New conversation"
                    ? question.slice(0, 48)
                    : item.title,
                messageCount: item.messages.length + 2,
                updatedAt: new Date().toISOString(),
                messages: [...item.messages, userMessage, assistantMessage],
              }
            : item,
        ),
      );
      setInput("");

      const result = await streamAnswer(
        question,
        {
          signal: controller.signal,
          onToken: (token) =>
            setConversations((current) =>
              (current ?? []).map((item) =>
                item.id === conversationId
                  ? {
                      ...item,
                      messages: item.messages.map((message) =>
                        message.id === assistantId
                          ? { ...message, content: message.content + token }
                          : message,
                      ),
                    }
                  : item,
              ),
            ),
          onCitations: (citations) =>
            conversationId && assistantId && patchMessage(conversationId, assistantId, { citations }),
          onMeta: (meta) =>
            conversationId && assistantId && patchMessage(conversationId, assistantId, meta),
        },
        conversationId,
        { user: userMessage, assistant: assistantMessage },
      );

      if (conversationId && assistantId) {
        patchMessage(conversationId, assistantId, {
          id: result.id ?? assistantId,
          content: result.content,
          citations: result.citations,
          model: result.model,
          latencyMs: result.latencyMs,
          tokenCount: result.tokenCount,
        });
      }
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") {
        toast.info("Generation stopped.");
      } else {
        if (conversationId && assistantId) {
          patchMessage(conversationId, assistantId, {
            content: "Something went wrong while generating an answer. Please try again.",
          });
        }
        toast.error(
          error instanceof ApiError ? error.message : "Failed to generate an answer.",
        );
      }
    } finally {
      setGenerating(false);
      abortRef.current = null;
    }
  };

  const stop = () => abortRef.current?.abort();

  const regenerate = (messageId: string) => {
    const index = messages.findIndex((message) => message.id === messageId);
    const previousUser = [...messages.slice(0, index)].reverse().find((m) => m.role === "user");
    if (!previousUser) return;
    setConversations((current) =>
      (current ?? []).map((item) =>
        item.id === activeId
          ? {
              ...item,
              messages: item.messages.filter(
                (message) => message.id !== messageId && message.id !== previousUser.id,
              ),
              messageCount: Math.max(item.messageCount - 2, 0),
            }
          : item,
      ),
    );
    void send(previousUser.content);
  };

  const handleFeedback = (messageId: string, feedback: "up" | "down") => {
    if (activeId) patchMessage(activeId, messageId, { feedback });
    void submitFeedback(messageId, feedback);
    toast.success(feedback === "up" ? "Thanks for the feedback." : "Feedback recorded.");
  };

  const startNewConversation = () => {
    setActiveId(null);
    setInput("");
    setActiveCitation(null);
    setMobileListOpen(false);
  };

  const removeConversation = (id: string) => {
    deleteConversation.mutate(id, {
      onSuccess: () => {
        setConversations((current) => (current ?? []).filter((item) => item.id !== id));
        if (activeId === id) setActiveId(null);
      },
    });
  };

  const list = (
    <ConversationList
      conversations={conversations ?? []}
      activeId={activeId}
      onSelect={(id) => {
        setActiveId(id);
        setMobileListOpen(false);
      }}
      onNew={startNewConversation}
      onDelete={removeConversation}
    />
  );

  const lastAssistant = [...messages].reverse().find((message) => message.role === "assistant");
  const showFollowUps =
    Boolean(lastAssistant) &&
    !generating &&
    lastAssistant?.id === messages[messages.length - 1]?.id &&
    (lastAssistant?.citations?.length ?? 0) > 0;

  return (
    <div className="flex h-[calc(100vh-3.5rem)] min-h-[520px]">
      <aside className="hidden w-72 shrink-0 border-r bg-sidebar lg:block">{list}</aside>

      <Sheet open={mobileListOpen} onOpenChange={setMobileListOpen}>
        <SheetContent side="left" className="w-72 p-0">
          {list}
        </SheetContent>
      </Sheet>

      <section className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center justify-between gap-3 border-b px-4 sm:px-6">
          <div className="flex min-w-0 items-center gap-2">
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8 lg:hidden"
              onClick={() => setMobileListOpen(true)}
              aria-label="Open conversation history"
            >
              <Menu className="h-4 w-4" />
            </Button>
            <span className="flex h-7 w-7 items-center justify-center rounded-md bg-primary/10 text-primary">
              <Sparkles className="h-4 w-4" />
            </span>
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold leading-tight">
                Knowledge Assistant
              </p>
              <p className="truncate text-xs text-muted-foreground">
                Answers grounded in your organization&apos;s documents
              </p>
            </div>
          </div>

          <div className="flex shrink-0 items-center gap-2">
            <Badge variant="outline" className="hidden text-muted-foreground md:inline-flex">
              Citations enabled
            </Badge>
            <Select value={collectionId} onValueChange={setCollectionId}>
              <SelectTrigger className="h-8 w-[150px] text-xs" aria-label="Filter by collection">
                <SelectValue placeholder="Collection" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All collections</SelectItem>
                {collections.data?.map((collection) => (
                  <SelectItem key={collection.id} value={collection.id}>
                    {collection.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8 text-muted-foreground"
              onClick={() => {
                if (activeId) removeConversation(activeId);
                else startNewConversation();
              }}
              aria-label="Clear conversation"
            >
              <Eraser className="h-4 w-4" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="hidden h-8 w-8 text-muted-foreground sm:inline-flex"
              onClick={startNewConversation}
              aria-label="New conversation"
            >
              <SquarePen className="h-4 w-4" />
            </Button>
          </div>
        </header>

        <div ref={scrollRef} className="scrollbar-thin min-h-0 flex-1 overflow-y-auto">
          <div className="mx-auto w-full max-w-3xl space-y-6 px-4 py-6 sm:px-6">
            {conversations === null ? (
              <div className="space-y-4">
                <Skeleton className="h-20 w-3/4 self-end" />
                <Skeleton className="h-28 w-full" />
              </div>
            ) : messages.length === 0 ? (
              <EmptyChat onPick={(question) => void send(question)} />
            ) : (
              messages.map((message) => (
                <Message
                  key={message.id}
                  message={message}
                  streaming={
                    generating && message.id === messages[messages.length - 1]?.id
                  }
                  activeCitation={
                    activeCitation && message.citations?.some((c) => c.index === activeCitation.index)
                      ? activeCitation.index
                      : null
                  }
                  onCitationClick={(citation) => setActiveCitation(citation)}
                  onFeedback={handleFeedback}
                  onRegenerate={regenerate}
                  suggestedFollowUps={
                    showFollowUps && message.id === lastAssistant?.id
                      ? pickFollowUps(message.content)
                      : undefined
                  }
                  onFollowUp={(question) => void send(question)}
                />
              ))
            )}

            {generating && messages[messages.length - 1]?.content === "" ? (
              <StreamingIndicator />
            ) : null}
          </div>
        </div>

        <div className="shrink-0 border-t bg-background/60 px-4 py-3 backdrop-blur sm:px-6">
          <div className="mx-auto w-full max-w-3xl">
            <MessageInput
              value={input}
              onChange={setInput}
              onSubmit={() => void send(input)}
              onStop={stop}
              generating={generating}
              disabled={conversations === null}
            />
            <p className="mt-2 text-center text-[11px] text-muted-foreground">
              Responses are grounded in your organization&apos;s documents. Verify critical details
              against the cited sources.
            </p>
          </div>
        </div>
      </section>

      <SourcePreview citation={activeCitation} onOpenChange={(open) => !open && setActiveCitation(null)} />
    </div>
  );
}

function EmptyChat({ onPick }: { onPick: (question: string) => void }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center animate-fade-in">
      <span className="mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-primary/10 text-primary">
        <Sparkles className="h-6 w-6" />
      </span>
      <h2 className="text-lg font-semibold tracking-tight">Ask your knowledge base</h2>
      <p className="mt-1.5 max-w-md text-sm text-muted-foreground">
        Answers are generated only from documents your account can access, with citations back to
        the exact page.
      </p>

      <div className="mt-6 grid w-full max-w-lg gap-2 sm:grid-cols-2">
        {suggestedQuestions.map((question) => (
          <button
            key={question}
            type="button"
            onClick={() => onPick(question)}
            className="rounded-lg border bg-card p-3 text-left text-sm transition-colors hover:border-primary/50 hover:bg-muted/50"
          >
            {question}
          </button>
        ))}
      </div>

      <div className="mt-6 flex items-center gap-2 text-xs text-muted-foreground">
        <PanelLeftClose className="hidden h-3.5 w-3.5 lg:block" />
        <span>Pick a past conversation on the left, or start fresh above.</span>
      </div>
    </div>
  );
}
