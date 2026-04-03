"""
test_stockage.py -- Tests de la base SQLite locale.
"""
import pytest
from Crypto.Random import get_random_bytes


class TestBaseLocale:
    def test_base_vide_au_depart(self, base_locale):
        assert base_locale.compter_bundles_en_attente() == 0

    def test_stocker_un_bundle(self, base_locale):
        bid = base_locale.stocker_bundle(
            iv=get_random_bytes(16),
            donnees_chiffrees=get_random_bytes(64),
            signature=get_random_bytes(64),
            nonce=get_random_bytes(16).hex(),
            nb_mesures=5,
        )
        assert isinstance(bid, str) and len(bid) == 36  # UUID

    def test_compter_apres_stockage(self, base_locale):
        for _ in range(5):
            base_locale.stocker_bundle(
                get_random_bytes(16), get_random_bytes(64),
                get_random_bytes(64), get_random_bytes(16).hex(), 3,
            )
        assert base_locale.compter_bundles_en_attente() == 5

    def test_recuperer_par_index_0(self, base_locale):
        base_locale.stocker_bundle(
            get_random_bytes(16), get_random_bytes(64),
            get_random_bytes(64), "nonce_test", 4,
        )
        b = base_locale.recuperer_bundle_par_index(0)
        assert b is not None
        assert b["nb_mesures"] == 4
        assert b["nonce"] == "nonce_test"

    def test_index_invalide_retourne_none(self, base_locale):
        assert base_locale.recuperer_bundle_par_index(99) is None

    def test_fifo_ordre(self, base_locale):
        ids = []
        for i in range(3):
            ids.append(base_locale.stocker_bundle(
                get_random_bytes(16), get_random_bytes(64),
                get_random_bytes(64), f"nonce_{i}", i + 1,
            ))
        b0 = base_locale.recuperer_bundle_par_index(0)
        assert b0["bundle_id"] == ids[0]

    def test_marquer_transfere(self, base_locale):
        bid = base_locale.stocker_bundle(
            get_random_bytes(16), get_random_bytes(64),
            get_random_bytes(64), "n", 1,
        )
        assert base_locale.compter_bundles_en_attente() == 1
        assert base_locale.marquer_transfere(bid) is True
        assert base_locale.compter_bundles_en_attente() == 0

    def test_marquer_inexistant(self, base_locale):
        assert base_locale.marquer_transfere("inexistant-uuid") is False

    def test_double_acquittement(self, base_locale):
        bid = base_locale.stocker_bundle(
            get_random_bytes(16), get_random_bytes(64),
            get_random_bytes(64), "n", 1,
        )
        base_locale.marquer_transfere(bid)
        assert base_locale.marquer_transfere(bid) is False

    def test_bundle_transfere_invisible(self, base_locale):
        bid = base_locale.stocker_bundle(
            get_random_bytes(16), get_random_bytes(64),
            get_random_bytes(64), "n", 1,
        )
        base_locale.marquer_transfere(bid)
        assert base_locale.recuperer_bundle_par_index(0) is None

    def test_structure_bundle_recupere(self, base_locale):
        base_locale.stocker_bundle(
            get_random_bytes(16), get_random_bytes(64),
            get_random_bytes(64), "nonce_x", 3,
        )
        b = base_locale.recuperer_bundle_par_index(0)
        champs = {"bundle_id", "sentinel_id", "iv", "donnees_chiffrees",
                   "signature", "nonce", "horodatage", "nb_mesures"}
        assert set(b.keys()) == champs

    def test_stocker_50_bundles(self, base_locale):
        for i in range(50):
            base_locale.stocker_bundle(
                get_random_bytes(16), get_random_bytes(64),
                get_random_bytes(64), f"n{i}", i,
            )
        assert base_locale.compter_bundles_en_attente() == 50

    def test_fermeture(self, base_locale):
        base_locale.fermer()
