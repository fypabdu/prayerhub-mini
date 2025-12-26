# PrayerHub Mini install bundle

These steps assume you are on the Raspberry Pi and have unpacked the bundle.

## Install

```bash
sudo ./deploy/install.sh
```

## Configure

```bash
sudo nano /etc/prayerhub/config.yml
```

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
