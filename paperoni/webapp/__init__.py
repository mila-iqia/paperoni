import logging

from .common import config


def _get_level(level_name: str) -> int:
    level = logging.getLevelName(level_name)
    return level if isinstance(level, int) else logging.INFO


cfg = config()

if hasattr(cfg, "sentry") and cfg.sentry.use:
    import sentry_sdk
    # Configure sentry to collect log events with minimal level INFO
    # (2023/10/25) https://docs.sentry.io/platforms/python/integrations/logging/
    from sentry_sdk.integrations.logging import LoggingIntegration

    sentry_sdk.init(
        dsn=cfg.sentry.dsn,
        traces_sample_rate=cfg.sentry.traces_sample_rate,
        environment=cfg.sentry.environment,
        integrations=[
            LoggingIntegration(
                level=_get_level(cfg.sentry.log_level),
                event_level=_get_level(cfg.sentry.event_log_level)
            )
        ]
    )
