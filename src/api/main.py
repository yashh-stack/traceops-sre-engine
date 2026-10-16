"""
TraceOps SRE Engine - High-Performance FastAPI Application.
Integrated with OpenTelemetry Google Cloud Trace propagation,
Tier-1 Jev Non-Autoregressive Telemetry Guard, and Tier-2 Gemini 1.5 Pro SRE Intelligence.
"""
from __future__ import annotations
import os
import time
import uuid
import logging
from typing import Any, Dict, List, Optional, Union
from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from src.engine.jev_triage import JevTelemetryGuard
from src.services.gemini_analyzer import GeminiSREAnalyzer
from src.db.firestore_client import firestore_ledger

# Configure structured logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("traceops.api")

app = FastAPI(
    title="TraceOps SRE Engine",
    description="Autonomous Multimodal SRE & Incident Intelligence Engine for Google Cloud",
    version="1.0.0"
)

# Initialize engines
jev_guard = JevTelemetryGuard(p99_latency_ms=500.0)
gemini_analyzer = GeminiSREAnalyzer(
    project_id=os.getenv("GCP_PROJECT", "builder-cup-511710"),
    model_name=os.getenv("MODEL_NAME", "gemini-1.5-pro")
)

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Google Cloud Trace ASGI Middleware
@app.middleware("http")
async def google_cloud_trace_middleware(request: Request, call_next):
    """
    Extracts or provisions W3C / Cloud Trace context.
    Propagates `X-Cloud-Trace-Context` header (format: TRACE_ID/SPAN_ID;o=TRACE_TRUE).
    """
    cloud_trace_header = request.headers.get("x-cloud-trace-context")
    if cloud_trace_header and "/" in cloud_trace_header:
        trace_id = cloud_trace_header.split("/")[0]
        span_part = cloud_trace_header.split("/")[1].split(";")[0]
    else:
        trace_id = request.headers.get("x-trace-id") or uuid.uuid4().hex
        span_part = uuid.uuid4().hex[:16]

    request.state.trace_id = trace_id
    request.state.span_id = span_part
    start_time = time.perf_counter()

    response: Response = await call_next(request)

    latency_ms = (time.perf_counter() - start_time) * 1000
    formatted_trace = f"{trace_id}/{span_part};o=1"
    response.headers["X-Cloud-Trace-Context"] = formatted_trace
    response.headers["X-Trace-ID"] = trace_id
    response.headers["Server-Timing"] = f"total;dur={latency_ms:.2f}"

    return response


# ========================== Pydantic Schemas ==========================
class SpanPayload(BaseModel):
    span_id: Optional[str] = None
    trace_id: Optional[str] = None
    service_name: Optional[str] = "service-under-test"
    name: Optional[str] = "http_request"
    http_status_code: Optional[int] = 200
    duration_ms: Optional[float] = 45.0
    error_message: Optional[str] = None
    attributes: Optional[Dict[str, Any]] = Field(default_factory=dict)

class IncidentAnalysisRequest(BaseModel):
    trace_id: Optional[str] = None
    service_name: str
    error_message: str
    http_status_code: Optional[int] = 500
    duration_ms: Optional[float] = 1200.0
    attributes: Optional[Dict[str, Any]] = Field(default_factory=dict)

class IncidentAnalysisResponse(BaseModel):
    root_cause: str
    confidence_score: float
    blast_radius: str
    remediation_code: str
    mitigation_steps: List[str]


# ========================== API Endpoints =============================
@app.get("/")
async def root():
    return {
        "service": "TraceOps SRE Engine",
        "competition": "Google Cloud AI Builder Cup 2026",
        "runtime": "Native Google Cloud Run",
        "status": "OPERATIONAL"
    }

@app.get("/healthz")
async def healthz():
    """Kubernetes / Cloud Run liveness and readiness probe."""
    return {
        "status": "HEALTHY",
        "version": "1.0.0",
        "gcp_project": os.getenv("GCP_PROJECT", "builder-cup-511710"),
        "region": os.getenv("REGION", "us-central1"),
        "model": os.getenv("MODEL_NAME", "gemini-1.5-pro")
    }

@app.post("/api/v1/telemetry/ingest")
async def ingest_telemetry(payload: Union[SpanPayload, Dict[str, Any]], request: Request):
    """
    Tier-1 / Tier-2 Telemetry Ingestion Pipeline.
    1. Evaluates payload via sub-15ms Jev Non-Autoregressive Telemetry Guard.
    2. If healthy, suppresses immediately with 200 OK (minimizing cloud egress/compute cost).
    3. If anomalous (5xx, unhandled exception, or latency > p99), promotes to Gemini 1.5 Pro SRE analyzer.
    """
    span_dict = payload.dict() if hasattr(payload, "dict") else dict(payload)
    if not span_dict.get("trace_id"):
        span_dict["trace_id"] = getattr(request.state, "trace_id", uuid.uuid4().hex)

    is_anomalous = jev_guard.evaluate_span(span_dict)

    if not is_anomalous:
        return {
            "status": "suppressed",
            "triaged": False,
            "message": "Span within nominal latency bounds; suppressed by Jev Telemetry Guard in sub-15ms.",
            "trace_id": span_dict["trace_id"]
        }

    # Anomalous span: Hand off to Gemini 1.5 Pro SRE Analyzer
    analysis = gemini_analyzer.analyze_incident(span_dict)
    
    # Persist incident state & telemetry audit to Google Cloud Firestore & Firebase sync
    incident_id = firestore_ledger.record_incident(span_dict["trace_id"], span_dict, analysis)
    
    return {
        "status": "anomalous",
        "triaged": True,
        "triage_reason": "Latency p99 threshold breach or unhandled error status detected.",
        "trace_id": span_dict["trace_id"],
        "incident_id": incident_id,
        "analysis": analysis
    }

@app.post("/api/v1/incidents/analyze", response_model=IncidentAnalysisResponse)
async def analyze_incident(incident: IncidentAnalysisRequest):
    """
    Direct Incident Diagnostic Endpoint.
    Executes multimodal root cause analysis, retrieves matching runbooks from vector storage,
    persists audit record to Firestore, and returns structured remediation.
    """
    payload = incident.dict()
    analysis = gemini_analyzer.analyze_incident(payload)
    trace_id = payload.get("trace_id") or uuid.uuid4().hex
    firestore_ledger.record_incident(trace_id, payload, analysis)
    
    return IncidentAnalysisResponse(
        root_cause=analysis.get("root_cause", "Undefined system exception"),
        confidence_score=float(analysis.get("confidence_score", 0.90)),
        blast_radius=analysis.get("blast_radius", "Localized to service"),
        remediation_code=analysis.get("remediation_code", "# Verify configuration"),
        mitigation_steps=analysis.get("mitigation_steps", ["Restart failing replica"])
    )

@app.get("/api/v1/incidents/audit")
async def get_incident_audit_trail(limit: int = 10):
    """
    Retrieves real-time persistent incident history from Google Cloud Firestore.
    Powers frontend SRE dashboards and Firebase incident synchronization.
    """
    records = firestore_ledger.list_recent_incidents(limit=limit)
    return {
        "count": len(records),
        "firestore_collection": "traceops_incidents",
        "incidents": records
    }

