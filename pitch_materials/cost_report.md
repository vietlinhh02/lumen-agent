# Cost Report & Projections

## Overview
This report outlines the estimated cost per user per month to operate Lumen, primarily driven by LLM API usage, vector embeddings, and database storage.

## Assumptions (Per User / Month)
- **Active Projects:** 3
- **Papers Saved / Processed:** 50
- **Matrix Generations:** 10
- **Reports Generated:** 5
- **Search Queries / Chat Interactions:** 100

## Unit Economics (LLM API - Claude 3 Haiku / GPT-4o-mini / DeepSeek)
- **Document Chunking & Embedding (OpenAI text-embedding-3-small):** ~$0.0005 per paper = **$0.025 / month**
- **AI Query Screening (Input/Output tokens):** ~$0.001 per query = **$0.10 / month**
- **Matrix Extraction (Structured JSON Output):** ~$0.02 per generation = **$0.20 / month**
- **Report Generation (High context window):** ~$0.15 per report = **$0.75 / month**

### Total LLM Cost Per User: ~$1.07 / month

## Infrastructure Costs (Amortized per user, assuming 1,000 active users)
- **PostgreSQL + pgvector (Railway/Supabase):** $50/mo -> **$0.05 / user**
- **Frontend Hosting (Vercel):** $20/mo -> **$0.02 / user**
- **Backend Compute (Cloud Run):** $80/mo -> **$0.08 / user**

### Total Infrastructure Cost: ~$0.15 / month

## Summary
- **Total Estimated Cost per User per Month:** **~$1.22**
- **Suggested Pricing / Buffer Model:** Given the low cost, a subscription of **$5.00 - $9.99 / month** provides excellent gross margins (> 75%) while keeping it highly affordable for students and researchers.
