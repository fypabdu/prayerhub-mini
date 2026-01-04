# Repository Guidelines

## Project Structure & Module Organization
This repository includes runtime code under `src/`, tests, and deployment assets. If you add application code, keep it organized and easy to scan. A common layout is:

- `src/` for runtime code
- `tests/` for test code
- `scripts/` for one-off automation
- `assets/` for static files

Keep module boundaries small and name files by responsibility (for example, `src/prayers.py`, `tests/test_prayers.py`).

## Build, Test, and Development Commands
Dependencies are tracked in `pyproject.toml` and managed by Poetry. Typical setup:

- `pip install poetry poetry-plugin-export`
- `poetry install`
- `poetry run pytest -q`

Run commands are defined in `README.md`. Keep this section aligned with Poetry-first workflows.

## Coding Style & Naming Conventions
No formatter or linter is configured. If you add Python code, follow standard conventions:

- 4-space indentation, one class or cohesive set of functions per file.
- `snake_case` for functions/variables and `PascalCase` for classes.
- Prefer small, testable functions with clear docstrings when needed.

If you introduce formatting or linting tools (for example, `ruff` or `black`), include the command in this file.

## Testing Guidelines
Tests use `pytest`. If you add tests, place them under `tests/` and use clear names such as `test_*.py`. Document the test runner and command you expect contributors to use.

## Commit & Pull Request Guidelines
No commit message convention is documented. Use concise, imperative summaries (for example, “Add prayer model”). For pull requests, include:

- A short summary of the change and rationale.
- Steps to verify (commands and expected outcome).
- Screenshots or notes if UI or content changes are involved.

## Configuration Tips
Keep secrets out of the repository. If you add environment variables, document them in a sample file like `.env.example` and reference it in `README.md`.



# AGENTS.md — PrayerHub Mini Prototype (Codex CLI playbook)

This file is written for **Codex CLI** to work effectively on this repository in **tiny, TDD-first increments**, with clean commits and reliable builds.

Codex reads `AGENTS.md` automatically before working. It also supports layered overrides (`AGENTS.override.md`) and a configurable maximum instruction size. See Codex docs for discovery order and config knobs. citeturn2view3turn1view3turn1view2

---

## 0) Golden rules (non-negotiable)

1. **One tiny feature at a time**  
   - Work on **exactly one ticket** per iteration.
   - Keep diffs small and reviewable.

2. **TDD is required**  
   For each ticket:
   - Write tests first (failing).
   - Implement minimal code to pass.
   - Refactor (only if tests remain green).
   - Run full test suite locally.

3. **OOP + SOLID**  
   - Prefer small classes with single responsibility.
   - Use interfaces (Protocols) for external systems (HTTP, Bluetooth, subprocess/audio, clock).

4. **Always update dependencies in `pyproject.toml` when adding packages**  
   - If you import a new third-party package, add it immediately to `pyproject.toml`.
   - Prefer pinning (`pkg==x.y.z`) for repeatable Pi installs and CI builds.
   - Regenerate `requirements.txt` via `poetry export` for the bundle.

5. **Never leave the user hanging**  
   - Every response MUST end with:
     - “What I changed”
     - “How to verify”
     - “Next tiny task suggestion”
     - Any required **manual steps** for the user

---

## 1) Repo context bundle (files Codex must use)

Codex must treat the following as the source of truth:

### Project spec / plan
- `docs/spec.md` — the mini design doc + 8-hour plan.

### Prayer times API reference (repo2txt export)
- `docs/converted-repo-prayer-api.txt` — includes endpoints, params, response shapes, and tests.

Key endpoints (from the text export; confirm inside that file):
- `GET /api/v1/times/today/?madhab=...&city=...`
- `GET /api/v1/times/date/?madhab=...&city=...&date=YYYY-MM-DD`
- `GET /api/v1/times/next/?madhab=...&city=...&datetime=YYYY-MM-DDTHH:MM`
- `GET /api/v1/times/range/?madhab=...&city=...&start=YYYY-MM-DD&end=YYYY-MM-DD`

### Context7 docs (you will provide)
Create a folder: `docs/context7/` and add markdown exports from Context7.
Codex must prefer these docs over random web browsing.

Minimum topics to export (recommended filenames):
- `docs/context7/apscheduler.md`
- `docs/context7/flask.md`
- `docs/context7/requests.md`
- `docs/context7/pyyaml.md`
- `docs/context7/github_actions.md`
- Optional: `docs/context7/python_stdlib_datetime_zoneinfo_logging_subprocess.md`

Linux/man-page style references (not in Context7 usually, but add notes):
- `docs/context7/systemd_service_units.md`
- `docs/context7/bluetoothctl_blueZ.md`
- `docs/context7/pactl_pulseaudio_pipewire.md`
- `docs/context7/mpg123.md`

**Codex workflow requirement:** At the start of each ticket, Codex MUST list the exact files it will consult (from above) and skim the relevant section(s) before coding.

---

## 2) Local dev commands (Codex should use these)

### Setup (dev machine)
```bash
pip install poetry poetry-plugin-export
poetry install
poetry run pytest -q
```

### Run app (dry-run schedule)
```bash
poetry run python -m prayerhub.app --config ./config.yml --dry-run
```

### Run app (real)
```bash
poetry run python -m prayerhub.app --config ./config.yml
```

### Git hygiene
```bash
git status
git diff
git log --oneline --decorate -n 20
git show <sha>
```

Codex must actively use `git log` / `git show` when debugging regressions.

---

## 3) Build + packaging (GitHub Actions artifact)

We require a GitHub Actions workflow that:
1) runs unit tests,
2) builds an **install bundle** artifact for the Pi, and
3) uploads the bundle to the workflow run as an artifact.

Use `actions/upload-artifact@v4` to publish artifacts. citeturn0search10turn0search1turn0search7

### Install bundle definition
The bundle should be a zip, e.g. `prayerhub-install-bundle.zip`, containing:
- a built wheel or sdist for this app (`dist/*.whl` preferred)
- `requirements.txt`
- `deploy/prayerhub.service`
- `deploy/install.sh`
- `config.example.yml`
- `README_INSTALL.md` (short, exact device steps)
- `data/audio/` (if bundled)

Codex should implement a script:
- `deploy/build_bundle.sh` (or `.py`) that creates the zip in a deterministic way.

**Rule:** CI must be able to build the artifact on a clean runner.

---

## 4) Runtime targets and constraints

### Device
- Raspberry Pi Zero 2 W, headless, on Wi-Fi
- Bluetooth speaker paired and trusted
- Audio via a `pactl`-compatible stack (works with PulseAudio or PipeWire’s pulse-compat)

### Audio backend choice
Prefer CLI playback:
- primary: `mpg123` (MP3), output via pulse if available
- fallback: `ffplay` if needed

The code should:
- detect if `pactl` exists
- detect if `mpg123` exists
- fail with actionable logs if not installed
- never hang indefinitely on subprocess calls (timeouts)

---

## 5) Feature: scheduler “test audio” (required)

We must be able to test on the real device that scheduling works.

### Requirements
- A “test audio file” configured in `config.yml` (e.g. `data/audio/test_beep.mp3`)
- A feature to schedule test playback at:
  - a specific clock time (`HH:MM` today, or tomorrow if already passed), and
  - “in N minutes” (relative trigger)

### Implementation guidance
- Add a `TestPlaybackService` (or similar) with methods:
  - `schedule_test_at_time("HH:MM")`
  - `schedule_test_in_minutes(n: int)`
  - `list_test_jobs()`
  - `cancel_test_job(job_id)`
- These must use APScheduler **DateTrigger** jobs so they can be inspected and removed.
- Test jobs must have stable IDs and appear in the `/status` view.

### Fail-safe rules
- Test jobs should never block normal Adhan/Quran jobs.
- If a test job fires and Bluetooth is down, attempt one reconnect; otherwise log and mark job failed.
- Tests must verify:
  - job is scheduled for the correct future datetime
  - job is not scheduled in the past
  - job removal works

---

## 6) Feature: Control Panel with basic UI + login (required)

We need a minimal HTML UI reachable on the LAN.

### Requirements
- Fixed username/password in `config.yml`
- UI pages:
  - `/login` (form)
  - `/` dashboard (status + next events + last logs tail)
  - `/test` (schedule test audio: HH:MM and “in N minutes”, list/cancel)
  - `/controls` (volume up/down, play adhan/quran test triggers)

### Security model (simple)
- Use server-side session cookies.
- Do not expose password in logs.
- Provide a very small attack surface:
  - bind to `0.0.0.0` but require login for all pages
  - optional: allow a token header for curl automation (non-UI endpoints)

### Testing
- Use Flask’s test client:
  - login required redirects
  - valid login creates session
  - schedule test endpoints create APScheduler jobs

---

## 7) Coding standards for this repo

### Style
- Prefer plain Python, no heavy frameworks.
- Use `dataclasses` for config and domain models.
- Use `typing.Protocol` to mock dependencies cleanly.

### Error handling
- All scheduled jobs must catch exceptions and log; never crash the scheduler thread.
- All external calls must have timeouts.
- Cache writes must be atomic.

### Logging
- Every major action logs:
  - fetch prayer times
  - cache hit/miss
  - schedule created/removed
  - bluetooth connect/reconnect
  - audio play start/stop/error
  - control panel login success/failure (no password)

---

## 8) Ticket execution protocol (how Codex must work)

For each ticket:
1. **Restate the ticket goal** in one sentence.
2. **List files to read** (spec + prayer-api + Context7 topic docs).
3. **Plan**: bullet list of steps.
4. **TDD**:
   - Add/extend tests under `tests/`
   - Run `pytest -q` (or instruct user to run if sandboxed)
5. **Implement** minimal code in `src/prayerhub/`
6. **Update `pyproject.toml`** if new deps added, then regenerate `requirements.txt` via `poetry export` for the bundle.
7. **Run full tests**.
8. **Show git diff summary** and propose a commit message.
9. **Stop** and tell the user:
   - exact command(s) to verify locally
   - what to do next

### Commit discipline
- One commit per ticket.
- Message format:
  - `feat: ...` / `fix: ...` / `test: ...` / `chore: ...`
- Do not bundle refactors with features unless tiny and required.

---

## 9) “Manual steps” checklist (human-only actions)

Codex cannot do these reliably; the user must do them.

### A) Codex CLI config (recommended)
1. Ensure your Codex config file exists at:
   - `~/.codex/config.toml` citeturn1view3
2. Optional but recommended settings:
   - increase instruction byte cap if needed (`project_doc_max_bytes`)
   - set approval policy and sandbox mode per your comfort

Codex instructions discovery and size caps are explained in the docs. citeturn2view3

### B) Device setup
- Flash OS, enable SSH, connect Wi-Fi
- Pair + trust the speaker with `bluetoothctl`
- Install system packages (bluez, mpg123, etc.)
- Copy install bundle from GitHub Actions and run `deploy/install.sh`
- Follow `deployment.md` for full device install steps

### C) Context7 exports
- Export the topic docs listed in section 1 into `docs/context7/`.
- Keep them short; prefer the parts you actually use (APScheduler scheduling, Flask auth/templates, etc.)

---

## 10) “Always tell me what to do next” (response template)

Codex responses MUST end with:

- **What I changed:** (files + summary)
- **How to verify:** exact commands
- **Next tiny task:** a single recommended next ticket
- **Manual step needed from you:** if any

---

## 11) If something is ambiguous, do this (no guessing silently)

If a requirement is unclear, Codex must:
1) make the smallest safe assumption,
2) implement it behind a config flag if possible,
3) **explicitly list the assumption** at the end, and
4) propose the smallest follow-up question.

Do not block progress unless the ambiguity is critical.

