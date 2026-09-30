"use client";

import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";

function GoogleMark() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" className="h-4 w-4">
      <path
        fill="#4285F4"
        d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.27-4.74 3.27-8.1Z"
      />
      <path
        fill="#34A853"
        d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84A11 11 0 0 0 12 23Z"
      />
      <path
        fill="#FBBC05"
        d="M5.84 14.1a6.6 6.6 0 0 1 0-4.2V7.06H2.18a11 11 0 0 0 0 9.88l3.66-2.84Z"
      />
      <path
        fill="#EA4335"
        d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1A11 11 0 0 0 2.18 7.06l3.66 2.84C6.71 7.31 9.14 5.38 12 5.38Z"
      />
    </svg>
  );
}

function MicrosoftMark() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" className="h-4 w-4">
      <path fill="#F25022" d="M2 2h9.5v9.5H2z" />
      <path fill="#7FBA00" d="M12.5 2H22v9.5h-9.5z" />
      <path fill="#00A4EF" d="M2 12.5h9.5V22H2z" />
      <path fill="#FFB900" d="M12.5 12.5H22V22h-9.5z" />
    </svg>
  );
}

interface OAuthButtonsProps {
  onSelect: (provider: "google" | "microsoft") => void;
  pending: "google" | "microsoft" | null;
}

export function OAuthButtons({ onSelect, pending }: OAuthButtonsProps) {
  return (
    <div className="space-y-4">
      <div className="relative my-5">
        <Separator />
        <span className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 bg-card px-2.5 text-xs text-muted-foreground">
          or continue with
        </span>
      </div>

      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        <Button
          type="button"
          variant="outline"
          className="h-10"
          onClick={() => onSelect("google")}
          disabled={pending !== null}
        >
          {pending === "google" ? (
            <span className="mr-2 h-4 w-4 animate-spin rounded-full border-2 border-muted-foreground border-t-transparent" />
          ) : (
            <GoogleMark />
          )}
          Google
        </Button>
        <Button
          type="button"
          variant="outline"
          className="h-10"
          onClick={() => onSelect("microsoft")}
          disabled={pending !== null}
        >
          {pending === "microsoft" ? (
            <span className="mr-2 h-4 w-4 animate-spin rounded-full border-2 border-muted-foreground border-t-transparent" />
          ) : (
            <MicrosoftMark />
          )}
          Microsoft
        </Button>
      </div>
    </div>
  );
}
