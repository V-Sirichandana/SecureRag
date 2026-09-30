"use client";

import * as React from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Check, Copy, Terminal } from "lucide-react";
import { cn } from "@/lib/utils";

function CodeBlock({ className, children }: React.HTMLAttributes<HTMLElement>) {
  const [copied, setCopied] = React.useState(false);
  const match = /language-(\w+)/.exec(className ?? "");
  const code = String(children).replace(/\n$/, "");

  const copy = async () => {
    await navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 1600);
  };

  return (
    <span className="group relative block overflow-hidden rounded-lg border bg-muted/60">
      <span className="flex items-center justify-between border-b bg-muted/80 px-3 py-1.5">
        <span className="inline-flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
          <Terminal className="h-3 w-3" />
          {match ? match[1] : "code"}
        </span>
        <button
          type="button"
          onClick={() => void copy()}
          className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] text-muted-foreground transition-colors hover:bg-background hover:text-foreground"
          aria-label="Copy code"
        >
          {copied ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
          {copied ? "Copied" : "Copy"}
        </button>
      </span>
      <pre className="scrollbar-thin overflow-x-auto p-3.5 text-[12.5px] leading-relaxed">
        <code className={cn("font-mono", match && `language-${match[1]}`)}>{code}</code>
      </pre>
    </span>
  );
}

interface MarkdownProps {
  content: string;
  citationRenderer?: (index: number) => React.ReactNode;
  className?: string;
}

export function Markdown({ content, citationRenderer, className }: MarkdownProps) {
  return (
    <div className={cn("text-sm leading-relaxed", className)}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          code: ({ className: codeClassName, children, ...props }) => {
            const isBlock = /\n/.test(String(children));
            if (isBlock) {
              return <CodeBlock className={codeClassName} {...props} />;
            }
            return (
              <code
                className="rounded border bg-muted px-1.5 py-0.5 font-mono text-[12.5px]"
                {...props}
              >
                {children}
              </code>
            );
          },
          pre: ({ children }) => <>{children}</>,
          a: ({ href, children }) => (
            <a
              href={href}
              target="_blank"
              rel="noreferrer"
              className="font-medium text-primary underline underline-offset-2 hover:opacity-80"
            >
              {children}
            </a>
          ),
          ul: ({ children }) => (
            <ul className="my-2 list-disc space-y-1.5 pl-5 marker:text-primary">{children}</ul>
          ),
          ol: ({ children }) => (
            <ol className="my-2 list-decimal space-y-1.5 pl-5 marker:text-primary">{children}</ol>
          ),
          p: ({ children }) => <p className="my-2 first:mt-0 last:mb-0">{children}</p>,
          h1: ({ children }) => <h3 className="mb-2 mt-4 text-base font-semibold">{children}</h3>,
          h2: ({ children }) => <h3 className="mb-2 mt-4 text-sm font-semibold">{children}</h3>,
          h3: ({ children }) => <h4 className="mb-1.5 mt-3 text-sm font-semibold">{children}</h4>,
          blockquote: ({ children }) => (
            <blockquote className="my-3 border-l-2 border-primary/50 bg-muted/40 py-2 pl-3 text-muted-foreground">
              {children}
            </blockquote>
          ),
          table: ({ children }) => (
            <span className="my-3 block overflow-x-auto">
              <table className="w-full border-collapse text-xs">{children}</table>
            </span>
          ),
          th: ({ children }) => (
            <th className="border bg-muted px-2.5 py-1.5 text-left font-medium">{children}</th>
          ),
          td: ({ children }) => <td className="border px-2.5 py-1.5">{children}</td>,
          text: ({ children }) => (
            <CitationText renderer={citationRenderer}>{children}</CitationText>
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}

function CitationText({
  children,
  renderer,
}: {
  children?: React.ReactNode;
  renderer?: (index: number) => React.ReactNode;
}) {
  if (!renderer || typeof children !== "string") {
    return <>{children}</>;
  }

  const parts = children.split(/(\[\d{1,2}\])/g);
  return (
    <>
      {parts.map((part, index) => {
        const match = part.match(/^\[(\d{1,2})\]$/);
        if (match) {
          return (
            <React.Fragment key={index}>{renderer(Number(match[1]))}</React.Fragment>
          );
        }
        return <React.Fragment key={index}>{part}</React.Fragment>;
      })}
    </>
  );
}
