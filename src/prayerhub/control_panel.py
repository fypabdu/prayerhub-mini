from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import logging
from pathlib import Path
import tempfile
from typing import Callable, Optional, Sequence

import yaml

from flask import Flask, redirect, render_template_string, request, session, url_for
from werkzeug.security import check_password_hash

from prayerhub.command_runner import SubprocessCommandRunner
from prayerhub.config import ConfigError, ConfigLoader
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


DASHBOARD_TEMPLATE = """
<!doctype html>
<title>PrayerHub Dashboard</title>
<h1>PrayerHub</h1>
<p>Status: OK</p>
<h2>Next Events</h2>
<ul>
{% for job in next_jobs %}
  <li>{{ job.id }} at {{ job.run_date }}</li>
{% else %}
  <li>No scheduled events.</li>
{% endfor %}
</ul>

<h2>Pending Test Jobs</h2>
<ul>
{% for job in test_jobs %}
  <li>{{ job.id }} at {{ job.run_date }}</li>
{% else %}
  <li>No pending tests.</li>
{% endfor %}
</ul>

<h2>Recent Logs</h2>
<pre>{{ logs }}</pre>
<p><a href="{{ url_for('test_page') }}">Test audio</a></p>
<p><a href="{{ url_for('controls') }}">Controls</a></p>
<p><a href="{{ url_for('config_page') }}">Config</a></p>

<h2>Device Status</h2>
<ul>
  <li>Bluetooth: {{ device_status.bluetooth }}</li>
  <li>Wi-Fi: {{ device_status.wifi }}</li>
  <li>IP: {{ device_status.ip }}</li>
</ul>
"""

STATUS_TEMPLATE = """
<!doctype html>
<title>PrayerHub Status</title>
<h1>PrayerHub Status</h1>
<p>Status: OK</p>
<h2>Next Events</h2>
<ul>
{% for job in next_jobs %}
  <li>{{ job.id }} at {{ job.run_date }}</li>
{% else %}
  <li>No scheduled events.</li>
{% endfor %}
</ul>

<h2>Pending Test Jobs</h2>
<ul>
{% for job in test_jobs %}
  <li>{{ job.id }} at {{ job.run_date }}</li>
{% else %}
  <li>No pending tests.</li>
{% endfor %}
</ul>
"""


TEST_TEMPLATE = """
<!doctype html>
<title>Test Audio</title>
<h1>Schedule Test Audio</h1>
<form method="post" action="{{ url_for('schedule_test') }}">
  <label>Time (HH:MM) <input name="time" /></label><br />
  <label>In minutes <input name="minutes" /></label><br />
  <button type="submit">Schedule</button>
</form>

<h2>Pending Tests</h2>
<ul>
{% for job in jobs %}
  <li>
    {{ job.id }} at {{ job.run_date }}
    <form method="post" action="{{ url_for('cancel_test', job_id=job.id) }}" style="display:inline">
      <button type="submit">Cancel</button>
    </form>
  </li>
{% else %}
  <li>No pending jobs.</li>
{% endfor %}
</ul>
"""

CONTROLS_TEMPLATE = """
<!doctype html>
<title>Controls</title>
<h1>Controls</h1>
<form method="post" action="{{ url_for('volume_control') }}">
  <button name="direction" value="up" type="submit">Volume Up</button>
  <button name="direction" value="down" type="submit">Volume Down</button>
</form>

<form method="post" action="{{ url_for('play_now') }}">
  <label>Event
    <select name="event">
      <option value="test_audio">Test Audio</option>
      <option value="fajr">Fajr</option>
      <option value="dhuhr">Dhuhr</option>
      <option value="asr">Asr</option>
      <option value="maghrib">Maghrib</option>
      <option value="isha">Isha</option>
      <option value="sunrise">Sunrise</option>
      <option value="sunset">Sunset</option>
      <option value="midnight">Midnight</option>
      <option value="tahajjud">Tahajjud</option>
      {% for time in quran_times %}
      <option value="quran@{{ time }}">Quran {{ time }}</option>
      {% endfor %}
    </select>
  </label>
  <button type="submit">Play Now</button>
</form>
"""

CONFIG_TEMPLATE = """
<!doctype html>
<title>Config</title>
<h1>Configuration</h1>
{% if error %}<p style="color:red">{{ error }}</p>{% endif %}
{% if message %}<p style="color:green">{{ message }}</p>{% endif %}
<form method="post">
  <h2>General</h2>
  {% for field in fields %}
    <label>{{ field.label }}
      <input name="{{ field.name }}" value="{{ field.value }}" />
    </label><br />
  {% endfor %}

  <h2>Quran Schedule</h2>
  {% for item in quran_fields %}
    <label>Time <input name="{{ item.time_name }}" value="{{ item.time_value }}" /></label>
    <label>File <input name="{{ item.file_name }}" value="{{ item.file_value }}" /></label>
    <br />
  {% endfor %}

  <h2>Update Password</h2>
  <label>New password <input type="password" name="new_password" /></label><br />
  <label>Confirm <input type="password" name="new_password_confirm" /></label><br />

  <button type="submit">Save</button>
</form>
<p>Restart the service to apply changes.</p>
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
    quran_times: Sequence[str] = ()
    host: str = "0.0.0.0"
    port: int = 8080
    volume_percent: int = 50
    volume_step: int = 5

    def __post_init__(self) -> None:
        self._logger = logging.getLogger(self.__class__.__name__)
        self._allowed_events = self._build_allowed_events()
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
            next_jobs = _sorted_jobs(self.scheduler, limit=5)
            test_jobs = self.test_scheduler.list_test_jobs()
            logs = _tail_log(self.log_path, lines=20)
            device_status = self._device_status()
            return render_template_string(
                DASHBOARD_TEMPLATE,
                next_jobs=next_jobs,
                test_jobs=test_jobs,
                logs=logs,
                device_status=device_status,
            )

        @app.route("/status")
        @_login_required
        def status():
            next_jobs = _sorted_jobs(self.scheduler, limit=5)
            test_jobs = self.test_scheduler.list_test_jobs()
            return render_template_string(
                STATUS_TEMPLATE,
                next_jobs=next_jobs,
                test_jobs=test_jobs,
            )

        @app.route("/test")
        @_login_required
        def test_page():
            jobs = self.test_scheduler.list_test_jobs()
            return render_template_string(TEST_TEMPLATE, jobs=jobs)

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
            return render_template_string(
                CONTROLS_TEMPLATE,
                quran_times=self.quran_times,
            )

        @app.route("/config", methods=["GET", "POST"])
        @_login_required
        def config_page():
            config_path = self._resolve_config_path()
            if config_path is None:
                return render_template_string(
                    CONFIG_TEMPLATE,
                    fields=[],
                    quran_fields=[],
                    error="Config path is not configured.",
                    message=None,
                )
            error = None
            message = None
            data = _load_config_data(config_path)

            if request.method == "POST":
                data, error = _apply_config_form(data, request.form)
                if error is None:
                    error = _validate_config_data(config_path, data)
                if error is None:
                    _save_config_data(config_path, data)
                    message = "Saved. Restart the service to apply changes."

            fields = _config_fields(data)
            quran_fields = _quran_form_fields(data)
            return render_template_string(
                CONFIG_TEMPLATE,
                fields=fields,
                quran_fields=quran_fields,
                error=error,
                message=message,
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
            return self.device_status_provider()
        return _default_device_status(self.device_mac)


def _sorted_jobs(scheduler: Optional[object], limit: int) -> Sequence[object]:
    if scheduler is None:
        return []
    try:
        jobs = scheduler.get_jobs()
    except Exception:
        return []
    return sorted(jobs, key=lambda job: job.next_run_time or datetime.max)[:limit]


def _tail_log(log_path: Optional[str], lines: int) -> str:
    if not log_path:
        return "No log file configured."
    try:
        path = Path(log_path)
        if not path.exists():
            return "Log file not found."
        content = path.read_text(encoding="utf-8")
    except OSError:
        return "Log unavailable."

    parts = content.splitlines()
    return "\n".join(parts[-lines:])


def _load_config_data(path: Path) -> dict:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _save_config_data(path: Path, data: dict) -> None:
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


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
            "label": "Playback Timeout (sec)",
            "name": "audio_timeout",
            "path": ["audio", "playback_timeout_seconds"],
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
        {"label": "Keepalive Enabled (true/false)", "name": "ka_enabled", "path": ["keepalive", "enabled"], "type": "bool"},
        {
            "label": "Keepalive Interval (min)",
            "name": "ka_interval",
            "path": ["keepalive", "interval_minutes"],
            "type": "int",
        },
        {"label": "Keepalive Audio File", "name": "ka_audio", "path": ["keepalive", "audio_file"], "type": "text"},
        {
            "label": "Keepalive Volume",
            "name": "ka_volume",
            "path": ["keepalive", "volume_percent"],
            "type": "int",
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
