#!/usr/bin/env python3
"""
installer.py -- Installation automatique de la sentinelle DTN.

Usage :
    python installer.py          # Setup complet (deps + cles + QR code)
    python installer.py --start  # Setup + lancement immédiat
    python installer.py --check  # Vérification uniquement (sans installer)

Ce script fait tout d'un coup :
  1. Vérifie la version Python
  2. Installe les dépendances pip
  3. Génère les clés AES-256 et ECDSA P-256
  4. Génère le QR code de déploiement
  5. Affiche un résumé clair
"""

import argparse
import os
import subprocess
import sys

# Ajouter le dossier courant au path pour les imports internes
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


# =============================================================================
# CONSTANTES
# =============================================================================

VERSION_PYTHON_MIN = (3, 10)
REPERTOIRE_RACINE = os.path.dirname(os.path.abspath(__file__))


# =============================================================================
# FONCTIONS D'INSTALLATION (toutes testables individuellement)
# =============================================================================

def verifier_python() -> dict:
    """
    Vérifie que la version Python est suffisante.

    Returns:
        {"ok": bool, "version": str, "message": str}
    """
    version = sys.version_info
    # Utiliser l'indexation pour compatibilité avec les mocks de test (tuple nu)
    major, minor, micro = version[0], version[1], version[2]
    ok = (major, minor) >= VERSION_PYTHON_MIN
    return {
        "ok": ok,
        "version": f"{major}.{minor}.{micro}",
        "message": (
            f"Python {major}.{minor} OK"
            if ok
            else f"Python {VERSION_PYTHON_MIN[0]}.{VERSION_PYTHON_MIN[1]}+ requis, "
                 f"vous avez {major}.{minor}"
        ),
    }


def installer_dependances(requirements_path: str = None) -> dict:
    """
    Installe les dépendances via pip.

    Args:
        requirements_path: Chemin vers requirements.txt (défaut : ./requirements.txt)

    Returns:
        {"ok": bool, "message": str}
    """
    if requirements_path is None:
        requirements_path = os.path.join(REPERTOIRE_RACINE, "requirements.txt")

    if not os.path.exists(requirements_path):
        return {"ok": False, "message": f"requirements.txt introuvable : {requirements_path}"}

    try:
        resultat = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", requirements_path, "-q"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if resultat.returncode == 0:
            return {"ok": True, "message": "Dépendances installées"}
        return {"ok": False, "message": f"pip error : {resultat.stderr.strip()}"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "message": "Timeout lors de l'installation pip (>120s)"}
    except FileNotFoundError:
        return {"ok": False, "message": "pip introuvable"}


def initialiser_cles() -> dict:
    """
    Génère les clés AES-256 et ECDSA P-256 si elles n'existent pas encore.

    Returns:
        {"ok": bool, "aes_nouveau": bool, "ecdsa_nouveau": bool, "message": str}
    """
    try:
        import config
        from securite.cles import generer_cle_aes, generer_cles_ecdsa

        aes_existait = os.path.exists(config.FICHIER_CLE_AES)
        ecdsa_existait = (
            os.path.exists(config.FICHIER_CLE_PRIVEE)
            and os.path.exists(config.FICHIER_CLE_PUBLIQUE)
        )

        generer_cle_aes()
        generer_cles_ecdsa()

        return {
            "ok": True,
            "aes_nouveau": not aes_existait,
            "ecdsa_nouveau": not ecdsa_existait,
            "message": "Clés prêtes",
        }
    except ImportError as e:
        return {"ok": False, "aes_nouveau": False, "ecdsa_nouveau": False,
                "message": f"Import impossible (dépendances non installées ?) : {e}"}
    except Exception as e:
        return {"ok": False, "aes_nouveau": False, "ecdsa_nouveau": False,
                "message": f"Erreur génération clés : {e}"}


def generer_qrcode_deploiement() -> dict:
    """
    Génère le QR code PNG à coller sur le boîtier de la sentinelle.

    Returns:
        {"ok": bool, "chemin": str | None, "message": str}
    """
    try:
        from utils.qrcode_gen import generer_qrcode, QRCODE_DISPONIBLE

        if not QRCODE_DISPONIBLE:
            return {
                "ok": False,
                "chemin": None,
                "message": "Package 'qrcode' non installé (pip install qrcode[pil])",
            }

        chemin = generer_qrcode()
        if chemin:
            return {"ok": True, "chemin": chemin, "message": f"QR code : {chemin}"}
        return {"ok": False, "chemin": None, "message": "Échec génération QR code"}

    except Exception as e:
        return {"ok": False, "chemin": None, "message": f"Erreur QR code : {e}"}


def verifier_etat_systeme() -> dict:
    """
    Vérifie l'état global du système sans rien installer.

    Returns:
        dict avec les statuts de chaque composant.
    """
    import config

    return {
        "python": verifier_python(),
        "cles_aes": os.path.exists(config.FICHIER_CLE_AES),
        "cles_ecdsa": (
            os.path.exists(config.FICHIER_CLE_PRIVEE)
            and os.path.exists(config.FICHIER_CLE_PUBLIQUE)
        ),
        "base_donnees": os.path.exists(config.FICHIER_BASE_DONNEES),
        "mode_simulation": config.MODE_SIMULATION,
        "sentinel_id": config.SENTINEL_ID,
    }


# =============================================================================
# AFFICHAGE
# =============================================================================

def _ok(msg: str) -> str:
    return f"  [OK] {msg}"


def _err(msg: str) -> str:
    return f"  [ERREUR] {msg}"


def _info(msg: str) -> str:
    return f"  [INFO] {msg}"


def afficher_resume(resultats: dict) -> None:
    """Affiche un résumé lisible du setup."""
    print()
    print("=" * 55)
    print("  IoT-Sentinelle -- Résumé de l'installation")
    print("=" * 55)

    py = resultats.get("python", {})
    print(_ok(py["message"]) if py.get("ok") else _err(py.get("message", "?")))

    deps = resultats.get("dependances", {})
    if deps:
        print(_ok(deps["message"]) if deps.get("ok") else _err(deps["message"]))

    cles = resultats.get("cles", {})
    if cles:
        if cles.get("ok"):
            statut_aes = "générée" if cles.get("aes_nouveau") else "existante"
            statut_ecdsa = "générée" if cles.get("ecdsa_nouveau") else "existante"
            print(_ok(f"Clé AES-256 {statut_aes}"))
            print(_ok(f"Paire ECDSA P-256 {statut_ecdsa}"))
        else:
            print(_err(cles["message"]))

    qr = resultats.get("qrcode", {})
    if qr:
        print(_ok(qr["message"]) if qr.get("ok") else _info(qr["message"]))

    print()
    if all(r.get("ok", True) for r in resultats.values() if isinstance(r, dict)):
        print("  Sentinelle prête. Lancer avec : python main.py")
    else:
        print("  Des erreurs se sont produites. Voir ci-dessus.")
    print("=" * 55)
    print()


# =============================================================================
# POINT D'ENTRÉE
# =============================================================================

def setup_complet(installer_deps: bool = True) -> dict:
    """
    Exécute le setup complet. Retourne le dict des résultats.
    Fonction principale appelable depuis les tests.
    """
    resultats = {}

    resultats["python"] = verifier_python()
    if not resultats["python"]["ok"]:
        return resultats

    if installer_deps:
        resultats["dependances"] = installer_dependances()
        if not resultats["dependances"]["ok"]:
            return resultats

    resultats["cles"] = initialiser_cles()
    resultats["qrcode"] = generer_qrcode_deploiement()

    return resultats


def main():
    parser = argparse.ArgumentParser(
        description="Installation automatique de la sentinelle IoT-Sentinelle"
    )
    parser.add_argument(
        "--start", action="store_true",
        help="Lancer main.py après le setup",
    )
    parser.add_argument(
        "--check", action="store_true",
        help="Vérifier l'état sans installer",
    )
    parser.add_argument(
        "--no-deps", action="store_true",
        help="Ne pas relancer pip install",
    )
    args = parser.parse_args()

    if args.check:
        try:
            etat = verifier_etat_systeme()
            print("\n=== État de la sentinelle ===")
            print(_ok(f"Python {etat['python']['version']}") if etat["python"]["ok"] else _err("Python trop ancien"))
            print(_ok("Clé AES présente") if etat["cles_aes"] else _info("Clé AES absente (sera générée au lancement)"))
            print(_ok("Clés ECDSA présentes") if etat["cles_ecdsa"] else _info("Clés ECDSA absentes (seront générées au lancement)"))
            print(_ok("Base SQLite présente") if etat["base_donnees"] else _info("Base SQLite absente (créée au premier lancement)"))
            print(_info(f"Sentinel ID : {etat['sentinel_id']}"))
            print(_info(f"Mode simulation : {etat['mode_simulation']}"))
            print()
        except Exception as e:
            print(_err(f"Impossible de lire la config : {e}"))
        return

    # Setup complet
    resultats = setup_complet(installer_deps=not args.no_deps)
    afficher_resume(resultats)

    if args.start:
        main_py = os.path.join(REPERTOIRE_RACINE, "main.py")
        print("Lancement de la sentinelle...\n")
        os.execv(sys.executable, [sys.executable, main_py])


if __name__ == "__main__":
    main()
