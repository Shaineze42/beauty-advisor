# Cahier des charges : solution d'IA Beauty Advisor (Bloc 4)

Organisation fictive, données synthétiques (graine 42). Aucune donnée réelle, aucune photo, aucune donnée biométrique ou médicale.

## 1. Contexte et problème métier

Beauty Advisor propose à un utilisateur une routine makeup de quatre produits (teint, blush, yeux, lèvres) compatible avec son profil, dans son budget, et expliquée. Les poids du score de recommandation étaient fixés à la main. Le besoin : un modèle dont les poids sont **appris sur les données**, **servi par une API**, **déployé et testé automatiquement**, **réentraîné** quand c'est utile et **surveillé** en production, sans jamais dégrader les règles métier.

## 2. Objectifs mesurables

| Objectif | Indicateur | Seuil |
|---|---|---|
| Qualité du modèle | AUC de contenu sur un jeu de test jamais vu | mesurée et comparée au modèle actif |
| Promotion d'un nouveau modèle | Gain d'AUC | au moins +0,01 |
| Pas de régression métier | Précision fonctionnelle | baisse de 0,02 au plus |
| Règles métier critiques | 6 taux (budget, compatibilité, disponibilité, explications, doublons, nombre de produits) | 100 % pour promouvoir |
| Dérive des données | PSI par caractéristique | stable < 0,10 ; surveiller 0,10 à 0,25 ; dérive à partir de 0,25 |
| Réactivité de l'API | Durée moyenne d'une requête | environ 8 ms mesurés en local (7 requêtes) |
| Qualité du code | Tests automatisés | 44 tests ML et API, tous verts en CI |

## 3. Périmètre

**Inclus** : apprentissage des poids (régression logistique), registre de versions, API de serving, conteneur, manifests Kubernetes, CI/CD, réentraînement planifié, détection de dérive, métriques de service.

**Exclus** : photos, diagnostic de peau, paiement, personnalisation en ligne par utilisateur en temps réel, entraînement sur données réelles.

## 4. Exigences fonctionnelles

| Réf. | Exigence | Statut |
|---|---|---|
| EF1 | Apprendre les poids de quatre signaux de contenu par régression logistique, validation croisée groupée par utilisateur | Appliqué |
| EF2 | Évaluer le candidat et le modèle actif sur le même test et décider de la promotion selon trois garde-fous | Appliqué |
| EF3 | Versionner chaque modèle (poids, données, métriques, décision) et permettre le retour arrière | Appliqué |
| EF4 | Exposer `POST /recommend` avec entrées validées et réponse expliquée par produit | Appliqué |
| EF5 | Exposer `GET /health`, `GET /model` et `GET /metrics` (format Prometheus) | Appliqué |
| EF6 | Réentraîner sur déclencheur (pas de modèle actif, dérive, données modifiées) ou à la demande | Appliqué |
| EF7 | Réentraînement planifié chaque lundi et manuel depuis GitHub, avec Pull Request automatique si un modèle est promu | Appliqué |
| EF8 | Détecter la dérive des données d'entrée (PSI) | Appliqué |
| EF9 | Brancher les métriques de l'API (service, modèle, dérive) sur Prometheus et Grafana | Appliqué |
| EF10 | Alertes sur arrêt de l'API, erreurs 5xx, latence, AUC du modèle servi et dérive des données | Appliqué (alertes visibles dans Prometheus et Grafana) |
| EF11 | Notification externe des alertes (e-mail, messagerie) | Prévu |

## 5. Exigences non fonctionnelles

| Réf. | Exigence | Statut |
|---|---|---|
| ENF1 | Explicabilité : chaque produit recommandé est accompagné de ses raisons | Appliqué |
| ENF2 | Sécurité : conteneur non-root, filesystem en lecture seule côté Kubernetes, clé d'API optionnelle (`API_KEY`), aucun secret dans le dépôt | Appliqué |
| ENF3 | Traçabilité : identifiant de requête (`X-Request-ID`), version du modèle servi dans `/health` et `/metrics` | Appliqué |
| ENF4 | Reproductibilité : graine fixe, empreinte (`data_hash`) des données dans chaque modèle | Appliqué |
| ENF5 | Disponibilité : 2 réplicas, sondes de santé, mise à l'échelle de 2 à 5 réplicas | Partiel (manifests validés par `kubeconform`, jamais déployés sur un cluster) |
| ENF6 | Confidentialité : données synthétiques uniquement | Appliqué |

## 6. Contraintes et hypothèses

- Les données sont synthétiques : les performances ne se transposent pas à des utilisateurs réels.
- Jeu de test de 40 lignes : les écarts de métriques sont bruités (intervalle de confiance par bootstrap dans le notebook).
- Les mêmes utilisateurs sont présents en entraînement et en test (un produit positif du test n'est jamais vu à l'entraînement pour le même utilisateur) : le test ne mesure pas la généralisation à de nouveaux utilisateurs.
- Quatre poids sur six sont appris : les deux autres sont calculés à partir des interactions passées, donc des labels (risque de fuite de cible).
- L'évaluation fonctionnelle est en partie circulaire : elle sert de garde-fou métier, pas de preuve de pertinence réelle.

## 7. Risques et réponses

| Risque | Réponse |
|---|---|
| Un modèle réentraîné est moins bon | Comparaison au modèle actif sur le même test, promotion refusée sans gain suffisant, retour arrière possible |
| Un modèle viole une règle métier | Promotion bloquée si l'un des six taux critiques est inférieur à 100 % |
| Les données changent | Détection de dérive par PSI, déclencheur de réentraînement |
| Une modification casse l'API | Tests automatiques, build de l'image et test de fumée du conteneur en CI |
| Le déploiement diverge du code | Manifests validés en CI, image publiée par la CI uniquement depuis `main` |

## 8. Critères d'acceptation

1. `python3 -m pytest tests/ml tests/api -q` : tous les tests passent.
2. `python3 retrain/retrain.py --dry-run` : affiche les déclencheurs et la décision sans rien écrire.
3. `python3 monitoring/drift.py --simulate` : signale une dérive sur les données décalées.
4. `GET /health` répond 200 avec la version du modèle ; `POST /recommend` renvoie 4 produits expliqués dans le budget.
5. La CI est verte sur chaque Pull Request et sur `main`.
