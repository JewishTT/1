#!/usr/bin/env bash
set -euo pipefail

# --- Defaults ---
CFG="./config/searxng-settings.yml"
SERVICE="searxng"
ENGINE_BASE_OK=("duckduckgo" "wikipedia")
CANDIDATES=(mojeek stackexchange github reddit reuters openverse svgrepo wikicommons vimeo dailymotion openstreetmap photon openmeteo wttr)

usage() {
  cat <<EOF
Usage: $0 [-c PATH_TO_SETTINGS] [-s SERVICE_NAME]
  -c  Path to searxng settings.yml (default: ./config/searxng-settings.yml)
  -s  Docker Compose service name (default: searxng)
EOF
}

while getopts ":c:s:h" opt; do
  case "$opt" in
    c) CFG="$OPTARG" ;;
    s) SERVICE="$OPTARG" ;;
    h) usage; exit 0 ;;
    \?) echo "Invalid option: -$OPTARG" >&2; usage; exit 1 ;;
  esac
done

# --- Normalize paths (absolute) ---
if command -v readlink >/dev/null 2>&1; then
  CFG="$(readlink -f "$CFG" 2>/dev/null || realpath "$CFG")"
else
  # Busy fallback: turn relative into absolute
  case "$CFG" in /*) ;; *) CFG="$PWD/$CFG" ;; esac
fi

[[ -f "$CFG" ]] || { echo "Settings not found: $CFG"; exit 1; }
CFG_DIR="$(dirname "$CFG")"
CFG_BASENAME="$(basename "$CFG")"

need() { command -v "$1" >/dev/null 2>&1 || { echo "Missing $1"; exit 1; }; }
need docker
need curl
python - <<<'print()' >/dev/null 2>&1 || { echo "Missing Python"; exit 1; }

# --- yq wrapper (local or container) ---
yqcmd() {
  if command -v yq >/dev/null 2>&1; then
    yq "$@"
  else
    docker run --rm -v "$CFG_DIR:/w" -w /w mikefarah/yq:latest "$@"
  fi
}

# --- Helpers ---
set_engine_disabled() {
  local name="$1" val="$2"   # true|false
  yqcmd eval -i ".engines |= map( if .name == \"$name\" then .disabled = $val else . end )" "$CFG_BASENAME"
}

disable_all_except_base() {
  yqcmd eval -i '.engines |= map(.disabled = true)' "$CFG_BASENAME"
  for n in "${ENGINE_BASE_OK[@]}"; do set_engine_disabled "$n" false; done
}

compose_cycle() {
  docker compose down -v --remove-orphans
  docker compose up -d --build --wait "$SERVICE"
  docker compose ps
  docker inspect --format '{{.State.Health.Status}}' "$SERVICE" 2>/dev/null || true
}

smoke_test() {
  # απλός JSON έλεγχος στις ενεργές default engines
  curl -sS "http://localhost:8081/search?q=athens&format=json" \
  | python - <<'PY'
import sys, json
try:
    data=json.load(sys.stdin)
    print("OK", len(data.get("results",[])))
except Exception as e:
    print("FAIL", e)
    sys.exit(1)
PY
}

# --- Checks & normalize ---
echo "[*] Checking YAML top-level type..."
TYPE=$(yqcmd eval 'type' "$CFG_BASENAME" | tr -d '\r')
[[ "$TYPE" == "!!map" ]] || { echo "Top-level YAML is not a map (got $TYPE)"; exit 1; }

echo "[*] Normalizing null/absent sections..."
for k in general server botdetection ui outgoing search; do
  yqcmd eval -i ".${k} = (.${k} // {})" "$CFG_BASENAME"
done
yqcmd eval -i '.engines = (.engines // [])' "$CFG_BASENAME"

echo "[*] Disable all engines except base..."
disable_all_except_base

PASS=()
FAIL=()

echo "[*] Baseline compose..."
compose_cycle
echo "[*] Baseline smoke test..."
smoke_test

for eng in "${CANDIDATES[@]}"; do
  echo
  echo "=== PROBE: $eng ==="
  set_engine_disabled "$eng" false
  if ! compose_cycle; then
    echo "[!] compose failed for $eng"
    set_engine_disabled "$eng" true
    FAIL+=("$eng")
    continue
  fi
  if smoke_test; then
    echo "[+] $eng: OK"
    PASS+=("$eng")
  else
    echo "[-] $eng: FAIL"
    set_engine_disabled "$eng" true
    FAIL+=("$eng")
  fi
done

echo
echo "=========== SUMMARY ==========="
echo "PASS: ${PASS[*]:-none}"
echo "FAIL: ${FAIL[*]:-none}"
echo "Final YAML saved at $CFG"
