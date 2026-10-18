"""Registre des modèles : versions, modèle actif, retour arrière.

models/
  versions/v0.json, v1.json ...   un fichier par version (poids + métriques)
  current.json                    copie du modèle actif, lue par le moteur
  registry.json                   historique des décisions
"""
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

MODELS_DIR = Path("models")


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read(path, default):
    path = Path(path)
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def _write(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
        file.write("\n")


def load_registry(models_dir=MODELS_DIR):
    return _read(Path(models_dir) / "registry.json", {"active": None, "history": []})


def load_active(models_dir=MODELS_DIR):
    return _read(Path(models_dir) / "current.json", None)


def next_version(models_dir=MODELS_DIR):
    versions = (Path(models_dir) / "versions").glob("v*.json")
    numbers = [int(p.stem[1:]) for p in versions if p.stem[1:].isdigit()]
    return f"v{max(numbers) + 1 if numbers else 0}"


def save_version(model, models_dir=MODELS_DIR):
    _write(Path(models_dir) / "versions" / f"{model['version']}.json", model)


def record(models_dir, version, decision, reason, metrics):
    registry = load_registry(models_dir)
    registry["history"].append(
        {
            "version": version,
            "date": now(),
            "decision": decision,
            "reason": reason,
            "metrics": metrics,
        }
    )
    _write(Path(models_dir) / "registry.json", registry)


def promote(version, models_dir=MODELS_DIR):
    """Rend une version active : current.json devient sa copie."""
    source = Path(models_dir) / "versions" / f"{version}.json"
    if not source.exists():
        raise FileNotFoundError(f"Version inconnue : {version}")
    shutil.copyfile(source, Path(models_dir) / "current.json")
    registry = load_registry(models_dir)
    registry["active"] = version
    _write(Path(models_dir) / "registry.json", registry)


def rollback(models_dir=MODELS_DIR):
    """Revient à la version promue juste avant la version active."""
    registry = load_registry(models_dir)
    promoted = [h["version"] for h in registry["history"] if h["decision"] == "promu"]
    unique = []
    for version in promoted:
        if version in unique:
            unique.remove(version)
        unique.append(version)
    if registry["active"] not in unique or unique.index(registry["active"]) == 0:
        raise ValueError("Aucune version précédente vers laquelle revenir.")
    previous = unique[unique.index(registry["active"]) - 1]
    promote(previous, models_dir)
    record(models_dir, previous, "retour_arriere", f"retour depuis {registry['active']}", {})
    return previous
