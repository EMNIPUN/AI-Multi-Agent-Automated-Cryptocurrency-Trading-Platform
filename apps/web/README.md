# CryptoNova Web — Premium Command Center (Phase 3A)

Dark fintech Next.js App Router UI with shadcn/ui + selective Magic UI patterns.

## Run

```powershell
# API (wallet + fixtures)
uv run uvicorn apps.api.main:app --host 127.0.0.1 --port 8000

# Web
cd apps/web
npm install
npm run dev
```

Open http://localhost:3000 (redirects to `/dashboard`).

Optional: `API_INTERNAL_BASE_URL=http://127.0.0.1:8000`

## Scripts

| Command | Purpose |
|---------|---------|
| `npm run dev` | Local Next server |
| `npm run build` | Production build |
| `npm run typecheck` | `tsc --noEmit` |
| `npm run test:events` | Offline event merge/dedupe checks |
| `npm run lint` | next lint |

## Safety

- SAMPLE/DEMO banners for fixtures
- No place/cancel/leverage UI actions
- Paper submit disabled
- Bybit keys stay on FastAPI only
- `PRIVATE_DATA_READS_ENABLED` remains false by backend default
