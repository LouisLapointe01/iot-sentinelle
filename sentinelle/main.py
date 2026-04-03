"""
main.py -- Point d'entree principal du firmware de la sentinelle DTN.

Ici, on orchestre l'ensemble du fonctionnement de la sentinelle :
1. Initialisation des cles cryptographiques (AES + ECDSA)
2. Initialisation des capteurs environnementaux
3. Initialisation de la base de donnees locale (SQLite)
4. Demarrage du serveur BLE GATT (dans un thread dedie)
5. Boucle principale : lecture capteurs -> chiffrement -> signature -> stockage
6. Mise en veille entre chaque cycle de mesure

Le paradigme DTN "store-carry-forward" se traduit ici par :
- STORE   : les mesures chiffrees sont stockees dans SQLite
- CARRY   : une mule (smartphone) les recupere via BLE quand elle passe
- FORWARD : la mule les transmet au serveur quand elle retrouve du reseau

Usage :
    python main.py                                    # Mode simulation
    SENTINEL_SIMULATION=false python main.py          # Mode reel Raspberry Pi
    SENTINEL_ID=sentinelle-042 python main.py         # ID personnalise
"""

import sys
import os
import signal
import logging
import json

# Ici, on ajoute le repertoire courant au path Python pour les imports.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
from capteurs.gestionnaire import GestionnaireCapteurs
from securite.cles import charger_cle_aes, charger_cle_privee_ecdsa, charger_cle_publique_ecdsa_pem
from securite.chiffrement import chiffrer_donnees
from securite.signature import signer_donnees
from stockage.base_locale import BaseLocale
from communication.ble_serveur import ServeurBLE
from energie.gestionnaire import GestionnaireEnergie
from Crypto.Random import get_random_bytes


# =============================================================================
# CONFIGURATION DU LOGGING
# =============================================================================
logging.basicConfig(
    level=getattr(logging, config.NIVEAU_LOG),
    format="%(asctime)s [%(levelname)-8s] %(name)-25s : %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("sentinelle.main")

# Variable globale pour l'arret propre via Ctrl+C.
en_fonctionnement = True


def gestionnaire_signal(signum, frame):
    """Ici, on capture Ctrl+C pour arreter la sentinelle proprement."""
    global en_fonctionnement
    logger.info("Signal d'arret recu (Ctrl+C). Arret en cours...")
    en_fonctionnement = False


def creer_et_stocker_bundle(cycle_mesures, cle_aes, cle_privee, base):
    """
    Ici, on transforme un cycle de mesures en bundle DTN securise :
    1. Chiffrement AES-256-CBC des mesures
    2. Signature ECDSA du bloc (IV + donnees chiffrees)
    3. Generation d'un nonce anti-rejeu
    4. Stockage dans la base SQLite locale

    Args:
        cycle_mesures: Dictionnaire des mesures brutes du cycle.
        cle_aes: Cle AES-256 (bytes, 32 octets).
        cle_privee: Cle privee ECDSA (objet ECC.EccKey).
        base: Instance de BaseLocale.

    Returns:
        Identifiant UUID du bundle stocke.
    """
    # Ici, on chiffre les mesures immediatement apres l'acquisition (CDC).
    iv, donnees_chiffrees = chiffrer_donnees(cycle_mesures, cle_aes)

    # Ici, on signe la concatenation IV + donnees chiffrees.
    bloc_a_signer = iv + donnees_chiffrees
    signature = signer_donnees(bloc_a_signer, cle_privee)

    # Ici, on genere un nonce anti-rejeu de 16 octets.
    nonce = get_random_bytes(16).hex()

    # Ici, on stocke le bundle dans SQLite.
    bundle_id = base.stocker_bundle(
        iv=iv,
        donnees_chiffrees=donnees_chiffrees,
        signature=signature,
        nonce=nonce,
        nb_mesures=cycle_mesures["nb_mesures"],
    )
    return bundle_id


def main():
    """Ici, on execute la boucle principale de la sentinelle DTN."""
    global en_fonctionnement

    signal.signal(signal.SIGINT, gestionnaire_signal)
    signal.signal(signal.SIGTERM, gestionnaire_signal)

    logger.info("=" * 60)
    logger.info(f"  SENTINELLE DTN -- {config.SENTINEL_ID}")
    logger.info(f"  Firmware v{config.FIRMWARE_VERSION}")
    logger.info(f"  Mode simulation : {config.MODE_SIMULATION}")
    logger.info("=" * 60)

    # Phase 1 : Cles cryptographiques
    logger.info("Phase 1 : Initialisation des cles cryptographiques...")
    cle_aes = charger_cle_aes()
    cle_privee = charger_cle_privee_ecdsa()
    cle_publique_pem = charger_cle_publique_ecdsa_pem()
    logger.info("Cles cryptographiques chargees")

    # Phase 2 : Capteurs
    logger.info("Phase 2 : Initialisation des capteurs...")
    gestionnaire_capteurs = GestionnaireCapteurs()

    # Phase 3 : Base de donnees
    logger.info("Phase 3 : Initialisation de la base de donnees...")
    base = BaseLocale()
    logger.info(f"Bundles en attente : {base.compter_bundles_en_attente()}")

    # Phase 4 : Serveur BLE
    logger.info("Phase 4 : Demarrage du serveur BLE...")
    serveur_ble = ServeurBLE(base, cle_publique_pem)
    serveur_ble.demarrer()

    # Phase 5 : Gestionnaire d'energie
    logger.info("Phase 5 : Initialisation du gestionnaire d'energie...")
    gestionnaire_energie = GestionnaireEnergie()

    # Boucle principale
    logger.info("Boucle principale demarree. Ctrl+C pour arreter.")
    compteur_cycles = 0

    while en_fonctionnement:
        try:
            compteur_cycles += 1
            logger.info(f"--- Cycle de mesure #{compteur_cycles} ---")

            # Ici, on lit les mesures de tous les capteurs.
            cycle_mesures = gestionnaire_capteurs.lire_tous()

            if cycle_mesures["nb_mesures"] == 0:
                logger.warning("Aucune mesure collectee dans ce cycle")
            else:
                # Ici, on cree un bundle DTN securise et on le stocke.
                bundle_id = creer_et_stocker_bundle(
                    cycle_mesures, cle_aes, cle_privee, base
                )
                serveur_ble.notifier_nouveau_bundle()

                nb_en_attente = base.compter_bundles_en_attente()
                logger.info(
                    f"Bundle {bundle_id[:8]}... stocke. "
                    f"Total en attente : {nb_en_attente}"
                )

            # Ici, on entre en mode veille jusqu'au prochain cycle.
            gestionnaire_energie.entrer_veille()

        except Exception as erreur:
            logger.error(f"Erreur dans la boucle principale : {erreur}")
            import time
            time.sleep(10)

    # Arret propre
    logger.info("Arret propre de la sentinelle...")
    gestionnaire_capteurs.fermer_tous()
    serveur_ble.arreter()
    base.fermer()
    logger.info("Sentinelle arretee. Au revoir.")


if __name__ == "__main__":
    main()
