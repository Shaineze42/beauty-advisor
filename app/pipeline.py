import json
import logging
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
REPORTS_DIR = Path("/app/reports")

REPORTS_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

LOG_PATH = REPORTS_DIR / "pipeline.log"
REPORT_PATH = REPORTS_DIR / "pipeline_report.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(
            LOG_PATH,
            encoding="utf-8",
        ),
    ],
)

logger = logging.getLogger("beauty_pipeline")

STEPS = [
    ("validation", "validate_data.py"),
    ("transformation", "transform_data.py"),
    ("chargement_postgresql", "load_pg.py"),
    ("chargement_mongodb", "load_mongo.py"),
]


def utc_now() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat()


def run_step(
    name: str,
    script_name: str,
) -> dict:
    script_path = APP_DIR / script_name
    started_at = utc_now()
    start_time = time.perf_counter()

    if not script_path.exists():
        raise FileNotFoundError(
            f"Script introuvable : {script_path}"
        )

    logger.info(
        "Début de l'étape : %s",
        name,
    )

    result = subprocess.run(
        [
            sys.executable,
            str(script_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    duration = round(
        time.perf_counter() - start_time,
        2,
    )

    if result.stdout:
        for line in result.stdout.strip().splitlines():
            logger.info(line)

    if result.stderr:
        for line in result.stderr.strip().splitlines():
            logger.warning(line)

    step_result = {
        "name": name,
        "script": script_name,
        "status": (
            "success"
            if result.returncode == 0
            else "failed"
        ),
        "started_at": started_at,
        "finished_at": utc_now(),
        "duration_seconds": duration,
        "return_code": result.returncode,
    }

    if result.returncode != 0:
        logger.error(
            "Échec de l'étape %s avec le code %s",
            name,
            result.returncode,
        )

        raise RuntimeError(
            f"L'étape {name} a échoué."
        )

    logger.info(
        "Étape terminée : %s en %s secondes",
        name,
        duration,
    )

    return step_result


def write_report(report: dict) -> None:
    with REPORT_PATH.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            report,
            file,
            ensure_ascii=False,
            indent=2,
        )


def main() -> None:
    pipeline_started_at = utc_now()
    pipeline_start = time.perf_counter()
    steps = []
    status = "success"

    logger.info(
        "===== DÉBUT DU PIPELINE BEAUTY ADVISOR ====="
    )

    try:
        for name, script_name in STEPS:
            steps.append(
                run_step(
                    name,
                    script_name,
                )
            )

    except Exception as error:
        status = "failed"

        logger.exception(
            "Le pipeline a échoué : %s",
            error,
        )

        raise

    finally:
        total_duration = round(
            time.perf_counter() - pipeline_start,
            2,
        )

        report = {
            "pipeline": "Beauty Advisor",
            "status": status,
            "started_at": pipeline_started_at,
            "finished_at": utc_now(),
            "duration_seconds": total_duration,
            "steps": steps,
        }

        write_report(report)

        logger.info(
            "Rapport créé : %s",
            REPORT_PATH,
        )

        logger.info(
            "===== FIN DU PIPELINE : %s =====",
            status.upper(),
        )


if __name__ == "__main__":
    main()