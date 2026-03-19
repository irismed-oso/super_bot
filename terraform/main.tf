# Verify Ubuntu 24.04 image family before applying:
# gcloud compute images list --filter='name~ubuntu-24' --project=ubuntu-os-cloud

terraform {
  required_version = ">= 1.5"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

provider "google" {
  project = var.gcp_project
  region  = var.region
}

# --- Service Account ---

resource "google_service_account" "superbot" {
  account_id   = "superbot-sa"
  display_name = "SuperBot Service Account"
}

# --- Compute Instance ---

resource "google_compute_instance" "superbot" {
  name         = "superbot-vm"
  machine_type = var.machine_type
  zone         = var.zone

  tags = ["superbot"]

  metadata = {
    enable-oslogin = "TRUE"
  }

  boot_disk {
    initialize_params {
      image = "ubuntu-os-cloud/ubuntu-2404-lts"
      size  = var.bot_disk_size_gb
      type  = "pd-balanced"
    }
  }

  network_interface {
    network = "default"
    access_config {
      # Ephemeral external IP
    }
  }

  metadata_startup_script = file("${path.module}/startup.sh")

  service_account {
    email  = google_service_account.superbot.email
    scopes = ["cloud-platform"]
  }
}

# --- Firewall (egress) ---

resource "google_compute_firewall" "superbot_egress" {
  name      = "superbot-egress"
  network   = "default"
  direction = "EGRESS"

  allow {
    protocol = "tcp"
    ports    = ["80", "443"]
  }

  destination_ranges = ["0.0.0.0/0"]
  target_tags        = ["superbot"]
}
