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

## Start service

```bash
sudo systemctl start prayerhub.service
sudo systemctl status prayerhub.service
```
