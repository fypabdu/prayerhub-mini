from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path
from typing import Iterable, Optional

from prayerhub.cache_store import CacheStore
from prayerhub.config import AudioConfig, ConfigError, ConfigLoader
from prayerhub.logging_utils import LoggerFactory
from prayerhub.prayer_api import PrayerApiClient
from prayerhub.prayer_times import PrayerTimeService
from prayerhub.scheduler import JobScheduler
from prayerhub.startup import schedule_from_cache, schedule_refresh
from prayerhub.test_scheduler import TestScheduleService


def main(argv: Optional[Iterable[str]] = None) -> int:
    args = _parse_args(argv)
    try:
        config_path = Path(args.config) if args.config else None
        config_loader = ConfigLoader(config_path=config_path)
        config = config_loader.load()
    except ConfigError as exc:
        LoggerFactory.create("prayerhub")
        logger = logging.getLogger("prayerhub")
        logger.error("Config error: %s", exc)
        return 2

    log_path = os.getenv("PRAYERHUB_LOG_PATH") or config.logging.file_path
    LoggerFactory.create("prayerhub", log_file=log_path)
    logger = logging.getLogger("prayerhub")
    logger.info("Config summary: %s", _config_summary(config))

    cache_dir = Path(os.getenv("PRAYERHUB_CACHE_DIR", "/var/lib/prayerhub/cache"))
    cache_store = CacheStore(cache_dir)

    api_client = PrayerApiClient(
        base_url=config.api.base_url,
        timeout_seconds=config.api.timeout_seconds,
        max_retries=config.api.max_retries,
    )
    prayer_service = PrayerTimeService(
        api_client=api_client,
        cache_store=cache_store,
        city=config.location.city,
        madhab=config.location.madhab,
    )

    # Import APScheduler/Flask only after config is valid to avoid noisy failures.
    from apscheduler.schedulers.background import BackgroundScheduler

    scheduler = BackgroundScheduler()
    job_handler = _make_noop_handler(logger, dry_run=args.dry_run)
    audio_router = None
    play_handler = None
    keepalive_service = None
    bluetooth = None
    if not args.dry_run:
        from prayerhub.audio import AudioPlayer, AudioRouter
        from prayerhub.bluetooth import BluetoothManager
        from prayerhub.command_runner import SubprocessCommandRunner
        from prayerhub.background_keepalive import BackgroundKeepAliveService
        from prayerhub.playback import PlaybackHandler
        from prayerhub.playback_timeout import FfprobeDurationProbe, PlaybackTimeoutPolicy

        runner = SubprocessCommandRunner()
        router = AudioRouter(runner)
        keepalive_service = None
        if config.audio.background_keepalive_enabled:
            keepalive_service = BackgroundKeepAliveService(
                runner=runner,
                bluetooth=None,
                audio_file=config.audio.background_keepalive_path,
                volume_percent=config.audio.background_keepalive_volume_percent,
                loop=config.audio.background_keepalive_loop,
                nice_level=config.audio.background_keepalive_nice,
                volume_cycle_enabled=config.audio.background_keepalive_volume_cycle_enabled,
                volume_cycle_min_percent=config.audio.background_keepalive_volume_cycle_min_percent,
                volume_cycle_max_percent=config.audio.background_keepalive_volume_cycle_max_percent,
                volume_cycle_step_seconds=config.audio.background_keepalive_volume_cycle_step_seconds,
            )
        player = AudioPlayer(runner, router, monitor=keepalive_service)
        duration_probe = FfprobeDurationProbe(
            runner,
            timeout_seconds=config.audio.ffprobe_timeout_seconds,
        )
        if config.audio.playback_timeout_strategy == "auto":
            _prewarm_duration_cache(duration_probe, config.audio)
        timeout_policy = PlaybackTimeoutPolicy(
            strategy=config.audio.playback_timeout_strategy,
            fallback_seconds=config.audio.playback_timeout_seconds,
            buffer_seconds=config.audio.playback_timeout_buffer_seconds,
            duration_probe=duration_probe,
        )
        bluetooth = BluetoothManager(
            runner=runner,
            audio_router=router,
            device_mac=config.bluetooth.device_mac,
            ensure_default_sink=config.bluetooth.ensure_default_sink,
            connected_tone_path=Path(config.audio.connected_tone),
            connected_tone_player=player,
            connected_tone_volume_percent=config.audio.volumes.notification_percent,
        )
        playback = PlaybackHandler(
            bluetooth=bluetooth,
            player=player,
            audio=config.audio,
            timeout_policy=timeout_policy,
        )
        audio_router = router
        play_handler = playback.handle_event

        if keepalive_service is not None:
            keepalive_service.bluetooth = bluetooth

        def handle(plan, name):
            logger.info("Executing scheduled event %s for %s", name, plan.date)
            playback.handle_event(name)

        job_handler = handle

    job_scheduler = JobScheduler(
        scheduler=scheduler,
        handler=job_handler,
    )

    test_handler = _make_noop_test_handler(logger, dry_run=args.dry_run)
    if play_handler is not None:
        test_handler = lambda: play_handler("test_audio")

    test_scheduler = TestScheduleService(
        scheduler=scheduler,
        now_provider=job_scheduler.now_provider,
        handler=test_handler,
        max_pending_tests=config.control_panel.test_scheduler.max_pending_tests,
        max_minutes_ahead=config.control_panel.test_scheduler.max_minutes_ahead,
    )

    if args.dry_run:
        # Dry-run should not block; it just validates config and wiring.
        logger.info("Dry-run mode enabled; no audio will play.")
        logger.info("Scheduled jobs: %s", scheduler.get_jobs())
        return 0

    quran_times = [item.time for item in config.audio.quran_schedule]
    schedule_from_cache(cache_store, job_scheduler, quran_times=quran_times)
    schedule_refresh(
        job_scheduler,
        prayer_service,
        config.api.prefetch_days,
        quran_times=quran_times,
    )
    if keepalive_service is not None:
        keepalive_service.resume_if_idle()
        logger.info(
            "Background keepalive enabled: file=%s volume=%s loop=%s",
            config.audio.background_keepalive_path,
            config.audio.background_keepalive_volume_percent,
            config.audio.background_keepalive_loop,
        )
    else:
        logger.info("Background keepalive disabled")

    if config.control_panel.enabled:
        from prayerhub.control_panel import ControlPanelServer

        secret_key = os.getenv("PRAYERHUB_SECRET_KEY", "prayerhub-dev")
        server = ControlPanelServer(
            username=config.control_panel.auth.username,
            password_hash=config.control_panel.auth.password_hash,
            test_scheduler=test_scheduler,
            secret_key=secret_key,
            host=config.control_panel.host,
            port=config.control_panel.port,
            scheduler=scheduler,
            audio_router=audio_router,
            play_handler=play_handler,
            log_path=log_path,
            quran_times=tuple(quran_times),
            config_path=str(config_path) if config_path else None,
            device_mac=config.bluetooth.device_mac,
            prayer_service=prayer_service,
            command_runner=runner,
            keepalive_service=keepalive_service,
        )
        scheduler.start()
        logger.info("Starting control panel on %s:%s", server.host, server.port)
        server.app.run(host=server.host, port=server.port)
    else:
        logger.info("Control panel disabled; scheduler starting only.")
        scheduler.start()

    return 0


def _config_summary(config) -> dict:
    return {
        "location": {
            "city": config.location.city,
            "madhab": config.location.madhab,
            "timezone": config.location.timezone,
        },
        "api": {
            "base_url": config.api.base_url,
            "timeout_seconds": config.api.timeout_seconds,
            "max_retries": config.api.max_retries,
            "prefetch_days": config.api.prefetch_days,
        },
        "audio": {
            "test_audio": config.audio.test_audio,
            "connected_tone": config.audio.connected_tone,
            "background_keepalive_enabled": config.audio.background_keepalive_enabled,
            "background_keepalive_path": config.audio.background_keepalive_path,
            "background_keepalive_volume_percent": config.audio.background_keepalive_volume_percent,
            "background_keepalive_loop": config.audio.background_keepalive_loop,
            "background_keepalive_nice": config.audio.background_keepalive_nice,
            "background_keepalive_volume_cycle_enabled": config.audio.background_keepalive_volume_cycle_enabled,
            "background_keepalive_volume_cycle_min_percent": config.audio.background_keepalive_volume_cycle_min_percent,
            "background_keepalive_volume_cycle_max_percent": config.audio.background_keepalive_volume_cycle_max_percent,
            "background_keepalive_volume_cycle_step_seconds": config.audio.background_keepalive_volume_cycle_step_seconds,
            "adhan": {
                "fajr": config.audio.adhan.fajr,
                "dhuhr": config.audio.adhan.dhuhr,
                "asr": config.audio.adhan.asr,
                "maghrib": config.audio.adhan.maghrib,
                "isha": config.audio.adhan.isha,
            },
            "quran_schedule": [item.time for item in config.audio.quran_schedule],
            "notifications": {
                "sunrise": config.audio.notifications.sunrise,
                "sunset": config.audio.notifications.sunset,
                "midnight": config.audio.notifications.midnight,
                "tahajjud": config.audio.notifications.tahajjud,
            },
            "volumes": {
                "master_percent": config.audio.volumes.master_percent,
                "adhan_percent": config.audio.volumes.adhan_percent,
                "fajr_adhan_percent": config.audio.volumes.fajr_adhan_percent,
                "quran_percent": config.audio.volumes.quran_percent,
                "notification_percent": config.audio.volumes.notification_percent,
                "test_percent": config.audio.volumes.test_percent,
            },
            "playback_timeout_seconds": config.audio.playback_timeout_seconds,
            "playback_timeout_strategy": config.audio.playback_timeout_strategy,
            "playback_timeout_buffer_seconds": config.audio.playback_timeout_buffer_seconds,
            "ffprobe_timeout_seconds": config.audio.ffprobe_timeout_seconds,
        },
        "bluetooth": {
            "device_mac": config.bluetooth.device_mac,
            "ensure_default_sink": config.bluetooth.ensure_default_sink,
        },
        "control_panel": {
            "enabled": config.control_panel.enabled,
            "host": config.control_panel.host,
            "port": config.control_panel.port,
            "auth": {
                "username": config.control_panel.auth.username,
            },
            "test_scheduler": {
                "max_pending_tests": config.control_panel.test_scheduler.max_pending_tests,
                "max_minutes_ahead": config.control_panel.test_scheduler.max_minutes_ahead,
            },
        },
        "logging": {
            "file_path": config.logging.file_path,
        },
    }


def _prewarm_duration_cache(duration_probe, audio: AudioConfig) -> None:
    logger = logging.getLogger("AudioDurationPrewarm")
    paths = []
    paths.append(_resolve_audio_path(audio.test_audio))
    for name in ("fajr", "dhuhr", "asr", "maghrib", "isha"):
        paths.append(_resolve_audio_path(getattr(audio.adhan, name)))
    for item in audio.quran_schedule:
        paths.append(_resolve_audio_path(item.file))
    for name in ("sunrise", "sunset", "midnight", "tahajjud"):
        paths.append(_resolve_audio_path(getattr(audio.notifications, name)))

    seen = set()
    probed = 0
    logger.info("Prewarming audio durations for %s files", len(paths))
    for path in paths:
        if path in seen:
            continue
        seen.add(path)
        try:
            logger.info("Prewarm duration for %s", path)
            duration_probe.duration_seconds(path)
            probed += 1
        except Exception as exc:
            logger.warning("Audio duration prewarm failed for %s: %s", path, exc)
    logger.info("Prewarm complete: %s files probed", probed)


def _resolve_audio_path(path_str: str) -> Path:
    path = Path(path_str)
    if path.is_absolute():
        return path
    return Path.cwd() / path

def _parse_args(argv: Optional[Iterable[str]]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="PrayerHub Mini")
    parser.add_argument("--config", help="Path to config.yml")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate config and scheduler wiring without playing audio",
    )
    return parser.parse_args(argv)


def _make_noop_handler(logger: logging.Logger, dry_run: bool):
    def handler(*_args, **_kwargs):
        # We keep a no-op handler until audio events are wired in T14.
        if dry_run:
            logger.info("Dry-run: skipping audio playback")
        else:
            logger.warning("Playback handler not yet implemented")

    return handler


def _make_noop_test_handler(logger: logging.Logger, dry_run: bool):
    def handler():
        # Tests should not play audio; log instead for traceability.
        if dry_run:
            logger.info("Dry-run test audio trigger")
        else:
            logger.warning("Test audio handler not yet implemented")

    return handler


if __name__ == "__main__":
    raise SystemExit(main())
