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

## Build install bundle

```bash
pip install build
bash deploy/build_bundle.sh
```

The bundle is created as `prayerhub-install-bundle.zip` and is also built by CI.
