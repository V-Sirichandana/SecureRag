"use client";

import * as React from "react";
import { toast } from "sonner";
import {
  Bot,
  Check,
  Copy,
  RefreshCw,
  Share2,
  ThumbsDown,
  ThumbsUp,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn, formatTime, initials } from "@/lib/utils";
import { Markdown } from "@/components/chat/markdown";
import { CitationChip, CitationSource } from "@/components/chat/citation";
import type { ChatMessage, Citation } from "@/lib/types";

interface MessageProps {
  message: ChatMessage;
  streaming?: boolean;
  activeCitation?: number | null;
  onCitationClick: (citation: Citation) => void;
  onFeedback?: (id: string, feedback: "up" | "down") => void;
  onRegenerate?: (id: string) => void;
  suggestedFollowUps?: string[];
  onFollowUp?: (question: string) => void;
}

export function Message({
  message,
  streaming,
  activeCitation,
  onCitationClick,
  onFeedback,
  onRegenerate,
  suggestedFollowUps,
  onFollowUp,
}: MessageProps) {
  const [copied, setCopied] = React.useState(false);

  const copy = async () => {
    await navigator.clipboard.writeText(message.content);
    setCopied(true);
    toast.success("Answer copied to clipboard.");
    setTimeout(() => setCopied(false), 1600);
  };

  if (message.role === "user") {
    return (
      <div className="flex justify-end animate-fade-in">
        <div className="max-w-[85%] rounded-2xl rounded-br-md bg-primary px-4 py-2.5 text-sm leading-relaxed text-primary-foreground sm:max-w-[70%]">
          {message.content}
          <p className="mt-1 text-right text-[10px] text-primary-foreground/70">
            {formatTime(message.createdAt)}
          </p>
        </div>
      </div>
    );
  }

  const citations = message.citations ?? [];

  return (
    <div className="flex gap-3 animate-fade-in">
      <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary">
        <Bot className="h-4 w-4" />
      </span>

      <div className="min-w-0 flex-1">
        <div className="mb-1 flex items-center gap-2 text-xs text-muted-foreground">
          <span className="font-medium text-foreground">Knowledge Assistant</span>
          {message.model ? (
            <span className="rounded border px-1.5 py-0.5 font-mono text-[10px]">
              {message.model}
            </span>
          ) : null}
          {message.latencyMs ? <span>{message.latencyMs} ms</span> : null}
          <span>{formatTime(message.createdAt)}</span>
        </div>

        <Markdown
          content={message.content}
          className="text-foreground"
          citationRenderer={(index) => (
            <CitationChip
              index={index}
              active={activeCitation === index}
              onClick={() => {
                const citation = citations.find((item) => item.index === index);
                if (citation) onCitationClick(citation);
              }}
            />
          )}
        />
        {streaming ? (
          <span
            className="inline-block h-4 w-2 translate-y-0.5 animate-caret-blink bg-primary"
            aria-hidden="true"
          />
        ) : null}

        {citations.length > 0 ? (
          <div className="mt-4 rounded-xl border bg-muted/30 p-3">
            <p className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              <span className="h-px flex-1 bg-border" />
              Sources
              <span className="h-px flex-1 bg-border" />
            </p>
            <div className="space-y-2">
              {citations.map((citation) => (
                <CitationSource
                  key={citation.index}
                  index={citation.index}
                  documentName={citation.documentName}
                  collectionName={citation.collectionName}
                  pageNumber={citation.pageNumber}
                  quote={citation.quote}
                  active={activeCitation === citation.index}
                  onClick={() => onCitationClick(citation)}
                />
              ))}
            </div>
          </div>
        ) : null}

        {!streaming ? (
          <div className="mt-2.5 flex flex-wrap items-center gap-1">
            <ActionButton
              label={copied ? "Copied" : "Copy answer"}
              onClick={() => void copy()}
            >
              {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
            </ActionButton>
            <ActionButton label="Regenerate" onClick={() => onRegenerate?.(message.id)}>
              <RefreshCw className="h-3.5 w-3.5" />
            </ActionButton>
            <ActionButton
              label="Helpful"
              active={message.feedback === "up"}
              onClick={() => onFeedback?.(message.id, "up")}
            >
              <ThumbsUp className="h-3.5 w-3.5" />
            </ActionButton>
            <ActionButton
              label="Not helpful"
              active={message.feedback === "down"}
              onClick={() => onFeedback?.(message.id, "down")}
            >
              <ThumbsDown className="h-3.5 w-3.5" />
            </ActionButton>
            <ActionButton
              label="Share"
              onClick={() => toast.success("Secure share link copied.")}
            >
              <Share2 className="h-3.5 w-3.5" />
            </ActionButton>
          </div>
        ) : null}

        {suggestedFollowUps?.length ? (
          <div className="mt-4 flex flex-wrap gap-2">
            {suggestedFollowUps.map((question) => (
              <button
                key={question}
                type="button"
                onClick={() => onFollowUp?.(question)}
                className="rounded-full border bg-card px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:border-primary/50 hover:text-foreground"
              >
                {question}
              </button>
            ))}
          </div>
        ) : null}
      </div>
    </div>
  );
}

function ActionButton({
  label,
  onClick,
  active,
  children,
}: {
  label: string;
  onClick: () => void;
  active?: boolean;
  children: React.ReactNode;
}) {
  return (
    <Button
      variant="ghost"
      size="sm"
      onClick={onClick}
      aria-label={label}
      className={cn(
        "h-7 gap-1.5 px-2 text-xs text-muted-foreground hover:text-foreground",
        active && "bg-primary/10 text-primary hover:bg-primary/15 hover:text-primary",
      )}
    >
      {children}
      <span className="hidden sm:inline">{label}</span>
    </Button>
  );
}

export function StreamingIndicator() {
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
      <span className="flex gap-1">
        <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-primary [animation-delay:-0.2s]" />
        <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-primary [animation-delay:-0.1s]" />
        <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-primary" />
      </span>
      Retrieving passages…
    </span>
  );
}

export function UserAvatar({ name }: { name: string }) {
  return (
    <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-secondary text-xs font-semibold">
      {initials(name)}
    </span>
  );
}
