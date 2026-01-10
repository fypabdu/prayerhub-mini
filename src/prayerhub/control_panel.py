from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import logging
from pathlib import Path
import re
import tempfile
from typing import Callable, Optional, Sequence

import yaml

from flask import Flask, redirect, render_template_string, request, session, url_for
from werkzeug.security import check_password_hash

from prayerhub.command_runner import SubprocessCommandRunner
from prayerhub.config import ConfigError, ConfigLoader
from prayerhub.prayer_times import DayPlan, PrayerTimeService
from prayerhub.test_scheduler import TestScheduleService


LOGIN_TEMPLATE = """
<!doctype html>
<title>PrayerHub Login</title>
<h1>Login</h1>
<form method="post">
  <label>Username <input name="username" /></label><br />
  <label>Password <input name="password" type="password" /></label><br />
  <button type="submit">Login</button>
</form>
{% if error %}<p style="color:red">{{ error }}</p>{% endif %}
"""


MAIN_TEMPLATE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>PrayerHub Control Panel</title>
  <style>
    :root {
      --ink: #0f1e1c;
      --muted: #5a6b67;
      --accent: #0f5b4d;
      --accent-2: #b5651d;
      --bg: #f7f3ea;
      --panel: #ffffff;
      --panel-2: #f2ede3;
      --border: #d9d2c2;
      --shadow: 0 12px 30px rgba(10, 20, 18, 0.08);
      --radius: 18px;
      --font-body: "Trebuchet MS", "Gill Sans", "Verdana", sans-serif;
      --font-display: "Palatino Linotype", "Bookman Old Style", "Garamond", serif;
    }

    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: var(--font-body);
      color: var(--ink);
      background: radial-gradient(circle at top left, #fefbf3, #efe7d6 45%, #e8e1d1 80%);
      min-height: 100vh;
    }
    header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 24px 28px 10px;
    }
    h1 {
      font-family: var(--font-display);
      font-size: 2rem;
      margin: 0;
      letter-spacing: 0.5px;
    }
    .subtitle {
      color: var(--muted);
      font-size: 0.95rem;
    }
    nav {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      padding: 0 28px 18px;
    }
    nav button {
      border: 1px solid var(--border);
      background: var(--panel);
      color: var(--ink);
      padding: 10px 14px;
      border-radius: 999px;
      cursor: pointer;
      font-weight: 600;
      transition: transform 0.15s ease, box-shadow 0.15s ease;
    }
    nav button.active {
      background: var(--accent);
      color: #fff;
      border-color: transparent;
      box-shadow: 0 8px 16px rgba(15, 91, 77, 0.2);
    }
    nav button:hover {
      transform: translateY(-1px);
    }
    .grid {
      display: grid;
      gap: 18px;
      padding: 0 28px 32px;
    }
    .panel {
      background: var(--panel);
      border-radius: var(--radius);
      box-shadow: var(--shadow);
      padding: 18px 20px;
      border: 1px solid var(--border);
      animation: fadeIn 0.4s ease;
    }
    .panel h2 {
      font-family: var(--font-display);
      margin: 0 0 12px;
      font-size: 1.3rem;
    }
    .muted { color: var(--muted); }
    .pill {
      background: var(--panel-2);
      padding: 8px 12px;
      border-radius: 999px;
      font-weight: 600;
      display: inline-block;
    }
    .section { display: none; }
    .section.active { display: block; }
    .table-scroll {
      max-height: 260px;
      overflow: auto;
      border-radius: 14px;
      border: 1px solid var(--border);
    }
    table {
      width: 100%;
      border-collapse: collapse;
    }
    th, td {
      text-align: left;
      padding: 10px 12px;
      border-bottom: 1px solid var(--border);
      font-size: 0.95rem;
    }
    th {
      position: sticky;
      top: 0;
      background: #fbf8f1;
      z-index: 1;
    }
    .log-panel {
      max-height: 280px;
      overflow: auto;
      background: #141816;
      color: #f6f1e3;
      padding: 14px;
      border-radius: 14px;
      font-family: "Courier New", monospace;
      font-size: 0.85rem;
    }
    .log-line { padding: 2px 0; }
    .form-grid {
      display: grid;
      gap: 12px;
    }
    .form-grid label { font-weight: 600; }
    .form-grid input, select {
      width: 100%;
      padding: 8px 10px;
      border-radius: 10px;
      border: 1px solid var(--border);
    }
    .actions {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
    }
    .actions button {
      padding: 10px 14px;
      border-radius: 12px;
      border: none;
      font-weight: 700;
      cursor: pointer;
      color: #fff;
      background: var(--accent);
    }
    .actions button.secondary {
      background: var(--accent-2);
    }
    .badge {
      display: inline-block;
      padding: 4px 10px;
      border-radius: 999px;
      background: #f0e6d2;
      font-size: 0.85rem;
      font-weight: 600;
    }
    @keyframes fadeIn {
      from { opacity: 0; transform: translateY(8px); }
      to { opacity: 1; transform: translateY(0); }
    }
    @media (min-width: 960px) {
      .grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .panel.span-2 { grid-column: span 2; }
    }
  </style>
</head>
<body>
  <header>
    <div>
      <h1>PrayerHub</h1>
      <div class="subtitle">Control panel · status {{ status_label }}</div>
    </div>
    <div class="pill">Timezone: {{ timezone }}</div>
  </header>

  <nav>
    <button data-section="overview">Overview</button>
    <button data-section="prayers">Prayer Times</button>
    <button data-section="schedule">Upcoming Events</button>
    <button data-section="tests">Test Audio</button>
    <button data-section="controls">Controls</button>
    <button data-section="config">Config</button>
    <button data-section="logs">Logs</button>
  </nav>

  <div class="grid">
    <section class="panel section" id="overview">
      <h2>Device Status</h2>
      <p><span class="badge">Bluetooth</span> {{ device_status.bluetooth }}</p>
      <p><span class="badge">Wi-Fi</span> {{ device_status.wifi }}</p>
      <p><span class="badge">IP</span> {{ device_status.ip }}</p>
      <p><span class="badge">Background Audio</span> {{ device_status.background_keepalive }}</p>
    </section>

    <section class="panel section" id="prayers">
      <h2>Today's Prayer Times</h2>
      <p class="muted">{{ prayer_source }}</p>
      {% if prayer_times %}
      <div class="table-scroll">
        <table>
          <thead>
            <tr><th>Prayer</th><th>Time</th></tr>
          </thead>
          <tbody>
            {% for item in prayer_times %}
            <tr><td>{{ item.name }}</td><td>{{ item.time }}</td></tr>
            {% endfor %}
          </tbody>
        </table>
      </div>
      {% else %}
      <p class="muted">Prayer times unavailable.</p>
      {% endif %}
    </section>

    <section class="panel section span-2" id="schedule">
      <h2>Upcoming Events</h2>
      {% if upcoming_events %}
      <div class="table-scroll">
        <table>
          <thead>
            <tr><th>Type</th><th>Name</th><th>Run Time</th></tr>
          </thead>
          <tbody>
            {% for item in upcoming_events %}
            <tr>
              <td>{{ item.kind }}</td>
              <td>{{ item.name }}</td>
              <td>{{ item.run_time }}</td>
            </tr>
            {% endfor %}
          </tbody>
        </table>
      </div>
      {% else %}
      <p class="muted">No scheduled events.</p>
      {% endif %}
    </section>

    <section class="panel section" id="tests">
      <h2>Schedule Test Audio</h2>
      <form method="post" action="{{ url_for('schedule_test') }}" class="form-grid">
        <label>Time (HH:MM)</label>
        <input name="time" />
        <label>In minutes</label>
        <input name="minutes" />
        <div class="actions">
          <button type="submit">Schedule</button>
        </div>
      </form>
      <h3>Pending Tests</h3>
      {% if test_jobs %}
      <ul>
        {% for job in test_jobs %}
        <li>
          {{ job.id }} at {{ job.run_date }}
          <form method="post" action="{{ url_for('cancel_test', job_id=job.id) }}" style="display:inline">
            <button type="submit" class="secondary">Cancel</button>
          </form>
        </li>
        {% endfor %}
      </ul>
      {% else %}
      <p class="muted">No pending tests.</p>
      {% endif %}
    </section>

    <section class="panel section" id="controls">
      <h2>Controls</h2>
      <div class="actions">
        <form method="post" action="{{ url_for('volume_control') }}">
          <input type="hidden" name="direction" value="up" />
          <button type="submit">Volume +</button>
        </form>
        <form method="post" action="{{ url_for('volume_control') }}">
          <input type="hidden" name="direction" value="down" />
          <button type="submit">Volume -</button>
        </form>
      </div>
      <form method="post" action="{{ url_for('play_now') }}" class="form-grid" style="margin-top:12px;">
        <label>Play Now</label>
        <select name="event">
          {% for event in allowed_events %}
          <option value="{{ event }}">{{ event }}</option>
          {% endfor %}
        </select>
        <div class="actions">
          <button type="submit">Play</button>
        </div>
      </form>
    </section>

    <section class="panel section span-2" id="config">
      <h2>Configuration</h2>
      {% if error %}<p class="muted">{{ error }}</p>{% endif %}
      {% if message %}<p class="muted">{{ message }}</p>{% endif %}
      <form method="post" action="{{ url_for('config_page') }}">
        <div class="form-grid">
          {% for field in fields %}
          <label>{{ field.label }}
            <input name="{{ field.name }}" value="{{ field.value }}" />
          </label>
          {% endfor %}
        </div>
        <h3>Quran Schedule</h3>
        <div class="form-grid">
          {% for item in quran_fields %}
          <label>Time <input name="{{ item.time_name }}" value="{{ item.time_value }}" /></label>
          <label>File <input name="{{ item.file_name }}" value="{{ item.file_value }}" /></label>
          {% endfor %}
        </div>
        <h3>Update Password</h3>
        <div class="form-grid">
          <label>New password <input type="password" name="new_password" /></label>
          <label>Confirm <input type="password" name="new_password_confirm" /></label>
        </div>
        <div class="actions" style="margin-top:12px;">
          <button type="submit" name="action" value="save">Save</button>
          <button type="submit" name="action" value="save_restart" class="secondary">Save + Restart</button>
        </div>
      </form>
    </section>

    <section class="panel section span-2" id="logs">
      <h2>Logs (last 24h)</h2>
      <div class="log-panel">
        {% for line in log_entries %}
        <div class="log-line">{{ line }}</div>
        {% endfor %}
      </div>
    </section>
  </div>

  <script>
    const defaultSection = "{{ active_section }}";
    const buttons = document.querySelectorAll("nav button");
    const sections = document.querySelectorAll(".section");
    function activate(section) {
      sections.forEach(el => el.classList.toggle("active", el.id === section));
      buttons.forEach(btn => btn.classList.toggle("active", btn.dataset.section === section));
      const url = new URL(window.location);
      url.searchParams.set("section", section);
      window.history.replaceState({}, "", url);
    }
    buttons.forEach(btn => btn.addEventListener("click", () => activate(btn.dataset.section)));
    activate(defaultSection || "overview");
  </script>
</body>
</html>
"""

TEST_TEMPLATE = """
<!doctype html>
<title>PrayerHub</title>
<body>
  <p>Use the main dashboard.</p>
</body>
"""

CONTROLS_TEMPLATE = """
<!doctype html>
<title>PrayerHub</title>
<body>
  <p>Use the main dashboard.</p>
</body>
"""

CONFIG_TEMPLATE = """
<!doctype html>
<title>PrayerHub</title>
<body>
  <p>Use the main dashboard.</p>
</body>
"""


def _login_required(handler):
    def wrapper(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("login"))
        return handler(*args, **kwargs)

    wrapper.__name__ = handler.__name__
    return wrapper


@dataclass
class ControlPanelServer:
    username: str
    password_hash: str
    test_scheduler: TestScheduleService
    secret_key: str
    scheduler: Optional[object] = None
    audio_router: Optional[object] = None
    play_handler: Optional[Callable[[str], bool]] = None
    log_path: Optional[str] = None
    config_path: Optional[str] = None
    device_mac: Optional[str] = None
    device_status_provider: Optional[Callable[[], dict]] = None
    prayer_service: Optional[PrayerTimeService] = None
    command_runner: Optional[SubprocessCommandRunner] = None
    quran_times: Sequence[str] = ()
    keepalive_service: Optional[object] = None
    host: str = "0.0.0.0"
    port: int = 8080
    volume_percent: int = 50
    volume_step: int = 5

    def __post_init__(self) -> None:
        self._logger = logging.getLogger(self.__class__.__name__)
        self._allowed_events = self._build_allowed_events()
        if self.command_runner is None:
            self.command_runner = SubprocessCommandRunner()
        self._app = self._create_app()

    @property
    def app(self) -> Flask:
        return self._app

    def _create_app(self) -> Flask:
        app = Flask(__name__)
        app.secret_key = self.secret_key

        @app.route("/login", methods=["GET", "POST"])
        def login():
            error: Optional[str] = None
            if request.method == "POST":
                username = request.form.get("username", "")
                password = request.form.get("password", "")
                if username == self.username and check_password_hash(
                    self.password_hash, password
                ):
                    session["user"] = username
                    self._logger.info("Control panel login success for %s", username)
                    return redirect(url_for("dashboard"))
                self._logger.warning("Control panel login failed for %s", username)
                error = "Invalid credentials"
            return render_template_string(LOGIN_TEMPLATE, error=error)

        @app.route("/")
        @_login_required
        def dashboard():
            section = request.args.get("section", "overview")
            upcoming_events = _collect_upcoming_events(self.scheduler)
            test_jobs = self.test_scheduler.list_test_jobs()
            log_entries = _read_log_entries(self.log_path, hours=24, max_entries=800)
            device_status = self._device_status()
            prayer_times, prayer_source = self._prayer_times_today()
            fields = []
            quran_fields = []
            config_path = self._resolve_config_path()
            if config_path is not None:
                data = _load_config_data(config_path)
                fields = _config_fields(data)
                quran_fields = _quran_form_fields(data)
            return render_template_string(
                MAIN_TEMPLATE,
                status_label="OK",
                timezone=self._timezone_label(),
                upcoming_events=upcoming_events,
                test_jobs=test_jobs,
                log_entries=log_entries,
                device_status=device_status,
                prayer_times=prayer_times,
                prayer_source=prayer_source,
                allowed_events=sorted(self._allowed_events),
                fields=fields,
                quran_fields=quran_fields,
                error=None,
                message=None,
                active_section=section,
            )

        @app.route("/status")
        @_login_required
        def status():
            return redirect(url_for("dashboard", section="overview"))

        @app.route("/test")
        @_login_required
        def test_page():
            return redirect(url_for("dashboard", section="tests"))

        @app.post("/test/schedule")
        @_login_required
        def schedule_test():
            hhmm = request.form.get("time", "").strip()
            minutes = request.form.get("minutes", "").strip()

            try:
                if hhmm:
                    self.test_scheduler.schedule_test_at_time(hhmm)
                elif minutes:
                    self.test_scheduler.schedule_test_in_minutes(int(minutes))
                else:
                    raise ValueError("Provide time or minutes")
            except ValueError as exc:
                self._logger.warning("Test schedule failed: %s", exc)
            return redirect(url_for("test_page"))

        @app.post("/test/cancel/<job_id>")
        @_login_required
        def cancel_test(job_id: str):
            self.test_scheduler.cancel_test_job(job_id)
            return redirect(url_for("test_page"))

        @app.route("/controls")
        @_login_required
        def controls():
            return redirect(url_for("dashboard", section="controls"))

        @app.route("/config", methods=["GET", "POST"])
        @_login_required
        def config_page():
            config_path = self._resolve_config_path()
            if config_path is None:
                return render_template_string(
                    MAIN_TEMPLATE,
                    fields=[],
                    quran_fields=[],
                    error="Config path is not configured.",
                    message=None,
                    active_section="config",
                    status_label="OK",
                    timezone=self._timezone_label(),
                    upcoming_events=_collect_upcoming_events(self.scheduler),
                    test_jobs=self.test_scheduler.list_test_jobs(),
                    log_entries=_read_log_entries(self.log_path, hours=24, max_entries=800),
                    device_status=self._device_status(),
                    prayer_times=[],
                    prayer_source="Prayer times unavailable.",
                    allowed_events=sorted(self._allowed_events),
                )
            error = None
            message = None
            data = _load_config_data(config_path)

            if request.method == "POST":
                action = request.form.get("action", "save")
                data, error = _apply_config_form(data, request.form)
                if error is None:
                    error = _validate_config_data(config_path, data)
                if error is None:
                    try:
                        _save_config_data(config_path, data)
                        if action == "save_restart":
                            restart_error = self._restart_service()
                            if restart_error:
                                error = restart_error
                            else:
                                message = "Saved and restarted."
                        else:
                            message = "Saved."
                    except OSError as exc:
                        error = f"Failed to save config: {exc}"

            fields = _config_fields(data)
            quran_fields = _quran_form_fields(data)
            prayer_times, prayer_source = self._prayer_times_today()
            return render_template_string(
                MAIN_TEMPLATE,
                fields=fields,
                quran_fields=quran_fields,
                error=error,
                message=message,
                active_section="config",
                status_label="OK",
                timezone=self._timezone_label(),
                upcoming_events=_collect_upcoming_events(self.scheduler),
                test_jobs=self.test_scheduler.list_test_jobs(),
                log_entries=_read_log_entries(self.log_path, hours=24, max_entries=800),
                device_status=self._device_status(),
                prayer_times=prayer_times,
                prayer_source=prayer_source,
                allowed_events=sorted(self._allowed_events),
            )

        @app.post("/controls/volume")
        @_login_required
        def volume_control():
            direction = request.form.get("direction")
            if direction not in {"up", "down"}:
                return redirect(url_for("controls"))
            self._adjust_volume(direction)
            return redirect(url_for("controls"))

        @app.post("/controls/play-now")
        @_login_required
        def play_now():
            event = request.form.get("event", "").strip()
            if event and self.play_handler and event in self._allowed_events:
                self.play_handler(event)
            elif event:
                self._logger.warning("Rejected play-now event: %s", event)
            return redirect(url_for("controls"))

        return app

    def _adjust_volume(self, direction: str) -> None:
        if not self.audio_router:
            self._logger.warning("Audio router not configured for volume control")
            return
        if direction == "up":
            self.volume_percent = min(100, self.volume_percent + self.volume_step)
        elif direction == "down":
            self.volume_percent = max(0, self.volume_percent - self.volume_step)
        # We keep volume state in memory so the UI feels responsive.
        self.audio_router.set_master_volume(self.volume_percent)

    def _build_allowed_events(self) -> set[str]:
        base = {
            "test_audio",
            "fajr",
            "dhuhr",
            "asr",
            "maghrib",
            "isha",
            "sunrise",
            "sunset",
            "midnight",
            "tahajjud",
        }
        for time in self.quran_times:
            base.add(f"quran@{time}")
        return base

    def _resolve_config_path(self) -> Optional[Path]:
        if self.config_path:
            return Path(self.config_path)
        return Path("/etc/prayerhub/config.yml")

    def _device_status(self) -> dict:
        if self.device_status_provider:
            status = self.device_status_provider()
        else:
            status = _default_device_status(self.device_mac)
        if self.keepalive_service is not None:
            status["background_keepalive"] = (
                "running" if self.keepalive_service.is_running() else "stopped"
            )
        else:
            status.setdefault("background_keepalive", "disabled")
        return status

    def _timezone_label(self) -> str:
        return "Local"

    def _prayer_times_today(self) -> tuple[list[dict], str]:
        if not self.prayer_service:
            return [], "Prayer times unavailable."
        today = datetime.now().date()
        plan = self.prayer_service.get_day(today)
        source = "Source: cache"
        if plan is None:
            try:
                self.prayer_service.prefetch(days=1)
            except Exception as exc:
                self._logger.warning("Prayer time refresh failed: %s", exc)
            plan = self.prayer_service.get_day(today)
            source = "Source: API" if plan else "Source: unavailable"
        return _plan_times(plan), source

    def _restart_service(self) -> Optional[str]:
        if not self.command_runner:
            return "Restart unavailable."
        result = self.command_runner.run(
            ["sudo", "-n", "systemctl", "restart", "prayerhub.service"],
            timeout=10,
        )
        if result.returncode != 0:
            self._logger.warning("Service restart failed: %s", result.stderr.strip())
            return "Restart failed. Check service permissions."
        return None


def _collect_upcoming_events(scheduler: Optional[object]) -> list[dict]:
    if scheduler is None:
        return []
    try:
        jobs = scheduler.get_jobs()
    except Exception:
        return []
    events = []
    for job in jobs:
        run_time = getattr(job, "next_run_time", None)
        if not run_time:
            continue
        kind, name = _job_kind_and_name(job.id)
        events.append(
            {
                "kind": kind,
                "name": name,
                "run_time": run_time.strftime("%Y-%m-%d %H:%M:%S"),
            }
        )
    return sorted(events, key=lambda item: item["run_time"])


def _job_kind_and_name(job_id: str) -> tuple[str, str]:
    if job_id.startswith("test_audio"):
        return "test", job_id
    if job_id.startswith("quran_"):
        return "quran", job_id
    if job_id.startswith("event_"):
        parts = job_id.split("_", 2)
        if len(parts) >= 2:
            return "event", parts[1]
    if job_id == "refresh_daily":
        return "maintenance", "refresh_daily"
    return "job", job_id


def _plan_times(plan: Optional[DayPlan]) -> list[dict]:
    if not plan:
        return []
    order = [
        "fajr",
        "sunrise",
        "dhuhr",
        "asr",
        "maghrib",
        "isha",
        "sunset",
        "midnight",
        "tahajjud",
    ]
    items = []
    for name in order:
        if name in plan.times:
            items.append({"name": name, "time": plan.times[name]})
    return items


def _read_log_entries(
    log_path: Optional[str], *, hours: int, max_entries: int
) -> list[str]:
    if not log_path:
        return ["No log file configured."]
    path = Path(log_path)
    if not path.exists():
        return ["Log file not found."]
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return ["Log unavailable."]

    now = datetime.now()
    cutoff = now - timedelta(hours=hours)
    timestamp = re.compile(r"^(\\d{4}-\\d{2}-\\d{2} \\d{2}:\\d{2}:\\d{2}),")
    entries: list[str] = []
    for line in content.splitlines():
        match = timestamp.match(line)
        if match:
            try:
                entry_time = datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S")
            except ValueError:
                entry_time = None
            if entry_time and entry_time < cutoff:
                continue
        entries.append(line)
    entries = entries[-max_entries:]
    return list(reversed(entries))


def _load_config_data(path: Path) -> dict:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _save_config_data(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = yaml.safe_dump(data, sort_keys=False)
    tmp_path = path.with_suffix(".tmp")
    tmp_path.write_text(payload, encoding="utf-8")
    tmp_path.replace(path)


def _apply_config_form(data: dict, form) -> tuple[dict, Optional[str]]:
    updated = dict(data)
    error = None

    def set_path(target: dict, keys: list[str], value):
        current = target
        for key in keys[:-1]:
            current = current.setdefault(key, {})
        current[keys[-1]] = value

    def parse_bool(value: str) -> Optional[bool]:
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False
        return None

    fields = _config_field_definitions()
    for field in fields:
        raw = form.get(field["name"], "").strip()
        if raw == "":
            continue
        if field["type"] == "int":
            try:
                value = int(raw)
            except ValueError:
                return data, f"Invalid number for {field['label']}"
        elif field["type"] == "bool":
            parsed = parse_bool(raw)
            if parsed is None:
                return data, f"Invalid boolean for {field['label']}"
            value = parsed
        else:
            value = raw
        set_path(updated, field["path"], value)

    quran_schedule = []
    for item in _quran_form_fields(updated):
        time_value = form.get(item["time_name"], "").strip()
        file_value = form.get(item["file_name"], "").strip()
        if not time_value and not file_value:
            continue
        if not time_value or not file_value:
            return data, "Quran schedule entries require both time and file"
        quran_schedule.append({"time": time_value, "file": file_value})
    if quran_schedule:
        set_path(updated, ["audio", "quran_schedule"], quran_schedule)

    new_password = form.get("new_password", "")
    confirm_password = form.get("new_password_confirm", "")
    if new_password:
        if new_password != confirm_password:
            return data, "Password confirmation does not match"
        from werkzeug.security import generate_password_hash

        set_path(
            updated,
            ["control_panel", "auth", "password_hash"],
            generate_password_hash(new_password),
        )

    return updated, error


def _validate_config_data(config_path: Path, data: dict) -> Optional[str]:
    with tempfile.NamedTemporaryFile("w", delete=False) as tmp:
        tmp_path = Path(tmp.name)
        tmp.write(yaml.safe_dump(data, sort_keys=False))
    try:
        loader = ConfigLoader(config_path=tmp_path)
        loader.load()
    except ConfigError as exc:
        return str(exc)
    finally:
        tmp_path.unlink(missing_ok=True)
    return None


def _config_field_definitions() -> list[dict]:
    return [
        {"label": "City", "name": "location_city", "path": ["location", "city"], "type": "text"},
        {"label": "Madhab", "name": "location_madhab", "path": ["location", "madhab"], "type": "text"},
        {"label": "Timezone", "name": "location_timezone", "path": ["location", "timezone"], "type": "text"},
        {"label": "API Base URL", "name": "api_base_url", "path": ["api", "base_url"], "type": "text"},
        {"label": "API Timeout (sec)", "name": "api_timeout", "path": ["api", "timeout_seconds"], "type": "int"},
        {"label": "API Max Retries", "name": "api_max_retries", "path": ["api", "max_retries"], "type": "int"},
        {"label": "Prefetch Days", "name": "api_prefetch_days", "path": ["api", "prefetch_days"], "type": "int"},
        {"label": "Test Audio", "name": "audio_test", "path": ["audio", "test_audio"], "type": "text"},
        {"label": "Connected Tone", "name": "audio_connected", "path": ["audio", "connected_tone"], "type": "text"},
        {
            "label": "Background Keepalive Enabled (true/false)",
            "name": "audio_bg_enabled",
            "path": ["audio", "background_keepalive_enabled"],
            "type": "bool",
        },
        {
            "label": "Background Keepalive Audio File",
            "name": "audio_bg_path",
            "path": ["audio", "background_keepalive_path"],
            "type": "text",
        },
        {
            "label": "Background Keepalive Volume",
            "name": "audio_bg_volume",
            "path": ["audio", "background_keepalive_volume_percent"],
            "type": "int",
        },
        {
            "label": "Background Keepalive Loop (true/false)",
            "name": "audio_bg_loop",
            "path": ["audio", "background_keepalive_loop"],
            "type": "bool",
        },
        {
            "label": "Background Keepalive Nice (int, optional)",
            "name": "audio_bg_nice",
            "path": ["audio", "background_keepalive_nice"],
            "type": "int",
        },
        {
            "label": "Playback Timeout (sec)",
            "name": "audio_timeout",
            "path": ["audio", "playback_timeout_seconds"],
            "type": "int",
        },
        {
            "label": "Playback Timeout Strategy (fixed/auto, advanced)",
            "name": "audio_timeout_strategy",
            "path": ["audio", "playback_timeout_strategy"],
            "type": "text",
        },
        {
            "label": "Playback Timeout Buffer (sec)",
            "name": "audio_timeout_buffer",
            "path": ["audio", "playback_timeout_buffer_seconds"],
            "type": "int",
        },
        {"label": "Adhan Fajr", "name": "adhan_fajr", "path": ["audio", "adhan", "fajr"], "type": "text"},
        {"label": "Adhan Dhuhr", "name": "adhan_dhuhr", "path": ["audio", "adhan", "dhuhr"], "type": "text"},
        {"label": "Adhan Asr", "name": "adhan_asr", "path": ["audio", "adhan", "asr"], "type": "text"},
        {"label": "Adhan Maghrib", "name": "adhan_maghrib", "path": ["audio", "adhan", "maghrib"], "type": "text"},
        {"label": "Adhan Isha", "name": "adhan_isha", "path": ["audio", "adhan", "isha"], "type": "text"},
        {"label": "Notif Sunrise", "name": "notif_sunrise", "path": ["audio", "notifications", "sunrise"], "type": "text"},
        {"label": "Notif Sunset", "name": "notif_sunset", "path": ["audio", "notifications", "sunset"], "type": "text"},
        {"label": "Notif Midnight", "name": "notif_midnight", "path": ["audio", "notifications", "midnight"], "type": "text"},
        {"label": "Notif Tahajjud", "name": "notif_tahajjud", "path": ["audio", "notifications", "tahajjud"], "type": "text"},
        {"label": "Master Volume", "name": "vol_master", "path": ["audio", "volumes", "master_percent"], "type": "int"},
        {"label": "Adhan Volume", "name": "vol_adhan", "path": ["audio", "volumes", "adhan_percent"], "type": "int"},
        {
            "label": "Fajr Adhan Volume",
            "name": "vol_fajr",
            "path": ["audio", "volumes", "fajr_adhan_percent"],
            "type": "int",
        },
        {"label": "Quran Volume", "name": "vol_quran", "path": ["audio", "volumes", "quran_percent"], "type": "int"},
        {
            "label": "Notification Volume",
            "name": "vol_notif",
            "path": ["audio", "volumes", "notification_percent"],
            "type": "int",
        },
        {"label": "Test Volume", "name": "vol_test", "path": ["audio", "volumes", "test_percent"], "type": "int"},
        {"label": "Bluetooth MAC", "name": "bt_mac", "path": ["bluetooth", "device_mac"], "type": "text"},
        {
            "label": "Ensure Default Sink (true/false)",
            "name": "bt_default_sink",
            "path": ["bluetooth", "ensure_default_sink"],
            "type": "bool",
        },
        {"label": "Control Panel Enabled (true/false)", "name": "cp_enabled", "path": ["control_panel", "enabled"], "type": "bool"},
        {"label": "Control Panel Host", "name": "cp_host", "path": ["control_panel", "host"], "type": "text"},
        {"label": "Control Panel Port", "name": "cp_port", "path": ["control_panel", "port"], "type": "int"},
        {"label": "Control Panel Username", "name": "cp_user", "path": ["control_panel", "auth", "username"], "type": "text"},
        {
            "label": "Max Pending Tests",
            "name": "cp_tests_pending",
            "path": ["control_panel", "test_scheduler", "max_pending_tests"],
            "type": "int",
        },
        {
            "label": "Max Minutes Ahead",
            "name": "cp_tests_minutes",
            "path": ["control_panel", "test_scheduler", "max_minutes_ahead"],
            "type": "int",
        },
        {"label": "Log File Path", "name": "log_path", "path": ["logging", "file_path"], "type": "text"},
    ]


def _config_fields(data: dict) -> list[dict]:
    fields = []
    for field in _config_field_definitions():
        value = _get_path(data, field["path"])
        if value is None:
            value = ""
        fields.append(
            {
                "label": field["label"],
                "name": field["name"],
                "value": value,
            }
        )
    return fields


def _quran_form_fields(data: dict) -> list[dict]:
    entries = data.get("audio", {}).get("quran_schedule", [])
    fields = []
    for idx, entry in enumerate(entries):
        fields.append(
            {
                "time_name": f"quran_time_{idx}",
                "time_value": entry.get("time", ""),
                "file_name": f"quran_file_{idx}",
                "file_value": entry.get("file", ""),
            }
        )
    fields.append(
        {
            "time_name": f"quran_time_{len(entries)}",
            "time_value": "",
            "file_name": f"quran_file_{len(entries)}",
            "file_value": "",
        }
    )
    return fields


def _get_path(data: dict, keys: list[str]):
    current = data
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current


def _default_device_status(device_mac: Optional[str]) -> dict:
    runner = SubprocessCommandRunner()

    bluetooth = "unknown"
    if device_mac:
        result = runner.run(
            ["bluetoothctl", "info", device_mac],
            timeout=5,
        )
        if result.returncode == 0:
            bluetooth = "connected" if "Connected: yes" in result.stdout else "disconnected"
        else:
            bluetooth = "error"

    wifi = "unknown"
    if runner.which("iwgetid"):
        result = runner.run(["iwgetid", "-r"], timeout=3)
        if result.returncode == 0 and result.stdout.strip():
            wifi = result.stdout.strip()
        else:
            wifi = "disconnected"

    ip = "unknown"
    result = runner.run(["hostname", "-I"], timeout=3)
    if result.returncode == 0 and result.stdout.strip():
        ip = result.stdout.strip()

    return {"bluetooth": bluetooth, "wifi": wifi, "ip": ip}
