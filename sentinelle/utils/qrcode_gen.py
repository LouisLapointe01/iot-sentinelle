"""
qrcode_gen.py -- Generation du QR code unique et statique de la sentinelle.

Ici, on genere le QR code qui sera physiquement appose sur le boitier
de la sentinelle lors du deploiement. Ce QR code est STATIQUE.

Contenu du QR code (JSON) :
- sentinel_id      : identifiant unique de la sentinelle
- ble_address      : adresse MAC BLE du Raspberry Pi
- ble_service_uuid : UUID du service GATT
- public_key       : cle publique ECDSA au format PEM

Ce script est un UTILITAIRE execute une seule fois au deploiement.
"""

import json
import logging
import os
import subprocess

import config
from securite.cles import charger_cle_publique_ecdsa_pem

logger = logging.getLogger(__name__)

try:
    import qrcode
    QRCODE_DISPONIBLE = True
except ImportError:
    QRCODE_DISPONIBLE = False


def obtenir_adresse_ble():
    """
    Ici, on recupere l'adresse MAC Bluetooth du Raspberry Pi via hciconfig.

    Returns:
        Adresse MAC Bluetooth (str), ou placeholder si indisponible.
    """
    try:
        resultat = subprocess.run(
            ["hciconfig", "hci0"],
            capture_output=True, text=True, timeout=5,
        )
        for ligne in resultat.stdout.split("\n"):
            if "BD Address" in ligne:
                return ligne.split("BD Address:")[1].strip().split(" ")[0]
    except (FileNotFoundError, subprocess.TimeoutExpired, IndexError):
        pass

    logger.warning("Adresse BLE non disponible (mode simulation?)")
    return "XX:XX:XX:XX:XX:XX"


def generer_qrcode(chemin_sortie=None):
    """
    Ici, on genere le QR code PNG de la sentinelle.

    Args:
        chemin_sortie: Chemin du fichier PNG de sortie (optionnel).

    Returns:
        Chemin du fichier PNG genere, ou None en cas d'erreur.
    """
    if not QRCODE_DISPONIBLE:
        logger.error("Impossible de generer le QR code (qrcode non installe)")
        return None

    cle_publique_pem = charger_cle_publique_ecdsa_pem()

    contenu = {
        "sentinel_id": config.SENTINEL_ID,
        "ble_service_uuid": config.BLE_SERVICE_UUID,
        "ble_address": obtenir_adresse_ble(),
        "public_key": cle_publique_pem,
    }

    contenu_json = json.dumps(contenu, indent=None, separators=(",", ":"))

    # Ici, error_correction=H (haute) permet au QR code de rester lisible
    # meme s'il est partiellement endommage (jusqu'a 30% d'erreur).
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=4,
    )
    qr.add_data(contenu_json)
    qr.make(fit=True)

    image = qr.make_image(fill_color="black", back_color="white")

    if chemin_sortie is None:
        chemin_sortie = os.path.join(
            os.path.dirname(config.REPERTOIRE_CLES),
            f"qrcode_{config.SENTINEL_ID}.png",
        )

    image.save(chemin_sortie)
    logger.info(f"QR code genere : {chemin_sortie}")
    return chemin_sortie


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

    chemin = generer_qrcode()
    if chemin:
        print(f"QR code genere : {chemin}")
    else:
        print("Erreur lors de la generation du QR code")
        sys.exit(1)
