# Evaluation Metrics

To ensure Lumen provides a high-quality, reliable, and performant experience, we track several key evaluation metrics.

## 1. RAG Retrieval Latency
- **Metric:** Time taken from user search query to retrieving embedded chunks and generating a synthesis response.
- **Current Performance:** ~1.8 seconds (p95)
- **Baseline Target:** < 3.0 seconds

## 2. LLM Extraction Cost (Per Paper)
- **Metric:** API cost associated with extracting methodologies, findings, and metadata into the Literature Matrix per paper.
- **Current Performance:** ~$0.015 per paper (using optimized Claude 3 Haiku / GPT-4o-mini).
- **Baseline Target:** < $0.05 per paper.

## 3. Hallucination Rate (Citation Accuracy)
- **Metric:** Percentage of generated claims in reports that cite sources NOT present in the user's project corpus.
- **Current Performance:** 0% (Achieved via strict system prompts and context bounding).
- **Baseline Target:** 0% tolerance.

## 4. Query Relevancy Score (AI Screening)
- **Metric:** Average AI relevance score of top 10 search results based on user query intent.
- **Current Performance:** 92% highly relevant.
- **Baseline Target:** > 80% baseline.
