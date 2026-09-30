"""
Contrôle qualité et sécurité du code Beauty Advisor (bibliothèque standard).

Vérifie : syntaxe, secrets en dur, fonctions dangereuses, imports inutilisés,
puis exécute les tests unitaires. Écrit reports/quality_report.json.
Code de sortie 1 si une ERREUR est trouvée (les avertissements n'échouent pas).
"""
import ast
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


APP_DIR = Path(__file__).resolve().parent
REPORT_PATH = Path("reports/quality_report.json")

SECRET_PATTERN = re.compile(
    r"""(password|passwd|secret|token|api[_-]?key)\s*=\s*['"]([^'"]{6,})['"]""",
    re.IGNORECASE,
)
TOKEN_PATTERN = re.compile(r"(ghp_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|sk-[A-Za-z0-9]{20,})")
ALLOWED_SECRET_VALUES = {"change_me", "changeme", "example"}
DANGEROUS_CALLS = {"eval", "exec"}


def python_files():
    return sorted(
        path
        for path in APP_DIR.rglob("*.py")
        if "__pycache__" not in path.parts
    )


def check_syntax(path, source):
    try:
        return ast.parse(source, filename=str(path)), None
    except SyntaxError as error:
        return None, f"{path.name}:{error.lineno} erreur de syntaxe : {error.msg}"


def check_secrets(path, source):
    findings = []
    for number, line in enumerate(source.splitlines(), 1):
        match = SECRET_PATTERN.search(line)
        if match and match.group(2).lower() not in ALLOWED_SECRET_VALUES:
            findings.append(f"{path.name}:{number} secret potentiel en dur")
        if TOKEN_PATTERN.search(line):
            findings.append(f"{path.name}:{number} jeton d'accès en dur")
    return findings


def check_dangerous(path, tree):
    findings = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in DANGEROUS_CALLS:
                findings.append(f"{path.name}:{node.lineno} appel à {func.id}()")
            for keyword in node.keywords:
                if (
                    keyword.arg == "shell"
                    and isinstance(keyword.value, ast.Constant)
                    and keyword.value.value is True
                ):
                    findings.append(f"{path.name}:{node.lineno} shell=True")
    return findings


def check_quality(path, tree):
    warnings = []
    imported = {}

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported[(alias.asname or alias.name).split(".")[0]] = node.lineno
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                imported[alias.asname or alias.name] = node.lineno
        elif isinstance(node, ast.ExceptHandler) and node.type is None:
            warnings.append(f"{path.name}:{node.lineno} except: sans type")

    used = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    used |= {
        n.value.id
        for n in ast.walk(tree)
        if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name)
    }

    for name, line in imported.items():
        if name not in used and path.name != "__init__.py":
            warnings.append(f"{path.name}:{line} import inutilisé : {name}")

    return warnings


def run_unit_tests():
    result = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", "."],
        cwd=APP_DIR,
        capture_output=True,
        text=True,
        check=False,
    )
    output = (result.stderr or result.stdout).strip().splitlines()
    return result.returncode == 0, output[-3:]


def main():
    files = python_files()
    errors = []
    warnings = []

    for path in files:
        source = path.read_text(encoding="utf-8")
        tree, syntax_error = check_syntax(path, source)

        if syntax_error:
            errors.append(syntax_error)
            continue

        errors += check_secrets(path, source)
        errors += check_dangerous(path, tree)
        warnings += check_quality(path, tree)

    tests_ok, tests_tail = run_unit_tests()

    if not tests_ok:
        errors.append("tests unitaires en échec : " + " | ".join(tests_tail))

    report = {
        "status": "success" if not errors else "failed",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "files_checked": len(files),
        "checks": [
            "syntaxe Python",
            "secrets et jetons en dur",
            "appels dangereux (eval, exec, shell=True)",
            "imports inutilisés et except: sans type (avertissements)",
            "tests unitaires (moteur et API)",
        ],
        "unit_tests": {"passed": tests_ok, "summary": tests_tail},
        "errors": errors,
        "warnings": warnings,
    }

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"Fichiers vérifiés : {len(files)}")
    print(f"Tests unitaires : {'✅ OK' if tests_ok else '❌ échec'} ({tests_tail[-1] if tests_tail else ''})")
    print(f"Erreurs : {len(errors)} | Avertissements : {len(warnings)}")

    for item in errors:
        print(f"❌ {item}")
    for item in warnings:
        print(f"⚠️  {item}")

    if errors:
        sys.exit(1)

    print(f"✅ Contrôle qualité réussi. Rapport : {REPORT_PATH}")


if __name__ == "__main__":
    main()