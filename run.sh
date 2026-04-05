#!/usr/bin/env bash
# =============================================================================
# run.sh -- Lancer la sentinelle (ou les tests)
#
# Usage :
#   bash run.sh                    # Lancer en mode simulation
#   bash run.sh --reel             # Lancer en mode reel (Raspberry Pi)
#   bash run.sh --id sentinelle-42 # Identifiant personnalise
#   bash run.sh --test             # Lancer tous les tests
#   bash run.sh --background       # Lancer en arriere-plan (nohup)
# =============================================================================

set -e

GRAS='\033[1m'; VERT='\033[0;32m'; BLEU='\033[0;34m'; JAUNE='\033[1;33m'; RESET='\033[0m'
info() { echo -e "  ${BLEU}[INFO]${RESET} $1"; }
ok()   { echo -e "  ${VERT}[OK]${RESET} $1"; }
warn() { echo -e "  ${JAUNE}[WARN]${RESET} $1"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RASPI_DIR="$SCRIPT_DIR/raspi_app"
VENV_DIR="$RASPI_DIR/.venv"
PYTHON="$VENV_DIR/bin/python"

# Verifier que bootstrap a ete lance
if [ ! -d "$VENV_DIR" ]; then
    echo -e "  ${GRAS}Environnement non configure. Lancez d'abord :${RESET}"
    echo -e "    bash bootstrap.sh"
    exit 1
fi

# ---------------------------------------------------------------------------
# Arguments
# ---------------------------------------------------------------------------
MODE_REEL=false
MODE_TEST=false
MODE_BACKGROUND=false
PYTEST_ARGS=""
SENTINEL_ID="${SENTINEL_ID:-sentinelle-001}"

while [[ $# -gt 0 ]]; do
    case $1 in
        --reel)       MODE_REEL=true; shift ;;
        --test)       MODE_TEST=true; shift ;;
        --background) MODE_BACKGROUND=true; shift ;;
        --id)         SENTINEL_ID="$2"; shift 2 ;;
        -v|--verbose) PYTEST_ARGS="-v"; shift ;;
        *) PYTEST_ARGS="$PYTEST_ARGS $1"; shift ;;
    esac
done

cd "$RASPI_DIR"

# ---------------------------------------------------------------------------
# Mode test
# ---------------------------------------------------------------------------
if $MODE_TEST; then
    echo ""
    echo -e "${GRAS}>>> Lancement des tests...${RESET}"
    echo ""
    source "$VENV_DIR/bin/activate"
    python -m pytest tests/ $PYTEST_ARGS
    exit $?
fi

# ---------------------------------------------------------------------------
# Re-executer avec sudo si necessaire (requis pour BLE GATT)
# ---------------------------------------------------------------------------
if [ "$EUID" -ne 0 ]; then
    warn "Le serveur BLE necessite sudo. Re-lancement avec sudo..."
    exec sudo bash "$SCRIPT_DIR/run.sh" \
        $($MODE_REEL && echo "--reel") \
        $($MODE_BACKGROUND && echo "--background") \
        --id "$SENTINEL_ID"
fi

# ---------------------------------------------------------------------------
# S'assurer que le Bluetooth est actif
# ---------------------------------------------------------------------------
if command -v bluetoothctl &>/dev/null; then
    rfkill unblock bluetooth 2>/dev/null || true
    bluetoothctl power on 2>/dev/null || true
    bluetoothctl discoverable-timeout 0 2>/dev/null || true
    bluetoothctl discoverable on 2>/dev/null || true
    POWERED=$(bluetoothctl show 2>/dev/null | grep "Powered:" | awk '{print $2}')
    [ "$POWERED" = "yes" ] && ok "Bluetooth actif" || warn "Bluetooth non disponible"
fi

# ---------------------------------------------------------------------------
# Lancement
# ---------------------------------------------------------------------------
echo ""
if $MODE_REEL; then
    echo -e "${GRAS}>>> Lancement de la sentinelle (mode reel)...${RESET}"
    info "Sentinel ID : $SENTINEL_ID"
    export SENTINEL_ID SENTINEL_SIMULATION=false
else
    echo -e "${GRAS}>>> Lancement de la sentinelle (mode simulation)...${RESET}"
    info "Sentinel ID : $SENTINEL_ID"
    export SENTINEL_ID
fi
echo ""

LOG_FILE="$RASPI_DIR/raspi.log"

if $MODE_BACKGROUND; then
    nohup "$PYTHON" main.py > "$LOG_FILE" 2>&1 &
    PID=$!
    ok "Sentinelle lancee en arriere-plan (PID $PID)"
    info "Logs : tail -f $LOG_FILE"
    info "Arreter : sudo kill $PID"
else
    "$PYTHON" main.py
fi
