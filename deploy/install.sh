#!/usr/bin/env bash
set -euo pipefail

bundle_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
app_dir="/opt/prayerhub"
config_dir="/etc/prayerhub"
service_file="/etc/systemd/system/prayerhub.service"

mkdir -p "$app_dir" "$config_dir"

python -m venv "$app_dir/.venv"
"$app_dir/.venv/bin/python" -m pip install --upgrade pip

if compgen -G "$bundle_dir/dist/*.whl" > /dev/null; then
  "$app_dir/.venv/bin/pip" install "$bundle_dir"/dist/*.whl
else
  "$app_dir/.venv/bin/pip" install -r "$bundle_dir/requirements.txt"
fi

if [ ! -f "$config_dir/config.yml" ]; then
  cp "$bundle_dir/config.example.yml" "$config_dir/config.yml"
fi

install -m 0644 "$bundle_dir/deploy/prayerhub.service" "$service_file"

systemctl daemon-reload
systemctl enable prayerhub.service

printf "Install complete. Update %s and start the service when ready.\n" "$config_dir/config.yml"
