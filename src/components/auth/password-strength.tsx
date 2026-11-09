"use client";

import { cn } from "@/lib/utils";

const levels = [
  { label: "Too short", min: 0 },
  { label: "Weak", min: 1 },
  { label: "Fair", min: 2 },
  { label: "Good", min: 3 },
  { label: "Strong", min: 4 },
];

export function scorePassword(password: string): number {
  if (!password) return 0;
  let score = 0;
  if (password.length >= 8) score += 1;
  if (password.length >= 12) score += 1;
  if (/[A-Z]/.test(password) && /[a-z]/.test(password)) score += 1;
  if (/\d/.test(password) && /[^A-Za-z0-9]/.test(password)) score += 1;
  return Math.min(score, 4);
}

const tone = [
  "bg-muted",
  "bg-destructive",
  "bg-warning",
  "bg-warning",
  "bg-success",
] as const;

export function PasswordStrength({ password }: { password: string }) {
  const score = scorePassword(password);
  const level = levels[score];

  return (
    <div className="space-y-1.5" aria-live="polite">
      <div className="flex gap-1.5">
        {[0, 1, 2, 3].map((index) => (
          <span
            key={index}
            className={cn(
              "h-1.5 flex-1 rounded-full transition-colors duration-300",
              password && index < score ? tone[score] : "bg-muted",
            )}
          />
        ))}
      </div>
      <p className="text-xs text-muted-foreground">
        {password ? (
          <>
            Password strength:{" "}
            <span
              className={cn(
                "font-medium",
                score >= 4 ? "text-success" : score >= 3 ? "text-warning" : "text-destructive",
              )}
            >
              {level.label}
            </span>
          </>
        ) : (
          "Use 12+ characters with upper, lower, number and symbol."
        )}
      </p>
    </div>
  );
}
