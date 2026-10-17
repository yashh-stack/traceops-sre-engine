variable "project_id" {
  description = "The target Google Cloud project ID"
  type        = string
  default     = "builder-cup-511710"
}

variable "region" {
  description = "The default GCP region for resource deployment"
  type        = string
  default     = "us-central1"
}
