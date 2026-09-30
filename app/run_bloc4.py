"""
Chaîne IA reproductible (n'altère PAS le pipeline du Bloc 3).

Usage :
  python run_bloc4.py               # chaîne IA sur les données actuelles
  python run_bloc4.py --regenerate  # régénère d'abord les données (seed 42)
"""
import subprocess
import sys


def run(script):
    print(f"\n▶ {script}")
    result = subprocess.run([sys.executable, script])
    if result.returncode != 0:
        print(f"❌ Échec : {script}")
        sys.exit(result.returncode)


steps = []

if "--regenerate" in sys.argv:
    steps += ["expand_raw_data.py", "check_dataset.py"]

steps += [
    "pipeline.py",
    "prepare_ai_data.py",
    "test_explainability.py",
    "evaluate_personalized.py",
]

for step in steps:
    run(step)

print("\n✅ Chaîne Bloc 4 terminée")