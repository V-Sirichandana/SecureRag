import { FileUp, KeyRound, Pencil, UserPlus, MessageSquare, ShieldCheck } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { timeAgo } from "@/lib/utils";
import type { ActivityEvent } from "@/lib/types";

const iconByType = {
  upload: FileUp,
  invite: UserPlus,
  api_key: KeyRound,
  update: Pencil,
  query: MessageSquare,
  permission: ShieldCheck,
} as const;

export function RecentActivity({ activity }: { activity: ActivityEvent[] }) {
  return (
    <Card className="shadow-[0_1px_2px_rgba(0,0,0,0.03)]">
      <CardHeader>
        <CardTitle className="text-base font-semibold">Recent activity</CardTitle>
        <CardDescription>What&apos;s happening across your organization</CardDescription>
      </CardHeader>
      <CardContent>
        <ol className="relative space-y-5 border-l pl-6">
          {activity.map((event) => {
            const Icon = iconByType[event.type];
            return (
              <li key={event.id} className="relative">
                <span className="absolute -left-[31px] flex h-5 w-5 items-center justify-center rounded-full border bg-background">
                  <Icon className="h-3 w-3 text-primary" />
                </span>
                <p className="text-sm leading-snug">
                  <span className="font-medium">{event.actor}</span>{" "}
                  <span className="text-muted-foreground">{event.action}</span>{" "}
                  <span className="font-medium">{event.target}</span>
                </p>
                <p className="mt-0.5 text-xs text-muted-foreground">{timeAgo(event.timestamp)}</p>
              </li>
            );
          })}
        </ol>
      </CardContent>
    </Card>
  );
}
