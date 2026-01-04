# PrayerHub Mini - Raspberry Pi Zero 2W Deployment Guide

This guide is for deploying the **install bundle artifact** built by GitHub Actions onto a Raspberry Pi Zero 2W, then configuring and testing the app end-to-end.

## Preconditions (make sure these are true before starting)

- You have a Raspberry Pi Zero 2W running Raspberry Pi OS Lite 64-bit (Bookworm).
- The Pi is on the same Wi-Fi network as your laptop.
- You know the Pi’s IP address (example: `192.168.1.50`).
- The Pi has a TV + keyboard + mouse attached (local access).
- The Bluetooth speaker is paired or can be paired (you know its MAC address).
- You can use `ssh`/`scp` from your laptop.
- You have a GitHub account that can access the repo.

## What the install script does for you

When you run `sudo ./deploy/install.sh`, it will:
- create `/opt/prayerhub` and `/etc/prayerhub`
- create a Python virtual environment in `/opt/prayerhub/.venv`
- install system packages `mpg123` and `bluez` via `apt-get`
- install the app wheel from `dist/*.whl` (or fail if missing)
- install `deploy/prayerhub.service` into systemd
- enable + start the `prayerhub` systemd service
- copy `config.example.yml` to `/etc/prayerhub/config.yml` if missing

Manual tasks are called out explicitly in the steps below.

## 1) Download the artifact on your laptop

1. Open the repo on GitHub.
2. Go to **Actions**.
3. Open the latest successful **CI** run.
4. Download the **prayerhub-install-bundle** artifact.
5. You should have a file like:
   - `prayerhub-install-bundle.zip`

## 2) Transfer the artifact to the Pi

### Option A: SCP (recommended)

```bash
scp ~/Downloads/prayerhub-install-bundle.zip pi@192.168.1.50:/home/pi/
```

Replace `192.168.1.50` with your Pi IP.

### Option B: USB stick

1. Copy `prayerhub-install-bundle.zip` to a USB stick.
2. Insert into the Pi.
3. Copy the zip to `/home/pi/`.

## 3) Unzip the bundle on the Pi

```bash
cd /home/pi
unzip prayerhub-install-bundle.zip -d prayerhub-bundle
cd prayerhub-bundle
ls -la
```

Expected contents:
- `deploy/`
- `dist/` (with a `.whl` file)
- `requirements.txt`
- `config.example.yml`
- `README_INSTALL.md`
- optional `data/audio/`

## 4) Run the installer (scripted setup)

```bash
sudo ./deploy/install.sh
```

This is where the script installs system packages, creates the venv, installs the wheel, and sets up the systemd service.

## 5) Configure the app (manual)

Open the config file:

```bash
sudo nano /etc/prayerhub/config.yml
```

At minimum, update:

1) **Bluetooth MAC address**  
Example:
```yaml
bluetooth:
  device_mac: "AA:BB:CC:DD:EE:FF"
```

2) **Control panel password hash**  
Generate a hash on the Pi:
```bash
python3 - <<'PY'
from werkzeug.security import generate_password_hash
print(generate_password_hash("your-password-here"))
PY
```

Paste the output into:
```yaml
control_panel:
  auth:
    username: "admin"
    password_hash: "pbkdf2:sha256:..."
```

3) **Audio file paths**  
Ensure every path listed in `audio:` points to a real file on the Pi.  
Example:
```yaml
audio:
  test_audio: "data/audio/test_beep.mp3"
  connected_tone: "data/audio/connected.mp3"
  adhan:
    fajr: "data/audio/adhan_fajr.mp3"
    dhuhr: "data/audio/adhan_dhuhr.mp3"
    asr: "data/audio/adhan_asr.mp3"
    maghrib: "data/audio/adhan_maghrib.mp3"
    isha: "data/audio/adhan_isha.mp3"
```

## 6) Install audio files (manual)

Place all audio files under `/opt/prayerhub/data/audio/`.

Example:
```bash
sudo mkdir -p /opt/prayerhub/data/audio
sudo cp /path/to/your/audio/*.mp3 /opt/prayerhub/data/audio/
sudo ls -la /opt/prayerhub/data/audio
```

Make sure filenames match the config exactly.

## 7) Bluetooth pairing (manual if not already paired)

```bash
bluetoothctl
power on
agent on
default-agent
scan on
pair AA:BB:CC:DD:EE:FF
trust AA:BB:CC:DD:EE:FF
connect AA:BB:CC:DD:EE:FF
quit
```

## 8) Restart the service

```bash
sudo systemctl restart prayerhub.service
sudo systemctl status prayerhub.service
```

## 9) Find the Pi IP (if needed)

On the Pi:
```bash
hostname -I
```

Example output:
```
192.168.1.50
```

## 10) Open the control panel (from laptop)

Open in a browser:
```
http://192.168.1.50:8080/
```

Login using the username + password you set in the config.

## 11) Test the scheduler (manual)

### A) Test audio job

1. Open `/test` in the control panel.
2. Schedule a test audio **in 2 minutes**.
3. Wait and confirm the audio plays on the speaker.

### B) Check logs

```bash
sudo journalctl -u prayerhub.service -f
```

You should see log lines for:
- schedule created
- bluetooth connect attempts
- audio playback start/end

## 12) Offline test (optional)

1. Disable Wi-Fi on the Pi.
2. Restart the service:
```bash
sudo systemctl restart prayerhub.service
```
3. Ensure it schedules from cache and does not crash-loop.

