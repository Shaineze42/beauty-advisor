# Beauty Advisor

Plateforme Data/IA de recommandation de routines makeup personnalisées.
Le système combine profils utilisateurs, catalogue produits et interactions pour proposer une routine
(teint, blush, yeux, lèvres) **compatible, dans le budget et expliquée**.

Aucune photo, donnée biométrique, donnée médicale ou tracking de navigation n'est utilisée.
Le type de peau est déclaré par l'utilisateur (pas de diagnostic).

## Architecture

```text
Sources CSV/JSON -> validation -> transformation -> PostgreSQL + MongoDB
                                      |
                                      v
        préparation IA -> moteur de scoring hybride -> routine + explications
                                      |
                        évaluation, biais, monitoring, API
```

| Bloc | Contenu | Scripts (`app/`) |
|---|---|---|
| 3. Pipelines | validation, transformation, chargement | `validate_data.py`, `transform_data.py`, `load_pg.py`, `load_mongo.py`, `pipeline.py` |
| 4. IA | données, moteur, explications, évaluation | `expand_raw_data.py`, `prepare_ai_data.py`, `recommendation_engine.py`, `evaluate_personalized.py`, `test_explainability.py` |
| 4. Qualité et exploitation | API, tests, biais, charge, monitoring | `api.py`, `quality_check.py`, `tests/`, `bias_check.py`, `scale_test_engine.py`, `monitor_model.py`, `run_bloc4.py` |

## Démarrage rapide

```bash
cp .env.example .env            # renseigner les mots de passe
docker compose up -d --build
docker compose exec app python run_bloc4.py --regenerate   # chaîne complète reproductible (seed 42)
docker compose exec app python monitor_model.py --set-reference
```

Commandes utiles :

```bash
docker compose exec app python run_bloc4.py               # relancer la chaîne sans régénérer les données
docker compose exec app python quality_check.py           # qualité, sécurité, 37 tests unitaires
docker compose exec app python recommendation_engine.py --user-id user_001
docker compose ps                                         # état des services (api en "healthy")
```

## API d'inférence

```bash
curl "http://localhost:8000/health"
curl "http://localhost:8000/recommend?user_id=user_001&max_products=4"
curl "http://localhost:8000/metrics"
```

Entrées validées (`user_id` en `[A-Za-z0-9_-]{1,50}`, `max_products` de 1 à 6), erreurs propres (400, 404, 405),
aucun secret dans le service, données en lecture seule, conteneur non-root sans privilèges.

## Méthode

- **Score de compatibilité** : `0,25 peau + 0,20 fini + 0,20 budget + 0,10 disponibilité + 0,15 interaction + 0,10 historique`.
- **Règle de filtrage** : produit disponible, prix <= budget, compatible avec la peau OU le fini.
- **Routine** : un produit par catégorie d'abord, puis complétion, budget total jamais dépassé.
- **Évaluation** : split par utilisateur (seed 42), historique issu du train uniquement, produits déjà vus exclus,
  comparaison à 2 baselines (aléatoire, règle peau + fini).

## Rapports (`reports/`)

| Rapport | Contenu |
|---|---|
| `ai_data_report.json` | jeu de données IA, split, hash des sources |
| `evaluation_personalized_report.json` | métriques métier, diagnostic, baselines |
| `explainability_report.json` | tests d'explicabilité et contre-tests |
| `bias_report.json` | équité par groupe, concentration par marque |
| `engine_scalability_report.json` | latence du moteur de 50 à 50 000 produits |
| `monitoring_report.json` | décision ok / warning / alert et règles de recalibration |
| `quality_report.json` | qualité du code, sécurité, tests unitaires |
| `chain_report.json` | durée et statut de chaque étape de la chaîne |

## CI/CD (GitHub Actions)

`.github/workflows/ci.yml` : à chaque push, pull request, et chaque lundi (recalibration planifiée) :
contrôle qualité et tests, chaîne IA complète, validation Docker, puis publication de l'image sur GHCR (branche `main`).
Une alerte de monitoring fait échouer le workflow et déclenche la notification GitHub.

## Limites assumées

- Données synthétiques (20 utilisateurs, 50 produits, 100 interactions) : les métriques sont indicatives.
- La précision exacte est un diagnostic : plusieurs produits différents peuvent convenir à la même personne.
- Les négatifs échantillonnés ne sont pas de vrais rejets utilisateurs.
- La pertinence fonctionnelle reprend la règle de génération des interactions (évaluation en partie circulaire).
- Aucun modèle supervisé : 100 interactions ne permettraient pas d'en valider un sérieusement.