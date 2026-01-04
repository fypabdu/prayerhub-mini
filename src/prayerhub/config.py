from __future__ import annotations


from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml


class ConfigError(ValueError):
    """Raised when configuration loading or validation fails."""


@dataclass(frozen=True)
class LocationConfig:
    city: str
    madhab: str
    timezone: str


@dataclass(frozen=True)
class ApiConfig:
    base_url: str
    timeout_seconds: int
    max_retries: int
    prefetch_days: int


@dataclass(frozen=True)
class AudioVolumes:
    master_percent: int
    adhan_percent: int
    fajr_adhan_percent: int
    quran_percent: int
    notification_percent: int
    test_percent: int


@dataclass(frozen=True)
class AudioConfig:
    test_audio: str
    connected_tone: str
    adhan: "AdhanAudio"
    quran_schedule: tuple["QuranScheduleItem", ...]
    notifications: "NotificationAudio"
    volumes: AudioVolumes
    playback_timeout_seconds: int


@dataclass(frozen=True)
class BluetoothConfig:
    device_mac: str
    ensure_default_sink: bool


@dataclass(frozen=True)
class ControlPanelAuthConfig:
    username: str
    password_hash: str


@dataclass(frozen=True)
class ControlPanelTestSchedulerConfig:
    max_pending_tests: int
    max_minutes_ahead: int


@dataclass(frozen=True)
class ControlPanelConfig:
    enabled: bool
    host: str
    port: int
    auth: ControlPanelAuthConfig
    test_scheduler: ControlPanelTestSchedulerConfig


@dataclass(frozen=True)
class LoggingConfig:
    file_path: Optional[str]


@dataclass(frozen=True)
class AdhanAudio:
    fajr: str
    dhuhr: str
    asr: str
    maghrib: str
    isha: str


@dataclass(frozen=True)
class QuranScheduleItem:
    time: str
    file: str


@dataclass(frozen=True)
class NotificationAudio:
    sunrise: str
    sunset: str
    midnight: str
    tahajjud: str


@dataclass(frozen=True)
class AppConfig:
    location: LocationConfig
    api: ApiConfig
    audio: AudioConfig
    bluetooth: BluetoothConfig
    control_panel: ControlPanelConfig
    logging: LoggingConfig


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    merged: Dict[str, Any] = dict(base)
    for key, value in override.items():
        if (
            key in merged
            and isinstance(merged[key], dict)
            and isinstance(value, dict)
        ):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _load_yaml(path: Path) -> Dict[str, Any]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ConfigError(f"Failed to read config file: {path}") from exc
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ConfigError(f"Expected mapping at root of config file: {path}")
    return data


class ConfigLoader:
    def __init__(self, root_dir: Path | None = None, config_path: Path | None = None) -> None:
        self._root_dir = root_dir
        self._config_path = config_path

    def load(self) -> AppConfig:
        root_dir = self._resolve_root_dir()
        config_path = self._resolve_config_path(root_dir)
        if not config_path.exists():
            raise ConfigError(f"Missing base config file: {config_path}")

        merged: Dict[str, Any] = {}
        merged = _deep_merge(merged, _load_yaml(config_path))

        config_d = root_dir / "config.d"
        if config_d.exists():
            for path in sorted(config_d.glob("*.yml")):
                merged = _deep_merge(merged, _load_yaml(path))

        secrets_path = root_dir / "secrets.yml"
        if secrets_path.exists():
            merged = _deep_merge(merged, _load_yaml(secrets_path))

        config = self._build_config(merged)
        self._validate(config)
        return config

    def _resolve_root_dir(self) -> Path:
        if self._root_dir is not None:
            return self._root_dir
        if self._config_path is not None:
            return self._config_path.parent
        env_dir = os.getenv("PRAYERHUB_CONFIG_DIR")
        if env_dir:
            return Path(env_dir)
        return Path("/etc/prayerhub")

    def _resolve_config_path(self, root_dir: Path) -> Path:
        if self._config_path is not None:
            return self._config_path
        return root_dir / "config.yml"

    def _build_config(self, data: Dict[str, Any]) -> AppConfig:
        try:
            location_data = data["location"]
            api_data = data["api"]
            audio_data = data["audio"]
            bluetooth_data = data["bluetooth"]
            control_panel_data = data["control_panel"]
        except KeyError as exc:
            raise ConfigError(f"Missing config section: {exc.args[0]}") from exc

        location = LocationConfig(
            city=location_data["city"],
            madhab=location_data["madhab"],
            timezone=location_data["timezone"],
        )
        api = ApiConfig(
            base_url=api_data["base_url"],
            timeout_seconds=int(api_data["timeout_seconds"]),
            max_retries=int(api_data["max_retries"]),
            prefetch_days=int(api_data["prefetch_days"]),
        )
        volumes_data = audio_data["volumes"]
        volumes = AudioVolumes(
            master_percent=int(volumes_data["master_percent"]),
            adhan_percent=int(volumes_data["adhan_percent"]),
            fajr_adhan_percent=int(volumes_data["fajr_adhan_percent"]),
            quran_percent=int(volumes_data["quran_percent"]),
            notification_percent=int(volumes_data["notification_percent"]),
            test_percent=int(volumes_data["test_percent"]),
        )
        adhan_data = audio_data["adhan"]
        adhan = AdhanAudio(
            fajr=adhan_data["fajr"],
            dhuhr=adhan_data["dhuhr"],
            asr=adhan_data["asr"],
            maghrib=adhan_data["maghrib"],
            isha=adhan_data["isha"],
        )
        quran_schedule = tuple(
            QuranScheduleItem(time=item["time"], file=item["file"])
            for item in audio_data.get("quran_schedule", [])
        )
        notifications_data = audio_data["notifications"]
        notifications = NotificationAudio(
            sunrise=notifications_data["sunrise"],
            sunset=notifications_data["sunset"],
            midnight=notifications_data["midnight"],
            tahajjud=notifications_data["tahajjud"],
        )
        audio = AudioConfig(
            test_audio=audio_data["test_audio"],
            connected_tone=audio_data["connected_tone"],
            adhan=adhan,
            quran_schedule=quran_schedule,
            notifications=notifications,
            volumes=volumes,
            playback_timeout_seconds=int(audio_data.get("playback_timeout_seconds", 300)),
        )
        bluetooth = BluetoothConfig(
            device_mac=bluetooth_data["device_mac"],
            ensure_default_sink=bool(bluetooth_data["ensure_default_sink"]),
        )
        auth_data = control_panel_data["auth"]
        test_scheduler_data = control_panel_data["test_scheduler"]
        control_panel = ControlPanelConfig(
            enabled=bool(control_panel_data["enabled"]),
            host=control_panel_data["host"],
            port=int(control_panel_data["port"]),
            auth=ControlPanelAuthConfig(
                username=auth_data.get("username", ""),
                password_hash=auth_data.get("password_hash", ""),
            ),
            test_scheduler=ControlPanelTestSchedulerConfig(
                max_pending_tests=int(test_scheduler_data["max_pending_tests"]),
                max_minutes_ahead=int(test_scheduler_data["max_minutes_ahead"]),
            ),
        )
        logging_data = data.get("logging", {})
        logging_config = LoggingConfig(
            file_path=logging_data.get("file_path"),
        )
        return AppConfig(
            location=location,
            api=api,
            audio=audio,
            bluetooth=bluetooth,
            control_panel=control_panel,
            logging=logging_config,
        )

    def _validate(self, config: AppConfig) -> None:
        self._validate_audio_paths(config.audio)
        self._validate_volumes(config.audio.volumes)
        self._validate_audio_timeout(config.audio)
        self._validate_control_panel(config.control_panel)

    def _validate_audio_paths(self, audio: AudioConfig) -> None:
        audio_paths = [
            ("test_audio", audio.test_audio),
            ("connected_tone", audio.connected_tone),
            ("adhan_fajr", audio.adhan.fajr),
            ("adhan_dhuhr", audio.adhan.dhuhr),
            ("adhan_asr", audio.adhan.asr),
            ("adhan_maghrib", audio.adhan.maghrib),
            ("adhan_isha", audio.adhan.isha),
            ("notification_sunrise", audio.notifications.sunrise),
            ("notification_sunset", audio.notifications.sunset),
            ("notification_midnight", audio.notifications.midnight),
            ("notification_tahajjud", audio.notifications.tahajjud),
        ]
        for item in audio.quran_schedule:
            audio_paths.append((f"quran_{item.time}", item.file))

        for label, path_str in audio_paths:
            path = Path(path_str)
            if not path.is_absolute():
                path = Path.cwd() / path
            if not path.exists():
                raise ConfigError(f"Audio file does not exist ({label}): {path}")

    def _validate_volumes(self, volumes: AudioVolumes) -> None:
        for name, value in vars(volumes).items():
            if not 0 <= value <= 100:
                raise ConfigError(f"Volume percent out of range for {name}: {value}")

    def _validate_audio_timeout(self, audio: AudioConfig) -> None:
        if audio.playback_timeout_seconds <= 0:
            raise ConfigError("playback_timeout_seconds must be greater than zero")

    def _validate_control_panel(self, control_panel: ControlPanelConfig) -> None:
        if not control_panel.enabled:
            return
        if not control_panel.auth.username:
            raise ConfigError("Control panel username is required")
        if not control_panel.auth.password_hash:
            raise ConfigError("Control panel password_hash is required")
