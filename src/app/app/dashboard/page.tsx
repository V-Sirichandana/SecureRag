"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ArrowUpRight,
  Database,
  FileText,
  HardDrive,
  MessageSquareQuote,
  Sparkles,
  Upload,
  Users,
  FolderOpen,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { PageHeader } from "@/components/common/page-header";
import { StatCard } from "@/components/dashboard/stat-card";
import { QueryActivityChart } from "@/components/dashboard/query-activity-chart";
import { RetrievalPerformanceGrid } from "@/components/dashboard/retrieval-performance";
import { RecentActivity } from "@/components/dashboard/recent-activity";
import { StatCardsSkeleton, CardSkeleton } from "@/components/common/skeletons";
import { ErrorState } from "@/components/common/error-state";
import { SecurityIndicator } from "@/components/common/security-indicators";
import { useCollections, useDashboard } from "@/lib/queries";
import { DEMO_NOTICE } from "@/lib/mock/utils";
import { formatNumber, timeAgo } from "@/lib/utils";

function greeting() {
  const hour = new Date().getHours();
  if (hour < 12) return "Good morning";
  if (hour < 18) return "Good afternoon";
  return "Good evening";
}

export default function DashboardPage() {
  const router = useRouter();
  const { data, isPending, isError, refetch } = useDashboard();
  const collections = useCollections();

  if (isError) {
    return (
      <div className="p-6">
        <ErrorState
          title="We couldn't load your dashboard"
          description="The analytics service didn't respond in time. Your data is safe — try again in a moment."
          onRetry={() => void refetch()}
        />
      </div>
    );
  }

  return (
    <div className="mx-auto w-full max-w-[1500px] space-y-6 p-4 sm:p-6 lg:p-8">
      <PageHeader
        title={`${greeting()}, ${"Vishvendra"}`}
        description="Here's what's happening across your organization's knowledge base."
        actions={
          <>
            <Button variant="outline" onClick={() => router.push("/app/documents")}>
              <Upload className="mr-2 h-4 w-4" />
              Upload documents
            </Button>
            <Button onClick={() => router.push("/app/chat")}>
              <Sparkles className="mr-2 h-4 w-4" />
              Ask the assistant
            </Button>
          </>
        }
      />

      <div className="flex flex-wrap items-center gap-2">
        <SecurityIndicator label="Organization isolated" />
        <SecurityIndicator label="Secure connection" />
        <SecurityIndicator label="Access controlled" />
        <SecurityIndicator label="Citations enabled" />
        <Badge variant="outline" className="text-muted-foreground">
          {DEMO_NOTICE}
        </Badge>
      </div>

      {isPending || !data ? (
        <StatCardsSkeleton />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <StatCard
            label="Documents"
            value={formatNumber(data.stats.documents.value)}
            icon={FileText}
            delta={data.stats.documents.delta}
            deltaLabel="vs. last month"
          />
          <StatCard
            label="Users"
            value={formatNumber(data.stats.users.value)}
            icon={Users}
            deltaLabel={`${data.stats.users.delta} this month`}
            delta={0}
            hint="seats in use"
          />
          <StatCard
            label="AI queries"
            value={formatNumber(data.stats.queries.value)}
            icon={MessageSquareQuote}
            delta={data.stats.queries.delta}
            deltaLabel="vs. last month"
          />
          <StatCard
            label="Storage"
            value={`${data.stats.storage.value} GB`}
            icon={HardDrive}
            hint={`of ${data.stats.storage.quota} GB`}
            progress={(data.stats.storage.value / data.stats.storage.quota) * 100}
            progressLabel={`${data.stats.storage.value} GB of ${data.stats.storage.quota} GB used`}
          />
        </div>
      )}

      <div className="grid gap-4 xl:grid-cols-3">
        <QueryActivityChart />
        {data ? <RetrievalPerformanceGrid data={data.performance} /> : <Card><CardSkeleton className="border-0" /></Card>}
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        {data ? (
          <RecentActivity activity={data.activity} />
        ) : (
          <Card>
            <CardSkeleton className="border-0" />
          </Card>
        )}

        <Card className="xl:col-span-2 shadow-[0_1px_2px_rgba(0,0,0,0.03)]">
          <CardHeader className="flex-row items-start justify-between space-y-0">
            <div className="space-y-1.5">
              <CardTitle className="text-base font-semibold">Collections overview</CardTitle>
              <CardDescription>Where your knowledge lives</CardDescription>
            </div>
            <Button variant="ghost" size="sm" asChild>
              <Link href="/app/collections">
                View all
                <ArrowUpRight className="ml-1.5 h-4 w-4" />
              </Link>
            </Button>
          </CardHeader>
          <CardContent className="grid gap-3 sm:grid-cols-2">
            {collections.isPending
              ? Array.from({ length: 4 }).map((_, index) => <CardSkeleton key={index} className="p-4" />)
              : collections.data?.map((collection) => (
                  <Link
                    key={collection.id}
                    href={`/app/documents?collection=${collection.id}`}
                    className="group rounded-lg border bg-muted/30 p-4 transition-colors hover:border-primary/40 hover:bg-background"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <span
                        className="flex h-9 w-9 items-center justify-center rounded-md"
                        style={{ backgroundColor: `${collection.color}1a`, color: collection.color }}
                      >
                        <FolderOpen className="h-4.5 w-4.5" />
                      </span>
                      <span className="text-xs text-muted-foreground">
                        {timeAgo(collection.updatedAt)}
                      </span>
                    </div>
                    <p className="mt-3 text-sm font-semibold">{collection.name}</p>
                    <p className="mt-0.5 text-xs text-muted-foreground">
                      {formatNumber(collection.documentCount)} documents · {collection.visibility}
                    </p>
                  </Link>
                ))}
          </CardContent>
        </Card>
      </div>

      <p className="flex items-center gap-1.5 pb-4 text-xs text-muted-foreground">
        <Database className="h-3.5 w-3.5" />
        Demo dataset — connect the FastAPI backend via <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-[11px]">NEXT_PUBLIC_API_URL</code> to stream live metrics.
      </p>
    </div>
  );
}
