variable "docker_host" {
  description = "Socket du démon Docker (Docker Desktop sur Mac : unix:///var/run/docker.sock)."
  type        = string
  default     = "unix:///var/run/docker.sock"
}

variable "project" {
  description = "Préfixe des ressources (réseau, volumes, conteneurs)."
  type        = string
  default     = "ba-tf"
}

variable "postgres_db" {
  type    = string
  default = "beauty_advisor"
}

variable "postgres_user" {
  type    = string
  default = "beauty_user"
}

variable "postgres_password" {
  description = "Mot de passe PostgreSQL (jamais versionné : terraform.tfvars est ignoré par Git)."
  type        = string
  sensitive   = true
}

variable "mongo_root_user" {
  type    = string
  default = "admin"
}

variable "mongo_root_password" {
  type      = string
  sensitive = true
}

variable "grafana_user" {
  type    = string
  default = "admin"
}

variable "grafana_password" {
  type      = string
  sensitive = true
}

# Ports publiés sur 127.0.0.1. Valeurs différentes de la pile Docker Compose
# pour que les deux déploiements puissent coexister sur la même machine.
variable "api_port" {
  type    = number
  default = 8100
}

variable "grafana_port" {
  type    = number
  default = 3100
}

variable "prometheus_port" {
  type    = number
  default = 9190
}

variable "postgres_port" {
  type    = number
  default = 5532
}
