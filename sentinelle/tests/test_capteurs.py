"""
test_capteurs.py -- Tests des modules capteurs (simulation).
"""
import pytest
import struct
from capteurs.dht22 import CapteurDHT22
from capteurs.bme280 import CapteurBME280
from capteurs.pms5003 import CapteurPMS5003
from capteurs.gestionnaire import GestionnaireCapteurs


class TestDHT22:
    def test_retourne_deux_mesures(self):
        c = CapteurDHT22(pin_gpio=4, mode_simulation=True)
        assert len(c.lire()) == 2

    def test_types_temperature_humidite(self):
        c = CapteurDHT22(pin_gpio=4, mode_simulation=True)
        types = [m["type"] for m in c.lire()]
        assert "temperature" in types and "humidite" in types

    def test_unites_correctes(self):
        c = CapteurDHT22(pin_gpio=4, mode_simulation=True)
        unites = {m["type"]: m["unite"] for m in c.lire()}
        assert unites["temperature"] == "degC"
        assert unites["humidite"] == "%"

    def test_plage_temperature(self):
        c = CapteurDHT22(pin_gpio=4, mode_simulation=True)
        for _ in range(50):
            for m in c.lire():
                if m["type"] == "temperature":
                    assert -40 <= m["valeur"] <= 80

    def test_plage_humidite(self):
        c = CapteurDHT22(pin_gpio=4, mode_simulation=True)
        for _ in range(50):
            for m in c.lire():
                if m["type"] == "humidite":
                    assert 0 <= m["valeur"] <= 100

    def test_horodatage_iso8601(self):
        c = CapteurDHT22(pin_gpio=4, mode_simulation=True)
        for m in c.lire():
            assert "T" in m["horodatage"]

    def test_lectures_aleatoires(self):
        c = CapteurDHT22(pin_gpio=4, mode_simulation=True)
        vals = {c.lire()[0]["valeur"] for _ in range(20)}
        assert len(vals) > 1

    def test_structure_4_champs(self):
        c = CapteurDHT22(pin_gpio=4, mode_simulation=True)
        for m in c.lire():
            assert set(m.keys()) == {"type", "valeur", "unite", "horodatage"}

    def test_fermeture(self):
        c = CapteurDHT22(pin_gpio=4, mode_simulation=True)
        c.fermer()


class TestBME280:
    def test_retourne_trois_mesures(self):
        c = CapteurBME280(0x76, 1, mode_simulation=True)
        assert len(c.lire()) == 3

    def test_types_corrects(self):
        c = CapteurBME280(0x76, 1, mode_simulation=True)
        types = {m["type"] for m in c.lire()}
        assert types == {"pression", "temperature_bme", "humidite_bme"}

    def test_unite_pression(self):
        c = CapteurBME280(0x76, 1, mode_simulation=True)
        for m in c.lire():
            if m["type"] == "pression":
                assert m["unite"] == "hPa"

    def test_plage_pression(self):
        c = CapteurBME280(0x76, 1, mode_simulation=True)
        for _ in range(50):
            for m in c.lire():
                if m["type"] == "pression":
                    assert 300 <= m["valeur"] <= 1100

    def test_fermeture(self):
        c = CapteurBME280(0x76, 1, mode_simulation=True)
        c.fermer()


class TestPMS5003:
    def test_retourne_trois_mesures(self):
        c = CapteurPMS5003("/dev/null", 9600, mode_simulation=True)
        assert len(c.lire()) == 3

    def test_types_pm(self):
        c = CapteurPMS5003("/dev/null", 9600, mode_simulation=True)
        types = {m["type"] for m in c.lire()}
        assert types == {"pm1_0", "pm2_5", "pm10"}

    def test_unite_ug_m3(self):
        c = CapteurPMS5003("/dev/null", 9600, mode_simulation=True)
        for m in c.lire():
            assert m["unite"] == "ug/m3"

    def test_valeurs_positives(self):
        c = CapteurPMS5003("/dev/null", 9600, mode_simulation=True)
        for _ in range(50):
            for m in c.lire():
                assert m["valeur"] >= 0

    def test_valeurs_entieres(self):
        c = CapteurPMS5003("/dev/null", 9600, mode_simulation=True)
        for m in c.lire():
            assert isinstance(m["valeur"], int)

    def test_decoder_trame_valide(self):
        c = CapteurPMS5003("/dev/null", 9600, mode_simulation=True)
        trame = bytearray(32)
        trame[0], trame[1] = 0x42, 0x4D
        struct.pack_into(">H", trame, 2, 28)
        struct.pack_into(">H", trame, 10, 7)   # PM1.0 atmo
        struct.pack_into(">H", trame, 12, 15)  # PM2.5 atmo
        struct.pack_into(">H", trame, 14, 30)  # PM10 atmo
        struct.pack_into(">H", trame, 30, sum(trame[:-2]))
        r = c._decoder_trame(bytes(trame))
        assert r == {"pm1_0": 7, "pm2_5": 15, "pm10": 30}

    def test_decoder_trame_checksum_invalide(self):
        c = CapteurPMS5003("/dev/null", 9600, mode_simulation=True)
        trame = bytearray(32)
        trame[0], trame[1] = 0x42, 0x4D
        struct.pack_into(">H", trame, 30, 0xFFFF)
        assert c._decoder_trame(bytes(trame)) is None

    def test_fermeture(self):
        c = CapteurPMS5003("/dev/null", 9600, mode_simulation=True)
        c.fermer()


class TestGestionnaire:
    def test_trois_capteurs_actifs(self):
        g = GestionnaireCapteurs()
        assert len(g.capteurs) == 3

    def test_huit_mesures_par_cycle(self):
        g = GestionnaireCapteurs()
        assert g.lire_tous()["nb_mesures"] == 8

    def test_sentinel_id_present(self):
        g = GestionnaireCapteurs()
        assert g.lire_tous()["sentinel_id"] == "test-sentinelle-001"

    def test_tous_types_presents(self):
        g = GestionnaireCapteurs()
        types = {m["type"] for m in g.lire_tous()["mesures"]}
        assert types == {
            "temperature", "humidite",
            "pression", "temperature_bme", "humidite_bme",
            "pm1_0", "pm2_5", "pm10",
        }

    def test_dix_cycles_consecutifs(self):
        g = GestionnaireCapteurs()
        for _ in range(10):
            assert g.lire_tous()["nb_mesures"] == 8

    def test_structure_cycle(self):
        g = GestionnaireCapteurs()
        c = g.lire_tous()
        assert all(k in c for k in ["sentinel_id", "horodatage", "mesures", "nb_mesures"])

    def test_fermer_tous(self):
        g = GestionnaireCapteurs()
        g.fermer_tous()
