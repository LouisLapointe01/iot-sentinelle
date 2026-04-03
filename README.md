# iot-sentinelle

## Présentation

**iot-sentinelle** est une solution IoT complète pour la collecte, la sécurisation et la transmission de données environnementales sur Raspberry Pi. Elle intègre la gestion de capteurs (DHT22, BME280, PMS5003), le stockage local sécurisé (SQLite), le chiffrement AES-256, la signature ECDSA, la communication BLE, et des utilitaires comme la génération de QR code.

---

## Installation rapide (Raspberry Pi)

### 1. Prérequis
- Raspberry Pi (Pi 3, 4 ou Zero W recommandé)
- Raspbian OS à jour
- Python 3.8+ (idéalement 3.10+)
- Accès SSH ou terminal

### 2. Cloner le dépôt
```bash
git clone https://github.com/LouisLapointe01/iot-sentinelle.git
cd iot-sentinelle/sentinelle
```

### 3. Installer les dépendances Python
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 4. Configurer la sentinelle
- Copier le fichier `config_raspi.py` en `config.py` :
```bash
cp config_raspi.py config.py
```
- Adapter les chemins, identifiants et ports selon votre matériel.

### 5. Lancer la sentinelle
```bash
python main.py
```

---

## Fonctionnalités principales
- Lecture de capteurs (DHT22, BME280, PMS5003)
- Stockage local sécurisé (SQLite)
- Chiffrement AES-256, signature ECDSA
- Communication BLE (Bluetooth Low Energy)
- Génération de QR code pour appairage
- Mode simulation pour tests sans matériel

---

## Structure du projet
- `capteurs/` : gestion des capteurs physiques
- `communication/` : BLE serveur
- `energie/` : gestion énergie (optionnel)
- `securite/` : chiffrement, clés, signature
- `stockage/` : base de données locale
- `utils/` : utilitaires (QR code, etc.)
- `tests/` : tests unitaires (pytest)
- `config.py` : configuration principale
- `main.py` : point d’entrée

---

## Dépannage & FAQ
- **Simulation** : passer `SENTINEL_SIMULATION = True` dans `config.py` pour tester sans capteurs.
- **Permissions** : certains ports (UART, I2C) nécessitent des droits root ou appartenance à des groupes (`dialout`, `i2c`).
- **BLE** : vérifier que le Bluetooth est activé (`sudo systemctl status bluetooth`).
- **Dépendances manquantes** : relancer `pip install -r requirements.txt`.

---

## Pour aller plus loin
- Ajouter vos propres capteurs dans `capteurs/`
- Modifier la base SQLite pour stocker d’autres données
- Intégrer avec Home Assistant, MQTT, etc.

---

## Auteur
Louis Lapointe — 2026

Pour toute question, ouvrir une issue sur le dépôt GitHub.
