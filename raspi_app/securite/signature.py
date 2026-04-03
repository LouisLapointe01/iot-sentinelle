"""
signature.py -- Signature numerique ECDSA des bundles de donnees.

Ici, on implemente la signature ECDSA qui garantit :
1. INTEGRITE : les donnees n'ont pas ete modifiees pendant le transport
2. NON-REPUDIATION : seule la sentinelle possedant la cle privee peut signer

Le processus de signature :
1. On calcule le hash SHA-256 des donnees a signer
2. On signe ce hash avec la cle privee ECDSA de la sentinelle
3. La signature accompagne les donnees dans le bundle
"""

import logging

from Crypto.PublicKey import ECC
from Crypto.Signature import DSS
from Crypto.Hash import SHA256

logger = logging.getLogger(__name__)


def signer_donnees(donnees_bytes, cle_privee):
    """
    Ici, on signe des donnees avec la cle privee ECDSA de la sentinelle.
    On utilise le schema DSS en mode 'fips-186-3' (standard NIST pour ECDSA).

    Args:
        donnees_bytes: Donnees a signer (bytes).
        cle_privee: Objet ECC.EccKey (cle privee ECDSA).

    Returns:
        Signature numerique (bytes, ~64 octets pour P-256).
    """
    hash_donnees = SHA256.new(donnees_bytes)
    signeur = DSS.new(cle_privee, "fips-186-3")
    signature = signeur.sign(hash_donnees)

    logger.debug(f"Signature ECDSA generee : {len(signature)} octets")
    return signature


def verifier_signature(donnees_bytes, signature, cle_publique):
    """
    Ici, on verifie une signature ECDSA avec la cle publique de la sentinelle.

    Args:
        donnees_bytes: Donnees dont on verifie la signature (bytes).
        signature: Signature a verifier (bytes).
        cle_publique: Objet ECC.EccKey (cle publique ECDSA).

    Returns:
        True si la signature est valide, False sinon.
    """
    hash_donnees = SHA256.new(donnees_bytes)
    verificateur = DSS.new(cle_publique, "fips-186-3")

    try:
        verificateur.verify(hash_donnees, signature)
        logger.debug("Verification de signature : SUCCES")
        return True
    except ValueError:
        logger.warning("Verification de signature : ECHEC (signature invalide)")
        return False
