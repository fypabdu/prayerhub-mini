# PrayerHub Prototype Specification

This document outlines the detailed requirements and design plan for the PrayerHub headless prototype on a Raspberry Pi Zero 2W. The system will automatically play Adhan and Quran recitations at specified times, handle natural sound notifications, and manage Bluetooth audio output. It will follow SOLID object-oriented design principles for maintainability
GitHub
.

## High-Level Features

- **Adhan Playback:** Five calls to prayer per day (Fajr, Dhuhr, Asr, Maghrib, Isha) using provided audio files. Fajr Adhan plays at a lower volume. Prayer times are fetched from a Sri Lanka-specific prayer API
GitHub
.

- **Quran Recitation:** Scheduled recitations (configurable surah/audio file and timing, e.g. morning and evening). These also play at reduced volume.

- **Notifications:** Play provided natural sound files (e.g. birds chirping) at Tahajjud (late-night prayer), Sunrise, Sunset, and Islamic Midnight. Notification timings derive from prayer times (e.g. sunrise time, Islamic midnight).

- **Resilience:** System must handle power and internet outages gracefully. Prayer times are fetched daily (e.g. at midnight) and cached locally for offline use. The service auto-retries API calls if offline.

- **Bluetooth Audio:** Automatically pair and connect to a fixed Bluetooth speaker (Philips home theater via USB dongle). Ensure PulseAudio’s Bluetooth module is enabled so audio routes to the speaker
GitHub
. Verify successful connection by playing a short “connected” tone.

- **Control Panel:** A simple remote control interface (e.g. Flask web UI or a Telegram bot) for manual commands like volume up/down, play-on-demand, etc. The control panel can use the internet but core functionality works offline.

- **Configurability:** A configuration file (INI or YAML) on the device defines settings such as location/city for prayer times, audio file paths, volumes, enabled notifications, Bluetooth device name, and control-panel credentials. Libraries like Python’s configparser may be used for parsing
GitHub
.

- **Logging:** All key events, errors, and missed triggers should be logged to a file using Python’s built-in logging module
GitHub
. Logs help diagnose issues (e.g. playback failures, connection drops).

- **Autostart:** The application runs as a background service on boot (e.g. via a systemd service or init script) and restarts on failures.

## Design Principles

- **Object-Oriented & SOLID:** The code will be organized into classes (e.g. ConfigManager, PrayerTimeService, AudioPlayer, BluetoothManager, Scheduler, ControlPanel, etc.), each with a single responsibility
GitHub
. This ensures easy extension and testing. For instance, the audio playback class will handle only playing sounds (and setting volume), while the scheduler class only handles timing and job dispatch. Dependencies will be inverted where appropriate (e.g. high-level modules depending on abstractions/interfaces rather than concrete low-level modules)
GitHub
.

- **Modularity:** New features (e.g. adding a new type of notification sound) should require minimal code changes. The system should be open for extension but closed for modification: adding a new task should not require altering existing classes
GitHub
.

- **Configuration-Driven:** Behavior (e.g. which Surah to recite, which notifications to enable) is controlled by an external config file. This adheres to dependency inversion by keeping code generic and data-specific details in configs
GitHub
.

- **Error Handling:** The app should catch exceptions (e.g. failed API call, playback error) and log them without crashing the entire service. On failure (e.g. no internet), it should retry with exponential backoff.

## Technology Stack

- **Language:** Python 3.x (compatible with Pi Zero 2W).

- **Scheduler:** Use a lightweight in-process scheduler like APScheduler or schedule to trigger actions at specific times
GitHub
. For example, APScheduler can schedule jobs at daily prayer times.

- **HTTP Client:** Use requests (or httpx) to fetch prayer times from the REST API (e.g. GET /api/v1/times/today/?madhab=shafi&city=colombo)
GitHub
.

- **Audio Playback:** Use pygame’s SDL_mixer or a system player (e.g. omxplayer or mpg321) to play MP3/WAV files. Pygame supports simultaneous channels, volume control, and MP3/OGG playback
GitHub
. For example, pygame.mixer.Sound can play a sound and set its volume.

- **Bluetooth Audio:** Leverage Linux’s BlueZ/PulseAudio. Ensure the pulseaudio-module-bluetooth is installed and loaded; then pair/connect via bluetoothctl or pactl commands as needed
GitHub
. The BluetoothManager class will handle connecting/reconnecting to the fixed speaker name.

- **Configuration:** Store settings in a config file (INI or YAML). Use configparser (std lib) or configobj for easy parsing and validation
GitHub
. Configurable items: city/madhab for prayer API, scheduled Surah file names, volume levels, Bluetooth device name, enabled notifications, control panel settings (e.g. web port or bot token).

- **Web/Control Interface:** Use Flask (with optional Flask-Admin) to serve a minimal web UI, or a lightweight Telegram bot using python-telegram-bot. Flask-Admin can provide ready-made admin pages quickly
GitHub
. Endpoints/buttons will issue commands (e.g. POST /volume/up, /play/adhan). This component depends on other services to enact commands.

- **Logging:** Use Python’s logging module (configured to write to a rotating file) for all info/debug/error messages
GitHub
. Optionally, integrate loguru or structlog if structured logs are desired (but stdlib logging suffices).

## Component and Task Breakdown

The implementation will be divided into the following interdependent tasks. Each task lists its key responsibilities and dependencies.

### Environment & Dependency Setup (initialization)

**Description:** Prepare the Raspberry Pi OS and install required packages: Python, BlueZ/PulseAudio for Bluetooth, pulseaudio-module-bluetooth, python3-pip, etc. Install audio utilities (e.g. omxplayer or mpg321 for MP3 playback). Create a dedicated Python virtual environment.

**Key Steps:**

- Install system packages (Bluetooth, PulseAudio, audio codecs). Ensure module-bluetooth-discover can load
GitHub
.

- Set up Python environment and install Python libraries (requests, pygame, APScheduler, Flask, etc.).

- Create a systemd service (or init script) to launch the main Python app on boot.

- Ensure auto-reconnect on boot (e.g. attempt BT pairing at startup).

**Depends on:** None (base environment). Once complete, other tasks assume the OS and Python env are ready.

### ConfigManager (Configuration Management)

**Description:** Implement a ConfigManager class responsible for reading and validating all settings from a config file. Settings include: prayer times city/madhab, audio file paths (Adhan, Surahs, sounds), volume levels, schedule flags, Bluetooth speaker name, and control panel credentials.

**Key Steps:**

- Choose config format (INI or YAML). For example, use configparser
GitHub
. Define sections for prayers, recitations, notifications, bluetooth, control_panel, etc.

- On startup, load and validate the config (check that specified audio files exist, volumes in range 0-100, etc.). Provide fallback defaults as needed.

- Expose config values through methods/properties to other components.

**Depends on:** Environment Setup (to be able to read files and confirm dependencies).

### PrayerTimeService (Prayer Times Fetcher)

**Description:** A class to obtain daily prayer times from the Sri Lanka prayer API
GitHub
and supply them to the scheduler. It should run once daily (e.g. at midnight) or on demand.

**Key Steps:**

- Use the requests library to call endpoints like /api/v1/times/today/?madhab=shafi&city=colombo (parameters from config)
GitHub
. Parse the JSON response into a usable format (datetime objects for each prayer).

- Store fetched times in memory and persistently (e.g. local file or SQLite) as a cache. If the API call fails (no internet), fall back to the last cached times.

- Provide a method get_prayer_times() that returns the current day’s times for Fajr, Dhuhr, Asr, Maghrib, Isha, Sunrise, Midnight (as needed). Sunrise and Sunset can be inferred from Fajr/Maghrib if the API provides them, or from prayer-time-lk data.

- Optionally, handle time zone explicitly (though Sri Lanka has no DST) using pytz.

**Depends on:** ConfigManager (for city/madhab) and network (for API). Also on ConfigManager’s logging to record success/failure.

### BluetoothManager (Audio Connection)

**Description:** Manage Bluetooth pairing and connection to the speaker. This ensures audio output from the Pi is routed to the external speaker.

**Key Steps:**

- At startup and whenever needed, run bluetoothctl or pactl commands via subprocess to scan and connect to the configured device name. Ensure the pulseaudio-module-bluetooth is loaded
GitHub
.

- Periodically check if the speaker is connected (or listen for PulseAudio signals). If the connection drops, automatically retry.

- After establishing connection, play a short “connected” audio notification via the AudioPlayer to confirm.

**Depends on:** Environment Setup (pulseaudio module must be present), ConfigManager (for speaker name), and AudioPlayer (to play the test tone).

### AudioPlayer (Sound Playback)

**Description:** Handle playing of all audio files (Adhan, Quran, notifications) through the connected speaker. Provide controls for playback and volume.

**Key Steps:**

- Initialize an audio library (e.g. pygame.mixer.init()) or prepare subprocess commands (omxplayer/mpg321).

- Implement methods play_sound(file_path, volume) and set_volume(level) that play a given audio file at the specified volume. For pygame, set Sound.set_volume(). For subprocess, use command-line volume flags or OS mixer.

- Support overlapping playback if needed (e.g. ensure previous playback finishes or is stopped before next).

- Handle exceptions (e.g. file not found) and report errors to the logger.

**Depends on:** ConfigManager (for default volumes, file locations) and BluetoothManager (speaker must be connected). The AudioPlayer should verify the speaker is ready before playing.

### Scheduler / Job Manager

**Description:** Coordinate all time-based actions. Use a job scheduler (e.g. APScheduler
GitHub
) to trigger functions at specific times each day.

**Key Steps:**

- On startup (or at a fixed time each day), fetch today’s prayer times from PrayerTimeService. Then schedule jobs: five Adhan jobs (Fajr, Dhuhr, Asr, Maghrib, Isha), Quran recitations, and notifications. For example, scheduler.add_job(play_adhan, 'date', run_date=prayer_time).

- Each scheduled job will call into AudioPlayer: e.g. play_adhan(prayer_name) which selects the correct audio file and volume (Fajr lower). For Quran, schedule e.g. after Fajr and after Maghrib (configurable times). For notifications (e.g. Tahajjud ~ midnight, sunrise, sunset).

- Also schedule a daily job (at midnight) to refresh prayer times for the next day and reschedule accordingly. If fetch fails, log and try again later.

- Ensure that the jobs respect enabling/disabling in config (e.g. skip Tahajjud if disabled).

**Depends on:** PrayerTimeService (for times), AudioPlayer (to play sounds), BluetoothManager (speaker connection). ConfigManager (for which jobs are enabled and file mappings).

### Adhan & Recitation Playback Logic

**Description:** Implement the actual functions that are invoked by the scheduler for each type of audio event.

**Key Steps:**

- Adhan Handler: For each prayer job, play the corresponding Adhan file via AudioPlayer. If it is Fajr, reduce volume per config. Example:

```python
def play_adhan(prayer):
    file = config.adhan_files[prayer]  # e.g. 'adhan_fajr.mp3'
    vol = config.volume_fajr if prayer=='fajr' else config.volume_adhan
    audio_player.play_sound(file, vol)
```

- Quran Recitation Handler: At scheduled times, play the configured Surah file(s). Possibly multiple Surahs (if morning and evening). Use a separate volume setting (volume_quran).

- Notification Handler: At times like sunrise, sunset, midnight (Tahajjud), play the specified natural sound file (birds.mp3 etc) at configured volume.

- Log each playback with timestamp and outcome (success/failure) for auditing.

**Depends on:** Scheduler (to invoke these at correct times), AudioPlayer, ConfigManager (for file paths and volumes).

### Logging and Persistence

**Description:** Record events, errors, and cache data.

**Key Steps:**

- Configure a rolling logfile (e.g. daily or 7-day rotation) using Python’s logging module
GitHub
. Log levels: INFO for normal operations (e.g. “Adhan played”), WARNING/ERROR for issues.

- Log connectivity events (Bluetooth connect/disconnect), API fetch status, playback errors, and control-panel commands.

- Persist prayer time data and optionally other state in a simple store (JSON file or SQLite) so that on reboot the app knows when the next prayers are without immediate internet.

**Depends on:** ConfigManager (for log file path), all services (they emit logs), and filesystem permissions.

### Control Panel (Remote Control Interface)

**Description:** Provide a user interface for on-demand control. Options include:

- Web UI: A lightweight Flask app with pages/buttons (e.g. “Play Adhan Now”, “Volume Up/Down”, status display). Consider using Flask-Admin or basic HTML forms.

- Telegram Bot: A bot that listens for commands (/play_adhan, /vol_up etc) and invokes the corresponding methods. Requires internet for Telegram.

**Key Steps:**

- Implement endpoints or bot handlers that call into existing services (AudioPlayer, Scheduler, etc.). For example, hitting /command/play_adhan?prayer=isha would schedule an immediate Isha Adhan playback.

- Ensure actions are executed immediately (not delayed by scheduler). For volume commands, adjust AudioPlayer volume on the fly.

- Secure the interface if necessary (e.g. a simple token in Flask, or bot token for Telegram).

- The control panel does not block primary functions if offline; it should fail gracefully (e.g. show an error if Telegram API is unreachable).

**Depends on:** All services (it orchestrates them), and ConfigManager (for any API keys, ports). Depends on Environment (if using Flask, ensure web port is open).

### Service Orchestration & Autostart

**Description:** Tie all components together and ensure the app runs continuously.

**Key Steps:**

- In the main application entrypoint, initialize all managers (ConfigManager, BluetoothManager, PrayerTimeService, AudioPlayer, Scheduler, etc.), then start the scheduler event loop and (if applicable) the Flask/Telegram server (in a background thread or async).

- Implement clean shutdown handlers (catch SIGINT/SIGTERM to gracefully close resources).

- Verify the systemd service starts the app on boot and automatically restarts on failure.

- Test power-cycle recovery: after a reboot or crash, the app should pick up current prayer times (from cache or refetch) and continue scheduling future events.

**Depends on:** All components above. Completion of this task means the system is fully integrated and self-running.

### Testing and Validation

**Description:** Ensure each part works correctly through tests.

**Key Steps:**

- Unit test modules (e.g. parse config, call fake prayer API, simulate scheduler jobs).

- Integration test on Pi: simulate times to verify Adhan plays, disconnect Bluetooth to test reconnection, test offline mode by disabling internet, etc.

- Have checks in code that critical config fields exist (e.g. valid city name) and report errors early.

**Depends on:** Completed implementation. While not a separate deliverable, planning for testing is essential.

## Dependencies Summary

Each task depends on the completion of earlier tasks:

- ConfigManager cannot run until the environment (file I/O, Python libs) is set up.

- PrayerTimeService depends on the configuration (to know city/madhab) and network availability.

- BluetoothManager depends on PulseAudio being configured (from setup) and config (speaker name).

- AudioPlayer depends on the speaker being connected (BluetoothManager).

- Scheduler depends on PrayerTimeService (for times) and the ability to play audio (AudioPlayer).

- Playback Handlers depend on Scheduler and AudioPlayer.

- Control Panel depends on all services being available to handle commands.

- Logging is used by all components.

- Autostart (systemd service) depends on the entire app being ready to run unattended.

By following this plan, the PrayerHub prototype will be modular, maintainable, and fulfill all specified requirements with clear task dependencies. The use of Python libraries and hardware modules follows best practices (SOLID design
GitHub
, APScheduler for tasks
GitHub
, configparser for settings
GitHub
, and PulseAudio for Bluetooth audio
GitHub
). All tasks should be implemented in order, verifying each dependency as outlined above.

## Sources
