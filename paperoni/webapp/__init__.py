from .common import config

cfg = config()

if hasattr(cfg, "sentry") and cfg.sentry.use:
    import sentry_sdk

    sentry_sdk.init(
        dsn=cfg.sentry.dsn,
        traces_sample_rate=cfg.sentry.traces_sample_rate,
        environment=cfg.sentry.environment,
    )
