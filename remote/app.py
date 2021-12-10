#! /usr/bin/env python
# -*- coding: utf-8 -*-

import logging
import os
from enum import Enum, unique
from pathlib import Path
from typing import Optional

import sentry_sdk
from flask import Flask
from sentry_sdk.integrations.flask import FlaskIntegration

from remote.blueprints import image_bp, index_bp, network_bp
from remote.config import base

# We use this environment variable to identify the env in which the project should run.
#
# When the project runs, we will load the basic configuration first,
# and then load the corresponding configuration set according to this name.
# It should be set to one of `AppENV`.
APP_ENV_NAME = "APP_ENV"


@unique
class AppENV(Enum):
    DEV = "DEV"
    TEST = "TEST"
    STAGING = "STAGING"
    PROD = "PROD"

    @classmethod
    def detect(cls) -> Optional["AppENV"]:
        _env = os.getenv(APP_ENV_NAME, "").upper()
        try:
            return cls[_env]
        except KeyError:
            return


def init_sentry(dsn: str, env: str = None):
    sentry_sdk.init(
        dsn=dsn,
        integrations=[FlaskIntegration()],
        environment=env,
        # Set traces_sample_rate to 1.0 to capture 100%
        # of transactions for performance monitoring.
        # We recommend adjusting this value in production.
        traces_sample_rate=1.0,
        # By default, the SDK will try to use the SENTRY_RELEASE
        # environment variable, or infer a git commit
        # SHA as release, however you may want to set
        # something more human-readable.
        # release="myapp@1.0.0",
    )


def load_config(flask_app: Flask, env: AppENV):
    # Load basic default config first.
    flask_app.config.from_object(base)
    if not env:
        flask_app.logger.warning("No env specified, skip loading config.")
        return

    # Try to load the configuration according to the env.
    _current_env = env.value.lower()
    if Path(f"remote/config/{_current_env}.py").exists():
        flask_app.config.from_object(f"remote.config.{_current_env}")
    else:
        flask_app.logger.warning("No config file found for env: %s", env.value)

    # Try load each config on base from env.
    for base_config in dir(base):
        # Only load uppercase config in case.
        if not base_config or not base_config.isupper():
            continue
        if base_config in os.environ:
            flask_app.logger.info("Load config: %s from env.", base_config)
            flask_app.config[base_config] = os.getenv(base_config)


def setup_logger(flask_app: Flask):
    # Default log level: `DEBUG` if app is running on debug/test mode, `INFO` otherwise.
    # If `LOG_LEVEL` is actively set in the configuration, the set value shall prevail.
    _loger = logging.getLogger(flask_app.name)

    level = logging.INFO
    if flask_app.debug or flask_app.testing:
        level = logging.DEBUG
    level = flask_app.config.get("LOG_LEVEL", level)
    _loger.setLevel(level)
    # TODO set logger format


def register_blueprint(flask_app: Flask):
    # TODO consider configuring each blueprint with its own `url_prefix`.
    blueprints = [
        index_bp,
        image_bp,
        network_bp,
    ]
    for bp in blueprints:
        flask_app.register_blueprint(bp)


def create_app(name: str = None, env: AppENV = None) -> Flask:
    _app_name = name or __name__
    current_env: Optional[AppENV] = env or AppENV.detect()

    _app = Flask(_app_name)

    # Load config from python module.
    # Make sure to load the configuration before other actions.
    # In case others from relying on the configuration.
    load_config(_app, current_env)

    # Setup logger for whole app.
    setup_logger(_app)

    # Register all blueprints.
    register_blueprint(_app)

    # Init sentry.
    init_sentry(_app.config["SENTRY_DSN"], _app.config["SENTRY_ENVIRONMENT"])

    # Since flask has built-in logging module(based on python native lib `logging`),
    # we use this(`Flask.logger`) instead of others(`logging`/`print`/...)
    # to print logs within the whole project.
    _app.logger.info(
        "Flask app `%s` created! running on `%s` env.", _app.name, current_env
    )

    return _app


app: Flask = create_app()


if __name__ == "__main__":
    app.run()
