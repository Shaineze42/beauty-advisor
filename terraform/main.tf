# Beauty Advisor : même pile que docker/docker-compose.yml, décrite en Terraform.
# Données : PostgreSQL + MongoDB. Application : API. Monitoring : exporter, postgres-exporter, Prometheus, Grafana.

locals {
  docker_dir  = abspath("${path.module}/../docker")
  app_dir     = abspath("${path.module}/../app")
  data_dir    = abspath("${path.module}/../data")
  reports_dir = abspath("${path.module}/../reports")
}

# ---------- Réseau et volumes ----------
resource "docker_network" "beauty" {
  name = "${var.project}-network"
}

resource "docker_volume" "postgres" {
  name = "${var.project}-postgres-data"
}

resource "docker_volume" "mongo" {
  name = "${var.project}-mongo-data"
}

resource "docker_volume" "prometheus" {
  name = "${var.project}-prometheus-data"
}

resource "docker_volume" "grafana" {
  name = "${var.project}-grafana-data"
}

# ---------- Images ----------
resource "docker_image" "postgres" {
  name         = "postgres:15"
  keep_locally = true
}

resource "docker_image" "mongo" {
  name         = "mongo:7"
  keep_locally = true
}

resource "docker_image" "postgres_exporter" {
  name         = "prometheuscommunity/postgres-exporter:v0.15.0"
  keep_locally = true
}

resource "docker_image" "prometheus" {
  name         = "prom/prometheus:v2.54.1"
  keep_locally = true
}

resource "docker_image" "grafana" {
  name         = "grafana/grafana:11.2.0"
  keep_locally = true
}

resource "docker_image" "api" {
  name = "beauty-advisor-api:tf"
  build {
    context = local.app_dir
  }
  triggers = {
    dockerfile = filesha1("${local.app_dir}/Dockerfile")
    api        = filesha1("${local.app_dir}/api.py")
  }
}

resource "docker_image" "exporter" {
  name = "beauty-advisor-exporter:tf"
  build {
    context = "${local.docker_dir}/exporter"
  }
  triggers = {
    code = filesha1("${local.docker_dir}/exporter/exporter.py")
  }
}

# ---------- Couche données ----------
resource "docker_container" "postgres" {
  name    = "${var.project}-postgres"
  image   = docker_image.postgres.image_id
  restart = "unless-stopped"

  env = [
    "POSTGRES_DB=${var.postgres_db}",
    "POSTGRES_USER=${var.postgres_user}",
    "POSTGRES_PASSWORD=${var.postgres_password}",
  ]

  ports {
    internal = 5432
    external = var.postgres_port
    ip       = "127.0.0.1"
  }

  volumes {
    volume_name    = docker_volume.postgres.name
    container_path = "/var/lib/postgresql/data"
  }
  volumes {
    host_path      = "${local.docker_dir}/postgres/init.sql"
    container_path = "/docker-entrypoint-initdb.d/01_init.sql"
    read_only      = true
  }
  volumes {
    host_path      = "${local.docker_dir}/postgres/02_star_schema.sql"
    container_path = "/docker-entrypoint-initdb.d/02_star_schema.sql"
    read_only      = true
  }

  networks_advanced {
    name    = docker_network.beauty.name
    aliases = ["postgres"]
  }

  healthcheck {
    test     = ["CMD-SHELL", "pg_isready -U ${var.postgres_user} -d ${var.postgres_db}"]
    interval = "10s"
    timeout  = "5s"
    retries  = 5
  }
}

resource "docker_container" "mongodb" {
  name    = "${var.project}-mongodb"
  image   = docker_image.mongo.image_id
  restart = "unless-stopped"

  env = [
    "MONGO_INITDB_ROOT_USERNAME=${var.mongo_root_user}",
    "MONGO_INITDB_ROOT_PASSWORD=${var.mongo_root_password}",
    "MONGO_INITDB_DATABASE=${var.postgres_db}",
  ]

  volumes {
    volume_name    = docker_volume.mongo.name
    container_path = "/data/db"
  }

  networks_advanced {
    name    = docker_network.beauty.name
    aliases = ["mongodb"]
  }
}

# ---------- Couche application ----------
resource "docker_container" "api" {
  name    = "${var.project}-api"
  image   = docker_image.api.image_id
  restart = "unless-stopped"

  command = ["python", "api.py"]
  env     = ["API_HOST=0.0.0.0", "API_PORT=8000"]

  user          = "1000:1000"
  read_only     = true
  security_opts = ["no-new-privileges:true"]

  capabilities {
    drop = ["ALL"]
  }

  ports {
    internal = 8000
    external = var.api_port
    ip       = "127.0.0.1"
  }

  volumes {
    host_path      = local.data_dir
    container_path = "/app/data"
    read_only      = true
  }
  volumes {
    host_path      = local.reports_dir
    container_path = "/app/reports"
    read_only      = true
  }

  networks_advanced {
    name    = docker_network.beauty.name
    aliases = ["api"]
  }

  healthcheck {
    test     = ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"]
    interval = "15s"
    timeout  = "5s"
    retries  = 3
  }
}

# ---------- Monitoring ----------
resource "docker_container" "exporter" {
  name    = "${var.project}-exporter"
  image   = docker_image.exporter.image_id
  restart = "unless-stopped"

  env = ["API_URL=http://api:8000", "REPORTS_DIR=/reports"]

  user          = "1000:1000"
  read_only     = true
  security_opts = ["no-new-privileges:true"]

  capabilities {
    drop = ["ALL"]
  }

  volumes {
    host_path      = local.reports_dir
    container_path = "/reports"
    read_only      = true
  }

  networks_advanced {
    name    = docker_network.beauty.name
    aliases = ["exporter"]
  }

  depends_on = [docker_container.api]
}

resource "docker_container" "postgres_exporter" {
  name    = "${var.project}-postgres-exporter"
  image   = docker_image.postgres_exporter.image_id
  restart = "unless-stopped"

  env = [
    "DATA_SOURCE_URI=postgres:5432/${var.postgres_db}?sslmode=disable",
    "DATA_SOURCE_USER=${var.postgres_user}",
    "DATA_SOURCE_PASS=${var.postgres_password}",
  ]

  networks_advanced {
    name    = docker_network.beauty.name
    aliases = ["postgres-exporter"]
  }

  depends_on = [docker_container.postgres]
}

resource "docker_container" "prometheus" {
  name    = "${var.project}-prometheus"
  image   = docker_image.prometheus.image_id
  restart = "unless-stopped"

  command = [
    "--config.file=/etc/prometheus/prometheus.yml",
    "--storage.tsdb.path=/prometheus",
    "--storage.tsdb.retention.time=15d",
  ]

  ports {
    internal = 9090
    external = var.prometheus_port
    ip       = "127.0.0.1"
  }

  volumes {
    host_path      = "${local.docker_dir}/prometheus"
    container_path = "/etc/prometheus"
    read_only      = true
  }
  volumes {
    volume_name    = docker_volume.prometheus.name
    container_path = "/prometheus"
  }

  networks_advanced {
    name    = docker_network.beauty.name
    aliases = ["prometheus"]
  }

  depends_on = [docker_container.exporter, docker_container.postgres_exporter]
}

resource "docker_container" "grafana" {
  name    = "${var.project}-grafana"
  image   = docker_image.grafana.image_id
  restart = "unless-stopped"

  env = [
    "GF_SECURITY_ADMIN_USER=${var.grafana_user}",
    "GF_SECURITY_ADMIN_PASSWORD=${var.grafana_password}",
    "GF_USERS_ALLOW_SIGN_UP=false",
    "GF_ANALYTICS_REPORTING_ENABLED=false",
  ]

  ports {
    internal = 3000
    external = var.grafana_port
    ip       = "127.0.0.1"
  }

  volumes {
    host_path      = "${local.docker_dir}/grafana/provisioning"
    container_path = "/etc/grafana/provisioning"
    read_only      = true
  }
  volumes {
    host_path      = "${local.docker_dir}/grafana/dashboards"
    container_path = "/var/lib/grafana/dashboards"
    read_only      = true
  }
  volumes {
    volume_name    = docker_volume.grafana.name
    container_path = "/var/lib/grafana"
  }

  networks_advanced {
    name    = docker_network.beauty.name
    aliases = ["grafana"]
  }

  depends_on = [docker_container.prometheus]
}
