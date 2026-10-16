"""
Playwright / HTTP E2E Alignment Verification for TraceOps SRE Engine.
Runs Test Vector 1: P0 DB connection pool exhaustion on GKE.
"""

import asyncio
from playwright.async_api import async_playwright

INGRESS_BASE = "https://traceops-sre-engine-5l2wymqnga-uc.a.run.app"


async def run_alignment_verification():
    async with async_playwright() as p:
        request_context = await p.request.new_context(base_url=INGRESS_BASE)

        # 1. Verify Live Swagger Ingress (HTTP 200)
        docs_res = await request_context.get("/docs")
        assert docs_res.status == 200, f"Docs endpoint failed: {docs_res.status}"
        print("[PASS] Swagger UI Accessible (200 OK)")

        # 2. Verify Tier 1: Jev Nominal Span Suppression (<15ms triage)
        nominal_payload = {
            "service_name": "payment-gateway",
            "http_status_code": 200,
            "duration_ms": 32.5,
            "error_message": None,
        }
        triage_res = await request_context.post(
            "/api/v1/telemetry/ingest", data=nominal_payload
        )
        triage_json = await triage_res.json()
        assert triage_json.get("status") == "suppressed", f"Nominal span not suppressed: {triage_json}"
        print(f"[PASS] Tier-1 Edge Guard: {triage_json.get('message')}")

        # 3. Verify Tier 2: P0 DB Connection Pool Exhaustion on GKE
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
        rca_res = await request_context.post("/api/v1/telemetry/ingest", data=p0_payload)
        rca_json = await rca_res.json()

        # Schema & Boundary Assertions
        assert rca_json.get("triaged") is True, f"P0 Incident failed to triage: {rca_json}"
        confidence = rca_json.get("confidence_score") or rca_json.get("analysis", {}).get("confidence_score", 0.0)
        root_cause = rca_json.get("root_cause") or rca_json.get("analysis", {}).get("root_cause", "")
        remediation = rca_json.get("remediation_code") or rca_json.get("analysis", {}).get("remediation_code", "")

        assert confidence >= 0.90, f"Confidence score below operational floor: {confidence}"
        assert "checkout-service" in root_cause, f"RCA culprit mismatch: {root_cause}"
        assert remediation, "Missing remediation payload"

        print(f"[PASS] Tier-2 Multimodal RCA Verified:")
        print(f"       Confidence: {confidence}")
        print(f"       Root Cause: {root_cause}")
        print(f"       Blast Radius: {rca_json.get('blast_radius') or rca_json.get('analysis', {}).get('blast_radius')}")
        print(f"       Mitigation Plan: {rca_json.get('mitigation_steps') or rca_json.get('analysis', {}).get('mitigation_steps')}")

        await request_context.dispose()


if __name__ == "__main__":
    asyncio.run(run_alignment_verification())
