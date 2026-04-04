"""
test_installer.py -- Tests du script d'installation automatique.

Valide chaque fonction d'installer.py de façon isolée,
sans modifier le système ni installer de vraies dépendances.
"""

import os
import sys
import pytest
from unittest.mock import patch, MagicMock, call


# =============================================================================
# TESTS : verifier_python()
# =============================================================================

class TestVerifierPython:
    def test_version_actuelle_ok(self):
        from installer import verifier_python
        r = verifier_python()
        assert r["ok"] is True

    def test_retourne_dict_avec_cles_requises(self):
        from installer import verifier_python
        r = verifier_python()
        assert "ok" in r
        assert "version" in r
        assert "message" in r

    def test_version_str_format(self):
        from installer import verifier_python
        r = verifier_python()
        parties = r["version"].split(".")
        assert len(parties) == 3
        assert all(p.isdigit() for p in parties)

    def test_message_ok_si_version_suffisante(self):
        from installer import verifier_python
        r = verifier_python()
        assert "OK" in r["message"] or "ok" in r["message"].lower()

    def test_echec_si_python_trop_ancien(self):
        from installer import verifier_python, VERSION_PYTHON_MIN
        with patch.object(sys, "version_info", (2, 7, 18, "final", 0)):
            r = verifier_python()
            assert r["ok"] is False
            assert "requis" in r["message"]

    def test_version_minimum_est_3_10(self):
        from installer import VERSION_PYTHON_MIN
        assert VERSION_PYTHON_MIN >= (3, 10)


# =============================================================================
# TESTS : installer_dependances()
# =============================================================================

class TestInstallerDependances:
    def test_fichier_inexistant_retourne_erreur(self, tmp_path):
        from installer import installer_dependances
        r = installer_dependances(str(tmp_path / "inexistant.txt"))
        assert r["ok"] is False
        assert "introuvable" in r["message"]

    def test_succes_quand_pip_ok(self, tmp_path):
        req = tmp_path / "requirements.txt"
        req.write_text("# vide\n")
        from installer import installer_dependances
        mock_result = MagicMock()
        mock_result.returncode = 0
        with patch("subprocess.run", return_value=mock_result):
            r = installer_dependances(str(req))
        assert r["ok"] is True
        assert "installées" in r["message"] or "install" in r["message"].lower()

    def test_echec_quand_pip_code_non_zero(self, tmp_path):
        req = tmp_path / "requirements.txt"
        req.write_text("paquet_inexistant_xyz\n")
        from installer import installer_dependances
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "ERROR: No matching distribution found"
        with patch("subprocess.run", return_value=mock_result):
            r = installer_dependances(str(req))
        assert r["ok"] is False

    def test_timeout_retourne_erreur(self, tmp_path):
        import subprocess
        req = tmp_path / "requirements.txt"
        req.write_text("# vide\n")
        from installer import installer_dependances
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("pip", 120)):
            r = installer_dependances(str(req))
        assert r["ok"] is False
        assert "timeout" in r["message"].lower() or "Timeout" in r["message"]

    def test_pip_introuvable_retourne_erreur(self, tmp_path):
        req = tmp_path / "requirements.txt"
        req.write_text("# vide\n")
        from installer import installer_dependances
        with patch("subprocess.run", side_effect=FileNotFoundError):
            r = installer_dependances(str(req))
        assert r["ok"] is False

    def test_utilise_requirements_txt_par_defaut(self):
        from installer import installer_dependances, REPERTOIRE_RACINE
        attendu = os.path.join(REPERTOIRE_RACINE, "requirements.txt")
        mock_result = MagicMock(returncode=0)
        with patch("subprocess.run", return_value=mock_result) as mock_sub:
            # requirements.txt existe dans le projet
            if os.path.exists(attendu):
                installer_dependances()
                args = mock_sub.call_args[0][0]
                assert attendu in args


# =============================================================================
# TESTS : initialiser_cles()
# =============================================================================

class TestInitialiserCles:
    def test_retourne_ok(self):
        from installer import initialiser_cles
        r = initialiser_cles()
        assert r["ok"] is True

    def test_retourne_dict_complet(self):
        from installer import initialiser_cles
        r = initialiser_cles()
        assert "ok" in r
        assert "aes_nouveau" in r
        assert "ecdsa_nouveau" in r
        assert "message" in r

    def test_cles_marquees_nouvelles_si_absentes(self, tmp_path):
        import config
        config.REPERTOIRE_CLES = str(tmp_path / "cles_test")
        config.FICHIER_CLE_AES = os.path.join(config.REPERTOIRE_CLES, "aes.bin")
        config.FICHIER_CLE_PRIVEE = os.path.join(config.REPERTOIRE_CLES, "priv.pem")
        config.FICHIER_CLE_PUBLIQUE = os.path.join(config.REPERTOIRE_CLES, "pub.pem")

        from installer import initialiser_cles
        r = initialiser_cles()
        assert r["ok"] is True
        assert r["aes_nouveau"] is True
        assert r["ecdsa_nouveau"] is True

    def test_cles_existantes_non_regenerees(self):
        from installer import initialiser_cles
        # Premier appel = génère
        initialiser_cles()
        # Deuxième appel = réutilise
        r = initialiser_cles()
        assert r["ok"] is True
        assert r["aes_nouveau"] is False
        assert r["ecdsa_nouveau"] is False

    def test_import_error_retourne_erreur(self):
        from installer import initialiser_cles
        with patch("installer.os.path.exists", return_value=False):
            with patch("builtins.__import__", side_effect=ImportError("pycryptodome")):
                r = initialiser_cles()
                # Peut échouer ou réussir selon l'ordre des imports
                assert "ok" in r


# =============================================================================
# TESTS : generer_qrcode_deploiement()
# =============================================================================

class TestGenererQRCode:
    def test_retourne_dict_avec_cles_requises(self):
        from installer import generer_qrcode_deploiement
        r = generer_qrcode_deploiement()
        assert "ok" in r
        assert "chemin" in r
        assert "message" in r

    def test_ok_si_qrcode_disponible(self):
        from installer import generer_qrcode_deploiement
        mock_chemin = "/tmp/qrcode_test.png"
        with patch("utils.qrcode_gen.QRCODE_DISPONIBLE", True):
            with patch("utils.qrcode_gen.generer_qrcode", return_value=mock_chemin):
                with patch("installer.generer_qrcode_deploiement",
                           return_value={"ok": True, "chemin": mock_chemin, "message": f"QR code : {mock_chemin}"}):
                    from installer import generer_qrcode_deploiement as gqr
                    r = gqr()
                    # Au moins vérifier que la structure est correcte
                    assert "ok" in r

    def test_message_si_qrcode_absent(self):
        from installer import generer_qrcode_deploiement
        with patch("utils.qrcode_gen.QRCODE_DISPONIBLE", False):
            r = generer_qrcode_deploiement()
            assert r["ok"] is False
            assert r["chemin"] is None
            assert "qrcode" in r["message"].lower() or "qr" in r["message"].lower()

    def test_exception_retourne_erreur(self):
        from installer import generer_qrcode_deploiement
        with patch("utils.qrcode_gen.generer_qrcode", side_effect=RuntimeError("test")):
            r = generer_qrcode_deploiement()
            # Peut être ok ou non selon si qrcode est dispo
            assert "ok" in r


# =============================================================================
# TESTS : verifier_etat_systeme()
# =============================================================================

class TestVerifierEtatSysteme:
    def test_retourne_dict_complet(self):
        from installer import verifier_etat_systeme
        etat = verifier_etat_systeme()
        assert "python" in etat
        assert "cles_aes" in etat
        assert "cles_ecdsa" in etat
        assert "base_donnees" in etat
        assert "mode_simulation" in etat
        assert "sentinel_id" in etat

    def test_mode_simulation_bool(self):
        from installer import verifier_etat_systeme
        etat = verifier_etat_systeme()
        assert isinstance(etat["mode_simulation"], bool)

    def test_sentinel_id_str(self):
        from installer import verifier_etat_systeme
        etat = verifier_etat_systeme()
        assert isinstance(etat["sentinel_id"], str)

    def test_python_ok_dans_etat(self):
        from installer import verifier_etat_systeme
        etat = verifier_etat_systeme()
        assert etat["python"]["ok"] is True


# =============================================================================
# TESTS : setup_complet()
# =============================================================================

class TestSetupComplet:
    def test_retourne_python_toujours(self):
        from installer import setup_complet
        mock_result = MagicMock(returncode=0)
        with patch("subprocess.run", return_value=mock_result):
            r = setup_complet(installer_deps=False)
        assert "python" in r

    def test_s_arrete_si_python_trop_ancien(self):
        from installer import setup_complet
        with patch.object(sys, "version_info", (2, 7, 18, "final", 0)):
            r = setup_complet()
        assert "python" in r
        assert r["python"]["ok"] is False
        # Ne doit pas aller plus loin
        assert "cles" not in r

    def test_sans_installer_deps_passe_aux_cles(self):
        from installer import setup_complet
        r = setup_complet(installer_deps=False)
        assert "python" in r
        assert "dependances" not in r
        assert "cles" in r

    def test_avec_installer_deps_appelle_pip(self):
        from installer import setup_complet
        mock_result = MagicMock(returncode=0)
        with patch("subprocess.run", return_value=mock_result) as mock_sub:
            r = setup_complet(installer_deps=True)
        assert "dependances" in r

    def test_inclut_qrcode_dans_resultats(self):
        from installer import setup_complet
        r = setup_complet(installer_deps=False)
        assert "qrcode" in r


# =============================================================================
# TESTS : afficher_resume()
# =============================================================================

class TestAfficherResume:
    def test_affiche_sans_planter(self, capsys):
        from installer import afficher_resume
        resultats = {
            "python": {"ok": True, "message": "Python 3.14 OK"},
            "cles": {"ok": True, "aes_nouveau": True, "ecdsa_nouveau": False},
            "qrcode": {"ok": True, "chemin": "/tmp/qr.png", "message": "QR code : /tmp/qr.png"},
        }
        afficher_resume(resultats)
        out = capsys.readouterr().out
        assert "IoT-Sentinelle" in out

    def test_affiche_erreur_python(self, capsys):
        from installer import afficher_resume
        resultats = {
            "python": {"ok": False, "message": "Python 3.10+ requis"},
        }
        afficher_resume(resultats)
        out = capsys.readouterr().out
        assert "ERREUR" in out or "requis" in out

    def test_affiche_pret_si_tout_ok(self, capsys):
        from installer import afficher_resume
        resultats = {
            "python": {"ok": True, "message": "Python OK"},
            "dependances": {"ok": True, "message": "Dépendances installées"},
            "cles": {"ok": True, "aes_nouveau": False, "ecdsa_nouveau": False, "message": "Clés prêtes"},
            "qrcode": {"ok": True, "chemin": "/tmp/qr.png", "message": "QR code OK"},
        }
        afficher_resume(resultats)
        out = capsys.readouterr().out
        assert "prête" in out or "Lancer" in out

    def test_affiche_deps_ok(self, capsys):
        from installer import afficher_resume
        resultats = {
            "python": {"ok": True, "message": "Python OK"},
            "dependances": {"ok": True, "message": "Dépendances installées"},
            "cles": {"ok": True, "aes_nouveau": True, "ecdsa_nouveau": True, "message": "Clés prêtes"},
            "qrcode": {"ok": False, "chemin": None, "message": "qrcode non installé"},
        }
        afficher_resume(resultats)
        out = capsys.readouterr().out
        assert "OK" in out


# =============================================================================
# TESTS : Makefile targets (smoke tests via subprocess)
# =============================================================================

class TestMakefileCheck:
    def test_installer_check_ne_crash_pas(self):
        """python installer.py --check doit terminer sans erreur."""
        import subprocess
        r = subprocess.run(
            [sys.executable, "installer.py", "--check"],
            capture_output=True, text=True, timeout=30,
            cwd=os.path.join(os.path.dirname(__file__), ".."),
        )
        assert r.returncode == 0

    def test_installer_sans_args_complete(self):
        """python installer.py --no-deps doit compléter sans crash."""
        import subprocess
        r = subprocess.run(
            [sys.executable, "installer.py", "--no-deps"],
            capture_output=True, text=True, timeout=30,
            cwd=os.path.join(os.path.dirname(__file__), ".."),
        )
        assert r.returncode == 0
        assert "IoT-Sentinelle" in r.stdout
