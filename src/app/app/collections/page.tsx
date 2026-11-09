"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { FolderOpen, FolderPlus, Lock, Building2, Users } from "lucide-react";
import { PageHeader } from "@/components/common/page-header";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { EmptyState } from "@/components/common/empty-state";
import { ErrorState } from "@/components/common/error-state";

import { CreateCollectionDialog } from "@/components/collections/create-collection-dialog";
import { useCollections } from "@/lib/queries";
import { formatNumber, timeAgo } from "@/lib/utils";
import type { Collection } from "@/lib/types";

const visibilityMeta = {
  everyone: { icon: Building2, label: "Everyone" },
  members: { icon: Users, label: "Members" },
  restricted: { icon: Lock, label: "Restricted" },
} as const;

export default function CollectionsPage() {
  const router = useRouter();
  const [open, setOpen] = React.useState(false);
  const collections = useCollections();

  return (
    <div className="mx-auto w-full max-w-[1500px] space-y-6 p-4 sm:p-6 lg:p-8">
      <PageHeader
        title="Collections"
        description="Organize documents into permissioned knowledge areas the assistant can search."
        actions={
          <Button onClick={() => setOpen(true)}>
            <FolderPlus className="mr-2 h-4 w-4" />
            New collection
          </Button>
        }
      />

      {collections.isError ? (
        <ErrorState
          title="We couldn't load your collections"
          description="The collections service didn't respond."
          onRetry={() => void collections.refetch()}
        />
      ) : collections.isPending ? (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 6 }).map((_, index) => (
            <div key={index} className="h-44 animate-pulse rounded-xl border bg-muted/40" />
          ))}
        </div>
      ) : collections.data?.length === 0 ? (
        <EmptyState
          icon={FolderOpen}
          title="No collections yet"
          description="Collections group related documents and inherit a single permission set."
          action={<Button onClick={() => setOpen(true)}>Create collection</Button>}
        />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {collections.data?.map((collection) => (
            <CollectionCard
              key={collection.id}
              collection={collection}
              onOpen={() =>
                router.push(`/app/documents?collection=${collection.id}`)
              }
            />
          ))}
        </div>
      )}

      <CreateCollectionDialog open={open} onOpenChange={setOpen} />
    </div>
  );
}

function CollectionCard({
  collection,
  onOpen,
}: {
  collection: Collection;
  onOpen: () => void;
}) {
  const meta = visibilityMeta[collection.visibility];
  const Icon = meta.icon;

  return (
    <Card className="group cursor-pointer gap-0 py-0 transition-all hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-md">
      <CardContent className="p-5" onClick={onOpen} role="button" tabIndex={0}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            onOpen();
          }
        }}
      >
        <div className="flex items-start justify-between gap-3">
          <span
            className="flex h-10 w-10 items-center justify-center rounded-lg"
            style={{ backgroundColor: `${collection.color}1a`, color: collection.color }}
          >
            <FolderOpen className="h-5 w-5" />
          </span>
          <Badge variant="outline" className="gap-1.5 text-muted-foreground">
            <Icon className="h-3 w-3" />
            {meta.label}
          </Badge>
        </div>

        <h2 className="mt-4 text-base font-semibold tracking-tight group-hover:text-primary">
          {collection.name}
        </h2>
        <p className="mt-1 line-clamp-2 min-h-10 text-sm text-muted-foreground">
          {collection.description}
        </p>

        <div className="mt-4 flex items-center justify-between border-t pt-3 text-xs text-muted-foreground">
          <span className="font-medium text-foreground">
            {formatNumber(collection.documentCount)} documents
          </span>
          <span>{timeAgo(collection.updatedAt)}</span>
        </div>
        <p className="mt-2 text-xs text-muted-foreground">Owner · {collection.owner}</p>
      </CardContent>
    </Card>
  );
}
