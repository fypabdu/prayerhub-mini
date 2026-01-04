from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import logging
from pathlib import Path
from typing import Callable, Optional, Sequence

from flask import Flask, redirect, render_template_string, request, session, url_for
from werkzeug.security import check_password_hash

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
      <option value="fajr">Fajr</option>
      <option value="dhuhr">Dhuhr</option>
      <option value="asr">Asr</option>
      <option value="maghrib">Maghrib</option>
      <option value="isha">Isha</option>
      <option value="sunrise">Sunrise</option>
      <option value="sunset">Sunset</option>
      <option value="midnight">Midnight</option>
      <option value="tahajjud">Tahajjud</option>
    </select>
  </label>
  <button type="submit">Play Now</button>
</form>
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
    host: str = "0.0.0.0"
    port: int = 8080
    volume_percent: int = 50
    volume_step: int = 5

    def __post_init__(self) -> None:
        self._logger = logging.getLogger(self.__class__.__name__)
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
            return render_template_string(
                DASHBOARD_TEMPLATE,
                next_jobs=next_jobs,
                test_jobs=test_jobs,
                logs=logs,
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
            return render_template_string(CONTROLS_TEMPLATE)

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
            if event and self.play_handler:
                self.play_handler(event)
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
