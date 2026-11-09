"use client";

import * as React from "react";
import { ArrowUp, Paperclip, Square } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

interface MessageInputProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  onStop: () => void;
  generating: boolean;
  disabled?: boolean;
}

export function MessageInput({
  value,
  onChange,
  onSubmit,
  onStop,
  generating,
  disabled,
}: MessageInputProps) {
  const textareaRef = React.useRef<HTMLTextAreaElement>(null);

  const resize = () => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "0px";
    el.style.height = `${Math.min(el.scrollHeight, 180)}px`;
  };

  React.useEffect(resize, [value]);

  return (
    <div className="rounded-2xl border bg-card p-2 shadow-[0_1px_2px_rgba(0,0,0,0.04)] transition-colors focus-within:border-primary/50">
      <Textarea
        ref={textareaRef}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();
            if (!generating && value.trim()) onSubmit();
          }
        }}
        placeholder="Ask your organization's knowledge base…"
        rows={1}
        disabled={disabled}
        aria-label="Message"
        className="min-h-11 resize-none border-0 bg-transparent px-2 py-2 shadow-none focus-visible:ring-0 focus-visible:ring-offset-0"
      />

      <div className="flex items-center justify-between gap-2 px-1 pt-1">
        <div className="flex items-center gap-1.5">
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8 text-muted-foreground"
            aria-label="Attach a file"
            onClick={() => undefined}
          >
            <Paperclip className="h-4 w-4" />
          </Button>
          <span className="hidden text-[11px] text-muted-foreground sm:inline">
            Enter to send · Shift + Enter for a new line
          </span>
        </div>

        {generating ? (
          <Button
            variant="outline"
            size="sm"
            onClick={onStop}
            className="h-8 gap-1.5"
            aria-label="Stop generation"
          >
            <Square className="h-3.5 w-3.5" />
            Stop
          </Button>
        ) : (
          <Button
            size="sm"
            onClick={onSubmit}
            disabled={disabled || !value.trim()}
            className={cn("h-8 w-8 p-0 sm:w-auto sm:px-3")}
            aria-label="Send message"
          >
            <ArrowUp className="h-4 w-4 sm:mr-1" />
            <span className="hidden sm:inline">Send</span>
          </Button>
        )}
      </div>
    </div>
  );
}
