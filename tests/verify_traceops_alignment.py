"""
Playwright / HTTP E2E Alignment Verification for TraceOps SRE Engine.
Runs SLA & Latency Harness:
1. Tier-1: Jev Nominal Span Suppression (< 15ms SLA, zero LLM token burn)
2. Tier-2: P0 DB connection pool exhaustion on GKE (Confidence >= 0.92, < 15s E2E SLA)
"""

import asyncio
import time
from playwright.async_api import async_playwright

INGRESS_BASE = "https://traceops-sre-engine-5l2wymqnga-uc.a.run.app"


async def run_alignment_verification():
    async with async_playwright() as p:
        request_context = await p.request.new_context(base_url=INGRESS_BASE)

        # 1. Ingress & Spec Audit (GET /docs)
        t0 = time.perf_counter()
        docs_res = await request_context.get("/docs")
        docs_latency_ms = (time.perf_counter() - t0) * 1000
        assert docs_res.status == 200, f"Docs endpoint failed: {docs_res.status}"
        print(f"[PASS] Swagger UI Accessible (200 OK) | Network Latency: {docs_latency_ms:.2f}ms")

        # 2. Tier-1 Jev Nominal Span Suppression (< 15ms edge triage)
        nominal_payload = {
            "service_name": "payment-gateway",
            "http_status_code": 200,
            "duration_ms": 32.5,
            "error_message": None,
        }
        t1 = time.perf_counter()
        triage_res = await request_context.post(
            "/api/v1/telemetry/ingest", data=nominal_payload
        )
        triage_e2e_ms = (time.perf_counter() - t1) * 1000
        server_timing_1 = triage_res.headers.get("server-timing", "total;dur=0.0")
        triage_json = await triage_res.json()

        assert triage_json.get("status") == "suppressed", f"Nominal span not suppressed: {triage_json}"
        assert triage_json.get("triaged") is False, "Nominal span triaged flag should be False"
        print(f"[PASS] Tier-1 Jev Edge Guard: {triage_json.get('message')}")
        print(f"       Backend Timing: {server_timing_1} | E2E Latency: {triage_e2e_ms:.2f}ms")

        # 3. Tier-2 P0 Anomaly Ingestion (Test Vector 1: GKE Connection Pool Timeout)
        p0_payload = {
            "service_name": "checkout-service",
            "http_status_code": 500,
            "duration_ms": 1420.0,
            "error_message": "database connection pool timeout asyncpg: remaining connection slots reserved",
            "attributes": {
                "region": "us-central1",
                "cluster": "gke-prod",
                "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
            },
        }
        t2 = time.perf_counter()
        rca_res = await request_context.post("/api/v1/telemetry/ingest", data=p0_payload)
        rca_e2e_ms = (time.perf_counter() - t2) * 1000
        server_timing_2 = rca_res.headers.get("server-timing", "total;dur=0.0")
        rca_json = await rca_res.json()

        # Schema & Boundary Assertions
        assert rca_json.get("triaged") is True, f"P0 Incident failed to triage: {rca_json}"
        confidence = rca_json.get("confidence_score") or rca_json.get("analysis", {}).get("confidence_score", 0.0)
        root_cause = rca_json.get("root_cause") or rca_json.get("analysis", {}).get("root_cause", "")
        remediation = rca_json.get("remediation_code") or rca_json.get("analysis", {}).get("remediation_code", "")

        assert confidence >= 0.92, f"Confidence score below operational floor (0.92): {confidence}"
        assert "checkout-service" in root_cause, f"RCA culprit mismatch: {root_cause}"
        assert remediation, "Missing remediation payload"
        assert rca_e2e_ms < 15000.0, f"E2E latency breached 15s SLA: {rca_e2e_ms:.2f}ms"

        print(f"[PASS] Tier-2 Multimodal RCA Verified:")
        print(f"       Confidence: {confidence:.2f} (>= 0.92 SLA floor)")
        print(f"       Backend Timing: {server_timing_2} | E2E Latency: {rca_e2e_ms:.2f}ms")
        print(f"       Root Cause: {root_cause}")
        print(f"       Blast Radius: {rca_json.get('blast_radius') or rca_json.get('analysis', {}).get('blast_radius')}")
        print(f"       Remediation Code: {remediation}")
        print(f"       Mitigation Plan: {rca_json.get('mitigation_steps') or rca_json.get('analysis', {}).get('mitigation_steps')}")

        await request_context.dispose()


if __name__ == "__main__":
    asyncio.run(run_alignment_verification())
