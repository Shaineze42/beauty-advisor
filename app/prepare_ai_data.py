import csv
import json
import random
from pathlib import Path


BASE_DIR = Path("data/processed")
REPORT_DIR = Path("reports")

PRODUCTS_PATH = BASE_DIR / "products_raw.csv"
USERS_PATH = BASE_DIR / "users_raw.csv"
INTERACTIONS_PATH = BASE_DIR / "interactions_raw.csv"
REQUESTS_PATH = BASE_DIR / "recommendation_requests.json"

FEATURES_PATH = BASE_DIR / "ai_features.csv"
TRAIN_PATH = BASE_DIR / "train.csv"
TEST_PATH = BASE_DIR / "test.csv"
REPORT_PATH = REPORT_DIR / "ai_data_report.json"


def read_csv(path):
    with path.open("r", encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def write_csv(path, rows):
    if not rows:
        path.write_text("", encoding="utf-8")
        return

    fieldnames = list(rows[0].keys())
    temporary_path = path.with_suffix(path.suffix + ".tmp")

    with temporary_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    temporary_path.replace(path)


def normalize(value):
    return str(value or "").strip().lower()


def to_float(value):
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None


def to_bool(value):
    return normalize(value) in {"true", "1", "yes", "oui"}


def interaction_label(row):
    interaction_type = normalize(row.get("interaction_type"))
    rating = to_float(row.get("rating"))

    if interaction_type in {"favorite", "purchase"}:
        return "positive", "1"

    if interaction_type == "review" and rating is not None:
        if rating >= 4:
            return "positive", "1"

        if rating <= 2:
            return "negative", "0"

        return "neutral", ""

    return "unknown", ""


products = read_csv(PRODUCTS_PATH)
users = read_csv(USERS_PATH)
interactions = read_csv(INTERACTIONS_PATH)

if not products or not users:
    raise ValueError(
        "Les fichiers produits et utilisateurs ne doivent pas être vides."
    )

required_product_columns = {
    "product_id",
    "price",
    "finish",
    "suitable_skin_type",
    "available",
}

required_user_columns = {
    "user_id",
    "skin_type",
    "preferred_finish",
    "max_budget",
}

missing_product_columns = (
    required_product_columns - set(products[0])
)

missing_user_columns = required_user_columns - set(users[0])

if missing_product_columns:
    raise ValueError(
        "Colonnes produits manquantes : "
        f"{sorted(missing_product_columns)}"
    )

if missing_user_columns:
    raise ValueError(
        "Colonnes utilisateurs manquantes : "
        f"{sorted(missing_user_columns)}"
    )


interaction_by_pair = {}

for interaction in interactions:
    key = (
        interaction.get("user_id"),
        interaction.get("product_id"),
    )
    interaction_by_pair[key] = interaction


feature_rows = []

for user in users:
    user_id = user.get("user_id", "")
    user_budget = to_float(user.get("max_budget"))

    for product in products:
        product_id = product.get("product_id", "")
        price = to_float(product.get("price"))

        interaction = interaction_by_pair.get(
            (user_id, product_id),
            {},
        )

        signal, label = interaction_label(interaction)

        budget_ok = (
            price is not None
            and user_budget is not None
            and price <= user_budget
        )

        price_budget_ratio = ""

        if price is not None and user_budget not in (None, 0):
            price_budget_ratio = round(
                price / user_budget,
                4,
            )

        feature_rows.append(
            {
                "user_id": user_id,
                "product_id": product_id,
                "skin_type": user.get("skin_type", ""),
                "complexion": user.get("complexion", ""),
                "undertone": user.get("undertone", ""),
                "preferred_finish": user.get(
                    "preferred_finish",
                    "",
                ),
                "preferred_style": user.get(
                    "preferred_style",
                    "",
                ),
                "max_budget": user.get("max_budget", ""),
                "category": product.get("category", ""),
                "price": product.get("price", ""),
                "shade": product.get("shade", ""),
                "finish": product.get("finish", ""),
                "suitable_skin_type": product.get(
                    "suitable_skin_type",
                    "",
                ),
                "available": product.get("available", ""),
                "skin_match": int(
                    normalize(user.get("skin_type"))
                    == normalize(
                        product.get("suitable_skin_type")
                    )
                ),
                "finish_match": int(
                    normalize(user.get("preferred_finish"))
                    == normalize(product.get("finish"))
                ),
                "budget_ok": int(budget_ok),
                "available_flag": int(
                    to_bool(product.get("available"))
                ),
                "price_budget_ratio": price_budget_ratio,
                "interaction_type": interaction.get(
                    "interaction_type",
                    "",
                ),
                "rating": interaction.get("rating", ""),
                "interaction_signal": signal,
                "label": label,
            }
        )


positive_rows = [
    row
    for row in feature_rows
    if row["label"] == "1"
]

real_negative_rows = [
    row
    for row in feature_rows
    if row["label"] == "0"
]

negative_candidates_by_user = {}

for row in feature_rows:
    if row["label"] == "":
        negative_candidates_by_user.setdefault(
            row["user_id"],
            [],
        ).append(row)

random_generator = random.Random(42)
sampled_negative_rows = []

for positive_row in positive_rows:
    user_id = positive_row["user_id"]

    candidates = negative_candidates_by_user.get(
        user_id,
        [],
    )

    if candidates:
        candidate = random_generator.choice(
            candidates
        ).copy()

        candidate["interaction_signal"] = (
            "sampled_non_interaction"
        )
        candidate["label"] = "0"
        candidate["interaction_type"] = ""
        candidate["rating"] = ""

        sampled_negative_rows.append(candidate)

labeled_rows = (
    positive_rows
    + real_negative_rows
    + sampled_negative_rows
)

shuffled_rows = labeled_rows.copy()
random.Random(42).shuffle(shuffled_rows)

if len(shuffled_rows) > 1:
    split_index = max(
        1,
        int(len(shuffled_rows) * 0.8),
    )
    split_index = min(
        split_index,
        len(shuffled_rows) - 1,
    )
else:
    split_index = len(shuffled_rows)

train_rows = shuffled_rows[:split_index]
test_rows = shuffled_rows[split_index:]


write_csv(FEATURES_PATH, feature_rows)
write_csv(TRAIN_PATH, train_rows)
write_csv(TEST_PATH, test_rows)


missing_values = {}

for row in feature_rows:
    for column, value in row.items():
        if value == "":
            missing_values[column] = (
                missing_values.get(column, 0) + 1
            )


request_count = 0

if REQUESTS_PATH.exists():
    with REQUESTS_PATH.open(
        "r",
        encoding="utf-8",
    ) as file:
        request_count = len(json.load(file))


report = {
    "status": "success",
    "users": len(users),
    "products": len(products),
    "source_interactions": len(interactions),
    "unique_user_product_pairs": len(
        interaction_by_pair
    ),
    "feature_rows": len(feature_rows),
    "labeled_rows": len(labeled_rows),
    "train_rows": len(train_rows),
    "test_rows": len(test_rows),
    "positive_rows": len(positive_rows),
    "real_negative_rows": len(real_negative_rows),
    "sampled_negative_rows": len(
        sampled_negative_rows
    ),
    "negative_rows": (
        len(real_negative_rows)
        + len(sampled_negative_rows)
    ),
    "recommendation_requests": request_count,
    "missing_values": missing_values,
}


REPORT_DIR.mkdir(parents=True, exist_ok=True)

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
    file.write("\n")


print("✅ Préparation des données IA terminée")
print(f"Lignes de variables : {len(feature_rows)}")
print(f"Lignes avec label : {len(labeled_rows)}")
print(f"Entraînement : {len(train_rows)}")
print(f"Test : {len(test_rows)}")
print(f"Rapport créé : {REPORT_PATH}")