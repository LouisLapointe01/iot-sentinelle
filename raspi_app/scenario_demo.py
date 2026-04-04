#!/usr/bin/env python3
"""
scenario_demo.py -- Démonstration visuelle d'un déploiement DTN complet.

Simule une journée complète en accéléré :
  T=0h  Déploiement initial (boot, clés, QR code)
  T=6h  12 cycles de mesure (simulés instantanément)
  T=12h Arrivée de la mule smartphone
  T=12h Transfert BLE complet (chunking)
  T=13h Transmission MQTT (simulation)
  T=24h Rapport final

Usage :
    python scenario_demo.py
    python scenario_demo.py --rapide   (sans pauses)
"""

import os
import sys

# Forcer UTF-8 sur Windows pour les caractères spéciaux
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import json
import base64
import datetime
import time
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["SENTINEL_SIMULATION"] = "true"
os.environ["SENTINEL_ID"] = "sentinelle-demo-001"


# =============================================================================
# AFFICHAGE
# =============================================================================

class Couleur:
    ROUGE  = "\033[0;31m"
    VERT   = "\033[0;32m"
    JAUNE  = "\033[1;33m"
    BLEU   = "\033[0;34m"
    CYAN   = "\033[0;36m"
    VIOLET = "\033[0;35m"
    GRAS   = "\033[1m"
    RESET  = "\033[0m"

def titre(texte: str):
    print(f"\n{Couleur.GRAS}{Couleur.CYAN}{'='*60}{Couleur.RESET}")
    print(f"{Couleur.GRAS}{Couleur.CYAN}  {texte}{Couleur.RESET}")
    print(f"{Couleur.GRAS}{Couleur.CYAN}{'='*60}{Couleur.RESET}")

def sous_titre(texte: str):
    print(f"\n{Couleur.GRAS}{Couleur.BLEU}  >> {texte}{Couleur.RESET}")

def ok(texte: str):
    print(f"  {Couleur.VERT}[OK]{Couleur.RESET} {texte}")

def info(texte: str):
    print(f"  {Couleur.BLEU}[--]{Couleur.RESET} {texte}")

def warn(texte: str):
    print(f"  {Couleur.JAUNE}[!!]{Couleur.RESET} {texte}")

def err(texte: str):
    print(f"  {Couleur.ROUGE}[KO]{Couleur.RESET} {texte}")

def horloge(heure_sim: str):
    now = datetime.datetime.now().strftime("%H:%M:%S")
    print(f"\n  {Couleur.VIOLET}[T] Temps simule : {heure_sim}  (reel : {now}){Couleur.RESET}")

def pause(secondes: float, rapide: bool):
    if not rapide:
        time.sleep(secondes)


# =============================================================================
# SCÉNARIO
# =============================================================================

def run_scenario(rapide: bool = False):
    import config
    from securite.cles import generer_cle_aes, generer_cles_ecdsa, charger_cle_privee_ecdsa
    from securite.chiffrement import chiffrer_donnees, dechiffrer_donnees
    from securite.signature import signer_donnees, verifier_signature
    from stockage.base_locale import BaseLocale
    from communication.ble_serveur import BLE_CHUNK_SIZE
    from Crypto.Random import get_random_bytes
    from Crypto.PublicKey import ECC

    stats = {
        "cycles": 0, "bundles_stockes": 0, "bundles_transferes": 0,
        "bundles_mqtt": 0, "erreurs": 0, "taille_totale_bytes": 0,
    }

    # =========================================================================
    # ACTE 1 : Déploiement initial
    # =========================================================================
    titre("ACTE 1 — Déploiement initial  (T = 00:00)")
    horloge("06:00")

    sous_titre("Initialisation des clés cryptographiques")
    pause(0.5, rapide)

    cle_aes = generer_cle_aes()
    ok(f"Clé AES-256 générée  ({len(cle_aes)} octets)")

    _, pub_pem = generer_cles_ecdsa()
    cle_privee = charger_cle_privee_ecdsa()
    cle_publique = ECC.import_key(pub_pem)
    ok(f"Paire ECDSA P-256 générée  (courbe {cle_privee.curve})")

    sous_titre("Initialisation de la base SQLite")
    os.makedirs(os.path.dirname(config.FICHIER_BASE_DONNEES), exist_ok=True)
    base = BaseLocale()
    ok(f"Base SQLite prête  ({config.FICHIER_BASE_DONNEES})")

    sous_titre("QR code de déploiement")
    qr_content = {
        "sentinel_id": config.SENTINEL_ID,
        "ble_service_uuid": config.BLE_SERVICE_UUID,
        "ble_address": "AA:BB:CC:DD:EE:FF",
        "public_key": pub_pem[:40] + "...",
    }
    info(f"Sentinel ID    : {qr_content['sentinel_id']}")
    info(f"BLE UUID       : {qr_content['ble_service_uuid']}")
    info(f"Clé publique   : {qr_content['public_key']}")
    ok("QR code prêt à coller sur le boîtier")

    pause(1.0, rapide)

    # =========================================================================
    # ACTE 2 : Collecte des données
    # =========================================================================
    NB_CYCLES = 12  # 1h = 12 cycles × 5min
    titre(f"ACTE 2 — Collecte environnementale  ({NB_CYCLES} cycles)")
    horloge("06:00 → 07:00")

    sous_titre(f"Démarrage de la boucle de mesure ({NB_CYCLES} cycles)")
    pause(0.3, rapide)

    t_debut = datetime.datetime(2026, 4, 4, 6, 0, 0, tzinfo=datetime.timezone.utc)

    for i in range(NB_CYCLES):
        t_cycle = t_debut + datetime.timedelta(minutes=5 * i)
        horodatage = t_cycle.isoformat()

        mesures = [
            {"type": "temperature", "valeur": round(18.5 + i * 0.1, 2),  "unite": "°C",    "horodatage": horodatage},
            {"type": "humidite",    "valeur": round(60.0 + (i % 10),  1), "unite": "%",     "horodatage": horodatage},
            {"type": "pression",    "valeur": round(1013.2 - i * 0.05, 2),"unite": "hPa",   "horodatage": horodatage},
            {"type": "pm2_5",       "valeur": round(5.0 + (i % 15),   1), "unite": "µg/m³", "horodatage": horodatage},
            {"type": "pm10",        "valeur": round(9.0 + (i % 20),   1), "unite": "µg/m³", "horodatage": horodatage},
        ]
        cycle = {
            "sentinel_id": config.SENTINEL_ID,
            "horodatage": horodatage,
            "mesures": mesures,
            "nb_mesures": len(mesures),
        }

        iv, chiffre = chiffrer_donnees(cycle, cle_aes)
        signature   = signer_donnees(iv + chiffre, cle_privee)
        nonce       = get_random_bytes(16).hex()
        bundle_id   = base.stocker_bundle(iv, chiffre, signature, nonce, len(mesures))

        stats["cycles"] += 1
        stats["bundles_stockes"] += 1
        taille_bundle = len(json.dumps(base.recuperer_bundle_par_index(i)))
        stats["taille_totale_bytes"] += taille_bundle

        temp = mesures[0]["valeur"]
        hum  = mesures[1]["valeur"]
        pm25 = mesures[3]["valeur"]
        print(f"    Cycle {i+1:2d}/12  {t_cycle.strftime('%H:%M')}  "
              f"T={temp}°C  H={hum}%  PM2.5={pm25}µg/m³  "
              f"{Couleur.VERT}→ Bundle {bundle_id[:8]}...{Couleur.RESET}")
        pause(0.05, rapide)

    print()
    ok(f"{stats['bundles_stockes']} bundles stockés  "
       f"(~{stats['taille_totale_bytes']//1024} Ko au total)")
    ok(f"Taille moyenne par bundle : {stats['taille_totale_bytes'] // NB_CYCLES} octets")

    pause(1.0, rapide)

    # =========================================================================
    # ACTE 3 : Arrivée de la mule
    # =========================================================================
    titre("ACTE 3 — Arrivée de la mule  (T = 06:00+)")
    horloge("12:00")

    sous_titre("Scan BLE → découverte de la sentinelle")
    pause(0.5, rapide)
    info(f"UUID service détecté : {config.BLE_SERVICE_UUID}")
    info(f"Connexion GATT établie avec {config.SENTINEL_ID}")
    ok("Mule connectée")

    sous_titre(f"Lecture BUNDLE_COUNT → {NB_CYCLES} bundles à récupérer")
    pause(0.3, rapide)

    bundles_recus = []

    for idx in range(NB_CYCLES):
        bundle = base.recuperer_bundle_par_index(0)  # toujours index 0 (FIFO)
        json_bundle = json.dumps(bundle)

        # Chunking BLE
        chunks = [json_bundle[i:i+BLE_CHUNK_SIZE]
                  for i in range(0, len(json_bundle), BLE_CHUNK_SIZE)]
        nb_chunks = len(chunks)

        # Reconstitution
        reconstitue = json.loads("".join(chunks))

        # Vérification signature
        iv  = base64.b64decode(reconstitue["iv"])
        enc = base64.b64decode(reconstitue["donnees_chiffrees"])
        sig = base64.b64decode(reconstitue["signature"])
        valide = verifier_signature(iv + enc, sig, cle_publique)

        if not valide:
            err(f"Bundle {reconstitue['bundle_id'][:8]}... SIGNATURE INVALIDE !")
            stats["erreurs"] += 1
            continue

        # ACK
        base.marquer_transfere(reconstitue["bundle_id"])
        bundles_recus.append(reconstitue)
        stats["bundles_transferes"] += 1

        print(f"    Bundle {idx+1:2d}/{NB_CYCLES}  "
              f"[{nb_chunks} chunks x {BLE_CHUNK_SIZE}B]  "
              f"sign={Couleur.VERT}OK{Couleur.RESET}  "
              f"ACK={Couleur.VERT}OK{Couleur.RESET}")
        pause(0.05, rapide)

    print()
    ok(f"{stats['bundles_transferes']}/{NB_CYCLES} bundles transférés")
    ok(f"Base sentinelle : {base.compter_bundles_en_attente()} bundles restants")
    if stats["erreurs"]:
        warn(f"{stats['erreurs']} erreurs de signature détectées")

    pause(1.0, rapide)

    # =========================================================================
    # ACTE 4 : Transmission MQTT
    # =========================================================================
    titre("ACTE 4 — Transmission MQTT  (mule → neOCampus)")
    horloge("13:00")

    sous_titre(f"Connexion au broker MQTT ({config.MQTT_BROKER}:{config.MQTT_PORT})")
    pause(0.3, rapide)
    info(f"Broker  : ws://{config.MQTT_BROKER}:{config.MQTT_PORT}")
    info(f"User    : {config.MQTT_USERNAME}")
    ok("Connexion WebSocket établie (simulée)")

    sous_titre(f"Publication de {len(bundles_recus)} bundles")
    pause(0.2, rapide)

    topic_base = f"{config.MQTT_TOPIC_PREFIX}/{config.SENTINEL_ID}"

    for i, bundle in enumerate(bundles_recus):
        topic   = topic_base
        payload = json.dumps(bundle)

        # Déchiffrement pour afficher les mesures claires
        iv  = base64.b64decode(bundle["iv"])
        enc = base64.b64decode(bundle["donnees_chiffrees"])
        dec = dechiffrer_donnees(iv, enc, cle_aes)

        temp_dec = next((m["valeur"] for m in dec["mesures"] if m["type"] == "temperature"), "?")

        print(f"    PUBLISH [{i+1:2d}/{len(bundles_recus)}]  "
              f"topic={Couleur.CYAN}{topic[-40:]}{Couleur.RESET}  "
              f"T={temp_dec}°C  "
              f"QoS=1  {Couleur.VERT}✓{Couleur.RESET}")
        stats["bundles_mqtt"] += 1
        pause(0.04, rapide)

    print()
    ok(f"{stats['bundles_mqtt']}/{len(bundles_recus)} bundles publiés sur MQTT")

    pause(1.0, rapide)

    # =========================================================================
    # RAPPORT FINAL
    # =========================================================================
    titre("RAPPORT FINAL  (T = 24h)")
    horloge("06:00 du lendemain")

    duree_sim = datetime.timedelta(hours=1)
    print()
    print(f"  {'Paramètre':<35} {'Valeur':>12}")
    print(f"  {'-'*49}")
    print(f"  {'Sentinel ID':<35} {config.SENTINEL_ID:>12}")
    print(f"  {'Cycles de mesure':<35} {stats['cycles']:>12}")
    print(f"  {'Bundles stockés (SQLite)':<35} {stats['bundles_stockes']:>12}")
    print(f"  {'Bundles transférés (BLE)':<35} {stats['bundles_transferes']:>12}")
    print(f"  {'Bundles publiés (MQTT)':<35} {stats['bundles_mqtt']:>12}")
    print(f"  {'Erreurs cryptographiques':<35} {stats['erreurs']:>12}")
    print(f"  {'Taille totale données':<35} {stats['taille_totale_bytes']//1024:>10} Ko")
    print(f"  {'Taille moy. par bundle':<35} {stats['taille_totale_bytes']//max(stats['cycles'],1):>8} oct.")
    print(f"  {'Bundles en attente restants':<35} {base.compter_bundles_en_attente():>12}")
    print()

    if stats["erreurs"] == 0 and stats["bundles_transferes"] == NB_CYCLES:
        print(f"  {Couleur.VERT}{Couleur.GRAS}[OK] Pipeline DTN complet -- aucune perte de donnees{Couleur.RESET}")
    else:
        print(f"  {Couleur.ROUGE}{Couleur.GRAS}[KO] Pipeline incomplet -- {stats['erreurs']} erreurs{Couleur.RESET}")

    print()
    base.fermer()


# =============================================================================
# POINT D'ENTRÉE
# =============================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Démo scénario DTN complet")
    parser.add_argument("--rapide", action="store_true",
                        help="Sans pauses (pour CI ou tests rapides)")
    args = parser.parse_args()

    print(f"\n{Couleur.GRAS}{Couleur.CYAN}")
    print("  ================================================")
    print("   IoT-Sentinelle  --  Demo DTN complete")
    print("   Store --> Carry --> Forward")
    print(f"  ================================================{Couleur.RESET}")

    run_scenario(rapide=args.rapide)
