from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Optional

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
<p><a href="{{ url_for('test_page') }}">Test audio</a></p>
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
    host: str = "0.0.0.0"
    port: int = 8080

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
            return render_template_string(DASHBOARD_TEMPLATE)

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
            # Placeholder to keep routes stable while controls are built out.
            return "<h1>Controls</h1>"

        return app
