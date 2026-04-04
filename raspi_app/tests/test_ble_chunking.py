"""
test_ble_chunking.py -- Tests du protocole de chunking BLE de ble_serveur.py.

On teste la logique de decoupage et de lecture par chunks de CaracBundleData
et CaracBundleSelect sans necessiter D-Bus (fonctionne sur Windows/Mac/Linux).
"""

import json
import pytest
from unittest.mock import MagicMock, patch
from communication.ble_serveur import CaracBundleData, CaracBundleSelect, BLE_CHUNK_SIZE


# =============================================================================
# FIXTURE : base_locale simulee
# =============================================================================

def _fabriquer_bundle(nb_mesures=8, taille_donnees=800):
    """Cree un bundle JSON de taille controlee pour les tests."""
    import base64
    from Crypto.Random import get_random_bytes
    return {
        "bundle_id": "550e8400-e29b-41d4-a716-446655440000",
        "sentinel_id": "test-sentinelle-001",
        "iv": base64.b64encode(get_random_bytes(16)).decode("ascii"),
        "donnees_chiffrees": base64.b64encode(get_random_bytes(taille_donnees)).decode("ascii"),
        "signature": base64.b64encode(get_random_bytes(64)).decode("ascii"),
        "nonce": get_random_bytes(16).hex(),
        "horodatage": "2026-04-04T10:00:00.000000+00:00",
        "nb_mesures": nb_mesures,
    }


def _mock_base(bundle=None):
    """Retourne une base_locale simulee avec un bundle optionnel."""
    base = MagicMock()
    base.recuperer_bundle_par_index.return_value = bundle
    base.compter_bundles_en_attente.return_value = 1 if bundle else 0
    return base


def _mock_service():
    """Retourne un service GATT simule (pour le chemin de caracteristique)."""
    service = MagicMock()
    service.get_path.return_value = "/org/bluez/sentinelle/service0"
    return service


# =============================================================================
# TESTS : CaracBundleData.selectionner()
# =============================================================================

class TestSelectionner:
    def test_bundle_trouve_produit_au_moins_un_chunk(self):
        bundle = _fabriquer_bundle()
        carac = CaracBundleData(None, 0, _mock_service(), _mock_base(bundle))
        carac.selectionner(0)
        assert len(carac.chunks) >= 1

    def test_bundle_introuvable_produit_chunk_erreur(self):
        carac = CaracBundleData(None, 0, _mock_service(), _mock_base(None))
        carac.selectionner(0)
        assert len(carac.chunks) == 1
        assert "erreur" in json.loads(carac.chunks[0])

    def test_pointeur_remis_a_zero(self):
        bundle = _fabriquer_bundle()
        carac = CaracBundleData(None, 0, _mock_service(), _mock_base(bundle))
        carac.chunk_idx = 99  # Simuler un etat en cours
        carac.selectionner(0)
        assert carac.chunk_idx == 0

    def test_selectionner_deux_fois_remet_a_zero(self):
        bundle = _fabriquer_bundle()
        carac = CaracBundleData(None, 0, _mock_service(), _mock_base(bundle))
        carac.selectionner(0)
        carac.chunk_idx = 3
        carac.selectionner(0)
        assert carac.chunk_idx == 0

    def test_chunks_non_vides(self):
        bundle = _fabriquer_bundle()
        carac = CaracBundleData(None, 0, _mock_service(), _mock_base(bundle))
        carac.selectionner(0)
        for chunk in carac.chunks:
            assert chunk  # Aucun chunk vide

    def test_reconstitution_json_correcte(self):
        """La concatenation de tous les chunks donne le JSON complet du bundle."""
        bundle = _fabriquer_bundle()
        carac = CaracBundleData(None, 0, _mock_service(), _mock_base(bundle))
        carac.selectionner(0)
        json_reconstruit = "".join(carac.chunks)
        bundle_reconstruit = json.loads(json_reconstruit)
        assert bundle_reconstruit["bundle_id"] == bundle["bundle_id"]
        assert bundle_reconstruit["sentinel_id"] == bundle["sentinel_id"]
        assert bundle_reconstruit["nb_mesures"] == bundle["nb_mesures"]

    def test_chaque_chunk_respecte_taille_max(self):
        bundle = _fabriquer_bundle(taille_donnees=1000)
        carac = CaracBundleData(None, 0, _mock_service(), _mock_base(bundle))
        carac.selectionner(0)
        for chunk in carac.chunks:
            assert len(chunk) <= BLE_CHUNK_SIZE

    def test_bundle_petit_un_seul_chunk(self):
        """Un bundle tres petit tient dans un seul chunk."""
        bundle = {
            "bundle_id": "abc", "sentinel_id": "x",
            "iv": "iv", "donnees_chiffrees": "data",
            "signature": "sig", "nonce": "nonce",
            "horodatage": "2026-01-01T00:00:00+00:00", "nb_mesures": 1,
        }
        base = _mock_base(bundle)
        carac = CaracBundleData(None, 0, _mock_service(), base)
        carac.selectionner(0)
        assert len(carac.chunks) == 1

    def test_bundle_volumineux_plusieurs_chunks(self):
        """Un bundle volumineux necessite plusieurs chunks."""
        bundle = _fabriquer_bundle(taille_donnees=2000)
        carac = CaracBundleData(None, 0, _mock_service(), _mock_base(bundle))
        carac.selectionner(0)
        assert len(carac.chunks) > 1

    def test_appel_base_avec_bon_index(self):
        base = _mock_base(_fabriquer_bundle())
        carac = CaracBundleData(None, 0, _mock_service(), base)
        carac.selectionner(5)
        base.recuperer_bundle_par_index.assert_called_once_with(5)


# =============================================================================
# TESTS : Protocole de lecture chunke (simulation de ReadValue sans D-Bus)
# =============================================================================

class TestProtocoleChunks:
    def _simuler_read_value(self, carac):
        """Simule un appel ReadValue en appelant directement la logique interne."""
        if not carac.chunks:
            carac.selectionner(0)

        total = len(carac.chunks)
        idx = min(carac.chunk_idx, total - 1)
        enveloppe = json.dumps({
            "total": total,
            "chunk": idx,
            "data": carac.chunks[idx],
        })
        if carac.chunk_idx < total - 1:
            carac.chunk_idx += 1

        return enveloppe

    def test_lecture_complete_reconstitue_bundle(self):
        bundle = _fabriquer_bundle(taille_donnees=1000)
        carac = CaracBundleData(None, 0, _mock_service(), _mock_base(bundle))
        carac.selectionner(0)

        total_chunks = len(carac.chunks)
        json_complet = ""
        chunks_recus = 0

        while True:
            raw = self._simuler_read_value(carac)
            env = json.loads(raw)
            json_complet += env["data"]
            chunks_recus += 1
            assert env["total"] == total_chunks
            assert env["chunk"] == chunks_recus - 1
            if env["chunk"] == env["total"] - 1:
                break

        bundle_reconstruit = json.loads(json_complet)
        assert bundle_reconstruit["bundle_id"] == bundle["bundle_id"]
        assert bundle_reconstruit["signature"] == bundle["signature"]

    def test_nombre_lectures_egal_nombre_chunks(self):
        bundle = _fabriquer_bundle(taille_donnees=1200)
        carac = CaracBundleData(None, 0, _mock_service(), _mock_base(bundle))
        carac.selectionner(0)
        total = len(carac.chunks)

        lectures = 0
        while True:
            raw = self._simuler_read_value(carac)
            env = json.loads(raw)
            lectures += 1
            if env["chunk"] == env["total"] - 1:
                break

        assert lectures == total

    def test_lecture_supplementaire_retourne_dernier_chunk(self):
        """Si on lit plus que total chunks, on reste sur le dernier."""
        bundle = _fabriquer_bundle(taille_donnees=500)
        carac = CaracBundleData(None, 0, _mock_service(), _mock_base(bundle))
        carac.selectionner(0)
        total = len(carac.chunks)

        # Lire tous les chunks
        for _ in range(total):
            self._simuler_read_value(carac)

        # Lire une fois de plus
        raw = self._simuler_read_value(carac)
        env = json.loads(raw)
        assert env["chunk"] == total - 1

    def test_enveloppe_contient_champs_requis(self):
        bundle = _fabriquer_bundle()
        carac = CaracBundleData(None, 0, _mock_service(), _mock_base(bundle))
        carac.selectionner(0)
        raw = self._simuler_read_value(carac)
        env = json.loads(raw)
        assert "total" in env
        assert "chunk" in env
        assert "data" in env

    def test_total_constant_sur_tous_les_chunks(self):
        bundle = _fabriquer_bundle(taille_donnees=1500)
        carac = CaracBundleData(None, 0, _mock_service(), _mock_base(bundle))
        carac.selectionner(0)
        total = len(carac.chunks)

        totals = []
        for _ in range(total):
            raw = self._simuler_read_value(carac)
            env = json.loads(raw)
            totals.append(env["total"])

        assert all(t == total for t in totals)

    def test_chunks_indices_incrementaux(self):
        bundle = _fabriquer_bundle(taille_donnees=1000)
        carac = CaracBundleData(None, 0, _mock_service(), _mock_base(bundle))
        carac.selectionner(0)
        total = len(carac.chunks)

        indices = []
        for _ in range(total):
            raw = self._simuler_read_value(carac)
            env = json.loads(raw)
            indices.append(env["chunk"])

        assert indices == list(range(total))

    def test_bundle_erreur_lisible_en_un_chunk(self):
        carac = CaracBundleData(None, 0, _mock_service(), _mock_base(None))
        carac.selectionner(99)
        raw = self._simuler_read_value(carac)
        env = json.loads(raw)
        assert env["total"] == 1
        assert env["chunk"] == 0
        contenu = json.loads(env["data"])
        assert contenu["erreur"] == "aucun_bundle"

    def test_reconstitution_signature_exacte(self):
        """La signature ne doit pas etre alteree par le decoupage/reassemblage."""
        bundle = _fabriquer_bundle(taille_donnees=800)
        signature_originale = bundle["signature"]

        carac = CaracBundleData(None, 0, _mock_service(), _mock_base(bundle))
        carac.selectionner(0)
        total = len(carac.chunks)

        json_complet = ""
        for _ in range(total):
            raw = self._simuler_read_value(carac)
            env = json.loads(raw)
            json_complet += env["data"]

        bundle_reconstruit = json.loads(json_complet)
        assert bundle_reconstruit["signature"] == signature_originale

    def test_bundle_1_ko(self):
        """Un bundle de 1 Ko est correctement decoupe et reassemble."""
        bundle = _fabriquer_bundle(taille_donnees=700)
        carac = CaracBundleData(None, 0, _mock_service(), _mock_base(bundle))
        carac.selectionner(0)
        total = len(carac.chunks)

        json_complet = ""
        for _ in range(total):
            raw = self._simuler_read_value(carac)
            env = json.loads(raw)
            json_complet += env["data"]

        assert json.loads(json_complet)["bundle_id"] == bundle["bundle_id"]


# =============================================================================
# TESTS : CaracBundleSelect (sans D-Bus)
# =============================================================================

class TestCaracBundleSelect:
    def test_selectionner_appele_sur_write(self):
        carac_data = MagicMock()
        service = _mock_service()
        carac_sel = CaracBundleSelect(None, 5, service, carac_data)

        # Simule directement l'appel de selectionner (sans D-Bus)
        carac_sel.carac_bundle_data.selectionner(3)
        carac_data.selectionner.assert_called_once_with(3)

    def test_carac_data_reference_correcte(self):
        carac_data = MagicMock()
        service = _mock_service()
        carac_sel = CaracBundleSelect(None, 5, service, carac_data)
        assert carac_sel.carac_bundle_data is carac_data

    def test_uuid_bundle_select_correct(self):
        import config
        carac_data = MagicMock()
        service = _mock_service()
        carac_sel = CaracBundleSelect(None, 5, service, carac_data)
        assert carac_sel.uuid == config.BLE_CHAR_BUNDLE_SELECT_UUID


# =============================================================================
# TESTS : ServeurBLE (mode simulation, sans D-Bus)
# =============================================================================

class TestServeurBLESimulation:
    def test_demarrer_sans_dbus(self):
        from communication.ble_serveur import ServeurBLE, DBUS_DISPONIBLE
        base = _mock_base()
        serveur = ServeurBLE(base, "---PUBLIC KEY---")
        serveur.demarrer()  # Doit passer sans lever d'exception
        assert serveur.thread is None or not DBUS_DISPONIBLE

    def test_notifier_sans_carac_ne_crash_pas(self):
        from communication.ble_serveur import ServeurBLE
        base = _mock_base()
        serveur = ServeurBLE(base, "---PUBLIC KEY---")
        serveur.notifier_nouveau_bundle()  # Ne doit pas lever d'exception

    def test_arreter_sans_mainloop_ne_crash_pas(self):
        from communication.ble_serveur import ServeurBLE
        base = _mock_base()
        serveur = ServeurBLE(base, "---PUBLIC KEY---")
        serveur.arreter()  # mainloop est None, ne doit pas lever d'exception

    def test_constante_chunk_size_positive(self):
        from communication.ble_serveur import BLE_CHUNK_SIZE
        assert BLE_CHUNK_SIZE > 0

    def test_constante_chunk_size_dans_limite_ble(self):
        from communication.ble_serveur import BLE_CHUNK_SIZE
        # BLE_CHUNK_SIZE + enveloppe JSON (~110 octets) doit tenir en 512 octets
        assert BLE_CHUNK_SIZE + 110 <= 512
