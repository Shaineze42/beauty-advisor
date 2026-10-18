import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# app/ contient un ancien api.py : il doit passer APRÈS le dossier api/ du dépôt.
for extra in (ROOT / "src", ROOT):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))
if str(ROOT / "app") not in sys.path:
    sys.path.append(str(ROOT / "app"))
