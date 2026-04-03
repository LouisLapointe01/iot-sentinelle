# Sentinelles Environnementales et Réseaux Opportunistes (DTN-IoT)

Projet réalisé dans le cadre de l’UE **Internet et Web des Objets** à l’**Université de Toulouse 3 – Paul Sabatier (UPSSITECH)**.  
Il propose une solution de **collecte participative** de données environnementales en **zones blanches**, basée sur des **réseaux tolérants aux délais (DTN)**.

---

## 🌍 Contexte et objectifs

Dans des environnements dépourvus d’infrastructures réseau classiques (montagnes, forêts, zones isolées), la transmission temps-réel est impossible.  
Ce projet utilise le paradigme **DTN (Delay/Disruption Tolerant Networking)** et le principe **Store–Carry–Forward** :

1. La **sentinelle** mesure et **stocke** les données localement.
2. Un citoyen volontaire (la **mule**) passe à proximité, récupère les données en **BLE** et les **emporte**.
3. Dès qu’une connectivité est retrouvée, la mule **déleste** les données vers un serveur **Cloud/Edge**.

---

## 🏗️ Architecture du système

Le projet est découpé en trois sous-systèmes modulaires :

### 1) Sentinelle (Raspberry Pi / ESP32)
- Unité autonome d’acquisition.
- Mesures typiques :
  - Température / humidité (**DHT22**)
  - Pression / température (**BME280**)
  - Particules fines (**PMS5003**)
- Sécurité :
  - Chiffrement **AES-256** (mode **CBC**)
- Communication :
  - Publication via un serveur **Bluetooth Low Energy (BLE)**

### 2) Mule (Application mobile)
- Smartphone récupérant les données via **BLE**.
- Déclenchement conditionné par la signature d’un **contrat numérique** (validation/consentement).
- Stockage local (tampon) avant transfert.
- Délestage vers le Cloud dès connectivité disponible (Wi‑Fi/4G/5G).

### 3) Serveur Cloud / Edge
- Centralisation et ingestion via **MQTT**.
- Vérification de la non-répudiation via signatures numériques **ECDSA**.
- Stockage et accès aux données pour visualisation / exploitation scientifique.

---

## 🛠️ Stack technique

- **Langage principal :** Python (approche *Clean Code* pédagogique)
- **Communication :** Bluetooth Low Energy (**BLE 4.2+**)
- **Sécurité :**
  - Chiffrement **AES-256-CBC**
  - Signatures **ECDSA**
  - Appairage / enrôlement par **QR Code**
- **Infrastructure :**
  - Broker MQTT (**neOCampus**)
  - Base de données **PostgreSQL**
- **Capteurs :** DHT22, BME280, PMS5003

---

## 🛡️ Sécurité et confidentialité

Quatre mécanismes principaux protègent l’intégrité et la confidentialité :

1. **Chiffrement de bout en bout** dès l’acquisition sur la sentinelle  
2. **Signatures numériques** pour garantir la **non-répudiation** des mesures  
3. **Appairage par QR Code** pour authentifier la source physique (provisionnement)  
4. **Protection contre le rejeu** via **nonces** et **horodatages**  

---

## 📦 Organisation du dépôt

> À compléter/ajuster selon le contenu réel du dépôt (dossiers, scripts, modules).
> Envoie-moi la structure du repo (Option A) et je te mets cette section exacte.

Exemples de sections possibles :
- `sentinelle/` : acquisition capteurs, chiffrement, serveur BLE
- `mule/` : app mobile / logique de collecte BLE / stockage local
- `server/` : ingestion MQTT, validation ECDSA, persistance PostgreSQL

---

## 🚀 Installation & exécution

> À compléter précisément selon `requirements.txt`, `pyproject.toml`, Docker, scripts, etc.
> Envoie-moi les fichiers de config présents et je te mets des commandes exactes.

Exemple (si projet Python) :
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## ✅ Bonnes pratiques / Qualité

- Code structuré et lisible (approche Clean Code)
- Séparation des responsabilités (acquisition / transport / ingestion)
- Tests (si présents) et logging (si présents)

---

## 👥 Contributeurs

Projet rédigé et développé par :
- **Thomas Collet**
- **Louis Lapointe**
- **Oussama Guelagli**
- **Bastien Cabanie**
