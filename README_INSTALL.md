# PrayerHub Mini install bundle

These steps assume you are on the Raspberry Pi and have unpacked the bundle.

The bundle includes:
- `dist/*.whl` (preferred install artifact)
- `requirements.txt` (exported fallback)
- `deploy/`, `config.example.yml`, `README_INSTALL.md`

## Install

```bash
sudo ./deploy/install.sh
```

## Interactive setup (recommended)

```bash
sudo ./deploy/setup_device.sh
```

You can reset and start over any time with:

```bash
sudo ./deploy/setup_device.sh --reset
```

## Configure

```bash
sudo nano /etc/prayerhub/config.yml
```

Note: `install.sh` replaces `/etc/prayerhub/config.yml` on every run.
Note: `install.sh` stops the service and force-reinstalls the wheel to ensure updates apply.

Playback timeouts default to `auto` (duration-based) and rely on `ffprobe`,
which `install.sh` installs via `ffmpeg`. Advanced users can set
`audio.playback_timeout_strategy: "fixed"` to use a static timeout.

## Audio files

Bundle includes placeholder files in `/opt/prayerhub/data/audio/`. Replace them with real MP3s:

```bash
sudo cp /path/to/your/audio/*.mp3 /opt/prayerhub/data/audio/
```

## Start service

```bash
sudo systemctl start prayerhub.service
sudo systemctl status prayerhub.service
```
