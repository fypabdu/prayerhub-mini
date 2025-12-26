from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any, Dict

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
    volumes: AudioVolumes


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
class AppConfig:
    location: LocationConfig
    api: ApiConfig
    audio: AudioConfig
    bluetooth: BluetoothConfig
    control_panel: ControlPanelConfig


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
    def __init__(self, root_dir: Path | None = None) -> None:
        self._root_dir = root_dir

    def load(self) -> AppConfig:
        root_dir = self._resolve_root_dir()
        config_path = root_dir / "config.yml"
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
        env_dir = os.getenv("PRAYERHUB_CONFIG_DIR")
        if env_dir:
            return Path(env_dir)
        return Path("/etc/prayerhub")

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
        audio = AudioConfig(
            test_audio=audio_data["test_audio"],
            connected_tone=audio_data["connected_tone"],
            volumes=volumes,
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
        return AppConfig(
            location=location,
            api=api,
            audio=audio,
            bluetooth=bluetooth,
            control_panel=control_panel,
        )

    def _validate(self, config: AppConfig) -> None:
        self._validate_audio_paths(config.audio)
        self._validate_volumes(config.audio.volumes)
        self._validate_control_panel(config.control_panel)

    def _validate_audio_paths(self, audio: AudioConfig) -> None:
        test_audio_path = Path(audio.test_audio)
        if not test_audio_path.is_absolute():
            test_audio_path = Path.cwd() / test_audio_path
        if not test_audio_path.exists():
            raise ConfigError(f"Test audio file does not exist: {test_audio_path}")

    def _validate_volumes(self, volumes: AudioVolumes) -> None:
        for name, value in vars(volumes).items():
            if not 0 <= value <= 100:
                raise ConfigError(f"Volume percent out of range for {name}: {value}")

    def _validate_control_panel(self, control_panel: ControlPanelConfig) -> None:
        if not control_panel.enabled:
            return
        if not control_panel.auth.username:
            raise ConfigError("Control panel username is required")
        if not control_panel.auth.password_hash:
            raise ConfigError("Control panel password_hash is required")
