#!/usr/bin/env bash
set -euo pipefail

# Configure kernel parameters required by OpenSearch and recommended for Redis in WSL.
# - vm.max_map_count: required by OpenSearch (min 262144)
# - vm.overcommit_memory: recommended by Redis (1 allows memory overcommit)

require_sudo() {
  if [ "${EUID:-$(id -u)}" -ne 0 ]; then
    echo "[INFO] Root privileges are required. Re-running with sudo..."
    exec sudo --preserve-env=EUID,BASH_ENV -E "$0" "$@"
  fi
}

persist_config() {
  local key="$1"
  local value="$2"
  local conf="/etc/sysctl.d/99-osint.conf"

  if ! grep -qs "^${key}=" "$conf" 2>/dev/null; then
    echo "${key}=${value}" >> "$conf"
  else
    # Replace existing line
    sed -i "s#^${key}=.*#${key}=${value}#" "$conf"
  fi
}

main() {
  require_sudo "$@"

  echo "[INFO] Setting runtime sysctls..."
  sysctl -w vm.max_map_count=262144
  sysctl -w vm.overcommit_memory=1

  echo "[INFO] Persisting settings in /etc/sysctl.d/99-osint.conf..."
  persist_config vm.max_map_count 262144
  persist_config vm.overcommit_memory 1

  echo "[INFO] Reloading sysctl configuration..."
  sysctl --system >/dev/null

  echo "[OK] Kernel parameters configured. You can now (re)start the Docker stack."
}

main "$@"

