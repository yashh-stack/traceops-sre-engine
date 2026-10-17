output "cloud_run_uri" {
  description = "The verified HTTPS URI of the deployed Cloud Run service"
  value       = google_cloud_run_v2_service.traceops_engine.uri
}

output "pubsub_topic_id" {
  description = "The Pub/Sub topic ID for incident events"
  value       = google_pubsub_topic.incident_events.id
}
