# =============================================================================
# Makefile -- IoT-Sentinelle : commandes simplifiées
#
# Usage :
#   make setup        Installation complète de la sentinelle (Pi)
#   make run          Lancer la sentinelle
#   make test         Tests Python (185 tests)
#   make apk          Compiler l'APK Android
#   make test-mobile  Tests Jest (mobile)
#   make clean        Supprimer les fichiers temporaires
#   make help         Afficher cette aide
# =============================================================================

PYTHON   := python
PIP      := $(PYTHON) -m pip
PYTEST   := $(PYTHON) -m pytest
NPM      := npm

RASPI    := raspi_app
MOBILE   := mobile_app

.PHONY: help setup run test test-v qrcode apk test-mobile clean

# Cible par défaut
help:
	@echo ""
	@echo "  IoT-Sentinelle -- Commandes disponibles"
	@echo "  ========================================"
	@echo ""
	@echo "  RASPBERRY PI"
	@echo "  make setup        Installation complete (deps + cles + QR code)"
	@echo "  make run          Lancer la sentinelle (mode simulation)"
	@echo "  make run-reel     Lancer la sentinelle (mode reel - Pi uniquement)"
	@echo "  make qrcode       Regenerer le QR code de deploiement"
	@echo "  make test         Tous les tests Python (185 tests)"
	@echo "  make test-v       Tests Python (mode verbose)"
	@echo ""
	@echo "  APPLICATION MOBILE"
	@echo "  make install-mobile  Installer les dependances npm"
	@echo "  make apk             Compiler l'APK Android"
	@echo "  make test-mobile     Tests Jest"
	@echo ""
	@echo "  UTILITAIRES"
	@echo "  make check        Verifier l'etat du systeme"
	@echo "  make clean        Supprimer les fichiers temporaires"
	@echo ""

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
	cd $(RASPI) && $(PYTHON) main.py

run-reel:
	@echo "\n>>> Lancement en mode reel (Raspberry Pi)...\n"
	cd $(RASPI) && SENTINEL_SIMULATION=false $(PYTHON) main.py

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
	@echo "\n>>> Tests Python...\n"
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
	@echo "\n>>> Compilation de l'APK Android...\n"
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
