import csv
import sys
from pathlib import Path

RAW = Path("data/raw")
EXPECTED = {"products_raw.csv": 50, "users_raw.csv": 20, "interactions_raw.csv": 100}


def read(name):
    with (RAW / name).open("r", encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


errors = []
products = read("products_raw.csv")
users = read("users_raw.csv")
interactions = read("interactions_raw.csv")

for name, rows in (
    ("products_raw.csv", products),
    ("users_raw.csv", users),
    ("interactions_raw.csv", interactions),
):
    if len(rows) != EXPECTED[name]:
        errors.append(f"{name} : {len(rows)} lignes au lieu de {EXPECTED[name]}")

product_signatures = {
    (p["category"], p["finish"], p["suitable_skin_type"], p["brand"], p["shade"], p["price"])
    for p in products
}
user_signatures = {
    (u["skin_type"], u["complexion"], u["undertone"], u["preferred_finish"],
     u["preferred_style"], u["max_budget"])
    for u in users
}
pairs = {(i["user_id"], i["product_id"]) for i in interactions}

print(f"Produits : {len(products)} | distincts : {len(product_signatures)}")
print(f"Utilisateurs : {len(users)} | distincts : {len(user_signatures)}")
print(f"Interactions : {len(interactions)} | paires distinctes : {len(pairs)}")

if len(product_signatures) != len(products):
    errors.append("produits en doublon fonctionnel")
if len(user_signatures) != len(users):
    errors.append("profils utilisateurs en doublon fonctionnel")
if len(pairs) != len(interactions):
    errors.append("paires utilisateur-produit dupliquées")

if errors:
    print("❌ Dataset invalide")
    for error in errors:
        print(f"- {error}")
    sys.exit(1)

print("✅ Dataset valide")