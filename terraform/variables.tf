variable "gcp_project" {
  description = "GCP project ID to deploy resources into"
  type        = string
  # No default — operator must supply this value
}

variable "region" {
  description = "GCP region for the VM"
  type        = string
  default     = "us-west1"
}

variable "zone" {
  description = "GCP zone for the VM"
  type        = string
  default     = "us-west1-a"
}

variable "machine_type" {
  description = "GCE machine type for the SuperBot VM"
  type        = string
  default     = "e2-small"
}

variable "bot_disk_size_gb" {
  description = "Boot disk size in GB"
  type        = number
  default     = 20
}
