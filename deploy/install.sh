#!/usr/bin/env bash
set -euo pipefail

bundle_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
app_dir="/opt/prayerhub"
config_dir="/etc/prayerhub"
service_file="/etc/systemd/system/prayerhub.service"
service_user="${PRAYERHUB_USER:-${SUDO_USER:-pi}}"

mkdir -p "$app_dir" "$config_dir"

# Install system packages once to keep audio and Bluetooth available.
if command -v apt-get >/dev/null 2>&1; then
  apt-get update
  apt-get install -y mpg123 bluez
fi

# Reuse the virtualenv if present so re-running install stays fast.
if [ ! -d "$app_dir/.venv" ]; then
  python -m venv "$app_dir/.venv"
fi
"$app_dir/.venv/bin/python" -m pip install --upgrade pip

if compgen -G "$bundle_dir/dist/*.whl" > /dev/null; then
  "$app_dir/.venv/bin/pip" install --upgrade "$bundle_dir"/dist/*.whl
elif compgen -G "$bundle_dir/dist/*.tar.gz" > /dev/null; then
  "$app_dir/.venv/bin/pip" install --upgrade "$bundle_dir"/dist/*.tar.gz
elif [ -f "$bundle_dir/requirements.txt" ]; then
  "$app_dir/.venv/bin/pip" install --upgrade -r "$bundle_dir/requirements.txt"
  echo "Bundle is missing a wheel/sdist; dependencies installed only." >&2
  echo "Rebuild the bundle to include dist/*.whl before running the service." >&2
  exit 1
else
  echo "Bundle is missing dist/*.whl and requirements.txt; cannot install." >&2
  exit 1
fi

if [ ! -f "$config_dir/config.yml" ]; then
  cp "$bundle_dir/config.example.yml" "$config_dir/config.yml"
fi

install -m 0644 "$bundle_dir/deploy/prayerhub.service" "$service_file"
# Allow overriding the service user without editing the unit file by hand.
sed -i "s/^User=.*/User=${service_user}/" "$service_file"

systemctl daemon-reload
systemctl enable --now prayerhub.service

printf "Install complete. Update %s if needed; service is enabled and running.\n" "$config_dir/config.yml"
