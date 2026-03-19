output "vm_external_ip" {
  description = "External IP address of the SuperBot VM"
  value       = google_compute_instance.superbot.network_interface[0].access_config[0].nat_ip
}

output "vm_name" {
  description = "Name of the SuperBot VM"
  value       = google_compute_instance.superbot.name
}

output "service_account_email" {
  description = "Email of the SuperBot service account"
  value       = google_service_account.superbot.email
}
