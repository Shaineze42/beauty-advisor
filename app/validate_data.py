import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

load_dotenv()

DATA_DIR = Path(os.getenv("DATA_DIR", "/app/data"))
RAW_DIR = DATA_DIR / "raw"
VALIDATED_DIR = DATA_DIR / "validated"
REJECTED_DIR = DATA_DIR / "rejected"
REPORTS_DIR = Path(os.getenv("REPORTS_DIR", "/app/reports"))

for directory in (VALIDATED_DIR, REJECTED_DIR, REPORTS_DIR):
    directory.mkdir(parents=True, exist_ok=True)

REQUIRED = {
    "products_raw.csv": {
        "product_id",
        "brand",
        "name",
        "category",
        "price",
        "shade",
        "finish",
        "suitable_skin_type",
        "available",
        "updated_at",
    },
    "users_raw.csv": {
        "user_id",
        "skin_type",
        "complexion",
        "undertone",
        "preferred_finish",
        "preferred_style",
        "max_budget",
        "created_at",
    },
    "interactions_raw.csv": {
        "interaction_id",
        "user_id",
        "product_id",
        "interaction_type",
        "rating",
        "created_at",
    },
}

CATEGORIES = {
    "teint",
    "blush",
    "yeux",
    "levres",
    "lèvres",
}

SKIN_TYPES = {
    "seche",
    "sèche",
    "grasse",
    "mixte",
    "normale",
}

FINISHES = {
    "mat",
    "naturel",
    "glowy",
}

INTERACTIONS = {
    "favorite",
    "purchase",
    "review",
}


def empty(value) -> bool:
    return pd.isna(value) or str(value).strip() == ""


def valid_date(value) -> bool:
    return not empty(value) and not pd.isna(
        pd.to_datetime(value, errors="coerce")
    )


def add_rejection(
    rejections,
    source,
    row_number,
    reason,
    record,
):
    rejections.append(
        {
            "source": source,
            "row_number": row_number,
            "reason": reason,
            "record": json.dumps(
                record,
                ensure_ascii=False,
                default=str,
            ),
        }
    )


def validate_row(filename, row):
    errors = []
    record = row.to_dict()

    identifier_column = next(
        column
        for column in row.index
        if column.endswith("_id")
    )

    if empty(row[identifier_column]):
        errors.append(
            f"{identifier_column} manquant"
        )

    for column in REQUIRED[filename]:
        if column in {"shade", "rating"}:
            continue

        if empty(row[column]):
            errors.append(f"{column} manquant")

    if filename == "products_raw.csv":
        price = pd.to_numeric(
            row["price"],
            errors="coerce",
        )

        if pd.isna(price) or price < 0:
            errors.append("prix invalide")

        if (
            str(row["category"]).strip().lower()
            not in CATEGORIES
        ):
            errors.append("catégorie inconnue")

        if (
            str(row["finish"]).strip().lower()
            not in FINISHES
        ):
            errors.append("fini inconnu")

        if (
            str(row["available"]).strip().lower()
            not in {"true", "false", "1", "0", "yes", "no"}
        ):
            errors.append("disponibilité invalide")

        if not valid_date(row["updated_at"]):
            errors.append("date invalide")

    elif filename == "users_raw.csv":
        budget = pd.to_numeric(
            row["max_budget"],
            errors="coerce",
        )

        if pd.isna(budget) or budget < 0:
            errors.append("budget invalide")

        if (
            str(row["skin_type"]).strip().lower()
            not in SKIN_TYPES
        ):
            errors.append("type de peau inconnu")

        if (
            str(row["preferred_finish"]).strip().lower()
            not in FINISHES
        ):
            errors.append("fini préféré inconnu")

        if not valid_date(row["created_at"]):
            errors.append("date invalide")

    elif filename == "interactions_raw.csv":
        interaction = str(
            row["interaction_type"]
        ).strip().lower()

        rating = pd.to_numeric(
            row["rating"],
            errors="coerce",
        )

        if interaction not in INTERACTIONS:
            errors.append(
                "type d'interaction inconnu"
            )

        elif interaction == "review":
            if pd.isna(rating) or not 1 <= rating <= 5:
                errors.append(
                    "note invalide pour une évaluation"
                )

        elif not pd.isna(rating):
            errors.append("note non applicable")

        if not valid_date(row["created_at"]):
            errors.append("date invalide")

    return errors, record


def validate_csv(filename):
    source = RAW_DIR / filename
    destination = VALIDATED_DIR / filename
    rejections = []

    if not source.exists():
        add_rejection(
            rejections,
            filename,
            0,
            "Fichier absent",
            {},
        )
        return 0, 0, rejections

    dataframe = pd.read_csv(source)

    missing = REQUIRED[filename] - set(
        dataframe.columns
    )

    if missing:
        add_rejection(
            rejections,
            filename,
            0,
            "Colonnes manquantes : "
            + ", ".join(sorted(missing)),
            {},
        )
        return len(dataframe), 0, rejections

    valid_rows = []
    seen_ids = set()

    identifier_column = next(
        column
        for column in dataframe.columns
        if column.endswith("_id")
    )

    for index, row in dataframe.iterrows():
        row_number = index + 2
        identifier = str(
            row[identifier_column]
        ).strip()

        errors, record = validate_row(
            filename,
            row,
        )

        if identifier in seen_ids:
            errors.append(
                f"doublon de {identifier_column}"
            )
        else:
            seen_ids.add(identifier)

        if errors:
            add_rejection(
                rejections,
                filename,
                row_number,
                "; ".join(errors),
                record,
            )
        else:
            valid_rows.append(row)

    pd.DataFrame(
        valid_rows,
        columns=dataframe.columns,
    ).to_csv(
        destination,
        index=False,
    )

    return (
        len(dataframe),
        len(valid_rows),
        rejections,
    )


def validate_json():
    filename = "recommendation_requests_raw.json"
    source = RAW_DIR / filename
    destination = VALIDATED_DIR / filename
    rejections = []
    valid_documents = []

    if not source.exists():
        add_rejection(
            rejections,
            filename,
            0,
            "Fichier absent",
            {},
        )
        return 0, 0, rejections

    with source.open(
        "r",
        encoding="utf-8",
    ) as file:
        documents = json.load(file)

    if not isinstance(documents, list):
        add_rejection(
            rejections,
            filename,
            0,
            "Le JSON doit contenir une liste",
            documents,
        )
        return 0, 0, rejections

    seen_ids = set()

    for index, document in enumerate(
        documents,
        start=1,
    ):
        errors = []

        if not isinstance(document, dict):
            errors.append("document invalide")
        else:
            request_id = str(
                document.get("request_id", "")
            ).strip()

            user_id = str(
                document.get("user_id", "")
            ).strip()

            if not request_id:
                errors.append(
                    "request_id manquant"
                )
            elif request_id in seen_ids:
                errors.append(
                    "doublon de request_id"
                )
            else:
                seen_ids.add(request_id)

            if not user_id:
                errors.append("user_id manquant")

            if not isinstance(
                document.get("context"),
                dict,
            ):
                errors.append("context invalide")

            if not valid_date(
                document.get("created_at")
            ):
                errors.append("date invalide")

        if errors:
            add_rejection(
                rejections,
                filename,
                index,
                "; ".join(errors),
                document,
            )
        else:
            valid_documents.append(document)

    with destination.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            valid_documents,
            file,
            ensure_ascii=False,
            indent=2,
        )

    return (
        len(documents),
        len(valid_documents),
        rejections,
    )


def main():
    all_rejections = []
    sources = []

    for filename in REQUIRED:
        total, valid, rejections = validate_csv(
            filename
        )

        all_rejections.extend(rejections)

        sources.append(
            {
                "source": filename,
                "input_rows": total,
                "valid_rows": valid,
                "rejected_rows": len(rejections),
            }
        )

    total, valid, rejections = validate_json()

    all_rejections.extend(rejections)

    sources.append(
        {
            "source": (
                "recommendation_requests_raw.json"
            ),
            "input_rows": total,
            "valid_rows": valid,
            "rejected_rows": len(rejections),
        }
    )

    if all_rejections:
        pd.DataFrame(all_rejections).to_csv(
            REJECTED_DIR / "rejected_rows.csv",
            index=False,
        )

    report = {
        "generated_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "sources": sources,
        "total_input_rows": sum(
            item["input_rows"]
            for item in sources
        ),
        "total_valid_rows": sum(
            item["valid_rows"]
            for item in sources
        ),
        "total_rejected_rows": len(
            all_rejections
        ),
    }

    with (
        REPORTS_DIR / "validation_report.json"
    ).open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            report,
            file,
            ensure_ascii=False,
            indent=2,
        )

    print("✅ Validation terminée")
    print(
        f"Lignes valides : "
        f"{report['total_valid_rows']}"
    )
    print(
        f"Lignes rejetées : "
        f"{report['total_rejected_rows']}"
    )
    print(
        "✅ Rapport créé dans /app/reports"
    )


if __name__ == "__main__":
    main()