"""
gestionnaire.py -- Orchestration des capteurs environnementaux.

Ici, le GestionnaireCapteurs coordonne la lecture de tous les capteurs
(DHT22, BME280, PMS5003) et retourne un ensemble unifie de mesures.
C'est le point d'entree unique du module capteurs pour le reste du systeme :
au lieu d'appeler chaque capteur individuellement, le code principal
appelle simplement gestionnaire.lire_tous() pour obtenir toutes les mesures.
"""

import logging
from datetime import datetime, timezone

from capteurs.dht22 import CapteurDHT22
from capteurs.bme280 import CapteurBME280
from capteurs.pms5003 import CapteurPMS5003
import config

logger = logging.getLogger(__name__)


class GestionnaireCapteurs:
    """
    Classe qui orchestre la lecture de tous les capteurs de la sentinelle.

    Elle cree et gere les instances de chaque capteur, collecte les mesures
    de facon unifiee, et gere les erreurs individuelles sans bloquer
    l'ensemble du cycle d'acquisition.
    """

    def __init__(self):
        """
        Ici, on initialise les trois capteurs en utilisant les parametres
        definis dans config.py. Si un capteur echoue a l'initialisation,
        les autres fonctionnent quand meme (resilience).
        """
        self.capteurs = {}

        # Ici, on initialise chaque capteur dans un bloc try/except separe.
        # Ainsi, si le BME280 est defaillant par exemple, le DHT22 et le PMS5003
        # continuent de fonctionner normalement.
        try:
            self.capteurs["dht22"] = CapteurDHT22(
                pin_gpio=config.DHT22_PIN,
                mode_simulation=config.MODE_SIMULATION,
            )
        except Exception as erreur:
            logger.error(f"Impossible d'initialiser le DHT22 : {erreur}")

        try:
            self.capteurs["bme280"] = CapteurBME280(
                adresse_i2c=config.BME280_I2C_ADDRESS,
                bus_i2c=config.BME280_I2C_BUS,
                mode_simulation=config.MODE_SIMULATION,
            )
        except Exception as erreur:
            logger.error(f"Impossible d'initialiser le BME280 : {erreur}")

        try:
            self.capteurs["pms5003"] = CapteurPMS5003(
                port_serie=config.PMS5003_SERIAL_PORT,
                debit=config.PMS5003_BAUD_RATE,
                mode_simulation=config.MODE_SIMULATION,
            )
        except Exception as erreur:
            logger.error(f"Impossible d'initialiser le PMS5003 : {erreur}")

        nb_capteurs = len(self.capteurs)
        logger.info(f"GestionnaireCapteurs : {nb_capteurs}/3 capteurs actifs")

    def lire_tous(self):
        """
        Ici, on lit les mesures de tous les capteurs actifs et on les regroupe
        dans une structure unifiee. Cette structure constitue un cycle de mesure
        qui sera ensuite chiffre, signe et stocke comme un bundle DTN.

        Returns:
            Dictionnaire contenant :
            - "sentinel_id" : identifiant de la sentinelle
            - "horodatage"  : date/heure du cycle de mesure (UTC ISO 8601)
            - "mesures"     : liste de toutes les mesures individuelles
            - "nb_mesures"  : nombre total de mesures dans ce cycle
        """
        horodatage_cycle = datetime.now(timezone.utc).isoformat()
        toutes_mesures = []

        # Ici, on parcourt chaque capteur actif et on collecte ses mesures.
        for nom, capteur in self.capteurs.items():
            try:
                mesures = capteur.lire()
                toutes_mesures.extend(mesures)
                logger.debug(f"Capteur {nom} : {len(mesures)} mesures lues")
            except Exception as erreur:
                logger.error(f"Erreur de lecture du capteur {nom} : {erreur}")

        cycle = {
            "sentinel_id": config.SENTINEL_ID,
            "horodatage": horodatage_cycle,
            "mesures": toutes_mesures,
            "nb_mesures": len(toutes_mesures),
        }

        logger.info(
            f"Cycle de mesure : {len(toutes_mesures)} mesures collectees "
            f"a {horodatage_cycle}"
        )
        return cycle

    def fermer_tous(self):
        """
        Ici, on ferme proprement tous les capteurs pour liberer les ressources.
        """
        for nom, capteur in self.capteurs.items():
            try:
                capteur.fermer()
            except Exception as erreur:
                logger.warning(f"Erreur lors de la fermeture de {nom} : {erreur}")

        logger.info("Tous les capteurs ont ete fermes")
