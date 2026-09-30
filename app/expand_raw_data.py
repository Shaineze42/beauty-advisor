import csv
import json
import random
from itertools import product as iter_product
from pathlib import Path


BASE = Path("data/raw")

RNG = random.Random(42)

BRANDS = ["Rare Beauty", "Fenty Beauty", "NYX", "Sephora Collection"]
CATEGORIES = ["teint", "blush", "yeux", "levres"]
FINISHES = ["mat", "naturel", "glowy"]
SKIN_TYPES = ["seche", "grasse", "mixte", "normale"]
SHADES = ["rose", "nude", "bronze", "marron", "rouge"]

CATEGORY_LABELS = {
    "teint": "Fond de teint",
    "blush": "Blush",
    "yeux": "Palette yeux",
    "levres": "Gloss",
}

COMPLEXIONS = ["claire", "medium", "foncee"]
UNDERTONES = ["chaud", "froid", "neutre"]
STYLES = ["naturel", "sophistique", "quotidien"]
BUDGET_TIERS = [30.0, 50.0, 60.0, 80.0, 100.0]

PRODUCT_COUNT = 50
USER_COUNT = 20
INTERACTIONS_PER_USER = 5
COMPATIBLE_INTERACTION_RATIO = 0.75  # 75% des interactions suivent le profil


def read_csv(path):
    with path.open("r", encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def write_csv(path, fieldnames, rows):
    temporary_path = path.with_suffix(path.suffix + ".tmp")

    with temporary_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    temporary_path.replace(path)


def build_products():
    """
    Génère PRODUCT_COUNT produits réellement distincts en couvrant les
    combinaisons (catégorie, fini, type de peau cible) au lieu de
    dupliquer 5 profils identiques sous des IDs différents (bug initial).
    """
    combos = list(iter_product(CATEGORIES, FINISHES, SKIN_TYPES))
    RNG.shuffle(combos)

    products = []

    for index in range(1, PRODUCT_COUNT + 1):
        category, finish, skin_type = combos[(index - 1) % len(combos)]
        brand = RNG.choice(BRANDS)
        shade = RNG.choice(SHADES)
        price = round(RNG.uniform(8, 65), 2)

        products.append(
            {
                "product_id": f"prod_{index:03d}",
                "brand": brand,
                "name": f"{CATEGORY_LABELS[category]} {brand} {shade.title()}",
                "category": category,
                "price": price,
                "shade": shade,
                "finish": finish,
                "suitable_skin_type": skin_type,
                "available": "true" if RNG.random() < 0.9 else "false",
                "updated_at": "2026-09-27",
            }
        )

    return products


def build_users():
    """
    Génère USER_COUNT profils distincts en couvrant les combinaisons
    (type de peau, fini préféré, style) au lieu de dupliquer 3 profils
    identiques (bug initial).
    """
    combos = list(iter_product(SKIN_TYPES, FINISHES, STYLES))
    RNG.shuffle(combos)

    users = []

    for index in range(1, USER_COUNT + 1):
        skin_type, preferred_finish, preferred_style = combos[
            (index - 1) % len(combos)
        ]

        users.append(
            {
                "user_id": f"user_{index:03d}",
                "skin_type": skin_type,
                "complexion": RNG.choice(COMPLEXIONS),
                "undertone": RNG.choice(UNDERTONES),
                "preferred_finish": preferred_finish,
                "preferred_style": preferred_style,
                "max_budget": RNG.choice(BUDGET_TIERS),
                "created_at": "2026-09-27",
            }
        )

    return users


def is_compatible(user, product):
    skin_ok = user["skin_type"] == product["suitable_skin_type"]
    finish_ok = user["preferred_finish"] == product["finish"]
    budget_ok = float(product["price"]) <= float(user["max_budget"])
    return (skin_ok or finish_ok) and budget_ok


def pick_product(compatible_pool, incompatible_pool, all_products):
    use_compatible = RNG.random() < COMPATIBLE_INTERACTION_RATIO and compatible_pool
    pool = compatible_pool if use_compatible else (incompatible_pool or all_products)
    return RNG.choice(pool)


def build_interaction_outcome(is_match: bool):
    """
    Une interaction "compatible" a plus de chances d'être positive
    (favori, achat, bonne note) ; une interaction "hors profil" a plus
    de chances d'être neutre/négative. Rien n'est déterministe à 100%
    pour rester réaliste (du bruit existe des deux côtés).
    """
    if is_match:
        interaction_type = RNG.choices(
            ["favorite", "purchase", "review"], weights=[0.35, 0.35, 0.30]
        )[0]
        rating = (
            RNG.choices([5, 4, 3], weights=[0.5, 0.35, 0.15])[0]
            if interaction_type == "review"
            else ""
        )
    else:
        interaction_type = RNG.choices(
            ["favorite", "purchase", "review"], weights=[0.15, 0.15, 0.70]
        )[0]
        rating = (
            RNG.choices([1, 2, 3, 4], weights=[0.3, 0.3, 0.25, 0.15])[0]
            if interaction_type == "review"
            else ""
        )

    return interaction_type, rating


def build_interactions(users, products):
    interactions = []
    interaction_index = 1

    for user in users:
        compatible_pool = [p for p in products if is_compatible(user, p)]
        incompatible_pool = [p for p in products if not is_compatible(user, p)]

        used_products = set()
        attempts = 0

        while (
            len(used_products) < INTERACTIONS_PER_USER
            and attempts < INTERACTIONS_PER_USER * 5
        ):
            attempts += 1
            product = pick_product(compatible_pool, incompatible_pool, products)

            if product["product_id"] in used_products:
                continue

            used_products.add(product["product_id"])

            is_match = is_compatible(user, product)
            interaction_type, rating = build_interaction_outcome(is_match)

            interactions.append(
                {
                    "interaction_id": f"interaction_{interaction_index:04d}",
                    "user_id": user["user_id"],
                    "product_id": product["product_id"],
                    "interaction_type": interaction_type,
                    "rating": rating,
                    "created_at": "2026-09-27",
                }
            )

            interaction_index += 1

    return interactions


products_path = BASE / "products_raw.csv"
users_path = BASE / "users_raw.csv"
interactions_path = BASE / "interactions_raw.csv"
requests_path = BASE / "recommendation_requests_raw.json"

# On relit les fichiers sources uniquement pour récupérer les noms de
# colonnes attendus par la suite du pipeline (validate_data.py, etc.).
existing_products = read_csv(products_path)
existing_users = read_csv(users_path)
existing_interactions = read_csv(interactions_path)

if not existing_products or not existing_users or not existing_interactions:
    raise ValueError("Les fichiers CSV sources doivent contenir au moins une ligne.")

product_fields = list(existing_products[0].keys())
user_fields = list(existing_users[0].keys())
interaction_fields = list(existing_interactions[0].keys())

expanded_products = build_products()
expanded_users = build_users()
expanded_interactions = build_interactions(expanded_users, expanded_products)

with requests_path.open("r", encoding="utf-8") as file:
    requests = json.load(file)

if not requests:
    raise ValueError("Le fichier JSON des demandes est vide.")

expanded_requests = []

for index in range(1, 11):
    source = requests[(index - 1) % len(requests)].copy()
    source["request_id"] = f"request_{index:03d}"
    source["user_id"] = f"user_{index:03d}"
    expanded_requests.append(source)


write_csv(products_path, product_fields, expanded_products)
write_csv(users_path, user_fields, expanded_users)
write_csv(interactions_path, interaction_fields, expanded_interactions)

temporary_requests_path = requests_path.with_suffix(requests_path.suffix + ".tmp")

with temporary_requests_path.open("w", encoding="utf-8") as file:
    json.dump(expanded_requests, file, ensure_ascii=False, indent=2)
    file.write("\n")

temporary_requests_path.replace(requests_path)

positive_estimate = sum(
    1
    for row in expanded_interactions
    if row["interaction_type"] in {"favorite", "purchase"}
    or (row["interaction_type"] == "review" and row["rating"] != "" and int(row["rating"]) >= 4)
)

print("✅ Sources régénérées avec un catalogue diversifié")
print(f"Produits distincts : {len(expanded_products)}")
print(f"Utilisateurs distincts : {len(expanded_users)}")
print(f"Interactions : {len(expanded_interactions)}")
print(f"Interactions positives estimées : {positive_estimate}")
print(f"Demandes JSON : {len(expanded_requests)}")