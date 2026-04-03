"""
dht22.py -- Module de lecture du capteur DHT22 (temperature et humidite).

Ici, on encapsule la lecture du capteur DHT22 dans une classe dediee,
car le principe de responsabilite unique impose qu'un seul module gere
un seul type de capteur. Le DHT22 est connecte sur un pin GPIO du
Raspberry Pi et communique via un protocole serie proprietaire a un fil.

En mode simulation, des valeurs aleatoires realistes sont generees
pour permettre le developpement sans materiel physique.
"""

import logging
import random
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class CapteurDHT22:
    """
    Classe responsable de la lecture du capteur DHT22.

    Le DHT22 mesure la temperature (de -40 a +80 degres C, precision +-0.5 degres C)
    et l'humidite relative (de 0 a 100%, precision +-2%).
    """

    def __init__(self, pin_gpio, mode_simulation=True):
        """
        Ici, on initialise le capteur DHT22 en specifiant le pin GPIO utilise.
        En mode reel, on importe la bibliotheque adafruit_dht qui pilote le capteur.
        En mode simulation, aucun materiel n'est requis.

        Args:
            pin_gpio: Numero du pin GPIO ou est connecte le DHT22.
            mode_simulation: Si True, genere des valeurs fictives.
        """
        self.pin_gpio = pin_gpio
        self.mode_simulation = mode_simulation
        self.capteur = None

        if not self.mode_simulation:
            # Ici, on importe les bibliotheques specifiques au Raspberry Pi
            # uniquement en mode reel, car elles ne sont pas disponibles sur PC.
            try:
                import adafruit_dht
                import board

                # Ici, on cree l'objet capteur DHT22 en lui passant le pin GPIO.
                # La bibliotheque adafruit_dht gere le protocole de communication
                # proprietaire du DHT22 (signal one-wire sur 40 bits).
                broche = getattr(board, f"D{pin_gpio}")
                self.capteur = adafruit_dht.DHT22(broche)
                logger.info(f"Capteur DHT22 initialise sur GPIO {pin_gpio}")
            except ImportError:
                logger.error(
                    "Bibliotheque adafruit_dht non disponible. "
                    "Installer avec : pip install adafruit-circuitpython-dht"
                )
                raise
            except Exception as erreur:
                logger.error(f"Erreur d'initialisation du DHT22 : {erreur}")
                raise
        else:
            logger.info(f"Capteur DHT22 en mode SIMULATION (GPIO {pin_gpio})")

    def lire(self):
        """
        Ici, on lit les valeurs de temperature et d'humidite depuis le capteur DHT22.
        Le DHT22 necessite un delai minimum de 2 secondes entre deux lectures.

        Returns:
            Liste de dictionnaires contenant les mesures horodatees,
            ou une liste vide en cas d'erreur de lecture.
        """
        horodatage = datetime.now(timezone.utc).isoformat()

        if self.mode_simulation:
            # Ici, on genere des valeurs realistes pour le developpement.
            # Temperature typique en exterieur : entre 5 et 35 degres C.
            # Humidite typique : entre 30 et 90%.
            temperature = round(random.uniform(5.0, 35.0), 1)
            humidite = round(random.uniform(30.0, 90.0), 1)
        else:
            try:
                # Ici, on lit les registres du capteur via la bibliotheque adafruit.
                # Le DHT22 peut echouer a la lecture (protocole sensible au timing),
                # c'est pourquoi on capture les exceptions.
                temperature = self.capteur.temperature
                humidite = self.capteur.humidity

                if temperature is None or humidite is None:
                    logger.warning("DHT22 : lecture incomplete (None recu)")
                    return []
            except RuntimeError as erreur:
                # Ici, les erreurs RuntimeError sont courantes avec le DHT22
                # (checksums incorrects, timeouts). On les traite sans planter.
                logger.warning(f"DHT22 : erreur de lecture transitoire : {erreur}")
                return []
            except Exception as erreur:
                logger.error(f"DHT22 : erreur inattendue : {erreur}")
                return []

        # Ici, on formate les mesures dans un dictionnaire standardise.
        # Chaque mesure contient son type, sa valeur, son unite et son horodatage,
        # conformement au modele de donnees du CDC (entite Mesure).
        mesures = [
            {
                "type": "temperature",
                "valeur": temperature,
                "unite": "degC",
                "horodatage": horodatage,
            },
            {
                "type": "humidite",
                "valeur": humidite,
                "unite": "%",
                "horodatage": horodatage,
            },
        ]

        logger.debug(f"DHT22 : temperature={temperature}degC, humidite={humidite}%")
        return mesures

    def fermer(self):
        """
        Ici, on libere les ressources du capteur DHT22 proprement.
        C'est important pour eviter que le pin GPIO reste bloque.
        """
        if self.capteur is not None:
            try:
                self.capteur.exit()
                logger.info("Capteur DHT22 ferme proprement")
            except Exception as erreur:
                logger.warning(f"Erreur lors de la fermeture du DHT22 : {erreur}")
