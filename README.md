# IoT-Sentinelle : Solution de Monitoring Environnemental Sécurisée

[![Version](https://img.shields.io/badge/version-1.0.0-blue.svg)](https://github.com/LouisLapointe01/iot-sentinelle)
[![Python](https://img.shields.io/badge/Python-3.10%2B-green.svg)](https://www.python.org/)
[![React Native](https://img.shields.io/badge/React%20Native-Expo-61dafb.svg)](https://reactnative.dev/)

**IoT-Sentinelle** est un système complet de collecte, de sécurisation et de transmission de données environnementales. Le projet est conçu pour fonctionner sur Raspberry Pi (la "Sentinelle") et permet la récupération des données via une application mobile dédiée en utilisant le paradigme **DTN** (*Delay-Tolerant Networking*) : Store, Carry and Forward.

---

## 📑 Sommaire

1. [🚀 Introduction](#-introduction)
2. [📂 Structure du projet](#-structure-du-projet)
3. [🍓 Application Raspberry Pi (raspi_app)](#-application-raspberry-pi-raspi_app)
    - [Installation](#installation-raspi)
    - [Utilisation](#utilisation-raspi)
4. [📱 Application Mobile (mobile_app)](#-application-mobile-mobile_app)
    - [Installation](#installation-mobile)
    - [Utilisation](#utilisation-mobile)
5. [💎 Profondeur & Fonctionnalités](#-profondeur--fonctionnalités)
6. [👤 Auteur](#-auteur)

---

## 🚀 Introduction

Le projet **IoT-Sentinelle** répond au besoin de collecter des données dans des zones sans connectivité internet permanente. La sentinelle (Raspberry Pi) capte les données, les chiffre et les signe localement, puis attend qu'un smartphone à proximité (la "mule") les récupère via Bluetooth Low Energy (BLE) pour les transmettre ultérieurement.

---

## 📂 Structure du projet

Le dépôt est organisé en deux piliers principaux :

```text
iot-sentinelle/
├── raspi_app/          # Firmware Python pour le Raspberry Pi
│   ├── capteurs/       # Gestion des modules BME280, DHT22, PMS5003
│   ├── communication/  # Serveur Bluetooth Low Energy (BLE)
│   ├── securite/       # Chiffrement AES-256 et signatures ECDSA
│   ├── stockage/       # Base de données SQLite locale sécurisée
│   └── main.py         # Point d'entrée de la sentinelle
├── mobile_app/         # Application mobile (React Native / Expo)
│   ├── App.tsx         # Interface utilisateur
│   ├── assets/         # Ressources visuelles
│   └── package.json    # Dépendances de l'application
└── README.md           # Ce fichier
```

---

## 🍓 Application Raspberry Pi (raspi_app)

### Installation (Raspi) {#installation-raspi}

1.  **Prérequis** : Un Raspberry Pi (3, 4, 5 ou Zero W) avec Python 3.10+.
2.  **Configuration du système** : Activer l'I2C et le Bluetooth sur le Pi.
3.  **Installation des dépendances** :
    ```bash
    cd raspi_app
    python -m venv .venv
    source .venv/bin/activate  # Sur Windows: .venv\Scripts\activate
    pip install -r requirements.txt
    ```
4.  **Configuration** :
    - Copiez `config_raspi.py` en `config.py`.
    - Ajustez les paramètres selon vos besoins (IDs, ports).

### Utilisation (Raspi) {#utilisation-raspi}

-   **Lancement classique** : `python main.py`
-   **Mode Simulation** : Pour tester sans capteurs physiques, réglez `SENTINEL_SIMULATION = True` dans `config.py`.
-   **Logs** : Le système affiche en temps réel les cycles de lecture et les notifications BLE.

---

## 📱 Application Mobile (mobile_app)

### Installation (Mobile) {#installation-mobile}

1.  **Prérequis** : Node.js installé sur votre machine.
2.  **Installation des dépendances** :
    ```bash
    cd mobile_app
    npm install
    ```
3.  **Lancement** :
    ```bash
    npx expo start
    ```
    Utilisez l'application **Expo Go** (sur iOS/Android) pour scanner le QR code et lancer l'application sur votre téléphone.

### Utilisation (Mobile) {#utilisation-mobile}

-   L'application scanne les périphériques BLE à proximité.
-   Connectez-vous à la "Sentinelle" identifiée.
-   L'application télécharge automatiquement les "bundles" de données chiffrées stockés sur le Pi.

---

## 💎 Profondeur & Fonctionnalités

### 🛡️ Sécurité de niveau industriel
-   **Confidentialité** : Toutes les données sont chiffrées avec **AES-256-CBC** dès leur acquisition.
-   **Intégrité** : Chaque lot de données (bundle) est signé numériquement avec **ECDSA** (courbe NIST P-256).
-   **Anti-rejeu** : Utilisation de nonces uniques pour chaque transmission.

### 📶 Communication Robuste
-   **BLE GATT** : Communication optimisée pour une faible consommation d'énergie.
-   **DTN Ready** : Architecture pensée pour les environnements hors-ligne.

### 📊 Capteurs supportés
-   **BME280** : Température, Humidité, Pression atmosphérique.
-   **DHT22** : Température, Humidité (alternative économique).
-   **PMS5003** : Qualité de l'air (Particules fines PM1.0, PM2.5, PM10).

### 🗄️ Stockage Intelligent
-   Base de données **SQLite** locale pour conserver les mesures jusqu'à leur récupération.
-   Gestion automatique de l'espace disque et suppression des données après transmission réussie.

---

## 👤 Auteur

**Louis Lapointe** — 2026

*Développé dans le cadre d'un projet IoT sécurisé.*
