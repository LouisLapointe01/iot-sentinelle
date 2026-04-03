"""
pms5003.py -- Module de lecture du capteur PMS5003 (particules fines).

Ici, on encapsule la lecture du capteur PMS5003 dans une classe dediee.
Le PMS5003 est un capteur laser de particules connecte via le port serie UART
du Raspberry Pi. Il mesure la concentration de particules en suspension :
- PM1.0 : particules de diametre inferieur a 1 micrometre
- PM2.5 : particules de diametre inferieur a 2.5 micrometres
- PM10  : particules de diametre inferieur a 10 micrometres

Les PM2.5 et PM10 sont les indicateurs les plus surveilles car ils sont
directement lies a la qualite de l'air et aux risques sanitaires.
"""

import logging
import random
import struct
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Ici, on definit les constantes du protocole du PMS5003.
# Le PMS5003 envoie des trames de 32 octets sur le port serie.
PMS5003_TRAME_DEBUT = bytes([0x42, 0x4D])  # Octets de debut de trame
PMS5003_TAILLE_TRAME = 32                   # Taille totale d'une trame


class CapteurPMS5003:
    """
    Classe responsable de la lecture du capteur PMS5003 via UART.

    Le PMS5003 utilise un laser pour compter les particules dans l'air.
    Il envoie periodiquement des trames de 32 octets sur le port serie,
    contenant les concentrations en PM1.0, PM2.5 et PM10.
    """

    def __init__(self, port_serie, debit, mode_simulation=True):
        """
        Ici, on initialise la connexion serie avec le capteur PMS5003.
        Sur Raspberry Pi, le port serie materiel est /dev/ttyS0 (ou /dev/ttyAMA0).

        Args:
            port_serie: Chemin du port serie (ex: /dev/ttyS0).
            debit: Debit en bauds (9600 pour le PMS5003).
            mode_simulation: Si True, genere des valeurs fictives.
        """
        self.port_serie = port_serie
        self.debit = debit
        self.mode_simulation = mode_simulation
        self.serial = None

        if not self.mode_simulation:
            try:
                import serial

                # Ici, on ouvre le port serie avec un timeout de 2 secondes.
                # Le timeout evite que la lecture bloque indefiniment si le
                # capteur ne repond pas (cable debranche, capteur en panne).
                self.serial = serial.Serial(
                    port=port_serie,
                    baudrate=debit,
                    timeout=2.0
                )
                logger.info(
                    f"Capteur PMS5003 initialise sur {port_serie} "
                    f"a {debit} bauds"
                )
            except ImportError:
                logger.error(
                    "Bibliotheque pyserial non disponible. "
                    "Installer avec : pip install pyserial"
                )
                raise
            except Exception as erreur:
                logger.error(f"Erreur d'initialisation du PMS5003 : {erreur}")
                raise
        else:
            logger.info(f"Capteur PMS5003 en mode SIMULATION ({port_serie})")

    def _lire_trame(self):
        """
        Ici, on lit une trame complete de 32 octets depuis le PMS5003.
        Le protocole impose de chercher les octets de debut (0x42, 0x4D),
        puis de lire les 30 octets restants.

        Returns:
            Trame brute de 32 octets, ou None si la lecture echoue.
        """
        # Ici, on cherche le debut de trame en lisant octet par octet.
        # C'est necessaire car le flux serie peut etre desynchronise.
        while True:
            octet = self.serial.read(1)
            if len(octet) == 0:
                logger.warning("PMS5003 : timeout en attente de trame")
                return None

            if octet[0] == 0x42:
                octet_suivant = self.serial.read(1)
                if len(octet_suivant) == 0:
                    return None
                if octet_suivant[0] == 0x4D:
                    # Ici, on a trouve le debut de trame.
                    reste = self.serial.read(30)
                    if len(reste) < 30:
                        logger.warning("PMS5003 : trame incomplete")
                        return None
                    return PMS5003_TRAME_DEBUT + reste

    def _decoder_trame(self, trame):
        """
        Ici, on decode la trame brute du PMS5003 pour extraire les concentrations.

        Structure de la trame (32 octets) :
        - [0-1]   : Octets de debut (0x42, 0x4D)
        - [2-3]   : Longueur des donnees (toujours 28)
        - [4-5]   : PM1.0 (conditions standard, ug/m3)
        - [6-7]   : PM2.5 (conditions standard, ug/m3)
        - [8-9]   : PM10  (conditions standard, ug/m3)
        - [10-11]  : PM1.0 (conditions atmospheriques)
        - [12-13]  : PM2.5 (conditions atmospheriques)
        - [14-15]  : PM10  (conditions atmospheriques)
        - [16-29]  : Comptage de particules par taille
        - [30-31]  : Checksum

        Args:
            trame: Trame brute de 32 octets.

        Returns:
            Dictionnaire avec les valeurs PM, ou None si le checksum est invalide.
        """
        # Ici, on verifie le checksum pour s'assurer de l'integrite de la trame.
        checksum_calcule = sum(trame[:-2])
        checksum_recu = struct.unpack(">H", trame[30:32])[0]

        if checksum_calcule != checksum_recu:
            logger.warning(
                f"PMS5003 : checksum invalide "
                f"(calcule={checksum_calcule}, recu={checksum_recu})"
            )
            return None

        # Ici, on extrait les valeurs PM en conditions atmospheriques (octets 10-15).
        valeurs = struct.unpack(">HHH", trame[10:16])

        return {
            "pm1_0": valeurs[0],
            "pm2_5": valeurs[1],
            "pm10": valeurs[2],
        }

    def lire(self):
        """
        Ici, on lit les concentrations en particules fines depuis le PMS5003.

        Returns:
            Liste de dictionnaires contenant les mesures horodatees,
            ou une liste vide en cas d'erreur.
        """
        horodatage = datetime.now(timezone.utc).isoformat()

        if self.mode_simulation:
            # Ici, on genere des valeurs realistes pour le developpement.
            pm1_0 = random.randint(1, 30)
            pm2_5 = random.randint(2, 50)
            pm10 = random.randint(5, 80)
        else:
            trame = self._lire_trame()
            if trame is None:
                return []

            donnees = self._decoder_trame(trame)
            if donnees is None:
                return []

            pm1_0 = donnees["pm1_0"]
            pm2_5 = donnees["pm2_5"]
            pm10 = donnees["pm10"]

        mesures = [
            {
                "type": "pm1_0",
                "valeur": pm1_0,
                "unite": "ug/m3",
                "horodatage": horodatage,
            },
            {
                "type": "pm2_5",
                "valeur": pm2_5,
                "unite": "ug/m3",
                "horodatage": horodatage,
            },
            {
                "type": "pm10",
                "valeur": pm10,
                "unite": "ug/m3",
                "horodatage": horodatage,
            },
        ]

        logger.debug(f"PMS5003 : PM1.0={pm1_0}, PM2.5={pm2_5}, PM10={pm10} ug/m3")
        return mesures

    def fermer(self):
        """Ici, on ferme le port serie proprement."""
        if self.serial is not None:
            try:
                self.serial.close()
                logger.info("Capteur PMS5003 ferme proprement")
            except Exception as erreur:
                logger.warning(f"Erreur lors de la fermeture du PMS5003 : {erreur}")
