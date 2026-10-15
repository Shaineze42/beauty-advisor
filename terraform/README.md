# Terraform : déploiement de la pile Beauty Advisor

Décrit la même pile que `docker/docker-compose.yml` (réseau, volumes, PostgreSQL, MongoDB, API,
exporter, postgres-exporter, Prometheus, Grafana) avec le fournisseur `kreuzwerker/docker`.
Les ports sont différents (API 8100, Grafana 3100, Prometheus 9190, PostgreSQL 5532) : les deux
déploiements peuvent tourner en même temps.

## Utilisation

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars   # choisir les mots de passe
terraform init
terraform validate
terraform plan
terraform apply
```

Les conteneurs sont préfixés `ba-tf-`. Pour tout supprimer : `terraform destroy`.

## Remarques

- `terraform.tfvars` et l'état (`*.tfstate`) sont ignorés par Git : ils contiennent des secrets.
- L'API lit `data/` et `reports/` : lancer d'abord la chaîne (`./scripts/dc.sh exec app python run_bloc4.py --regenerate`)
  ou la pile Docker Compose une fois, pour que ces dossiers existent et soient remplis.
- Le déploiement cible un démon Docker local (on-premise). Pour un serveur distant ou une machine
  virtuelle cloud, seul `docker_host` change (`ssh://utilisateur@serveur`).
