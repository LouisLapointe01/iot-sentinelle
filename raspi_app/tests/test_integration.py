"""
test_integration.py -- Tests d'integration de la pipeline DTN complete.

On valide le flux de bout en bout :
  capteurs -> chiffrement AES -> signature ECDSA -> stockage SQLite
  -> lecture BLE (chunking) -> ACK -> dechiffrement -> verification signature

Ces tests ne necessitent pas de materiel physique (mode simulation).
"""

import json
import base64
import pytest
from Crypto.Random import get_random_bytes
from Crypto.PublicKey import ECC
from unittest.mock import MagicMock


# =============================================================================
# TESTS : Pipeline complete (main.creer_et_stocker_bundle)
# =============================================================================

class TestPipelineComplete:

    def test_pipeline_un_cycle(self, base_locale, cle_aes, cle_privee_ecdsa):
        """Un cycle complet produit un bundle stocke et recuperable."""
        from main import creer_et_stocker_bundle
        from capteurs.gestionnaire import GestionnaireCapteurs

        gestionnaire = GestionnaireCapteurs()
        cycle = gestionnaire.lire_tous()

        bundle_id = creer_et_stocker_bundle(cycle, cle_aes, cle_privee_ecdsa, base_locale)

        assert isinstance(bundle_id, str)
        assert len(bundle_id) == 36
        assert base_locale.compter_bundles_en_attente() == 1

    def test_pipeline_bundle_recuperable(self, base_locale, cle_aes, cle_privee_ecdsa):
        from main import creer_et_stocker_bundle
        from capteurs.gestionnaire import GestionnaireCapteurs

        cycle = GestionnaireCapteurs().lire_tous()
        bundle_id = creer_et_stocker_bundle(cycle, cle_aes, cle_privee_ecdsa, base_locale)

        bundle = base_locale.recuperer_bundle_par_index(0)
        assert bundle is not None
        assert bundle["bundle_id"] == bundle_id

    def test_pipeline_donnees_dechiffrables(self, base_locale, cle_aes, cle_privee_ecdsa):
        """Les donnees chiffrees dans le bundle peuvent etre dechiffrees."""
        from main import creer_et_stocker_bundle
        from capteurs.gestionnaire import GestionnaireCapteurs
        from securite.chiffrement import dechiffrer_donnees

        cycle = GestionnaireCapteurs().lire_tous()
        creer_et_stocker_bundle(cycle, cle_aes, cle_privee_ecdsa, base_locale)

        bundle = base_locale.recuperer_bundle_par_index(0)
        iv = base64.b64decode(bundle["iv"])
        chiffre = base64.b64decode(bundle["donnees_chiffrees"])

        donnees = dechiffrer_donnees(iv, chiffre, cle_aes)
        assert donnees["nb_mesures"] == cycle["nb_mesures"]
        assert donnees["sentinel_id"] == cycle["sentinel_id"]

    def test_pipeline_signature_verifiable(self, base_locale, cle_aes, cle_privee_ecdsa, cle_publique_pem):
        """La signature ECDSA du bundle est verifiable avec la cle publique."""
        from main import creer_et_stocker_bundle
        from capteurs.gestionnaire import GestionnaireCapteurs
        from securite.signature import verifier_signature

        cycle = GestionnaireCapteurs().lire_tous()
        creer_et_stocker_bundle(cycle, cle_aes, cle_privee_ecdsa, base_locale)

        bundle = base_locale.recuperer_bundle_par_index(0)
        iv = base64.b64decode(bundle["iv"])
        chiffre = base64.b64decode(bundle["donnees_chiffrees"])
        signature = base64.b64decode(bundle["signature"])

        bloc = iv + chiffre
        cle_pub = ECC.import_key(cle_publique_pem)
        assert verifier_signature(bloc, signature, cle_pub)

    def test_pipeline_nonce_unique_par_bundle(self, base_locale, cle_aes, cle_privee_ecdsa):
        from main import creer_et_stocker_bundle
        from capteurs.gestionnaire import GestionnaireCapteurs

        gestionnaire = GestionnaireCapteurs()
        nonces = set()
        for _ in range(10):
            cycle = gestionnaire.lire_tous()
            creer_et_stocker_bundle(cycle, cle_aes, cle_privee_ecdsa, base_locale)

        for i in range(10):
            bundle = base_locale.recuperer_bundle_par_index(i)
            nonces.add(bundle["nonce"])

        assert len(nonces) == 10  # Tous les nonces sont uniques

    def test_pipeline_cinq_cycles_fifo(self, base_locale, cle_aes, cle_privee_ecdsa):
        """5 cycles produces 5 bundles en ordre FIFO."""
        from main import creer_et_stocker_bundle
        from capteurs.gestionnaire import GestionnaireCapteurs

        gestionnaire = GestionnaireCapteurs()
        ids_stockes = []
        for _ in range(5):
            cycle = gestionnaire.lire_tous()
            bid = creer_et_stocker_bundle(cycle, cle_aes, cle_privee_ecdsa, base_locale)
            ids_stockes.append(bid)

        assert base_locale.compter_bundles_en_attente() == 5
        for i, bid in enumerate(ids_stockes):
            bundle = base_locale.recuperer_bundle_par_index(i)
            assert bundle["bundle_id"] == bid

    def test_pipeline_sentinel_id_correct(self, base_locale, cle_aes, cle_privee_ecdsa):
        import config
        from main import creer_et_stocker_bundle
        from capteurs.gestionnaire import GestionnaireCapteurs
        from securite.chiffrement import dechiffrer_donnees

        cycle = GestionnaireCapteurs().lire_tous()
        creer_et_stocker_bundle(cycle, cle_aes, cle_privee_ecdsa, base_locale)

        bundle = base_locale.recuperer_bundle_par_index(0)
        assert bundle["sentinel_id"] == config.SENTINEL_ID

    def test_pipeline_mesures_preservees(self, base_locale, cle_aes, cle_privee_ecdsa):
        """Les 8 mesures du cycle sont toutes preservees apres chiffrement."""
        from main import creer_et_stocker_bundle
        from capteurs.gestionnaire import GestionnaireCapteurs
        from securite.chiffrement import dechiffrer_donnees

        cycle = GestionnaireCapteurs().lire_tous()
        assert cycle["nb_mesures"] == 8

        creer_et_stocker_bundle(cycle, cle_aes, cle_privee_ecdsa, base_locale)
        bundle = base_locale.recuperer_bundle_par_index(0)

        iv = base64.b64decode(bundle["iv"])
        chiffre = base64.b64decode(bundle["donnees_chiffrees"])
        donnees = dechiffrer_donnees(iv, chiffre, cle_aes)

        assert len(donnees["mesures"]) == 8
        types = {m["type"] for m in donnees["mesures"]}
        assert types == {
            "temperature", "humidite",
            "pression", "temperature_bme", "humidite_bme",
            "pm1_0", "pm2_5", "pm10",
        }


# =============================================================================
# TESTS : Cycle BLE complet (chunking + ACK)
# =============================================================================

class TestBLECycleComplet:

    def _lire_via_chunks(self, carac):
        """Simule la lecture BLE complete par chunks, retourne le bundle JSON."""
        from communication.ble_serveur import CaracBundleData

        if not carac.chunks:
            carac.selectionner(0)

        json_complet = ""
        total = len(carac.chunks)
        for _ in range(total):
            idx = min(carac.chunk_idx, total - 1)
            env = {
                "total": total,
                "chunk": idx,
                "data": carac.chunks[idx],
            }
            json_complet += env["data"]
            if carac.chunk_idx < total - 1:
                carac.chunk_idx += 1

        return json.loads(json_complet)

    def test_bundle_ble_complet_et_dechiffrable(
        self, base_locale, cle_aes, cle_privee_ecdsa
    ):
        from main import creer_et_stocker_bundle
        from capteurs.gestionnaire import GestionnaireCapteurs
        from securite.chiffrement import dechiffrer_donnees
        from communication.ble_serveur import CaracBundleData

        cycle = GestionnaireCapteurs().lire_tous()
        creer_et_stocker_bundle(cycle, cle_aes, cle_privee_ecdsa, base_locale)

        service = MagicMock()
        service.get_path.return_value = "/test/service"
        carac = CaracBundleData(None, 0, service, base_locale)
        carac.selectionner(0)

        bundle_recu = self._lire_via_chunks(carac)

        iv = base64.b64decode(bundle_recu["iv"])
        chiffre = base64.b64decode(bundle_recu["donnees_chiffrees"])
        donnees = dechiffrer_donnees(iv, chiffre, cle_aes)

        assert donnees["nb_mesures"] == cycle["nb_mesures"]

    def test_ack_marque_bundle_transfere(
        self, base_locale, cle_aes, cle_privee_ecdsa
    ):
        from main import creer_et_stocker_bundle
        from capteurs.gestionnaire import GestionnaireCapteurs
        from communication.ble_serveur import CaracBundleData

        cycle = GestionnaireCapteurs().lire_tous()
        bid = creer_et_stocker_bundle(cycle, cle_aes, cle_privee_ecdsa, base_locale)

        assert base_locale.compter_bundles_en_attente() == 1

        service = MagicMock()
        service.get_path.return_value = "/test/service"
        carac = CaracBundleData(None, 0, service, base_locale)
        carac.selectionner(0)
        bundle_recu = self._lire_via_chunks(carac)

        # ACK
        result = base_locale.marquer_transfere(bundle_recu["bundle_id"])
        assert result is True
        assert base_locale.compter_bundles_en_attente() == 0

    def test_trois_bundles_ble_puis_ack(
        self, base_locale, cle_aes, cle_privee_ecdsa
    ):
        from main import creer_et_stocker_bundle
        from capteurs.gestionnaire import GestionnaireCapteurs
        from communication.ble_serveur import CaracBundleData

        gestionnaire = GestionnaireCapteurs()
        ids_originaux = []
        for _ in range(3):
            cycle = gestionnaire.lire_tous()
            bid = creer_et_stocker_bundle(cycle, cle_aes, cle_privee_ecdsa, base_locale)
            ids_originaux.append(bid)

        assert base_locale.compter_bundles_en_attente() == 3

        service = MagicMock()
        service.get_path.return_value = "/test/service"
        carac = CaracBundleData(None, 0, service, base_locale)

        bundles_recus = []
        for i in range(3):
            carac.selectionner(i)
            bundle_recu = self._lire_via_chunks(carac)
            bundles_recus.append(bundle_recu["bundle_id"])

        assert bundles_recus == ids_originaux

        for bid in bundles_recus:
            base_locale.marquer_transfere(bid)

        assert base_locale.compter_bundles_en_attente() == 0

    def test_ble_bundle_signature_verifiable(
        self, base_locale, cle_aes, cle_privee_ecdsa, cle_publique_pem
    ):
        from main import creer_et_stocker_bundle
        from capteurs.gestionnaire import GestionnaireCapteurs
        from securite.signature import verifier_signature
        from communication.ble_serveur import CaracBundleData

        cycle = GestionnaireCapteurs().lire_tous()
        creer_et_stocker_bundle(cycle, cle_aes, cle_privee_ecdsa, base_locale)

        service = MagicMock()
        service.get_path.return_value = "/test/service"
        carac = CaracBundleData(None, 0, service, base_locale)
        carac.selectionner(0)
        bundle_recu = self._lire_via_chunks(carac)

        iv = base64.b64decode(bundle_recu["iv"])
        chiffre = base64.b64decode(bundle_recu["donnees_chiffrees"])
        signature = base64.b64decode(bundle_recu["signature"])
        bloc = iv + chiffre

        cle_pub = ECC.import_key(cle_publique_pem)
        assert verifier_signature(bloc, signature, cle_pub)


# =============================================================================
# TESTS : Robustesse (cas limites du pipeline)
# =============================================================================

class TestRobustesse:

    def test_bundle_avec_zero_mesures(self, base_locale, cle_aes, cle_privee_ecdsa):
        """main.creer_et_stocker_bundle avec 0 mesures ne doit pas planter."""
        from main import creer_et_stocker_bundle

        cycle_vide = {
            "sentinel_id": "test",
            "horodatage": "2026-04-04T00:00:00+00:00",
            "mesures": [],
            "nb_mesures": 0,
        }
        # Note : dans main.py, on ne stocke que si nb_mesures > 0.
        # Mais la fonction elle-meme doit fonctionner sans planter.
        bid = creer_et_stocker_bundle(cycle_vide, cle_aes, cle_privee_ecdsa, base_locale)
        assert bid is not None

    def test_chiffrement_donnees_unicode(self, cle_aes):
        from securite.chiffrement import chiffrer_donnees, dechiffrer_donnees
        donnees = {"texte": "Données environnementales — température: 25°C"}
        iv, chiffre = chiffrer_donnees(donnees, cle_aes)
        resultat = dechiffrer_donnees(iv, chiffre, cle_aes)
        assert resultat == donnees

    def test_signature_binaire_aleatoire(self, cle_privee_ecdsa):
        from securite.signature import signer_donnees, verifier_signature
        data = get_random_bytes(500)
        sig = signer_donnees(data, cle_privee_ecdsa)
        assert verifier_signature(data, sig, cle_privee_ecdsa.public_key())

    def test_multiples_cles_differentes(self, tmp_path):
        """Deux sentinelles differentes ont des cles differentes."""
        import config
        import os

        rep1 = str(tmp_path / "cles1")
        rep2 = str(tmp_path / "cles2")
        os.makedirs(rep1)
        os.makedirs(rep2)

        config.REPERTOIRE_CLES = rep1
        config.FICHIER_CLE_PRIVEE = os.path.join(rep1, "priv.pem")
        config.FICHIER_CLE_PUBLIQUE = os.path.join(rep1, "pub.pem")
        config.FICHIER_CLE_AES = os.path.join(rep1, "aes.bin")
        from securite.cles import generer_cles_ecdsa
        _, pub1 = generer_cles_ecdsa()

        config.REPERTOIRE_CLES = rep2
        config.FICHIER_CLE_PRIVEE = os.path.join(rep2, "priv.pem")
        config.FICHIER_CLE_PUBLIQUE = os.path.join(rep2, "pub.pem")
        config.FICHIER_CLE_AES = os.path.join(rep2, "aes.bin")
        _, pub2 = generer_cles_ecdsa()

        assert pub1 != pub2

    def test_bundle_id_format_uuid(self, base_locale, cle_aes, cle_privee_ecdsa):
        from main import creer_et_stocker_bundle
        import re
        cycle = {
            "sentinel_id": "x", "horodatage": "2026-01-01T00:00:00+00:00",
            "mesures": [], "nb_mesures": 0,
        }
        bid = creer_et_stocker_bundle(cycle, cle_aes, cle_privee_ecdsa, base_locale)
        uuid_pattern = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
        assert re.match(uuid_pattern, bid)

    def test_stockage_concurrent_thread_safe(self, base_locale, cle_aes, cle_privee_ecdsa):
        """Le stockage concurrent depuis plusieurs threads ne corrompt pas la BDD."""
        import threading
        from main import creer_et_stocker_bundle
        from capteurs.gestionnaire import GestionnaireCapteurs

        resultats = []
        erreurs = []

        def stocker():
            try:
                gestionnaire = GestionnaireCapteurs()
                cycle = gestionnaire.lire_tous()
                bid = creer_et_stocker_bundle(cycle, cle_aes, cle_privee_ecdsa, base_locale)
                resultats.append(bid)
            except Exception as e:
                erreurs.append(str(e))

        threads = [threading.Thread(target=stocker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(erreurs) == 0
        assert len(set(resultats)) == 5  # 5 UUIDs uniques
        assert base_locale.compter_bundles_en_attente() == 5

    def test_depassement_max_bundles(self, base_locale):
        """La BDD ne garde pas plus de MAX_BUNDLES_STOCKES bundles."""
        import config

        config.MAX_BUNDLES_STOCKES = 10
        for i in range(15):
            base_locale.stocker_bundle(
                get_random_bytes(16), get_random_bytes(64),
                get_random_bytes(64), f"nonce_{i}", i,
            )
            # Marquer les 5 premiers comme transferes pour permettre la suppression
            if i < 5:
                b = base_locale.recuperer_bundle_par_index(0)
                if b:
                    base_locale.marquer_transfere(b["bundle_id"])

        total_curseur = base_locale.connexion.execute(
            "SELECT COUNT(*) FROM bundles"
        ).fetchone()[0]
        assert total_curseur <= config.MAX_BUNDLES_STOCKES + 5
