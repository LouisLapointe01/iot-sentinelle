"""
bme280.py -- Module de lecture du capteur BME280 (pression atmospherique).

Ici, on encapsule la lecture du capteur BME280 dans une classe dediee.
Le BME280 est un capteur numerique connecte via le bus I2C du Raspberry Pi.
Il mesure la pression atmospherique, la temperature et l'humidite.

Dans notre systeme, on utilise principalement la pression du BME280
(le DHT22 fournissant deja temperature et humidite), mais on collecte
aussi les valeurs de temperature et humidite du BME280 pour avoir
une mesure de reference croisee.
"""

import logging
import random
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class CapteurBME280:
    """
    Classe responsable de la lecture du capteur BME280 via I2C.

    Le BME280 mesure :
    - Pression atmospherique : 300 a 1100 hPa (precision +-1 hPa)
    - Temperature : -40 a +85 degres C (precision +-1 degre C)
    - Humidite : 0 a 100% (precision +-3%)
    """

    def __init__(self, adresse_i2c, bus_i2c, mode_simulation=True):
        """
        Ici, on initialise la connexion I2C avec le capteur BME280.
        Le bus I2C n-1 est le bus standard sur Raspberry Pi 3/4,
        et l'adresse par defaut du BME280 est 0x76.

        Args:
            adresse_i2c: Adresse I2C du capteur (generalement 0x76 ou 0x77).
            bus_i2c: Numero du bus I2C (1 pour Raspberry Pi 3/4).
            mode_simulation: Si True, genere des valeurs fictives.
        """
        self.adresse_i2c = adresse_i2c
        self.bus_i2c = bus_i2c
        self.mode_simulation = mode_simulation
        self.bus = None
        self.params_calibration = None

        if not self.mode_simulation:
            try:
                import smbus2
                import bme280 as bme280_lib

                # Ici, on ouvre le bus I2C et on charge les parametres de calibration
                # du BME280. Chaque capteur BME280 contient des coefficients de
                # calibration uniques en ROM, necessaires pour convertir les valeurs
                # brutes en unites physiques.
                self.bus = smbus2.SMBus(bus_i2c)
                self.params_calibration = bme280_lib.load_calibration_params(
                    self.bus, adresse_i2c
                )
                self.bme280_lib = bme280_lib
                logger.info(
                    f"Capteur BME280 initialise sur I2C bus={bus_i2c}, "
                    f"adresse=0x{adresse_i2c:02x}"
                )
            except ImportError:
                logger.error(
                    "Bibliotheques smbus2/bme280 non disponibles. "
                    "Installer avec : pip install smbus2 RPi.bme280"
                )
                raise
            except Exception as erreur:
                logger.error(f"Erreur d'initialisation du BME280 : {erreur}")
                raise
        else:
            logger.info(
                f"Capteur BME280 en mode SIMULATION "
                f"(I2C 0x{adresse_i2c:02x})"
            )

    def lire(self):
        """
        Ici, on lit les trois grandeurs mesurees par le BME280.
        La lecture I2C est rapide (quelques millisecondes) et fiable.

        Returns:
            Liste de dictionnaires contenant les mesures horodatees,
            ou une liste vide en cas d'erreur.
        """
        horodatage = datetime.now(timezone.utc).isoformat()

        if self.mode_simulation:
            # Ici, on genere des valeurs realistes pour le developpement.
            # Pression standard au niveau de la mer : ~1013 hPa.
            # En altitude (montagne), la pression diminue (~800-900 hPa).
            pression = round(random.uniform(980.0, 1040.0), 1)
            temperature = round(random.uniform(5.0, 35.0), 1)
            humidite = round(random.uniform(30.0, 90.0), 1)
        else:
            try:
                # Ici, on effectue un echantillonnage force du BME280.
                # La fonction sample() envoie une commande de mesure au capteur
                # et lit les registres de donnees via I2C.
                donnees = self.bme280_lib.sample(
                    self.bus, self.adresse_i2c, self.params_calibration
                )
                pression = round(donnees.pressure, 1)
                temperature = round(donnees.temperature, 1)
                humidite = round(donnees.humidity, 1)
            except Exception as erreur:
                logger.error(f"BME280 : erreur de lecture : {erreur}")
                return []

        # Ici, on prefixe les mesures du BME280 pour les distinguer de celles
        # du DHT22. Cela permet de faire des comparaisons croisees cote serveur.
        mesures = [
            {
                "type": "pression",
                "valeur": pression,
                "unite": "hPa",
                "horodatage": horodatage,
            },
            {
                "type": "temperature_bme",
                "valeur": temperature,
                "unite": "degC",
                "horodatage": horodatage,
            },
            {
                "type": "humidite_bme",
                "valeur": humidite,
                "unite": "%",
                "horodatage": horodatage,
            },
        ]

        logger.debug(
            f"BME280 : pression={pression}hPa, "
            f"temperature={temperature}degC, humidite={humidite}%"
        )
        return mesures

    def fermer(self):
        """
        Ici, on ferme le bus I2C proprement pour liberer la ressource systeme.
        """
        if self.bus is not None:
            try:
                self.bus.close()
                logger.info("Capteur BME280 ferme proprement")
            except Exception as erreur:
                logger.warning(f"Erreur lors de la fermeture du BME280 : {erreur}")
