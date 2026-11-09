"use client";

import * as React from "react";
import { useParams } from "next/navigation";
import { History, Lock, ShieldCheck } from "lucide-react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/common/skeletons";
import { ErrorState } from "@/components/common/error-state";
import { DocumentDetailHeader } from "@/components/documents/document-detail-header";
import { DocumentPermissions } from "@/components/documents/document-permissions";
import { useDocument, useDocumentPages } from "@/lib/queries";
import { formatDate, timeAgo } from "@/lib/utils";

const activityFeed = [
  { id: "a1", label: "Indexed into vector store", timestamp: "2 hours ago", tone: "text-success" },
  { id: "a2", label: "Access policy updated by Sarah Johnson", timestamp: "5 hours ago", tone: "text-primary" },
  { id: "a3", label: "Cited in 14 AI answers", timestamp: "yesterday", tone: "text-muted-foreground" },
  { id: "a4", label: "Uploaded by Vishvendra Vadla", timestamp: "120 days ago", tone: "text-muted-foreground" },
];

export default function DocumentDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;
  const [tab, setTab] = React.useState("overview");
  const { data, isPending, isError, refetch } = useDocument(id);
  const pages = useDocumentPages(id, tab === "content");

  if (isPending) {
    return (
      <div className="mx-auto w-full max-w-[1500px] space-y-5 p-4 sm:p-6 lg:p-8">
        <Skeleton className="h-4 w-32" />
        <Skeleton className="h-9 w-96" />
        <Skeleton className="h-28 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="mx-auto w-full max-w-[1500px] p-4 sm:p-6 lg:p-8">
        <ErrorState
          variant="not-found"
          title="Document not found"
          description="The document may have been deleted or you may not have permission to access it."
          onRetry={() => void refetch()}
        />
      </div>
    );
  }

  return (
    <div className="mx-auto w-full max-w-[1500px] space-y-6 p-4 sm:p-6 lg:p-8">
      <DocumentDetailHeader id={id} />

      <Tabs value={tab} onValueChange={setTab} className="space-y-4">
        <TabsList className="h-10 w-full justify-start overflow-x-auto sm:w-auto">
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="content">Content</TabsTrigger>
          <TabsTrigger value="permissions">Permissions</TabsTrigger>
          <TabsTrigger value="activity">Activity</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="space-y-4">
          <div className="grid gap-4 lg:grid-cols-3">
            <Card className="lg:col-span-2">
              <CardHeader>
                <CardTitle className="text-base font-semibold">About this document</CardTitle>
                <CardDescription>
                  Extracted metadata and indexing state for {data.name}
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4 text-sm">
                <p className="text-muted-foreground">
                  This document belongs to the <span className="font-medium text-foreground">{data.collectionName}</span>{" "}
                  collection and is classified as{" "}
                  <span className="font-medium text-foreground capitalize">{data.classification}</span>.
                  {data.status === "ready"
                    ? " It is fully indexed and available to the assistant with citation support."
                    : data.status === "processing"
                      ? " Indexing is still in progress — answers may not cite it yet."
                      : data.status === "failed"
                        ? " Processing failed. Retry the upload to index this file."
                        : " It is archived and excluded from new answers."}
                </p>

                <div className="grid gap-3 sm:grid-cols-2">
                  <InfoRow label="Department" value={data.department} />
                  <InfoRow label="Classification" value={data.classification} capitalize />
                  <InfoRow label="Pages detected" value={String(data.pageCount)} />
                  <InfoRow label="Chunks indexed" value={String(data.chunkCount)} />
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base font-semibold">
                  <ShieldCheck className="h-4 w-4 text-success" />
                  Security posture
                </CardTitle>
                <CardDescription>Applies to this document</CardDescription>
              </CardHeader>
              <CardContent className="space-y-3 text-sm">
                <SecurityRow label="Organization isolated" value="Active" demo />
                <SecurityRow label="Access controlled" value="Active" />
                <SecurityRow label="Citation tracking" value="Enabled" />
                <SecurityRow label="Encryption at rest" value="Active" demo />
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="content" className="space-y-4">
          {pages.isPending ? (
            <div className="space-y-3">
              <Skeleton className="h-40 w-full" />
              <Skeleton className="h-40 w-full" />
            </div>
          ) : pages.isError ? (
            <ErrorState
              title="We couldn't extract this document"
              description="The content endpoint failed. Try again in a moment."
              onRetry={() => void pages.refetch()}
            />
          ) : (
            <div className="space-y-4">
              {pages.data?.map((page) => (
                <Card key={page.pageNumber}>
                  <CardHeader className="flex-row items-center justify-between space-y-0">
                    <CardTitle className="text-sm font-semibold">{page.title}</CardTitle>
                    <Badge variant="outline" className="text-muted-foreground">
                      Page {page.pageNumber}
                    </Badge>
                  </CardHeader>
                  <CardContent className="space-y-3 text-sm leading-relaxed text-muted-foreground">
                    {page.paragraphs.map((paragraph) => (
                      <p key={paragraph.id}>
                        {paragraph.highlight ? (
                          <>
                            {paragraph.text.split(paragraph.highlight).map((part, index, all) => (
                              <React.Fragment key={index}>
                                {part}
                                {index < all.length - 1 ? (
                                  <mark className="rounded bg-warning/25 px-0.5 text-foreground">
                                    {paragraph.highlight}
                                  </mark>
                                ) : null}
                              </React.Fragment>
                            ))}
                          </>
                        ) : (
                          paragraph.text
                        )}
                      </p>
                    ))}
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </TabsContent>

        <TabsContent value="permissions">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base font-semibold">
                <Lock className="h-4 w-4 text-primary" />
                Document permissions
              </CardTitle>
              <CardDescription>
                Decide who inside Acme Technologies can retrieve this document.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <DocumentPermissions documentId={data.id} />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="activity">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base font-semibold">
                <History className="h-4 w-4 text-primary" />
                Document activity
              </CardTitle>
              <CardDescription>
                Created {formatDate(data.createdAt)} · updated {timeAgo(data.updatedAt)}
              </CardDescription>
            </CardHeader>
            <CardContent>
              <ol className="space-y-4 border-l pl-5">
                {activityFeed.map((item) => (
                  <li key={item.id} className="relative">
                    <span className="absolute -left-[26px] top-1.5 h-2.5 w-2.5 rounded-full border bg-background" />
                    <p className={`text-sm ${item.tone}`}>{item.label}</p>
                    <p className="text-xs text-muted-foreground">{item.timestamp}</p>
                  </li>
                ))}
              </ol>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}

function InfoRow({ label, value, capitalize }: { label: string; value: string; capitalize?: boolean }) {
  return (
    <div className="rounded-lg border bg-muted/30 px-3.5 py-2.5">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className={`mt-0.5 text-sm font-medium ${capitalize ? "capitalize" : ""}`}>{value}</p>
    </div>
  );
}

function SecurityRow({ label, value, demo }: { label: string; value: string; demo?: boolean }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="text-muted-foreground">{label}</span>
      <span className="flex items-center gap-1.5 font-medium">
        {value}
        <span className="text-success">✓</span>
        {demo ? (
          <Badge variant="outline" className="text-[10px] text-muted-foreground">
            demo
          </Badge>
        ) : null}
      </span>
    </div>
  );
}
