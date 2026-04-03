"""
conftest.py -- Fixtures partagees pour tous les tests.
"""

import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["SENTINEL_SIMULATION"] = "true"
os.environ["SENTINEL_ID"] = "test-sentinelle-001"

import config


@pytest.fixture(autouse=True)
def config_temporaire(tmp_path):
    """Redirige cles et BDD vers un repertoire temporaire pour chaque test."""
    ancien = {
        "rep": config.REPERTOIRE_CLES,
        "db": config.FICHIER_BASE_DONNEES,
        "priv": config.FICHIER_CLE_PRIVEE,
        "pub": config.FICHIER_CLE_PUBLIQUE,
        "aes": config.FICHIER_CLE_AES,
    }

    config.REPERTOIRE_CLES = str(tmp_path / "cles")
    config.FICHIER_CLE_PRIVEE = os.path.join(config.REPERTOIRE_CLES, "cle_privee.pem")
    config.FICHIER_CLE_PUBLIQUE = os.path.join(config.REPERTOIRE_CLES, "cle_publique.pem")
    config.FICHIER_CLE_AES = os.path.join(config.REPERTOIRE_CLES, "cle_aes.bin")
    config.FICHIER_BASE_DONNEES = str(tmp_path / "donnees" / "test.db")
    config.MODE_SIMULATION = True

    yield tmp_path

    config.REPERTOIRE_CLES = ancien["rep"]
    config.FICHIER_BASE_DONNEES = ancien["db"]
    config.FICHIER_CLE_PRIVEE = ancien["priv"]
    config.FICHIER_CLE_PUBLIQUE = ancien["pub"]
    config.FICHIER_CLE_AES = ancien["aes"]


@pytest.fixture
def cle_aes():
    from securite.cles import generer_cle_aes
    return generer_cle_aes()


@pytest.fixture
def cle_privee_ecdsa():
    from securite.cles import charger_cle_privee_ecdsa
    return charger_cle_privee_ecdsa()


@pytest.fixture
def cle_publique_pem():
    from securite.cles import charger_cle_publique_ecdsa_pem
    return charger_cle_publique_ecdsa_pem()


@pytest.fixture
def base_locale():
    from stockage.base_locale import BaseLocale
    base = BaseLocale()
    yield base
    base.fermer()


@pytest.fixture
def mesures_exemple():
    return {
        "sentinel_id": "test-sentinelle-001",
        "horodatage": "2026-04-03T10:00:00+00:00",
        "mesures": [
            {"type": "temperature", "valeur": 22.5, "unite": "degC",
             "horodatage": "2026-04-03T10:00:00+00:00"},
            {"type": "humidite", "valeur": 65.0, "unite": "%",
             "horodatage": "2026-04-03T10:00:00+00:00"},
            {"type": "pression", "valeur": 1013.2, "unite": "hPa",
             "horodatage": "2026-04-03T10:00:00+00:00"},
        ],
        "nb_mesures": 3,
    }
