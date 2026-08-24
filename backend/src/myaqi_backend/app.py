from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from flask import Flask, Response, g, jsonify, request
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError

from myaqi_backend.config import DEVELOPMENT_MASTER_KEY, Settings
from myaqi_backend.database import make_engine, make_session_factory
from myaqi_backend.errors import ApiError
from myaqi_backend.ingestion import blueprint as ingestion_blueprint
from myaqi_backend.logging_config import configure_logging
from myaqi_backend.metrics import Metrics


def create_app(
    config: dict[str, Any] | None = None,
    *,
    engine: Engine | None = None,
) -> Flask:
    settings = Settings.from_env()
    app = Flask(__name__)
    app.config.update(settings.as_flask_config())
    if config:
        app.config.update(config)

    configure_logging(str(app.config["LOG_LEVEL"]))
    logger = logging.getLogger("myaqi.api")
    if app.config["DEVICE_MASTER_KEY"] == DEVELOPMENT_MASTER_KEY and not app.config.get("TESTING"):
        logger.warning("Using development DEVICE_MASTER_KEY; do not deploy this configuration")

    database_engine = engine or make_engine(
        str(app.config["DATABASE_URL"]),
        testing=bool(app.config.get("TESTING")),
    )
    app.extensions["myaqi_engine"] = database_engine
    app.extensions["myaqi_session_factory"] = make_session_factory(database_engine)
    app.extensions["myaqi_metrics"] = Metrics()
    app.register_blueprint(ingestion_blueprint)

    @app.before_request
    def begin_request() -> None:
        supplied = request.headers.get("X-Request-ID", "")
        g.request_id = supplied[:128] if supplied else str(uuid.uuid4())
        g.request_started = time.perf_counter()

    @app.after_request
    def finish_request(response):
        response.headers["X-Request-ID"] = g.get("request_id", "")
        logger.info(
            "request_completed",
            extra={
                "request_id": g.get("request_id"),
                "method": request.method,
                "path": request.path,
                "status": response.status_code,
                "duration_ms": round(
                    (time.perf_counter() - g.get("request_started", time.perf_counter())) * 1000,
                    2,
                ),
            },
        )
        return response

    @app.errorhandler(ApiError)
    def handle_api_error(error: ApiError):
        response = jsonify(
            {
                "type": f"https://github.com/rdfds/myaqi-iot-platform/errors/{error.code}",
                "title": error.title,
                "status": error.status,
                "detail": error.detail,
                "request_id": g.get("request_id"),
            }
        )
        response.status_code = error.status
        return response

    @app.errorhandler(SQLAlchemyError)
    def handle_database_error(error: SQLAlchemyError):
        logger.exception("database_request_failed")
        response = jsonify(
            {
                "title": "Database unavailable",
                "status": 503,
                "detail": "The request could not be completed safely",
                "request_id": g.get("request_id"),
            }
        )
        response.status_code = 503
        return response

    @app.get("/health/live")
    def live() -> tuple[dict[str, str], int]:
        return {
            "status": "ok",
            "service": "myaqi-api",
            "version": str(app.config["SERVICE_VERSION"]),
            "revision": str(app.config["APP_REVISION"]),
            "environment": str(app.config["APP_ENVIRONMENT"]),
        }, 200

    @app.get("/health/ready")
    def ready() -> tuple[dict[str, str], int]:
        with database_engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return {
            "status": "ready",
            "revision": str(app.config["APP_REVISION"]),
        }, 200

    @app.get("/metrics")
    def metrics() -> Response:
        registry = app.extensions["myaqi_metrics"].registry
        return Response(generate_latest(registry), mimetype=CONTENT_TYPE_LATEST)

    return app
