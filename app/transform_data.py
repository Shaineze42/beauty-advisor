import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

load_dotenv()

DATA_DIR = Path(os.getenv("DATA_DIR", "/app/data"))
VALIDATED_DIR = DATA_DIR / "validated"
PROCESSED_DIR = DATA_DIR / "processed"
REPORTS_DIR = Path(os.getenv("REPORTS_DIR", "/app/reports"))

PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

TEXT_COLUMNS = {
    "brand",
    "name",
    "category",
    "shade",
    "finish",
    "suitable_skin_type",
    "skin_type",
    "complexion",
    "undertone",
    "preferred_finish",
    "preferred_style",
    "interaction_type",
}

VALUE_MAP = {
    "seche": "sèche",
    "levres": "lèvres",
    "sophistique": "sophistiqué",
}


def normalize_text(value):
    if pd.isna(value):
        return value

    normalized = str(value).strip().lower()
    return VALUE_MAP.get(normalized, normalized)


def transform_csv(filename: str) -> int:
    source = VALIDATED_DIR / filename
    destination = PROCESSED_DIR / filename

    dataframe = pd.read_csv(source)

    for column in TEXT_COLUMNS.intersection(
        dataframe.columns
    ):
        dataframe[column] = dataframe[column].map(
            normalize_text
        )

    if "price" in dataframe.columns:
        dataframe["price"] = pd.to_numeric(
            dataframe["price"],
            errors="raise",
        ).round(2)

    if "max_budget" in dataframe.columns:
        dataframe["max_budget"] = pd.to_numeric(
            dataframe["max_budget"],
            errors="raise",
        ).round(2)

    if "rating" in dataframe.columns:
        dataframe["rating"] = pd.to_numeric(
            dataframe["rating"],
            errors="coerce",
        ).astype("Int64")

    if "available" in dataframe.columns:
        dataframe["available"] = (
            dataframe["available"]
            .astype(str)
            .str.strip()
            .str.lower()
            .map(
                {
                    "true": True,
                    "false": False,
                    "1": True,
                    "0": False,
                    "yes": True,
                    "no": False,
                }
            )
        )

    for column in {
        "created_at",
        "updated_at",
    }.intersection(dataframe.columns):
        dataframe[column] = pd.to_datetime(
            dataframe[column],
            errors="raise",
        ).dt.strftime("%Y-%m-%d")

    dataframe.to_csv(
        destination,
        index=False,
    )

    return len(dataframe)


def transform_json() -> int:
    source = (
        VALIDATED_DIR
        / "recommendation_requests_raw.json"
    )

    destination = (
        PROCESSED_DIR
        / "recommendation_requests.json"
    )

    with source.open(
        "r",
        encoding="utf-8",
    ) as file:
        documents = json.load(file)

    for document in documents:
        context = document.get("context", {})

        for key in {
            "occasion",
            "style",
            "finish",
        }:
            if key in context:
                context[key] = normalize_text(
                    context[key]
                )

        if "preferred_colors" in context:
            context["preferred_colors"] = [
                normalize_text(color)
                for color in context["preferred_colors"]
            ]

        if "budget" in context:
            context["budget"] = round(
                float(context["budget"]),
                2,
            )

        if "created_at" in document:
            document["created_at"] = pd.to_datetime(
                document["created_at"],
                errors="raise",
                utc=True,
            ).isoformat()

    with destination.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            documents,
            file,
            ensure_ascii=False,
            indent=2,
        )

    return len(documents)


def main() -> None:
    files = [
        "products_raw.csv",
        "users_raw.csv",
        "interactions_raw.csv",
    ]

    processed_rows = {}

    for filename in files:
        processed_rows[filename] = transform_csv(
            filename
        )

    processed_rows[
        "recommendation_requests.json"
    ] = transform_json()

    report = {
        "generated_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "processed_files": processed_rows,
        "total_processed_rows": sum(
            processed_rows.values()
        ),
    }

    report_path = (
        REPORTS_DIR
        / "transformation_report.json"
    )

    with report_path.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            report,
            file,
            ensure_ascii=False,
            indent=2,
        )

    print("✅ Transformation terminée")
    print(
        f"Lignes transformées : "
        f"{report['total_processed_rows']}"
    )
    print(
        f"✅ Rapport créé dans {report_path}"
    )


if __name__ == "__main__":
    main()