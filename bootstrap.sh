#!/usr/bin/env bash
# =============================================================================
# bootstrap.sh -- Installation COMPLETE en une seule commande
#
# Usage :
#   bash bootstrap.sh              # Mode simulation (PC sans capteurs)
#   bash bootstrap.sh --reel       # Mode reel (Raspberry Pi avec capteurs)
#   bash bootstrap.sh --id XYZ     # ID personnalise (ex: sentinelle-042)
#   bash bootstrap.sh --lancer     # Installer ET lancer immédiatement
#
# Ce script fait tout :
#   1. Vérifie Python 3.10+
#   2. Crée l'environnement virtuel
#   3. Installe toutes les dépendances
#   4. Génère les clés AES-256 et ECDSA P-256
#   5. Génère le QR code
#   6. Affiche un résumé et les commandes pour démarrer
# =============================================================================

set -e

# ---------------------------------------------------------------------------
# Couleurs terminal
# ---------------------------------------------------------------------------
ROUGE='\033[0;31m'
VERT='\033[0;32m'
JAUNE='\033[1;33m'
BLEU='\033[0;34m'
GRAS='\033[1m'
RESET='\033[0m'

ok()   { echo -e "  ${VERT}[OK]${RESET} $1"; }
err()  { echo -e "  ${ROUGE}[ERREUR]${RESET} $1"; }
info() { echo -e "  ${BLEU}[INFO]${RESET} $1"; }
step() { echo -e "\n${GRAS}$1${RESET}"; }

# ---------------------------------------------------------------------------
# Arguments
# ---------------------------------------------------------------------------
SENTINEL_ID="sentinelle-001"
MODE_REEL=false
LANCER=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --reel)    MODE_REEL=true; shift ;;
        --id)      SENTINEL_ID="$2"; shift 2 ;;
        --lancer)  LANCER=true; shift ;;
        -h|--help)
            echo "Usage: bash bootstrap.sh [--reel] [--id <sentinel_id>] [--lancer]"
            exit 0 ;;
        *)
            err "Option inconnue : $1"
            echo "Utiliser --help pour l'aide"
            exit 1 ;;
    esac
done

# ---------------------------------------------------------------------------
# Bannière
# ---------------------------------------------------------------------------
echo ""
echo -e "${GRAS}=========================================${RESET}"
echo -e "${GRAS}   IoT-Sentinelle -- Installation auto${RESET}"
echo -e "${GRAS}=========================================${RESET}"
echo ""
info "Sentinel ID : ${SENTINEL_ID}"
if $MODE_REEL; then
    info "Mode : Réel (Raspberry Pi)"
else
    info "Mode : Simulation (PC)"
fi
echo ""

# ---------------------------------------------------------------------------
# Étape 1 : Python 3.10+
# ---------------------------------------------------------------------------
step "Étape 1/5 : Vérification Python"

PYTHON_CMD=""
for cmd in python3 python python3.12 python3.11 python3.10; do
    if command -v "$cmd" &>/dev/null; then
        VERSION=$($cmd -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null)
        MAJOR=$(echo "$VERSION" | cut -d. -f1)
        MINOR=$(echo "$VERSION" | cut -d. -f2)
        if [ "$MAJOR" -ge 3 ] && [ "$MINOR" -ge 10 ]; then
            PYTHON_CMD="$cmd"
            ok "Python $VERSION trouvé ($cmd)"
            break
        fi
    fi
done

if [ -z "$PYTHON_CMD" ]; then
    err "Python 3.10+ requis. Installer depuis https://python.org"
    exit 1
fi

# ---------------------------------------------------------------------------
# Étape 2 : Environnement virtuel
# ---------------------------------------------------------------------------
step "Étape 2/5 : Environnement virtuel"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RASPI_DIR="$SCRIPT_DIR/raspi_app"
VENV_DIR="$RASPI_DIR/.venv"

if [ -d "$VENV_DIR" ]; then
    ok "Environnement virtuel existant réutilisé"
else
    info "Création de l'environnement virtuel..."
    $PYTHON_CMD -m venv "$VENV_DIR"
    ok "Environnement virtuel créé dans raspi_app/.venv"
fi

# Activer le venv
if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" || "$OSTYPE" == "cygwin" ]]; then
    ACTIVATE="$VENV_DIR/Scripts/activate"
else
    ACTIVATE="$VENV_DIR/bin/activate"
fi

source "$ACTIVATE"
ok "Environnement virtuel activé"

# ---------------------------------------------------------------------------
# Étape 3 : Dépendances pip
# ---------------------------------------------------------------------------
step "Étape 3/5 : Installation des dépendances"

info "Installation de pycryptodome, qrcode..."
pip install -r "$RASPI_DIR/requirements.txt" -q
ok "Dépendances installées"

# Sur Raspberry Pi réel : installer les dépendances système BLE
if $MODE_REEL; then
    info "Mode réel : vérification des dépendances BLE système..."
    if command -v apt-get &>/dev/null; then
        info "Installation des paquets système BLE (sudo requis)..."
        sudo apt-get install -y python3-dbus python3-gi libglib2.0-dev 2>/dev/null \
            && ok "Dépendances BLE système installées" \
            || info "Installer manuellement : sudo apt-get install python3-dbus python3-gi libglib2.0-dev"
    fi
fi

# ---------------------------------------------------------------------------
# Étape 4 : Clés cryptographiques + QR code
# ---------------------------------------------------------------------------
step "Étape 4/5 : Génération des clés et QR code"

cd "$RASPI_DIR"
SENTINEL_ID="$SENTINEL_ID" python installer.py --no-deps

# ---------------------------------------------------------------------------
# Étape 5 : Vérification finale
# ---------------------------------------------------------------------------
step "Étape 5/5 : Vérification du système"

SENTINEL_ID="$SENTINEL_ID" python installer.py --check

# ---------------------------------------------------------------------------
# Résumé
# ---------------------------------------------------------------------------
echo ""
echo -e "${GRAS}=========================================${RESET}"
echo -e "${VERT}${GRAS}   Installation terminée avec succès !${RESET}"
echo -e "${GRAS}=========================================${RESET}"
echo ""
echo -e "  Pour lancer la sentinelle :"
echo ""
if $MODE_REEL; then
    echo -e "    ${GRAS}bash run.sh --reel --id ${SENTINEL_ID}${RESET}"
else
    echo -e "    ${GRAS}bash run.sh${RESET}"
fi
echo ""
echo -e "  Pour lancer les tests :"
echo -e "    ${GRAS}bash run.sh --test${RESET}"
echo ""

# ---------------------------------------------------------------------------
# Lancement automatique si demandé
# ---------------------------------------------------------------------------
if $LANCER; then
    echo ""
    info "Lancement de la sentinelle..."
    if $MODE_REEL; then
        SENTINEL_ID="$SENTINEL_ID" SENTINEL_SIMULATION=false python main.py
    else
        SENTINEL_ID="$SENTINEL_ID" python main.py
    fi
fi
