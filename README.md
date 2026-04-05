# IoT-Sentinelle

[![Build Android APK](https://github.com/LouisLapointe01/iot-sentinelle/actions/workflows/build-apk.yml/badge.svg)](https://github.com/LouisLapointe01/iot-sentinelle/actions/workflows/build-apk.yml)

**Repo :** [https://github.com/LouisLapointe01/iot-sentinelle](https://github.com/LouisLapointe01/iot-sentinelle)

Système de collecte de données environnementales sécurisé, fonctionnant selon le paradigme **DTN** (*Delay-Tolerant Networking*) : **Store → Carry → Forward**.

```
[Sentinelle Pi]  --BLE-->  [Smartphone mule]  --MQTT/Wi-Fi-->  [Broker MQTT]
   capteurs                  app mobile                          stockage central
   SQLite                    store & carry
```

---

## Sommaire

1. [Démarrage rapide (TL;DR)](#démarrage-rapide-tldr)
2. [Vue d'ensemble](#vue-densemble)
3. [Architecture](#architecture)
4. [Guide de déploiement complet](#guide-de-déploiement-complet)
5. [Application Raspberry Pi (`raspi_app`)](#application-raspberry-pi-raspi_app)
6. [Application mobile (`mobile_app`)](#application-mobile-mobile_app)
7. [Configuration MQTT](#configuration-mqtt)
8. [Protocole BLE GATT](#protocole-ble-gatt)
9. [Sécurité](#sécurité)
10. [Tests](#tests)
11. [Dépannage](#dépannage)
12. [Structure du projet](#structure-du-projet)

---

## Démarrage rapide (TL;DR)

### Sentinelle Raspberry Pi

```bash
# 1. Cloner et installer
git clone https://github.com/LouisLapointe01/iot-sentinelle.git
cd iot-sentinelle
bash bootstrap.sh --reel --id sentinelle-001

# 2. Préparer le Bluetooth (une seule fois)
sudo rfkill unblock bluetooth
sudo bluetoothctl power on
sudo bluetoothctl discoverable-timeout 0
sudo bluetoothctl discoverable on

# 3. Lancer (avec sudo pour le serveur BLE GATT)
cd raspi_app
sudo .venv/bin/python main.py
```

### Application mobile Android

Télécharger directement depuis **[GitHub Releases](../../releases/latest)** → `app-release.apk`

> L'APK est recompilé automatiquement à chaque mise à jour du code (GitHub Actions). Le bundle JavaScript est embarqué — **aucun PC ni Metro requis**.

---

## Vue d'ensemble

Une **sentinelle** (Raspberry Pi) est déployée dans une zone sans connectivité Internet. Elle mesure en continu la qualité de l'air et les conditions météo, chiffre et signe chaque relevé, puis les stocke localement dans SQLite.

Lorsqu'un agent (smartphone) passe à proximité, l'application **mule** se connecte à la sentinelle via BLE GATT, récupère les bundles chiffrés, les acquitte, puis les transmet au broker MQTT dès qu'elle retrouve du réseau.

---

## Architecture

```
iot-sentinelle/
├── raspi_app/                  # Firmware Python – Raspberry Pi
│   ├── main.py                 # Point d'entrée : boucle principale
│   ├── config.py               # Toute la configuration (UUIDs, broches, intervalles…)
│   ├── capteurs/               # DHT22, BME280, PMS5003
│   ├── securite/               # AES-256-CBC + ECDSA P-256
│   ├── stockage/               # SQLite thread-safe (WAL + verrou)
│   ├── communication/          # Serveur BLE GATT (BlueZ/D-Bus) + chunking
│   ├── energie/                # Veille CPU, adaptation intervalle
│   ├── utils/                  # Générateur de QR code
│   ├── tests/                  # Suite complète pytest
│   └── requirements.txt
│
└── mobile_app/                 # Application React Native / Expo
    ├── App.tsx                 # Application mule complète (5 phases)
    ├── config.ts               # Configuration centralisée (MQTT, BLE, timeouts)
    ├── index.ts                # Point d'entrée + polyfill Buffer
    ├── app.json                # Config Expo + permissions BLE/caméra
    ├── package.json            # Dépendances
    └── __tests__/              # Tests Jest + snapshots
```

---

## Guide de déploiement complet

De la carte SD vierge à la sentinelle opérationnelle.

---

### Étape 1 — Flasher la carte SD

1. Télécharge **[Raspberry Pi Imager](https://www.raspberrypi.com/software/)** sur ton PC
2. Choisis **Raspberry Pi OS Lite (64-bit)**
3. Clique sur l'icône ⚙️ **avant** de flasher et configure :
   - Hostname : `sentinelle`
   - Active **SSH**
   - Wi-Fi : ton réseau + mot de passe
   - Utilisateur : `admin` / mot de passe au choix
4. Flashe la carte SD, insère-la dans le Pi, branche l'alimentation

---

### Étape 2 — Se connecter en SSH

Depuis ton PC (attends ~1 min que le Pi démarre) :

```bash
ssh admin@sentinelle.local
```

Si `sentinelle.local` ne répond pas, trouve l'IP dans ton routeur :

```bash
# Sur le Raspi
hostname -I
# Exemple : 192.168.1.56

# Depuis le PC
ssh admin@192.168.1.56
```

---

### Étape 3 — Récupérer le projet

```bash
sudo apt-get update && sudo apt-get install -y git
git clone https://github.com/LouisLapointe01/iot-sentinelle.git
cd iot-sentinelle
```

---

### Étape 4 — Installer les dépendances système BLE

> **Critique :** ces paquets doivent être installés via `apt` **avant** de créer le venv.

```bash
sudo apt install -y python3-dbus python3-gi libglib2.0-dev bluetooth bluez
```

---

### Étape 5 — Installer la sentinelle

```bash
bash bootstrap.sh --reel --id sentinelle-001
```

Ce script fait **tout automatiquement** :
- Vérifie Python 3.10+
- Crée le venv avec `--system-site-packages` (indispensable pour les libs BLE système)
- Installe toutes les dépendances pip
- Génère les clés AES-256 et ECDSA P-256
- Génère le QR code de déploiement

| Commande | Description |
|----------|-------------|
| `bash bootstrap.sh --reel` | Mode réel (Raspberry Pi + capteurs) |
| `bash bootstrap.sh --id sentinelle-042` | Identifiant personnalisé |
| `bash bootstrap.sh` | Mode simulation (sans capteurs) |
| `bash bootstrap.sh --lancer` | Installer et lancer immédiatement |

---

### Étape 6 — Activer et configurer le Bluetooth

```bash
# Débloquer le Bluetooth (si bloqué par rfkill)
sudo rfkill unblock bluetooth

# Activer le service Bluetooth
sudo systemctl enable bluetooth
sudo systemctl start bluetooth

# Allumer et rendre découvrable en permanence
sudo bluetoothctl power on
sudo bluetoothctl discoverable-timeout 0
sudo bluetoothctl discoverable on
sudo bluetoothctl pairable on
```

> Pour vérifier l'état : `sudo bluetoothctl show | grep -E "Powered|Discoverable"`

---

### Étape 7 — (Optionnel) Broker MQTT local pour tests à domicile

Par défaut, la mule envoie les données au broker neOCampus (réseau université). Pour tester chez soi, installer Mosquitto sur le Raspi :

```bash
sudo apt install -y mosquitto mosquitto-clients
echo -e "listener 9001\nprotocol websockets\nallow_anonymous true" | sudo tee /etc/mosquitto/conf.d/local.conf
sudo systemctl enable mosquitto
sudo systemctl restart mosquitto
```

Puis modifier `mobile_app/config.ts` :

```ts
export const MQTT_BROKER_WS = 'ws://192.168.1.XX:9001'; // IP du Raspi
export const MQTT_USERNAME  = '';
export const MQTT_PASSWORD  = '';
```

Pour vérifier que Mosquitto fonctionne :

```bash
# Terminal 1 — abonné
mosquitto_sub -h localhost -p 1883 -t "TestTopic/#"

# Terminal 2 — publier un message test
mosquitto_pub -h localhost -p 1883 -t "TestTopic/test" -m "hello"
```

---

### Étape 8 — Lancer la sentinelle

```bash
cd ~/iot-sentinelle/raspi_app
source .venv/bin/activate

# Lancer en arrière-plan (recommandé)
sudo .venv/bin/python main.py > raspi.log 2>&1 &

# Suivre les logs
tail -f raspi.log
```

> **Important :** le serveur BLE GATT nécessite `sudo` pour accéder à BlueZ via D-Bus.

Sortie attendue :

```
[INFO] SENTINELLE DTN -- sentinelle-001
[INFO] Firmware v1.0.0
[INFO] Boucle principale démarrée. Ctrl+C pour arrêter.
[INFO] Adaptateur Bluetooth : /org/bluez/hci0
[INFO] Application GATT enregistrée
[INFO] Advertisement BLE : Sentinelle-sentinelle-001
```

Pour arrêter proprement :

```bash
sudo pkill -f main.py
```

---

### Étape 9 — Récupérer le QR code

Le QR code est généré dans `raspi_app/` au format PNG. Pour le transférer sur ton PC :

```bash
# Depuis ton PC Windows
scp admin@192.168.1.XX:~/iot-sentinelle/raspi_app/qrcode_test-sentinelle-001.png C:\Users\<toi>\Desktop\
```

Imprime-le ou colle-le sur le boîtier. L'application mobile le scannera pour se connecter en BLE.

---

### Étape 10 — Installer l'application mobile Android

**Option A — APK prêt à l'emploi (recommandé) :**

1. Aller sur **[GitHub Releases](https://github.com/LouisLapointe01/iot-sentinelle/releases/latest)**
2. Télécharger `app-release.apk`
3. L'installer sur Android (activer "Sources inconnues" si demandé)

> Sur **GrapheneOS** : Paramètres → Applications → [navigateur] → Installer des apps inconnues → Autoriser

**Option B — Compiler localement :**

```bash
cd mobile_app
npm install       # Node.js 20+ requis
npm run apk       # Build release avec JS embarqué
# → android/app/build/outputs/apk/release/app-release.apk
```

---

### Récapitulatif des commandes

```bash
# Installation (une seule fois)
sudo apt install -y python3-dbus python3-gi libglib2.0-dev bluetooth bluez
bash bootstrap.sh --reel --id sentinelle-001

# Bluetooth (une seule fois, ou après redémarrage)
sudo rfkill unblock bluetooth && sudo bluetoothctl power on
sudo bluetoothctl discoverable-timeout 0 && sudo bluetoothctl discoverable on

# Lancer la sentinelle
cd raspi_app && sudo .venv/bin/python main.py > raspi.log 2>&1 &

# Vérifier les logs
tail -f ~/iot-sentinelle/raspi_app/raspi.log

# Tests
bash run.sh --test
```

---

## Application Raspberry Pi (`raspi_app`)

### Prérequis

- Raspberry Pi 3, 4, 5 ou Zero W avec **Raspberry Pi OS Bookworm** (64-bit recommandé)
- Python 3.10+
- Bluetooth activé
- I2C activé (`sudo raspi-config` → Interface Options → I2C) — pour le BME280

### Installation manuelle (si bootstrap.sh non utilisé)

```bash
# 1. Dépendances système BLE (obligatoire avant le venv)
sudo apt install -y python3-dbus python3-gi libglib2.0-dev bluetooth bluez

# 2. Venv avec accès aux paquets système
cd raspi_app
python3 -m venv .venv --system-site-packages
source .venv/bin/activate

# 3. Dépendances pip
pip install -r requirements.txt
```

> **Ne pas** créer le venv sans `--system-site-packages` — les libs `dbus` et `gi` installées via `apt` ne seraient pas accessibles et le serveur BLE tournerait en mode simulation.

### Configuration

Tous les paramètres sont centralisés dans `config.py` :

| Paramètre | Défaut | Description |
|-----------|--------|-------------|
| `SENTINEL_ID` | `sentinelle-001` | Identifiant unique (surcharge via `SENTINEL_ID=xxx`) |
| `MODE_SIMULATION` | `true` | Données simulées si pas de capteurs physiques |
| `INTERVALLE_MESURE_SECONDES` | `300` | Cycle de mesure (5 minutes) |
| `DHT22_PIN` | `4` | Broche GPIO du DHT22 |
| `BME280_I2C_ADDRESS` | `0x76` | Adresse I2C du BME280 |
| `PMS5003_SERIAL_PORT` | `/dev/ttyS0` | Port UART du PMS5003 |
| `BLE_SERVICE_UUID` | `12345678-1234-5678-1234-56789abcdef0` | UUID service GATT |
| `MAX_BUNDLES_STOCKES` | `1000` | Limite de bundles en SQLite |

### Lancement

```bash
# Mode simulation (sans capteurs physiques)
sudo .venv/bin/python main.py

# Mode réel sur Raspberry Pi
sudo SENTINEL_SIMULATION=false .venv/bin/python main.py

# Identifiant personnalisé
sudo SENTINEL_ID=sentinelle-042 SENTINEL_SIMULATION=false .venv/bin/python main.py

# Générer le QR code (une seule fois au déploiement)
.venv/bin/python utils/qrcode_gen.py
```

Le QR code contient :

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

### Prérequis

- Android 8.0+ (testé sur GrapheneOS)
- Bluetooth et Localisation activés
- Permissions : Bluetooth, Caméra, Localisation (requises par Android pour scanner BLE)

### Configuration (`config.ts`)

Toutes les constantes sont centralisées dans `mobile_app/config.ts`. **Modifier ce fichier** pour changer les paramètres sans toucher à la logique de l'app :

```ts
// Broker MQTT — réseau université
export const MQTT_BROKER_WS    = 'ws://neocampus.univ-tlse3.fr:9001';

// Broker MQTT — tests à domicile (Mosquitto local sur le Raspi)
// export const MQTT_BROKER_WS = 'ws://192.168.1.56:9001';

export const MQTT_USERNAME     = 'test';
export const MQTT_PASSWORD     = 'test';
export const MQTT_TOPIC_PREFIX = 'TestTopic/lora/neOCampus';

// Timeouts
export const BLE_SCAN_TIMEOUT_MS     = 30_000;  // 30s pour trouver la sentinelle
export const BLE_CHUNK_TIMEOUT_MS    = 10_000;  // 10s par chunk BLE
export const MQTT_CONNECT_TIMEOUT_MS = 15_000;  // 15s pour le broker MQTT
```

### Build

> **Important :** `react-native-ble-plx` contient du code natif — l'app **ne fonctionne pas dans Expo Go**.

```bash
cd mobile_app
npm install              # Node.js 20+ requis

npm run apk              # APK release (JS embarqué, autonome)
npm run apk:debug        # APK debug (nécessite Metro)
npm run typecheck        # Vérification TypeScript
npm test                 # Tests Jest
```

### Flux de l'application (5 phases)

```
1. [Scanner QR]
   └─ Scanner le QR code apposé sur la sentinelle
      Extrait : sentinel_id, ble_service_uuid, public_key

2. [Connexion BLE]
   └─ Scan BLE des périphériques annonçant l'UUID de service (timeout 30s)
      Connexion GATT + découverte des services

3. [Téléchargement]
   └─ Lecture BUNDLE_COUNT → nombre de bundles à récupérer
      Pour chaque bundle :
        ① Écrire l'index dans BUNDLE_SELECT
        ② Lire BUNDLE_DATA en boucle (protocole chunké, timeout 10s/chunk)
        ③ Écrire le bundle_id dans BUNDLE_ACK
      Barre de progression visuelle (%)

4. [Transmission MQTT]
   └─ Connexion WebSocket au broker MQTT (timeout 15s)
      Publication sur TestTopic/lora/neOCampus/<sentinel_id> (QoS 1)

5. [Résultats]
   └─ Bundles récupérés / envois réussis / échecs
      Bouton "Nouvelle session"
```

---

## Configuration MQTT

| Environnement | Broker | Port | Notes |
|---------------|--------|------|-------|
| Université (neOCampus) | `neocampus.univ-tlse3.fr` | `9001` (WS) | Réseau campus ou VPN requis |
| Domicile (Mosquitto local) | IP du Raspi (`192.168.1.XX`) | `9001` (WS) | Installer Mosquitto sur le Raspi |
| Public (test) | `broker.hivemq.com` | `8000` (WS) | Sans authentification |

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

Les bundles font ~1 600–1 800 octets, au-delà de la limite BLE de 512 octets. Le chunking résout cela :

```
WRITE  BUNDLE_SELECT = "0"
READ   BUNDLE_DATA → {"total":4, "chunk":0, "data":"..."}
READ   BUNDLE_DATA → {"total":4, "chunk":1, "data":"..."}
READ   BUNDLE_DATA → {"total":4, "chunk":2, "data":"..."}
READ   BUNDLE_DATA → {"total":4, "chunk":3, "data":"..."}  ← reconstituer le JSON
WRITE  BUNDLE_ACK  = "<bundle_id>"
```

---

## Sécurité

### Chiffrement AES-256-CBC

- IV aléatoire de 16 octets généré pour chaque chiffrement
- Padding PKCS7
- Les données claires ne transitent jamais hors de la mémoire de la sentinelle

### Signature ECDSA P-256

- Bloc signé : `IV || données_chiffrées`
- Algorithme : DSS FIPS 186-3, courbe NIST P-256 (secp256r1)
- La clé publique est diffusée via le QR code et la caractéristique `PUBLIC_KEY`

### Anti-rejeu

Chaque bundle contient un nonce de 16 octets aléatoires (`/dev/urandom`) pour détecter les doublons côté serveur.

---

## Tests

### Raspberry Pi (`raspi_app`)

```bash
cd raspi_app
source .venv/bin/activate
python -m pytest tests/ -v
# ou
bash run.sh --test
```

| Fichier | Tests | Couverture |
|---------|-------|-----------|
| `test_capteurs.py` | 29 | DHT22, BME280, PMS5003 |
| `test_securite.py` | 30 | Clés AES/ECDSA, chiffrement, signature |
| `test_stockage.py` | 13 | SQLite CRUD, FIFO, ACK |
| `test_ble_chunking.py` | 27 | Chunking BLE, reconstitution JSON |
| `test_energie.py` | 18 | Intervalles batterie, veille |
| `test_config.py` | 37 | UUIDs (cohérence Python↔TypeScript), types |
| `test_qrcode.py` | 11 | Génération QR, contenu JSON |
| `test_integration.py` | 20 | Pipeline DTN bout-en-bout |
| `test_installer.py` | 36 | Installation automatique |
| `test_setup_integration.py` | 31 | Setup depuis zéro, idempotence |
| `test_main_loop.py` | 23 | Boucle principale, signaux, arrêt propre |
| `test_fonctionnement_global.py` | 35 | Pipeline DTN complet, BLE, concurrence |
| `test_scenario_complet.py` | — | Scénario DTN bout-en-bout sans hardware |

> Le test `test_uuids_coherents_avec_app_tsx` vérifie automatiquement la synchronisation des UUIDs entre `config.py` et `config.ts`.

### Application mobile (`mobile_app`)

```bash
cd mobile_app
npm test                     # Tous les tests Jest
npm test -- --watch          # Mode interactif
npm test -- --updateSnapshot # Mettre à jour les snapshots
```

---

## Dépannage

### "Unable to load script" au démarrage de l'app

L'APK installé est une ancienne version qui nécessite Metro. **Solution :** télécharger et réinstaller `app-release.apk` depuis [GitHub Releases](../../releases/latest).

### "Aucune sentinelle trouvée en 30s"

1. Vérifier que `main.py` tourne sur le Raspi : `ps aux | grep main.py`
2. Vérifier que le Bluetooth est actif : `sudo bluetoothctl show | grep Powered`
3. Si `Powered: no` → `sudo rfkill unblock bluetooth && sudo bluetoothctl power on`
4. Vérifier que l'app a les permissions **Bluetooth + Localisation** sur Android
5. S'assurer que `main.py` est lancé avec `sudo`

### "Erreur connexion : operation was cancelled"

1. Le serveur BLE tourne-t-il avec `sudo` ? (requis pour D-Bus/BlueZ)
2. Redémarrer bluetoothd : `sudo systemctl restart bluetooth`
3. Relancer `main.py` après le redémarrage bluetooth

### Le serveur BLE tourne en mode simulation

```
[INFO] ServeurBLE : démarrage ignoré (mode simulation)
```

Cause : les libs `dbus`/`gi` ne sont pas accessibles depuis le venv.

**Solution :** recréer le venv avec `--system-site-packages` :

```bash
deactivate
rm -rf .venv
python3 -m venv .venv --system-site-packages
source .venv/bin/activate
pip install -r requirements.txt
```

### Timeout MQTT — bundles non transmis

- **Sur réseau université :** connecter le téléphone au Wi-Fi campus ou via VPN
- **À domicile :** installer Mosquitto sur le Raspi (voir [Étape 7](#étape-7--optionnel-broker-mqtt-local-pour-tests-à-domicile))

### `pip` / `pip3` introuvable

```bash
sudo apt install -y python3-pip
# ou via venv :
python3 -m venv .venv --system-site-packages
source .venv/bin/activate
pip install -r requirements.txt
```

---

## Structure du projet

```
iot-sentinelle/
├── .github/workflows/
│   └── build-apk.yml        ← CI : build APK release à chaque push sur main
├── raspi_app/
│   ├── main.py              ← Boucle principale DTN
│   ├── config.py            ← Configuration centralisée
│   ├── capteurs/            ← Acquisition des données
│   ├── securite/            ← Cryptographie (AES + ECDSA)
│   ├── stockage/            ← Persistance SQLite thread-safe
│   ├── communication/       ← Serveur BLE GATT + chunking
│   ├── energie/             ← Gestion batterie et veille CPU
│   ├── utils/               ← Générateur de QR code
│   ├── tests/               ← Banc de tests complet
│   └── requirements.txt
├── mobile_app/
│   ├── App.tsx              ← Application mule (5 phases)
│   ├── config.ts            ← Configuration centralisée (MQTT, BLE, timeouts)
│   ├── index.ts             ← Polyfill Buffer
│   ├── app.json             ← Config Expo + permissions BLE/caméra
│   ├── package.json         ← Dépendances (Node.js 20+ requis)
│   └── __tests__/           ← Tests Jest
├── bootstrap.sh             ← Installation complète en une commande
├── run.sh                   ← Lancer la sentinelle ou les tests
└── Makefile                 ← Alias make bootstrap / make run / make test
```

---

## Contributeurs

| Nom | Rôle |
|-----|------|
| Thomas Collet | Développement |
| Louis Lapointe | Développement |
| Oussama Guelagli | Développement |
| Bastien Cabanie | Développement |

*Développé dans le cadre d'un projet IoT sécurisé — 2026.*
