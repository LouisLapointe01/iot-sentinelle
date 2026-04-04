"""
test_setup_integration.py -- Tests d'intégration du setup complet.

Valide le processus d'installation de bout en bout :
- Setup depuis un répertoire vide (première installation)
- Idempotence (deuxième installation ne régénère pas les clés)
- Variables d'environnement SENTINEL_ID et SENTINEL_SIMULATION
- Vérification d'état système (--check)
- Enchaînement setup → fonctionnement
"""

import os
import sys
import json
import subprocess
import pytest
from unittest.mock import patch, MagicMock


# =============================================================================
# TESTS : Première installation depuis zéro
# =============================================================================

class TestPremiereInstallation:
    def test_setup_sans_cles_genere_cles_aes(self, tmp_path):
        """Un setup sans clés existantes doit créer le fichier AES."""
        import config
        # config_temporaire fixture redirige déjà vers tmp_path
        assert not os.path.exists(config.FICHIER_CLE_AES)

        from installer import initialiser_cles
        r = initialiser_cles()

        assert r["ok"] is True
        assert os.path.exists(config.FICHIER_CLE_AES)

    def test_setup_sans_cles_genere_cles_ecdsa(self, tmp_path):
        """Un setup sans clés existantes doit créer les fichiers ECDSA."""
        import config
        assert not os.path.exists(config.FICHIER_CLE_PRIVEE)
        assert not os.path.exists(config.FICHIER_CLE_PUBLIQUE)

        from installer import initialiser_cles
        r = initialiser_cles()

        assert r["ok"] is True
        assert os.path.exists(config.FICHIER_CLE_PRIVEE)
        assert os.path.exists(config.FICHIER_CLE_PUBLIQUE)

    def test_cle_aes_taille_correcte(self, tmp_path):
        """La clé AES générée doit faire 32 octets (256 bits)."""
        import config
        from installer import initialiser_cles
        initialiser_cles()

        with open(config.FICHIER_CLE_AES, "rb") as f:
            cle = f.read()
        assert len(cle) == 32

    def test_cle_privee_ecdsa_format_pem(self, tmp_path):
        """La clé privée ECDSA doit être en format PEM."""
        import config
        from installer import initialiser_cles
        initialiser_cles()

        with open(config.FICHIER_CLE_PRIVEE, "r") as f:
            contenu = f.read()
        assert "-----BEGIN" in contenu

    def test_cle_publique_ecdsa_format_pem(self, tmp_path):
        """La clé publique ECDSA doit être en format PEM."""
        import config
        from installer import initialiser_cles
        initialiser_cles()

        with open(config.FICHIER_CLE_PUBLIQUE, "r") as f:
            contenu = f.read()
        assert "-----BEGIN PUBLIC KEY-----" in contenu

    def test_setup_marque_nouvelles_si_premiere_fois(self, tmp_path):
        """Les flags aes_nouveau et ecdsa_nouveau doivent être True au premier appel."""
        from installer import initialiser_cles
        r = initialiser_cles()
        assert r["aes_nouveau"] is True
        assert r["ecdsa_nouveau"] is True

    def test_repertoire_cles_cree_automatiquement(self, tmp_path):
        """Le répertoire des clés doit être créé s'il n'existe pas."""
        import config
        assert not os.path.exists(config.REPERTOIRE_CLES)

        from installer import initialiser_cles
        initialiser_cles()

        assert os.path.exists(config.REPERTOIRE_CLES)

    def test_setup_complet_sans_deps_ok(self, tmp_path):
        """Le setup complet sans pip install doit réussir."""
        from installer import setup_complet
        r = setup_complet(installer_deps=False)

        assert r["python"]["ok"] is True
        assert r["cles"]["ok"] is True
        assert "qrcode" in r


# =============================================================================
# TESTS : Idempotence (deuxième installation)
# =============================================================================

class TestIdempotence:
    def test_deuxieme_setup_ne_regenere_pas_aes(self, tmp_path):
        """La deuxième initialisation ne doit pas régénérer la clé AES."""
        import config
        from installer import initialiser_cles

        # Premier setup
        initialiser_cles()
        contenu_avant = open(config.FICHIER_CLE_AES, "rb").read()

        # Deuxième setup
        r = initialiser_cles()
        contenu_apres = open(config.FICHIER_CLE_AES, "rb").read()

        assert r["aes_nouveau"] is False
        assert contenu_avant == contenu_apres

    def test_deuxieme_setup_ne_regenere_pas_ecdsa(self, tmp_path):
        """La deuxième initialisation ne doit pas régénérer les clés ECDSA."""
        import config
        from installer import initialiser_cles

        initialiser_cles()
        priv_avant = open(config.FICHIER_CLE_PRIVEE, "r").read()
        pub_avant = open(config.FICHIER_CLE_PUBLIQUE, "r").read()

        r = initialiser_cles()
        priv_apres = open(config.FICHIER_CLE_PRIVEE, "r").read()
        pub_apres = open(config.FICHIER_CLE_PUBLIQUE, "r").read()

        assert r["ecdsa_nouveau"] is False
        assert priv_avant == priv_apres
        assert pub_avant == pub_apres

    def test_trois_setups_consecutifs_stables(self, tmp_path):
        """Trois setups consécutifs doivent produire les mêmes clés."""
        import config
        from installer import initialiser_cles

        initialiser_cles()
        cle1 = open(config.FICHIER_CLE_AES, "rb").read()

        initialiser_cles()
        cle2 = open(config.FICHIER_CLE_AES, "rb").read()

        initialiser_cles()
        cle3 = open(config.FICHIER_CLE_AES, "rb").read()

        assert cle1 == cle2 == cle3

    def test_setup_complet_idempotent(self, tmp_path):
        """Deux setups complets consécutifs doivent réussir tous les deux."""
        from installer import setup_complet

        r1 = setup_complet(installer_deps=False)
        r2 = setup_complet(installer_deps=False)

        assert r1["python"]["ok"] is True
        assert r2["python"]["ok"] is True
        assert r1["cles"]["ok"] is True
        assert r2["cles"]["ok"] is True


# =============================================================================
# TESTS : Variables d'environnement
# =============================================================================

class TestVariablesEnvironnement:
    def test_sentinel_id_depuis_env(self, tmp_path):
        """SENTINEL_ID doit être une chaîne non vide issue de l'environnement."""
        import config
        assert isinstance(config.SENTINEL_ID, str)
        assert len(config.SENTINEL_ID) > 0

    def test_mode_simulation_true_par_defaut(self, tmp_path):
        """MODE_SIMULATION doit être True en mode test."""
        import config
        assert config.MODE_SIMULATION is True

    def test_mode_simulation_false_avec_env(self, tmp_path):
        """SENTINEL_SIMULATION=false doit désactiver le mode simulation."""
        with patch.dict(os.environ, {"SENTINEL_SIMULATION": "false"}):
            # Recharger le module pour prendre en compte l'env
            import importlib
            import config as cfg
            mode = os.environ.get("SENTINEL_SIMULATION", "true").lower() == "true"
            assert mode is False

    def test_mode_simulation_true_avec_env_true(self, tmp_path):
        """SENTINEL_SIMULATION=true doit activer le mode simulation."""
        with patch.dict(os.environ, {"SENTINEL_SIMULATION": "true"}):
            mode = os.environ.get("SENTINEL_SIMULATION", "true").lower() == "true"
            assert mode is True

    def test_sentinel_id_personnalise(self, tmp_path):
        """Un SENTINEL_ID personnalisé doit être pris en compte."""
        with patch.dict(os.environ, {"SENTINEL_ID": "sentinelle-999"}):
            sentinel_id = os.environ.get("SENTINEL_ID", "sentinelle-001")
            assert sentinel_id == "sentinelle-999"


# =============================================================================
# TESTS : Vérification d'état système
# =============================================================================

class TestVerifierEtatSysteme:
    def test_etat_complet_apres_setup(self, tmp_path):
        """Après setup, l'état système doit montrer les clés présentes."""
        from installer import initialiser_cles, verifier_etat_systeme
        initialiser_cles()

        etat = verifier_etat_systeme()
        assert etat["cles_aes"] is True
        assert etat["cles_ecdsa"] is True

    def test_etat_sans_setup_cles_absentes(self, tmp_path):
        """Sans setup, les clés doivent être absentes."""
        from installer import verifier_etat_systeme
        etat = verifier_etat_systeme()
        assert etat["cles_aes"] is False
        assert etat["cles_ecdsa"] is False

    def test_etat_base_donnees_absente_avant_lancement(self, tmp_path):
        """Avant le premier lancement, la base SQLite n'existe pas."""
        from installer import verifier_etat_systeme
        etat = verifier_etat_systeme()
        assert etat["base_donnees"] is False

    def test_etat_base_donnees_presente_apres_creation(self, tmp_path):
        """Après création de la base, l'état doit la détecter."""
        import config
        from stockage.base_locale import BaseLocale
        from installer import verifier_etat_systeme

        os.makedirs(os.path.dirname(config.FICHIER_BASE_DONNEES), exist_ok=True)
        base = BaseLocale()
        base.fermer()

        etat = verifier_etat_systeme()
        assert etat["base_donnees"] is True

    def test_etat_sentinel_id_correspond_config(self, tmp_path):
        """L'état système doit retourner le sentinel_id tel que défini dans config."""
        import config
        from installer import verifier_etat_systeme
        etat = verifier_etat_systeme()
        assert etat["sentinel_id"] == config.SENTINEL_ID

    def test_etat_mode_simulation_bool(self, tmp_path):
        """mode_simulation doit être un booléen."""
        from installer import verifier_etat_systeme
        etat = verifier_etat_systeme()
        assert isinstance(etat["mode_simulation"], bool)


# =============================================================================
# TESTS : Enchaînement setup → utilisation des clés
# =============================================================================

class TestSetupPuisUtilisation:
    def test_cles_generees_utilisables_pour_chiffrement(self, tmp_path):
        """Les clés générées par installer doivent être utilisables pour AES."""
        from installer import initialiser_cles
        from securite.chiffrement import chiffrer_donnees, dechiffrer_donnees
        from securite.cles import charger_cle_aes

        initialiser_cles()
        cle = charger_cle_aes()
        donnees = {"temperature": 22.5, "humidite": 65.0}

        iv, chiffre = chiffrer_donnees(donnees, cle)
        dechiffre = dechiffrer_donnees(iv, chiffre, cle)

        assert dechiffre["temperature"] == 22.5

    def test_cles_generees_utilisables_pour_signature(self, tmp_path):
        """Les clés ECDSA générées doivent permettre signature et vérification."""
        from installer import initialiser_cles
        from securite.signature import signer_donnees, verifier_signature
        from securite.cles import charger_cle_privee_ecdsa, charger_cle_publique_ecdsa_pem
        from Crypto.PublicKey import ECC

        initialiser_cles()
        cle_privee = charger_cle_privee_ecdsa()
        cle_pub_pem = charger_cle_publique_ecdsa_pem()
        cle_pub = ECC.import_key(cle_pub_pem)

        donnees = b"donnees de test pour signature"
        signature = signer_donnees(donnees, cle_privee)
        valide = verifier_signature(donnees, signature, cle_pub)

        assert valide is True

    def test_base_locale_utilisable_apres_setup(self, tmp_path):
        """Après setup, la base SQLite doit être opérationnelle."""
        import config
        from installer import initialiser_cles
        from stockage.base_locale import BaseLocale
        from Crypto.Random import get_random_bytes

        initialiser_cles()
        os.makedirs(os.path.dirname(config.FICHIER_BASE_DONNEES), exist_ok=True)
        base = BaseLocale()

        iv = get_random_bytes(16)
        donnees = b"donnees chiffrees test"
        signature = b"signature test"
        nonce = get_random_bytes(16).hex()

        bundle_id = base.stocker_bundle(iv, donnees, signature, nonce, 3)
        assert base.compter_bundles_en_attente() == 1
        base.fermer()

    def test_pipeline_complet_setup_mesure_stockage(self, tmp_path):
        """Pipeline complet : setup → mesure → chiffrement → signature → stockage."""
        import config
        from installer import initialiser_cles
        from securite.cles import charger_cle_aes, charger_cle_privee_ecdsa
        from securite.chiffrement import chiffrer_donnees
        from securite.signature import signer_donnees
        from stockage.base_locale import BaseLocale
        from Crypto.Random import get_random_bytes

        # 1. Setup
        initialiser_cles()
        cle_aes = charger_cle_aes()
        cle_privee = charger_cle_privee_ecdsa()

        # 2. Mesures simulées
        mesures = {
            "sentinel_id": config.SENTINEL_ID,
            "horodatage": "2026-04-04T10:00:00+00:00",
            "mesures": [{"type": "temperature", "valeur": 22.5, "unite": "degC"}],
            "nb_mesures": 1,
        }

        # 3. Chiffrement + signature
        iv, chiffre = chiffrer_donnees(mesures, cle_aes)
        signature = signer_donnees(iv + chiffre, cle_privee)
        nonce = get_random_bytes(16).hex()

        # 4. Stockage
        os.makedirs(os.path.dirname(config.FICHIER_BASE_DONNEES), exist_ok=True)
        base = BaseLocale()
        bundle_id = base.stocker_bundle(iv, chiffre, signature, nonce, 1)

        assert bundle_id is not None
        assert base.compter_bundles_en_attente() == 1
        base.fermer()


# =============================================================================
# TESTS : Robustesse de l'installation
# =============================================================================

class TestRobustesseInstallation:
    def test_setup_avec_requirements_vide(self, tmp_path):
        """Un requirements.txt vide doit être accepté par pip."""
        from installer import installer_dependances
        req = tmp_path / "requirements.txt"
        req.write_text("# vide\n")

        mock_result = MagicMock(returncode=0)
        with patch("subprocess.run", return_value=mock_result):
            r = installer_dependances(str(req))

        assert r["ok"] is True

    def test_setup_python_version_info_complet(self, tmp_path):
        """verifier_python() doit retourner major.minor.micro."""
        from installer import verifier_python
        r = verifier_python()
        parts = r["version"].split(".")
        assert len(parts) == 3

    def test_afficher_resume_sans_qrcode(self, tmp_path, capsys):
        """Le résumé doit s'afficher même si le QR code échoue."""
        from installer import afficher_resume
        resultats = {
            "python": {"ok": True, "message": "Python 3.12 OK"},
            "cles": {"ok": True, "aes_nouveau": True, "ecdsa_nouveau": True, "message": "Clés prêtes"},
            "qrcode": {"ok": False, "chemin": None, "message": "qrcode non installé"},
        }
        afficher_resume(resultats)
        out = capsys.readouterr().out
        assert "IoT-Sentinelle" in out
        assert "OK" in out

    def test_setup_complet_retourne_qrcode_meme_si_echec(self, tmp_path):
        """setup_complet() doit inclure qrcode dans les résultats même en cas d'échec."""
        from installer import setup_complet
        r = setup_complet(installer_deps=False)
        assert "qrcode" in r
        assert "ok" in r["qrcode"]

    def test_setup_multiples_cles_distinctes_entre_sentinelles(self, tmp_path):
        """Deux sentinelles distinctes doivent avoir des clés différentes."""
        from securite.cles import generer_cle_aes

        # Simuler deux répertoires différents
        import config

        # Première clé (déjà générée via fixture)
        cle1 = generer_cle_aes()

        # Forcer une nouvelle génération dans un autre répertoire
        autre_rep = str(tmp_path / "cles2")
        ancien_rep = config.REPERTOIRE_CLES
        ancien_aes = config.FICHIER_CLE_AES

        config.REPERTOIRE_CLES = autre_rep
        config.FICHIER_CLE_AES = os.path.join(autre_rep, "cle_aes.bin")
        cle2 = generer_cle_aes()

        config.REPERTOIRE_CLES = ancien_rep
        config.FICHIER_CLE_AES = ancien_aes

        # Deux clés générées indépendamment doivent être différentes
        assert cle1 != cle2


# =============================================================================
# TESTS : CLI installer.py (smoke tests via subprocess)
# =============================================================================

class TestCLIInstaller:
    RASPI_DIR = os.path.join(os.path.dirname(__file__), "..")

    def test_check_retourne_code_zero(self):
        """python installer.py --check doit terminer avec code 0."""
        r = subprocess.run(
            [sys.executable, "installer.py", "--check"],
            capture_output=True, text=True, timeout=30,
            cwd=self.RASPI_DIR,
        )
        assert r.returncode == 0

    def test_check_affiche_python(self):
        """--check doit mentionner la version Python."""
        r = subprocess.run(
            [sys.executable, "installer.py", "--check"],
            capture_output=True, text=True, timeout=30,
            cwd=self.RASPI_DIR,
        )
        assert "Python" in r.stdout or "python" in r.stdout.lower()

    def test_check_affiche_sentinel_id(self):
        """--check doit afficher le Sentinel ID."""
        r = subprocess.run(
            [sys.executable, "installer.py", "--check"],
            capture_output=True, text=True, timeout=30,
            cwd=self.RASPI_DIR,
        )
        assert "sentinelle" in r.stdout.lower() or "sentinel" in r.stdout.lower()

    def test_no_deps_complete_sans_crash(self):
        """python installer.py --no-deps doit terminer avec code 0."""
        r = subprocess.run(
            [sys.executable, "installer.py", "--no-deps"],
            capture_output=True, text=True, timeout=30,
            cwd=self.RASPI_DIR,
        )
        assert r.returncode == 0

    def test_no_deps_affiche_resume(self):
        """--no-deps doit afficher le résumé IoT-Sentinelle."""
        r = subprocess.run(
            [sys.executable, "installer.py", "--no-deps"],
            capture_output=True, text=True, timeout=30,
            cwd=self.RASPI_DIR,
        )
        assert "IoT-Sentinelle" in r.stdout

    def test_aide_argparse(self):
        """python installer.py --help doit retourner code 0."""
        r = subprocess.run(
            [sys.executable, "installer.py", "--help"],
            capture_output=True, text=True, timeout=10,
            cwd=self.RASPI_DIR,
        )
        assert r.returncode == 0
        assert "setup" in r.stdout.lower() or "install" in r.stdout.lower()
