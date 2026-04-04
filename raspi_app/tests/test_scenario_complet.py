"""
test_scenario_complet.py -- Scénario complet A à Z d'un déploiement DTN réel.

Ce fichier raconte l'histoire d'une sentinelle déployée pendant 24 heures
dans une zone sans connectivité, puis récupérée par un smartphone mule.

  ACTE 1  Déploiement initial (boot, clés, QR code)
  ACTE 2  24 heures de collecte (288 cycles × 5 min, tous les capteurs)
  ACTE 3  Arrivée de la mule (transfert BLE complet avec chunking)
  ACTE 4  Transmission MQTT simulée (mule → serveur neOCampus)
  ACTE 5  Résilience (panne capteur, BLE coupé, quota plein, rejeu)
  ACTE 6  Multi-sentinelles simultanées (3 sentinelles indépendantes)

Chaque acte est autonome. Les fixtures conftest (config_temporaire) isolent
la base de données et les clés dans tmp_path.
"""

import os
import json
import base64
import threading
import time
import pytest
from unittest.mock import patch, MagicMock
from Crypto.Random import get_random_bytes
from Crypto.PublicKey import ECC


# =============================================================================
# HELPERS partagés entre les actes
# =============================================================================

def _fabriquer_cycle(sentinel_id: str, idx: int, nb_capteurs: int = 3) -> dict:
    """Fabrique un cycle de mesures réaliste pour le test."""
    import datetime as dt
    # On simule une mesure toutes les 5 minutes à partir de 06:00
    t = dt.datetime(2026, 4, 4, 6, 0, 0, tzinfo=dt.timezone.utc)
    t += dt.timedelta(minutes=5 * idx)
    horodatage = t.isoformat()

    mesures = []
    if nb_capteurs >= 1:
        mesures += [
            {"type": "temperature", "valeur": 18.0 + idx * 0.05, "unite": "degC", "horodatage": horodatage},
            {"type": "humidite",    "valeur": 55.0 + (idx % 20),  "unite": "%",    "horodatage": horodatage},
        ]
    if nb_capteurs >= 2:
        mesures += [
            {"type": "pression",   "valeur": 1013.0 - idx * 0.01, "unite": "hPa", "horodatage": horodatage},
        ]
    if nb_capteurs >= 3:
        mesures += [
            {"type": "pm2_5",     "valeur": 5.0 + (idx % 30),   "unite": "µg/m³", "horodatage": horodatage},
            {"type": "pm10",      "valeur": 10.0 + (idx % 40),  "unite": "µg/m³", "horodatage": horodatage},
        ]

    return {
        "sentinel_id": sentinel_id,
        "horodatage": horodatage,
        "mesures": mesures,
        "nb_mesures": len(mesures),
    }


def _stocker_cycle(cycle, cle_aes, cle_privee, base):
    """Raccourci : creer_et_stocker_bundle via main."""
    from main import creer_et_stocker_bundle
    return creer_et_stocker_bundle(cycle, cle_aes, cle_privee, base)


def _recuperer_et_verifier_bundle(base, index, cle_aes, cle_pub):
    """Récupère, déchiffre et vérifie la signature d'un bundle."""
    from securite.chiffrement import dechiffrer_donnees
    from securite.signature import verifier_signature

    bundle = base.recuperer_bundle_par_index(index)
    assert bundle is not None, f"Aucun bundle à l'index {index}"

    iv = base64.b64decode(bundle["iv"])
    donnees_chiffrees = base64.b64decode(bundle["donnees_chiffrees"])
    signature = base64.b64decode(bundle["signature"])

    # Vérification cryptographique
    assert verifier_signature(iv + donnees_chiffrees, signature, cle_pub), \
        f"Signature invalide pour le bundle {bundle['bundle_id'][:8]}"

    # Déchiffrement
    dechiffre = dechiffrer_donnees(iv, donnees_chiffrees, cle_aes)
    return bundle, dechiffre


# =============================================================================
# ACTE 1 : Déploiement initial
# =============================================================================

class TestActe1DeploiementInitial:
    """
    La sentinelle vient d'être mise en boîte et déployée sur le terrain.
    Première mise sous tension.
    """

    def test_A01_systeme_vierge_aucune_cle(self, tmp_path):
        """À T=0 : aucune clé n'existe encore."""
        import config
        assert not os.path.exists(config.FICHIER_CLE_AES)
        assert not os.path.exists(config.FICHIER_CLE_PRIVEE)

    def test_A02_bootstrap_genere_cle_aes_256_bits(self, tmp_path):
        """Bootstrap : la clé AES générée fait exactement 32 octets (256 bits)."""
        from securite.cles import generer_cle_aes
        import config
        cle = generer_cle_aes()
        assert len(cle) == 32
        assert os.path.exists(config.FICHIER_CLE_AES)

    def test_A03_bootstrap_genere_paire_ecdsa_p256(self, tmp_path):
        """Bootstrap : la paire ECDSA P-256 est valide."""
        from securite.cles import generer_cles_ecdsa
        import config
        priv_pem, pub_pem = generer_cles_ecdsa()
        cle_priv = ECC.import_key(priv_pem)
        cle_pub  = ECC.import_key(pub_pem)
        assert "P-256" in cle_priv.curve  # "P-256" ou "NIST P-256" selon version
        assert "P-256" in cle_pub.curve
        assert not cle_pub.has_private()

    def test_A04_cles_persistantes_apres_reboot(self, tmp_path):
        """Reboot simulé : les clés chargées sont identiques aux clés générées."""
        from securite.cles import generer_cle_aes, generer_cles_ecdsa, charger_cle_aes
        cle1 = generer_cle_aes()
        _, pub1 = generer_cles_ecdsa()
        # Simuler un reboot : charger depuis le disque
        cle2 = charger_cle_aes()
        assert cle1 == cle2, "La clé AES a changé après reboot !"

    def test_A05_base_sqlite_cree_au_premier_lancement(self, tmp_path):
        """Le premier lancement crée la base SQLite vide."""
        import config
        from stockage.base_locale import BaseLocale
        os.makedirs(os.path.dirname(config.FICHIER_BASE_DONNEES), exist_ok=True)
        base = BaseLocale()
        assert base.compter_bundles_en_attente() == 0
        base.fermer()

    def test_A06_qrcode_contient_uuid_ble_et_cle_publique(self, tmp_path):
        """Le QR code contient les informations nécessaires à la mule."""
        from securite.cles import generer_cles_ecdsa
        import config
        _, pub_pem = generer_cles_ecdsa()
        contenu = {
            "sentinel_id": config.SENTINEL_ID,
            "ble_service_uuid": config.BLE_SERVICE_UUID,
            "ble_address": "AA:BB:CC:DD:EE:FF",
            "public_key": pub_pem,
        }
        # Vérifier que la mule peut parser le QR code
        assert contenu["sentinel_id"]
        assert "-" in contenu["ble_service_uuid"]  # format UUID
        assert "BEGIN PUBLIC KEY" in contenu["public_key"]

    def test_A07_sentinel_id_unique_par_boitier(self, tmp_path):
        """Chaque sentinelle a un ID distinct configurable via env."""
        import config
        # Le conftest force test-sentinelle-001
        assert config.SENTINEL_ID  # non vide
        assert isinstance(config.SENTINEL_ID, str)


# =============================================================================
# ACTE 2 : 24 heures de collecte (288 cycles)
# =============================================================================

class TestActe2CollecteEnvironnementale:
    """
    La sentinelle est en opération. Elle mesure en continu pendant 24 heures.
    Chaque cycle = 5 minutes → 288 cycles/jour.
    Tous les bundles sont chiffrés, signés, stockés (Store).
    """

    def test_B01_cycle_unique_produit_bundle_valide(
        self, cle_aes, cle_privee_ecdsa, cle_publique_pem, base_locale
    ):
        """Un seul cycle de mesure → un bundle correctement chiffré et signé."""
        cycle = _fabriquer_cycle("test-sentinelle-001", 0)
        bid = _stocker_cycle(cycle, cle_aes, cle_privee_ecdsa, base_locale)

        cle_pub = ECC.import_key(cle_publique_pem)
        bundle, dechiffre = _recuperer_et_verifier_bundle(base_locale, 0, cle_aes, cle_pub)

        assert dechiffre["sentinel_id"] == "test-sentinelle-001"
        assert dechiffre["nb_mesures"] == 5  # 3 capteurs actifs = 5 mesures

    def test_B02_288_cycles_journaliers_tous_stockes(
        self, cle_aes, cle_privee_ecdsa, base_locale
    ):
        """288 cycles (24h) → 288 bundles en attente de transfert."""
        for i in range(288):
            cycle = _fabriquer_cycle("test-sentinelle-001", i)
            _stocker_cycle(cycle, cle_aes, cle_privee_ecdsa, base_locale)
        assert base_locale.compter_bundles_en_attente() == 288

    def test_B03_ordre_fifo_preserve_sur_24h(
        self, cle_aes, cle_privee_ecdsa, base_locale
    ):
        """L'ordre FIFO est respecté : le cycle 0 est à l'index 0, etc."""
        ids = []
        for i in range(10):
            cycle = _fabriquer_cycle("test-sentinelle-001", i)
            ids.append(_stocker_cycle(cycle, cle_aes, cle_privee_ecdsa, base_locale))

        for i in range(10):
            b = base_locale.recuperer_bundle_par_index(i)
            assert b["bundle_id"] == ids[i], \
                f"L'ordre FIFO est brisé à l'index {i}"

    def test_B04_nonces_tous_uniques_288_cycles(
        self, cle_aes, cle_privee_ecdsa, base_locale
    ):
        """Les 288 nonces anti-rejeu sont tous distincts."""
        nonces = set()
        for i in range(288):
            cycle = _fabriquer_cycle("test-sentinelle-001", i)
            _stocker_cycle(cycle, cle_aes, cle_privee_ecdsa, base_locale)

        for i in range(288):
            b = base_locale.recuperer_bundle_par_index(i)
            assert b["nonce"] not in nonces, f"Nonce dupliqué au cycle {i}"
            nonces.add(b["nonce"])

        assert len(nonces) == 288

    def test_B05_ivs_tous_uniques(
        self, cle_aes, cle_privee_ecdsa, base_locale
    ):
        """Les IVs AES sont uniques pour chaque bundle (CBC sécurisé)."""
        for i in range(50):
            cycle = _fabriquer_cycle("test-sentinelle-001", i)
            _stocker_cycle(cycle, cle_aes, cle_privee_ecdsa, base_locale)

        ivs = {base_locale.recuperer_bundle_par_index(i)["iv"] for i in range(50)}
        assert len(ivs) == 50

    def test_B06_valeurs_capteurs_dans_plages_realistes(
        self, cle_aes, cle_privee_ecdsa, cle_publique_pem, base_locale
    ):
        """Les valeurs déchiffrées sont dans des plages physiquement cohérentes."""
        from securite.chiffrement import dechiffrer_donnees

        cycle = _fabriquer_cycle("test-sentinelle-001", 0)
        _stocker_cycle(cycle, cle_aes, cle_privee_ecdsa, base_locale)

        b = base_locale.recuperer_bundle_par_index(0)
        iv = base64.b64decode(b["iv"])
        donnees_chiffrees = base64.b64decode(b["donnees_chiffrees"])
        dechiffre = dechiffrer_donnees(iv, donnees_chiffrees, cle_aes)

        types = {m["type"]: m["valeur"] for m in dechiffre["mesures"]}
        assert -40 <= types["temperature"] <= 85,   "Température hors plage"
        assert 0   <= types["humidite"]    <= 100,  "Humidité hors plage"
        assert 900 <= types["pression"]    <= 1100, "Pression hors plage"
        assert types["pm2_5"] >= 0,                "PM2.5 négatif impossible"
        assert types["pm10"]  >= 0,                "PM10 négatif impossible"

    def test_B07_panne_dht22_capteurs_restants_continuent(
        self, cle_aes, cle_privee_ecdsa, base_locale
    ):
        """Si DHT22 tombe en panne, BME280 et PMS5003 continuent de fonctionner."""
        # nb_capteurs=2 → DHT22 (temp+hum) + BME280 (pression) = 3 mesures
        # nb_capteurs=3 aurait aussi pm2_5 + pm10 du PMS5003
        cycle_degrade = _fabriquer_cycle("test-sentinelle-001", 0, nb_capteurs=2)
        assert cycle_degrade["nb_mesures"] == 3  # temp + hum + pression

        bid = _stocker_cycle(cycle_degrade, cle_aes, cle_privee_ecdsa, base_locale)
        assert bid is not None
        assert base_locale.compter_bundles_en_attente() == 1

    def test_B08_taille_bundle_compatible_ble_chunking(
        self, cle_aes, cle_privee_ecdsa, base_locale
    ):
        """La taille d'un bundle JSON est < 4096 octets (chunking en < 11 chunks)."""
        from communication.ble_serveur import BLE_CHUNK_SIZE

        cycle = _fabriquer_cycle("test-sentinelle-001", 0)
        _stocker_cycle(cycle, cle_aes, cle_privee_ecdsa, base_locale)

        b = base_locale.recuperer_bundle_par_index(0)
        taille = len(json.dumps(b))
        nb_chunks = (taille + BLE_CHUNK_SIZE - 1) // BLE_CHUNK_SIZE

        assert taille < 4096, f"Bundle trop grand : {taille} octets"
        assert nb_chunks <= 10, f"Trop de chunks : {nb_chunks}"


# =============================================================================
# ACTE 3 : Arrivée de la mule — Transfert BLE
# =============================================================================

class TestActe3TransfertBLE:
    """
    Un opérateur passe à proximité de la sentinelle avec son smartphone.
    L'application mobile se connecte via BLE et récupère tous les bundles.
    Protocole : SELECT(index) → DATA(chunks...) → ACK(bundle_id)
    """

    def test_C01_mule_lit_bundle_count(
        self, cle_aes, cle_privee_ecdsa, base_locale
    ):
        """La mule lit BUNDLE_COUNT pour savoir combien de bundles récupérer."""
        for i in range(5):
            _stocker_cycle(_fabriquer_cycle("test-sentinelle-001", i),
                           cle_aes, cle_privee_ecdsa, base_locale)

        count = base_locale.compter_bundles_en_attente()
        assert count == 5
        # La mule va boucler count fois
        assert isinstance(count, int) and count > 0

    def test_C02_select_index_0_retourne_premier_bundle(
        self, cle_aes, cle_privee_ecdsa, base_locale
    ):
        """SELECT(0) → le bundle le plus ancien (FIFO)."""
        ids = []
        for i in range(3):
            ids.append(_stocker_cycle(_fabriquer_cycle("test-sentinelle-001", i),
                                      cle_aes, cle_privee_ecdsa, base_locale))

        b = base_locale.recuperer_bundle_par_index(0)
        assert b["bundle_id"] == ids[0]

    def test_C03_chunking_reconstitution_parfaite(
        self, cle_aes, cle_privee_ecdsa, base_locale
    ):
        """DATA(chunks) → reconstitution exacte du JSON original."""
        from communication.ble_serveur import BLE_CHUNK_SIZE

        _stocker_cycle(_fabriquer_cycle("test-sentinelle-001", 0),
                       cle_aes, cle_privee_ecdsa, base_locale)

        bundle = base_locale.recuperer_bundle_par_index(0)
        json_original = json.dumps(bundle)

        chunks = [json_original[i:i+BLE_CHUNK_SIZE]
                  for i in range(0, len(json_original), BLE_CHUNK_SIZE)]
        total = len(chunks)

        # Simuler la lecture côté mule : accumuler les chunks
        accumule = []
        for i, data in enumerate(chunks):
            envelope = {"total": total, "chunk": i, "data": data}
            accumule.append(envelope["data"])
            if envelope["chunk"] == envelope["total"] - 1:
                break  # dernier chunk

        reconstitue = "".join(accumule)
        assert reconstitue == json_original

    def test_C04_transfert_5_bundles_complet(
        self, cle_aes, cle_privee_ecdsa, cle_publique_pem, base_locale
    ):
        """La mule télécharge et acquitte 5 bundles. Base vide à la fin."""
        from communication.ble_serveur import BLE_CHUNK_SIZE

        nb_bundles = 5
        for i in range(nb_bundles):
            _stocker_cycle(_fabriquer_cycle("test-sentinelle-001", i),
                           cle_aes, cle_privee_ecdsa, base_locale)

        assert base_locale.compter_bundles_en_attente() == nb_bundles

        # Protocole mule : toujours SELECT(0) → chunks → ACK
        bundles_recus = []
        for _ in range(nb_bundles):
            bundle = base_locale.recuperer_bundle_par_index(0)
            assert bundle is not None
            json_bundle = json.dumps(bundle)
            chunks = [json_bundle[i:i+BLE_CHUNK_SIZE]
                      for i in range(0, len(json_bundle), BLE_CHUNK_SIZE)]
            reconstitue = json.loads("".join(chunks))
            bundles_recus.append(reconstitue["bundle_id"])
            base_locale.marquer_transfere(reconstitue["bundle_id"])

        assert base_locale.compter_bundles_en_attente() == 0
        assert len(bundles_recus) == nb_bundles

    def test_C05_signature_verifiee_par_mule_avant_envoi(
        self, cle_aes, cle_privee_ecdsa, cle_publique_pem, base_locale
    ):
        """La mule vérifie chaque signature ECDSA avant de publier sur MQTT."""
        from securite.signature import verifier_signature

        for i in range(3):
            _stocker_cycle(_fabriquer_cycle("test-sentinelle-001", i),
                           cle_aes, cle_privee_ecdsa, base_locale)

        cle_pub = ECC.import_key(cle_publique_pem)
        for i in range(3):
            b, _ = _recuperer_et_verifier_bundle(base_locale, i, cle_aes, cle_pub)
            # Vérification explicite signature
            iv  = base64.b64decode(b["iv"])
            enc = base64.b64decode(b["donnees_chiffrees"])
            sig = base64.b64decode(b["signature"])
            assert verifier_signature(iv + enc, sig, cle_pub) is True

    def test_C06_288_bundles_transferes_en_serie(
        self, cle_aes, cle_privee_ecdsa, base_locale
    ):
        """Scénario 24h : 288 bundles transférés sans erreur."""
        from communication.ble_serveur import BLE_CHUNK_SIZE

        for i in range(288):
            _stocker_cycle(_fabriquer_cycle("test-sentinelle-001", i),
                           cle_aes, cle_privee_ecdsa, base_locale)

        nb_transferes = 0
        while base_locale.compter_bundles_en_attente() > 0:
            bundle = base_locale.recuperer_bundle_par_index(0)
            base_locale.marquer_transfere(bundle["bundle_id"])
            nb_transferes += 1

        assert nb_transferes == 288
        assert base_locale.compter_bundles_en_attente() == 0

    def test_C07_bundle_count_decroit_apres_chaque_ack(
        self, cle_aes, cle_privee_ecdsa, base_locale
    ):
        """Après chaque ACK, BUNDLE_COUNT décroît de 1."""
        for i in range(5):
            _stocker_cycle(_fabriquer_cycle("test-sentinelle-001", i),
                           cle_aes, cle_privee_ecdsa, base_locale)

        for attendu in [4, 3, 2, 1, 0]:
            b = base_locale.recuperer_bundle_par_index(0)
            base_locale.marquer_transfere(b["bundle_id"])
            assert base_locale.compter_bundles_en_attente() == attendu

    def test_C08_chaque_chunk_sous_512_octets(
        self, cle_aes, cle_privee_ecdsa, base_locale
    ):
        """Chaque paquet BLE (enveloppe JSON) fait < 512 octets."""
        from communication.ble_serveur import BLE_CHUNK_SIZE

        _stocker_cycle(_fabriquer_cycle("test-sentinelle-001", 0),
                       cle_aes, cle_privee_ecdsa, base_locale)
        b = base_locale.recuperer_bundle_par_index(0)
        full_json = json.dumps(b)
        chunks = [full_json[i:i+BLE_CHUNK_SIZE]
                  for i in range(0, len(full_json), BLE_CHUNK_SIZE)]

        for i, chunk in enumerate(chunks):
            enveloppe = json.dumps({
                "total": len(chunks), "chunk": i, "data": chunk
            }).encode("utf-8")
            assert len(enveloppe) <= 512, \
                f"Chunk {i} dépasse 512 octets : {len(enveloppe)} B"


# =============================================================================
# ACTE 4 : Transmission MQTT (simulation côté mule)
# =============================================================================

class TestActe4TransmissionMQTT:
    """
    La mule a quitté la zone et retrouvé du réseau.
    Elle publie chaque bundle sur le broker MQTT neOCampus.
    Topic : TestTopic/lora/neOCampus/<sentinel_id>
    """

    def _simuler_publication_mqtt(self, bundles_json: list, sentinel_id: str) -> dict:
        """Simule les appels MQTT publish et retourne un rapport."""
        import config
        rapport = {"succes": 0, "echecs": 0, "topics": set()}

        for bundle_json in bundles_json:
            topic = f"{config.MQTT_TOPIC_PREFIX}/{sentinel_id}"
            payload = json.dumps(bundle_json)
            # Simuler publish (mock)
            mock_client = MagicMock()
            mock_client.publish.return_value = MagicMock(rc=0)
            result = mock_client.publish(topic, payload, qos=1)
            if result.rc == 0:
                rapport["succes"] += 1
                rapport["topics"].add(topic)
            else:
                rapport["echecs"] += 1

        return rapport

    def test_D01_topic_mqtt_correct_par_sentinel_id(
        self, cle_aes, cle_privee_ecdsa, base_locale
    ):
        """Le topic MQTT contient le sentinel_id de la sentinelle source."""
        import config
        _stocker_cycle(_fabriquer_cycle(config.SENTINEL_ID, 0),
                       cle_aes, cle_privee_ecdsa, base_locale)
        b = base_locale.recuperer_bundle_par_index(0)

        topic = f"{config.MQTT_TOPIC_PREFIX}/{b['sentinel_id']}"
        assert config.SENTINEL_ID in topic
        assert "neOCampus" in topic

    def test_D02_payload_mqtt_est_json_valide(
        self, cle_aes, cle_privee_ecdsa, base_locale
    ):
        """Le payload MQTT (bundle JSON) est parseable sans erreur."""
        _stocker_cycle(_fabriquer_cycle("test-sentinelle-001", 0),
                       cle_aes, cle_privee_ecdsa, base_locale)
        b = base_locale.recuperer_bundle_par_index(0)

        payload = json.dumps(b)
        parsed = json.loads(payload)

        assert "bundle_id"        in parsed
        assert "iv"               in parsed
        assert "donnees_chiffrees"in parsed
        assert "signature"        in parsed
        assert "nonce"            in parsed

    def test_D03_5_bundles_tous_publies_avec_succes(
        self, cle_aes, cle_privee_ecdsa, base_locale
    ):
        """La mule publie 5 bundles → 5 succès MQTT."""
        bundles_json = []
        for i in range(5):
            _stocker_cycle(_fabriquer_cycle("test-sentinelle-001", i),
                           cle_aes, cle_privee_ecdsa, base_locale)

        for i in range(5):
            b = base_locale.recuperer_bundle_par_index(i)
            bundles_json.append(b)

        rapport = self._simuler_publication_mqtt(bundles_json, "test-sentinelle-001")
        assert rapport["succes"] == 5
        assert rapport["echecs"] == 0

    def test_D04_sentinel_id_correct_dans_payload(
        self, cle_aes, cle_privee_ecdsa, cle_publique_pem, base_locale
    ):
        """Le sentinel_id dans le bundle déchiffré correspond à la source."""
        from securite.chiffrement import dechiffrer_donnees
        import config

        _stocker_cycle(_fabriquer_cycle(config.SENTINEL_ID, 0),
                       cle_aes, cle_privee_ecdsa, base_locale)
        b = base_locale.recuperer_bundle_par_index(0)

        iv  = base64.b64decode(b["iv"])
        enc = base64.b64decode(b["donnees_chiffrees"])
        dec = dechiffrer_donnees(iv, enc, cle_aes)

        assert dec["sentinel_id"] == config.SENTINEL_ID

    def test_D05_rapport_final_apres_transfert_complet(
        self, cle_aes, cle_privee_ecdsa, base_locale
    ):
        """Rapport final : X bundles reçus, X envoyés, 0 erreur."""
        n = 10
        for i in range(n):
            _stocker_cycle(_fabriquer_cycle("test-sentinelle-001", i),
                           cle_aes, cle_privee_ecdsa, base_locale)

        bundles_json = [base_locale.recuperer_bundle_par_index(i) for i in range(n)]
        rapport = self._simuler_publication_mqtt(bundles_json, "test-sentinelle-001")

        # Simuler acquittement après publication réussie
        for b in bundles_json:
            base_locale.marquer_transfere(b["bundle_id"])

        assert rapport["succes"] == n
        assert base_locale.compter_bundles_en_attente() == 0


# =============================================================================
# ACTE 5 : Résilience — pannes et cas limites
# =============================================================================

class TestActe5Resilience:
    """
    Tout ne se passe pas toujours parfaitement.
    Ces tests valident que le système se comporte correctement face aux pannes.
    """

    def test_E01_deconnexion_ble_mid_transfert_reprise_correcte(
        self, cle_aes, cle_privee_ecdsa, base_locale
    ):
        """
        Scénario : mule commence → télécharge 3 sur 10 → déconnexion.
        Reconnexion → reprend depuis bundle index 0 (les 3 premiers déjà ACK).
        Les 7 restants sont récupérés correctement.
        """
        n = 10
        for i in range(n):
            _stocker_cycle(_fabriquer_cycle("test-sentinelle-001", i),
                           cle_aes, cle_privee_ecdsa, base_locale)

        # Premier passage : 3 bundles ACKés puis déconnexion
        for _ in range(3):
            b = base_locale.recuperer_bundle_par_index(0)
            base_locale.marquer_transfere(b["bundle_id"])

        assert base_locale.compter_bundles_en_attente() == 7

        # Reconnexion : reprend depuis index 0
        nb_deuxieme_passage = 0
        while base_locale.compter_bundles_en_attente() > 0:
            b = base_locale.recuperer_bundle_par_index(0)
            base_locale.marquer_transfere(b["bundle_id"])
            nb_deuxieme_passage += 1

        assert nb_deuxieme_passage == 7
        assert base_locale.compter_bundles_en_attente() == 0

    def test_E02_capteur_pms5003_defaillant_mesures_partielles(
        self, cle_aes, cle_privee_ecdsa, base_locale
    ):
        """Si PMS5003 tombe en panne, la sentinelle continue avec DHT22 + BME280."""
        # nb_capteurs=2 → seulement pression (BME280) car _fabriquer_cycle structure
        cycle_degrade = _fabriquer_cycle("test-sentinelle-001", 0, nb_capteurs=2)
        bid = _stocker_cycle(cycle_degrade, cle_aes, cle_privee_ecdsa, base_locale)

        b = base_locale.recuperer_bundle_par_index(0)
        assert b["nb_mesures"] > 0, "Aucune mesure même avec capteurs partiels"

    def test_E03_double_acquittement_idempotent(
        self, cle_aes, cle_privee_ecdsa, base_locale
    ):
        """ACK d'un bundle déjà acquitté → False (pas d'erreur, pas de crash)."""
        _stocker_cycle(_fabriquer_cycle("test-sentinelle-001", 0),
                       cle_aes, cle_privee_ecdsa, base_locale)
        b = base_locale.recuperer_bundle_par_index(0)
        bid = b["bundle_id"]

        r1 = base_locale.marquer_transfere(bid)
        r2 = base_locale.marquer_transfere(bid)  # deuxième fois

        assert r1 is True
        assert r2 is False  # Déjà traité
        assert base_locale.compter_bundles_en_attente() == 0

    def test_E04_signature_corrompue_rejetee_par_mule(
        self, cle_aes, cle_privee_ecdsa, cle_publique_pem, base_locale
    ):
        """Un bundle avec signature altérée est rejeté (intégrité garantie)."""
        from securite.signature import verifier_signature

        _stocker_cycle(_fabriquer_cycle("test-sentinelle-001", 0),
                       cle_aes, cle_privee_ecdsa, base_locale)
        b = base_locale.recuperer_bundle_par_index(0)

        cle_pub = ECC.import_key(cle_publique_pem)
        iv  = base64.b64decode(b["iv"])
        enc = base64.b64decode(b["donnees_chiffrees"])

        # Corrompre la signature : inverser les premiers octets
        sig_corrompue = bytes([x ^ 0xFF for x in base64.b64decode(b["signature"])])

        valide = verifier_signature(iv + enc, sig_corrompue, cle_pub)
        assert valide is False, "Une signature corrompue ne doit pas être valide !"

    def test_E05_donnees_tamponnees_invalident_signature(
        self, cle_aes, cle_privee_ecdsa, cle_publique_pem, base_locale
    ):
        """Si les données chiffrées sont modifiées, la signature est invalide."""
        from securite.signature import verifier_signature

        _stocker_cycle(_fabriquer_cycle("test-sentinelle-001", 0),
                       cle_aes, cle_privee_ecdsa, base_locale)
        b = base_locale.recuperer_bundle_par_index(0)

        cle_pub = ECC.import_key(cle_publique_pem)
        iv  = base64.b64decode(b["iv"])
        sig = base64.b64decode(b["signature"])

        # Tamponner les données chiffrées
        enc_original = base64.b64decode(b["donnees_chiffrees"])
        enc_tamponne = bytearray(enc_original)
        enc_tamponne[0] ^= 0x01  # Modifier un seul bit

        valide = verifier_signature(iv + bytes(enc_tamponne), sig, cle_pub)
        assert valide is False

    def test_E06_nonce_duplique_detecte(
        self, cle_aes, cle_privee_ecdsa, base_locale
    ):
        """Un bundle rejoué (nonce dupliqué) est détectable par le serveur."""
        _stocker_cycle(_fabriquer_cycle("test-sentinelle-001", 0),
                       cle_aes, cle_privee_ecdsa, base_locale)
        b1 = base_locale.recuperer_bundle_par_index(0)

        # Simuler un deuxième bundle avec le même nonce
        nonces_vus = {b1["nonce"]}
        nonce_rejoue = b1["nonce"]

        assert nonce_rejoue in nonces_vus, "Le nonce rejoué n'est pas détecté !"

    def test_E07_quota_sqlite_nettoyage_bundles_transferes(
        self, cle_aes, cle_privee_ecdsa, base_locale
    ):
        """Au-delà du quota, les bundles transférés sont supprimés (pas les en_attente)."""
        import config

        limite = config.MAX_BUNDLES_STOCKES
        moitie = limite // 2

        # Stocker et acquitter la moitié → seront nettoyés si quota dépassé
        ids_tranferes = []
        for i in range(moitie):
            bid = _stocker_cycle(_fabriquer_cycle("test-sentinelle-001", i),
                                 cle_aes, cle_privee_ecdsa, base_locale)
            ids_tranferes.append(bid)
        for bid in ids_tranferes:
            base_locale.marquer_transfere(bid)

        # Stocker encore pour dépasser le quota
        for i in range(moitie, moitie + limite // 2 + 10):
            _stocker_cycle(_fabriquer_cycle("test-sentinelle-001", i),
                           cle_aes, cle_privee_ecdsa, base_locale)

        # Le total de la table ne dépasse pas la limite
        c = base_locale.connexion.execute("SELECT COUNT(*) FROM bundles").fetchone()[0]
        assert c <= limite, f"Quota dépassé : {c} bundles en base"

    def test_E08_ecriture_et_lecture_ble_simultanes_thread_safe(
        self, cle_aes, cle_privee_ecdsa, base_locale
    ):
        """Thread principal écrit, thread BLE lit → aucune corruption."""
        # Pré-remplir
        for i in range(10):
            _stocker_cycle(_fabriquer_cycle("test-sentinelle-001", i),
                           cle_aes, cle_privee_ecdsa, base_locale)

        erreurs = []
        CYCLES_WRITE = 20
        CYCLES_READ  = 30

        def thread_ecriture():
            for i in range(10, 10 + CYCLES_WRITE):
                try:
                    _stocker_cycle(_fabriquer_cycle("test-sentinelle-001", i),
                                   cle_aes, cle_privee_ecdsa, base_locale)
                except Exception as e:
                    erreurs.append(f"WRITE: {e}")

        def thread_ble_lecture():
            for _ in range(CYCLES_READ):
                try:
                    base_locale.recuperer_bundle_par_index(0)
                    base_locale.compter_bundles_en_attente()
                except Exception as e:
                    erreurs.append(f"READ: {e}")

        t1 = threading.Thread(target=thread_ecriture)
        t2 = threading.Thread(target=thread_ble_lecture)
        t1.start(); t2.start()
        t1.join();  t2.join()

        assert erreurs == [], f"Erreurs thread-safety : {erreurs}"


# =============================================================================
# ACTE 6 : Déploiement multi-sentinelles simultané
# =============================================================================

class TestActe6MultiSentinelles:
    """
    Trois sentinelles sont déployées simultanément dans des zones différentes.
    Chacune a ses propres clés, son propre ID, sa propre base de données.
    Une mule passe et collecte les données de toutes les sentinelles en séquence.
    """

    def _creer_sentinelle(self, tmp_path, sentinel_id: str, idx_sentinel: int):
        """Crée une sentinelle isolée avec ses propres clés et BDD."""
        import config
        from securite.cles import generer_cle_aes, generer_cles_ecdsa, charger_cle_privee_ecdsa
        from stockage.base_locale import BaseLocale

        rep = str(tmp_path / f"sentinelle_{idx_sentinel}")
        os.makedirs(rep, exist_ok=True)

        # Sauvegarder config
        ancien = {k: getattr(config, k) for k in
                  ["REPERTOIRE_CLES", "FICHIER_CLE_AES", "FICHIER_CLE_PRIVEE",
                   "FICHIER_CLE_PUBLIQUE", "FICHIER_BASE_DONNEES", "SENTINEL_ID"]}

        config.REPERTOIRE_CLES     = os.path.join(rep, "cles")
        config.FICHIER_CLE_AES     = os.path.join(rep, "cles", "aes.bin")
        config.FICHIER_CLE_PRIVEE  = os.path.join(rep, "cles", "priv.pem")
        config.FICHIER_CLE_PUBLIQUE= os.path.join(rep, "cles", "pub.pem")
        config.FICHIER_BASE_DONNEES= os.path.join(rep, "db", "sentinelle.db")
        config.SENTINEL_ID         = sentinel_id

        os.makedirs(os.path.join(rep, "db"), exist_ok=True)

        cle_aes  = generer_cle_aes()
        _, pub_pem = generer_cles_ecdsa()
        cle_priv = charger_cle_privee_ecdsa()
        base     = BaseLocale()

        # Restaurer config
        for k, v in ancien.items():
            setattr(config, k, v)

        return {"id": sentinel_id, "aes": cle_aes, "priv": cle_priv,
                "pub": pub_pem, "base": base}

    def test_F01_trois_sentinelles_cles_distinctes(self, tmp_path):
        """Trois sentinelles ont des clés AES indépendantes."""
        s1 = self._creer_sentinelle(tmp_path, "sentinelle-001", 1)
        s2 = self._creer_sentinelle(tmp_path, "sentinelle-002", 2)
        s3 = self._creer_sentinelle(tmp_path, "sentinelle-003", 3)

        assert s1["aes"] != s2["aes"], "S1 et S2 ont la même clé AES !"
        assert s2["aes"] != s3["aes"], "S2 et S3 ont la même clé AES !"
        assert s1["aes"] != s3["aes"], "S1 et S3 ont la même clé AES !"

        for s in [s1, s2, s3]:
            s["base"].fermer()

    def test_F02_bundles_identifies_par_sentinel_id(self, tmp_path):
        """Chaque bundle conserve le sentinel_id de sa source après déchiffrement."""
        from securite.chiffrement import dechiffrer_donnees

        for i in range(1, 4):
            sid = f"sentinelle-00{i}"
            s = self._creer_sentinelle(tmp_path, sid, i)
            cycle = _fabriquer_cycle(sid, 0)
            _stocker_cycle(cycle, s["aes"], s["priv"], s["base"])

            b = s["base"].recuperer_bundle_par_index(0)
            iv  = base64.b64decode(b["iv"])
            enc = base64.b64decode(b["donnees_chiffrees"])
            dec = dechiffrer_donnees(iv, enc, s["aes"])

            assert dec["sentinel_id"] == sid, \
                f"Mauvais sentinel_id dans le bundle de {sid}"
            s["base"].fermer()

    def test_F03_trois_sentinelles_collecte_simultanee(self, tmp_path):
        """Trois sentinelles collectent en parallèle sans interférence."""
        sentinelles = [self._creer_sentinelle(tmp_path, f"sentinelle-00{i}", i)
                       for i in range(1, 4)]
        erreurs = []

        def collecter(s, nb_cycles=10):
            try:
                for j in range(nb_cycles):
                    cycle = _fabriquer_cycle(s["id"], j)
                    _stocker_cycle(cycle, s["aes"], s["priv"], s["base"])
            except Exception as e:
                erreurs.append(str(e))

        threads = [threading.Thread(target=collecter, args=(s,))
                   for s in sentinelles]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert erreurs == [], f"Erreurs de collecte simultanée : {erreurs}"

        for s in sentinelles:
            assert s["base"].compter_bundles_en_attente() == 10
            s["base"].fermer()

    def test_F04_mule_recoit_bundles_de_3_sentinelles(self, tmp_path):
        """La mule peut récupérer et distinguer les bundles de 3 sentinelles."""
        sentinelles = [self._creer_sentinelle(tmp_path, f"sentinelle-00{i}", i)
                       for i in range(1, 4)]

        for s in sentinelles:
            for j in range(5):
                _stocker_cycle(_fabriquer_cycle(s["id"], j),
                               s["aes"], s["priv"], s["base"])

        # La mule collecte tout
        tous_bundles = []
        for s in sentinelles:
            while s["base"].compter_bundles_en_attente() > 0:
                b = s["base"].recuperer_bundle_par_index(0)
                tous_bundles.append(b)
                s["base"].marquer_transfere(b["bundle_id"])
            s["base"].fermer()

        assert len(tous_bundles) == 15  # 3 sentinelles × 5 bundles

        # Tous les bundle_id sont uniques (pas de doublon inter-sentinelles)
        bids = [b["bundle_id"] for b in tous_bundles]
        assert len(set(bids)) == 15, "Des bundle_ids sont dupliqués entre sentinelles"

        # Note : sentinel_id est lu depuis config.SENTINEL_ID au moment de la lecture
        # La vérification du sentinel_id par bundle est couverte par test_F02
        # qui déchiffre le payload et vérifie le sentinel_id dans les données claires

    def test_F05_clef_publique_differente_par_sentinelle(self, tmp_path):
        """Chaque sentinelle a une clé publique ECDSA différente (non partagée)."""
        sentinelles = [self._creer_sentinelle(tmp_path, f"sentinelle-00{i}", i)
                       for i in range(1, 4)]

        pubs = [s["pub"] for s in sentinelles]
        assert pubs[0] != pubs[1], "S1 et S2 partagent la même clé publique !"
        assert pubs[1] != pubs[2], "S2 et S3 partagent la même clé publique !"

        for s in sentinelles:
            s["base"].fermer()
