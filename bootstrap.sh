#!/usr/bin/env bash
# =============================================================================
# bootstrap.sh -- Installation COMPLETE en une seule commande
#
# Usage :
#   bash bootstrap.sh              # Mode simulation (PC sans capteurs)
#   bash bootstrap.sh --reel       # Mode reel (Raspberry Pi avec capteurs)
#   bash bootstrap.sh --id XYZ     # ID personnalise (ex: sentinelle-042)
#   bash bootstrap.sh --lancer     # Installer ET lancer immediatement
#
# Ce script fait tout :
#   1. Verifie Python 3.10+
#   2. Installe les dependances systeme BLE (apt)
#   3. Configure et active le Bluetooth
#   4. Cree l'environnement virtuel (--system-site-packages pour BLE)
#   5. Installe les dependances pip
#   6. Genere les cles AES-256 et ECDSA P-256
#   7. Genere le QR code
#   8. Affiche les commandes pour demarrer
# =============================================================================

set -e

ROUGE='\033[0;31m'
VERT='\033[0;32m'
JAUNE='\033[1;33m'
BLEU='\033[0;34m'
GRAS='\033[1m'
RESET='\033[0m'

ok()   { echo -e "  ${VERT}[OK]${RESET} $1"; }
err()  { echo -e "  ${ROUGE}[ERREUR]${RESET} $1"; exit 1; }
warn() { echo -e "  ${JAUNE}[WARN]${RESET} $1"; }
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
            warn "Option inconnue : $1"
            shift ;;
    esac
done

# ---------------------------------------------------------------------------
# Banniere
# ---------------------------------------------------------------------------
echo ""
echo -e "${GRAS}=========================================${RESET}"
echo -e "${GRAS}   IoT-Sentinelle -- Installation auto  ${RESET}"
echo -e "${GRAS}=========================================${RESET}"
echo ""
info "Sentinel ID : ${SENTINEL_ID}"
$MODE_REEL && info "Mode : Reel (Raspberry Pi)" || info "Mode : Simulation (PC)"
echo ""

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RASPI_DIR="$SCRIPT_DIR/raspi_app"
VENV_DIR="$RASPI_DIR/.venv"

# ---------------------------------------------------------------------------
# Etape 1 : Python 3.10+
# ---------------------------------------------------------------------------
step "Etape 1/6 : Verification Python"

PYTHON_CMD=""
for cmd in python3 python python3.12 python3.11 python3.10; do
    if command -v "$cmd" &>/dev/null; then
        VERSION=$($cmd -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null)
        MAJOR=$(echo "$VERSION" | cut -d. -f1)
        MINOR=$(echo "$VERSION" | cut -d. -f2)
        if [ "$MAJOR" -ge 3 ] && [ "$MINOR" -ge 10 ]; then
            PYTHON_CMD="$cmd"
            ok "Python $VERSION trouve ($cmd)"
            break
        fi
    fi
done

[ -z "$PYTHON_CMD" ] && err "Python 3.10+ requis. Installer depuis https://python.org"

# ---------------------------------------------------------------------------
# Etape 2 : Dependances systeme BLE (Raspberry Pi uniquement)
# ---------------------------------------------------------------------------
step "Etape 2/6 : Dependances systeme"

if command -v apt-get &>/dev/null; then
    info "Installation des paquets systeme BLE..."
    sudo apt-get update -qq
    sudo apt-get install -y python3-dbus python3-gi libglib2.0-dev bluetooth bluez -qq
    ok "Paquets systeme installes (python3-dbus, python3-gi, bluetooth, bluez)"
else
    warn "apt-get non disponible -- paquets BLE systeme non installes (normal sur PC)"
fi

# ---------------------------------------------------------------------------
# Etape 3 : Configuration Bluetooth
# ---------------------------------------------------------------------------
step "Etape 3/6 : Configuration Bluetooth"

if command -v bluetoothctl &>/dev/null; then
    # Debloquer rfkill si necessaire
    if command -v rfkill &>/dev/null; then
        sudo rfkill unblock bluetooth 2>/dev/null && ok "rfkill : Bluetooth debloque" || true
    fi

    # Activer et demarrer le service
    sudo systemctl enable bluetooth 2>/dev/null || true
    sudo systemctl start bluetooth 2>/dev/null || true

    # Configurer l'adaptateur
    sleep 1
    sudo bluetoothctl power on 2>/dev/null || true
    sudo bluetoothctl discoverable-timeout 0 2>/dev/null || true
    sudo bluetoothctl discoverable on 2>/dev/null || true
    sudo bluetoothctl pairable on 2>/dev/null || true

    POWERED=$(sudo bluetoothctl show 2>/dev/null | grep "Powered:" | awk '{print $2}')
    if [ "$POWERED" = "yes" ]; then
        ok "Bluetooth actif et decouvrabe"
    else
        warn "Bluetooth non disponible sur ce systeme"
    fi
else
    warn "bluetoothctl non disponible -- configuration Bluetooth ignoree"
fi

# ---------------------------------------------------------------------------
# Etape 4 : Environnement virtuel
# ---------------------------------------------------------------------------
step "Etape 4/6 : Environnement virtuel"

if [ -d "$VENV_DIR" ]; then
    ok "Environnement virtuel existant reutilise"
else
    info "Creation du venv avec --system-site-packages (requis pour BLE)..."
    $PYTHON_CMD -m venv "$VENV_DIR" --system-site-packages
    ok "Environnement virtuel cree dans raspi_app/.venv"
fi

if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" || "$OSTYPE" == "cygwin" ]]; then
    ACTIVATE="$VENV_DIR/Scripts/activate"
else
    ACTIVATE="$VENV_DIR/bin/activate"
fi

source "$ACTIVATE"
ok "Environnement virtuel active"

# ---------------------------------------------------------------------------
# Etape 5 : Dependances pip
# ---------------------------------------------------------------------------
step "Etape 5/6 : Installation des dependances pip"

pip install -r "$RASPI_DIR/requirements.txt" -q
ok "Dependances pip installees (pycryptodome, qrcode...)"

# Verifier que dbus est accessible depuis le venv
if $PYTHON_CMD -c "import dbus" 2>/dev/null; then
    ok "dbus accessible depuis le venv (BLE fonctionnel)"
else
    warn "dbus non accessible -- le serveur BLE tournera en mode simulation"
    warn "Solution : sudo apt install python3-dbus python3-gi && recreer le venv"
fi

# ---------------------------------------------------------------------------
# Etape 6 : Cles cryptographiques + QR code
# ---------------------------------------------------------------------------
step "Etape 6/6 : Generation des cles et QR code"

cd "$RASPI_DIR"
SENTINEL_ID="$SENTINEL_ID" $PYTHON_CMD installer.py --no-deps
ok "Cles AES-256 et ECDSA P-256 generees"
ok "QR code genere : raspi_app/qrcode_${SENTINEL_ID}.png"

# ---------------------------------------------------------------------------
# Resume
# ---------------------------------------------------------------------------
echo ""
echo -e "${GRAS}=========================================${RESET}"
echo -e "${VERT}${GRAS}   Installation terminee avec succes !  ${RESET}"
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
echo -e "  QR code a coller sur le boitier :"
echo -e "    ${GRAS}raspi_app/qrcode_${SENTINEL_ID}.png${RESET}"
echo ""

# ---------------------------------------------------------------------------
# Lancement automatique si demande
# ---------------------------------------------------------------------------
if $LANCER; then
    info "Lancement de la sentinelle..."
    bash "$SCRIPT_DIR/run.sh" $($MODE_REEL && echo "--reel") --id "$SENTINEL_ID"
fi
