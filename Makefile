# =============================================================================
# Makefile -- IoT-Sentinelle : commandes simplifiées
#
# Usage rapide (UN SEUL COMMANDE) :
#   make bootstrap    Installation complète (venv + deps + clés + QR code)
#   make run          Lancer la sentinelle (simulation)
#   make test         Tous les tests Python (310 tests)
# =============================================================================

PYTHON   := python
PIP      := $(PYTHON) -m pip
PYTEST   := $(PYTHON) -m pytest
NPM      := npm

RASPI    := raspi_app
MOBILE   := mobile_app

# Venv (créé par bootstrap.sh)
VENV_PYTHON := $(RASPI)/.venv/bin/python
VENV_PYTEST := $(RASPI)/.venv/bin/python -m pytest
# Sur Windows avec Git Bash :
ifeq ($(OS),Windows_NT)
	VENV_PYTHON := $(RASPI)/.venv/Scripts/python
	VENV_PYTEST := $(RASPI)/.venv/Scripts/python -m pytest
endif

.PHONY: help bootstrap setup run run-reel test test-v qrcode apk test-mobile clean check

# Cible par défaut
help:
	@echo ""
	@echo "  IoT-Sentinelle -- Commandes disponibles"
	@echo "  ========================================"
	@echo ""
	@echo "  DÉMARRAGE RAPIDE (une seule commande)"
	@echo "  make bootstrap    Installation complete + venv + cles + QR code"
	@echo "  make run          Lancer (simulation, venv auto-détecté)"
	@echo "  make test         Tous les tests Python (310 tests)"
	@echo ""
	@echo "  RASPBERRY PI"
	@echo "  make setup        Installation sans venv (si déjà activé)"
	@echo "  make run-reel     Lancer en mode reel (Pi + capteurs physiques)"
	@echo "  make run-start    Setup + lancement immédiat"
	@echo "  make qrcode       Regenerer le QR code de deploiement"
	@echo "  make check        Verifier l'etat du systeme"
	@echo "  make test-v       Tests Python (mode verbose)"
	@echo ""
	@echo "  APPLICATION MOBILE"
	@echo "  make install-mobile  Installer les dependances npm"
	@echo "  make apk             Compiler l'APK Android (local)"
	@echo "  make test-mobile     Tests Jest"
	@echo ""
	@echo "  UTILITAIRES"
	@echo "  make clean        Supprimer les fichiers temporaires"
	@echo ""

# ---------------------------------------------------------------------------
# DÉMARRAGE RAPIDE
# ---------------------------------------------------------------------------

bootstrap:
	@echo "\n>>> Installation complète (venv + deps + clés + QR code)...\n"
	bash bootstrap.sh

bootstrap-reel:
	@echo "\n>>> Installation complète en mode réel (Raspberry Pi)...\n"
	bash bootstrap.sh --reel

# ---------------------------------------------------------------------------
# RASPBERRY PI
# ---------------------------------------------------------------------------

setup:
	@echo "\n>>> Installation de la sentinelle...\n"
	cd $(RASPI) && $(PYTHON) installer.py

setup-no-deps:
	@echo "\n>>> Setup sans reinstallation pip...\n"
	cd $(RASPI) && $(PYTHON) installer.py --no-deps

run:
	@echo "\n>>> Lancement en mode simulation...\n"
	bash run.sh

run-reel:
	@echo "\n>>> Lancement en mode reel (Raspberry Pi)...\n"
	bash run.sh --reel

run-start:
	@echo "\n>>> Setup + lancement automatique...\n"
	cd $(RASPI) && $(PYTHON) installer.py --start

qrcode:
	@echo "\n>>> Generation du QR code...\n"
	cd $(RASPI) && $(PYTHON) utils/qrcode_gen.py

check:
	@echo "\n>>> Verification de l'etat du systeme...\n"
	cd $(RASPI) && $(PYTHON) installer.py --check

test:
	@echo "\n>>> Tests Python (310 tests)...\n"
	cd $(RASPI) && $(PYTEST) tests/ --tb=short -q

test-v:
	@echo "\n>>> Tests Python (verbose)...\n"
	cd $(RASPI) && $(PYTEST) tests/ -v

test-installer:
	@echo "\n>>> Tests de l'installateur...\n"
	cd $(RASPI) && $(PYTEST) tests/test_installer.py -v

# ---------------------------------------------------------------------------
# APPLICATION MOBILE
# ---------------------------------------------------------------------------

install-mobile:
	@echo "\n>>> Installation des dependances npm...\n"
	cd $(MOBILE) && $(NPM) install

apk:
	@echo "\n>>> Compilation de l'APK Android (local)...\n"
	cd $(MOBILE) && $(NPM) run apk

test-mobile:
	@echo "\n>>> Tests Jest...\n"
	cd $(MOBILE) && $(NPM) test -- --passWithNoTests

test-mobile-v:
	@echo "\n>>> Tests Jest (verbose)...\n"
	cd $(MOBILE) && $(NPM) test -- --verbose

# ---------------------------------------------------------------------------
# UTILITAIRES
# ---------------------------------------------------------------------------

clean:
	@echo "\n>>> Nettoyage...\n"
	find $(RASPI) -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find $(RASPI) -name "*.pyc" -delete 2>/dev/null || true
	find $(RASPI) -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	@echo "  Nettoyage termine."
