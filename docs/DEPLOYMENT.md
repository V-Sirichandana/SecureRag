# SecureRAG Deployment Guide

## Local development

See `README.md`.

## Render backend

- Root directory: `backend`
- Build command: `pip install -r requirements.txt`
- Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Health check: `/health`
- Python version: `3.12.10`
- Plan: **Free**
- Set `autoDeploy: false` until the deployment branch is approved

### Required environment variables

Secrets are entered only in the Render dashboard, never in git.

```text
APP_ENV=production
DEBUG=false
LOG_LEVEL=INFO
DATABASE_URL=<Neon asyncpg URL>
JWT_SECRET_KEY=<generated secret>
COOKIE_SECURE=true
COOKIE_SAMESITE=none          # cross-site: vercel.app -> onrender.com
CORS_ORIGINS=https://<frontend>.vercel.app
QDRANT_URL=<cluster URL>
QDRANT_API_KEY=<cluster key>
QDRANT_COLLECTION=securerag
EMBEDDING_PROVIDER=hashing
EMBEDDING_DIM=384
LLM_PROVIDER=openai
LLM_MODEL=<Groq model>
LLM_API_KEY=<Groq key>
LLM_BASE_URL=https://api.groq.com/openai/v1
LLM_TIMEOUT_SECONDS=30
MAX_UPLOAD_BYTES=10485760
RATE_LIMIT_LOGIN_ATTEMPTS=5
RATE_LIMIT_LOGIN_WINDOW_SECONDS=60
RETRIEVAL_MODE=hybrid
```

Leave `REDIS_URL` and every `STORAGE_*` variable unset while R2 is not approved.
`DATABASE_URL` may be pasted as a plain Neon URL (`postgresql://…?sslmode=require`);
the application normalises it to `postgresql+asyncpg://…?ssl=require` and removes
`channel_binding`. An empty value fails fast with a clear configuration error.

## Vercel frontend

- Root directory: repository root
- Build command: `npm run build`
- Environment variables:
  - `NEXT_PUBLIC_API_URL=https://YOUR-BACKEND.onrender.com`
  - `NEXT_PUBLIC_USE_MOCKS=false`

## PostgreSQL migration (prepare only, do not execute without approval)

```bash
cd backend
export DATABASE_URL="postgresql+asyncpg://USER:PASSWORD@HOST:5432/DBNAME"
alembic upgrade head
```

On Windows PowerShell:

```powershell
cd backend
$env:DATABASE_URL = "postgresql+asyncpg://USER:PASSWORD@HOST:5432/DBNAME"
alembic upgrade head
```

## Qdrant migration (prepare only)

1. Create a separate Qdrant Cloud collection.
2. Verify the active embedding provider, model, and dimension.
3. Use the existing embedding migration library to plan and validate a target collection.
4. Do not delete or modify the original collection.
5. Perform cutover only after validation.

## Cloudflare R2

R2 is S3-compatible. Configure:

```text
STORAGE_PROVIDER=s3
STORAGE_BUCKET=your-private-bucket
STORAGE_ENDPOINT_URL=https://<account-id>.r2.cloudflarestorage.com
STORAGE_REGION=auto
STORAGE_ACCESS_KEY_ID=<r2-access-key>
STORAGE_SECRET_ACCESS_KEY=<r2-secret-key>
```

Keep the bucket private. Verify the R2 free allowance and billing controls before enabling usage.

## Groq LLM

Use the OpenAI-compatible endpoint:

```text
LLM_PROVIDER=openai
LLM_MODEL=<groq-model>
LLM_API_KEY=<groq-api-key>
LLM_BASE_URL=https://api.groq.com/openai/v1
LLM_TIMEOUT_SECONDS=30
```

Enter the API key directly in Render's environment settings.

## Storage limitation

Render's free filesystem is ephemeral: uploaded documents do not survive a
restart or redeploy. Keep `STORAGE_PROVIDER=local` only for demos. Do not
create or enable Cloudflare R2 without explicit approval.
