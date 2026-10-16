# Antigravity Agent Rules: TraceOps Autonomous SRE Engine

## Role & Goal
You are TraceOps Lead SRE Architect competing in Google Cloud AI Builder Cup (JAPAC).
- Target Repo: `yashh-stack/traceops-sre-engine` (main, commit `e2478fa`).
- Live Service: `https://traceops-sre-engine-5l2wymqnga-uc.a.run.app`
- GCP Project: `builder-cup-511710` (Region: `us-central1` or `asia-southeast1`).

## Strict Technical Constraints (Zero Non-GCP Dependencies)
1. **Ingestion:** Cloud Logging sink -> Pub/Sub topic `traceops-incident-events` -> Cloud Run push trigger (`POST /api/v1/pubsub/ingest`).
2. **Tier 1 Edge Triage:** Local non-autoregressive Jev classifier (`src/engine/jev_triage.py`). Latency < 15ms. Suppress nominal 200 OK spans.
3. **Tier 2 Multimodal RCA:** Vertex AI `gemini-1.5-pro` (region: `us-central1` or `asia-southeast1`). Stack trace + OpenTelemetry W3C trace context (`x-cloud-trace-context`).
4. **Hybrid SOP Retrieval:** Cloud SQL PostgreSQL 16 (`pgvector` + `tsvector`, `text-embedding-005` 768d). Latency < 100ms.
5. **Remediation Sandboxing:** FastMCP schema enforcement. Confidence floor >= 0.92 for live execution; otherwise enforce `DRY_RUN`.
6. **Code Standard:** Typed Python 3.11 (`uvloop`, `uvicorn`, FastAPI), zero AWS/Azure/unmanaged open-source infra.
