"""
Chaîne IA reproductible (n'altère PAS le pipeline du Bloc 3).

Usage :
  python run_bloc4.py               # chaîne complète sur les données actuelles
  python run_bloc4.py --regenerate  # régénère d'abord les données (seed 42)
  python run_bloc4.py --no-db       # sans PostgreSQL/MongoDB (validation + transformation seulement, utilisé par la CI)

Écrit reports/chain_report.json (durée et statut de chaque étape).
"""
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


APP_DIR = Path(__file__).resolve().parent
REPORT_PATH = Path("reports/chain_report.json")

results = []
chain_start = time.perf_counter()


def write_report(status):
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(
        json.dumps(
            {
                "status": status,
                "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "total_seconds": round(time.perf_counter() - chain_start, 2),
                "steps": results,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def run(script):
    print(f"\n▶ {script}")
    start = time.perf_counter()
    completed = subprocess.run([sys.executable, str(APP_DIR / script)], check=False)
    results.append(
        {
            "step": script,
            "status": "success" if completed.returncode == 0 else "failed",
            "seconds": round(time.perf_counter() - start, 2),
        }
    )

    if completed.returncode != 0:
        print(f"❌ Échec : {script}")
        write_report("failed")
        sys.exit(completed.returncode)


steps = []

if "--regenerate" in sys.argv:
    steps += ["expand_raw_data.py", "check_dataset.py"]

if "--no-db" in sys.argv:
    steps += ["validate_data.py", "transform_data.py"]
else:
    steps += ["pipeline.py"]

steps += [
    "prepare_ai_data.py",
    "test_explainability.py",
    "evaluate_personalized.py",
    "bias_check.py",
    "scale_test_engine.py",
    "monitor_model.py",
]

for step in steps:
    run(step)

write_report("success")
print("\n✅ Chaîne Bloc 4 terminée")