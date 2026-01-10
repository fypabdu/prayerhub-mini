#!/usr/bin/env bash
set -euo pipefail

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
bundle_dir="$root_dir"
config_path="/etc/prayerhub/config.yml"
audio_dir="/opt/prayerhub/data/audio"
log_dir="/var/log/prayerhub"
cache_dir="/var/lib/prayerhub/cache"
override_dir="/etc/systemd/system/prayerhub.service.d"
override_file="${override_dir}/override.conf"

if [ "$(id -u)" -ne 0 ]; then
  echo "This script must be run with sudo." >&2
  exit 1
fi

if [ "${1:-}" = "--reset" ]; then
  echo "This will remove config, audio, cache, and logs:"
  echo "  - /etc/prayerhub/config.yml"
  echo "  - /opt/prayerhub/data/audio/"
  echo "  - /var/lib/prayerhub/cache/"
  echo "  - /var/log/prayerhub/"
  read -r -p "Type 'RESET' to continue: " confirm
  if [ "$confirm" = "RESET" ]; then
    rm -f /etc/prayerhub/config.yml
    rm -rf /opt/prayerhub/data/audio
    rm -rf /var/lib/prayerhub/cache
    rm -rf /var/log/prayerhub
    echo "Reset complete."
  else
    echo "Reset cancelled."
  fi
  exit 0
fi

prompt() {
  local message="$1"
  local default="${2:-}"
  local value
  while true; do
    if [ -n "$default" ]; then
      read -r -p "${message} [${default}]: " value
    else
      read -r -p "${message}: " value
    fi
    if [ "$value" = "q" ] || [ "$value" = "quit" ]; then
      echo "Setup cancelled."
      exit 1
    fi
    if [ -z "$value" ] && [ -n "$default" ]; then
      value="$default"
    fi
    if [ -n "$value" ]; then
      echo "$value"
      return 0
    fi
    echo "Please provide a value (or type 'q' to quit)."
  done
}

prompt_password() {
  local message="$1"
  local pass1 pass2
  while true; do
    read -r -s -p "${message}: " pass1
    echo ""
    if [ -z "$pass1" ]; then
      echo "Password cannot be empty."
      continue
    fi
    read -r -s -p "Confirm password: " pass2
    echo ""
    if [ "$pass1" = "$pass2" ]; then
      echo "$pass1"
      return 0
    fi
    echo "Passwords do not match. Try again."
  done
}

prompt_file() {
  local label="$1"
  local default_name="${2:-}"
  local filename
  while true; do
    read -r -p "${label} (enter number or filename) [${default_name}]: " filename
    if [ "$filename" = "q" ] || [ "$filename" = "quit" ]; then
      echo "Setup cancelled."
      exit 1
    fi
    if [ -z "$filename" ]; then
      filename="$default_name"
    fi
    if [[ "$filename" =~ ^[0-9]+$ ]]; then
      local index=$((filename - 1))
      if [ "$index" -ge 0 ] && [ "$index" -lt "${#audio_files[@]}" ]; then
        filename="${audio_files[$index]}"
      else
        echo "Invalid selection: $filename"
        continue
      fi
    fi
    if [ -n "$filename" ] && [ -f "${audio_source_dir}/${filename}" ]; then
      echo "$filename"
      return 0
    fi
    echo "File not found: ${audio_source_dir}/${filename}"
  done
}

load_audio_files() {
  mapfile -t audio_files < <(find "$audio_source_dir" -maxdepth 1 -type f -printf "%f\n" | sort)
  if [ "${#audio_files[@]}" -eq 0 ]; then
    echo "No audio files found in ${audio_source_dir}" >&2
    exit 1
  fi
}

print_audio_files() {
  echo "Available audio files in ${audio_source_dir}:"
  local i=1
  for file in "${audio_files[@]}"; do
    echo "  ${i}) ${file}"
    i=$((i + 1))
  done
}

echo "PrayerHub Mini interactive setup"
echo "Type 'q' at any prompt to quit."

echo "Step 1/6: Install bundle dependencies and app"
bash "$bundle_dir/deploy/install.sh"

service_user="$(systemctl cat prayerhub.service | awk -F= '/^User=/{print $2; exit}')"
if [ -z "$service_user" ]; then
  service_user="${SUDO_USER:-$(whoami)}"
fi
service_uid="$(id -u "$service_user")"

mkdir -p "$audio_dir" "$log_dir" "$cache_dir"
chown -R "$service_user":"$service_user" "$audio_dir" "$log_dir" "$cache_dir"

echo "Step 2/6: Bluetooth + audio user permissions"
usermod -aG audio,bluetooth "$service_user"
loginctl enable-linger "$service_user"
systemctl start "user@${service_uid}.service"

echo "Step 3/6: Configure Pulse/PipeWire for the service user"
sudo -u "$service_user" \
  XDG_RUNTIME_DIR="/run/user/${service_uid}" \
  DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/${service_uid}/bus" \
  systemctl --user enable --now pipewire pipewire-pulse

mkdir -p "$override_dir"
cat >"$override_file" <<EOF
[Service]
Environment=XDG_RUNTIME_DIR=/run/user/${service_uid}
Environment=DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/${service_uid}/bus
Environment=PULSE_SERVER=unix:/run/user/${service_uid}/pulse/native
EOF

systemctl daemon-reload

echo "Step 4/6: Update config values"
if [ ! -f "$config_path" ]; then
  echo "Missing config file: $config_path" >&2
  exit 1
fi

device_mac="$(prompt "Bluetooth MAC address" "")"
if ! [[ "$device_mac" =~ ^[0-9A-Fa-f]{2}(:[0-9A-Fa-f]{2}){5}$ ]]; then
  echo "Invalid Bluetooth MAC address: $device_mac" >&2
  exit 1
fi
username="$(prompt "Control panel username" "admin")"
password="$(prompt_password "Control panel password")"
audio_source_dir="$(prompt "Local folder with your audio files" "/home/${service_user}")"

if [ ! -d "$audio_source_dir" ]; then
  echo "Folder not found: $audio_source_dir" >&2
  exit 1
fi

load_audio_files
print_audio_files

test_audio="$(prompt_file "Test audio" "2sec-audio.mp3")"
connected_audio="$(prompt_file "Connected tone" "$test_audio")"
keepalive_audio="$(prompt_file "Background keepalive audio" "keepalive_low_freq.mp3")"

adhan_fajr="$(prompt_file "Adhan fajr" "adhan_fajr.mp3")"
adhan_dhuhr="$(prompt_file "Adhan dhuhr" "$adhan_fajr")"
adhan_asr="$(prompt_file "Adhan asr" "$adhan_fajr")"
adhan_maghrib="$(prompt_file "Adhan maghrib" "$adhan_fajr")"
adhan_isha="$(prompt_file "Adhan isha" "$adhan_fajr")"

notif_sunrise="$(prompt_file "Notification sunrise" "$test_audio")"
notif_sunset="$(prompt_file "Notification sunset" "$test_audio")"
notif_midnight="$(prompt_file "Notification midnight" "$test_audio")"
notif_tahajjud="$(prompt_file "Notification tahajjud" "$test_audio")"

quran_time="$(prompt "Quran schedule time (HH:MM)" "06:30")"
quran_file="$(prompt_file "Quran audio" "$adhan_fajr")"

echo "Step 5/6: Copy audio files into ${audio_dir}"
cp "${audio_source_dir}/${test_audio}" "${audio_dir}/${test_audio}"
cp "${audio_source_dir}/${connected_audio}" "${audio_dir}/${connected_audio}"
cp "${audio_source_dir}/${keepalive_audio}" "${audio_dir}/${keepalive_audio}"
cp "${audio_source_dir}/${adhan_fajr}" "${audio_dir}/${adhan_fajr}"
cp "${audio_source_dir}/${adhan_dhuhr}" "${audio_dir}/${adhan_dhuhr}"
cp "${audio_source_dir}/${adhan_asr}" "${audio_dir}/${adhan_asr}"
cp "${audio_source_dir}/${adhan_maghrib}" "${audio_dir}/${adhan_maghrib}"
cp "${audio_source_dir}/${adhan_isha}" "${audio_dir}/${adhan_isha}"
cp "${audio_source_dir}/${notif_sunrise}" "${audio_dir}/${notif_sunrise}"
cp "${audio_source_dir}/${notif_sunset}" "${audio_dir}/${notif_sunset}"
cp "${audio_source_dir}/${notif_midnight}" "${audio_dir}/${notif_midnight}"
cp "${audio_source_dir}/${notif_tahajjud}" "${audio_dir}/${notif_tahajjud}"
cp "${audio_source_dir}/${quran_file}" "${audio_dir}/${quran_file}"
chown -R "$service_user":"$service_user" "$audio_dir"

echo "Step 6/6: Write config updates"
hash="$(
  PRAYERHUB_PASSWORD="$password" \
  /opt/prayerhub/.venv/bin/python - <<'PY'
from werkzeug.security import generate_password_hash
import os
print(generate_password_hash(os.environ["PRAYERHUB_PASSWORD"]))
PY
)"

PRAYERHUB_DEVICE_MAC="$device_mac" \
PRAYERHUB_USERNAME="$username" \
PRAYERHUB_PASSWORD_HASH="$hash" \
PRAYERHUB_TEST_AUDIO="$test_audio" \
PRAYERHUB_CONNECTED_AUDIO="$connected_audio" \
PRAYERHUB_KEEPALIVE_AUDIO="$keepalive_audio" \
PRAYERHUB_ADHAN_FAJR="$adhan_fajr" \
PRAYERHUB_ADHAN_DHUHR="$adhan_dhuhr" \
PRAYERHUB_ADHAN_ASR="$adhan_asr" \
PRAYERHUB_ADHAN_MAGHRIB="$adhan_maghrib" \
PRAYERHUB_ADHAN_ISHA="$adhan_isha" \
PRAYERHUB_NOTIF_SUNRISE="$notif_sunrise" \
PRAYERHUB_NOTIF_SUNSET="$notif_sunset" \
PRAYERHUB_NOTIF_MIDNIGHT="$notif_midnight" \
PRAYERHUB_NOTIF_TAHAJJUD="$notif_tahajjud" \
PRAYERHUB_QURAN_TIME="$quran_time" \
PRAYERHUB_QURAN_FILE="$quran_file" \
PRAYERHUB_PASSWORD="$password" \
/opt/prayerhub/.venv/bin/python - <<'PY'
import os
from pathlib import Path
import yaml

config_path = Path("/etc/prayerhub/config.yml")
data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}

def set_path(value):
    return f"data/audio/{value}"

data.setdefault("audio", {})
data["audio"]["test_audio"] = set_path(os.environ["PRAYERHUB_TEST_AUDIO"])
data["audio"]["connected_tone"] = set_path(os.environ["PRAYERHUB_CONNECTED_AUDIO"])
data["audio"]["background_keepalive_enabled"] = True
data["audio"]["background_keepalive_path"] = set_path(os.environ["PRAYERHUB_KEEPALIVE_AUDIO"])
data["audio"]["background_keepalive_volume_percent"] = 1
data["audio"]["background_keepalive_loop"] = True
data["audio"]["background_keepalive_nice"] = 10
data["audio"].setdefault("playback_timeout_seconds", 300)
data["audio"]["playback_timeout_strategy"] = "auto"
data["audio"].setdefault("playback_timeout_buffer_seconds", 5)
data.setdefault("audio", {}).setdefault("adhan", {})
data["audio"]["adhan"]["fajr"] = set_path(os.environ["PRAYERHUB_ADHAN_FAJR"])
data["audio"]["adhan"]["dhuhr"] = set_path(os.environ["PRAYERHUB_ADHAN_DHUHR"])
data["audio"]["adhan"]["asr"] = set_path(os.environ["PRAYERHUB_ADHAN_ASR"])
data["audio"]["adhan"]["maghrib"] = set_path(os.environ["PRAYERHUB_ADHAN_MAGHRIB"])
data["audio"]["adhan"]["isha"] = set_path(os.environ["PRAYERHUB_ADHAN_ISHA"])

data.setdefault("audio", {}).setdefault("notifications", {})
data["audio"]["notifications"]["sunrise"] = set_path(os.environ["PRAYERHUB_NOTIF_SUNRISE"])
data["audio"]["notifications"]["sunset"] = set_path(os.environ["PRAYERHUB_NOTIF_SUNSET"])
data["audio"]["notifications"]["midnight"] = set_path(os.environ["PRAYERHUB_NOTIF_MIDNIGHT"])
data["audio"]["notifications"]["tahajjud"] = set_path(os.environ["PRAYERHUB_NOTIF_TAHAJJUD"])

data["audio"]["quran_schedule"] = [
    {"time": os.environ["PRAYERHUB_QURAN_TIME"], "file": set_path(os.environ["PRAYERHUB_QURAN_FILE"])}
]

data.setdefault("bluetooth", {})
data["bluetooth"]["device_mac"] = os.environ["PRAYERHUB_DEVICE_MAC"]

data.setdefault("control_panel", {}).setdefault("auth", {})
data["control_panel"]["auth"]["username"] = os.environ["PRAYERHUB_USERNAME"]
data["control_panel"]["auth"]["password_hash"] = os.environ["PRAYERHUB_PASSWORD_HASH"]

data.setdefault("logging", {})
data["logging"]["file_path"] = "/var/log/prayerhub/prayerhub.log"

config_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
PY

chown "${service_user}:${service_user}" /etc/prayerhub /etc/prayerhub/config.yml

systemctl restart prayerhub.service

echo "Setup complete."
echo "Open the control panel at: http://$(hostname -I | awk '{print $1}'):8080/"
echo "To reset and start over: sudo $0 --reset"
