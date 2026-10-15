output "api_url" {
  description = "Santé de l'API"
  value       = "http://localhost:${var.api_port}/health"
}

output "grafana_url" {
  description = "Tableau de bord Grafana"
  value       = "http://localhost:${var.grafana_port}"
}

output "prometheus_url" {
  description = "Prometheus"
  value       = "http://localhost:${var.prometheus_port}"
}

output "containers" {
  description = "Conteneurs créés"
  value = [
    docker_container.postgres.name,
    docker_container.mongodb.name,
    docker_container.api.name,
    docker_container.exporter.name,
    docker_container.postgres_exporter.name,
    docker_container.prometheus.name,
    docker_container.grafana.name,
  ]
}
