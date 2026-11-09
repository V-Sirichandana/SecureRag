"use client";

import { Plus, Trash2, MessagesSquare } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn, timeAgo } from "@/lib/utils";
import type { Conversation } from "@/lib/types";

interface ConversationListProps {
  conversations: Conversation[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
  onDelete: (id: string) => void;
}

export function ConversationList({
  conversations,
  activeId,
  onSelect,
  onNew,
  onDelete,
}: ConversationListProps) {
  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="border-b p-3">
        <Button className="w-full justify-start gap-2" variant="outline" onClick={onNew}>
          <Plus className="h-4 w-4" />
          New conversation
        </Button>
      </div>

      <ScrollArea className="min-h-0 flex-1 px-2 py-3">
        <p className="mb-2 px-2 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground/80">
          Conversation history
        </p>

        {conversations.length === 0 ? (
          <p className="px-2 py-6 text-center text-xs text-muted-foreground">
            No conversations yet. Ask your first question below.
          </p>
        ) : (
          <ul className="space-y-1">
            {conversations.map((conversation) => (
              <li key={conversation.id} className="group relative">
                <button
                  type="button"
                  onClick={() => onSelect(conversation.id)}
                  className={cn(
                    "w-full rounded-lg px-2.5 py-2 pr-8 text-left transition-colors",
                    activeId === conversation.id
                      ? "bg-primary/10 text-foreground"
                      : "hover:bg-muted",
                  )}
                  aria-current={activeId === conversation.id ? "true" : undefined}
                >
                  <span className="flex items-start gap-2">
                    <MessagesSquare
                      className={cn(
                        "mt-0.5 h-3.5 w-3.5 shrink-0",
                        activeId === conversation.id ? "text-primary" : "text-muted-foreground",
                      )}
                    />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm font-medium">
                        {conversation.title}
                      </span>
                      <span className="mt-0.5 block text-xs text-muted-foreground">
                        {timeAgo(conversation.updatedAt)} · {conversation.messageCount} messages
                      </span>
                    </span>
                  </span>
                </button>

                <button
                  type="button"
                  onClick={() => onDelete(conversation.id)}
                  aria-label={`Delete conversation ${conversation.title}`}
                  className="absolute right-1.5 top-2 hidden h-6 w-6 items-center justify-center rounded-md text-muted-foreground opacity-0 transition-opacity hover:bg-destructive/10 hover:text-destructive focus-visible:opacity-100 group-hover:opacity-100 sm:flex"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </li>
            ))}
          </ul>
        )}
      </ScrollArea>
    </div>
  );
}
