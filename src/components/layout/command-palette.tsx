"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  FileText,
  Folder,
  HelpCircle,
  Search,
  Settings,
  ShieldCheck,
  User,
} from "lucide-react";
import { CommandDialog, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList, CommandSeparator } from "@/components/ui/command";
import { globalSearch } from "@/lib/api/search";
import type { SearchResult } from "@/lib/types";
import { useDebounce } from "@/hooks/use-client";
import { useUIStore } from "@/stores/ui";

const quickLinks: SearchResult[] = [
  { id: "q1", title: "Dashboard", subtitle: "Overview", type: "page", href: "/app/dashboard" },
  { id: "q2", title: "AI Chat", subtitle: "Ask your knowledge base", type: "page", href: "/app/chat" },
  { id: "q3", title: "Documents", subtitle: "Manage uploads", type: "page", href: "/app/documents" },
  { id: "q4", title: "Collections", subtitle: "Organise knowledge", type: "page", href: "/app/collections" },
  { id: "q5", title: "Users", subtitle: "Team directory", type: "page", href: "/app/users" },
  { id: "q6", title: "Usage", subtitle: "Analytics", type: "page", href: "/app/usage" },
];

const iconForType = {
  document: FileText,
  user: User,
  collection: Folder,
  setting: Settings,
  page: Search,
} as const;

export function CommandPalette() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [searching, setSearching] = useState(false);
  const router = useRouter();
  const debounced = useDebounce(query, 200);
  const setStoreOpen = useUIStore((state) => state.setCommandPaletteOpen);
  const storeOpen = useUIStore((state) => state.commandPaletteOpen);

  useEffect(() => {
    setOpen(storeOpen);
  }, [storeOpen]);

  useEffect(() => {
    const down = (event: KeyboardEvent) => {
      if (event.key === "k" && (event.metaKey || event.ctrlKey)) {
        event.preventDefault();
        setStoreOpen(!useUIStore.getState().commandPaletteOpen);
      }
    };
    document.addEventListener("keydown", down);
    return () => document.removeEventListener("keydown", down);
  }, [setStoreOpen]);

  useEffect(() => {
    let cancelled = false;
    if (!debounced.trim()) {
      setResults([]);
      setSearching(false);
      return;
    }
    setSearching(true);
    globalSearch(debounced)
      .then((data) => {
        if (!cancelled) setResults(data);
      })
      .finally(() => {
        if (!cancelled) setSearching(false);
      });
    return () => {
      cancelled = true;
    };
  }, [debounced]);

  const handleOpenChange = (value: boolean) => {
    setOpen(value);
    setStoreOpen(value);
    if (!value) setQuery("");
  };

  const grouped = useMemo(() => {
    const groups: Record<string, SearchResult[]> = {};
    results.forEach((result) => {
      const key = `${result.type}s`;
      groups[key] = [...(groups[key] ?? []), result];
    });
    return groups;
  }, [results]);

  const filteredQuickLinks = useMemo(() => {
    if (!query.trim()) return quickLinks;
    const q = query.toLowerCase();
    return quickLinks.filter((item) => item.title.toLowerCase().includes(q));
  }, [query]);

  const navigate = (href: string) => {
    handleOpenChange(false);
    router.push(href);
  };

  return (
    <CommandDialog open={open} onOpenChange={handleOpenChange}>
      <CommandInput
        placeholder="Search documents, users, collections, settings…"
        value={query}
        onValueChange={setQuery}
        aria-label="Global search"
      />
      <CommandList className="max-h-[420px]">
        <CommandEmpty>
          {searching ? "Searching…" : "No results found."}
        </CommandEmpty>

        {!query.trim() ? (
          <CommandGroup heading="Quick navigation">
            {filteredQuickLinks.map((item) => (
              <CommandItem
                key={item.id}
                onSelect={() => navigate(item.href)}
                value={`quick-${item.title}`}
              >
                <Search className="mr-2 h-4 w-4 text-muted-foreground" />
                {item.title}
                <span className="ml-auto text-xs text-muted-foreground">{item.subtitle}</span>
              </CommandItem>
            ))}
          </CommandGroup>
        ) : null}

        {Object.entries(grouped).map(([group, items], index) => (
          <div key={group}>
            {index > 0 ? <CommandSeparator /> : null}
            <CommandGroup heading={group}>
              {items.map((item) => {
                const Icon = iconForType[item.type];
                return (
                  <CommandItem
                    key={`${item.type}-${item.id}`}
                    onSelect={() => navigate(item.href)}
                    value={`${item.type}-${item.title}`}
                  >
                    <Icon className="mr-2 h-4 w-4 text-muted-foreground" />
                    <span className="truncate">{item.title}</span>
                    <span className="ml-auto truncate pl-3 text-xs text-muted-foreground">
                      {item.subtitle}
                    </span>
                  </CommandItem>
                );
              })}
            </CommandGroup>
          </div>
        ))}

        {query.trim() ? null : (
          <>
            <CommandSeparator />
            <CommandGroup heading="Help">
              <CommandItem onSelect={() => navigate("/app/settings/security")}>
                <ShieldCheck className="mr-2 h-4 w-4 text-muted-foreground" />
                Security settings
              </CommandItem>
              <CommandItem onSelect={() => navigate("/app/audit-logs")}>
                <HelpCircle className="mr-2 h-4 w-4 text-muted-foreground" />
                Audit logs
              </CommandItem>
            </CommandGroup>
          </>
        )}
      </CommandList>
    </CommandDialog>
  );
}
