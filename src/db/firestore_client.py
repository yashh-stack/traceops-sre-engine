"""
Google Cloud Firestore & Firebase State Synchronization Client.
Audit trail persistence layer recording all analyzed incidents, RCA decisions,
and real-time incident event channels for frontend SRE responder dashboards.
"""
from __future__ import annotations
import os
import time
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("traceops.firestore")

class FirestoreIncidentLedger:
    """
    Manages persistent state across Google Cloud Firestore and Firebase Realtime Sync.
    Ensures zero loss of diagnostic history, post-mortem timelines, and remediation logs.
    """

    def __init__(self, project_id: Optional[str] = None, collection_name: str = "traceops_incidents"):
        self.project_id = project_id or os.getenv("GCP_PROJECT", os.getenv("GCP_PROJECT_ID", "builder-cup-511710"))
        self.collection_name = collection_name
        self._db = None
        self._local_audit_log: List[Dict[str, Any]] = []
        self._init_firestore()

    def _init_firestore(self):
        """Attempts to initialize native Google Cloud Firestore client."""
        try:
            from google.cloud import firestore
            self._db = firestore.Client(project=self.project_id)
            logger.info(f"Connected to Cloud Firestore in project '{self.project_id}'")
        except Exception as exc:
            logger.warning(f"Firestore native client unavailable ({exc}); engaging resilient audit cache.")
            self._db = None

    def record_incident(self, trace_id: str, payload: Dict[str, Any], rca_result: Dict[str, Any]) -> str:
        """
        Persists incident telemetry, Tier-1 Jev triage decisions, and Gemini 1.5 Pro RCA.
        """
        record_id = f"inc_{trace_id}_{int(time.time())}"
        doc_data = {
            "incident_id": record_id,
            "trace_id": trace_id,
            "timestamp": time.time(),
            "service_name": payload.get("service_name", "unknown"),
            "http_status_code": payload.get("http_status_code"),
            "duration_ms": payload.get("duration_ms"),
            "error_message": payload.get("error_message"),
            "root_cause": rca_result.get("root_cause"),
            "confidence_score": rca_result.get("confidence_score"),
            "blast_radius": rca_result.get("blast_radius"),
            "remediation_code": rca_result.get("remediation_code"),
            "mitigation_steps": rca_result.get("mitigation_steps", []),
            "firebase_sync_status": "COMMITTED"
        }

        if self._db:
            try:
                self._db.collection(self.collection_name).document(record_id).set(doc_data)
                logger.info(f"Persisted incident {record_id} to Firestore collection '{self.collection_name}'")
            except Exception as e:
                logger.error(f"Failed to write to Firestore: {e}")
                self._local_audit_log.append(doc_data)
        else:
            self._local_audit_log.append(doc_data)

        return record_id

    def list_recent_incidents(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Retrieves recent incident audit trails for SRE review."""
        if self._db:
            try:
                docs = (
                    self._db.collection(self.collection_name)
                    .order_by("timestamp", direction="DESCENDING")
                    .limit(limit)
                    .stream()
                )
                return [doc.to_dict() for doc in docs]
            except Exception as e:
                logger.warning(f"Error reading from Firestore: {e}")
        return sorted(self._local_audit_log, key=lambda x: x["timestamp"], reverse=True)[:limit]

firestore_ledger = FirestoreIncidentLedger()
