# IoT-Sentinelle

Système de collecte de données environnementales sécurisé, fonctionnant selon le paradigme **DTN** (*Delay-Tolerant Networking*) : **Store → Carry → Forward**.

---

## Sommaire

1. [Vue d'ensemble](#vue-densemble)
2. [Architecture](#architecture)
3. [Application Raspberry Pi (`raspi_app`)](#application-raspberry-pi-raspi_app)
   - [Prérequis et installation](#prérequis-et-installation)
   - [Configuration](#configuration)
   - [Lancement](#lancement)
4. [Application mobile (`mobile_app`)](#application-mobile-mobile_app)
   - [Prérequis et installation](#prérequis-et-installation-1)
   - [Build (obligatoire)](#build-obligatoire)
   - [Lancement](#lancement-1)
5. [Protocole BLE GATT](#protocole-ble-gatt)
   - [Service et caractéristiques](#service-et-caractéristiques)
   - [Protocole de chunking](#protocole-de-chunking)
6. [Sécurité](#sécurité)
7. [Tests](#tests)
8. [Structure du projet](#structure-du-projet)

---

## Vue d'ensemble

Une **sentinelle** (Raspberry Pi) est déployée dans une zone sans connectivité Internet. Elle mesure en continu la qualité de l'air et les conditions météo, chiffre et signe chaque relevé, puis les stocke localement.

Lorsqu'un agent (smartphone) passe à proximité, l'application **mule** se connecte à la sentinelle via BLE, récupère les données chiffrées, les acquitte, puis les transmet au serveur MQTT (neOCampus) dès qu'il retrouve du réseau.

```
[Sentinelle Pi]  --BLE-->  [Smartphone mule]  --MQTT/Wi-Fi-->  [Serveur neOCampus]
   capteurs                  app mobile                          broker MQTT
   SQLite                    store & carry                       stockage central
```

---

## Architecture

```
iot-sentinelle/
├── raspi_app/                  # Firmware Python – Raspberry Pi
│   ├── main.py                 # Point d'entrée : boucle principale
│   ├── config.py               # Toute la configuration (UUIDs, broches, intervalles…)
│   ├── capteurs/
│   │   ├── dht22.py            # Température + humidité (GPIO one-wire)
│   │   ├── bme280.py           # Pression + temp + humidité (I2C)
│   │   ├── pms5003.py          # Particules PM1.0/PM2.5/PM10 (UART)
│   │   └── gestionnaire.py     # Orchestrateur des 3 capteurs
│   ├── securite/
│   │   ├── cles.py             # Génération/chargement des clés AES-256 et ECDSA P-256
│   │   ├── chiffrement.py      # Chiffrement AES-256-CBC
│   │   └── signature.py        # Signature ECDSA (SHA-256)
│   ├── stockage/
│   │   └── base_locale.py      # SQLite thread-safe (WAL + verrou)
│   ├── communication/
│   │   └── ble_serveur.py      # Serveur BLE GATT (BlueZ/D-Bus) + chunking
│   ├── energie/
│   │   └── gestionnaire.py     # Veille CPU, adaptation intervalle selon batterie
│   ├── utils/
│   │   └── qrcode_gen.py       # Génération du QR code de déploiement
│   ├── tests/                  # 185 tests pytest (100 % de réussite)
│   └── requirements.txt
│
└── mobile_app/                 # Application React Native / Expo
    ├── App.tsx                 # Application mule complète (5 phases)
    ├── index.ts                # Point d'entrée + polyfill Buffer
    ├── app.json                # Config Expo + permissions BLE/caméra
    ├── package.json            # Dépendances (ble-plx, mqtt, buffer…)
    └── __tests__/              # Tests Jest + snapshots
```

---

## Application Raspberry Pi (`raspi_app`)

### Prérequis et installation

- Raspberry Pi 3, 4, 5 ou Zero W avec **Raspberry Pi OS** (Bullseye ou supérieur)
- Python 3.10+
- Bluetooth activé (`sudo systemctl enable bluetooth`)
- I2C activé (`sudo raspi-config` → Interface Options → I2C)

```bash
cd raspi_app
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Pour les capteurs physiques, décommenter dans `requirements.txt` :

```
adafruit-circuitpython-dht>=4.0.0
RPi.bme280>=0.2.4
smbus2>=0.4.3
pyserial>=3.5
```

Pour le serveur BLE (D-Bus/BlueZ), installer les dépendances système :

```bash
sudo apt-get install python3-dbus python3-gi libglib2.0-dev
```

### Configuration

Tous les paramètres sont centralisés dans `config.py` :

| Paramètre | Défaut | Description |
|-----------|--------|-------------|
| `SENTINEL_ID` | `sentinelle-001` | Identifiant unique (surcharge via env `SENTINEL_ID`) |
| `MODE_SIMULATION` | `true` | Données aléatoires si pas de capteurs physiques |
| `INTERVALLE_MESURE_SECONDES` | `300` | Cycle de mesure (5 minutes) |
| `DHT22_PIN` | `4` | Broche GPIO du DHT22 |
| `BME280_I2C_ADDRESS` | `0x76` | Adresse I2C du BME280 |
| `PMS5003_SERIAL_PORT` | `/dev/ttyS0` | Port UART du PMS5003 |
| `BLE_SERVICE_UUID` | `12345678-1234-5678-1234-56789abcdef0` | UUID service GATT |
| `MAX_BUNDLES_STOCKES` | `1000` | Limite de bundles en SQLite |

### Lancement

```bash
# Mode simulation (sans capteurs physiques, pour développement)
python main.py

# Mode réel sur Raspberry Pi
SENTINEL_SIMULATION=false python main.py

# Identifiant personnalisé
SENTINEL_ID=sentinelle-042 SENTINEL_SIMULATION=false python main.py

# Générer le QR code à coller sur le boîtier (une seule fois au déploiement)
python utils/qrcode_gen.py
```

Le QR code généré (`qrcode_sentinelle-XXX.png`) contient :

```json
{
  "sentinel_id": "sentinelle-001",
  "ble_service_uuid": "12345678-1234-5678-1234-56789abcdef0",
  "ble_address": "AA:BB:CC:DD:EE:FF",
  "public_key": "-----BEGIN PUBLIC KEY-----\n..."
}
```

---

## Application mobile (`mobile_app`)

### Prérequis et installation

- Node.js 18+
- Android Studio (pour le build Android) ou Xcode (pour iOS)

```bash
cd mobile_app
npm install
```

### Build (obligatoire)

> **Important :** `react-native-ble-plx` contient du code natif.
> L'application **ne fonctionne pas dans Expo Go** — un build natif est requis.

```bash
# Android (génère un APK de développement)
npx expo run:android

# iOS
npx expo run:ios

# APK de débogage autonome
npm run apk
# → android/app/build/outputs/apk/debug/app-debug.apk
```

### Lancement

```bash
# Démarrer le serveur de développement
npm start

# Lancer les tests Jest
npm test

# Vérification TypeScript
npm run typecheck
```

### Flux de l'application (5 phases)

```
1. [Scanner QR]
   └─ Scanner le QR code apposé sur la sentinelle
      Extrait : sentinel_id, ble_service_uuid, public_key

2. [Connexion BLE]
   └─ Scan BLE des périphériques annonçant l'UUID de service
      Timeout 30 secondes
      Connexion + découverte des services GATT

3. [Téléchargement]
   └─ Lecture BUNDLE_COUNT → nombre de bundles à récupérer
      Pour chaque bundle :
        ① Écrire l'index dans BUNDLE_SELECT
        ② Lire BUNDLE_DATA en boucle (protocole chunké)
        ③ Écrire le bundle_id dans BUNDLE_ACK

4. [Transmission MQTT]
   └─ Connexion WebSocket au broker neOCampus
      Publication sur TestTopic/lora/neOCampus/<sentinel_id>
      QoS 1 (at least once), timeout 15 secondes

5. [Résultats]
   └─ Affiche : bundles récupérés, envois réussis/échoués
      Bouton "Nouvelle session" pour recommencer
```

---

## Protocole BLE GATT

### Service et caractéristiques

| Caractéristique | UUID | Opération | Description |
|-----------------|------|-----------|-------------|
| `BUNDLE_DATA` | `…abcdef1` | Read | Chunk courant du bundle sélectionné |
| `PUBLIC_KEY` | `…abcdef2` | Read | Clé publique ECDSA (PEM) |
| `SENTINEL_INFO` | `…abcdef3` | Read | `{sentinel_id, firmware, bundles_en_attente}` |
| `BUNDLE_ACK` | `…abcdef4` | Write | UUID du bundle acquitté (UTF-8) |
| `BUNDLE_COUNT` | `…abcdef5` | Read/Notify | Nombre de bundles en attente (UTF-8) |
| `BUNDLE_SELECT` | `…abcdef6` | Write | Index du bundle à lire (UTF-8) |

Préfixe commun des UUID : `12345678-1234-5678-1234-56789`

### Protocole de chunking

Les bundles chiffrés font typiquement **1 600–1 800 octets** (données AES-256 en base64 + signature ECDSA + métadonnées), soit bien au-delà de la limite BLE de 512 octets par caractéristique.

Le protocole de chunking résout cela :

**Côté sentinelle (`ble_serveur.py`) :**
1. À réception de `BUNDLE_SELECT = "N"`, le bundle N est découpé en tranches de 400 octets.
2. Chaque lecture de `BUNDLE_DATA` retourne la tranche suivante, enveloppée en JSON :

```json
{ "total": 4, "chunk": 0, "data": "<400 caractères du JSON du bundle>" }
```

**Côté mule (`App.tsx`) :**
```
WRITE  BUNDLE_SELECT = "0"          ← sélectionner le bundle 0
READ   BUNDLE_DATA → {total:4, chunk:0, data:"..."}
READ   BUNDLE_DATA → {total:4, chunk:1, data:"..."}
READ   BUNDLE_DATA → {total:4, chunk:2, data:"..."}
READ   BUNDLE_DATA → {total:4, chunk:3, data:"..."}  ← dernier (chunk == total-1)
                                                       → reconstituer le JSON complet
WRITE  BUNDLE_ACK = "<bundle_id>"   ← acquittement
```

---

## Sécurité

### Chiffrement AES-256-CBC

Chaque cycle de mesures est chiffré **dès l'acquisition** avec une clé AES-256 partagée entre la sentinelle et le serveur :

- IV aléatoire de 16 octets généré pour chaque chiffrement
- Padding PKCS7
- Les données claires ne transitent jamais en clair hors de la mémoire de la sentinelle

### Signature ECDSA P-256

Chaque bundle est signé avec la clé privée ECDSA de la sentinelle :

- Bloc signé : `IV || données_chiffrées`
- Algorithme : DSS FIPS 186-3, courbe NIST P-256 (secp256r1)
- La clé publique est diffusée via le QR code et la caractéristique `PUBLIC_KEY`
- La mule (ou le serveur) peut vérifier l'intégrité sans connaître la clé AES

### Anti-rejeu

Chaque bundle contient un nonce de 16 octets générés aléatoirement (`/dev/urandom`), permettant au serveur de détecter les doublons.

### Thread-safety

Le stockage SQLite utilise un `threading.Lock` pour sérialiser les accès entre le thread principal (écriture des bundles) et le thread BLE (lecture + acquittement).

---

## Tests

### Raspberry Pi (`raspi_app`)

```bash
cd raspi_app
python -m pytest tests/ -v
```

**185 tests — 100 % de réussite.**

| Fichier | Tests | Couverture |
|---------|-------|-----------|
| `test_capteurs.py` | 29 | DHT22, BME280, PMS5003, décodage trame UART |
| `test_securite.py` | 30 | Clés AES/ECDSA, chiffrement, signature, cas limites |
| `test_stockage.py` | 13 | SQLite CRUD, FIFO, ACK, double ACK, nettoyage |
| `test_ble_chunking.py` | 27 | Chunking BLE, reconstitution JSON, limites 512 octets |
| `test_energie.py` | 18 | Intervalles batterie, veille, gestion erreurs système |
| `test_config.py` | 37 | UUIDs (cohérence Python↔TypeScript), types, valeurs |
| `test_qrcode.py` | 11 | Génération QR, contenu JSON, fallback MAC BLE |
| `test_integration.py` | 20 | Pipeline DTN bout-en-bout + test de concurrence |

Le test `test_uuids_coherents_avec_app_tsx` détecte automatiquement toute désynchronisation entre les UUIDs de `config.py` et ceux de `App.tsx`.

### Application mobile (`mobile_app`)

```bash
cd mobile_app
npm test                    # Tous les tests
npm test -- --watch         # Mode interactif
npm test -- --updateSnapshot # Mettre à jour les snapshots
```

---

## Structure du projet

```
raspi_app/
├── main.py              ← Boucle principale DTN
├── config.py            ← Configuration centralisée
├── capteurs/            ← Acquisition des données
├── securite/            ← Cryptographie (AES + ECDSA)
├── stockage/            ← Persistance SQLite thread-safe
├── communication/       ← Serveur BLE GATT + chunking
├── energie/             ← Gestion batterie et veille CPU
├── utils/               ← Générateur de QR code
├── tests/               ← Banc de tests complet
└── requirements.txt

mobile_app/
├── App.tsx              ← Application mule (5 phases)
├── index.ts             ← Polyfill Buffer
├── app.json             ← Config Expo + permissions BLE/caméra
├── package.json         ← Dépendances
└── __tests__/           ← Tests Jest
```

---

**Auteur :** Louis Lapointe — 2026
*Développé dans le cadre d'un projet IoT sécurisé.*
