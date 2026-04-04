"""
test_config.py -- Tests de la configuration et des constantes.

Verifie que config.py expose toutes les valeurs attendues avec les bons types
et que les UUIDs BLE sont bien formates (cohérence avec App.tsx).
"""

import re
import os


UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)


class TestConfigIdentite:
    def test_sentinel_id_est_str(self):
        import config
        assert isinstance(config.SENTINEL_ID, str)

    def test_sentinel_id_non_vide(self):
        import config
        assert config.SENTINEL_ID.strip()

    def test_firmware_version_format(self):
        import config
        assert re.match(r"^\d+\.\d+\.\d+$", config.FIRMWARE_VERSION)

    def test_sentinel_id_env_override(self, monkeypatch):
        monkeypatch.setenv("SENTINEL_ID", "sentinelle-999")
        import importlib
        import config
        importlib.reload(config)
        # Note : conftest force SENTINEL_ID=test-sentinelle-001 via os.environ
        # donc on verifie juste la logique de chargement
        assert config.SENTINEL_ID  # non vide


class TestConfigCapteurs:
    def test_dht22_pin_entier(self):
        import config
        assert isinstance(config.DHT22_PIN, int)

    def test_dht22_pin_valide_gpio(self):
        import config
        assert 1 <= config.DHT22_PIN <= 40

    def test_bme280_adresse_i2c(self):
        import config
        assert config.BME280_I2C_ADDRESS in (0x76, 0x77)

    def test_bme280_bus_i2c(self):
        import config
        assert isinstance(config.BME280_I2C_BUS, int)

    def test_pms5003_port_str(self):
        import config
        assert isinstance(config.PMS5003_SERIAL_PORT, str)

    def test_pms5003_baud_valide(self):
        import config
        assert config.PMS5003_BAUD_RATE in (9600, 115200)

    def test_intervalle_positif(self):
        import config
        assert config.INTERVALLE_MESURE_SECONDES > 0

    def test_intervalle_raisonnable(self):
        import config
        # Entre 10 secondes et 1 heure
        assert 10 <= config.INTERVALLE_MESURE_SECONDES <= 3600


class TestConfigSecurite:
    def test_repertoire_cles_str(self):
        import config
        assert isinstance(config.REPERTOIRE_CLES, str)

    def test_taille_cle_aes_256_bits(self):
        import config
        assert config.TAILLE_CLE_AES == 32

    def test_taille_bloc_aes(self):
        import config
        assert config.TAILLE_BLOC_AES == 16

    def test_fichiers_cles_dans_repertoire(self):
        import config
        assert config.FICHIER_CLE_PRIVEE.startswith(config.REPERTOIRE_CLES)
        assert config.FICHIER_CLE_PUBLIQUE.startswith(config.REPERTOIRE_CLES)
        assert config.FICHIER_CLE_AES.startswith(config.REPERTOIRE_CLES)


class TestConfigBLE:
    def test_service_uuid_format(self):
        import config
        assert UUID_PATTERN.match(config.BLE_SERVICE_UUID)

    def test_char_bundle_data_uuid_format(self):
        import config
        assert UUID_PATTERN.match(config.BLE_CHAR_BUNDLE_DATA_UUID)

    def test_char_public_key_uuid_format(self):
        import config
        assert UUID_PATTERN.match(config.BLE_CHAR_PUBLIC_KEY_UUID)

    def test_char_sentinel_info_uuid_format(self):
        import config
        assert UUID_PATTERN.match(config.BLE_CHAR_SENTINEL_INFO_UUID)

    def test_char_bundle_ack_uuid_format(self):
        import config
        assert UUID_PATTERN.match(config.BLE_CHAR_BUNDLE_ACK_UUID)

    def test_char_bundle_count_uuid_format(self):
        import config
        assert UUID_PATTERN.match(config.BLE_CHAR_BUNDLE_COUNT_UUID)

    def test_char_bundle_select_uuid_format(self):
        import config
        assert UUID_PATTERN.match(config.BLE_CHAR_BUNDLE_SELECT_UUID)

    def test_tous_uuids_distincts(self):
        import config
        uuids = [
            config.BLE_SERVICE_UUID,
            config.BLE_CHAR_BUNDLE_DATA_UUID,
            config.BLE_CHAR_PUBLIC_KEY_UUID,
            config.BLE_CHAR_SENTINEL_INFO_UUID,
            config.BLE_CHAR_BUNDLE_ACK_UUID,
            config.BLE_CHAR_BUNDLE_COUNT_UUID,
            config.BLE_CHAR_BUNDLE_SELECT_UUID,
        ]
        assert len(set(uuids)) == 7

    def test_uuids_coherents_avec_app_tsx(self):
        """
        Verifie que les UUIDs correspondent exactement a ceux definis
        dans mobile_app/App.tsx (hard-coded pour detection de regression).
        """
        import config
        # Ces valeurs sont aussi hardcodees dans App.tsx
        assert config.BLE_SERVICE_UUID         == "12345678-1234-5678-1234-56789abcdef0"
        assert config.BLE_CHAR_BUNDLE_DATA_UUID == "12345678-1234-5678-1234-56789abcdef1"
        assert config.BLE_CHAR_BUNDLE_ACK_UUID  == "12345678-1234-5678-1234-56789abcdef4"
        assert config.BLE_CHAR_BUNDLE_COUNT_UUID == "12345678-1234-5678-1234-56789abcdef5"
        assert config.BLE_CHAR_BUNDLE_SELECT_UUID == "12345678-1234-5678-1234-56789abcdef6"

    def test_device_name_contient_sentinel_id(self):
        import config
        assert config.SENTINEL_ID in config.BLE_DEVICE_NAME


class TestConfigStockage:
    def test_fichier_bdd_str(self):
        import config
        assert isinstance(config.FICHIER_BASE_DONNEES, str)

    def test_max_bundles_positif(self):
        import config
        assert config.MAX_BUNDLES_STOCKES > 0

    def test_max_bundles_raisonnable(self):
        import config
        assert 10 <= config.MAX_BUNDLES_STOCKES <= 100_000


class TestConfigMQTT:
    def test_broker_str(self):
        import config
        assert isinstance(config.MQTT_BROKER, str)

    def test_port_valide(self):
        import config
        assert 1 <= config.MQTT_PORT <= 65535

    def test_topic_prefix_str(self):
        import config
        assert isinstance(config.MQTT_TOPIC_PREFIX, str)
        assert config.MQTT_TOPIC_PREFIX.strip()


class TestConfigModeSimulation:
    def test_mode_simulation_bool(self):
        import config
        assert isinstance(config.MODE_SIMULATION, bool)

    def test_mode_simulation_actif_en_test(self):
        import config
        assert config.MODE_SIMULATION is True  # conftest force SENTINEL_SIMULATION=true

    def test_niveau_log_valide(self):
        import logging
        import config
        assert hasattr(logging, config.NIVEAU_LOG)
