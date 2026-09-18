# Cost Report & Projections

## Overview
This report outlines the estimated cost per user per month to operate Lumen, primarily driven by LLM API usage, vector embeddings, and database storage.

## Assumptions (Per User / Month)
- **Active Projects:** 3
- **Papers Saved / Processed:** 50
- **Matrix Generations:** 10
- **Reports Generated:** 5
- **Search Queries / Chat Interactions:** 100

## Unit Economics (LLM API - mimo-v2.5 / mimo-v2.5-pro)
- **Document Chunking & Embedding (Jina AI / Nemotron):** ~$0.0005 per paper = **$0.025 / month**
- **AI Query Screening & Chat (mimo-v2.5):** ~$0.00026 per query/turn (average 30 in / 280 out tokens) = **$0.026 / month**
- **Matrix Extraction (mimo-v2.5-pro):** ~$0.0021 per paper average (from 128 database log runs) = **$0.105 / month**
- **Report Generation (mimo-v2.5):** ~$0.027 per report average (from 15 database log runs) = **$0.135 / month**

### Total LLM Cost Per User: ~$0.29 / month

## Infrastructure Costs (Amortized per user, assuming 1,000 active users)
- **PostgreSQL + pgvector (Railway/Supabase):** $50/mo -> **$0.05 / user**
- **Frontend Hosting (Vercel):** $20/mo -> **$0.02 / user**
- **Backend Compute (Cloud Run):** $80/mo -> **$0.08 / user**

### Total Infrastructure Cost: ~$0.15 / month

## Summary
- **Total Estimated Cost per User per Month:** **~$0.44** (LLM: $0.29 + Infrastructure: $0.15)
- **Suggested Pricing / Buffer Model:** Given the low cost, a subscription of **$4.99 - $9.99 / month** provides excellent gross margins (> 90%) while keeping it highly affordable for students and researchers.
