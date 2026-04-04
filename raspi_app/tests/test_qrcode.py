"""
test_qrcode.py -- Tests du generateur de QR code.
"""

import json
import os
import pytest
from unittest.mock import patch, MagicMock


class TestObtenirAdresseBLE:
    def test_retourne_str(self):
        from utils.qrcode_gen import obtenir_adresse_ble
        result = obtenir_adresse_ble()
        assert isinstance(result, str)

    def test_fallback_placeholder_si_hciconfig_absent(self):
        from utils.qrcode_gen import obtenir_adresse_ble
        with patch("subprocess.run", side_effect=FileNotFoundError):
            result = obtenir_adresse_ble()
            assert result == "XX:XX:XX:XX:XX:XX"

    def test_fallback_si_timeout(self):
        import subprocess
        from utils.qrcode_gen import obtenir_adresse_ble
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("hciconfig", 5)):
            result = obtenir_adresse_ble()
            assert result == "XX:XX:XX:XX:XX:XX"

    def test_parse_adresse_mac_depuis_hciconfig(self):
        from utils.qrcode_gen import obtenir_adresse_ble
        sortie_hciconfig = (
            "hci0:\tType: Primary  Bus: UART\n"
            "\tBD Address: DC:A6:32:12:AB:CD  ACL MTU: 1021:8  SCO MTU: 64:1\n"
        )
        mock_result = MagicMock()
        mock_result.stdout = sortie_hciconfig
        with patch("subprocess.run", return_value=mock_result):
            result = obtenir_adresse_ble()
            assert result == "DC:A6:32:12:AB:CD"


class TestGenererQRCode:
    def test_retourne_none_si_qrcode_absent(self, tmp_path):
        from utils import qrcode_gen
        original = qrcode_gen.QRCODE_DISPONIBLE
        qrcode_gen.QRCODE_DISPONIBLE = False
        try:
            result = qrcode_gen.generer_qrcode(str(tmp_path / "qr.png"))
            assert result is None
        finally:
            qrcode_gen.QRCODE_DISPONIBLE = original

    def test_genere_fichier_si_qrcode_disponible(self, tmp_path):
        from utils import qrcode_gen
        if not qrcode_gen.QRCODE_DISPONIBLE:
            pytest.skip("qrcode non installe")

        chemin = str(tmp_path / "qr.png")
        with patch("utils.qrcode_gen.obtenir_adresse_ble", return_value="AA:BB:CC:DD:EE:FF"):
            result = qrcode_gen.generer_qrcode(chemin)

        assert result == chemin
        assert os.path.exists(chemin)

    def test_contenu_json_champs_requis(self, tmp_path):
        from utils import qrcode_gen
        if not qrcode_gen.QRCODE_DISPONIBLE:
            pytest.skip("qrcode non installe")

        chemin = str(tmp_path / "qr.png")
        contenu_capture = []

        import qrcode as qrcode_lib

        class FakeQR:
            def __init__(self, **kwargs): pass
            def add_data(self, data): contenu_capture.append(data)
            def make(self, fit): pass
            def make_image(self, **kwargs): return MagicMock(save=MagicMock())

        with patch("utils.qrcode_gen.obtenir_adresse_ble", return_value="AA:BB:CC:DD:EE:FF"):
            with patch("qrcode.QRCode", return_value=FakeQR()):
                qrcode_gen.generer_qrcode(chemin)

        assert contenu_capture
        contenu = json.loads(contenu_capture[0])
        assert "sentinel_id" in contenu
        assert "ble_service_uuid" in contenu
        assert "ble_address" in contenu
        assert "public_key" in contenu

    def test_contenu_sentinel_id_correct(self, tmp_path):
        import config
        from utils import qrcode_gen
        if not qrcode_gen.QRCODE_DISPONIBLE:
            pytest.skip("qrcode non installe")

        contenu_capture = []

        class FakeQR:
            def __init__(self, **kwargs): pass
            def add_data(self, data): contenu_capture.append(data)
            def make(self, fit): pass
            def make_image(self, **kwargs): return MagicMock(save=MagicMock())

        with patch("utils.qrcode_gen.obtenir_adresse_ble", return_value="AA:BB:CC:DD:EE:FF"):
            with patch("qrcode.QRCode", return_value=FakeQR()):
                qrcode_gen.generer_qrcode(str(tmp_path / "qr.png"))

        contenu = json.loads(contenu_capture[0])
        assert contenu["sentinel_id"] == config.SENTINEL_ID

    def test_contenu_ble_uuid_correct(self, tmp_path):
        import config
        from utils import qrcode_gen
        if not qrcode_gen.QRCODE_DISPONIBLE:
            pytest.skip("qrcode non installe")

        contenu_capture = []

        class FakeQR:
            def __init__(self, **kwargs): pass
            def add_data(self, data): contenu_capture.append(data)
            def make(self, fit): pass
            def make_image(self, **kwargs): return MagicMock(save=MagicMock())

        with patch("utils.qrcode_gen.obtenir_adresse_ble", return_value="AA:BB:CC:DD:EE:FF"):
            with patch("qrcode.QRCode", return_value=FakeQR()):
                qrcode_gen.generer_qrcode(str(tmp_path / "qr.png"))

        contenu = json.loads(contenu_capture[0])
        assert contenu["ble_service_uuid"] == config.BLE_SERVICE_UUID

    def test_chemin_defaut_dans_repertoire_cles(self, tmp_path):
        from utils import qrcode_gen
        if not qrcode_gen.QRCODE_DISPONIBLE:
            pytest.skip("qrcode non installe")

        class FakeQR:
            def __init__(self, **kwargs): pass
            def add_data(self, data): pass
            def make(self, fit): pass
            def make_image(self, **kwargs): return MagicMock(save=MagicMock())

        with patch("utils.qrcode_gen.obtenir_adresse_ble", return_value="AA:BB:CC:DD:EE:FF"):
            with patch("qrcode.QRCode", return_value=FakeQR()):
                chemin = qrcode_gen.generer_qrcode()

        assert chemin is not None
        assert "qrcode_" in chemin
        assert chemin.endswith(".png")

    def test_cle_publique_dans_contenu_qr(self, tmp_path):
        from utils import qrcode_gen
        if not qrcode_gen.QRCODE_DISPONIBLE:
            pytest.skip("qrcode non installe")

        contenu_capture = []

        class FakeQR:
            def __init__(self, **kwargs): pass
            def add_data(self, data): contenu_capture.append(data)
            def make(self, fit): pass
            def make_image(self, **kwargs): return MagicMock(save=MagicMock())

        with patch("utils.qrcode_gen.obtenir_adresse_ble", return_value="AA:BB:CC:DD:EE:FF"):
            with patch("qrcode.QRCode", return_value=FakeQR()):
                qrcode_gen.generer_qrcode(str(tmp_path / "qr.png"))

        contenu = json.loads(contenu_capture[0])
        assert "BEGIN PUBLIC KEY" in contenu["public_key"]
