export function iso(offset: { days?: number; hours?: number; minutes?: number }): string {
  const now = Date.now();
  const ms =
    (offset.days ?? 0) * 86_400_000 +
    (offset.hours ?? 0) * 3_600_000 +
    (offset.minutes ?? 0) * 60_000;
  return new Date(now - ms).toISOString();
}

export function daysFromNow(days: number): string {
  return new Date(Date.now() + days * 86_400_000).toISOString();
}

export function dateOnly(daysAgo: number): string {
  const d = new Date(Date.now() - daysAgo * 86_400_000);
  return d.toISOString().slice(0, 10);
}

/** Deterministic pseudo-random generator so mock series stay stable between renders. */
export function seeded(seed: number): () => number {
  let state = seed % 2147483647;
  if (state <= 0) state += 2147483646;
  return () => {
    state = (state * 16807) % 2147483647;
    return (state - 1) / 2147483646;
  };
}

export async function latency(min = 350, max = 750): Promise<void> {
  const ms = min + Math.random() * (max - min);
  await new Promise((resolve) => setTimeout(resolve, ms));
}

export const DEMO_NOTICE = "Demo data — backend not connected";
