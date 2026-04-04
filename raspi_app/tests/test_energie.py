"""
test_energie.py -- Tests du gestionnaire d'energie.
"""

import pytest
from unittest.mock import patch, MagicMock


class TestGestionnaireEnergie:

    def test_init_intervalle_defaut(self):
        from energie.gestionnaire import GestionnaireEnergie
        import config
        g = GestionnaireEnergie()
        assert g.intervalle_actuel == config.INTERVALLE_MESURE_SECONDES

    def test_init_mode_simulation(self):
        from energie.gestionnaire import GestionnaireEnergie
        g = GestionnaireEnergie()
        assert g.mode_simulation is True  # conftest force SENTINEL_SIMULATION=true

    def test_obtenir_intervalle_retourne_valeur(self):
        from energie.gestionnaire import GestionnaireEnergie
        g = GestionnaireEnergie()
        assert g.obtenir_intervalle() == g.intervalle_actuel

    # -------------------------------------------------------------------
    # Tests d'adapter_intervalle
    # -------------------------------------------------------------------

    def test_adapter_intervalle_batterie_pleine(self):
        """Batterie > 50% -> intervalle normal."""
        from energie.gestionnaire import GestionnaireEnergie
        import config
        g = GestionnaireEnergie()
        g.adapter_intervalle(tension_batterie=4.2)  # ~100%
        assert g.intervalle_actuel == config.INTERVALLE_MESURE_SECONDES

    def test_adapter_intervalle_batterie_mi(self):
        """Batterie 25-50% -> intervalle double."""
        from energie.gestionnaire import GestionnaireEnergie
        import config
        g = GestionnaireEnergie()
        g.adapter_intervalle(tension_batterie=3.45)  # ~37.5%
        assert g.intervalle_actuel == config.INTERVALLE_MESURE_SECONDES * 2

    def test_adapter_intervalle_batterie_faible(self):
        """Batterie < 25% -> intervalle quadruple."""
        from energie.gestionnaire import GestionnaireEnergie
        import config
        g = GestionnaireEnergie()
        g.adapter_intervalle(tension_batterie=3.15)  # ~12.5%
        assert g.intervalle_actuel == config.INTERVALLE_MESURE_SECONDES * 4

    def test_adapter_intervalle_none_sans_effet(self):
        """Sans tension, l'intervalle ne change pas."""
        from energie.gestionnaire import GestionnaireEnergie
        import config
        g = GestionnaireEnergie()
        g.adapter_intervalle(tension_batterie=None)
        assert g.intervalle_actuel == config.INTERVALLE_MESURE_SECONDES

    def test_adapter_intervalle_batterie_vide(self):
        """Tension = 3.0 V -> batterie vide (0%) -> quadruple."""
        from energie.gestionnaire import GestionnaireEnergie
        import config
        g = GestionnaireEnergie()
        g.adapter_intervalle(tension_batterie=3.0)
        assert g.intervalle_actuel == config.INTERVALLE_MESURE_SECONDES * 4

    def test_adapter_intervalle_tension_trop_haute(self):
        """Tension > 4.2V -> clampe a 100% -> intervalle normal."""
        from energie.gestionnaire import GestionnaireEnergie
        import config
        g = GestionnaireEnergie()
        g.adapter_intervalle(tension_batterie=5.0)
        assert g.intervalle_actuel == config.INTERVALLE_MESURE_SECONDES

    def test_adapter_intervalle_tension_negative(self):
        """Tension negative -> clampe a 0% -> quadruple."""
        from energie.gestionnaire import GestionnaireEnergie
        import config
        g = GestionnaireEnergie()
        g.adapter_intervalle(tension_batterie=-1.0)
        assert g.intervalle_actuel == config.INTERVALLE_MESURE_SECONDES * 4

    def test_adapter_intervalle_mise_a_jour_obtenir(self):
        from energie.gestionnaire import GestionnaireEnergie
        g = GestionnaireEnergie()
        g.adapter_intervalle(tension_batterie=3.15)
        assert g.obtenir_intervalle() == g.intervalle_actuel

    # -------------------------------------------------------------------
    # Tests d'entrer_veille (mode simulation : juste time.sleep)
    # -------------------------------------------------------------------

    def test_entrer_veille_appelle_sleep(self):
        from energie.gestionnaire import GestionnaireEnergie
        import config
        g = GestionnaireEnergie()
        with patch("energie.gestionnaire.time.sleep") as mock_sleep:
            g.entrer_veille()
            mock_sleep.assert_called_once_with(config.INTERVALLE_MESURE_SECONDES)

    def test_entrer_veille_utilise_intervalle_actuel(self):
        from energie.gestionnaire import GestionnaireEnergie
        import config
        g = GestionnaireEnergie()
        g.intervalle_actuel = 999
        with patch("energie.gestionnaire.time.sleep") as mock_sleep:
            g.entrer_veille()
            mock_sleep.assert_called_once_with(999)

    def test_entrer_veille_simulation_pas_de_subprocess(self):
        """En mode simulation, aucun subprocess ne doit etre appele."""
        from energie.gestionnaire import GestionnaireEnergie
        g = GestionnaireEnergie()
        with patch("energie.gestionnaire.time.sleep"):
            with patch("subprocess.run") as mock_sub:
                g.entrer_veille()
                mock_sub.assert_not_called()

    def test_entrer_veille_deux_fois(self):
        """Deux veilles successives fonctionnent correctement."""
        from energie.gestionnaire import GestionnaireEnergie
        g = GestionnaireEnergie()
        with patch("energie.gestionnaire.time.sleep") as mock_sleep:
            g.entrer_veille()
            g.entrer_veille()
            assert mock_sleep.call_count == 2

    # -------------------------------------------------------------------
    # Tests des methodes privees (mode reel simule avec mocks)
    # -------------------------------------------------------------------

    def test_reduire_frequence_cpu_tolere_erreur(self):
        """La methode ne leve pas d'exception si subprocess echoue."""
        from energie.gestionnaire import GestionnaireEnergie
        g = GestionnaireEnergie()
        g.mode_simulation = False
        with patch("subprocess.run", side_effect=FileNotFoundError):
            g._reduire_frequence_cpu()  # Ne doit pas planter

    def test_restaurer_frequence_cpu_tolere_erreur(self):
        from energie.gestionnaire import GestionnaireEnergie
        g = GestionnaireEnergie()
        with patch("subprocess.run", side_effect=FileNotFoundError):
            g._restaurer_frequence_cpu()  # Ne doit pas planter

    def test_desactiver_leds_tolere_erreur(self):
        from energie.gestionnaire import GestionnaireEnergie
        g = GestionnaireEnergie()
        with patch("builtins.open", side_effect=FileNotFoundError):
            g._desactiver_leds()  # Ne doit pas planter

    def test_desactiver_leds_tolere_permission_error(self):
        from energie.gestionnaire import GestionnaireEnergie
        g = GestionnaireEnergie()
        with patch("builtins.open", side_effect=PermissionError):
            g._desactiver_leds()  # Ne doit pas planter
