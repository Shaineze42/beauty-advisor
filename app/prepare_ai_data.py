import csv
import hashlib
import json
import random
from datetime import datetime, timezone
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

DATASET_VERSION = "beauty-advisor-v1"
TEST_RATIO = 0.2
SPLIT_SEED = 42
NEGATIVE_SEED = 42
MIN_POSITIVES_TO_EVALUATE = 2

POSITIVE_DEFINITION = (
    "favorite, purchase, ou review avec note >= 4"
)
NEGATIVE_DEFINITION = (
    "review avec note <= 2 (rejet explicite), ou produit jamais "
    "interagi tiré au hasard sans remise (non-interaction échantillonnée, "
    "pas un rejet réel)"
)


def read_csv(path):
    with path.open("r", encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def write_csv(path, rows, fieldnames=None):
    if fieldnames is None:
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


def file_hash(path):
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def split_train_test(rows, test_ratio=TEST_RATIO, seed=SPLIT_SEED):
    """
    Découpe train/test PAR UTILISATEUR :
      - un utilisateur avec au moins 2 positifs voit au moins 1 positif
        en test et garde au moins 1 positif en train (signal personnalisé) ;
      - un utilisateur avec moins de 2 positifs reste entièrement en train
        et n'est pas évalué (un seul positif rendrait le rappel binaire) ;
      - un produit positif de test n'apparaît jamais dans le train pour
        le même utilisateur (pas de fuite de données).
    """
    split_rng = random.Random(seed)
    rows_by_user = {}

    for row in rows:
        rows_by_user.setdefault(row["user_id"], []).append(row)

    train_rows = []
    test_rows = []

    for user_id in sorted(rows_by_user):
        user_rows = rows_by_user[user_id]

        positives = sorted(
            (row for row in user_rows if row["label"] == "1"),
            key=lambda row: row["product_id"],
        )
        negatives = sorted(
            (row for row in user_rows if row["label"] == "0"),
            key=lambda row: row["product_id"],
        )

        split_rng.shuffle(positives)
        split_rng.shuffle(negatives)

        if len(positives) >= MIN_POSITIVES_TO_EVALUATE:
            n_test_positive = max(1, round(len(positives) * test_ratio))
            n_test_positive = min(n_test_positive, len(positives) - 1)
            test_positive = positives[:n_test_positive]
            train_positive = positives[n_test_positive:]
        else:
            test_positive = []
            train_positive = positives

        n_test_negative = round(len(negatives) * test_ratio)
        test_negative = negatives[:n_test_negative]
        train_negative = negatives[n_test_negative:]

        train_rows.extend(train_positive + train_negative)
        test_rows.extend(test_positive + test_negative)

    return train_rows, test_rows


def build_feature_rows(users, products, interaction_by_pair):
    feature_rows = []

    for user in users:
        user_id = user.get("user_id", "")
        user_budget = to_float(user.get("max_budget"))

        for product in products:
            product_id = product.get("product_id", "")
            price = to_float(product.get("price"))

            interaction = interaction_by_pair.get((user_id, product_id), {})
            signal, label = interaction_label(interaction)

            budget_ok = (
                price is not None
                and user_budget is not None
                and price <= user_budget
            )

            price_budget_ratio = ""

            if price is not None and user_budget not in (None, 0):
                price_budget_ratio = round(price / user_budget, 4)

            feature_rows.append(
                {
                    "user_id": user_id,
                    "product_id": product_id,
                    "skin_type": user.get("skin_type", ""),
                    "complexion": user.get("complexion", ""),
                    "undertone": user.get("undertone", ""),
                    "preferred_finish": user.get("preferred_finish", ""),
                    "preferred_style": user.get("preferred_style", ""),
                    "max_budget": user.get("max_budget", ""),
                    "brand": product.get("brand", ""),
                    "name": product.get("name", ""),
                    "category": product.get("category", ""),
                    "price": product.get("price", ""),
                    "shade": product.get("shade", ""),
                    "finish": product.get("finish", ""),
                    "suitable_skin_type": product.get("suitable_skin_type", ""),
                    "available": product.get("available", ""),
                    "skin_match": int(
                        normalize(user.get("skin_type"))
                        == normalize(product.get("suitable_skin_type"))
                    ),
                    "finish_match": int(
                        normalize(user.get("preferred_finish"))
                        == normalize(product.get("finish"))
                    ),
                    "budget_ok": int(budget_ok),
                    "available_flag": int(to_bool(product.get("available"))),
                    "price_budget_ratio": price_budget_ratio,
                    "interaction_type": interaction.get("interaction_type", ""),
                    "rating": interaction.get("rating", ""),
                    "interaction_signal": signal if interaction else "",
                    "label": label,
                }
            )

    return feature_rows


def sample_negatives(feature_rows, positive_rows, seed=NEGATIVE_SEED):
    """
    Pour chaque utilisateur, tire SANS REMISE autant de non-interactions
    que de positifs. Seuls les produits JAMAIS interagis sont éligibles
    (une interaction neutre, par exemple une note de 3, n'est pas une
    non-interaction).
    """
    rng = random.Random(seed)

    candidates_by_user = {}

    for row in feature_rows:
        if row["interaction_type"] == "" and row["label"] == "":
            candidates_by_user.setdefault(row["user_id"], []).append(row)

    positives_by_user = {}

    for row in positive_rows:
        positives_by_user[row["user_id"]] = (
            positives_by_user.get(row["user_id"], 0) + 1
        )

    sampled = []

    for user_id in sorted(positives_by_user):
        candidates = sorted(
            candidates_by_user.get(user_id, []),
            key=lambda row: row["product_id"],
        )
        n_samples = min(positives_by_user[user_id], len(candidates))

        for candidate in rng.sample(candidates, n_samples):
            row = candidate.copy()
            row["interaction_signal"] = "sampled_non_interaction"
            row["label"] = "0"
            sampled.append(row)

    return sampled


def main():
    products = read_csv(PRODUCTS_PATH)
    users = read_csv(USERS_PATH)
    interactions = read_csv(INTERACTIONS_PATH)

    if not products or not users:
        raise ValueError(
            "Les fichiers produits et utilisateurs ne doivent pas être vides."
        )

    required_product_columns = {
        "product_id", "price", "finish", "suitable_skin_type", "available",
    }
    required_user_columns = {
        "user_id", "skin_type", "preferred_finish", "max_budget",
    }

    missing_product_columns = required_product_columns - set(products[0])
    missing_user_columns = required_user_columns - set(users[0])

    if missing_product_columns:
        raise ValueError(
            f"Colonnes produits manquantes : {sorted(missing_product_columns)}"
        )

    if missing_user_columns:
        raise ValueError(
            f"Colonnes utilisateurs manquantes : {sorted(missing_user_columns)}"
        )

    interaction_by_pair = {}

    for interaction in interactions:
        key = (interaction.get("user_id"), interaction.get("product_id"))
        interaction_by_pair[key] = interaction

    feature_rows = build_feature_rows(users, products, interaction_by_pair)

    positive_rows = [row for row in feature_rows if row["label"] == "1"]
    real_negative_rows = [row for row in feature_rows if row["label"] == "0"]
    sampled_negative_rows = sample_negatives(feature_rows, positive_rows)

    labeled_rows = positive_rows + real_negative_rows + sampled_negative_rows

    duplicated_pairs = len(labeled_rows) - len(
        {(row["user_id"], row["product_id"]) for row in labeled_rows}
    )

    train_rows, test_rows = split_train_test(labeled_rows)

    write_csv(FEATURES_PATH, feature_rows)
    write_csv(TRAIN_PATH, train_rows, list(feature_rows[0].keys()))
    write_csv(TEST_PATH, test_rows, list(feature_rows[0].keys()))

    missing_values = {}

    for row in feature_rows:
        for column, value in row.items():
            if value == "":
                missing_values[column] = missing_values.get(column, 0) + 1

    request_count = 0

    if REQUESTS_PATH.exists():
        with REQUESTS_PATH.open("r", encoding="utf-8") as file:
            request_count = len(json.load(file))

    positives_by_user = {}

    for row in positive_rows:
        positives_by_user[row["user_id"]] = (
            positives_by_user.get(row["user_id"], 0) + 1
        )

    users_with_2_positives = sum(
        1
        for count in positives_by_user.values()
        if count >= MIN_POSITIVES_TO_EVALUATE
    )
    users_in_test = len(
        {row["user_id"] for row in test_rows if row["label"] == "1"}
    )

    report = {
        "status": "success" if duplicated_pairs == 0 else "warning",
        "dataset_version": DATASET_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_hash": {
            path.name: file_hash(path)[:16]
            for path in (PRODUCTS_PATH, USERS_PATH, INTERACTIONS_PATH)
        },
        "split": {
            "method": "par utilisateur",
            "test_ratio": TEST_RATIO,
            "split_seed": SPLIT_SEED,
            "negative_seed": NEGATIVE_SEED,
            "min_positives_to_evaluate": MIN_POSITIVES_TO_EVALUATE,
        },
        "positive_definition": POSITIVE_DEFINITION,
        "negative_definition": NEGATIVE_DEFINITION,
        "users": len(users),
        "products": len(products),
        "source_interactions": len(interactions),
        "unique_user_product_pairs": len(interaction_by_pair),
        "feature_rows": len(feature_rows),
        "labeled_rows": len(labeled_rows),
        "duplicated_labeled_pairs": duplicated_pairs,
        "train_rows": len(train_rows),
        "test_rows": len(test_rows),
        "positive_rows": len(positive_rows),
        "real_negative_rows": len(real_negative_rows),
        "sampled_negative_rows": len(sampled_negative_rows),
        "negative_rows": len(real_negative_rows) + len(sampled_negative_rows),
        "users_total": len(users),
        "users_with_at_least_2_positives": users_with_2_positives,
        "users_in_test": users_in_test,
        "recommendation_requests": request_count,
        "missing_values": missing_values,
    }

    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    with REPORT_PATH.open("w", encoding="utf-8") as file:
        json.dump(report, file, ensure_ascii=False, indent=2)
        file.write("\n")

    print("✅ Préparation des données IA terminée")
    print(f"Lignes de variables : {len(feature_rows)}")
    print(f"Lignes avec label : {len(labeled_rows)}")
    print(f"Entraînement : {len(train_rows)} | Test : {len(test_rows)}")
    print(f"Utilisateurs totaux : {len(users)}")
    print(f"Utilisateurs avec ≥2 positifs : {users_with_2_positives}")
    print(f"Utilisateurs présents dans le test : {users_in_test}")
    print(f"Paires dupliquées : {duplicated_pairs}")
    print(f"Rapport créé : {REPORT_PATH}")


if __name__ == "__main__":
    main()