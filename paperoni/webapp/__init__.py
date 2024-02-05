from ..config import papconf

if papconf.sentry and papconf.sentry.use:
    import sentry_sdk

    sentry_sdk.init(
        dsn=papconf.sentry.dsn,
        traces_sample_rate=papconf.sentry.traces_sample_rate,
        environment=papconf.sentry.environment,
    )
