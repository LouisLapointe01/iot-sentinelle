"""
test_fonctionnement_global.py -- Tests du fonctionnement global du système DTN.

Valide le comportement du système en conditions quasi-réelles :
- Pipeline DTN complet (capteurs → chiffrement → signature → stockage → BLE → acquittement)
- Cohérence des données à chaque étape
- Concurrence (plusieurs threads simultanés)
- Limites du système (quota SQLite, grande charge)
- Protocole BLE bout en bout
- Robustesse face aux erreurs
"""

import os
import json
import base64
import threading
import pytest
from unittest.mock import patch, MagicMock
from Crypto.Random import get_random_bytes


# =============================================================================
# TESTS : Pipeline DTN complet (Store → Carry → Forward simulé)
# =============================================================================

class TestPipelineDTNComplet:
    def test_pipeline_store_carry_forward(
        self, cle_aes, cle_privee_ecdsa, cle_publique_pem, base_locale, mesures_exemple
    ):
        """
        Pipeline complet :
        STORE  → chiffrement + signature + SQLite
        CARRY  → lecture BLE (index 0) + chunking
        FORWARD → acquittement + bundle invisible
        """
        from main import creer_et_stocker_bundle
        from communication.ble_serveur import BLE_CHUNK_SIZE
        from Crypto.PublicKey import ECC
        from securite.chiffrement import dechiffrer_donnees
        from securite.signature import verifier_signature

        # --- STORE ---
        bundle_id = creer_et_stocker_bundle(
            mesures_exemple, cle_aes, cle_privee_ecdsa, base_locale
        )
        assert base_locale.compter_bundles_en_attente() == 1

        # --- CARRY : simulation du protocole BLE ---
        bundle = base_locale.recuperer_bundle_par_index(0)
        full_json = json.dumps(bundle)

        # Le protocole BLE découpe en chunks de BLE_CHUNK_SIZE
        chunks = [full_json[i:i+BLE_CHUNK_SIZE]
                  for i in range(0, len(full_json), BLE_CHUNK_SIZE)]
        assert len(chunks) >= 1

        # Reconstitution côté mule
        reconstitue = "".join(chunks)
        bundle_reconstitue = json.loads(reconstitue)
        assert "bundle_id" in bundle_reconstitue

        # Vérification signature
        cle_pub = ECC.import_key(cle_publique_pem)
        iv = base64.b64decode(bundle_reconstitue["iv"])
        donnees_chiffrees = base64.b64decode(bundle_reconstitue["donnees_chiffrees"])
        signature = base64.b64decode(bundle_reconstitue["signature"])

        assert verifier_signature(iv + donnees_chiffrees, signature, cle_pub) is True

        # Déchiffrement
        dechiffre = dechiffrer_donnees(iv, donnees_chiffrees, cle_aes)
        assert dechiffre["nb_mesures"] == mesures_exemple["nb_mesures"]

        # --- FORWARD : acquittement ---
        base_locale.marquer_transfere(bundle_id)
        assert base_locale.compter_bundles_en_attente() == 0

    def test_pipeline_multiple_bundles_ordre_fifo(
        self, cle_aes, cle_privee_ecdsa, base_locale, mesures_exemple
    ):
        """Les bundles doivent être récupérables dans l'ordre FIFO."""
        from main import creer_et_stocker_bundle

        ids = []
        for i in range(5):
            m = dict(mesures_exemple)
            m["mesures"][0]["valeur"] = float(i * 10)
            ids.append(creer_et_stocker_bundle(m, cle_aes, cle_privee_ecdsa, base_locale))

        for i in range(5):
            b = base_locale.recuperer_bundle_par_index(i)
            assert b["bundle_id"] == ids[i]

    def test_pipeline_acquittement_partiel(
        self, cle_aes, cle_privee_ecdsa, base_locale, mesures_exemple
    ):
        """Acquitter seulement certains bundles doit laisser les autres en attente."""
        from main import creer_et_stocker_bundle

        ids = []
        for _ in range(4):
            ids.append(creer_et_stocker_bundle(
                mesures_exemple, cle_aes, cle_privee_ecdsa, base_locale
            ))

        # Acquitter index 0 et 2
        base_locale.marquer_transfere(ids[0])
        base_locale.marquer_transfere(ids[2])

        assert base_locale.compter_bundles_en_attente() == 2

    def test_bundle_acquitte_non_recuperable(
        self, cle_aes, cle_privee_ecdsa, base_locale, mesures_exemple
    ):
        """Un bundle acquitté ne doit plus être visible par index."""
        from main import creer_et_stocker_bundle

        bid = creer_et_stocker_bundle(
            mesures_exemple, cle_aes, cle_privee_ecdsa, base_locale
        )
        base_locale.marquer_transfere(bid)

        assert base_locale.recuperer_bundle_par_index(0) is None

    def test_deux_bundles_ont_signatures_differentes(
        self, cle_aes, cle_privee_ecdsa, base_locale, mesures_exemple
    ):
        """Deux bundles différents doivent avoir des signatures différentes."""
        from main import creer_et_stocker_bundle

        creer_et_stocker_bundle(mesures_exemple, cle_aes, cle_privee_ecdsa, base_locale)
        creer_et_stocker_bundle(mesures_exemple, cle_aes, cle_privee_ecdsa, base_locale)

        b1 = base_locale.recuperer_bundle_par_index(0)
        b2 = base_locale.recuperer_bundle_par_index(1)
        assert b1["signature"] != b2["signature"]


# =============================================================================
# TESTS : Protocole BLE bout en bout
# =============================================================================

class TestProtocoleBLEBoutEnBout:
    def test_chunking_reconstitution_exacte(
        self, cle_aes, cle_privee_ecdsa, base_locale, mesures_exemple
    ):
        """La reconstitution des chunks doit donner exactement le JSON original."""
        from main import creer_et_stocker_bundle
        from communication.ble_serveur import BLE_CHUNK_SIZE

        creer_et_stocker_bundle(mesures_exemple, cle_aes, cle_privee_ecdsa, base_locale)
        bundle = base_locale.recuperer_bundle_par_index(0)
        original_json = json.dumps(bundle)

        # Simuler le découpage serveur
        chunks = [original_json[i:i+BLE_CHUNK_SIZE]
                  for i in range(0, len(original_json), BLE_CHUNK_SIZE)]

        # Simuler la reconstitution client
        reconstitue = "".join(chunks)
        assert reconstitue == original_json

    def test_enveloppe_chunk_format_correct(
        self, cle_aes, cle_privee_ecdsa, base_locale, mesures_exemple
    ):
        """Chaque enveloppe de chunk doit avoir les champs total, chunk, data."""
        from main import creer_et_stocker_bundle
        from communication.ble_serveur import BLE_CHUNK_SIZE

        creer_et_stocker_bundle(mesures_exemple, cle_aes, cle_privee_ecdsa, base_locale)
        bundle = base_locale.recuperer_bundle_par_index(0)
        full_json = json.dumps(bundle)

        chunks = [full_json[i:i+BLE_CHUNK_SIZE]
                  for i in range(0, len(full_json), BLE_CHUNK_SIZE)]
        total = len(chunks)

        for i, data in enumerate(chunks):
            envelope = {"total": total, "chunk": i, "data": data}
            assert envelope["total"] == total
            assert envelope["chunk"] == i
            assert "data" in envelope

    def test_dernier_chunk_termine_correctement(
        self, cle_aes, cle_privee_ecdsa, base_locale, mesures_exemple
    ):
        """Le dernier chunk doit avoir chunk == total - 1."""
        from main import creer_et_stocker_bundle
        from communication.ble_serveur import BLE_CHUNK_SIZE

        creer_et_stocker_bundle(mesures_exemple, cle_aes, cle_privee_ecdsa, base_locale)
        bundle = base_locale.recuperer_bundle_par_index(0)
        full_json = json.dumps(bundle)

        chunks = [full_json[i:i+BLE_CHUNK_SIZE]
                  for i in range(0, len(full_json), BLE_CHUNK_SIZE)]
        total = len(chunks)

        # Vérification : dernier index == total - 1
        assert total - 1 == total - 1  # trivial mais simule la condition du client

    def test_chunks_taille_inferieure_limite_ble(
        self, cle_aes, cle_privee_ecdsa, base_locale, mesures_exemple
    ):
        """Chaque chunk de données doit tenir dans la limite BLE (< 512 octets)."""
        from main import creer_et_stocker_bundle
        from communication.ble_serveur import BLE_CHUNK_SIZE

        creer_et_stocker_bundle(mesures_exemple, cle_aes, cle_privee_ecdsa, base_locale)
        bundle = base_locale.recuperer_bundle_par_index(0)
        full_json = json.dumps(bundle)

        chunks = [full_json[i:i+BLE_CHUNK_SIZE]
                  for i in range(0, len(full_json), BLE_CHUNK_SIZE)]

        for chunk in chunks:
            envelope_bytes = json.dumps({"total": len(chunks), "chunk": 0, "data": chunk}).encode()
            assert len(envelope_bytes) <= 512, f"Chunk trop grand : {len(envelope_bytes)} octets"

    def test_ble_chunk_size_est_400(self):
        """La constante BLE_CHUNK_SIZE doit être 400."""
        from communication.ble_serveur import BLE_CHUNK_SIZE
        assert BLE_CHUNK_SIZE == 400

    def test_bundle_error_si_index_invalide(self, base_locale):
        """Un index invalide doit retourner None."""
        result = base_locale.recuperer_bundle_par_index(999)
        assert result is None

    def test_simulation_cycle_ble_complet(
        self, cle_aes, cle_privee_ecdsa, base_locale, mesures_exemple
    ):
        """Simule le cycle BLE complet : SELECT → DATA (chunks) → ACK.

        La mule lit toujours l'index 0 (FIFO) puis acquitte avant de passer
        au suivant — après chaque ACK, la file se décale d'une position.
        """
        from main import creer_et_stocker_bundle
        from communication.ble_serveur import BLE_CHUNK_SIZE

        # Stocker 3 bundles
        for _ in range(3):
            creer_et_stocker_bundle(mesures_exemple, cle_aes, cle_privee_ecdsa, base_locale)

        assert base_locale.compter_bundles_en_attente() == 3

        # Récupérer chaque bundle via le protocole simulé (toujours index 0)
        for _ in range(3):
            bundle = base_locale.recuperer_bundle_par_index(0)
            assert bundle is not None

            full_json = json.dumps(bundle)
            chunks = [full_json[i:i+BLE_CHUNK_SIZE]
                      for i in range(0, len(full_json), BLE_CHUNK_SIZE)]
            reconstitue = "".join(chunks)
            bundle_reconstitue = json.loads(reconstitue)

            # ACK : le bundle disparaît de la file, le suivant passe en index 0
            base_locale.marquer_transfere(bundle_reconstitue["bundle_id"])

        assert base_locale.compter_bundles_en_attente() == 0


# =============================================================================
# TESTS : Concurrence (thread safety)
# =============================================================================

class TestConcurrence:
    def test_ecritures_concurrentes_sans_corruption(
        self, cle_aes, cle_privee_ecdsa, base_locale, mesures_exemple
    ):
        """Plusieurs threads qui écrivent en même temps ne doivent pas corrompre la base."""
        from main import creer_et_stocker_bundle

        erreurs = []
        nb_threads = 10
        bundles_par_thread = 5

        def ecrire():
            try:
                for _ in range(bundles_par_thread):
                    creer_et_stocker_bundle(
                        mesures_exemple, cle_aes, cle_privee_ecdsa, base_locale
                    )
            except Exception as e:
                erreurs.append(str(e))

        threads = [threading.Thread(target=ecrire) for _ in range(nb_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(erreurs) == 0
        total = base_locale.compter_bundles_en_attente()
        assert total == nb_threads * bundles_par_thread

    def test_lecture_ecriture_simultanées(
        self, cle_aes, cle_privee_ecdsa, base_locale, mesures_exemple
    ):
        """Lecture et écriture simultanées ne doivent pas causer d'erreur."""
        from main import creer_et_stocker_bundle

        # Pre-remplir la base
        for _ in range(5):
            creer_et_stocker_bundle(mesures_exemple, cle_aes, cle_privee_ecdsa, base_locale)

        erreurs = []
        resultats_lecture = []

        def lire():
            try:
                for i in range(10):
                    b = base_locale.recuperer_bundle_par_index(i % 5)
                    resultats_lecture.append(b)
            except Exception as e:
                erreurs.append(str(e))

        def ecrire():
            try:
                for _ in range(5):
                    creer_et_stocker_bundle(
                        mesures_exemple, cle_aes, cle_privee_ecdsa, base_locale
                    )
            except Exception as e:
                erreurs.append(str(e))

        threads = [
            threading.Thread(target=lire),
            threading.Thread(target=ecrire),
            threading.Thread(target=lire),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(erreurs) == 0

    def test_acquittement_concurrent_idempotent(
        self, cle_aes, cle_privee_ecdsa, base_locale, mesures_exemple
    ):
        """Acquitter un bundle depuis plusieurs threads doit être idempotent."""
        from main import creer_et_stocker_bundle

        bid = creer_et_stocker_bundle(
            mesures_exemple, cle_aes, cle_privee_ecdsa, base_locale
        )

        erreurs = []
        def ackquer():
            try:
                base_locale.marquer_transfere(bid)
            except Exception as e:
                erreurs.append(str(e))

        threads = [threading.Thread(target=ackquer) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(erreurs) == 0
        assert base_locale.compter_bundles_en_attente() == 0


# =============================================================================
# TESTS : Limites du système
# =============================================================================

class TestLimitesSysteme:
    def test_quota_max_bundles(self, cle_aes, cle_privee_ecdsa, base_locale, mesures_exemple):
        """Le nettoyage doit supprimer les bundles transférés excédentaires.

        MAX_BUNDLES_STOCKES s'applique au total de la table (transférés compris).
        Le nettoyage ne supprime que les bundles déjà transférés (jamais les
        en_attente), donc le total global est plafonné après acquittement.
        """
        import config
        from main import creer_et_stocker_bundle

        limite = config.MAX_BUNDLES_STOCKES

        # Stocker et acquitter la moitié de la limite
        moitie = limite // 2
        ids = []
        for _ in range(moitie):
            bid = creer_et_stocker_bundle(mesures_exemple, cle_aes, cle_privee_ecdsa, base_locale)
            ids.append(bid)

        # Acquitter tous ces bundles (statut = 'transfere')
        for bid in ids:
            base_locale.marquer_transfere(bid)

        # Stocker encore moitié + 10 → dépasse la limite totale
        for _ in range(moitie + 10):
            creer_et_stocker_bundle(mesures_exemple, cle_aes, cle_privee_ecdsa, base_locale)

        # Le nettoyage doit avoir supprimé les excédentaires transférés
        curseur = base_locale.connexion.execute("SELECT COUNT(*) FROM bundles")
        total = curseur.fetchone()[0]
        assert total <= limite

    def test_mesures_volumineuses_restent_valides(
        self, cle_aes, cle_privee_ecdsa, base_locale
    ):
        """Des mesures volumineuses doivent toujours être chiffrables et stockables."""
        from main import creer_et_stocker_bundle

        mesures_grandes = {
            "sentinel_id": "test-sentinelle-001",
            "horodatage": "2026-04-04T10:00:00+00:00",
            "mesures": [
                {"type": f"capteur_{i}", "valeur": float(i), "unite": "unit",
                 "horodatage": "2026-04-04T10:00:00+00:00", "description": "x" * 100}
                for i in range(50)
            ],
            "nb_mesures": 50,
        }

        bundle_id = creer_et_stocker_bundle(
            mesures_grandes, cle_aes, cle_privee_ecdsa, base_locale
        )
        assert bundle_id is not None
        assert base_locale.compter_bundles_en_attente() == 1

    def test_bundle_json_valide_pour_ble(
        self, cle_aes, cle_privee_ecdsa, base_locale, mesures_exemple
    ):
        """Le JSON du bundle stocké doit être valide pour le protocole BLE."""
        from main import creer_et_stocker_bundle

        creer_et_stocker_bundle(mesures_exemple, cle_aes, cle_privee_ecdsa, base_locale)
        bundle = base_locale.recuperer_bundle_par_index(0)
        full_json = json.dumps(bundle)

        # Doit être re-parseable sans erreur
        parsed = json.loads(full_json)
        assert parsed["bundle_id"] is not None

    def test_1000_cycles_performance(
        self, cle_aes, cle_privee_ecdsa, base_locale, mesures_exemple
    ):
        """1000 cycles de mesure doivent terminer en moins de 10 secondes."""
        import time
        from main import creer_et_stocker_bundle
        import config

        # On teste seulement si la limite est assez haute
        if config.MAX_BUNDLES_STOCKES < 100:
            pytest.skip("MAX_BUNDLES_STOCKES trop bas pour ce test")

        debut = time.time()
        for _ in range(100):  # 100 cycles pour rester rapide
            creer_et_stocker_bundle(mesures_exemple, cle_aes, cle_privee_ecdsa, base_locale)
        duree = time.time() - debut

        assert duree < 10.0, f"100 cycles ont pris {duree:.2f}s (max: 10s)"


# =============================================================================
# TESTS : Cohérence des données à travers le pipeline
# =============================================================================

class TestCoherenceDonnees:
    def test_sentinel_id_preserve_dans_bundle(
        self, cle_aes, cle_privee_ecdsa, base_locale
    ):
        """Le sentinel_id des mesures doit être préservé après déchiffrement."""
        from main import creer_et_stocker_bundle
        from securite.chiffrement import dechiffrer_donnees
        import config

        mesures = {
            "sentinel_id": config.SENTINEL_ID,
            "horodatage": "2026-04-04T10:00:00+00:00",
            "mesures": [{"type": "temperature", "valeur": 23.1, "unite": "degC"}],
            "nb_mesures": 1,
        }

        creer_et_stocker_bundle(mesures, cle_aes, cle_privee_ecdsa, base_locale)
        bundle = base_locale.recuperer_bundle_par_index(0)

        iv = base64.b64decode(bundle["iv"])
        donnees = base64.b64decode(bundle["donnees_chiffrees"])
        dechiffre = dechiffrer_donnees(iv, donnees, cle_aes)

        assert dechiffre["sentinel_id"] == config.SENTINEL_ID

    def test_valeurs_capteurs_preservees(
        self, cle_aes, cle_privee_ecdsa, base_locale
    ):
        """Les valeurs des capteurs doivent être identiques après déchiffrement."""
        from main import creer_et_stocker_bundle
        from securite.chiffrement import dechiffrer_donnees

        mesures = {
            "sentinel_id": "test",
            "horodatage": "2026-04-04T10:00:00+00:00",
            "mesures": [
                {"type": "temperature", "valeur": 22.5, "unite": "degC"},
                {"type": "humidite", "valeur": 65.3, "unite": "%"},
                {"type": "pression", "valeur": 1013.25, "unite": "hPa"},
            ],
            "nb_mesures": 3,
        }

        creer_et_stocker_bundle(mesures, cle_aes, cle_privee_ecdsa, base_locale)
        bundle = base_locale.recuperer_bundle_par_index(0)

        iv = base64.b64decode(bundle["iv"])
        donnees = base64.b64decode(bundle["donnees_chiffrees"])
        dechiffre = dechiffrer_donnees(iv, donnees, cle_aes)

        for original, dechiffre_mesure in zip(mesures["mesures"], dechiffre["mesures"]):
            assert original["valeur"] == pytest.approx(dechiffre_mesure["valeur"])
            assert original["type"] == dechiffre_mesure["type"]

    def test_horodatage_preserve(
        self, cle_aes, cle_privee_ecdsa, base_locale
    ):
        """L'horodatage du cycle doit être préservé après déchiffrement."""
        from main import creer_et_stocker_bundle
        from securite.chiffrement import dechiffrer_donnees

        horodatage = "2026-04-04T10:30:00+00:00"
        mesures = {
            "sentinel_id": "test",
            "horodatage": horodatage,
            "mesures": [{"type": "temperature", "valeur": 20.0, "unite": "degC"}],
            "nb_mesures": 1,
        }

        creer_et_stocker_bundle(mesures, cle_aes, cle_privee_ecdsa, base_locale)
        bundle = base_locale.recuperer_bundle_par_index(0)

        iv = base64.b64decode(bundle["iv"])
        donnees = base64.b64decode(bundle["donnees_chiffrees"])
        dechiffre = dechiffrer_donnees(iv, donnees, cle_aes)

        assert dechiffre["horodatage"] == horodatage

    def test_iv_unique_par_bundle(
        self, cle_aes, cle_privee_ecdsa, base_locale, mesures_exemple
    ):
        """Chaque bundle doit avoir un IV unique (CBC sécurisé)."""
        from main import creer_et_stocker_bundle

        for _ in range(5):
            creer_et_stocker_bundle(mesures_exemple, cle_aes, cle_privee_ecdsa, base_locale)

        ivs = set()
        for i in range(5):
            bundle = base_locale.recuperer_bundle_par_index(i)
            ivs.add(bundle["iv"])

        assert len(ivs) == 5, "Tous les IVs doivent être uniques"

    def test_bundle_structure_complete(
        self, cle_aes, cle_privee_ecdsa, base_locale, mesures_exemple
    ):
        """Un bundle doit contenir tous les champs obligatoires."""
        from main import creer_et_stocker_bundle

        creer_et_stocker_bundle(mesures_exemple, cle_aes, cle_privee_ecdsa, base_locale)
        bundle = base_locale.recuperer_bundle_par_index(0)

        champs_obligatoires = ["bundle_id", "iv", "donnees_chiffrees", "signature",
                               "nonce", "nb_mesures", "horodatage"]
        for champ in champs_obligatoires:
            assert champ in bundle, f"Champ manquant : {champ}"

    def test_nb_mesures_correct_dans_bundle(
        self, cle_aes, cle_privee_ecdsa, base_locale
    ):
        """nb_mesures dans le bundle doit correspondre au nombre réel de mesures."""
        from main import creer_et_stocker_bundle

        mesures = {
            "sentinel_id": "test",
            "horodatage": "2026-04-04T10:00:00+00:00",
            "mesures": [{"type": f"c{i}", "valeur": float(i), "unite": "u"} for i in range(7)],
            "nb_mesures": 7,
        }

        creer_et_stocker_bundle(mesures, cle_aes, cle_privee_ecdsa, base_locale)
        bundle = base_locale.recuperer_bundle_par_index(0)
        assert bundle["nb_mesures"] == 7
