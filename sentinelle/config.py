"""
config.py -- Configuration globale de la sentinelle DTN.

Ici, on centralise tous les parametres de la sentinelle dans un seul fichier,
car cela permet de modifier les reglages (intervalle de mesure, broches GPIO,
parametres BLE, etc.) sans toucher au code metier. C'est une bonne pratique
pour un projet modulaire : chaque module importe ses parametres depuis ce fichier.
"""

import os

# =============================================================================
# IDENTITE DE LA SENTINELLE
# =============================================================================
# Ici, on definit un identifiant unique pour chaque sentinelle deployee.
# Cet identifiant est utilise dans les bundles DTN, le QR code et le topic MQTT.
# En production, chaque Raspberry Pi aura un ID different.
SENTINEL_ID = os.environ.get("SENTINEL_ID", "sentinelle-001")

# Version du firmware, utile pour le suivi et le debogage a distance.
FIRMWARE_VERSION = "1.0.0"

# =============================================================================
# CONFIGURATION DES CAPTEURS
# =============================================================================
# Ici, on specifie les broches GPIO et bus utilises par chaque capteur,
# car le Raspberry Pi utilise des interfaces physiques specifiques (GPIO, I2C, UART).

# DHT22 : capteur de temperature et d'humidite, connecte sur un pin GPIO.
DHT22_PIN = 4  # GPIO 4 (pin physique 7)

# BME280 : capteur de pression atmospherique, connecte via le bus I2C.
BME280_I2C_ADDRESS = 0x76  # Adresse I2C par defaut du BME280
BME280_I2C_BUS = 1         # Bus I2C n-1 sur Raspberry Pi 3/4

# PMS5003 : capteur de particules fines, connecte via le port serie UART.
PMS5003_SERIAL_PORT = "/dev/ttyS0"  # Port serie materiel du Raspberry Pi
PMS5003_BAUD_RATE = 9600            # Debit serie impose par le PMS5003

# =============================================================================
# INTERVALLES DE MESURE
# =============================================================================
# Ici, on definit la periodicite d'acquisition des mesures (en secondes).
# Le CDC preconise une mesure toutes les 5 minutes (300 secondes).
INTERVALLE_MESURE_SECONDES = 300  # 5 minutes

# =============================================================================
# SECURITE -- CHIFFREMENT ET SIGNATURE
# =============================================================================
# Ici, on definit les parametres cryptographiques conformement au CDC :
# - AES-256-CBC pour le chiffrement symetrique des donnees
# - ECDSA (courbe P-256) pour la signature numerique

# Repertoire de stockage des cles cryptographiques sur la sentinelle.
REPERTOIRE_CLES = os.path.join(os.path.dirname(__file__), "cles")

# Fichiers de cles ECDSA (paire publique/privee de la sentinelle).
FICHIER_CLE_PRIVEE = os.path.join(REPERTOIRE_CLES, "cle_privee.pem")
FICHIER_CLE_PUBLIQUE = os.path.join(REPERTOIRE_CLES, "cle_publique.pem")

# Fichier de la cle symetrique AES-256 (32 octets = 256 bits).
FICHIER_CLE_AES = os.path.join(REPERTOIRE_CLES, "cle_aes.bin")

# Taille de la cle AES en octets (256 bits = 32 octets).
TAILLE_CLE_AES = 32

# Taille du bloc AES en octets (toujours 16 pour AES).
TAILLE_BLOC_AES = 16

# =============================================================================
# BLUETOOTH LOW ENERGY (BLE)
# =============================================================================
# Ici, on definit les UUIDs du service GATT et de ses caracteristiques.
# Ces UUIDs sont des identifiants uniques qui permettent a l'application mobile
# de reconnaitre et d'interagir avec le bon service BLE de la sentinelle.

# UUID du service GATT personnalise de la sentinelle DTN.
BLE_SERVICE_UUID = "12345678-1234-5678-1234-56789abcdef0"

# UUID de la caracteristique contenant les donnees du bundle chiffre (Read/Notify).
BLE_CHAR_BUNDLE_DATA_UUID = "12345678-1234-5678-1234-56789abcdef1"

# UUID de la caracteristique contenant la cle publique ECDSA (Read).
BLE_CHAR_PUBLIC_KEY_UUID = "12345678-1234-5678-1234-56789abcdef2"

# UUID de la caracteristique contenant les infos de la sentinelle (Read).
BLE_CHAR_SENTINEL_INFO_UUID = "12345678-1234-5678-1234-56789abcdef3"

# UUID de la caracteristique d'acquittement des bundles (Write).
BLE_CHAR_BUNDLE_ACK_UUID = "12345678-1234-5678-1234-56789abcdef4"

# UUID de la caracteristique indiquant le nombre de bundles en attente (Read/Notify).
BLE_CHAR_BUNDLE_COUNT_UUID = "12345678-1234-5678-1234-56789abcdef5"

# UUID de la caracteristique de selection de bundle par index (Write).
BLE_CHAR_BUNDLE_SELECT_UUID = "12345678-1234-5678-1234-56789abcdef6"

# Nom BLE diffuse par la sentinelle (visible lors du scan BLE).
BLE_DEVICE_NAME = f"Sentinelle-{SENTINEL_ID}"

# =============================================================================
# STOCKAGE LOCAL (SQLite)
# =============================================================================
# Ici, on definit le chemin vers la base de donnees SQLite locale.
# Cette base stocke les bundles chiffres en attendant qu'une mule les recupere.
FICHIER_BASE_DONNEES = os.path.join(os.path.dirname(__file__), "donnees", "sentinelle.db")

# Nombre maximum de bundles conserves localement.
MAX_BUNDLES_STOCKES = 1000

# =============================================================================
# MQTT / neOCampus (reference)
# =============================================================================
# Ici, on stocke les parametres MQTT du broker neOCampus.
# Note : c'est l'application mobile (mule) qui publie vers MQTT, pas la sentinelle.
MQTT_BROKER = "neocampus.univ-tlse3.fr"
MQTT_PORT = 1882
MQTT_USERNAME = "test"
MQTT_PASSWORD = "test"
MQTT_TOPIC_PREFIX = "TestTopic/lora/neOCampus"

# =============================================================================
# MODE SIMULATION
# =============================================================================
# Ici, on active un mode simulation pour le developpement sur un PC sans capteurs.
# En mode simulation, les capteurs renvoient des valeurs aleatoires realistes.
MODE_SIMULATION = os.environ.get("SENTINEL_SIMULATION", "true").lower() == "true"

# =============================================================================
# JOURNALISATION (Logging)
# =============================================================================
NIVEAU_LOG = os.environ.get("SENTINEL_LOG_LEVEL", "INFO")
