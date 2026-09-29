import csv
import json
from pathlib import Path


BASE = Path("data/raw")


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


products_path = BASE / "products_raw.csv"
users_path = BASE / "users_raw.csv"
interactions_path = BASE / "interactions_raw.csv"
requests_path = BASE / "recommendation_requests_raw.json"

products = read_csv(products_path)
users = read_csv(users_path)
interactions = read_csv(interactions_path)

if not products or not users or not interactions:
    raise ValueError("Les fichiers CSV sources doivent contenir au moins une ligne.")

product_fields = list(products[0].keys())
user_fields = list(users[0].keys())
interaction_fields = list(interactions[0].keys())

expanded_products = []

for index in range(1, 51):
    source = products[(index - 1) % len(products)].copy()
    source["product_id"] = f"prod_{index:03d}"
    expanded_products.append(source)


expanded_users = []

for index in range(1, 21):
    source = users[(index - 1) % len(users)].copy()
    source["user_id"] = f"user_{index:03d}"
    expanded_users.append(source)


expanded_interactions = []

interaction_types = [
    row.get("interaction_type", "favorite")
    for row in interactions
]

ratings = [
    row.get("rating", "")
    for row in interactions
]

for index in range(1, 101):
    source = interactions[(index - 1) % len(interactions)].copy()

    source["interaction_id"] = f"interaction_{index:04d}"
    source["user_id"] = f"user_{((index - 1) % 20) + 1:03d}"
    source["product_id"] = f"prod_{((index - 1) % 50) + 1:03d}"
    source["interaction_type"] = interaction_types[
        (index - 1) % len(interaction_types)
    ]
    source["rating"] = ratings[(index - 1) % len(ratings)]

    expanded_interactions.append(source)


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

temporary_requests_path = requests_path.with_suffix(
    requests_path.suffix + ".tmp"
)

with temporary_requests_path.open("w", encoding="utf-8") as file:
    json.dump(expanded_requests, file, ensure_ascii=False, indent=2)
    file.write("\n")

temporary_requests_path.replace(requests_path)

print("✅ Sources alignées")
print(f"Produits : {len(expanded_products)}")
print(f"Utilisateurs : {len(expanded_users)}")
print(f"Interactions : {len(expanded_interactions)}")
print(f"Demandes JSON : {len(expanded_requests)}")