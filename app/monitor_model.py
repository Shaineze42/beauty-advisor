"""
Monitoring de Beauty Advisor et règles de recalibration.

Compare l'état courant (données, évaluation) à des seuils et à une référence,
puis écrit reports/monitoring_report.json avec une décision explicite :
  ok       : rien à faire
  warning  : à surveiller
  alert    : recalibrer / relancer la chaîne (python run_bloc4.py)

Usage :
  python monitor_model.py                   # contrôle (crée la référence si absente)
  python monitor_model.py --set-reference   # fige l'état actuel comme référence
"""
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


PROCESSED_DIR = Path("data/processed")
AI_REPORT_PATH = Path("reports/ai_data_report.json")
EVAL_REPORT_PATH = Path("reports/evaluation_personalized_report.json")
EXPLAIN_REPORT_PATH = Path("reports/explainability_report.json")
REFERENCE_PATH = Path("reports/monitoring_reference.json")
REPORT_PATH = Path("reports/monitoring_report.json")

SOURCE_FILES = ["products_raw.csv", "users_raw.csv", "interactions_raw.csv"]

# Seuils critiques : le produit doit TOUJOURS respecter ces règles métier.
CRITICAL_RULES = {
    "budget_compliance": 1.0,
    "compatibility_rate": 1.0,
    "availability_rate": 1.0,
    "explanation_coverage": 1.0,
    "no_duplicates_rate": 1.0,
    "max_products_respected_rate": 1.0,
}
MAX_LATENCY_SECONDS = 0.5
MIN_FILL_RATE = 0.5
MAX_METRIC_DROP = 0.10

RETRAINING_POLICY = [
    "sources modifiées depuis la dernière préparation (hash différent)",
    "règle critique métier violée (budget, compatibilité, disponibilité, explications)",
    "hit rate fonctionnel inférieur ou égal à la baseline aléatoire",
    "baisse de plus de 10 points d'une métrique par rapport à la référence",
    "nouvelles interactions ajoutées (régénération du split et réévaluation)",
]


def read_json(path):
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def file_hash(path):
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()[:16]


def current_source_hash():
    return {
        name: file_hash(PROCESSED_DIR / name)
        for name in SOURCE_FILES
        if (PROCESSED_DIR / name).exists()
    }


def make_check(name, status, detail):
    return {"check": name, "status": status, "detail": detail}


def snapshot(evaluation, source_hash):
    return {
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "dataset_version": evaluation.get("dataset_version"),
        "source_hash": source_hash,
        "business_metrics": evaluation.get("business_metrics"),
        "diagnostic_metrics": evaluation.get("diagnostic_metrics"),
    }


def run_checks(evaluation, ai_report, explain_report, reference, source_hash):
    checks = []
    business = evaluation.get("business_metrics", {})
    diagnostic = evaluation.get("diagnostic_metrics", {})
    random_baseline = evaluation.get("baselines", {}).get("random_eligible", {})

    # 1. Règles métier critiques
    for metric, threshold in CRITICAL_RULES.items():
        value = business.get(metric)
        ok = value is not None and value >= threshold
        checks.append(
            make_check(
                f"règle critique : {metric}",
                "ok" if ok else "alert",
                f"valeur {value} (seuil {threshold})",
            )
        )

    # 2. Explicabilité
    explain_ok = bool(explain_report) and explain_report.get("status") == "success"
    checks.append(
        make_check(
            "tests d'explicabilité",
            "ok" if explain_ok else "alert",
            "réussis" if explain_ok else "échec ou rapport absent",
        )
    )

    # 3. Pertinence face à la baseline aléatoire
    hit = diagnostic.get("hit_functional")
    random_hit = random_baseline.get("hit_functional")
    if hit is None or random_hit is None:
        checks.append(make_check("pertinence vs aléatoire", "warning", "métriques absentes"))
    else:
        checks.append(
            make_check(
                "pertinence vs aléatoire",
                "ok" if hit > random_hit else "alert",
                f"hit rate fonctionnel {hit} contre {random_hit} (aléatoire)",
            )
        )

    # 4. Performance et remplissage
    latency = business.get("latency_seconds")
    checks.append(
        make_check(
            "latence moyenne",
            "ok" if latency is not None and latency <= MAX_LATENCY_SECONDS else "warning",
            f"{latency} s (seuil {MAX_LATENCY_SECONDS} s)",
        )
    )
    fill = business.get("fill_rate")
    checks.append(
        make_check(
            "fill rate (routines complètes)",
            "ok" if fill is not None and fill >= MIN_FILL_RATE else "warning",
            f"{fill} (seuil {MIN_FILL_RATE}, limité par le budget total)",
        )
    )

    # 5. Fraîcheur : l'évaluation porte-t-elle sur les données actuelles ?
    ai_hash = (ai_report or {}).get("source_hash")
    eval_hash = evaluation.get("source_hash")
    checks.append(
        make_check(
            "évaluation à jour avec la préparation IA",
            "ok" if ai_hash and ai_hash == eval_hash else "alert",
            "hash identiques" if ai_hash == eval_hash else "évaluation calculée sur d'autres données",
        )
    )
    checks.append(
        make_check(
            "données sources inchangées depuis la préparation",
            "ok" if ai_hash and ai_hash == source_hash else "alert",
            "hash identiques" if ai_hash == source_hash else "sources modifiées : relancer run_bloc4.py",
        )
    )

    # 6. Dérive par rapport à la référence
    if reference:
        for metric in ("hit_functional", "precision_functional", "hit_category"):
            now = diagnostic.get(metric)
            before = (reference.get("diagnostic_metrics") or {}).get(metric)
            if now is None or before is None:
                continue
            drop = round(before - now, 4)
            checks.append(
                make_check(
                    f"dérive : {metric}",
                    "ok" if drop <= MAX_METRIC_DROP else "alert",
                    f"référence {before}, actuel {now}, baisse {drop}",
                )
            )
    else:
        checks.append(
            make_check("dérive", "warning", "aucune référence : créée automatiquement")
        )

    return checks


def decide(checks):
    statuses = {check["status"] for check in checks}
    if "alert" in statuses:
        return "alert", "Recalibrer : relancer `python run_bloc4.py` et analyser les métriques en alerte."
    if "warning" in statuses:
        return "warning", "Surveiller : aucun blocage, mais des points à examiner."
    return "ok", "Aucune action : le système respecte toutes les règles."


def main():
    evaluation = read_json(EVAL_REPORT_PATH)

    if not evaluation:
        print("❌ Rapport d'évaluation introuvable : lancer evaluate_personalized.py d'abord.")
        sys.exit(2)

    ai_report = read_json(AI_REPORT_PATH)
    explain_report = read_json(EXPLAIN_REPORT_PATH)
    source_hash = current_source_hash()

    if "--set-reference" in sys.argv:
        REFERENCE_PATH.write_text(
            json.dumps(snapshot(evaluation, source_hash), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"✅ Référence enregistrée : {REFERENCE_PATH}")
        return

    reference = read_json(REFERENCE_PATH)
    reference_created = False

    if reference is None:
        reference = snapshot(evaluation, source_hash)
        REFERENCE_PATH.write_text(
            json.dumps(reference, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        reference_created = True
        reference_for_drift = None
    else:
        reference_for_drift = reference

    checks = run_checks(evaluation, ai_report, explain_report, reference_for_drift, source_hash)
    status, action = decide(checks)

    report = {
        "status": status,
        "recommended_action": action,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "dataset_version": evaluation.get("dataset_version"),
        "reference_created_this_run": reference_created,
        "checks": checks,
        "retraining_policy": RETRAINING_POLICY,
        "summary": {
            "ok": sum(c["status"] == "ok" for c in checks),
            "warning": sum(c["status"] == "warning" for c in checks),
            "alert": sum(c["status"] == "alert" for c in checks),
        },
    }

    REPORT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    icons = {"ok": "✅", "warning": "⚠️ ", "alert": "❌"}
    print(f"Monitoring : {icons[status]} {status.upper()}")
    print(f"Contrôles : {report['summary']}")
    for check in checks:
        if check["status"] != "ok":
            print(f"{icons[check['status']]} {check['check']} : {check['detail']}")
    print(f"Action : {action}")
    print(f"Rapport créé : {REPORT_PATH}")

    if status == "alert":
        sys.exit(1)


if __name__ == "__main__":
    main()