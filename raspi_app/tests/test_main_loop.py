"""
test_main_loop.py -- Tests de la boucle principale (main.py).

Valide l'orchestration du firmware :
- Initialisation des composants (clés, capteurs, BLE, énergie)
- Cycle de mesure complet (lire → chiffrer → signer → stocker)
- Gestion des signaux (SIGINT/SIGTERM → arrêt propre)
- Comportement en cas d'erreur dans la boucle
- Fonction creer_et_stocker_bundle isolée
"""

import os
import sys
import signal
import pytest
from unittest.mock import patch, MagicMock, call
from Crypto.Random import get_random_bytes


# =============================================================================
# TESTS : creer_et_stocker_bundle()
# =============================================================================

class TestCreerEtStockerBundle:
    def test_retourne_bundle_id(self, cle_aes, cle_privee_ecdsa, base_locale, mesures_exemple):
        """creer_et_stocker_bundle doit retourner un identifiant."""
        from main import creer_et_stocker_bundle
        bundle_id = creer_et_stocker_bundle(mesures_exemple, cle_aes, cle_privee_ecdsa, base_locale)
        assert bundle_id is not None
        assert len(bundle_id) > 0

    def test_bundle_id_est_uuid(self, cle_aes, cle_privee_ecdsa, base_locale, mesures_exemple):
        """Le bundle_id doit être au format UUID."""
        import re
        from main import creer_et_stocker_bundle
        bundle_id = creer_et_stocker_bundle(mesures_exemple, cle_aes, cle_privee_ecdsa, base_locale)
        uuid_pattern = re.compile(
            r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
        )
        assert uuid_pattern.match(bundle_id)

    def test_bundle_stocke_en_base(self, cle_aes, cle_privee_ecdsa, base_locale, mesures_exemple):
        """Après creer_et_stocker_bundle, la base doit contenir 1 bundle."""
        from main import creer_et_stocker_bundle
        assert base_locale.compter_bundles_en_attente() == 0
        creer_et_stocker_bundle(mesures_exemple, cle_aes, cle_privee_ecdsa, base_locale)
        assert base_locale.compter_bundles_en_attente() == 1

    def test_bundle_contient_iv_chiffre_signature(self, cle_aes, cle_privee_ecdsa, base_locale, mesures_exemple):
        """Le bundle stocké doit contenir iv, donnees_chiffrees et signature."""
        from main import creer_et_stocker_bundle
        creer_et_stocker_bundle(mesures_exemple, cle_aes, cle_privee_ecdsa, base_locale)
        bundle = base_locale.recuperer_bundle_par_index(0)
        assert "iv" in bundle
        assert "donnees_chiffrees" in bundle
        assert "signature" in bundle

    def test_nonce_present_et_hex(self, cle_aes, cle_privee_ecdsa, base_locale, mesures_exemple):
        """Le nonce anti-rejeu doit être présent et en hexadécimal."""
        from main import creer_et_stocker_bundle
        creer_et_stocker_bundle(mesures_exemple, cle_aes, cle_privee_ecdsa, base_locale)
        bundle = base_locale.recuperer_bundle_par_index(0)
        assert "nonce" in bundle
        try:
            bytes.fromhex(bundle["nonce"])
        except ValueError:
            pytest.fail("nonce n'est pas en hexadécimal valide")

    def test_nonce_taille_32_hex(self, cle_aes, cle_privee_ecdsa, base_locale, mesures_exemple):
        """Le nonce doit être de 16 octets = 32 caractères hexadécimaux."""
        from main import creer_et_stocker_bundle
        creer_et_stocker_bundle(mesures_exemple, cle_aes, cle_privee_ecdsa, base_locale)
        bundle = base_locale.recuperer_bundle_par_index(0)
        assert len(bundle["nonce"]) == 32

    def test_deux_bundles_ont_nonces_differents(self, cle_aes, cle_privee_ecdsa, base_locale, mesures_exemple):
        """Deux bundles doivent avoir des nonces différents (anti-rejeu)."""
        from main import creer_et_stocker_bundle
        creer_et_stocker_bundle(mesures_exemple, cle_aes, cle_privee_ecdsa, base_locale)
        creer_et_stocker_bundle(mesures_exemple, cle_aes, cle_privee_ecdsa, base_locale)
        b1 = base_locale.recuperer_bundle_par_index(0)
        b2 = base_locale.recuperer_bundle_par_index(1)
        assert b1["nonce"] != b2["nonce"]

    def test_bundle_donnees_dechiffrables(self, cle_aes, cle_privee_ecdsa, base_locale, mesures_exemple):
        """Les données du bundle doivent être déchiffrables avec la clé AES."""
        import base64
        from main import creer_et_stocker_bundle
        from securite.chiffrement import dechiffrer_donnees

        creer_et_stocker_bundle(mesures_exemple, cle_aes, cle_privee_ecdsa, base_locale)
        bundle = base_locale.recuperer_bundle_par_index(0)

        iv = base64.b64decode(bundle["iv"])
        donnees_chiffrees = base64.b64decode(bundle["donnees_chiffrees"])

        dechiffre = dechiffrer_donnees(iv, donnees_chiffrees, cle_aes)
        assert dechiffre["nb_mesures"] == mesures_exemple["nb_mesures"]

    def test_signature_verifiable(self, cle_aes, cle_privee_ecdsa, base_locale, mesures_exemple):
        """La signature ECDSA du bundle doit être vérifiable."""
        import base64
        from Crypto.PublicKey import ECC
        from main import creer_et_stocker_bundle
        from securite.signature import verifier_signature
        from securite.cles import charger_cle_publique_ecdsa_pem

        creer_et_stocker_bundle(mesures_exemple, cle_aes, cle_privee_ecdsa, base_locale)
        bundle = base_locale.recuperer_bundle_par_index(0)

        iv = base64.b64decode(bundle["iv"])
        donnees_chiffrees = base64.b64decode(bundle["donnees_chiffrees"])
        signature = base64.b64decode(bundle["signature"])

        cle_pub_pem = charger_cle_publique_ecdsa_pem()
        cle_pub = ECC.import_key(cle_pub_pem)

        assert verifier_signature(iv + donnees_chiffrees, signature, cle_pub) is True

    def test_plusieurs_cycles_incrementent_compteur(self, cle_aes, cle_privee_ecdsa, base_locale, mesures_exemple):
        """Chaque appel doit incrémenter le nombre de bundles."""
        from main import creer_et_stocker_bundle
        for i in range(5):
            creer_et_stocker_bundle(mesures_exemple, cle_aes, cle_privee_ecdsa, base_locale)
        assert base_locale.compter_bundles_en_attente() == 5


# =============================================================================
# TESTS : gestionnaire_signal()
# =============================================================================

class TestGestionnaireSignal:
    def test_sigint_met_fin_fonctionnement_a_false(self):
        """SIGINT doit mettre en_fonctionnement à False."""
        import main
        main.en_fonctionnement = True
        main.gestionnaire_signal(signal.SIGINT, None)
        assert main.en_fonctionnement is False
        # Reset
        main.en_fonctionnement = True

    def test_sigterm_met_fin_fonctionnement_a_false(self):
        """SIGTERM doit mettre en_fonctionnement à False."""
        import main
        main.en_fonctionnement = True
        main.gestionnaire_signal(signal.SIGTERM, None)
        assert main.en_fonctionnement is False
        main.en_fonctionnement = True

    def test_gestionnaire_appele_avec_signal_inconnu(self):
        """Le gestionnaire ne doit pas planter avec un signal quelconque."""
        import main
        main.en_fonctionnement = True
        try:
            main.gestionnaire_signal(99, None)
        except Exception:
            pytest.fail("gestionnaire_signal ne doit pas lever d'exception")
        main.en_fonctionnement = True


# =============================================================================
# TESTS : Boucle principale (main() mockée)
# =============================================================================

class TestBouclePrincipale:
    def _mocks_complets(self):
        """Retourne un dict de mocks pour tous les composants."""
        mock_cle_aes = get_random_bytes(32)
        mock_cle_privee = MagicMock()
        mock_cle_pub_pem = "-----BEGIN PUBLIC KEY-----\nMOCK\n-----END PUBLIC KEY-----"

        mock_gestionnaire_capteurs = MagicMock()
        mock_gestionnaire_capteurs.lire_tous.return_value = {
            "sentinel_id": "test-sentinelle-001",
            "horodatage": "2026-04-04T10:00:00+00:00",
            "mesures": [{"type": "temperature", "valeur": 22.5, "unite": "degC"}],
            "nb_mesures": 1,
        }

        mock_base = MagicMock()
        mock_base.compter_bundles_en_attente.return_value = 1
        mock_base.stocker_bundle.return_value = "fake-bundle-uuid"

        mock_serveur_ble = MagicMock()
        mock_gestionnaire_energie = MagicMock()

        return {
            "cle_aes": mock_cle_aes,
            "cle_privee": mock_cle_privee,
            "cle_pub_pem": mock_cle_pub_pem,
            "capteurs": mock_gestionnaire_capteurs,
            "base": mock_base,
            "ble": mock_serveur_ble,
            "energie": mock_gestionnaire_energie,
        }

    def test_main_execute_au_moins_un_cycle(self):
        """main() doit exécuter au moins un cycle de mesure avant de s'arrêter."""
        import main as main_module
        mocks = self._mocks_complets()

        # On fait tourner la boucle exactement 1 fois
        call_count = [0]
        def energie_side_effect():
            call_count[0] += 1
            main_module.en_fonctionnement = False

        mocks["energie"].entrer_veille.side_effect = energie_side_effect

        with patch("main.charger_cle_aes", return_value=mocks["cle_aes"]), \
             patch("main.charger_cle_privee_ecdsa", return_value=mocks["cle_privee"]), \
             patch("main.charger_cle_publique_ecdsa_pem", return_value=mocks["cle_pub_pem"]), \
             patch("main.GestionnaireCapteurs", return_value=mocks["capteurs"]), \
             patch("main.BaseLocale", return_value=mocks["base"]), \
             patch("main.ServeurBLE", return_value=mocks["ble"]), \
             patch("main.GestionnaireEnergie", return_value=mocks["energie"]), \
             patch("main.creer_et_stocker_bundle", return_value="fake-uuid"):
            main_module.en_fonctionnement = True
            main_module.main()

        assert call_count[0] >= 1

    def test_main_appelle_demarrer_ble(self):
        """main() doit appeler serveur_ble.demarrer()."""
        import main as main_module
        mocks = self._mocks_complets()

        def stop_loop():
            main_module.en_fonctionnement = False

        mocks["energie"].entrer_veille.side_effect = stop_loop

        with patch("main.charger_cle_aes", return_value=mocks["cle_aes"]), \
             patch("main.charger_cle_privee_ecdsa", return_value=mocks["cle_privee"]), \
             patch("main.charger_cle_publique_ecdsa_pem", return_value=mocks["cle_pub_pem"]), \
             patch("main.GestionnaireCapteurs", return_value=mocks["capteurs"]), \
             patch("main.BaseLocale", return_value=mocks["base"]), \
             patch("main.ServeurBLE", return_value=mocks["ble"]), \
             patch("main.GestionnaireEnergie", return_value=mocks["energie"]), \
             patch("main.creer_et_stocker_bundle", return_value="fake-uuid"):
            main_module.en_fonctionnement = True
            main_module.main()

        mocks["ble"].demarrer.assert_called_once()

    def test_main_appelle_arreter_ble_a_la_fin(self):
        """main() doit appeler serveur_ble.arreter() lors de l'arrêt propre."""
        import main as main_module
        mocks = self._mocks_complets()

        def stop_loop():
            main_module.en_fonctionnement = False

        mocks["energie"].entrer_veille.side_effect = stop_loop

        with patch("main.charger_cle_aes", return_value=mocks["cle_aes"]), \
             patch("main.charger_cle_privee_ecdsa", return_value=mocks["cle_privee"]), \
             patch("main.charger_cle_publique_ecdsa_pem", return_value=mocks["cle_pub_pem"]), \
             patch("main.GestionnaireCapteurs", return_value=mocks["capteurs"]), \
             patch("main.BaseLocale", return_value=mocks["base"]), \
             patch("main.ServeurBLE", return_value=mocks["ble"]), \
             patch("main.GestionnaireEnergie", return_value=mocks["energie"]), \
             patch("main.creer_et_stocker_bundle", return_value="fake-uuid"):
            main_module.en_fonctionnement = True
            main_module.main()

        mocks["ble"].arreter.assert_called_once()

    def test_main_ferme_base_a_la_fin(self):
        """main() doit appeler base.fermer() lors de l'arrêt propre."""
        import main as main_module
        mocks = self._mocks_complets()

        def stop_loop():
            main_module.en_fonctionnement = False

        mocks["energie"].entrer_veille.side_effect = stop_loop

        with patch("main.charger_cle_aes", return_value=mocks["cle_aes"]), \
             patch("main.charger_cle_privee_ecdsa", return_value=mocks["cle_privee"]), \
             patch("main.charger_cle_publique_ecdsa_pem", return_value=mocks["cle_pub_pem"]), \
             patch("main.GestionnaireCapteurs", return_value=mocks["capteurs"]), \
             patch("main.BaseLocale", return_value=mocks["base"]), \
             patch("main.ServeurBLE", return_value=mocks["ble"]), \
             patch("main.GestionnaireEnergie", return_value=mocks["energie"]), \
             patch("main.creer_et_stocker_bundle", return_value="fake-uuid"):
            main_module.en_fonctionnement = True
            main_module.main()

        mocks["base"].fermer.assert_called_once()

    def test_main_appelle_fermer_capteurs_a_la_fin(self):
        """main() doit appeler gestionnaire_capteurs.fermer_tous() à l'arrêt."""
        import main as main_module
        mocks = self._mocks_complets()

        def stop_loop():
            main_module.en_fonctionnement = False

        mocks["energie"].entrer_veille.side_effect = stop_loop

        with patch("main.charger_cle_aes", return_value=mocks["cle_aes"]), \
             patch("main.charger_cle_privee_ecdsa", return_value=mocks["cle_privee"]), \
             patch("main.charger_cle_publique_ecdsa_pem", return_value=mocks["cle_pub_pem"]), \
             patch("main.GestionnaireCapteurs", return_value=mocks["capteurs"]), \
             patch("main.BaseLocale", return_value=mocks["base"]), \
             patch("main.ServeurBLE", return_value=mocks["ble"]), \
             patch("main.GestionnaireEnergie", return_value=mocks["energie"]), \
             patch("main.creer_et_stocker_bundle", return_value="fake-uuid"):
            main_module.en_fonctionnement = True
            main_module.main()

        mocks["capteurs"].fermer_tous.assert_called_once()

    def test_main_continue_apres_exception_capteurs(self):
        """Une exception dans lire_tous() ne doit pas crasher la boucle."""
        import main as main_module
        mocks = self._mocks_complets()

        call_count = [0]
        def lire_side_effect():
            call_count[0] += 1
            if call_count[0] == 1:
                raise RuntimeError("Capteur défaillant")
            main_module.en_fonctionnement = False
            return {
                "sentinel_id": "test", "horodatage": "2026-04-04T10:00:00+00:00",
                "mesures": [], "nb_mesures": 0,
            }

        mocks["capteurs"].lire_tous.side_effect = lire_side_effect

        with patch("main.charger_cle_aes", return_value=mocks["cle_aes"]), \
             patch("main.charger_cle_privee_ecdsa", return_value=mocks["cle_privee"]), \
             patch("main.charger_cle_publique_ecdsa_pem", return_value=mocks["cle_pub_pem"]), \
             patch("main.GestionnaireCapteurs", return_value=mocks["capteurs"]), \
             patch("main.BaseLocale", return_value=mocks["base"]), \
             patch("main.ServeurBLE", return_value=mocks["ble"]), \
             patch("main.GestionnaireEnergie", return_value=mocks["energie"]), \
             patch("main.creer_et_stocker_bundle", return_value="fake-uuid"), \
             patch("time.sleep"):
            main_module.en_fonctionnement = True
            main_module.main()  # Ne doit pas lever d'exception

        assert call_count[0] >= 2

    def test_main_ne_stocke_pas_si_aucune_mesure(self):
        """Si nb_mesures == 0, creer_et_stocker_bundle ne doit pas être appelé."""
        import main as main_module
        mocks = self._mocks_complets()

        mocks["capteurs"].lire_tous.return_value = {
            "sentinel_id": "test", "horodatage": "2026-04-04T10:00:00+00:00",
            "mesures": [], "nb_mesures": 0,
        }

        def stop_loop():
            main_module.en_fonctionnement = False

        mocks["energie"].entrer_veille.side_effect = stop_loop

        with patch("main.charger_cle_aes", return_value=mocks["cle_aes"]), \
             patch("main.charger_cle_privee_ecdsa", return_value=mocks["cle_privee"]), \
             patch("main.charger_cle_publique_ecdsa_pem", return_value=mocks["cle_pub_pem"]), \
             patch("main.GestionnaireCapteurs", return_value=mocks["capteurs"]), \
             patch("main.BaseLocale", return_value=mocks["base"]), \
             patch("main.ServeurBLE", return_value=mocks["ble"]), \
             patch("main.GestionnaireEnergie", return_value=mocks["energie"]), \
             patch("main.creer_et_stocker_bundle", return_value="fake-uuid") as mock_creer:
            main_module.en_fonctionnement = True
            main_module.main()

        mock_creer.assert_not_called()

    def test_main_notifie_ble_apres_stockage(self):
        """Après chaque bundle stocké, notifier_nouveau_bundle() doit être appelé."""
        import main as main_module
        mocks = self._mocks_complets()

        def stop_loop():
            main_module.en_fonctionnement = False

        mocks["energie"].entrer_veille.side_effect = stop_loop

        with patch("main.charger_cle_aes", return_value=mocks["cle_aes"]), \
             patch("main.charger_cle_privee_ecdsa", return_value=mocks["cle_privee"]), \
             patch("main.charger_cle_publique_ecdsa_pem", return_value=mocks["cle_pub_pem"]), \
             patch("main.GestionnaireCapteurs", return_value=mocks["capteurs"]), \
             patch("main.BaseLocale", return_value=mocks["base"]), \
             patch("main.ServeurBLE", return_value=mocks["ble"]), \
             patch("main.GestionnaireEnergie", return_value=mocks["energie"]), \
             patch("main.creer_et_stocker_bundle", return_value="fake-uuid"):
            main_module.en_fonctionnement = True
            main_module.main()

        mocks["ble"].notifier_nouveau_bundle.assert_called()

    def test_main_plusieurs_cycles(self):
        """main() doit exécuter plusieurs cycles avant l'arrêt."""
        import main as main_module
        mocks = self._mocks_complets()

        cycle_count = [0]
        def energie_side():
            cycle_count[0] += 1
            if cycle_count[0] >= 3:
                main_module.en_fonctionnement = False

        mocks["energie"].entrer_veille.side_effect = energie_side

        with patch("main.charger_cle_aes", return_value=mocks["cle_aes"]), \
             patch("main.charger_cle_privee_ecdsa", return_value=mocks["cle_privee"]), \
             patch("main.charger_cle_publique_ecdsa_pem", return_value=mocks["cle_pub_pem"]), \
             patch("main.GestionnaireCapteurs", return_value=mocks["capteurs"]), \
             patch("main.BaseLocale", return_value=mocks["base"]), \
             patch("main.ServeurBLE", return_value=mocks["ble"]), \
             patch("main.GestionnaireEnergie", return_value=mocks["energie"]), \
             patch("main.creer_et_stocker_bundle", return_value="fake-uuid"):
            main_module.en_fonctionnement = True
            main_module.main()

        assert cycle_count[0] == 3
        assert mocks["capteurs"].lire_tous.call_count == 3


# =============================================================================
# TESTS : Démarrage et imports de main.py
# =============================================================================

class TestMainImports:
    def test_main_importable(self):
        """main.py doit être importable sans erreur."""
        try:
            import main
        except Exception as e:
            pytest.fail(f"Impossible d'importer main.py : {e}")

    def test_en_fonctionnement_est_true_au_demarrage(self):
        """La variable globale en_fonctionnement doit être True initialement."""
        import main
        # On remet à True si un test précédent l'a modifiée
        main.en_fonctionnement = True
        assert main.en_fonctionnement is True

    def test_creer_et_stocker_bundle_importable(self):
        """creer_et_stocker_bundle doit être importable depuis main."""
        from main import creer_et_stocker_bundle
        assert callable(creer_et_stocker_bundle)

    def test_gestionnaire_signal_importable(self):
        """gestionnaire_signal doit être importable depuis main."""
        from main import gestionnaire_signal
        assert callable(gestionnaire_signal)
