#!/usr/bin/env bash
# =============================================================================
# run.sh -- Lancer la sentinelle (ou les tests)
#
# Usage :
#   bash run.sh                    # Lancer en mode simulation
#   bash run.sh --reel             # Lancer en mode réel (Raspberry Pi)
#   bash run.sh --id sentinelle-42 # Identifiant personnalisé
#   bash run.sh --test             # Lancer tous les tests (310 tests)
#   bash run.sh --test -v          # Tests en mode verbeux
# =============================================================================

set -e

GRAS='\033[1m'; VERT='\033[0;32m'; BLEU='\033[0;34m'; RESET='\033[0m'
info() { echo -e "  ${BLEU}[INFO]${RESET} $1"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RASPI_DIR="$SCRIPT_DIR/raspi_app"
VENV_DIR="$RASPI_DIR/.venv"

# Vérifier que bootstrap a été lancé
if [ ! -d "$VENV_DIR" ]; then
    echo -e "  ${GRAS}Environnement non configuré. Lancez d'abord :${RESET}"
    echo -e "    bash bootstrap.sh"
    exit 1
fi

# Activer le venv
if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" || "$OSTYPE" == "cygwin" ]]; then
    source "$VENV_DIR/Scripts/activate"
else
    source "$VENV_DIR/bin/activate"
fi

cd "$RASPI_DIR"

# ---------------------------------------------------------------------------
# Arguments
# ---------------------------------------------------------------------------
MODE_REEL=false
MODE_TEST=false
PYTEST_ARGS=""
SENTINEL_ID="${SENTINEL_ID:-sentinelle-001}"

while [[ $# -gt 0 ]]; do
    case $1 in
        --reel)  MODE_REEL=true; shift ;;
        --test)  MODE_TEST=true; shift ;;
        --id)    SENTINEL_ID="$2"; shift 2 ;;
        -v|--verbose) PYTEST_ARGS="-v"; shift ;;
        *) PYTEST_ARGS="$PYTEST_ARGS $1"; shift ;;
    esac
done

# ---------------------------------------------------------------------------
# Mode test
# ---------------------------------------------------------------------------
if $MODE_TEST; then
    echo ""
    echo -e "${GRAS}>>> Lancement des tests (310 tests)...${RESET}"
    echo ""
    python -m pytest tests/ $PYTEST_ARGS
    exit $?
fi

# ---------------------------------------------------------------------------
# Mode simulation ou réel
# ---------------------------------------------------------------------------
echo ""
if $MODE_REEL; then
    echo -e "${GRAS}>>> Lancement de la sentinelle (mode réel)...${RESET}"
    info "Sentinel ID : $SENTINEL_ID"
    info "Capteurs physiques actifs"
    echo ""
    SENTINEL_ID="$SENTINEL_ID" SENTINEL_SIMULATION=false python main.py
else
    echo -e "${GRAS}>>> Lancement de la sentinelle (mode simulation)...${RESET}"
    info "Sentinel ID : $SENTINEL_ID"
    info "Données simulées (pas de capteurs requis)"
    echo ""
    SENTINEL_ID="$SENTINEL_ID" python main.py
fi
