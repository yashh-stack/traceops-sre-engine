/**
 * TraceOps SRE Engine - Declarative GCP Infrastructure
 * Provisions Cloud Run, Pub/Sub topic, and Cloud Logging sink.
 */

terraform {
  required_version = ">= 1.5.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# 1. Cloud Run Service
resource "google_cloud_run_v2_service" "traceops_engine" {
  name     = "traceops-sre-engine"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    scaling {
      min_instance_count = 0
      max_instance_count = 3
    }

    containers {
      image = "gcr.io/${var.project_id}/traceops-sre-engine:latest"
      resources {
        limits = {
          cpu    = "2"
          memory = "2Gi"
        }
      }

      env {
        name  = "GCP_PROJECT"
        value = var.project_id
      }
      env {
        name  = "MODEL_NAME"
        value = "gemini-1.5-pro"
      }
      env {
        name  = "REGION"
        value = var.region
      }
    }
  }
}

# 2. Pub/Sub Topic for Incident Events
resource "google_pubsub_topic" "incident_events" {
  name = "traceops-incident-events"
}

# 3. Cloud Logging Sink routing error telemetry to Pub/Sub
resource "google_logging_project_sink" "incident_sink" {
  name        = "traceops-error-sink"
  destination = "pubsub.googleapis.com/${google_pubsub_topic.incident_events.id}"
  filter      = "severity >= ERROR OR httpRequest.status >= 500"

  unique_writer_identity = true
}

# Allow unauthenticated ingress for public health & triage endpoints
resource "google_cloud_run_v2_service_iam_member" "public_invoker" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.traceops_engine.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}
