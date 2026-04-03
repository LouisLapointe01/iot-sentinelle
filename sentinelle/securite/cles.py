"""
cles.py -- Generation et gestion des cles cryptographiques de la sentinelle.

Ici, on gere deux types de cles :
1. Cle symetrique AES-256 (32 octets) pour le chiffrement des donnees.
2. Paire de cles ECDSA (courbe P-256) pour la signature numerique.

La cle AES est partagee entre la sentinelle et le serveur (pre-provisionnee).
La cle privee ECDSA reste sur la sentinelle ; la cle publique est diffusee
via le QR code et le service BLE pour permettre la verification des signatures.
"""

import os
import logging

from Crypto.PublicKey import ECC
from Crypto.Random import get_random_bytes

import config

logger = logging.getLogger(__name__)


def creer_repertoire_cles():
    """
    Ici, on cree le repertoire de stockage des cles s'il n'existe pas encore.
    """
    if not os.path.exists(config.REPERTOIRE_CLES):
        os.makedirs(config.REPERTOIRE_CLES, exist_ok=True)
        logger.info(f"Repertoire de cles cree : {config.REPERTOIRE_CLES}")


def generer_cle_aes():
    """
    Ici, on genere une cle AES-256 aleatoire de 32 octets (256 bits),
    ou on la charge depuis le disque si elle existe deja.

    Returns:
        Cle AES de 32 octets (bytes).
    """
    creer_repertoire_cles()

    if os.path.exists(config.FICHIER_CLE_AES):
        logger.info("Cle AES existante chargee depuis le disque")
        with open(config.FICHIER_CLE_AES, "rb") as fichier:
            return fichier.read()

    # Ici, get_random_bytes() utilise le CSPRNG du systeme (/dev/urandom sur Linux).
    cle = get_random_bytes(config.TAILLE_CLE_AES)

    with open(config.FICHIER_CLE_AES, "wb") as fichier:
        fichier.write(cle)

    logger.info("Nouvelle cle AES-256 generee et sauvegardee")
    return cle


def generer_cles_ecdsa():
    """
    Ici, on genere une paire de cles ECDSA sur la courbe P-256 (secp256r1).
    ECDSA est prefere a RSA dans le CDC car les cles sont plus compactes
    et les operations plus rapides sur un processeur ARM.

    Returns:
        Tuple (cle_privee_pem, cle_publique_pem) en format PEM (str).
    """
    creer_repertoire_cles()

    # Ici, on verifie si les cles existent deja pour ne pas les regenerer.
    if (
        os.path.exists(config.FICHIER_CLE_PRIVEE)
        and os.path.exists(config.FICHIER_CLE_PUBLIQUE)
    ):
        logger.info("Cles ECDSA existantes chargees depuis le disque")
        with open(config.FICHIER_CLE_PRIVEE, "r") as fichier:
            cle_privee_pem = fichier.read()
        with open(config.FICHIER_CLE_PUBLIQUE, "r") as fichier:
            cle_publique_pem = fichier.read()
        return cle_privee_pem, cle_publique_pem

    # Ici, on genere une nouvelle paire de cles ECDSA P-256.
    cle_privee = ECC.generate(curve="P-256")
    cle_publique = cle_privee.public_key()

    cle_privee_pem = cle_privee.export_key(format="PEM", use_pkcs8=False)
    cle_publique_pem = cle_publique.export_key(format="PEM")

    with open(config.FICHIER_CLE_PRIVEE, "w") as fichier:
        fichier.write(cle_privee_pem)

    with open(config.FICHIER_CLE_PUBLIQUE, "w") as fichier:
        fichier.write(cle_publique_pem)

    logger.info("Nouvelle paire de cles ECDSA P-256 generee et sauvegardee")
    return cle_privee_pem, cle_publique_pem


def charger_cle_aes():
    """Charge ou genere la cle AES."""
    return generer_cle_aes()


def charger_cle_privee_ecdsa():
    """Charge la cle privee ECDSA comme objet ECC.EccKey."""
    cle_privee_pem, _ = generer_cles_ecdsa()
    return ECC.import_key(cle_privee_pem)


def charger_cle_publique_ecdsa_pem():
    """Charge la cle publique ECDSA au format PEM (str)."""
    _, cle_publique_pem = generer_cles_ecdsa()
    return cle_publique_pem
