# SecureRAG — Frontend

Enterprise, multi-tenant RAG (retrieval-augmented generation) SaaS frontend. Upload documents into
collections, chat with AI answers grounded in your knowledge base, and administer tenants with
roles, audit logging, API keys and usage analytics.

> **Status:** UI complete against a mock API layer. The frontend never enforces tenant security —
> every request must be authorized by the backend against the authenticated principal.

## Quick start

```bash
npm install
cp .env.local.example .env.local
npm run dev
```

Open http://localhost:3000. The root route redirects to `/app/dashboard`.

Sign in with any credentials (demo mode ignores verification), or use the prefilled demo user.

### Scripts

| Command             | Purpose                                  |
| ------------------- | ---------------------------------------- |
| `npm run dev`       | Start the dev server on port 3000        |
| `npm run build`     | Production build (`next build`)          |
| `npm run start`     | Serve the production build               |
| `npm run lint`      | ESLint with `--max-warnings 0`           |
| `npm run typecheck` | TypeScript project check (`tsc --noEmit`)|

## Environment

`.env.local.example`:

```bash
# Base URL of the FastAPI backend. Never hardcode API URLs in components.
NEXT_PUBLIC_API_URL=http://localhost:8000

# Set to "true" to force the mock API layer (no backend required).
NEXT_PUBLIC_USE_MOCKS=true
```

With `NEXT_PUBLIC_USE_MOCKS=true` every call in `src/lib/api/*` resolves locally with simulated
latency, so the app is fully explorable offline. Set it to `false` to hit the real API.

## Stack

- **Next.js 15** (App Router) + **React 19** + **TypeScript**
- **Tailwind CSS 3.4** with HSL design tokens, `tailwindcss-animate`, dark mode
- **shadcn/ui** (new-york / zinc) on Radix primitives
- **TanStack Query v5** for server state, **Zustand** for UI/session state
- **React Hook Form + Zod** for forms, **Recharts** for analytics, **Sonner** for toasts

## Route map

| Route | Description |
| --- | --- |
| `/login`, `/signup`, `/forgot-password` | Auth flows (strength meter, OAuth buttons) |
| `/app/dashboard` | KPIs, query activity chart, retrieval performance, recent activity |
| `/app/chat` | Streaming answers with citation chips and source preview drawer |
| `/app/documents` | Upload dropzone, filters, table, per-document detail tabs |
| `/app/collections` | Collection cards and create flow |
| `/app/users` | Invite dialog, role changes, status toggle, removal |
| `/app/roles` | Role cards + editable permission matrix |
| `/app/audit-logs` | Filters (user/action/resource/status/date) + event detail drawer |
| `/app/api-keys` | Key cards, scoped creation, one-time plaintext reveal |
| `/app/usage` | 7/30/90/custom ranges, token + latency charts, model split, daily table |
| `/app/settings` | `general` / `security` / `ai` sub-sections with sticky secondary nav |
| `/app/forbidden` | 403 state |
| — | Global `not-found.tsx` (404) and `error.tsx` boundaries |

Every authenticated route is guarded by `src/app/app/layout.tsx`, which redirects to `/login` when
no session exists in the persisted Zustand store.

## Architecture

```
src/
├── app/                  # App Router routes (auth, app shell, globals, error/404)
├── components/
│   ├── ui/               # shadcn/ui primitives
│   ├── layout/           # sidebar, header, command palette, nav model
│   ├── dashboard|documents|chat|users|settings|usage|security|api-keys|common
├── hooks/                # useMediaQuery, useDebounce, useMounted
├── lib/
│   ├── api/              # typed fetch client + per-domain API functions
│   ├── mock/             # demo datasets + latency simulation
│   ├── queries.ts        # query keys, hooks and mutations
│   ├── types.ts          # shared domain types
│   └── utils.ts          # cn + formatters
└── stores/               # zustand (auth session, org, sidebar, command palette)
```

**Data flow:** component → `lib/queries.ts` hook → `lib/api/*.ts` function → `client.request()` →
(mocks | `NEXT_PUBLIC_API_URL`). Components never import from `lib/mock` directly, except for
static reference data (labels, permission matrices, models).

**Key behaviours**

- Chat streams tokens via `streamAnswer()` and renders markdown with citation chips; clicking a
  citation opens a source-preview drawer with the exact quoted page content.
- Uploads are client-side simulated with progress, then invalidate the documents cache.
- Command palette (`⌘K` / `Ctrl+K`) searches documents, collections, users and settings routes.
- Theme is persisted (`next-themes`), sidebar collapse and active organization persist in
  Zustand; both hydrate-safe to avoid SSR mismatch.
- Route-level `loading.tsx` skeletons plus in-page skeletons cover loading states; every query has
  an error state with retry; lists ship empty states with recovery actions.

## Security notes

- Never store API key plaintext beyond the one-time reveal dialog; only masked values persist.
- Roles and permissions in the UI are advisory display state, not enforcement.
- Avoid `useSearchParams` without a `<Suspense>` boundary (documents page wraps it).

## Verification

```bash
npm run lint
npm run typecheck
npm run build
```
