"""
chiffrement.py -- Chiffrement symetrique AES-256-CBC des donnees.

Ici, on implemente le chiffrement AES-256-CBC tel que specifie dans le CDC.
AES-256-CBC signifie :
- AES : Advanced Encryption Standard, algorithme de chiffrement par blocs
- 256 : taille de la cle en bits (32 octets)
- CBC : Cipher Block Chaining, mode ou chaque bloc est XOR avec le precedent

Le mode CBC necessite un vecteur d'initialisation (IV) de 16 octets,
genere aleatoirement pour chaque operation de chiffrement.
Le padding PKCS7 est utilise car AES opere sur des blocs de 16 octets.
"""

import json
import logging

from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes
from Crypto.Util.Padding import pad, unpad

import config

logger = logging.getLogger(__name__)


def chiffrer_donnees(donnees_dict, cle_aes):
    """
    Ici, on chiffre un dictionnaire de mesures en AES-256-CBC.

    Le processus :
    1. Serialiser le dictionnaire en JSON (UTF-8)
    2. Appliquer le padding PKCS7
    3. Generer un IV aleatoire de 16 octets
    4. Chiffrer avec AES-256-CBC

    Args:
        donnees_dict: Dictionnaire contenant les mesures a chiffrer.
        cle_aes: Cle AES de 32 octets (bytes).

    Returns:
        Tuple (iv, donnees_chiffrees) ou iv et donnees_chiffrees sont des bytes.
    """
    donnees_json = json.dumps(donnees_dict, ensure_ascii=False)
    donnees_octets = donnees_json.encode("utf-8")

    # Ici, on genere un IV aleatoire de 16 octets.
    # Un nouvel IV est genere pour CHAQUE chiffrement, car reutiliser un IV
    # avec la meme cle compromettrait la confidentialite.
    iv = get_random_bytes(config.TAILLE_BLOC_AES)

    cipher = AES.new(cle_aes, AES.MODE_CBC, iv)
    donnees_paddees = pad(donnees_octets, config.TAILLE_BLOC_AES)
    donnees_chiffrees = cipher.encrypt(donnees_paddees)

    logger.debug(
        f"Chiffrement : {len(donnees_octets)} octets clairs -> "
        f"{len(donnees_chiffrees)} octets chiffres"
    )
    return iv, donnees_chiffrees


def dechiffrer_donnees(iv, donnees_chiffrees, cle_aes):
    """
    Ici, on dechiffre des donnees chiffrees en AES-256-CBC.
    Cette fonction est fournie pour les tests et la validation locale.

    Args:
        iv: Vecteur d'initialisation de 16 octets.
        donnees_chiffrees: Donnees chiffrees (bytes).
        cle_aes: Cle AES de 32 octets (bytes).

    Returns:
        Dictionnaire contenant les mesures dechiffrees.
    """
    cipher = AES.new(cle_aes, AES.MODE_CBC, iv)
    donnees_paddees = cipher.decrypt(donnees_chiffrees)
    donnees_octets = unpad(donnees_paddees, config.TAILLE_BLOC_AES)
    donnees_json = donnees_octets.decode("utf-8")
    return json.loads(donnees_json)
