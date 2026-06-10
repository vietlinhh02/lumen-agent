# Lumen Frontend

Next.js 16 frontend for the Lumen AI Literature Review Assistant.

## Run

From the repository root:

```bash
make frontend
```

Or from this directory:

```bash
pnpm dev --port 3000
```

Open `http://localhost:3000`.

## Backend Proxy

Frontend API calls use `/api/*`. Next.js proxies those requests to the FastAPI
backend on `http://localhost:8010` by default.

To use a different backend port:

```bash
BACKEND_PORT=8011 pnpm dev --port 3000
```

## Checks

From the repository root:

```bash
make lint-frontend
make typecheck-frontend
```
