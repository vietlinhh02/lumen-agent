# Deployed Production URL

## Live Environments

- **Production Frontend (Vercel):** [https://lumen-app-prod.vercel.app](https://lumen-app-prod.vercel.app) *(Example)*
- **Production Backend API (Railway/Cloud Run):** [https://api-lumen.railway.app](https://api-lumen.railway.app) *(Example)*

### Deployment Strategy
- **Frontend:** Deployed via Vercel for fast edge delivery, automatic CI/CD from the `main` branch, and native Next.js support.
- **Backend:** Deployed via Railway (or Google Cloud Run) using the provided `Dockerfile`. PostgreSQL with `pgvector` extension is hosted as a managed service on Railway/Supabase.

*(Note: Replace the example URLs with actual deployed endpoints once the pipeline is configured.)*
