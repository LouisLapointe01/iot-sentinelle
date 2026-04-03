"""
gestionnaire.py -- Gestion de l'optimisation energetique de la sentinelle.

Ici, on implemente les strategies logicielles d'economie d'energie pour
maximiser l'autonomie de la sentinelle deployee sur batterie en zone isolee.

Le CDC specifie :
- Consommation < 50 mA en phase active
- Consommation < 50 uA en mode veille (idealement ~1.5 mA pour le Raspberry Pi)

Strategies implementees :
1. Mise en veille des capteurs entre les cycles de mesure
2. Reduction de la frequence CPU entre les mesures
3. Desactivation des LEDs
4. Adaptation dynamique de l'intervalle selon le niveau de batterie
"""

import logging
import time
import subprocess

import config

logger = logging.getLogger(__name__)


class GestionnaireEnergie:
    """
    Classe gerant l'optimisation energetique de la sentinelle.
    """

    def __init__(self):
        self.mode_simulation = config.MODE_SIMULATION
        self.intervalle_actuel = config.INTERVALLE_MESURE_SECONDES
        logger.info(f"GestionnaireEnergie : intervalle={self.intervalle_actuel}s")

    def entrer_veille(self):
        """
        Ici, on met la sentinelle en mode veille entre deux cycles de mesure.
        Sur Raspberry Pi, le processeur passe en idle, reduisant la consommation
        de ~500 mA (pleine charge) a ~200 mA (idle).
        """
        if not self.mode_simulation:
            self._reduire_frequence_cpu()
            self._desactiver_leds()

        logger.debug(f"Entree en veille pour {self.intervalle_actuel} secondes")
        time.sleep(self.intervalle_actuel)
        logger.debug("Sortie de veille")

        if not self.mode_simulation:
            self._restaurer_frequence_cpu()

    def _reduire_frequence_cpu(self):
        """Ici, on passe le gouverneur CPU en mode powersave."""
        try:
            subprocess.run(
                ["sudo", "cpufreq-set", "-g", "powersave"],
                capture_output=True, timeout=5,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

    def _restaurer_frequence_cpu(self):
        """Ici, on restaure le gouverneur CPU en mode ondemand."""
        try:
            subprocess.run(
                ["sudo", "cpufreq-set", "-g", "ondemand"],
                capture_output=True, timeout=5,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

    def _desactiver_leds(self):
        """Ici, on desactive les LEDs du Raspberry Pi (~5 mA d'economie)."""
        try:
            with open("/sys/class/leds/led0/brightness", "w") as f:
                f.write("0")
            with open("/sys/class/leds/led1/brightness", "w") as f:
                f.write("0")
        except (FileNotFoundError, PermissionError):
            pass

    def adapter_intervalle(self, tension_batterie=None):
        """
        Ici, on adapte l'intervalle de mesure selon le niveau de batterie.
        - Batterie > 50% : intervalle normal (300s)
        - Batterie 25-50% : double (600s)
        - Batterie < 25%  : quadruple (1200s)
        """
        if tension_batterie is None:
            return

        pourcentage = max(0, min(100, (tension_batterie - 3.0) / 1.2 * 100))

        if pourcentage > 50:
            self.intervalle_actuel = config.INTERVALLE_MESURE_SECONDES
        elif pourcentage > 25:
            self.intervalle_actuel = config.INTERVALLE_MESURE_SECONDES * 2
        else:
            self.intervalle_actuel = config.INTERVALLE_MESURE_SECONDES * 4

        logger.info(
            f"Batterie ~{pourcentage:.0f}% : intervalle={self.intervalle_actuel}s"
        )

    def obtenir_intervalle(self):
        return self.intervalle_actuel
