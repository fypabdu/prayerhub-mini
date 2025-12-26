# PrayerHub Mini

Headless PrayerHub prototype for a Raspberry Pi device. This repo is intentionally small and grows by ticket.

## Structure

- `src/` runtime code
- `tests/` tests
- `deploy/` install and systemd assets

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Tests

```bash
pytest -q
```

## Run (dry-run)

```bash
python -m prayerhub.app --config ./config.yml --dry-run
```

## End-to-end validation checklist (manual)

- boot device and confirm `prayerhub` service is active
- login to the control panel and schedule a test audio in 2 minutes
- hear test audio from the Bluetooth speaker
- disable Wi-Fi, restart service, and confirm it still schedules from cache

## Smoke test

```bash
pytest -m smoke -q
```

## Build install bundle

```bash
pip install build
bash deploy/build_bundle.sh
```

The bundle is created as `prayerhub-install-bundle.zip` and is also built by CI.
